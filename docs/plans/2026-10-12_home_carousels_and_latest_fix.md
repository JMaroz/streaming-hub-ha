# Plan: Home Carousels Expansion & Chronological "Ultimi Arrivi" Fix

## Objective
Fix the missing thematic/editorial carousels on the Home ("Tutti") view and restore true chronological addition ordering for the "Ultimi Arrivi" catalog across both Reactive (`StreamingCommunity`) and Anime (`AnimeUnity`) engines.

## Scope & Non-Goals
- **In Scope**:
  - Fetch dynamic homepage sliders via `POST /api/sliders/fetch?lang=it` in batches of max 6 items in `ReactiveStreamClient.get_homepage_carousels()`.
  - Remove forced `(year, rating)` sorting and `"trending"` slider pollution in `ReactiveStreamClient.get_latest_movies()` and `get_latest_tv()`.
  - Fix broken `&sort=uploaded_at` query parameter on `/it/archive` URLs in `ReactiveStreamClient`.
  - Extract `<the-carousel animes="...">` and `<layout-items items-json="...">` (with `item["anime"]` unwrapping and deduplication) from `/` in `AnimeStreamClient.get_homepage_carousels()` and `get_latest_releases()`.
  - Add unit tests in `tests/test_home_carousels.py` and `tests/test_anime_engine.py`.
- **Non-Goals (YAGNI)**:
  - No frontend HTML/CSS layout structural changes (existing carousel shelf renderer already supports an arbitrary number of carousels).
  - No changes to database schema or stream proxy logic.

## Task Checklist
- [x] Create structured work plan in `docs/plans/2026-10-12_home_carousels_and_latest_fix.md`
- [x] Implement `_fetch_dynamic_sliders` and expand `get_homepage_carousels` in `streaming_hub/backend/engine_reactive.py`
- [x] Fix `get_latest_movies` and `get_latest_tv` in `streaming_hub/backend/engine_reactive.py` (preserve chronological order, exclude `trending`, remove invalid `sort=uploaded_at`)
- [x] Update `_extract_embedded_records`, `get_latest_releases`, and `get_homepage_carousels` in `streaming_hub/backend/engine_anime.py`
- [x] Add unit tests in `tests/test_home_carousels.py` and `tests/test_anime_engine.py`
- [x] Run test suite and `ruff` linter/formatter checks
- [x] Verify empirically against live sources and update `docs/HANDOFF.md`

## Verification Strategy
```bash
.venv/bin/pytest tests/test_home_carousels.py tests/test_anime_engine.py -v
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```
