# Piano di Lavoro: Gestione Prossimo Episodio su Cast via Notifica Ibrida e Countdown Server-Side

## Obiettivo
Implementare un sistema robusto e autonomo per l'avanzamento automatico al prossimo episodio durante la riproduzione su Google Cast / Home Assistant (`media_player`). Il flusso gestisce sia una notifica push actionable su Home Assistant (`notify.notify`) sia un banner interattivo in-app, con countdown di 15 secondi. La notifica si attiva solo in presenza di metadati sui titoli di coda (`outro`), oppure al termine dell'episodio se i metadati sono assenti.

## Scope & Non-Goals
- **In Scope**:
  - Spostamento della logica di autoplay e countdown sul backend (`ha_client.py`), indipendente dallo stato del browser/smartphone.
  - Sottoscrizione/ascolto agli eventi di Home Assistant per notifiche push actionable (`mobile_app_notification_action`).
  - Invio di notifica push broadcast con `notify.notify` contenente i pulsanti "▶ Riproduci Ora" e "⏹ Ferma".
  - Triggering condizionato rigoroso:
    - Se `outro.start` è presente da SkipDB -> trigger all'inizio dei titoli di coda, con salto al prossimo episodio alla fine del countdown (stile Netflix).
    - Se `outro.start` è assente -> trigger solo al termine effettivo della puntata (quando il player va in `idle` o finisce lo stream).
  - Endpoint REST `/api/cast/next-episode/action` per confermare o annullare il passaggio.
  - Sincronizzazione dello stato nel polling di `/api/cast/status` e banner interattivo in-app nel frontend.
  - Risoluzione del bug in `castToDevice` dove i parametri di stagione ed episodio venivano sovrascritti dallo stato globale della UI.
- **Non-Goals (YAGNI / Ponytail)**:
  - Nessuna dipendenza esterna aggiuntiva (usare `aiohttp` e la stdlib già presenti).
  - Nessun sistema di code playlist personalizzate o riordino manuale; seguire la numerazione sequenziale naturale della serie (stagione/episodio).

## Task Checklist
- [x] **1. Backend: Predisposizione Sessione e Metadati Prossimo Episodio**
  - [x] Aggiornare `start_cast_tracker` e `_track_cast_playback` in `streaming_hub/backend/ha_client.py` per pre-caricare i metadati del prossimo episodio e i segmenti di skip (`outro.start`).
  - [x] Aggiungere lo stato del countdown (`countdown_active`, `countdown_remaining`, `next_episode_info`) nella sessione di cast attiva.
- [x] **2. Backend: Logica di Countdown e Invio Notifiche Home Assistant**
  - [x] Implementare il controllo durante il tracking: trigger su `media_position >= outro_start` se presente, altrimenti su transizione a fine stream / `idle`.
  - [x] Implementare il metodo `send_next_episode_notification` via `notify.notify` con azioni actionable (`STREAMING_HUB_PLAY_NEXT`, `STREAMING_HUB_STOP`).
  - [x] Gestire il loop di countdown asincrono (15s) nel backend. Alla scadenza o su approvazione, risolvere la sorgente e inviare `play_media` per l'episodio successivo.
  - [x] Aggiungere l'ascolto per le azioni delle notifiche push tramite Home Assistant WebSocket / Event bus (`mobile_app_notification_action`).
- [x] **3. Backend: Endpoint REST per Status e Azioni**
  - [x] Esporre lo stato del prossimo episodio e del countdown in `/api/cast/status`.
  - [x] Creare l'endpoint `POST /api/cast/next-episode/action` per gestire comandi `play_now` e `cancel`.
- [x] **4. Frontend: Banner Interattivo Sincronizzato e Fix Casting**
  - [x] Aggiornare `pollCastStatus` in `streaming_hub/frontend/js/app.js` per mostrare il banner in-app sincronizzato con il countdown server-side.
  - [x] Collegare i pulsanti "Riproduci Ora" e "Annulla" all'endpoint API.
  - [x] Correggere `castToDevice` per accettare e utilizzare parametri espliciti di serie, stagione ed episodio senza dipendere da `state.selectedEpisode`.
- [x] **5. Test e Verifica Empirica**
  - [x] Scrivere unit test per `ha_client` (verifica trigger con `outro.start`, trigger su `idle` senza metadati, decremento countdown e transizione al prossimo episodio).
  - [x] Eseguire `pytest` su tutta la suite e verificare l'assenza di regressioni (98/98 test passati).
  - [x] Verificare il linting con `ruff` e sintassi JS.

## Strategia di Verifica
- **Automated Tests**:
  - `.venv/bin/pytest tests/test_cast_next_episode.py -v`
  - `.venv/bin/pytest`
- **Linting**:
  - `.venv/bin/ruff check .`
- **Manual Verification**:
  - Avviare un episodio di una serie con Cast.
  - Verificare che il log backend e `/api/cast/status` mostrino il countdown e che la notifica venga inviata su Home Assistant.
  - Verificare che alla scadenza dei 15s l'episodio successivo parta automaticamente sulla TV anche senza interazione dell'utente.
