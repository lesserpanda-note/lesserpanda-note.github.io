# Project Instructions

## Daily Digest Routine

The digest routine (`chore: update daily digest` / `chore: digest heartbeat`) commits **directly to `main`**, regardless of any session-level designated branch.

Steps 6–11 of the digest routine (archive, write digest.json, write archive.json, write digest-status.json, commit, push) must all target `origin/main`. Do NOT commit to a feature branch for these files.

## Item Selection Rules

- **No derivative content**: Do not include quizzes, companion exercises, or any page that is purely a test/supplement for another item already in the digest. Each highlight must stand alone as an independent article.
- **DataScience category**: Must be genuinely about applied statistics, predictive modeling, causal inference, feature engineering, tabular ML, or data pipelines. Career advice, coding interview prep ("how I mastered X in N weeks"), and general Python programming patterns do NOT qualify — skip them even if filed under DataScience by the feed.
- **Duplicate stories**: If the same announcement appears from multiple sources (e.g., company blog + press coverage), pick one source only.
