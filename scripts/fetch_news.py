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
from datetime import datetime, timezone
from pathlib import Path

import feedparser

# (feed url, source label, category) — category drives grouping/filtering on the page.
FEEDS = [
    ("https://inside.java/feed.xml", "Inside Java", "Java"),
    ("https://feed.infoq.com/java/", "InfoQ Java", "Java"),
    ("https://spring.io/blog.atom", "Spring Blog", "Spring"),
    ("https://blog.google/technology/ai/rss/", "Google AI", "AI"),
    ("https://huggingface.co/blog/feed.xml", "Hugging Face", "AI"),
    ("https://www.technologyreview.com/topic/artificial-intelligence/feed", "MIT Tech Review", "AI"),
    ("https://openai.com/blog/rss.xml", "OpenAI", "AI"),
    # Agents — Claude Code, agent / harness / context engineering
    ("https://simonwillison.net/atom/everything/", "Simon Willison", "Agents"),
    ("https://www.latent.space/feed", "Latent Space", "Agents"),
    ("https://hnrss.org/newest?q=Claude+Code&points=20", "Hacker News", "Agents"),
    ("https://hnrss.org/newest?q=AI+agents&points=50", "Hacker News", "Agents"),
    ("https://hnrss.org/newest?q=context+engineering&points=10", "Hacker News", "Agents"),
    # LLM / models — latest model & local-LLM trends (Grok, Llama, Ollama)
    ("https://ollama.com/blog/rss.xml", "Ollama", "LLM"),
    ("https://magazine.sebastianraschka.com/feed", "Ahead of AI", "LLM"),
    ("https://importai.substack.com/feed", "Import AI", "LLM"),
    ("https://hnrss.org/newest?q=Grok&points=30", "Hacker News", "LLM"),
    ("https://hnrss.org/newest?q=Llama&points=30", "Hacker News", "LLM"),
]

USER_AGENT = "lesserpanda-note/1.0 (+https://lesserpanda-note.github.io)"
RETENTION_DAYS = 90  # accumulate items, dropping anything older than this
SUMMARY_CHARS = 220
REQUEST_TIMEOUT = 20  # seconds per feed

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "news.json"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


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


def fetch_feed(url: str, source: str, category: str) -> list[dict]:
    items: list[dict] = []
    try:
        parsed = feedparser.parse(url, agent=USER_AGENT)
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


def main() -> int:
    socket.setdefaulttimeout(REQUEST_TIMEOUT)

    existing = load_existing()
    # Accumulate: start from what we already have, fold in fresh entries by link.
    merged: dict[str, dict] = {it["link"]: it for it in existing if it.get("link")}
    for url, source, category in FEEDS:
        for item in fetch_feed(url, source, category):
            merged.setdefault(item["link"], item)  # keep the first-seen copy

    now_ts = int(datetime.now(timezone.utc).timestamp())
    cutoff = now_ts - RETENTION_DAYS * 86_400
    result = [it for it in merged.values() if (it.get("ts") or now_ts) >= cutoff]
    result.sort(key=lambda x: x["ts"] or 0, reverse=True)

    if not result:
        print("WARNING: no items; keeping existing news.json", file=sys.stderr)
        return 0

    # Nothing added or aged out -> leave the file (and its commit) untouched.
    if [it.get("link") for it in result] == [it.get("link") for it in existing]:
        print(f"no change ({len(result)} items)")
        return 0

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "count": len(result),
        "items": result,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(result)} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
