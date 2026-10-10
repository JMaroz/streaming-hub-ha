# Handoff: Cast Next Episode Autoplay with Hybrid Notifications & Server-Side Countdown

## Current State
- Completely resolved the issue where Cast playback failed to advance to the next episode on TVs (`media_player.tpm191e`).
- Migrated the next-episode autoplay, countdown, and transition logic to the backend (`ha_client.py`), rendering playback completely independent of mobile sleep/backgrounding states.
- Implemented a hybrid notification system:
  - **In-App Banner**: Integrated in the frontend Cast bar with live countdown, "▶ Riproduci Ora" and "⏹ Annulla" buttons, and automatic episode title/badge refresh.
  - **Actionable Push Notification**: Dispatched via Home Assistant `notify.notify` broadcast with `STREAMING_HUB_PLAY_NEXT` and `STREAMING_HUB_STOP` actions.
  - **Home Assistant WebSocket Event Listener**: Subscribes to `mobile_app_notification_action` for instant remote approval or cancellation without opening the app.
- Enforced strict trigger rules (no arbitrary percentage triggers):
  - Triggers on end-credits metadata (`outro.start`) via SkipDB when available, skipping the rest of the credits at countdown expiry (Netflix-style).
  - Triggers on playback completion (`idle` state after playing) when end-credits metadata is absent.
- Fixed a bug in `castToDevice` where explicit season/episode parameters were overridden by the global UI selection state.
- Fixed a pre-existing integer parsing error in `metadata.py` for runtimes returned as strings (e.g. `'148 min'`).
- Added full unit test coverage in `tests/test_cast_next_episode.py`. All 98 tests in the project pass with 0 regressions.

## Relevant Files
- `streaming_hub/backend/ha_client.py`: Server-side countdown worker (`_run_next_episode_countdown`), prefetching (`_prepare_next_episode`), actionable notification dispatch (`send_next_episode_notification`), WebSocket event listener (`mobile_app_notification_action`), and outro/idle trigger handling in playback tracker.
- `streaming_hub/backend/main.py`: Connected next episode fetcher, skip segments fetcher, and autoplay transition handler; added `POST /api/cast/next-episode/action` and event listener lifecycle hooks.
- `streaming_hub/backend/metadata.py`: Robust runtime parsing handling strings with unit suffixes.
- `streaming_hub/frontend/js/app.js`: Real-time banner countdown synchronization with server, action dispatches, and explicit options handling in `castToDevice`.
- `tests/test_cast_next_episode.py`: 10 comprehensive unit tests for metadata prefetching, outro triggers, idle fallback triggers, notification dispatch, action handling, and API endpoint delegation.
- `docs/plans/2026-10-10_cast_next_episode_autoplay.md`: Plan checklist fully completed.

## Next Steps
- Verify on live Home Assistant setup with physical Cast device (Philips TV `media_player.tpm191e`).
- Suggested Conventional Commit:
  ```bash
  git add streaming_hub/backend/ha_client.py streaming_hub/backend/main.py streaming_hub/backend/metadata.py streaming_hub/frontend/js/app.js tests/test_cast_next_episode.py docs/plans/2026-10-10_cast_next_episode_autoplay.md docs/HANDOFF.md
  git commit -m "feat(cast): server-side next episode autoplay with actionable notifications"
  ```

## Useful Commands
- Run Cast next episode tests: `.venv/bin/pytest tests/test_cast_next_episode.py -v`
- Run full test suite: `.venv/bin/pytest`
