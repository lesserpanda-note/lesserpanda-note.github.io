# Project Instructions

## Daily Digest Routine

The digest routine (`chore: update daily digest` / `chore: digest heartbeat`) commits **directly to `main`**, regardless of any session-level designated branch.

Steps 6–11 of the digest routine (archive, write digest.json, write archive.json, write digest-status.json, commit, push) must all target `origin/main`. Do NOT commit to a feature branch for these files.
