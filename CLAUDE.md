# Project Instructions

## Daily Digest Routine

The digest routine (`chore: update daily digest` / `chore: digest heartbeat`) commits **directly to `main`**, regardless of any session-level designated branch.

Steps 6–11 of the digest routine (archive, write digest.json, write archive.json, write digest-status.json, commit, push) must all target `origin/main`. Do NOT commit to a feature branch for these files.

## Categories

Ten, and every one of them is reviewed on its own each day. This list is the source of
truth; the two routine prompts repeat it, so a change here has to be carried into both.

| Category | Scope |
|---|---|
| Java | JDK and JEPs, the runtime, the language and build ecosystem. JVM, not Kotlin. |
| Kotlin | The language, Multiplatform, the toolchain. |
| Spring | Framework and Boot releases, Spring portfolio security advisories. |
| Node | The runtime, npm, release lines, security releases. |
| Go | The language, the toolchain, release notes, security responses. |
| AI | Frontier models, LLM research, model releases, the shape of the AI industry. |
| Agents | Claude Code, agent frameworks, MCP, context engineering, LLM app engineering. |
| Architecture | System design and engineering practice, in a backend context. |
| Python | Python as the agent-development stack: language, packaging, performance, PyPI security. |
| DataScience | Applied predictive modeling. Frontier LLM research belongs in AI, not here. |

Kotlin, Go and the Spring security feed are low-volume by design — a handful of items a
month each. They are empty most days, and that is the correct result, not a gap to fill.

## Item Selection Rules

- **No derivative content**: Do not include quizzes, companion exercises, or any page that is purely a test/supplement for another item already in the digest. Each highlight must stand alone as an independent article.
- **DataScience category**: Must be genuinely about applied statistics, predictive modeling, causal inference, feature engineering, tabular ML, or data pipelines. Career advice, coding interview prep ("how I mastered X in N weeks"), and general Python programming patterns do NOT qualify — skip them even if filed under DataScience by the feed.
- **Duplicate stories**: If the same announcement appears from multiple sources (e.g., company blog + press coverage), pick one source only.
- **How many per category**: two is the baseline, not a ceiling. Take up to five when a category genuinely has that many that matter. Judge importance the way a backend engineer, an AI-agent developer and a senior engineer or software CTO would: releases and version news that change what you build on, security advisories, language and API changes, architecture decisions backed by real numbers, and shifts in tooling. A third, fourth or fifth item must clear the same bar as the first two — never pad a category to reach five. Keep the whole digest under about twenty items.
- **An empty category is a valid result**: the digest is a daily increment, so a category with no news worth carrying that day stays empty. Never substitute a weaker article, and never reach further back in time, just to avoid a gap.
- **Releases and advisories clear the bar on their own**: a language, runtime or framework release that changes what you build on, and any security advisory, qualifies even when the announcement itself is three lines long — the value is the version number and what it breaks, not the prose. This is what Spring, Node, Go and Kotlin are here for. When a release day lands several at once (Spring shipped six on 2026-10-23 and the digest took one), take them, up to the five-per-category ceiling. Still excluded: patch-level bumps from library release feeds (LangGraph, Pydantic AI, CrewAI and the like), and Node alpha, nightly and point releases. A new major line, an LTS transition and a security release are never patch bumps.
- **Link-roundup newsletters are not articles**: a weekly page that is only a list of links out to other writing ("This Week in Spring") is not independent content — skip it, and take the underlying item instead if that item matters. A roundup that carries the substance itself, like InfoQ's Java News Roundup, does qualify.
- **The feed's category stands**: file each highlight under the category its feed assigned, even when the subject would sit just as well elsewhere — an agent-architecture piece from the InfoQ Architecture feed is Architecture, not Agents. The only re-filing is `reclassify()` in `scripts/fetch_news.py`, which moves LLM and agent items out of DataScience.
- **Say nothing you could not read**: if the body is unreachable (403, paywall, a link to a filing or an X post), do not carry the item on its headline alone. Take another source for the same story, or drop it. A `detail` that opens by saying the article could not be read is not a highlight.

## Writing Style

The Korean text in `data/digest.json` and `data/archive.json` — every `summary`,
every `detail`, and the day's overall `summary` — is written in 합쇼체: each
sentence ends in `~습니다`, `~합니다` or `~입니다`. The plain declarative
(`~다`, `~한다`, `~했다`, `~이다`) is not used. Article titles and quoted source
text stay verbatim and are never restyled.

This holds for both digest paths (the local 09:39 KST routine and the cloud
backup) and for anything written back into `archive.json`.
