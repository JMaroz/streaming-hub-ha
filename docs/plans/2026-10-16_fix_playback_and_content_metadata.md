# Plan: Comprehensive Fix for Missing Titles and Metadata in Playback and Catalog

## Objective
Eliminate missing titles and metadata across both media playback (Google Cast, Home Assistant media player entity, browser web player, OS MediaSession, stream proxy) and catalog content (TV seasons, episodes, movies, carousels, continue watching, search), ensuring full title resolution and metadata enrichment even when no TMDb API key is configured.

## Scope & Non-Goals
- **In Scope**:
  - Enrich Home Assistant Cast `play_media` payload with standard Google Cast `extra.metadata` (metadataType 1 for movies, metadataType 2 for TV episodes, seriesTitle, season, episode, title, images) and preserve metadata in fallback attempts.
  - Implement Web `navigator.mediaSession` API in the frontend so browser playback displays accurate title, season/episode, artist/series name, and artwork in macOS Control Center, Windows media overlays, Android lockscreens, and Chrome media controls.
  - Fix frontend player title display: show full episode designation (`${seriesTitle} - S${season}E${episode}: ${epTitle}`) instead of collapsing to series name.
  - Add free fallback episode metadata enrichment via Cinemeta (`v3-cinemeta.strem.io`) and TVmaze in `metadata.py` so TV seasons and episodes have titles, descriptions, and thumbnails even without a TMDb API key.
  - Enhance `_clean_title` to strip suffixes like `- Serie TV`, `- Stagione \d+`, `- Miniserie`, `- Film`, and marketing keywords that break Cinemeta/TMDb search matching.
  - Fix `slug_to_title` in `database.py` and `getDisplayTitle` in `app.js` to avoid truncating the first word of slug-based identifiers (e.g., `breaking-bad` -> `Breaking Bad`, not `Bad`).
  - Update `_enrich_items_sync` in `database.py` to hydrate `title`, `description`, `year`, `tmdb_id`, and `imdb_id` from SQLite cache into catalog items.
  - Include `Content-Disposition` header with sanitized title in `proxy.py` stream responses so DLNA/Kodi/VLC/Cast receivers can read the media title directly from the stream.
- **Non-Goals**:
  - Re-architecting the streaming proxy protocol.
  - Changing upstream scraping engines beyond metadata parsing and title cleaning.

## Task Checklist
- [x] Task 1: Fix Cast & Home Assistant Playback Metadata (`streaming_hub/backend/ha_client.py` & `streaming_hub/backend/main.py`)
  - [x] Add `media_type`, `series_title`, `season_number`, `episode_number` parameters to `ha_client.play_on_device()`.
  - [x] Construct standard Google Cast `extra["metadata"]` (type 1 for movie, type 2 for tv) with `seriesTitle`, `season`, `episode`, `title`, and `images`.
  - [x] Preserve `title` and `thumb` in Fallback 1 and Fallback 2 attempts.
  - [x] Pass `year`, `tmdb_id`, and `imdb_id` from frontend in `castToDevice()` to `/api/cast`.
  - [x] Clean both `Serie TV - S` and `Senza Titolo - S` prefixes when resolving cast title in `/api/cast`.
- [x] Task 2: Implement MediaSession & Web Player Metadata in Frontend (`streaming_hub/frontend/js/app.js`)
  - [x] Retain full episode title (`Series - S1E1: Title`) for browser player header in `playInBrowser()`.
  - [x] Implement `updateMediaSession(metadata)` using `navigator.mediaSession` with title, artist/series, album/season, and artwork.
  - [x] Clean up `navigator.mediaSession` on player close.
  - [x] Fix `getDisplayTitle()` slug parsing so words are not truncated.
- [x] Task 3: Free Public Fallback for TV Season & Episode Metadata (`streaming_hub/backend/metadata.py`)
  - [x] Add Cinemeta series episodes resolver using IMDb ID (`/meta/series/{imdb_id}.json`).
  - [x] Add TVmaze series episodes resolver using show name (`/singlesearch/shows?q={name}&embed=episodes`).
  - [x] Update `enrich_tv_season()` to fall back to Cinemeta and TVmaze when `tmdb_api_key` or `series_tmdb_id` is missing.
  - [x] Preserve Cinemeta `videos` episode data during `enrich_tv_series()`.
  - [x] Enhance `_clean_title()` to strip `- Serie TV`, `- Stagione \d+`, `- Miniserie`, etc.
- [x] Task 4: Fix Database Cache Hydration & Slug Extraction (`streaming_hub/backend/database.py`)
  - [x] Fix `slug_to_title()` to check if the first split token is numeric before stripping it.
  - [x] Update `_enrich_items_sync()` to SELECT and populate `title`, `description`, `year`, `tmdb_id`, `imdb_id` when missing on items.
- [x] Task 5: Add Media Title Header in Stream Proxy (`streaming_hub/backend/proxy.py`)
  - [x] Support optional `media_title` in `StreamSession` and `register_stream()`.
  - [x] Add `Content-Disposition: inline; filename="{title}.mp4"` / `.m3u8` to proxy stream responses.
- [x] Task 6: Comprehensive Unit & Regression Tests (`tests/`)
  - [x] Unit tests for `extra["metadata"]` structure in `ha_client.py`.
  - [x] Unit tests for Cinemeta & TVmaze season episode fallbacks in `metadata.py`.
  - [x] Unit tests for `_clean_title()` and `slug_to_title()`.
  - [x] Unit tests for `_enrich_items_sync()` cache hydration.
  - [x] Run full test suite and verify 0 ruff lint errors.

## Verification Strategy
- Run unit tests: `.venv/bin/pytest tests/ -v`
- Run linter: `.venv/bin/ruff check .`
