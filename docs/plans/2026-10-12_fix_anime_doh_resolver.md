# Work Plan: Fix Anime and Crawler DoHResolver & Comprehensive Metadata Parsing

## Objective
Fix the failure when initializing the anime (and crawler) streaming engines caused by passing an unexpected keyword argument `provider` to `DoHResolver.__init__()`, and audit/verify that all metadata (titles, years, ratings, genres, episodes, movie sources, and stream resolution) are properly extracted and parsed without errors.

## Scope & Non-Goals
- **In Scope**:
  - Update `DoHResolver.__init__` in `dns_resolver.py` to accept both `mode` and `provider`.
  - Add `get_connector` helper method to `DoHResolver`.
  - Update `AnimeStreamClient` and `CrawlerStreamClient` to use `mode` and configure connectors with `ssl=False`.
  - Fix title cleaning regex in `_clean_title` to use word boundaries `\b`, preventing truncation of titles containing "ita" (e.g., "Titan" -> "Tn").
  - Fix HTML attribute parsing in `_extract_embedded_records` and `get_anime_details` to use quote backreferences (`(["\'])(.*?)\1`), preventing JSON parsing failures on Italian apostrophes (`'`).
  - Populate movie sources in `get_anime_details` for `Movie` objects so anime films can be played.
  - Enrich episode models in `get_tv_season` with individual episode title, plot description, and thumbnail.
  - Add unit tests verifying `_get_session`, `get_anime_details`, `get_latest_releases`, `resolve_stream`, and adapter integration.
- **Non-Goals**:
  - Unrelated backend refactoring (YAGNI).

## Task Checklist
- [x] Create structured work plan (`docs/plans/2026-10-12_fix_anime_doh_resolver.md`)
- [x] Update `streaming_hub/backend/dns_resolver.py` (`__init__` signature & `get_connector`)
- [x] Update `streaming_hub/backend/engine_anime.py` (`_get_session`, `close`, `_clean_title`, backreference regex, movie sources, episode metadata)
- [x] Update `streaming_hub/backend/engine_crawler.py` (`_get_session`)
- [x] Add comprehensive unit tests in `tests/test_anime_engine.py` (22 tests passing)
- [x] Run full test suite (`pytest`, 101 tests passing) and linter (`ruff check`)
- [x] Update `docs/HANDOFF.md` (complete overwrite)
