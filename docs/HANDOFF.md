# Handoff: Fix Anime Provider DoHResolver & Comprehensive Metadata Parsing

## Current State
- Completely resolved the anime engine startup exception: `DoHResolver.__init__() got an unexpected keyword argument 'provider'`.
- Performed an exhaustive audit on all anime metadata parsing and stream extraction:
  - **Title Cleaning Fix**: Added word boundary markers (`\b`) to `_clean_title` in `engine_anime.py` to prevent corrupting titles containing substrings like "Titan" into "Tn". Stripped dangling punctuation (` -:`).
  - **Apostrophe & JSON Fix**: Refactored regex parsing in `_extract_embedded_records` and `get_anime_details` to use exact quote backreferences (`(["\'])(.*?)\1`), resolving a critical bug where Italian apostrophes (e.g. `un'altra`) prematurely terminated attribute extraction and threw `JSONDecodeError`.
  - **Movie Sources Populated**: Added missing `ProviderSource` resolution for anime `Movie` objects in `get_anime_details`, allowing anime films (e.g., Demon Slayer Mugen Train) to be played directly from the UI without "Nessuna sorgente video disponibile".
  - **Rich Episode Metadata**: Enriched `TvEpisode` objects in `get_tv_season` with individual episode titles, descriptions, and thumbnails when returned by the upstream source.
  - **Vue Props Support**: Enhanced attribute extraction to support Vue dynamic bindings (`:anime`, `:records`, `:episodes`, `:items`).
- Expanded test suite in `tests/test_anime_engine.py` from 8 tests to 22 tests, covering DoH sessions, title variations, TV/movie parsing, episode metadata, VixCloud stream resolution, and adapter routing. All 101 tests in the repository pass with 0 regressions.

## Relevant Files
- `streaming_hub/backend/dns_resolver.py`: Added `provider` parameter alias in `DoHResolver.__init__` and implemented `get_connector()`.
- `streaming_hub/backend/engine_anime.py`: Fixed `_clean_title`, regex quote backreferences, movie source population, episode metadata extraction, and session DoH initialization with `ssl=False`.
- `streaming_hub/backend/engine_crawler.py`: Standardized `DoHResolver` usage with `mode`.
- `tests/test_anime_engine.py`: Added extensive unit tests covering metadata extraction, title sanitization, movie playback sources, and stream resolution.
- `docs/plans/2026-10-12_fix_anime_doh_resolver.md`: Plan updated and completed.

## Next Steps
- Commit the metadata parsing and testing improvements.
- Verify live operation in Home Assistant at `http://192.168.1.67:8123/config/app/f94709c2_streaming_hub/logs`.
- Suggested Conventional Commit:
  ```bash
  git add streaming_hub/backend/engine_anime.py tests/test_anime_engine.py docs/plans/2026-10-12_fix_anime_doh_resolver.md docs/HANDOFF.md
  git commit -m "fix(anime): ensure robust metadata parsing, movie playback sources and regex backreferences"
  ```

## Useful Commands
- Run anime unit tests: `.venv/bin/pytest tests/test_anime_engine.py -v`
- Run full test suite: `.venv/bin/pytest`
- Run linter: `.venv/bin/ruff check .`
