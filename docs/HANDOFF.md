# Handoff State — Streaming Hub HA

## Current State
Completed Root-cause Evaluation & Analysis (REA) and implemented the fix for homepage carousels expansion and chronological "Ultimi Arrivi" ordering across both `ReactiveStreamClient` (`StreamingCommunity`) and `AnimeStreamClient` (`AnimeUnity`):
- **Dynamic Homepage Carousels (`StreamingCommunity`)**: Added `_fetch_dynamic_sliders()` in `ReactiveStreamClient` to query `POST /api/sliders/fetch?lang=it` in parallel batches of $\le 6$ items (respecting Laravel's `max:6` validation rule). Expanded `get_homepage_carousels()` from 3 initial Inertia sliders to 21 carousels (`trending`, `latest`, `top10`, `new-episodes`, `top10_movie`, `top10_tv`, plus 15 genre sliders).
- **Chronological "Ultimi Arrivi" (`StreamingCommunity`)**: Removed forced `.sort(key=lambda m: (m.year or 0, m.rating or 0.0), reverse=True)` and `"trending"` slider mixing from `get_latest_movies()` and `get_latest_tv()`. Removed invalid `&sort=uploaded_at` query parameter on `/it/archive` URLs so `/it/archive?type=movie|tv&page={page}` returns the 60 chronological titles per page instead of redirecting to `Home/Home`.
- **Anime Homepage & Latest Releases (`AnimeUnity`)**: Updated `AnimeStreamClient._extract_embedded_records()` to support `animes="..."` attributes, unwrap nested `item["anime"]` episode objects from `<layout-items>`, and deduplicate by anime ID. Switched `get_latest_releases()` and `get_homepage_carousels()` from the alphabetical `/archivio` (`Lista A-Z`) to the chronological homepage `/?page={page}` (`Ultime Uscite Anime` + `Anime in Evidenza`).
- **Verification**: All 105 unit tests pass (`pytest`), `ruff check` and `ruff format --check` pass with 0 issues, and live empirical verification against `streamingcommunityz.shiksha` and `animeunity.so` confirmed 21 + 2 carousels and genuine chronological latest releases.

## Relevant Files
- `streaming_hub/backend/engine_reactive.py`: Added `_fetch_dynamic_sliders()`, expanded `get_homepage_carousels()`, and fixed chronological ordering and `/it/archive` URLs in `get_latest_movies()` / `get_latest_tv()`.
- `streaming_hub/backend/engine_anime.py`: Enhanced `_extract_embedded_records()` (`animes` attribute, `item["anime"]` unwrapping, ID deduplication) and updated `get_latest_releases()` and `get_homepage_carousels()` to use `/` instead of alphabetical `/archivio`.
- `tests/test_home_carousels.py`: Added unit tests for dynamic slider batching ($\le 6$), carousel expansion, and chronological order preservation in `get_latest_movies()`.
- `tests/test_anime_engine.py`: Added unit tests for `/?page=1` chronological episode unwrapping/deduplication and dual homepage carousels (`anime_latest` + `anime_featured`).
- `docs/plans/2026-10-12_home_carousels_and_latest_fix.md`: Structured implementation and verification plan (completed).

## Next Steps
1. Commit the changes using Conventional Commits (`fix(catalog): expand dynamic home carousels and restore chronological latest releases`).
2. Restart or rebuild the local Home Assistant add-on instance (`http://192.168.1.67:8099`) to deploy the updated backend code and clear the in-memory `TTLCache`.
3. Optionally expose genre customization or user-selectable carousel ordering in settings if needed in the future.

## Useful Commands
```bash
# Run unit tests
.venv/bin/pytest -q

# Run linter and formatter checks
.venv/bin/ruff check streaming_hub/backend/engine_reactive.py streaming_hub/backend/engine_anime.py tests/test_home_carousels.py tests/test_anime_engine.py
.venv/bin/ruff format --check streaming_hub/backend/engine_reactive.py streaming_hub/backend/engine_anime.py tests/test_home_carousels.py tests/test_anime_engine.py
```
