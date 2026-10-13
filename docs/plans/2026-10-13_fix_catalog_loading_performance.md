# Plan: Optimize Catalog & Home Loading Performance

## Objective
Resolve the severe app loading performance degradation introduced in recent commits (v3.0.2 / `cd77884`) by decoupling frontend blocking, bounding dynamic carousel slider fetching, parallelizing multi-source carousel retrieval, and skipping redundant archive queries when upstream sliders provide sufficient items.

## Scope & Non-Goals
- **In Scope**:
  - Bound dynamic sliders in `ReactiveStreamClient.get_homepage_carousels()` to max 4 primary genres (down from 15) and enforce a bounded 6s timeout on batch slider fetches.
  - Parallelize `carousel_sources` execution using `asyncio.gather` with `_safe_call` in `SourceManager.get_home_carousels()`.
  - Avoid redundant `/it/archive` HTTP requests in `ReactiveStreamClient.get_latest_movies()` and `get_latest_tv()` if page 1 slider already yielded sufficient items (>= 12).
  - Decouple `homePromise` (`/api/catalog/home`) from the initial grid display in `streaming_hub/frontend/js/app.js`: unblock the loading spinner and render `state.catalogItems` immediately as soon as `/api/catalog/latest` resolves, loading carousels progressively with active-tab safety checks.
  - Regression testing with unit test suite (`pytest`) and linter (`ruff check`).
- **Non-Goals (YAGNI)**:
  - Do not alter the database schema or rewrite the caching architecture.
  - Do not remove carousels entirely; preserve the rich carousel shelves experience while making it fast and resilient.

## Task Checklist
- [x] Create structured work plan (`docs/plans/2026-10-13_fix_catalog_loading_performance.md`)
- [x] Optimize `streaming_hub/backend/engine_reactive.py`:
  - [x] Bound genre selection in `get_homepage_carousels` to max 4 genres.
  - [x] Add bounded timeout to `_fetch_dynamic_sliders` batches.
  - [x] Conditionally fetch `/it/archive` in `get_latest_movies` and `get_latest_tv` only when `len(items) < 12` or `page > 1`.
- [x] Optimize `streaming_hub/backend/sources/manager.py`:
  - [x] Parallelize `get_home_carousels` across sources using `asyncio.gather` and `_safe_call`.
- [x] Optimize `streaming_hub/frontend/js/app.js`:
  - [x] Make home carousels load progressively without delaying `showLoading(false)` or blocking grid rendering.
  - [x] Add safety check to ensure user is still on Home view before injecting carousels.
- [x] Run test suite (`pytest`) and linter (`ruff`).
- [x] Overwrite `docs/HANDOFF.md` with updated state and DoD verification.

## Verification Strategy
- Run unit test suite: `.venv/bin/pytest tests/test_home_carousels.py tests/test_anime_engine.py -v`
- Run full test suite: `.venv/bin/pytest`
- Run linter and formatting: `.venv/bin/ruff check streaming_hub/ tests/`
