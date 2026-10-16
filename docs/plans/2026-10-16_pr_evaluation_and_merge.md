# Plan: Evaluation and Merging of Open Performance PRs (#21, #22, #23, #24, #25)

## Objective
Evaluate all open GitHub pull requests (excluding #26 release-please), determine code correctness, alignment with project guidelines (Ponytail minimalist philosophy, test coverage, no regressions), resolve merge conflicts resulting from commit `5608d33`, and merge valid PRs cleanly into `main`.

## Scope & Non-Goals
- **In Scope**:
  - PR #21 (`perf/regex-compilation-crawler-parser-13481397741245254065`): Pre-compile regexes in `CrawlerCatalogParser`.
  - PR #22 (`perf/cursor-fetchall-optimization-5980700606779293752`): Cursor streaming instead of `fetchall()` in `database.py`.
  - PR #23 (`perf-optimize-import-items-n1-query-549372766176824421`): Batch queries for `_import_items` / `import_favorites_batch`.
  - PR #24 (`perf/optimize-favorites-sync-loop-3227426585553287857`): TMDb favorites sync loop with batch projection and semaphore concurrency.
  - PR #25 (`perf/asyncio-gather-save-seasons-11691753831184545411`): Concurrent TV series season saving via `asyncio.gather`.
  - Conflict resolution against `5608d33` (`fix(metadata): enrich playback and catalog titles`).
  - Empirical verification via pytest and ruff.
- **Non-Goals**:
  - Merging PR #26 (release-please PR to be managed separately/automatically after these merges).
  - Unrelated refactorings or new feature additions.

## Task Checklist
- [x] Task 1: Deep Review and Conflict Analysis of PR #21 (Crawler Parser Regexes)
- [x] Task 2: Deep Review and Conflict Analysis of PR #22 (Database Cursor Iteration)
- [x] Task 3: Deep Review and Conflict Analysis of PR #23 (Import Items Batch Queries)
- [x] Task 4: Deep Review and Conflict Analysis of PR #24 (Favorites Sync Optimization)
- [x] Task 5: Deep Review and Conflict Analysis of PR #25 (Concurrent TV Season Saving)
- [x] Task 6: Sequential Integration, Conflict Resolution, and Local Verification
- [x] Task 7: Run Full Verification Suite (`ruff check`, `pytest`)
- [x] Task 8: Update Remote Branches, Merge PRs on GitHub, and Push to `main`
- [x] Task 9: Update Documentation (`docs/HANDOFF.md`)

## Verification Strategy
- For each PR: Inspect diff, examine compatibility with `5608d33`.
- Run linter: `.venv/bin/ruff check .`
- Run test suite: `.venv/bin/pytest tests/ -v`
