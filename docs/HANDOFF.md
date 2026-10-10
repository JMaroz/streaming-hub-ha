# Handoff: Kids Profile Content Filtering & Safe Family Titles Fix

## Current State
- Successfully resolved content classification and rating filtering issues causing family and children's titles (such as "PAW Patrol: Missione Natale", "The Super Mario Galaxy Movie", "Hotel Transylvania", "Il Re Leone", "Minions", "Zootropolis") to be blocked as unsuitable on Kids profiles (`T` and `6+`).
- Implemented precision regex word boundary matching (`\b...\b`) for adult keywords, eliminating overbroad substring collisions (`hot` in `hotel`, `adulto` in coming-of-age plots, `strip` in comic strips/stripes, `intimo` in intimate friendships).
- Removed overbroad words from kids restricted heuristics (`mistero`, `giallo`, unanchored `war`, `crime`).
- Added precedence for `SAFE_FAMILY_FRANCHISES` and family animation genres (`Animazione` + `Famiglia`), ensuring known family content is not rejected by uncertified keyword fallbacks.
- Expanded `RATING_MAP` with child certifications (`U`: 0, `0+`: 0, `TV-Y7-FV`: 6, `E`: 0), and allowed `PG`/`TV-PG`/`TV-Y7` family animations for profile `T` (0+).
- Fixed TMDb release date certification extraction in `metadata.py` to fall back to US/international certifications when the Italian release date has an empty string (`""`).
- Fixed Cinemeta catalog search URL in `metadata.py` (`/catalog/...` instead of `/meta/catalog/...`).
- Added comprehensive unit tests in `tests/test_rating_filter.py`. All 88 tests in the project pass with 0 failures.

## Relevant Files
- `streaming_hub/backend/rating_filter.py`: Refined adult/restricted keywords, compiled regexes, added child ratings to `RATING_MAP`, and added family franchise precedence.
- `streaming_hub/backend/metadata.py`: Fixed certification fallback across release dates and Cinemeta catalog search URL.
- `tests/test_rating_filter.py`: Added tests for "PAW Patrol: Missione Natale", "The Super Mario Galaxy Movie", "Hotel Transylvania", coming-of-age plots, and uncertified family franchises.
- `docs/plans/2026-10-10_kids_profile_content_filtering.md`: Work plan with all tasks completed.

## Next Steps
- Verify behavior in live Home Assistant environment with user custom sources.
- Suggest atomic Conventional Commit (e.g. `fix(catalog): refine kids profile content filtering and safe family titles`).

## Useful Commands
- Run unit tests: `.venv/bin/pytest tests/test_rating_filter.py -v`
- Run full test suite: `.venv/bin/pytest`
