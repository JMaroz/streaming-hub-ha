# Plan: Fix CatalogMerger Anime Sequel and Multi-Part Deduplication

## Obiettivo
Risolvere il problema per cui la ricerca nel catalogo anime per parole chiave generiche (come "gate") omette sequel/cour successivi (come `166-gate-part-2`) a causa di un'errata deduplicazione in `CatalogMerger`, preservando la corretta unificazione tra fonti diverse senza cancellare le diverse stagioni/parti o versioni dello stesso provider.

## Scope & Non-Goals
- **Scope**:
  - Evitare che `CatalogMerger.is_same_media` consideri duplicati contenuti distinti provenienti dallo stesso provider (es. `anime-15` e `anime-166`, oppure `anime-4290` SUB e `anime-4500` DUB).
  - Rafforzare `CatalogMerger.titles_match` affinché il check su `words1.issubset(words2)` non consideri uguali titoli che differiscono per numeri, parti, stagioni o marker di sequel (es. `Part 2`, `Season 2`, `2`, `Movie`, ecc.).
  - Aggiungere test dedicati a coprire la ricerca e il merging di titoli con sequel/parti (in particolare Gate e Gate Part 2) e versioni SUB/DUB.
- **Non-Goals**:
  - Nessuna modifica alle API remote del provider anime (la ricerca lato provider funziona correttamente e restituisce tutti gli elementi).
  - Nessuna modifica all'interfaccia utente o al frontend (il frontend mostra correttamente tutti i risultati restituiti dall'API backend).

## Task Checklist
- [x] Creare il piano di lavoro in `docs/plans/2026-10-13_fix_catalog_merger_anime_sequels.md`
- [x] Aggiornare `CatalogMerger.is_same_media` in `streaming_hub/backend/utils.py` per non fondere item distinti con lo stesso prefisso provider
- [x] Aggiornare `CatalogMerger.titles_match` in `streaming_hub/backend/utils.py` per escludere titoli con differenze numeriche o marker di sequel
- [x] Aggiungere test unitari in `tests/test_anime_engine.py` per Gate Part 1 vs Gate Part 2 e deduplicazione
- [x] Verificare la suite di test completa (`pytest`) e il linter (`ruff`)
- [x] Aggiornare `docs/HANDOFF.md` sovrascrivendolo completamente

## Strategia di Verifica
- Test unitari dedicati con `python3.14 -m pytest tests/test_anime_engine.py`
- Test suite completa con `python3.14 -m pytest`
- Linting con `python3.14 -m ruff check streaming_hub/ tests/`
