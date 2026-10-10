# Work Plan: Kids Profile Content Filtering & Safe Family Titles Fix

## Goal Description
Fix content classification and rating filtering so children's and family titles (including "PAW Patrol: Missione Natale", "The Super Mario Galaxy Movie", and animation classics) are properly available and playable on Kids profiles (`T` and `6+`), while maintaining strict protection against actual adult, mature, or violent content.

## Scope & Non-Goals
- **In Scope**:
  - Fix false-positive keyword matching in `streaming_hub/backend/rating_filter.py` by introducing regex word boundaries (`\b...\b`), eliminating overbroad substrings (`hot`, `hard`, `adulto`, `strip`, `intimo`), and context-checking.
  - Refine `KIDS_RESTRICTED_KEYWORDS` so family themes (e.g., "mistero", "guerra" in space/galactic context, "giallo", "war" substring in "award") do not block legitimate family animation titles.
  - Prioritize `FAMILY_FRIENDLY_KEYWORDS` and `SAFE_FAMILY_FRANCHISES`: if a title is explicitly classified as family/animation or belongs to safe family franchises, heuristic keyword blocks must not reject it unless explicit mature certifications (e.g. VM14, VM18, R, TV-MA) or `is_adult` flags exist.
  - Add missing child certifications to `RATING_MAP` (e.g., `U`, `0+`, `TV-Y7-FV`, `E`) and allow `PG` / `TV-PG` / `TV-Y7` family animations for profile `T` (0+).
  - Fix certification fallback in `streaming_hub/backend/metadata.py` so empty Italian certifications (`""`) fall back to US certifications (`PG`, `G`, etc.).
  - Fix Cinemeta catalog search endpoint URL in `streaming_hub/backend/metadata.py` (`/catalog/...` instead of `/meta/catalog/...`).
  - Add unit and regression tests in `tests/test_rating_filter.py`.
- **Non-Goals (YAGNI)**:
  - Do not introduce new third-party NLP or AI content moderation libraries.
  - Do not alter the database schema or configuration schema in `config.yaml`.
  - Do not weaken protection against genuinely adult/pornographic/extreme splatter titles.

## Task Checklist
- [x] **Task 1: Certification Fallbacks & Cinemeta URL in `metadata.py`**
  - Fix `_apply_movie_metadata` and `_apply_tv_metadata` to continue searching release dates for non-empty certification when `it_entry` has an empty certification string.
  - Fix `_search_cinemeta_imdb_id` URL formatting to query `https://v3-cinemeta.strem.io/catalog/...` without duplicate `/meta`.
- [x] **Task 2: Precision Matching & False-Positive Elimination in `rating_filter.py`**
  - Replace substring search `any(ak in text)` with regex word boundary matching `\b...\b` for adult keywords.
  - Clean up overbroad terms like `hot` (matched `hotel`), `hard` (matched `hardware`), `strip` (matched `stripes`), and `intimo`.
  - Replace unanchored `adulto`/`adulti`/`adult` with specific adult phrases like `film per adulti`, `contenuto per adulti`, `adult only`, `pubblico adulto`.
  - Remove overbroad keywords from `KIDS_RESTRICTED_KEYWORDS` (`mistero`, `giallo`, unanchored `war`).
- [x] **Task 3: Safe Family Franchise & Genre Precedence in `rating_filter.py`**
  - Ensure family animation genre (`Animazione` + `Famiglia` / `Kids`) and `SAFE_FAMILY_FRANCHISES` are exempted from heuristic keyword rejections when uncertified.
  - Expand `SAFE_FAMILY_FRANCHISES` with common kids franchises (e.g., `mario galaxy`, `super mario`, `paw patrol`, `sonic`, `pokemon`, `dragon ball`, `pokemon`, `garfield`, `shrek`).
  - Update `RATING_MAP` to include `U: 0`, `0+: 0`, `TV-Y7-FV: 6`, `E: 0`, and permit `PG` family animation on profile `T`.
- [x] **Task 4: Comprehensive Test Suite & Verification**
  - Add test cases in `tests/test_rating_filter.py` covering "PAW Patrol: Missione Natale", "The Super Mario Galaxy Movie", "Hotel Transylvania", and coming-of-age plots.
  - Run full test suite via `.venv/bin/pytest`.
  - Run linter via `uvx ruff check .` and `uvx ruff format --check .`.

## Verification Strategy
- Run `.venv/bin/pytest tests/test_rating_filter.py -v` to ensure all existing and new rating filter test cases pass.
- Run `.venv/bin/pytest` to ensure zero regressions across the entire suite.
- Test diagnostic script validating `is_title_allowed_for_profile` on "PAW Patrol: Missione Natale" and "Super Mario Galaxy" across both `T` and `6+` profiles.
