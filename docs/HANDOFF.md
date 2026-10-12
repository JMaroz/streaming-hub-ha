# Handoff: Fix Anime and Crawler DoHResolver Keyword Argument & Connector Error

## Current State
- Completely resolved the issue causing the anime provider (and crawler provider) to fail during startup and catalog fetch: `DoHResolver.__init__() got an unexpected keyword argument 'provider'`.
- Updated `DoHResolver.__init__` in `dns_resolver.py` to accept both `mode` and `provider` (as a backward-compatible keyword argument), ensuring any calling pattern works seamlessly.
- Added `get_connector(ssl: bool | None = False)` to `DoHResolver` to provide a standard `aiohttp.TCPConnector` configured with the DoH resolver and SSL verification toggle.
- Standardized `AnimeStreamClient._get_session` to pass `mode=self._custom_dns` and use `ssl=False` on the TCPConnector, matching `engine_reactive.py`.
- Standardized `CrawlerStreamClient._get_session` to use `mode=self.custom_dns` and leverage `self._resolver.get_connector()`.
- Ensured `AnimeStreamClient.close()` properly cleans up `self._resolver`.
- Added comprehensive unit tests in `tests/test_anime_engine.py` covering DoH session initialization for both anime and crawler clients, and parameter compatibility. All 94 project tests pass with 0 regressions.

## Relevant Files
- `streaming_hub/backend/dns_resolver.py`: Added `provider` parameter support to `DoHResolver.__init__` and implemented `get_connector()`.
- `streaming_hub/backend/engine_anime.py`: Updated `_get_session()` to use `mode` and `ssl=False`; closed resolver in `close()`.
- `streaming_hub/backend/engine_crawler.py`: Updated `_get_session()` to use `mode=self.custom_dns`.
- `tests/test_anime_engine.py`: Added unit tests for DoH session creation in anime/crawler clients and resolver parameter compatibility.
- `docs/plans/2026-10-12_fix_anime_doh_resolver.md`: Plan checklist fully completed.

## Next Steps
- Rebuild or restart the Streaming Hub Home Assistant add-on to test the anime provider live at `http://192.168.1.67:8123/config/app/f94709c2_streaming_hub/logs`.
- Suggested Conventional Commit:
  ```bash
  git add streaming_hub/backend/dns_resolver.py streaming_hub/backend/engine_anime.py streaming_hub/backend/engine_crawler.py tests/test_anime_engine.py docs/plans/2026-10-12_fix_anime_doh_resolver.md docs/HANDOFF.md
  git commit -m "fix(anime): support provider keyword and add connector helper in DoHResolver"
  ```

## Useful Commands
- Run anime and crawler tests: `.venv/bin/pytest tests/test_anime_engine.py -v`
- Run full test suite: `.venv/bin/pytest`
- Run linter: `.venv/bin/ruff check .`
