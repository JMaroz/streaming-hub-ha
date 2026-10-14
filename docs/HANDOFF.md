# Handoff State — Streaming Hub HA

## Current State
Resolved home carousel regression, isolated anime from the Home grid, and added fetch timing lookup observability:
- **Root Causes**:
  1. `app.js` contained a typo checking `state.activeMode !== "browse"` to render carousels; because `state.activeMode` is `"latest"`, the check always aborted early and hid carousels.
  2. `AnimeSource.supported_types` advertised `["tv", "movie", "anime"]`, causing `source_manager.get_latest(media_type="all")` to query anime releases twice per page, polluting the generic Home grid, triggering slow/failed Cinemeta lookups, and flooding the frontend with 30-50+ proxied Anilist image requests.
  3. `AnimeStreamClient.get_homepage_carousels()` emitted two carousels (`anime_latest` and `anime_featured`) and an Anime hero spotlight candidate.
  4. Unbounded upstream anime requests could cause backend delays.
- **Resolution**:
  - Fixed carousel render condition in `app.js` (`state.activeMode !== "latest"` check).
  - Restricted `AnimeSource.supported_types` strictly to `["anime"]`, keeping the main Home latest grid clean of anime entries while preserving full anime access under the dedicated "Anime" tab and global search.
  - Relegated homepage anime carousels to a single shelf "Ultimi Episodi Anime" without overriding the primary hero banner.
  - Added bounded 10s timeout to `AnimeStreamClient._request`.
  - Added execution duration tracking in `SourceManager._safe_call()`, exposed `get_fetch_timings()`, and added `source_fetch_timings` to `/api/status` for real-time latency lookups.
- **Verification**: All 110 unit tests pass in 2.25s (`.venv/bin/pytest`), and `.venv/bin/ruff check .` passes with 0 issues.

## Relevant Files
- `streaming_hub/frontend/js/app.js`: Corrected home carousel active mode verification.
- `streaming_hub/backend/sources/anime_source.py`: Restricted `supported_types` to `["anime"]`.
- `streaming_hub/backend/engine_anime.py`: Single "Ultimi Episodi Anime" carousel and 10s request timeout.
- `streaming_hub/backend/sources/manager.py`: Timing measurement in `_safe_call()` and `get_fetch_timings()`.
- `streaming_hub/backend/main.py`: Expose `source_fetch_timings` in `/api/status`.
- `tests/test_anime_engine.py`: Unit tests for timing lookup, timeout enforcement, and feed isolation.
- `docs/plans/2026-10-14_fix_home_carousels_and_anime_isolation.md`: Work plan and verification tracking.

## Next Steps
1. Review git diff and commit changes using Conventional Commits (`fix(catalog): isolate anime home content and add fetch timing lookups`).
2. Verify in Home Assistant that `/api/status` reports `source_fetch_timings` and the Home page loads with low latency.

## Useful Commands
```bash
# Run targeted tests
.venv/bin/pytest tests/test_anime_engine.py -v

# Run full test suite
.venv/bin/pytest

# Run linter
.venv/bin/ruff check .
```
