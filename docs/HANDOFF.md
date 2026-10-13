# Handoff State — Streaming Hub HA

## Current State
Resolved the severe catalog loading slowness introduced in v3.0.2 (`cd77884`):
- **Root Cause**:
  1. `ReactiveStreamClient.get_homepage_carousels()` requested 18 slider categories (3 editorial + 15 genres) via 3 heavy concurrent POST batches to `/api/sliders/fetch`, causing upstream timeouts, 400+ title payloads, and extreme latency.
  2. `loadHome()` in `app.js` blocked UI unmasking (`showLoading(false)`) by synchronously awaiting `homePromise` (`/api/catalog/home`).
  3. `SourceManager.get_home_carousels()` queried sources in a sequential loop.
  4. `get_latest_movies` / `get_latest_tv` unconditionally made redundant second requests to `/it/archive` on page 1.
- **Resolution**:
  - Bounded dynamic genre sliders to max 4 categories with a 6s batch timeout in `engine_reactive.py`.
  - Conditioned `/it/archive` queries in `get_latest_movies` and `get_latest_tv` to only execute when `page > 1` or `len(items) < 12`.
  - Parallelized multi-source carousel fetching using `asyncio.gather` and `_safe_call` in `SourceManager.get_home_carousels()`.
  - Decoupled `homePromise` in `app.js`: unblocks loading and displays latest grid + hero instantly, injecting carousels progressively with active-tab safety checks.
- **Verification**: All 107 unit tests pass in 2.1s (`.venv/bin/pytest`), and `.venv/bin/ruff check .` passes with 0 issues.

## Relevant Files
- `streaming_hub/backend/engine_reactive.py`: Capped dynamic genres to 4, added 6s batch timeout, conditioned archive fallback.
- `streaming_hub/backend/sources/manager.py`: Concurrent carousel fetching with `asyncio.gather`.
- `streaming_hub/frontend/js/app.js`: Progressive asynchronous home carousel loading without blocking UI.
- `docs/plans/2026-10-13_fix_catalog_loading_performance.md`: Work plan and verification tracking.

## Next Steps
1. Create conventional commit (`fix(catalog): optimize home carousels and latest loading performance`).
2. Rebuild/restart add-on container to verify the instant initial page render in Home Assistant.

## Useful Commands
```bash
# Run test suite
.venv/bin/pytest tests/test_home_carousels.py tests/test_anime_engine.py -v
.venv/bin/pytest

# Run linter
.venv/bin/ruff check .
```
