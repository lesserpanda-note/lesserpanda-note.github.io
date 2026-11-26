#!/usr/bin/env python3
"""Unit tests for the digest selection rules in select_digest.py.

Run: python scripts/test_select_digest.py   (plain asserts, no pytest dependency)

The exclude_reason() and tier() cases use real titles from data/news.json as of
2026-11-27 (collection date in the trailing comment where it matters), so the rules are
pinned to the feeds as they actually write. Three cases come from elsewhere and say so
in their comment: one Node.js Security title from data/security.json, one Spring Blog
title that has aged out of news.json but is still in data/archive.json, and "shape" — a
Node major line, which the feed has not carried in the 30-day window, written the way
its release posts are titled. The check() cases are synthetic: they test the caps and
tier order, which do not depend on wording.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("select_digest", Path(__file__).with_name("select_digest.py"))
_select = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_select)
exclude_reason = _select.exclude_reason
tier = _select.tier
check = _select.check


def item(source: str, title: str, category: str = "", summary: str = "", link: str = "") -> dict:
    return {"source": source, "title": title, "category": category, "summary": summary,
            "link": link or f"https://example.test/{source}/{title}"}


# (source, title, summary) -> expected exclude_reason
EXCLUDE_CASES = [
    # AC3 quizzes
    ("Real Python", "Quiz: LLM Evaluation in Python: Build an Eval Harness From Scratch", "", "quiz"),  # 11-25
    ("Real Python", "Quiz: Understanding Python Namespace Packages", "", "quiz"),
    ("Real Python", "Python 3.15 Ships and Other Python News for November 2026", "", None),
    # AC4 link roundups out, roundups that carry the substance in
    ("Latent Space", "[AINews] Gemini 4 Neon marks GDM's full return as a Frontier Lab", "", "roundup"),  # 11-25
    ("Latent Space", "[AINews] Math Proofs Are Landing Faster Than We Can Read Them", "", "roundup"),  # 11-26
    ("Spring Blog", "This Week in Spring - November 24th, 2026", "", "roundup"),
    ("InfoQ Java", "Java News Roundup: Java4Shell, Oracle CSPUs, OpenJDK, Azul Payara, BellSoft, Helidon, LangChain4j", "", None),
    ("InfoQ Java", "Spring News Roundup: First Release Candidates of Boot, Framework, Data, Security, Modulith, AI", "", None),
    ("Latent Space", "The Revolution vs The Renaissance — Thariq Shihipar, OpenAI", "", None),  # 11-26
    ("Latent Space", "[One Million AI Engineer Special] How Stanford Teaches AI-Native Engineering — Mihail Eric, Monaco", "", None),
    # AC5 patch bumps from library release feeds
    ("CrewAI", "1.15.45", "What's Changed Features Add ability to save HTML or markdown output as a PDF artifact.", "patch_bump"),  # 11-24
    ("Transformers", "Patch release v5.24.1", "Patch release v5.24.1 A patch to fix a bunch of stuff for vLLM", "patch_bump"),  # 11-25
    ("Transformers", "v5.22.1", "v5.22.1", "patch_bump"),
    ("NumPy", "v2.5.5", "NumPy 2.5.5 release", "patch_bump"),
    ("pandas", "pandas 3.1.1", "This is a patch release in the 3.1.x series and includes some regression fixes", "patch_bump"),
    # ... unless the title or the stored summary carries security wording
    ("Pydantic AI", "v1.107.11 (2026-11-24)", "What's Changed 🛡️ Security GHSA-7xcv-6766-v6v5 (medium, CVE-2026-136643)", None),
    ("Transformers", "Patch release v5.22.2", "Some in between patch for security and distributed fixes.", None),
    ("LlamaIndex", "v0.14.26", "Release Notes [2026-11-13] llama-index-agent-agentmesh [0.3.0] Python security relock: all integration uv.lock files (lock files only, no Python floor changes) ( #24039 ) BREAKING: raise requires-python for security fix…", None),
    # ... and minor or major releases are not patch bumps
    ("Transformers", "Release v5.24.0", "Release v5.24.0 New Model additions Inkling 2 Mini", None),
    ("Pydantic AI", "v2.75.0 (2026-11-25)", "What's Changed ⚠️ Compatibility Notes", None),
    ("MCP servers", "v2.5.0", "Security fixes v2.5.0 fixes eight vulnerabilities in three servers.", None),
    # the rule is scoped to library feeds: a Go point release is left to selection
    ("Go Releases", "[release-branch.go1.27] go1.27.4", "", None),
    # AC6 Node alpha and point releases out; new lines, minor/LTS releases and security in
    ("Node.js Blog", "Node.js 27.0.0-alpha.0.1.1 (Alpha)", "", "prerelease"),  # 11-17
    ("Node.js Blog", "Node.js 27.0.0-alpha.0.0.0 (Alpha)", "", "prerelease"),
    ("Node.js Blog", "Node.js 26.13.1 (LTS)", "", "node_point"),  # 11-12
    ("Node.js Blog", "Node.js 22.23.5 (LTS)", "", "node_point"),
    ("Node.js Blog", "Node.js 26.13.0 (LTS)", "", None),  # 11-03, minor on the LTS line
    ("Node.js Blog", "Node.js 27.0.0 (Current)", "", None),  # shape: a new major line
    ("Node.js Blog", "Wednesday, November 11, 2026 Security Releases", "", None),  # 11-04
    ("Node.js Blog", "Notable V8 changes from Node.js 26 to 27 (Alpha)", "", None),  # an article, not a release
    # AC6 prerelease markers on any release-shaped title
    ("Spring Blog", "Spring AI 2.1.0-RC2 Available Now", "", "prerelease"),
    ("Spring Blog", "Spring Boot 4.2.0-RC2 available now", "", "prerelease"),
    ("Spring Blog", "Spring Cloud 2026.0.0-RC2 (aka Paddington) Has Been Released", "", "prerelease"),
    ("Hibernate", "Hibernate 8.0.0.CR1", "", "prerelease"),
    ("Hibernate", "Hibernate 8.0.0.Beta4", "", "prerelease"),
    ("Hibernate", "Hibernate Reactive 5.1.0.Beta1 and 5.0.0.Beta3 released", "", "prerelease"),
    ("Python Insider", "Python 3.16.0 alpha 2 is now available", "", "prerelease"),
    ("Simon Willison", "datasette-charts 0.3a0", "", "prerelease"),
    # a final release announced alongside a candidate stays
    ("Hibernate", "Hibernate Reactive 5.1.0.CR3 and 5.0.0.Final released", "", None),  # 11-26
    ("Spring Blog", "Spring Batch 6.1.0-RC1 and 6.0.6 available now!", "", None),  # archive.json 10-23
    ("Spring Blog", "Spring Boot 4.2.0 available now", "", None),
    # articles that merely mention a prerelease are not releases
    ("Kotlin", "Kodee’s Kotlin Roundup: Shipaton 2026 Winners, Kotlin 2.5.0-Beta2, and KotlinConf 2027", "", None),
    ("Simon Willison", "Ladybird's first alpha release", "", None),
    ("Rust Blog", "Enabling the parallel frontend on nightly", "", None),
    ("Cloudflare", "Quad9’s withdrawal from France: A canary in the coal mine", "", None),
    # AC7 security advisories stay
    ("Spring Security", "cve-2026-59273 - CRITICAL - Spring Security ELRequestMatcher allows Remote Code Execution via unrestricted SpEL evaluation", "", None),  # 11-20
]

# (source, title) -> expected tier
TIER_CASES = [
    ("Spring Security", "cve-2026-59329 - LOW - Spring Security Reactive Authentication Timing Attack Enables Username Enumeration", 0),
    ("Node.js Security", "Wednesday, November 11, 2026 Security Releases", 0),  # security.json
    ("Node.js Blog", "Wednesday, November 11, 2026 Security Releases", 0),
    ("Foojay", "Java4Shell (CVE-2026-114938): What It Is, Who Is Affected, and What to Do Now", 0),  # 11-19
    ("Cloudflare", "How Cloudflare WAF protects against ruby2shell (CVE-2026-132825)", 0),  # 11-21
    ("Spring Blog", "Spring Cloud 2026.0.0 (aka Paddington) Has Been Released", 1),
    ("Hibernate", "Hibernate Reactive 5.1.0.CR3 and 5.0.0.Final released", 1),
    ("InfoQ AI/ML", "Open Source DocumentDB 1.0 Reaches General Availability", 1),
    ("Node.js Blog", "Node.js 27.0.0 (Current)", 1),  # shape
    ("Spring Blog", "Spring Boot 4.2.0 available now", 2),
    ("Rust Blog", "Announcing Rust 1.100.0", 2),
    ("Spring Blog", "Spring Batch 6.1 is now GA!", 2),
    ("Node.js Blog", "Node.js 26.13.0 (LTS)", 2),
    ("Towards Data Science", "DuckDB 2.0 vs Polars 2.0 in Five Real-World Tests and One 14x Gap", 2),
    ("Kotlin", "Kotlin Benchmark 2.0: How AI Coding Agents Handle Harder Tasks and Closed-Source Code", 2),
    ("InfoQ Java", "Java News Roundup: Java4Shell, Oracle CSPUs, OpenJDK, Azul Payara, BellSoft, Helidon, LangChain4j", 2),
]


def _spring_cve(n: int) -> dict:
    return item("Spring Security", f"cve-2026-5933{n} - HIGH - Spring Security advisory {n}", "Spring")


def _article(category: str, n: int) -> dict:
    return item("Some Blog", f"{category} article {n}", category)


def check_cases() -> list[tuple[str, list[dict], list[dict], bool]]:
    """(label, highlights, candidates, expect_violation)"""
    cats = ["Java", "Spring", "AI", "Agents", "Architecture", "Python"]
    ten = [_article(c, n) for c in cats for n in range(2)][:10]
    eleven = ten + [_article("DataScience", 0)]
    three_java = [_article("Java", n) for n in range(3)]
    four_java = three_java + [_article("Java", 3)]
    cves = [_spring_cve(n) for n in range(4)]
    blog = [_article("Spring", n) for n in range(4)]
    quiz = item("Real Python", "Quiz: Python Conditional Statements", "Python")
    ainews = item("Latent Space", "[AINews] Gemini 4 Neon marks GDM's full return as a Frontier Lab", "Agents")
    sec_patch = item("Pydantic AI", "v1.107.11 (2026-11-24)", "Agents",
                     "What's Changed 🛡️ Security GHSA-7xcv-6766-v6v5 (medium, CVE-2026-136643)")
    # the digest carries a Korean summary, not the feed's, so check() reads the candidate's
    sec_patch_highlight = {**sec_patch, "summary": "보안 수정이 들어간 패치입니다."}
    return [
        ("AC1 ten in total passes", ten, ten, False),
        ("AC1 eleven in total fails", eleven, eleven, True),
        ("AC1 three in a category passes", three_java, three_java, False),
        ("AC1 four in a category fails", four_java, four_java, True),
        ("AC2 over-cap category skipping a tier-0 for a tier-2 fails", cves[:2] + blog[:1], cves + blog, True),
        ("AC2 over-cap category of tier-0 passes", cves[:3], cves + blog, False),
        ("AC2 over-cap category stopping short still keeps tier order", blog[:2], cves + blog, True),
        ("AC2 over-cap category taking every tier-0 first passes", cves[:1] + blog[:2], cves[:1] + blog, False),
        ("AC2 category within its cap leaves the choice to selection", blog[:2], cves[:1] + blog[:2], False),
        ("AC3-6 excluded item in the digest fails", [quiz], [quiz], True),
        ("AC4 [AINews] in the digest fails", [ainews], [ainews], True),
        ("AC5 security patch read through its candidate passes", [sec_patch_highlight], [sec_patch], False),
    ]


def main() -> int:
    failed = 0
    total = 0
    for source, title, summary, expected in EXCLUDE_CASES:
        total += 1
        got = exclude_reason(item(source, title, summary=summary))
        if got != expected:
            failed += 1
            print(f"FAIL  exclude_reason({source!r}, {title!r}) = {got!r}, expected {expected!r}")
    for source, title, expected in TIER_CASES:
        total += 1
        got = tier(item(source, title))
        if got != expected:
            failed += 1
            print(f"FAIL  tier({source!r}, {title!r}) = {got!r}, expected {expected!r}")
    for label, highlights, candidates, expect_violation in check_cases():
        total += 1
        got = check(highlights, candidates)
        if bool(got) != expect_violation:
            failed += 1
            print(f"FAIL  check: {label} -> {got!r}")
    if failed:
        print(f"\n{failed}/{total} FAILED")
        return 1
    print(f"all {total} select_digest cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
