# Project Instructions

## Daily Digest Routine

The digest routine (`chore: update daily digest` / `chore: digest heartbeat`) commits **directly to `main`**, regardless of any session-level designated branch.

Steps 6–11 of the digest routine (archive, write digest.json, write archive.json, write digest-status.json, commit, push) must all target `origin/main`. Do NOT commit to a feature branch for these files.

## Categories

Twelve, and every one of them is reviewed on its own each day. This list is the source of
truth; the two routine prompts repeat it, so a change here has to be carried into both.

| Category | Scope |
|---|---|
| Java | JDK and JEPs, the runtime, the language and build ecosystem. JVM, not Kotlin. |
| Kotlin | The language, Multiplatform, the toolchain. |
| Spring | Framework and Boot releases, Spring portfolio security advisories. |
| Node | The runtime, npm, release lines, security releases. |
| Go | The language, the toolchain, release notes, security responses. |
| Rust | The language, the toolchain, release notes, security responses. |
| TypeScript | The language and its compiler. The runtime it targets is Node. |
| AI | Frontier models, LLM research, model releases, the shape of the AI industry. |
| Agents | Claude Code, agent frameworks, MCP, context engineering, LLM app engineering. |
| Architecture | System design and engineering practice, in a backend context. |
| Python | Python as the agent-development stack: language, packaging, performance, PyPI security. |
| DataScience | Applied predictive modeling. Frontier LLM research belongs in AI, not here. |

Kotlin, Go, Rust, TypeScript and the Spring security feed are low-volume by design — a
handful of items a month each. They are empty most days, and that is the correct result,
not a gap to fill.

## Item Selection Rules

- **No derivative content**: Do not include quizzes, companion exercises, or any page that is purely a test/supplement for another item already in the digest. Each highlight must stand alone as an independent article.
- **DataScience category**: Must be genuinely about applied statistics, predictive modeling, causal inference, feature engineering, tabular ML, or data pipelines. Career advice, coding interview prep ("how I mastered X in N weeks"), and general Python programming patterns do NOT qualify — skip them even if filed under DataScience by the feed.
- **Duplicate stories**: If the same announcement appears from multiple sources (e.g., company blog + press coverage), pick one source only.
- **How many**: at most ten highlights a day and at most three per category. When a backfill writes several days at once, each day gets its own ten and three. These are ceilings, not targets. Judge importance the way a backend engineer, an AI-agent developer and a senior engineer or software CTO would: releases and version news that change what you build on, security advisories, language and API changes, architecture decisions backed by real numbers, and shifts in tooling. Every item must clear that bar on its own — never pad a category or the day to reach the cap.
- **Order inside a category**: when a category has more eligible candidates than its cap, fill it with security advisories first (tier 0), then new major releases (tier 1: a release titled `x.0` or `x.0.0`, so `Go 1.28` and `Kotlin 2.4.0` are tier 2), then the rest (tier 2). Advisories and major releases count toward the cap. Which item to take within one tier is the model's call. A higher-tier candidate may be left out for a lower one only for a stated reason: the same story is already carried from another source (`duplicate`), or its body could not be read (`unreadable`). Pass it to `check` as `--skip URL duplicate|unreadable` and record it in `data/digest-status.json` under `skipped`. An advisory pushed out by the cap still shows in the security panel when `data/security.json` collects its source (Spring Security, Node.js Security and the other vendor feeds in `fetch_news.py`); a CVE post from a blog such as Cloudflare or Foojay does not.
- **An empty category is a valid result**: the digest is a daily increment, so a category with no news worth carrying that day stays empty. Never substitute a weaker article, and never reach further back in time, just to avoid a gap.
- **Releases and advisories clear the bar on their own**: a language, runtime or framework release that changes what you build on, and any security advisory, qualifies even when the announcement itself is three lines long — the value is the version number and what it breaks, not the prose. This is what Spring, Node, Go and Kotlin are here for. When a release day lands several at once (Spring shipped six on 2026-10-23 and the digest took one), take them, up to the three-per-category cap. Still excluded: patch bumps (`x.y.z` with z ≥ 1) from the seven library release feeds — Transformers, MCP servers, Pydantic AI, LlamaIndex, CrewAI, NumPy and pandas — unless the title or summary says CVE, security or vulnerability; any release whose title marks it alpha, beta, rc, milestone (`-M1`), nightly or canary, unless the same title also ships a final; and Node.js point releases (`x.y.z` with z ≥ 1). A new major line, an LTS transition and a security release are never patch bumps. Node `x.y.0` stays, because its title does not tell an LTS transition from a minor release.
- **Link-roundup newsletters are not articles**: a weekly page that is only a list of links out to other writing ("This Week in Spring") is not independent content — skip it, and take the underlying item instead if that item matters. Latent Space's daily `[AINews]` digest is the same kind. A roundup that carries the substance itself, like InfoQ's Java News Roundup, does qualify.
- **The feed's category stands**: file each highlight under the category its feed assigned, even when the subject would sit just as well elsewhere — an agent-architecture piece from the InfoQ Architecture feed is Architecture, not Agents. The only re-filing is `reclassify()` in `scripts/fetch_news.py`, which moves LLM and agent items out of DataScience.
- **Say nothing you could not read**: if the body is unreachable (403, paywall, a link to a filing or an X post), do not carry the item on its headline alone. Take another source for the same story, or drop it. A `detail` that opens by saying the article could not be read is not a highlight.
- **The script judges what a title can decide**: `scripts/select_digest.py` holds the caps, the tiers and the exclusions above — quizzes (`Quiz:`), link roundups (`[AINews]`, `This Week in …`), library patch bumps, prereleases and Node point releases — with the numbers and feed lists at the top of the file. Both routines run `candidates` before choosing, which lists the window's candidates by category and tier along with the excluded items and why, and `check --candidates FILE` before committing. A digest that fails `check` is not committed. Fix each line it prints and check again: remove an excluded item or one missing from the candidates; for a cap overrun, remove the weakest lowest-tier item in that day and category; for a tier-order violation, swap a lower-tier pick for the higher-tier candidate it names, or pass that candidate with `--skip` if a stated reason applies — never empty the category to make the line go away. Record each removed item in `data/digest-status.json` under `dropped`. A backfill runs `candidates --since/--until` and `check --date` for each day. Choosing within a tier and writing every `summary` and `detail` stay with the model.

## Writing Style

The Korean text in `data/digest.json` and `data/archive.json` — every `summary`,
every `detail`, and the day's overall `summary` — is written in 합쇼체: each
sentence ends in `~습니다`, `~합니다` or `~입니다`. The plain declarative
(`~다`, `~한다`, `~했다`, `~이다`) is not used. Article titles and quoted source
text stay verbatim and are never restyled.

This holds for both digest paths (the local 09:39 KST routine and the cloud
backup) and for anything written back into `archive.json`.
