# Handoff State — Streaming Hub HA

## Current State
Fixed issue where anime split-cours/sequels (e.g. `GATE Part 2` / `166-gate-part-2`) and SUB/DUB distinct audio releases were erroneously swallowed and hidden during global catalog searches:
- **Root Cause**: `CatalogMerger.titles_match` matched multi-part titles (`words1.issubset(words2)`) when difference only contained sequel tokens/numbers (e.g. `Part 2`) within a 1-year window, merging them into season 1. Additionally, `CatalogMerger.is_same_media` did not prevent merging distinct items with different IDs from the same catalog source or distinct anime audio releases.
- **Resolution**:
  - Added `_SEQUEL_MARKERS` and numeric difference checks in `CatalogMerger.titles_match` so sequels, parts, cour divisions, and numeric increments are never matched as duplicate titles.
  - Updated `CatalogMerger.is_same_media` to protect items from the same provider prefix (e.g. `anime-15` vs `anime-166`) and preserve distinct `dub_type` audio releases.
- **Verification**: All 107 unit tests pass (`python3.14 -m pytest`), including new tests for `GATE Part 1` vs `GATE Part 2` and SUB/DUB preservation. `ruff check` and `ruff format` pass with 0 issues.

## Relevant Files
- `streaming_hub/backend/utils.py`: Added `_SEQUEL_MARKERS`, numeric token checks in `titles_match`, same-source ID protection and dub type separation in `is_same_media`.
- `tests/test_anime_engine.py`: Added `test_source_manager_search_preserves_anime_sequels_and_parts` and `test_source_manager_search_preserves_sub_and_dub_anime_releases`.
- `docs/plans/2026-10-13_fix_catalog_merger_anime_sequels.md`: Structured plan and verification tracking for this task.

## Next Steps
1. Suggest or create a conventional commit (`fix(catalog): prevent CatalogMerger from deduplicating anime sequels and audio variants`).
2. Rebuild/restart the add-on container in Home Assistant to load the updated `CatalogMerger` logic.

## Useful Commands
```bash
# Run unit tests
python3.14 -m pytest tests/test_anime_engine.py
python3.14 -m pytest

# Run linter and formatting checks
python3.14 -m ruff check streaming_hub/backend/utils.py tests/test_anime_engine.py
python3.14 -m ruff format --check streaming_hub/backend/utils.py tests/test_anime_engine.py
```
