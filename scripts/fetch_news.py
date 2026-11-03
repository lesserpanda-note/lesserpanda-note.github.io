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
    ("https://blog.google/technology/ai/rss/", "Google AI", "AI"),
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
    ("https://eugeneyan.com/rss/", "Eugene Yan", "Agents"),
    ("https://hnrss.org/newest?q=Claude+Code&points=20", "Hacker News", "Agents"),
    ("https://hnrss.org/newest?q=AI+agents&points=50", "Hacker News", "Agents"),
    ("https://hnrss.org/newest?q=context+engineering&points=10", "Hacker News", "Agents"),
    ("https://hnrss.org/newest?q=MCP&points=20", "Hacker News", "Agents"),
    # Agent frameworks — GitHub release feeds (version tracking; big releases surface).
    ("https://github.com/modelcontextprotocol/servers/releases.atom", "MCP servers", "Agents"),
    ("https://github.com/langchain-ai/langgraph/releases.atom", "LangGraph", "Agents"),
    ("https://github.com/pydantic/pydantic-ai/releases.atom", "Pydantic AI", "Agents"),
    ("https://github.com/openai/openai-agents-python/releases.atom", "OpenAI Agents SDK", "Agents"),
    ("https://github.com/run-llama/llama_index/releases.atom", "LlamaIndex", "Agents"),
    ("https://github.com/crewAIInc/crewAI/releases.atom", "CrewAI", "Agents"),
    ("https://github.com/microsoft/agent-framework/releases.atom", "Agent Framework", "Agents"),
    # Architecture — system design & engineering practice (fits Java/Spring backend)
    ("https://feed.infoq.com/architecture-design/", "InfoQ Architecture", "Architecture"),
    ("https://martinfowler.com/feed.atom", "Martin Fowler", "Architecture"),
    # Python — the AI-agent-development stack (language, packaging, performance, PyPI security)
    ("https://realpython.com/atom.xml", "Real Python", "Python"),
    ("https://blog.python.org/feeds/posts/default", "Python Insider", "Python"),
    ("https://pythonspeed.com/atom.xml", "Python Speed", "Python"),
    # PyPI supply-chain / security incidents & advisories (official blog).
    ("https://blog.pypi.org/feed_rss_created.xml", "PyPI Blog", "Python"),
    # Data Science — applied predictive modeling (scikit-learn / XGBoost / LightGBM /
    # tabular data / feature engineering), the working data-scientist's toolkit
    ("https://machinelearningmastery.com/feed/", "ML Mastery", "DataScience"),
    ("https://www.kdnuggets.com/feed", "KDnuggets", "DataScience"),
    ("https://www.analyticsvidhya.com/feed/", "Analytics Vidhya", "DataScience"),
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

# Some DataScience feeds (Towards Data Science, KDnuggets, ML Mastery) publish a lot of
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


if __name__ == "__main__":
    raise SystemExit(main())
