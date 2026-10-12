# Work Plan: Fix Anime and Crawler DoHResolver Keyword Argument & Connector Error

## Objective
Fix the failure when initializing the anime (and crawler) streaming engines caused by passing an unexpected keyword argument `provider` to `DoHResolver.__init__()` and calling non-existent `get_connector()`.

## Scope & Non-Goals
- **In Scope**:
  - Update `DoHResolver.__init__` in `dns_resolver.py` to accept both `mode` and `provider` (defensive alias).
  - Add `get_connector` helper method to `DoHResolver` for clean aiohttp connector instantiation.
  - Update `AnimeStreamClient` in `engine_anime.py` to use `mode` and configure connector with `ssl=False`.
  - Update `CrawlerStreamClient` in `engine_crawler.py` to use `mode` and configure connector consistently.
  - Close `self._resolver` in `AnimeStreamClient.close()`.
  - Add unit tests verifying `_get_session()` creates active sessions with custom DoH DNS without errors.
- **Non-Goals**:
  - Modifying anime parsing logic or third-party API contracts (YAGNI).
  - Modifying UI components or unrelated backend routes.

## Task Checklist
- [x] Create structured work plan (`docs/plans/2026-10-12_fix_anime_doh_resolver.md`)
- [x] Update `streaming_hub/backend/dns_resolver.py` (`__init__` signature & `get_connector`)
- [x] Update `streaming_hub/backend/engine_anime.py` (`_get_session` and `close`)
- [x] Update `streaming_hub/backend/engine_crawler.py` (`_get_session`)
- [x] Add unit tests in `tests/test_anime_engine.py` for session and resolver initialization
- [x] Run test suite (`pytest`) and linter (`ruff check`)
- [x] Update `docs/HANDOFF.md` (complete overwrite)
