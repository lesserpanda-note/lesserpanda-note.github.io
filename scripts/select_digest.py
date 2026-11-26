#!/usr/bin/env python3
"""Deterministic half of the daily digest selection.

The digest routines (local SKILL.md and the cloud prompt) leave three things to this
script and keep the rest for the model:

- exclude_reason(): candidates that never qualify — quizzes, link-roundup newsletters,
  patch bumps from library release feeds, prereleases and Node point releases.
- tier(): the priority band inside a category — 0 security advisory, 1 new major
  release, 2 everything else. Which item to take inside a band is the model's call.
- check(): the caps (10 in total, 3 per category), no excluded item, and, in a
  category with more eligible candidates than its cap, no lower band taken while a
  higher one was left out.

Every decision reads only news.json fields (title, source, category, summary), because
the cloud routine cannot open article bodies.
"""
from __future__ import annotations

import re
from collections import Counter

MAX_HIGHLIGHTS = 10
MAX_PER_CATEGORY = 3

# GitHub release feeds of libraries (not languages or runtimes): their patch tags are
# noise unless the notes say security. Feed names as in FEEDS of fetch_news.py.
LIBRARY_RELEASE_FEEDS = frozenset({
    "Transformers", "MCP servers", "Pydantic AI", "LlamaIndex", "CrewAI", "NumPy", "pandas",
})
# The security tripwire feeds; data/security.json collects the same advisories for the panel.
SECURITY_FEEDS = frozenset({"Spring Security", "Node.js Security"})

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


def exclude_reason(item: dict) -> str | None:
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
        return "node_point"
    if item.get("source") in LIBRARY_RELEASE_FEEDS and not first["pre"] and patch >= 1:
        if not _SECURITY_WORDS_RE.search(f"{title} {item.get('summary', '')}"):
            return "patch_bump"
    return None


def tier(item: dict) -> int:
    """Priority band inside a category: 0 security advisory, 1 new major release, 2 the rest."""
    title = item.get("title", "")
    if item.get("source") in SECURITY_FEEDS or _CVE_RE.search(title) or _SECURITY_RELEASE_RE.search(title):
        return TIER_SECURITY
    if _is_release(item) and any(
        not v["pre"] and int(v["minor"]) == 0 and int(v["patch"] or 0) == 0 for v in _versions(title)
    ):
        return TIER_MAJOR
    return TIER_OTHER


def check(highlights: list[dict], candidates: list[dict]) -> list[str]:
    """Rule violations in one day's highlights; an empty list means the day passes.

    `candidates` are that day's news.json items. A highlight is judged through its
    candidate (matched by link), because the digest's own summary is the Korean one
    the model wrote, not the feed text the rules read.
    """
    by_link = {c["link"]: c for c in candidates}
    violations: list[str] = []

    if len(highlights) > MAX_HIGHLIGHTS:
        violations.append(f"{len(highlights)} highlights, over the cap of {MAX_HIGHLIGHTS}")
    per_category = Counter(h["category"] for h in highlights)
    for category, count in per_category.items():
        if count > MAX_PER_CATEGORY:
            violations.append(f"{category}: {count} highlights, over the cap of {MAX_PER_CATEGORY}")

    for h in highlights:
        reason = exclude_reason(by_link.get(h["link"], h))
        if reason:
            violations.append(f"{h['link']}: excluded item ({reason}) — {h['title']}")

    # Tier order binds a category whose eligible candidates outnumber its cap, whether
    # the day filled the category or stopped short of it (the total cap can do that).
    picked = {h["link"] for h in highlights}
    for category in per_category:
        eligible = [
            c for c in candidates
            if c.get("category") == category and exclude_reason(c) is None
        ]
        if len(eligible) <= MAX_PER_CATEGORY:
            continue
        lowest = max(
            tier(by_link.get(h["link"], h)) for h in highlights if h["category"] == category
        )
        left_out: list[tuple[int, dict]] = []
        for c in eligible:
            if c["link"] in picked:
                continue
            c_tier = tier(c)
            if c_tier < lowest:
                left_out.append((c_tier, c))
        if left_out:
            best_tier, best = min(left_out, key=lambda pair: pair[0])
            violations.append(
                f"{category}: took a tier-{lowest} item while {len(left_out)} higher-tier "
                f"candidate(s) were left out, e.g. tier-{best_tier} {best['link']} — {best['title']}"
            )
    return violations
