#!/usr/bin/env python3
"""Deterministic half of the daily digest selection.

The digest routines (local SKILL.md and the cloud prompt) leave three things to this
script and keep the rest for the model:

- exclude_reason(): candidates that never qualify — quizzes, link-roundup newsletters,
  patch bumps from library release feeds, prereleases and Node point releases (unless
  they are a Node security release).
- tier(): the priority band inside a category — 0 security advisory, 1 new major
  release, 2 everything else. Which item to take inside a band is the model's call.
- check(): the caps (10 in total, 3 per category), no excluded item, and, in a
  category with more eligible candidates than its cap, no lower band taken while a
  higher one was left out.

Every decision reads only news.json fields (title, source, category, summary, published),
because the cloud routine cannot open article bodies. The one outside input is the dates
of Node's "Security Releases" advisories in data/security.json: the Node.js Blog feed
has no summary, so its point releases can only be told apart from a security release by
an advisory within NODE_ADVISORY_WINDOW of them.

CLI, run from the repo root before and after the model's selection:

  python scripts/select_digest.py candidates [--since ISO] [--until ISO] > candidates.json
  python scripts/select_digest.py check --candidates candidates.json [--date YYYY-MM-DD]
                                        [--skip URL duplicate|unreadable]...

`candidates` applies STEP 2 of the routine (the window since the last digest) and the
exclusions, grouped by category and tier. `check` judges data/digest.json, or the
archive.json day given by --date, against the candidates saved for that window — saved,
because once the digest is written the previous `updated` that bounded it is gone.
It prints one line per violation and exits 1 if there is any.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Collection, Iterable, Mapping
from datetime import datetime, timedelta
from pathlib import Path

MAX_HIGHLIGHTS = 10
MAX_PER_CATEGORY = 3

# GitHub release feeds of libraries (not languages or runtimes): their patch tags are
# noise unless the notes say security. Feed names as in FEEDS of fetch_news.py.
LIBRARY_RELEASE_FEEDS = frozenset({
    "Transformers", "MCP servers", "Pydantic AI", "LlamaIndex", "CrewAI", "NumPy", "pandas",
})
# The security tripwire feeds; data/security.json collects the same advisories for the panel.
SECURITY_FEEDS = frozenset({"Spring Security", "Node.js Security"})

# A Node.js Blog release this close to a Node "Security Releases" advisory is that security
# release. The advisory's feed time is often midnight UTC of the release day, the release
# itself that afternoon (2026-11-11: 00:00Z advisory, 16:45Z releases).
NODE_ADVISORY_WINDOW = timedelta(days=1)

# A late-published item older than this is a backfill from a newly added feed, not news.
PUBLISHED_WINDOW = timedelta(days=7)
# Reasons the routine may give for leaving a higher-tier candidate out (M1 gate decision).
SKIP_REASONS = ("duplicate", "unreadable")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
# news.json fields carried into the `candidates` output, which `check` reads back.
CANDIDATE_FIELDS = ("title", "link", "source", "category", "summary", "published", "collected_at")

TIER_SECURITY = 0
TIER_MAJOR = 1
TIER_OTHER = 2

_QUIZ_RE = re.compile(r"^Quiz:", re.I)
# Latent Space's daily X/Reddit digest and the "This Week in Spring"-style link lists.
# InfoQ's "... News Roundup" carries the substance itself and is deliberately not matched.
_ROUNDUP_RE = re.compile(r"^(?:\[AINews\]|This Week in\b)", re.I)
_SECURITY_WORDS_RE = re.compile(r"\b(?:CVE|security|vulnerabilit(?:y|ies))\b", re.I)
_CVE_RE = re.compile(r"\bCVE-\d{4}-\d+", re.I)
_SECURITY_RELEASE_RE = re.compile(r"\bsecurity releases?\b", re.I)
_NODE_RELEASE_RE = re.compile(r"^Node\.js v?\d+\.\d+\.\d+")

# A version token: 5.0.0, v2.75.0, 2026.0.0, 1.0. The optional suffix marks a
# prerelease in the spellings the feeds use: -alpha.0, -RC2, .CR1, .Beta4, " alpha 2",
# -M3, and PEP 440's 0.3a0 / 1.0b2. The lookbehind keeps "go1.27.4" and the tail of
# "27.0.0-alpha.0.1.1" from being read as versions of their own.
_PRERELEASE = r"(?:[.\s-]?(?:alpha|beta|rc|cr|nightly|canary)(?![a-z])(?:[.\s]?\d+)?|-m\d+|[ab]\d+)"
_VERSION_RE = re.compile(
    rf"(?<![\w.])v?(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?(?:\.\d+)?(?P<pre>{_PRERELEASE})?",
    re.I,
)
# What may follow the version in a title that only announces a release.
_RELEASE_WORDS = frozenset(
    "and ga available now released release is out has been reaches general availability final".split()
)
_MAX_NAME_WORDS = 4


def _versions(title: str) -> list[re.Match[str]]:
    return list(_VERSION_RE.finditer(title))


def _release_shaped(title: str) -> bool:
    """True for a title that announces a release and says nothing else.

    "Spring Cloud 2026.0.0 (aka Paddington) Has Been Released" is one; "Kodee's Kotlin
    Roundup: ..., Kotlin 2.5.0-Beta2, ..." and "DuckDB 2.0 vs Polars 2.0 ..." are
    articles that mention a version.
    """
    title = re.sub(r"\([^)]*\)", " ", title)
    first = _VERSION_RE.search(title)
    if first is None:
        return False
    name = title[: first.start()]
    if ":" in name or len(name.split()) > _MAX_NAME_WORDS:
        return False
    rest = _VERSION_RE.sub(" ", title[first.start():]).lower()
    return all(w in _RELEASE_WORDS or w.isdigit() for w in re.findall(r"[a-z]+|\d+", rest))


def _is_release(item: dict) -> bool:
    return item.get("source") in LIBRARY_RELEASE_FEEDS or _release_shaped(item.get("title", ""))


def _node_security_release(item: dict, node_security_advisories: Collection[datetime]) -> bool:
    """A final Node.js release published within NODE_ADVISORY_WINDOW of a security advisory."""
    title = item.get("title", "")
    published = item.get("published")
    if not (node_security_advisories and published and item.get("source") == "Node.js Blog"
            and _NODE_RELEASE_RE.match(title)):
        return False
    if any(v["pre"] for v in _versions(title)):
        return False
    released = _parse_time(published)
    return any(abs(released - a) <= NODE_ADVISORY_WINDOW for a in node_security_advisories)


def exclude_reason(item: dict, node_security_advisories: Collection[datetime] = ()) -> str | None:
    """Why a news.json item can never be a highlight, or None if it may be."""
    title = item.get("title", "").strip()
    if _QUIZ_RE.match(title):
        return "quiz"
    if _ROUNDUP_RE.match(title):
        return "roundup"
    if not _is_release(item):
        return None
    versions = _versions(title)
    if not versions:
        return None
    # "Hibernate Reactive 5.1.0.CR3 and 5.0.0.Final released" ships a final, so it stays.
    if all(v["pre"] for v in versions):
        return "prerelease"
    first = versions[0]
    patch = int(first["patch"] or 0)
    if item.get("source") == "Node.js Blog" and _NODE_RELEASE_RE.match(title) and patch >= 1:
        if not _node_security_release(item, node_security_advisories):
            return "node_point"
    if item.get("source") in LIBRARY_RELEASE_FEEDS and not first["pre"] and patch >= 1:
        if not _SECURITY_WORDS_RE.search(f"{title} {item.get('summary', '')}"):
            return "patch_bump"
    return None


def tier(item: dict, node_security_advisories: Collection[datetime] = ()) -> int:
    """Priority band inside a category: 0 security advisory, 1 new major release, 2 the rest."""
    title = item.get("title", "")
    if (item.get("source") in SECURITY_FEEDS or _CVE_RE.search(title) or _SECURITY_RELEASE_RE.search(title)
            or _node_security_release(item, node_security_advisories)):
        return TIER_SECURITY
    if _is_release(item) and any(
        not v["pre"] and int(v["minor"]) == 0 and int(v["patch"] or 0) == 0 for v in _versions(title)
    ):
        return TIER_MAJOR
    return TIER_OTHER


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _window_bound(value: str) -> datetime:
    """--since/--until: an ISO time with an offset, since the data's times all carry one."""
    try:
        parsed = _parse_time(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(f"{value!r} has no UTC offset, e.g. 2026-11-27T00:06:00Z")
    return parsed


def select_candidates(items: Iterable[dict], updated: datetime, known_links: set[str],
                      since: datetime | None = None, until: datetime | None = None) -> list[dict]:
    """News items that are up for review in the window (since, until].

    STEP 2 of the routine: collected after the last digest, published within
    PUBLISHED_WINDOW of it unless it is a security advisory (those arrive days late and
    still matter), and not carried by any earlier digest. `updated` is that last
    digest's time. A backfill cuts the days by collection time alone, so `since` and
    `until` move the window while the 7-day guard stays anchored to `updated`.
    """
    since = since or updated
    oldest = updated - PUBLISHED_WINDOW
    out = []
    for it in items:
        collected = _parse_time(it["collected_at"])
        if collected <= since or (until is not None and collected > until):
            continue
        if it["link"] in known_links:
            continue
        advisory = it.get("source") in SECURITY_FEEDS or "CVE" in it.get("title", "")
        if not advisory:
            published = it.get("published")
            if not published or _parse_time(published) <= oldest:
                continue
        out.append(it)
    return out


def check(highlights: list[dict], candidates: list[dict],
          skipped: Mapping[str, str] | None = None,
          node_security_advisories: Collection[datetime] = (),
          feed_links: Collection[str] = ()) -> list[str]:
    """Rule violations in one day's highlights; an empty list means the day passes.

    `candidates` are that day's news.json items. A highlight is judged through its
    candidate (matched by link), because the digest's own summary is the Korean one
    the model wrote, not the feed text the rules read. `skipped` maps the link of a
    candidate the routine left out on purpose to one of SKIP_REASONS; it drops out of
    the tier-order check. `node_security_advisories` are those the candidates were judged
    with. `feed_links` are every news.json link: a highlight outside the candidates is a
    violation when it is a feed item from another window, and allowed when it is another
    source for the same story, which CLAUDE.md tells the routine to take.
    """
    skipped = skipped or {}
    by_link = {c["link"]: c for c in candidates}
    violations: list[str] = []

    if len(highlights) > MAX_HIGHLIGHTS:
        violations.append(f"{len(highlights)} highlights, over the cap of {MAX_HIGHLIGHTS}")
    per_category = Counter(h["category"] for h in highlights)
    for category, count in per_category.items():
        if count > MAX_PER_CATEGORY:
            violations.append(f"{category}: {count} highlights, over the cap of {MAX_PER_CATEGORY}")

    for h in highlights:
        if h["link"] not in by_link and h["link"] in feed_links:
            violations.append(f"{h['link']}: a feed item outside this window's candidates — {h['title']}")
            continue
        reason = exclude_reason(by_link.get(h["link"], h), node_security_advisories)
        if reason:
            violations.append(f"{h['link']}: excluded item ({reason}) — {h['title']}")

    # Tier order binds a category whose eligible candidates outnumber its cap, whether
    # the day filled the category or stopped short of it (the total cap can do that).
    picked = {h["link"] for h in highlights}
    for category in per_category:
        eligible = [
            c for c in candidates
            if c.get("category") == category and exclude_reason(c, node_security_advisories) is None
            and c["link"] not in skipped
        ]
        if len(eligible) <= MAX_PER_CATEGORY:
            continue
        lowest = max(
            tier(by_link.get(h["link"], h), node_security_advisories)
            for h in highlights if h["category"] == category
        )
        left_out: list[tuple[int, dict]] = []
        for c in eligible:
            if c["link"] in picked:
                continue
            c_tier = tier(c, node_security_advisories)
            if c_tier < lowest:
                left_out.append((c_tier, c))
        if left_out:
            best_tier, best = min(left_out, key=lambda pair: pair[0])
            violations.append(
                f"{category}: took a tier-{lowest} item while {len(left_out)} higher-tier "
                f"candidate(s) were left out, e.g. tier-{best_tier} {best['link']} — {best['title']}"
            )
    return violations


def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def node_security_advisories(security: dict) -> list[datetime]:
    """Times of Node's "Security Releases" advisories in data/security.json."""
    return sorted({
        _parse_time(a["published"])
        for a in security["items"]
        if a.get("source") == "Node.js Security" and a.get("published")
        and _SECURITY_RELEASE_RE.search(a.get("title", ""))
    })


def _known_links(digest: dict, archive: dict) -> set[str]:
    days = [digest, *archive["digests"]]
    return {h["link"] for day in days for h in day.get("highlights", [])}


def cmd_candidates(args: argparse.Namespace) -> int:
    digest = _load("digest.json")
    updated = _parse_time(digest["updated"])
    since = args.since or updated
    window = select_candidates(
        _load("news.json")["items"], updated, _known_links(digest, _load("archive.json")),
        since, args.until,
    )
    advisories = node_security_advisories(_load("security.json"))
    by_category: dict[str, list[dict]] = {}
    excluded = []
    for it in window:
        entry = {k: it.get(k) for k in CANDIDATE_FIELDS}
        reason = exclude_reason(it, advisories)
        if reason:
            excluded.append({**entry, "reason": reason})
        else:
            by_category.setdefault(it["category"], []).append({**entry, "tier": tier(it, advisories)})
    for entries in by_category.values():
        entries.sort(key=lambda e: e["tier"])
    out = {
        "since": since.isoformat(),
        "until": args.until.isoformat() if args.until else None,
        "count": len(window),
        "eligible": len(window) - len(excluded),
        "node_security_advisories": [a.isoformat() for a in advisories],
        "by_category": dict(sorted(by_category.items())),
        "excluded": excluded,
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    saved = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    candidates = [c for entries in saved["by_category"].values() for c in entries]
    candidates += saved["excluded"]
    if args.date:
        days = [d for d in _load("archive.json")["digests"] if d["date"] == args.date]
        if not days:
            print(f"no archive.json day {args.date}", file=sys.stderr)
            return 2
        highlights = days[0]["highlights"]
    else:
        highlights = _load("digest.json")["highlights"]
    if "node_security_advisories" not in saved:
        print(f"{args.candidates} has no node_security_advisories; run `candidates` again",
              file=sys.stderr)
        return 2
    advisories = [_parse_time(a) for a in saved["node_security_advisories"]]
    feed_links = {it["link"] for it in _load("news.json")["items"]}
    violations = check(highlights, candidates, dict(args.skip or []), advisories, feed_links)
    for v in violations:
        print(v)
    if violations:
        return 1
    print(f"ok: {len(highlights)} highlights")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic half of the digest selection.")
    sub = parser.add_subparsers(dest="command", required=True)
    cand = sub.add_parser("candidates", help="list the window's candidates by category and tier")
    cand.add_argument("--since", type=_window_bound,
                      help="window start for a backfill day, default: data/digest.json updated")
    cand.add_argument("--until", type=_window_bound, help="window end for a backfill day")
    cand.set_defaults(func=cmd_candidates)
    chk = sub.add_parser("check", help="check a day's highlights against its saved candidates")
    chk.add_argument("--candidates", required=True, help="the `candidates` output for that window")
    chk.add_argument("--date", help="check this archive.json day instead of data/digest.json")
    chk.add_argument("--skip", nargs=2, action="append", metavar=("URL", "REASON"),
                     help=f"a higher-tier candidate left out on purpose; REASON is one of {SKIP_REASONS}")
    chk.set_defaults(func=cmd_check)
    args = parser.parse_args(argv)
    for _, reason in getattr(args, "skip", None) or []:
        if reason not in SKIP_REASONS:
            parser.error(f"--skip reason must be one of {SKIP_REASONS}, not {reason!r}")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
