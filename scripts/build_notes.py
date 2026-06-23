#!/usr/bin/env python3
"""Render notes/*.md (my insights) into data/notes.json.

Each note may start with an optional YAML-ish front matter block:

    ---
    title: Virtual threads in practice
    date: 2026-06-23
    tags: java, concurrency
    ---
    markdown body...

Missing fields fall back to the filename (``YYYY-MM-DD-slug.md``), the first
``# heading`` in the body, and the file's modification time.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = ROOT / "notes"
OUT = ROOT / "data" / "notes.json"

MD_EXTENSIONS = ["fenced_code", "tables", "sane_lists", "nl2br"]
FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[-_]?(.*)$")
EXCERPT_CHARS = 180

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def parse_front_matter(text: str) -> tuple[dict, str]:
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip().lower()] = val.strip()
    return meta, m.group(2)


def derive_title(meta: dict, body: str, fallback: str) -> str:
    if meta.get("title"):
        return meta["title"]
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return fallback.replace("-", " ").replace("_", " ").strip().title() or "(untitled)"


def derive_date(meta: dict, slug: str, path: Path) -> str:
    if meta.get("date"):
        return meta["date"][:10]
    m = FILENAME_DATE_RE.match(slug)
    if m:
        return m.group(1)
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def parse_tags(meta: dict) -> list[str]:
    raw = meta.get("tags", "").strip().strip("[]")
    return [t.strip() for t in raw.split(",") if t.strip()]


def excerpt_of(html_body: str) -> str:
    plain = _WS_RE.sub(" ", _TAG_RE.sub(" ", html_body)).strip()
    return (plain[: EXCERPT_CHARS - 1].rstrip() + "…") if len(plain) > EXCERPT_CHARS else plain


def main() -> int:
    items: list[dict] = []
    if NOTES_DIR.exists():
        for path in sorted(NOTES_DIR.glob("*.md")):
            meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
            slug = path.stem
            fm = FILENAME_DATE_RE.match(slug)
            html_body = markdown.markdown(body, extensions=MD_EXTENSIONS, output_format="html5")
            items.append(
                {
                    "slug": slug,
                    "title": derive_title(meta, body, fm.group(2) if fm else slug),
                    "date": derive_date(meta, slug, path),
                    "tags": parse_tags(meta),
                    "html": html_body,
                    "excerpt": excerpt_of(html_body),
                }
            )
    items.sort(key=lambda x: (x["date"], x["slug"]), reverse=True)

    payload = {
        "updated": datetime.now().astimezone().isoformat(),
        "count": len(items),
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(items)} notes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
