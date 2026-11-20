#!/usr/bin/env python3
"""Fetch latest Java / Spring / AI news from RSS feeds into data/news.json.

Runs in GitHub Actions on a schedule (pure RSS aggregation, no API keys).
A single dead or slow feed is skipped so it never breaks the whole build, and
if nothing at all comes back the previous data/news.json is left untouched.
"""
from __future__ import annotations

import calendar
import html
import json
import os
import re
import socket
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser

# (feed url, source label, category) — category drives grouping/filtering on the page.
# Categories: Java (JVM), Kotlin, Spring, Node, Go, Rust, TypeScript, AI (incl.
# models/LLM), Agents, Architecture, Python, DataScience (applied predictive modeling —
# scikit-learn/XGBoost/tabular, feature engineering; not frontier LLM research, that's AI).
FEEDS = [
    ("https://inside.java/feed.xml", "Inside Java", "Java"),
    ("https://feed.infoq.com/java/", "InfoQ Java", "Java"),
    ("https://foojay.io/feed/", "Foojay", "Java"),
    # Hibernate ORM releases land directly under Spring Data JPA.
    ("https://in.relation.to/blog.atom", "Hibernate", "Java"),
    # Kotlin stands on its own instead of being folded into Java: under Java it never
    # got reviewed as a bucket, so it reached the digest only when a Java roundup
    # happened to mention it. Supply is low (~6 items/month), so this category is empty
    # most days — a valid result, not a gap to fill.
    ("https://blog.jetbrains.com/kotlin/feed/", "Kotlin", "Kotlin"),
    ("https://spring.io/blog.atom", "Spring Blog", "Spring"),
    # Spring portfolio CVE advisories — sporadic, so it contributes nothing most days and
    # everything on the day one lands. That is the point: it is the security tripwire.
    ("https://spring.io/security.atom", "Spring Security", "Spring"),
    # Node — the other backend runtime. The blog feed carries release announcements
    # (alphas and nightlies included, so the patch-bump rule does the filtering) and
    # the vulnerability feed is the security tripwire, like Spring Security above.
    ("https://nodejs.org/en/feed/blog.xml", "Node.js Blog", "Node"),
    ("https://nodejs.org/en/feed/vulnerability.xml", "Node.js Security", "Node"),
    # Go — the official blog carries design notes and security responses; the release
    # tags are a separate feed because the blog does not announce every point release.
    # go.dev/security/feed.atom is not a feed (301 to a doc page, re-checked 2026-11-03).
    ("https://go.dev/blog/feed.atom", "Go Blog", "Go"),
    ("https://github.com/golang/go/releases.atom", "Go Releases", "Go"),
    # Rust — the official blog plus the release tags, same split as Go. Two feeds are
    # deliberately absent: this-week-in-rust is a links-only weekly, and rustsec.org is
    # the ecosystem advisory DB — unlike Spring Security and the Node one it covers every
    # crate in the index, and a trial run put 25 of 32 Rust items there, 9 on one day,
    # mostly for crates nobody here uses. Product advisories yes, index-wide ones no.
    ("https://blog.rust-lang.org/feed.xml", "Rust Blog", "Rust"),
    ("https://github.com/rust-lang/rust/releases.atom", "Rust Releases", "Rust"),
    # TypeScript — the language itself. The runtime it targets is Node above; the blog
    # announces the named releases and the tags catch the point releases in between.
    ("https://devblogs.microsoft.com/typescript/feed/", "TypeScript Blog", "TypeScript"),
    ("https://github.com/microsoft/TypeScript/releases.atom", "TypeScript Releases", "TypeScript"),
    ("https://openai.com/news/rss.xml", "OpenAI", "AI"),
    ("https://deepmind.google/blog/rss.xml", "DeepMind", "AI"),
    ("https://huggingface.co/blog/feed.xml", "Hugging Face", "AI"),
    ("https://www.technologyreview.com/topic/artificial-intelligence/feed", "MIT Tech Review", "AI"),
    ("https://feed.infoq.com/ai-ml-data-eng/", "InfoQ AI/ML", "AI"),
    # Anthropic still publishes no official RSS (re-checked 2026-11-03: /rss.xml, /feed.xml,
    # /news/rss.xml, /engineering/rss.xml all 404), so a community mirror is the only direct
    # path. This one replaces taobojlen's, which stopped updating on 2026-10-20 and went
    # unnoticed for two weeks, taking the S-1 filing and six other posts with it — it kept
    # answering 200 with 14 stale entries, so nothing in the run looked broken. The HN query
    # below does not cover that gap, contrary to what this comment used to claim: it carries
    # commentary *about* Anthropic, not Anthropic's own announcements, which is precisely what
    # went dark. A second mirror would be the obvious insurance, and the link-keyed merge would
    # dedupe it for free (every mirror emits canonical anthropic.com links), but the two other
    # live ones each inject junk: lingnik.com turns the site's category pages into items
    # ("Models", "Policy", ...), and alan-turing-institute files real headlines under the
    # /news/ index link, which is the worse of the two because the title looks legitimate.
    ("https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml", "Anthropic", "AI"),
    # The same mirror's engineering feed: Anthropic's own posts on Claude Code, agent
    # harnesses and context engineering, which the news feed above does not carry.
    ("https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_engineering.xml", "Anthropic Engineering", "Agents"),
    ("https://hnrss.org/newest?q=Anthropic&points=50", "Hacker News", "AI"),
    # Models / LLM trends folded into AI (weekly newsletters + local-LLM releases).
    ("https://ollama.com/blog/rss.xml", "Ollama", "AI"),
    ("https://magazine.sebastianraschka.com/feed", "Ahead of AI", "AI"),
    ("https://importai.substack.com/feed", "Import AI", "AI"),
    ("https://hnrss.org/newest?q=Grok&points=10", "Hacker News", "AI"),
    ("https://hnrss.org/newest?q=Llama&points=10", "Hacker News", "AI"),
    # The model library itself — releases carry new architectures + security fixes.
    ("https://github.com/huggingface/transformers/releases.atom", "Transformers", "AI"),
    # Agents — Claude Code, agent frameworks, MCP, context engineering, LLM-app eng
    ("https://simonwillison.net/atom/everything/", "Simon Willison", "Agents"),
    ("https://www.latent.space/feed", "Latent Space", "Agents"),
    ("https://hnrss.org/newest?q=Claude+Code&points=20", "Hacker News", "Agents"),
    ("https://hnrss.org/newest?q=AI+agents&points=50", "Hacker News", "Agents"),
    ("https://hnrss.org/newest?q=context+engineering&points=10", "Hacker News", "Agents"),
    ("https://hnrss.org/newest?q=MCP&points=20", "Hacker News", "Agents"),
    # MCP spec releases and SDK news; the spec repo's release feed last moved 2026-07-28.
    ("https://blog.modelcontextprotocol.io/index.xml", "MCP Blog", "Agents"),
    # Agent frameworks — GitHub release feeds (version tracking; big releases surface).
    # These feeds are the only path to these projects: LangChain serves HTML at
    # blog.langchain.com/rss/, llamaindex.ai has no feed, blog.crewai.com stopped in June
    # 2026, and the HN agent queries have never once mentioned one of them (0 of 76 pooled
    # HN items) — a "CrewAI 2.0" headline carries none of the phrases those queries search.
    # So a feed is worth what its release notes carry, not what it has had picked: the
    # patch-bump exclusion only reached the selection rules on 2026-11-03, so every pick
    # before that was made under rules that allowed it. Over each project's last 100
    # releases, counting security wording that falls inside SUMMARY_CHARS, which is all the
    # digest ever reads: Pydantic AI 24, MCP servers 3 of 32, CrewAI 4, LlamaIndex 2, Agent
    # Framework 2, LangGraph 1, OpenAI Agents SDK 0. Those releases are patch-level (CrewAI
    # bumped pypdf and torch for CVEs, LlamaIndex fixed CWE-502 in v0.14.16), so filtering
    # on version shape would drop precisely the items that qualify. LangGraph and the OpenAI
    # SDK went on 2026-11-04: LangGraph pools 29 items a month of which 22 are sub-package
    # tags (langgraph-sdk, -cli, -checkpoint) rather than the framework, and the SDK's own
    # announcements arrive through openai.com/news. Agent Framework went on 2026-11-20:
    # github.com/microsoft/agent-framework answers 404, feed and API alike.
    ("https://github.com/modelcontextprotocol/servers/releases.atom", "MCP servers", "Agents"),
    ("https://github.com/pydantic/pydantic-ai/releases.atom", "Pydantic AI", "Agents"),
    ("https://github.com/run-llama/llama_index/releases.atom", "LlamaIndex", "Agents"),
    ("https://github.com/crewAIInc/crewAI/releases.atom", "CrewAI", "Agents"),
    # Architecture — system design & engineering practice (fits Java/Spring backend)
    ("https://feed.infoq.com/architecture-design/", "InfoQ Architecture", "Architecture"),
    ("https://martinfowler.com/feed.atom", "Martin Fowler", "Architecture"),
    # Infrastructure write-ups with real numbers and vulnerability analyses; product
    # announcements ride along and are left to selection.
    ("https://blog.cloudflare.com/rss/", "Cloudflare", "Architecture"),
    # Git and GitHub platform vulnerabilities, GitHub Security Lab research.
    ("https://github.blog/security/feed/", "GitHub Security", "Architecture"),
    # Korean backend and AI-platform case studies (Spring services, agent platforms on
    # segregated networks). Culture and event posts ride along and are left to selection.
    ("https://toss.tech/rss.xml", "Toss Tech", "Architecture"),
    ("https://techblog.woowahan.com/feed/", "Woowahan Tech", "Architecture"),
    ("https://tech.kakao.com/feed/", "Kakao Tech", "Architecture"),
    # Python — the AI-agent-development stack (language, packaging, performance, PyPI security)
    ("https://realpython.com/atom.xml", "Real Python", "Python"),
    ("https://blog.python.org/feeds/posts/default", "Python Insider", "Python"),
    # PyPI supply-chain / security incidents & advisories (official blog).
    ("https://blog.pypi.org/feed_rss_created.xml", "PyPI Blog", "Python"),
    # PyPI and npm supply-chain incidents as they break — the 2026-11-17 hijack of
    # Microsoft's agent-framework PyPI package reached us through nothing else.
    ("https://socket.dev/api/blog/feed.atom", "Socket", "Python"),
    # Data Science — applied predictive modeling (scikit-learn / XGBoost / LightGBM /
    # tabular data / feature engineering), the working data-scientist's toolkit
    ("https://www.kdnuggets.com/feed", "KDnuggets", "DataScience"),
    ("https://towardsdatascience.com/feed", "Towards Data Science", "DataScience"),
    ("https://statmodeling.stat.columbia.edu/feed/", "Statistical Modeling", "DataScience"),
    # Core numerical / tabular libraries — release feeds (versions + security fixes).
    ("https://github.com/numpy/numpy/releases.atom", "NumPy", "DataScience"),
    ("https://github.com/pandas-dev/pandas/releases.atom", "pandas", "DataScience"),
]

# GitHub Actions runners are UTC, so we can't trust the environment's local time —
# pin KST as a fixed +09:00 offset and convert explicitly. Every timestamp we mint
# here (feed-agnostic "when we collected it") is KST so the digest can group by day
# without re-converting.
KST = timezone(timedelta(hours=9))

USER_AGENT = "lesserpanda-note/1.0 (+https://lesserpanda-note.github.io)"
RETENTION_DAYS = 30  # keep ~1 month; items older than this are dropped on each run
SUMMARY_CHARS = 220
REQUEST_TIMEOUT = 20  # seconds per feed
MAX_WORKERS = 8  # feeds are network-bound; fetch them concurrently, not one by one

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "news.json"
SOURCES_OUT = ROOT / "data" / "sources.json"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Some DataScience feeds (Towards Data Science, KDnuggets) publish a lot of
# LLM / agent / RAG content, which by this category's own definition belongs in AI/Agents
# ("not frontier LLM research, that's AI"). Categorization is per-feed, so we reclassify
# individual items by title: agent / LLM-app tooling -> Agents, frontier-model / LLM -> AI.
# Scoped to DataScience on purpose — Python's theme *is* the AI stack, and Java/Spring AI
# mentions are framework context, so those buckets keep their items. Keyword heuristic, so
# it is deliberately conservative: it under-moves ambiguous items rather than mis-move real
# stats/ML posts (regression, survival analysis, feature engineering all stay put).
# Vendor model names go stale every few months — Kimi, Reflection and Meta Muse all arrived
# after this list was written — so the durable half of the vocabulary is the generic phrasing
# release and eval posts use whoever built the model: "AI model", "reasoning model",
# "open-weight", "world model", "AI assistant". The names that are listed also match glued to
# a prefix (EmbeddingGemma, CodeLlama); requiring a word boundary in front of them missed
# "EmbeddingGemma 2", which then ran as a DataScience highlight on 2026-10-10.
_AGENTS_RE = re.compile(
    r"""(?ix) \b(
        mcp | model\s+context\s+protocol | rag | agentic | agents? | subagents?
        | claude\s+code | langchain | langgraph | llama[-_ ]?index | crew\s?ai
        | context\s+engineering | context\s+windows?
        | prompt(-|\s+)?(engineering|pruning|caching|injection)
        | tool[-\s]?(calling|selection) | vector\s+(dbs?|databases?|searches?|stores?)
        | ai\s+(coding\s+)?assistants?
        | retrieval[-\s]?augmented | react\s+loop
    )\b """
)
_AI_RE = re.compile(
    r"""(?ix) \b(
        llms? | slms? | (small|large)?\s*language\s+models? | chatgpt
        | \w*(gpt(-\w+)?|gemini|gemma|grok|claude|llama|qwen|deepseek)
        | ollama | mistral | phi-\d
        | fine[-\s]?tun\w+ | pretrained\s+models? | generative\s+ai | gen\s?ai
        | foundation\s+models? | diffusion\s+models? | multimodal
        | transformers? | chatbots? | hugging\s?face | openai | anthropic
        | frontier\s+(models?|ai) | ai\s+models? | reasoning\s+models?
        | world\s+models? | open[-\s]?weight | post[-\s]?training
        | text[-\s]?to[-\s]?(image|video|speech)
    )\b """
)


def reclassify(category: str, title: str) -> str:
    """Move LLM/agent items that arrived under DataScience to Agents/AI (see note above)."""
    if category != "DataScience":
        return category
    if _AGENTS_RE.search(title):
        return "Agents"
    if _AI_RE.search(title):
        return "AI"
    return category


def clean_text(raw: str, limit: int = SUMMARY_CHARS) -> str:
    """Strip HTML tags/entities and collapse whitespace, truncating to `limit`."""
    if not raw:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", raw))
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def entry_epoch(entry) -> int | None:
    """UTC epoch seconds from a feed entry, or None if it carries no date."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return calendar.timegm(t)  # struct_time from feedparser is UTC
    return None


def fetch_feed(url: str, source: str, category: str, collected_at: str) -> list[dict]:
    items: list[dict] = []
    try:
        # Fetch the bytes ourselves with a hard timeout, THEN parse in-memory.
        # feedparser.parse(url) does its own network I/O that can hang for many
        # minutes past socket timeouts on a slow feed; urlopen(timeout=...) caps it
        # so one bad feed can't stall the whole build.
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
        parsed = feedparser.parse(raw)
    except Exception as exc:  # network/parse blow-ups must not kill the run
        print(f"  ! {source}: {exc}", file=sys.stderr)
        return items
    if not parsed.entries:
        print(f"  ! {source}: no entries (bozo={getattr(parsed, 'bozo', '?')})", file=sys.stderr)
        return items
    for e in parsed.entries:
        link = e.get("link")
        title = clean_text(e.get("title", ""), 200)
        if not link or not title:
            continue
        ts = entry_epoch(e)
        items.append(
            {
                "title": title,
                "link": link,
                "source": source,
                "category": category,
                "summary": clean_text(e.get("summary") or e.get("description") or ""),
                "ts": ts,
                "published": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
                # When this item first entered our feed (KST). Preserved across runs by
                # the first-seen merge below, so the digest can tell "collected today"
                # apart from an item's original publish date.
                "collected_at": collected_at,
            }
        )
    print(f"  ✓ {source}: {len(items)} items")
    return items


def load_existing() -> list[dict]:
    """Items already on disk, so each run grows the feed instead of resetting it."""
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return prev.get("items", []) if isinstance(prev, dict) else []


def source_home(feed_url: str) -> str:
    """Human-facing homepage for a feed URL (the page shows sources, not raw feeds)."""
    p = urlparse(feed_url)
    host = p.netloc
    if "hnrss.org" in host:
        return "https://news.ycombinator.com/"
    if "anthropic" in feed_url.lower():  # community RSS mirror -> the real news page
        return "https://www.anthropic.com/news"
    if host.startswith("feed.infoq.com") or host.startswith("feed.") and "infoq" in host:
        return "https://www.infoq.com/"
    # GitHub release feeds: .../owner/repo/releases.atom -> the repo page.
    if host == "github.com" and p.path.endswith("/releases.atom"):
        return f"https://github.com{p.path[: -len('/releases.atom')]}"
    return f"{p.scheme}://{host}/"


def write_sources() -> None:
    """Emit data/sources.json (category -> sources) from FEEDS, the single source of
    truth, so the site's 'sources per category' page never drifts from what we fetch."""
    by_category: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()  # (category, source) — dedupe HN's many queries
    for url, source, category in FEEDS:
        key = (category, source)
        if key in seen:
            continue
        seen.add(key)
        by_category.setdefault(category, []).append({"name": source, "url": source_home(url)})
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "categories": [{"category": c, "sources": s} for c, s in by_category.items()],
    }
    SOURCES_OUT.parent.mkdir(parents=True, exist_ok=True)
    SOURCES_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {SOURCES_OUT} ({len(by_category)} categories)")


def main() -> int:
    socket.setdefaulttimeout(REQUEST_TIMEOUT)

    # Always regenerate the sources page data from FEEDS, even when news is unchanged.
    write_sources()
    # Advisories live in their own file with their own retention; runs every time,
    # independent of whether the news below changed.
    try:
        write_security()
    except Exception as exc:  # advisories must never cost the news run
        print(f"  ! security: {exc}", file=sys.stderr)

    # Drop accumulated items whose feed was removed or recategorized, so retiring a
    # source (or moving a feed to another category) actually purges its old items
    # instead of letting them linger for the full retention window. The test is on the
    # (source, category) pair, not on the two independently: when a feed moves to a new
    # category both the old and the new one are still live, so independent checks keep
    # the stale copies — and the merge below prefers the copy already on file, so the
    # feed can never re-file them. Moving the Kotlin feed out of Java hit exactly that.
    # A source can sit in more than one category (Hacker News is both AI and Agents),
    # and reclassify() files some items under a pair FEEDS does not contain, so the
    # feed's own category goes through it before the comparison.
    source_categories: dict[str, set[str]] = {}
    for _, source, category in FEEDS:
        source_categories.setdefault(source, set()).add(category)
    on_disk = load_existing()
    existing = [
        it
        for it in on_disk
        if any(
            reclassify(c, it.get("title", "")) == it.get("category")
            for c in source_categories.get(it.get("source"), ())
        )
    ]
    # Accumulate: start from what we already have, fold in fresh entries by link.
    merged: dict[str, dict] = {it["link"]: it for it in existing if it.get("link")}
    # Feeds are independent and network-bound, so fetch them concurrently — one slow
    # feed no longer serializes the whole run. map() yields results in FEEDS order,
    # so the first-seen dedup below still keeps the earliest-listed source for a link.
    # One collection timestamp (KST) shared by every item fetched this run.
    collected_at = datetime.now(KST).isoformat(timespec="seconds")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        batches = list(pool.map(lambda feed: fetch_feed(*feed, collected_at), FEEDS))
    for items in batches:
        for item in items:
            merged.setdefault(item["link"], item)  # keep the first-seen copy (and its collected_at)

    now_ts = int(datetime.now(timezone.utc).timestamp())
    cutoff = now_ts - RETENTION_DAYS * 86_400
    result = [it for it in merged.values() if (it.get("ts") or now_ts) >= cutoff]
    result.sort(key=lambda x: x["ts"] or 0, reverse=True)

    if not result:
        print("WARNING: no items; keeping existing news.json", file=sys.stderr)
        return 0

    # Items carried over from before this field existed have no collected_at; normalize
    # the key in so every item in the file has it (older ones stay null — we can't know
    # in hindsight when they were first collected).
    for it in result:
        it.setdefault("collected_at", None)
        # Re-file LLM/agent items that came in under DataScience (both fresh and carried
        # over), so the fix also reaches items collected before this rule existed.
        it["category"] = reclassify(it.get("category", ""), it.get("title", ""))

    # Nothing added, aged out, purged or re-filed -> leave the file (and its commit)
    # untouched. The comparison is against what is on disk, not against `existing`,
    # which already has the purged items dropped — otherwise a run whose only effect is
    # a purge compares equal and never writes it out. It carries the category too, so a
    # feed moving to another category counts as a change even though the links match.
    def shape(items: list[dict]) -> list[tuple]:
        return [(it.get("link"), it.get("category")) for it in items]

    if shape(result) == shape(on_disk):
        print(f"no change ({len(result)} items)")
        return 0

    payload = {
        "updated": datetime.now(KST).isoformat(timespec="seconds"),
        "count": len(result),
        "items": result,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(result)} items)")
    return 0


# --- security advisories -----------------------------------------------------------
# A separate list from the news feed: the digest *selects* (five per category at most,
# whatever was visible at 09:39), but an advisory is something to check, not to pick.
# On 2026-11-19 Spring published ~50 advisories just after the morning run and none
# reached the digest. So every official advisory is kept here, for a year, in
# data/security.json, and the page lists them on their own panel.
# Only first-party sources: ecosystem-wide package DBs (GitHub Advisory DB, rustsec)
# are dominated by libraries nobody here uses — see the Rust note in FEEDS.
SECURITY_OUT = ROOT / "data" / "security.json"
SECURITY_RETENTION_DAYS = 365
GO_LOOKBACK_DAYS = 90  # vuln.go.dev needs one request per ID, so only fetch recent ones
# Stored advisories are re-fetched while they may still change: a Go entry modified in
# the last two days (the index says when), an OpenJDK advisory for 30 days after its
# date (the index gives no modified time, and pages gain fixes after release).
GO_REFRESH_DAYS = 2
OPENJDK_REFRESH_DAYS = 30

ORACLE_FEED = "https://www.oracle.com/ocom/groups/public/@otn/documents/webcontent/rss-otn-sec.xml"
OPENJDK_INDEX = "https://openjdk.org/groups/vulnerability/advisories/"
SPRING_FEED = "https://spring.io/security.atom"
NODE_FEED = "https://nodejs.org/en/feed/vulnerability.xml"
GO_INDEX = "https://vuln.go.dev/index/modules.json"
PYTHON_FEED = "https://mail.python.org/archives/list/security-announce@python.org/feed/"
# The Rust blog feed holds only its last ten posts, none of them advisories (checked
# 2026-11-20); the project files its std and Cargo advisories as GitHub advisories.
RUST_REPOS = ("rust-lang/rust", "rust-lang/cargo")

_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.I)
_SPRING_SEVERITY_RE = re.compile(r"\s-\s(CRITICAL|HIGH|MEDIUM|LOW)\s-\s")
_WORD_SEVERITY_RE = re.compile(r"\b(critical|high|medium|low)\s+severity\b", re.I)
_LIST_TAG_RE = re.compile(r"^\[Security-announce\]\s*", re.I)
_OPENJDK_DATE_RE = re.compile(r'href="(?:/groups/vulnerability/advisories/)?(\d{4}-\d{2}-\d{2})"')
# A risk-matrix row: "CVE-2026-114938 hotspot/ compiler 8.1 NHNNUHHH" — the component
# is one to three tokens, then the CVSS score, then the 8-letter vector.
_OPENJDK_SCORE_RE = re.compile(r"CVE-\d{4}-\d{4,}\s+(?:\S+\s+){1,3}?(\d{1,2}\.\d)\s+[A-Z]{8}\b")


def cve_ids(text: str) -> list[str]:
    """CVE IDs in order of first appearance, upper-cased and de-duplicated."""
    return list(dict.fromkeys(m.upper() for m in _CVE_RE.findall(text or "")))


def cvss_severity(score: float | None) -> str | None:
    """CVSS 3.x qualitative rating for a base score."""
    if not score:
        return None
    return "CRITICAL" if score >= 9 else "HIGH" if score >= 7 else "MEDIUM" if score >= 4 else "LOW"


def advisory(ecosystem: str, source: str, title: str, link: str, published: str | None,
             severity: str | None = None, ids: list[str] | None = None) -> dict:
    return {
        "ecosystem": ecosystem,
        "source": source,
        "title": title,
        "link": link,
        "published": published,
        "severity": severity,
        "ids": ids or [],
    }


def parse_feed_advisories(raw: bytes, ecosystem: str, source: str) -> list[dict]:
    """One advisory per RSS/Atom entry. Severity comes from Spring's "- HIGH -" title
    convention or from "LOW severity" wording in the body (Python's announcements)."""
    out = []
    for e in feedparser.parse(raw).entries:
        title = _LIST_TAG_RE.sub("", clean_text(e.get("title", ""), 200))
        link = e.get("link")
        if not title or not link:
            continue
        body = clean_text(e.get("summary") or e.get("description") or "", 2000)
        m = _SPRING_SEVERITY_RE.search(title) or _WORD_SEVERITY_RE.search(body)
        ts = entry_epoch(e)
        out.append(advisory(
            ecosystem, source, title, link,
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
            m.group(1).upper() if m else None,
            cve_ids(f"{title} {body}"),
        ))
    return out


def parse_openjdk_index(page: str) -> list[str]:
    """Advisory dates (YYYY-MM-DD) listed on the OpenJDK advisories index."""
    return list(dict.fromkeys(_OPENJDK_DATE_RE.findall(page)))


def parse_openjdk_advisory(page: str, date: str) -> dict:
    """One advisory per release date; severity is that of its worst CVE."""
    text = clean_text(re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page), 10**7)
    scores = [float(s) for s in _OPENJDK_SCORE_RE.findall(text)]
    return advisory(
        "Java", "OpenJDK",
        f"OpenJDK Vulnerability Advisory: {date.replace('-', '/')}",
        OPENJDK_INDEX + date,
        f"{date}T00:00:00+00:00",
        cvss_severity(max(scores, default=None)),
        cve_ids(text),
    )


def recent_go_ids(index: list[dict], since: str) -> list[str]:
    """Go advisory IDs for the standard library and toolchain modified since `since`."""
    ids = {
        v["id"]
        for mod in index
        if mod.get("path") in ("stdlib", "toolchain")
        for v in mod.get("vulns", [])
        if v.get("modified", "") >= since
    }
    return sorted(ids, reverse=True)


def go_ids_to_fetch(index: list[dict], known: set[str], now: datetime) -> list[str]:
    """Recent Go IDs not stored yet, plus stored ones the index shows as just modified."""
    def since(days: int) -> str:
        return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    changed = set(recent_go_ids(index, since(GO_REFRESH_DAYS)))
    return [i for i in recent_go_ids(index, since(GO_LOOKBACK_DAYS))
            if i in changed or f"https://pkg.go.dev/vuln/{i}" not in known]


def openjdk_dates_to_fetch(dates: list[str], known: set[str], now: datetime) -> list[str]:
    """Advisory dates within retention that are new, or recent enough to still change."""
    cutoff = (now - timedelta(days=SECURITY_RETENTION_DAYS)).date().isoformat()
    refresh = (now - timedelta(days=OPENJDK_REFRESH_DAYS)).date().isoformat()
    return [d for d in dates if d >= cutoff and (d >= refresh or OPENJDK_INDEX + d not in known)]


def parse_go_entry(entry: dict) -> dict:
    vid = entry["id"]
    return advisory(
        "Go", "Go Vulnerability DB",
        f"{vid}: {entry.get('summary', '')}".rstrip(": "),
        f"https://pkg.go.dev/vuln/{vid}",
        entry.get("published"),
        None,  # the Go DB carries no severity rating
        [vid, *entry.get("aliases", [])],
    )


def parse_github_advisories(data: list[dict], ecosystem: str, source: str) -> list[dict]:
    out = []
    for a in data:
        sev = (a.get("severity") or "").upper()
        out.append(advisory(
            ecosystem, source, a.get("summary", ""), a["html_url"], a.get("published_at"),
            sev if sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW") else None,
            [i for i in (a.get("cve_id"), a.get("ghsa_id")) if i],
        ))
    return out


def merge_advisories(existing: list[dict], fresh: list[dict], now: datetime) -> list[dict]:
    """Fold fresh advisories over stored ones by link, drop those past retention, and
    sort newest first. A fresh copy wins, so a re-rated advisory picks up the change."""
    merged = {a["link"]: a for a in existing}
    merged.update((a["link"], a) for a in fresh)
    cutoff = (now - timedelta(days=SECURITY_RETENTION_DAYS)).isoformat()
    # ISO timestamps in different offsets compare correctly only once normalized to UTC.
    def utc(a: dict) -> str:
        p = a.get("published")
        return datetime.fromisoformat(p).astimezone(timezone.utc).isoformat() if p else ""
    # An undated advisory cannot age out, so it is kept rather than dropped unseen.
    kept = [a for a in merged.values() if not a.get("published") or utc(a) >= cutoff]
    kept.sort(key=utc, reverse=True)
    return kept


def _get(url: str) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    # Unauthenticated GitHub API calls share a 60/hour quota per IP, and Actions runners
    # share IPs; the workflow's own token lifts that.
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()


def fetch_security(known: set[str], now: datetime) -> list[dict]:
    """Collect from every source. A failing source logs and contributes nothing, so one
    dead endpoint never costs the others (or the news run) their results. OpenJDK and Go
    need one request per advisory, so those skip stored ones that can no longer change."""

    def openjdk() -> list[dict]:
        index = parse_openjdk_index(_get(OPENJDK_INDEX).decode("utf-8", "replace"))
        dates = openjdk_dates_to_fetch(index, known, now)
        return [parse_openjdk_advisory(_get(OPENJDK_INDEX + d).decode("utf-8", "replace"), d)
                for d in dates]

    def go() -> list[dict]:
        ids = go_ids_to_fetch(json.loads(_get(GO_INDEX)), known, now)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            return list(pool.map(lambda i: parse_go_entry(json.loads(_get(f"https://vuln.go.dev/ID/{i}.json"))), ids))

    def rust() -> list[dict]:
        out = []
        for repo in RUST_REPOS:
            data = json.loads(_get(f"https://api.github.com/repos/{repo}/security-advisories?per_page=100"))
            out += parse_github_advisories(data, "Rust", repo)
        return out

    sources = [
        ("Oracle", lambda: parse_feed_advisories(_get(ORACLE_FEED), "Java", "Oracle")),
        ("OpenJDK", openjdk),
        ("Spring", lambda: parse_feed_advisories(_get(SPRING_FEED), "Spring", "Spring Security")),
        ("Node", lambda: parse_feed_advisories(_get(NODE_FEED), "Node", "Node.js Security")),
        ("Go", go),
        ("Python", lambda: parse_feed_advisories(_get(PYTHON_FEED), "Python", "Python Security")),
        ("Rust", rust),
    ]

    def run(src: tuple) -> list[dict]:
        name, fn = src
        try:
            got = fn()
        except Exception as exc:  # network/parse blow-ups must not kill the run
            print(f"  ! security/{name}: {exc}", file=sys.stderr)
            return []
        print(f"  ✓ security/{name}: {len(got)} new or refreshed")
        return got

    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        return [a for batch in pool.map(run, sources) for a in batch]


def write_security() -> None:
    try:
        on_disk = json.loads(SECURITY_OUT.read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError):
        on_disk = []
    now = datetime.now(timezone.utc)
    items = merge_advisories(on_disk, fetch_security({a["link"] for a in on_disk}, now), now)
    if items == on_disk:
        print(f"security: no change ({len(items)} advisories)")
        return
    payload = {
        "updated": datetime.now(KST).isoformat(timespec="seconds"),
        "count": len(items),
        "items": items,
    }
    SECURITY_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {SECURITY_OUT} ({len(items)} advisories)")


if __name__ == "__main__":
    raise SystemExit(main())
