# Handoff: Fix Anime Provider DoHResolver & Comprehensive Metadata Parsing (Release 3.0.1)

## Current State
- Push su `main` completato con successo (commit `6daf270` e `a726cd6`).
- Release Please ha aperto automaticamente la PR [#16](https://github.com/JMaroz/streaming-hub-ha/pull/16) (`chore(main): release 3.0.1`).
- La PR #16 è stata mergiata e il branch remoto eliminato.
- Eseguito `git pull origin main` in locale, portando il repository alla versione **3.0.1** (commit `c70a889`).
- Tutti i 101 test unitari e i controlli di linting `ruff` sono passati con esito positivo.

## Relevant Files
- `streaming_hub/config.yaml`: Versione incrementata a `3.0.1`.
- `CHANGELOG.md`: Changelog aggiornato con le fix per DoHResolver, regex backreference, metadati e movie playback.
- `streaming_hub/backend/dns_resolver.py`: Supporto parametro `provider` e metodo `get_connector()`.
- `streaming_hub/backend/engine_anime.py`: Parsing metadati robusto, quote backreferences, gestione sorgenti film.
- `tests/test_anime_engine.py`: Test unitari espansi a 22 verifiche dedicate.
- `docs/plans/2026-10-12_fix_anime_doh_resolver.md`: Piano completato.

## Next Steps
- Aggiornare l'add-on da Home Assistant (disponibile con la nuova versione 3.0.1) oppure riavviarlo su `http://192.168.1.67:8123/config/app/f94709c2_streaming_hub`.

## Useful Commands
- Verificare i log dell'istanza locale: `curl -s http://192.168.1.67:8123/config/app/f94709c2_streaming_hub/logs`
- Eseguire i test unitari: `.venv/bin/pytest tests/test_anime_engine.py -v`
- Eseguire la suite completa: `.venv/bin/pytest`
