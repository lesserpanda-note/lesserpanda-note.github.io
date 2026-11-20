#!/usr/bin/env python3
"""Unit tests for the security-advisory parsers and merge in fetch_news.py.

Run: python scripts/test_security.py   (plain asserts, no pytest dependency)

Samples are trimmed from real responses fetched on 2026-11-20.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fetch_news", Path(__file__).with_name("fetch_news.py"))
fn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fn)

SPRING_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Spring</title>
<entry><title>cve-2026-59273 - CRITICAL - Spring Security ELRequestMatcher allows Remote Code Execution</title>
<link href="https://spring.io/security/cve-2026-59273"/><updated>2026-11-19T00:00:00Z</updated>
<summary>ELRequestMatcher evaluates a provided SpEL expression</summary></entry>
</feed>"""

PYTHON_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>[Security-announce][CVE-2026-16052] Cookie Attribute Injection via Unescaped Semicolons</title>
<link>https://mail.python.org/archives/list/security-announce@python.org/message/IZL4/</link>
<pubDate>Thu, 12 Nov 2026 16:07:16 +0000</pubDate>
<description>There is a LOW severity vulnerability affecting CPython.</description></item>
</channel></rss>"""

NODE_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title><![CDATA[Wednesday, November 11, 2026 Security Releases]]></title>
<link>https://nodejs.org/en/blog/vulnerability/november-2026-security-releases</link>
<pubDate>Wed, 11 Nov 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""

OPENJDK_INDEX = """<ul><li><a href="advisory-key">advisory key</a></li>
<li><a href="2026-11-17">2026/11/17 (latest)</a></li><li><a href="2026-10-24">2026/10/24</a></li>
<li><a href="/groups/vulnerability/advisories/2026-10-20">2026/10/20</a></li></ul>"""

OPENJDK_PAGE = """<html><head><script>var CVE = "CVE-2000-0001 x 9.9 ABCDEFGH";</script></head><body>
<table><tr><td>CVE-2026-114938</td><td>hotspot/ compiler</td><td>8.1</td><td>NHNNUHHH</td></tr>
<tr><td>CVE-2026-114942</td><td>core-libs</td><td>7.0</td><td>NHNNULLH</td></tr>
<tr><td>CVE-2026-114944</td><td>core-svc/ java.lang.management</td><td>5.9</td><td>NHNNUNHN</td></tr>
</table></body></html>"""

GO_INDEX = [
    {"path": "stdlib", "vulns": [
        {"id": "GO-2026-6859", "modified": "2026-11-11T02:51:11Z"},
        {"id": "GO-2025-0001", "modified": "2025-01-01T00:00:00Z"},
    ]},
    {"path": "toolchain", "vulns": [{"id": "GO-2026-6855", "modified": "2026-11-11T02:51:11Z"}]},
    {"path": "golang.org/x/net", "vulns": [{"id": "GO-2026-7000", "modified": "2026-11-12T00:00:00Z"}]},
]

GO_ENTRY = {"id": "GO-2026-6859", "published": "2026-11-11T02:51:11Z", "aliases": ["CVE-2026-97054"],
            "summary": "HTTP/1 server crash due to MaxBytesReader header race in net/http"}

GITHUB_ADVISORIES = [
    {"ghsa_id": "GHSA-p688-r7jv-fm6f", "cve_id": "CVE-2026-1111", "severity": "low",
     "summary": "Cargo can be coerced to share credentials", "html_url": "https://github.com/rust-lang/cargo/security/advisories/GHSA-p688-r7jv-fm6f",
     "published_at": "2026-05-25T15:00:00Z"},
    {"ghsa_id": "GHSA-xxxx", "cve_id": None, "severity": "unknown",
     "summary": "No rating", "html_url": "https://github.com/rust-lang/rust/security/advisories/GHSA-xxxx",
     "published_at": "2026-06-01T00:00:00Z"},
]


def test_spring_severity_and_ids():
    [a] = fn.parse_feed_advisories(SPRING_ATOM, "Spring", "Spring Security")
    assert a["severity"] == "CRITICAL", a
    assert a["ids"] == ["CVE-2026-59273"], a
    assert a["link"] == "https://spring.io/security/cve-2026-59273"
    assert a["published"].startswith("2026-11-19"), a


def test_python_list_tag_stripped_and_word_severity():
    [a] = fn.parse_feed_advisories(PYTHON_RSS, "Python", "Python Security")
    assert a["title"].startswith("[CVE-2026-16052] Cookie"), a["title"]
    assert a["severity"] == "LOW", a
    assert a["ids"] == ["CVE-2026-16052"], a


def test_node_without_severity():
    [a] = fn.parse_feed_advisories(NODE_RSS, "Node", "Node.js Security")
    assert a["title"] == "Wednesday, November 11, 2026 Security Releases", a["title"]
    assert a["severity"] is None and a["ids"] == [], a


def test_openjdk_index_and_page():
    assert fn.parse_openjdk_index(OPENJDK_INDEX) == ["2026-11-17", "2026-10-24", "2026-10-20"]
    a = fn.parse_openjdk_advisory(OPENJDK_PAGE, "2026-11-17")
    assert a["title"] == "OpenJDK Vulnerability Advisory: 2026/11/17"
    assert a["link"] == "https://openjdk.org/groups/vulnerability/advisories/2026-11-17"
    assert a["ids"] == ["CVE-2026-114938", "CVE-2026-114942", "CVE-2026-114944"], a["ids"]  # script ignored
    assert a["severity"] == "HIGH", a  # worst score 8.1, not the 9.9 inside <script>


def test_cvss_bands():
    assert [fn.cvss_severity(s) for s in (9.0, 8.9, 7.0, 4.0, 3.9, 0.1, None)] == \
        ["CRITICAL", "HIGH", "HIGH", "MEDIUM", "LOW", "LOW", None]


def test_go_ids_only_stdlib_and_toolchain_since():
    assert fn.recent_go_ids(GO_INDEX, "2026-08-22T00:00:00Z") == ["GO-2026-6859", "GO-2026-6855"]
    a = fn.parse_go_entry(GO_ENTRY)
    assert a["title"] == "GO-2026-6859: HTTP/1 server crash due to MaxBytesReader header race in net/http"
    assert a["link"] == "https://pkg.go.dev/vuln/GO-2026-6859"
    assert a["ids"] == ["GO-2026-6859", "CVE-2026-97054"] and a["severity"] is None


def test_github_advisories():
    a, b = fn.parse_github_advisories(GITHUB_ADVISORIES, "Rust", "rust-lang/cargo")
    assert a["severity"] == "LOW" and a["ids"] == ["CVE-2026-1111", "GHSA-p688-r7jv-fm6f"], a
    assert b["severity"] is None and b["ids"] == ["GHSA-xxxx"], b


def test_merge_retention_refresh_and_order():
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    old = fn.advisory("Java", "Oracle", "ancient", "https://x/old", "2025-11-01T00:00:00+00:00")
    kept = fn.advisory("Go", "Go", "kept", "https://x/kept", "2026-01-05T00:00:00+00:00", "LOW")
    rerated = fn.advisory("Go", "Go", "kept", "https://x/kept", "2026-01-05T00:00:00+00:00", "HIGH")
    # -07:00 evening is the next day in UTC, so it must sort above the UTC-midnight item
    late = fn.advisory("Java", "Oracle", "late", "https://x/late", "2026-11-17T20:00:00-07:00")
    early = fn.advisory("Spring", "S", "early", "https://x/early", "2026-11-18T00:00:00+00:00")
    undated = fn.advisory("Node", "N", "undated", "https://x/undated", None)
    out = fn.merge_advisories([old, kept], [rerated, early, late, undated], now)
    assert [a["title"] for a in out] == ["late", "early", "kept", "undated"], [a["title"] for a in out]
    assert out[2]["severity"] == "HIGH"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok ({len(tests)} tests)")
