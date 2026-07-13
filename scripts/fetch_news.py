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
# Categories: Java (incl. Kotlin/JVM), Spring, AI (incl. models/LLM), Agents,
# Architecture, Python, DataScience (applied predictive modeling — scikit-learn/
# XGBoost/tabular, feature engineering; not frontier LLM research, that's AI).
FEEDS = [
    ("https://inside.java/feed.xml", "Inside Java", "Java"),
    ("https://feed.infoq.com/java/", "InfoQ Java", "Java"),
    ("https://foojay.io/feed/", "Foojay", "Java"),
    ("https://blog.jetbrains.com/kotlin/feed/", "Kotlin", "Java"),
    ("https://spring.io/blog.atom", "Spring Blog", "Spring"),
    ("https://blog.google/technology/ai/rss/", "Google AI", "AI"),
    ("https://huggingface.co/blog/feed.xml", "Hugging Face", "AI"),
    ("https://www.technologyreview.com/topic/artificial-intelligence/feed", "MIT Tech Review", "AI"),
    ("https://feed.infoq.com/ai-ml-data-eng/", "InfoQ AI/ML", "AI"),
    # Anthropic publishes no official RSS; this is a community mirror of anthropic.com/news.
    ("https://raw.githubusercontent.com/taobojlen/anthropic-rss-feed/main/anthropic_news_rss.xml", "Anthropic", "AI"),
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
    ("https://www.analyticsvidhya.com/blog/feed/", "Analytics Vidhya", "DataScience"),
    ("https://towardsdatascience.com/feed", "Towards Data Science", "DataScience"),
    ("https://simplystatistics.org/index.xml", "Simply Statistics", "DataScience"),
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
_AGENTS_RE = re.compile(
    r"""(?ix) \b(
        mcp | model\s+context\s+protocol | rag | agentic | agents? | subagents?
        | claude\s+code | langchain | langgraph | llama[-_ ]?index | crew\s?ai
        | context\s+engineering | context\s+windows?
        | prompt(-|\s+)?(engineering|pruning|caching|injection)
        | tool[-\s]?(calling|selection) | vector\s+(db|database|search|store)
        | retrieval[-\s]?augmented | react\s+loop
    )\b """
)
_AI_RE = re.compile(
    r"""(?ix) \b(
        llms? | (small|large)?\s*language\s+models? | gpt(-\w+)? | chatgpt
        | gemini | gemma | grok | claude | llama | ollama | qwen | deepseek | phi-\d
        | fine[-\s]?tun\w+ | pretrained\s+models? | generative\s+ai | gen\s?ai
        | foundation\s+models? | diffusion\s+models? | multimodal
        | transformers? | chatbots? | hugging\s?face | openai | anthropic | mistral
        | frontier\s+(models?|ai) | text[-\s]?to[-\s]?(image|video|speech)
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
    # source (or merging a category) actually purges its old items instead of letting
    # them linger for the full retention window.
    active_sources = {source for _, source, _ in FEEDS}
    active_categories = {category for _, _, category in FEEDS}
    existing = [
        it
        for it in load_existing()
        if it.get("source") in active_sources and it.get("category") in active_categories
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

    # Nothing added or aged out -> leave the file (and its commit) untouched.
    if [it.get("link") for it in result] == [it.get("link") for it in existing]:
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
