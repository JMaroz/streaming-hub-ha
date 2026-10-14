# Plan: Fix Home Carousels Visibility, Isolate Anime, and Add Fetch Timing Lookups

## Objective
1. Restore home thematic carousels that stopped appearing in v3.0.4 due to an invalid mode check in `app.js`.
2. Remove anime titles from the generic Home latest grid feed (`type=all`, `type=movie`, `type=tv`) to eliminate severe latency, failed metadata lookups, and mass image proxy flooding.
3. Relegate home anime content strictly to a single dedicated carousel titled "Ultimi Episodi Anime", preserving full catalog access under the dedicated "Anime" tab and global search.
4. Add observability and verification of content fetch latency via `SourceManager` timing lookup and status exposure.

## Scope & Non-Goals
- **In Scope**:
  - Fix mode check in `streaming_hub/frontend/js/app.js` (`state.activeMode !== "latest"` instead of non-existent `"browse"`).
  - Restrict `AnimeSource.supported_types` to `["anime"]` so generic movie/tv latest queries do not query anime feeds twice.
  - Simplify `AnimeStreamClient.get_homepage_carousels()` / `AnimeSource.get_carousels()` to provide solely the single carousel "Ultimi Episodi Anime" (id `anime_latest`) and yield hero priority to main film/series content.
  - Bound upstream HTTP requests in `AnimeStreamClient._request` with `asyncio.timeout(10)`.
  - Add execution duration tracking in `SourceManager._safe_call()`, expose `get_fetch_timings()`, and provide `source_fetch_timings` in `/api/status`.
  - Update unit tests in `tests/test_home_carousels.py` and `tests/test_anime_engine.py` to assert fetch timing lookup and feed isolation.
- **Non-Goals**:
  - Removing anime from global search (anime must remain searchable via `source_manager.search`).
  - Altering the dedicated "Anime" tab (`/api/catalog/anime`) functionality or pagination.
  - Modifying HLS video playback or segment proxy architecture.

## Task Checklist
- [x] Create/Update plan in `docs/plans/2026-10-14_fix_home_carousels_and_anime_isolation.md`
- [x] Fix carousel visibility check in `streaming_hub/frontend/js/app.js`
- [x] Update `AnimeSource.supported_types` in `streaming_hub/backend/sources/anime_source.py`
- [x] Restrict `AnimeSource.get_carousels()` to a single "Ultimi Episodi Anime" carousel and neutral hero
- [x] Bound `AnimeStreamClient._request` with 10s timeout
- [x] Implement timing measurement in `SourceManager._safe_call()` and `get_fetch_timings()`
- [x] Expose `source_fetch_timings` in `/api/status`
- [x] Update and verify test suite in `tests/test_anime_engine.py` with timing lookup and isolation tests
- [x] Run linter (`ruff check .`) and verify 0 issues
- [x] Update `docs/HANDOFF.md`

## Verification Strategy
- **Tests**:
  - Run `.venv/bin/pytest tests/test_anime_engine.py -v` (29 passed in 0.46s)
  - Run full test suite `.venv/bin/pytest` (110 passed in 2.25s)
- **Lint**:
  - Run `.venv/bin/ruff check .` (0 issues)
