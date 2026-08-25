# CRM Vocal — AI Call Analysis Pipeline for Ora Telecom

**CRM Vocal** is an AI-powered call processing pipeline. It takes a phone call transcript, uses an LLM to generate a structured **Procès-Verbal** (PV) report, and routes the resulting tasks to either **HubSpot** (commercial calls) or **Ora Studio** (technical support calls). The call type is **auto-detected** — never manually declared.

> **Stack:** FastAPI · Python 3.13 · DeepSeek API (OpenAI-compatible) · PostgreSQL · Redis · WebSocket-ready  
> **Current Phase:** Phase 1 (mock transcripts, full pipeline functional, most integrations in mock mode)

---

## Table of Contents

- [What does it do?](#what-does-it-do)
- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Pipeline: Step by Step](#pipeline-step-by-step)
- [What's Already Built](#whats-already-built)
- [What's Stubbed / Coming Next](#whats-stubbed--coming-next)
- [Getting Started](#getting-started)
- [Development](#development)
- [Key Design Decisions](#key-design-decisions)

---

## What does it do?

CRM Vocal listens to phone calls between Ora Telecom agents and external contacts, then:

1. **Transcribes** the call → raw text (Phase 2 — currently mock transcripts)
2. **Summarizes** it via DeepSeek LLM → structured JSON PV
3. **Classifies** it as commercial or technical (keyword scoring)
4. **Extracts & validates** action items, sets difficulty levels, assigns AI model hints
5. **Routes** the output:
   - **Commercial calls** → HubSpot (creates a note + individual tasks + optional meeting)
   - **Technical calls** → Ora Studio (posts todo list with model hints + optional RDV)

**One call = one destination.** No cross-routing. The PV is the single source of truth from summarization through routing.

---

## Architecture Overview

```
┌──────────────┐     ┌───────────────────────────────┐
│  Transcript  │────▶│         Summarizer            │
│  (text/WS)   │     │  (DeepSeek LLM)               │
└──────────────┘     │  → Summarizes                 │
                     │  → Classifies (context-aware) │
                     │  → Extracts actions           │
                     └──────────────┬────────────────┘
                                    │
                    ┌───────────────┘
                    ▼
┌──────────────────────────────────────────────────────┐
│                    Router                            │
│                                                      │
│  #appel-commercial ──▶ HubSpot (notes, tasks, mtg)  │
│  #appel-tech       ──▶ Ora Studio (todos, RDV)      │
└──────────────────────────────────────────────────────┘
```

### Three Phases (planned)

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 1** | Mock text transcripts → full AI + routing pipeline | ✅ Active |
| **Phase 2** | WebSocket live transcription (Whisper/Deepgram) | 📋 Planned |
| **Phase 3** | Production call platform (Twilio, Recall.ai, custom VoIP) | 📋 Planned |

---

## Project Structure

```
D:\smart agent\
│
├── app/                              # Main application package
│   ├── main.py                       # FastAPI app, 3 endpoints
│   ├── config.py                     # Pydantic settings (.env → config)
│   │
│   ├── agent/                        # AI pipeline core
│   │   ├── summarizer.py             # DeepSeek LLM → structured PV (JSON)
│   │   ├── classifier.py             # Keyword scoring → call type detection
│   │   └── action_extractor.py       # Validate/enrich actions, assign model hints
│   │
│   ├── routing/                      # Output destinations
│   │   ├── router.py                 # Dispatcher (one call → one destination)
│   │   ├── hubspot/                  # HubSpot integration
│   │   │   ├── client.py             # HTTP client (mock/live modes)
│   │   │   ├── notes.py              # Create formatted notes
│   │   │   ├── tasks.py              # Create individual tasks
│   │   │   ├── deals.py              # Update deal stages (stub)
│   │   │   └── meetings.py           # Create follow-up meetings
│   │   └── ora_studio/               # Ora Studio integration
│   │       ├── client.py             # HTTP client (mock/live modes)
│   │       └── todo.py               # Post task list with model hints
│   │
│   ├── models/                       # Pydantic schemas
│   │   ├── pv.py                     # PV data contract (the core schema)
│   │   ├── call.py                   # Call session state machine
│   │   └── task.py                   # TaskItem with difficulty → model mapping
│   │
│   ├── db/                           # Database layer
│   │   ├── session.py                # Async SQLAlchemy engine + session
│   │   └── models.py                 # ORM: CallLog + PVReport tables
│   │
│   ├── ws/                           # WebSocket (Phase 2)
│   │   └── call_handler.py           # WS handler stub
│   │
│   └── mcp/                          # MCP tools
│       └── agenda.py                 # RDV creation stub (tech calls)
│
├── scripts/                          # Dev utilities
│   ├── mock_call.py                  # Run pipeline from CLI with a transcript
│   └── migrate.py                    # Create DB tables
│
├── tests/                            # Test suite
│   ├── fixtures/
│   │   ├── sample_transcript_tech.txt
│   │   └── sample_transcript_commercial.txt
│   └── __init__.py
│
├── ui/
│   └── index.html                    # Test console (dark-mode web UI)
│
├── docker-compose.yml                # PostgreSQL 16 + Redis 7 for local dev
├── Dockerfile                        # Production container (python:3.13-slim)
├── requirements.txt                  # Python dependencies
├── .env.example                      # Env var template
├── README_ARCH.md                    # Detailed architecture document
└── README.md                         # ← This file
```

---

## Pipeline: Step by Step

Here's exactly what happens when a transcript is processed:

### 1. Summarizer (`app/agent/summarizer.py`)

Sends the transcript to DeepSeek (OpenAI-compatible API) with a detailed French-language system prompt. The prompt instructs the model to:

- Auto-detect call type (`#appel-commercial` or `#appel-tech`)
- Identify participants — `left` (primary Ora Telecom side), `right` (primary external), and `additional_participants` for any extra speakers in a multi-party meeting
- Write a 3–6 sentence *compte rendu* in French
- Extract action items with owner + deadline (commercial) or difficulty level (tech)
- Detect if a follow-up meeting was scheduled
- Return **only valid JSON** (with 3 fallback parsers: direct parse → ```json``` block → `{...}` brace finder)

**Settings:** `temperature=0.3`, `max_tokens=4500`, today's date injected into the prompt.

### 2. Validation (`app/agent/classifier.py`)

The LLM already classified the call during summarization. This step is a thin safety net:
- If the LLM returned `#appel-commercial` or `#appel-tech` → pass through
- If the LLM returned anything else (malformed, empty, wrong format) → default to `#appel-commercial` and log a warning

**No keyword scoring.** The LLM understands that "API integration for the client's contract renewal" is commercial despite containing tech terms. Keyword counting can't make that distinction — only context-aware classification can. See [Key Design Decisions](#7-classification-is-llm-first-not-keyword-based).

### 3. Action Extractor (`app/agent/action_extractor.py`)

Validates each action item:
- Ensures title and owner are non-empty
- Parses ISO date strings into `datetime` objects
- Sets default difficulty to `"difficile"` if missing (tech calls)
- Maps difficulty → AI model hint:

| Difficulty | Model Hint |
|------------|------------|
| `facile` | `gpt-4o-mini` |
| `difficile` | `claude-sonnet-4-6` |
| `très difficile` | `claude-opus-4-6` |

These hints tell Ora Studio which AI model to use when executing the task. Invalid actions are skipped with a warning.

### 4. Router (`app/routing/router.py`)

Dispatches based on `call_type`:

- **`#appel-commercial`** → HubSpot: creates a formatted note, individual tasks per action, optional meeting
- **`#appel-tech`** → Ora Studio: posts todo list with model hints, optional RDV via MCP agenda
- **Unknown type** → returns `"unrouted"` status

Each operation is wrapped in individual try/except — one failure doesn't block the others.

---

## What's Already Built

### ✅ Fully Functional

| Component | What it does |
|-----------|-------------|
| **Summarizer** | Calls DeepSeek LLM, generates structured PV JSON with 3 fallback parsers |
| **Classifier** | Thin validation layer — trusts LLM classification, defaults if malformed |
| **Action Extractor** | Validates, enriches, assigns difficulty → model hints |
| **Router** | One-call-one-destination dispatcher with error isolation |
| **Pydantic schemas** | `PV`, `CallSession`, `TaskItem` — the full data contract |
| **FastAPI app** | 3 endpoints: health check, call start, call process |
| **Test UI** | Dark-mode HTML console with sample transcripts, live PV display |
| **CLI runner** | `scripts/mock_call.py` — run pipeline from terminal with `--file` or `--text` |
| **Config system** | Pydantic-settings loading from `.env` for all services |
| **DB models** | `CallLog` + `PVReport` ORM models (async SQLAlchemy) |
| **DB migration** | `scripts/migrate.py` creates all tables |
| **Docker Compose** | PostgreSQL 16 + Redis 7 with healthchecks and persistent volumes |
| **Dockerfile** | Production-ready container (python:3.13-slim, uvicorn) |
| **Test fixtures** | Realistic French-language mock transcripts (tech + commercial) |

### ⚙️ Working in Mock Mode (no credentials needed)

| Component | Mock behavior |
|-----------|--------------|
| **HubSpot client** | Logs what it would create, returns fake IDs |
| **Ora Studio client** | Logs what it would post, returns fake response |
| **MCP Agenda** | Logs RDV creation, returns mock RDV ID |

### 🗄️ Database Schema

```sql
call_logs
├── id (serial PK)
├── session_id (varchar, unique)
├── started_at (timestamp)
├── ended_at (timestamp)
├── participants (jsonb)
├── call_type (varchar)
└── pv_report (1:1 relationship)

pv_reports
├── id (serial PK)
├── call_log_id (FK → call_logs)
├── subject (varchar)
├── compte_rendu (text)
├── actions (jsonb)
├── raw_transcript (text)
├── created_at (timestamp)
└── routed_to (varchar)
```

---

## What's Stubbed / Coming Next

### Phase 2 — Live Transcription

- **`app/ws/call_handler.py`**: WebSocket handler exists as a stub — accepts connections and logs chunks, but is **not yet wired** into the FastAPI app. No WebSocket route registered in `main.py`.
- **`app/agent/transcriber.py`**: Does not exist yet. Will convert raw audio → text via Whisper or Deepgram. The exact format (raw audio vs. text from Ahmed's server) is TBD.

### Other Known Gaps

- **Alembic not configured** — listed in `requirements.txt` but no `alembic.ini` or migration directory
- **Deals integration stub** — `app/routing/hubspot/deals.py` can PATCH deal stages but is not wired into the summarizer (deal IDs aren't extracted from transcripts yet)
- **No CI/CD** — no GitHub Actions, GitLab CI, or similar
- **DeepSeek API key is empty** in `.env` — fill it in to make real LLM calls

---

## Input Format

DeepSeek expects a timestamped dialogue transcript. See **[INPUT_SCHEMA.md](INPUT_SCHEMA.md)** for the complete specification with examples, alternative formats, and best practices for LLM accuracy.

Quick reference:
```
[HH:MM:SS] APPEL DÉMARRÉ
[HH:MM:SS] SpeakerName : Message text in French...
[HH:MM:SS] OtherSpeaker : Reply...
...
[HH:MM:SS] APPEL TERMINÉ
```

---

## Getting Started

### Prerequisites

- Python 3.13
- Docker (for PostgreSQL + Redis — or bring your own)
- DeepSeek API key (or run with mock transcripts — the pipeline code itself is fully functional)

### Quick Start

```bash
# 1. Clone and enter the project
cd "D:\smart agent"

# 2. Create virtual environment
python -m venv .venv
source .venv/Scripts/activate  # Windows
# or: source .venv/bin/activate  # Unix

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env → add your DEEPSEEK_API_KEY

# 5. Start infrastructure (PostgreSQL + Redis)
docker compose up -d

# 6. Create database tables
python scripts/migrate.py

# 7. Launch the app
uvicorn app.main:app --reload --port 8000

# 8. Open the test UI
# Visit http://localhost:8000
```

### Run the Pipeline from CLI (no server needed)

```bash
# Process the sample tech transcript
python scripts/mock_call.py --file tests/fixtures/sample_transcript_tech.txt

# Process the commercial sample
python scripts/mock_call.py --file tests/fixtures/sample_transcript_commercial.txt

# Pass inline text
python scripts/mock_call.py --text "Ahmed: Bonjour... Kh: Bonjour..."

# Pretty-print the full JSON output
python scripts/mock_call.py --file tests/fixtures/sample_transcript_tech.txt --json
```

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | Test UI |
| `GET` | `/api/health` | Health check (reports if DeepSeek is configured) |
| `POST` | `/api/call/start` | Register a new call session → returns `session_id` |
| `POST` | `/api/call/process` | Run the full pipeline → returns PV + routing results |

---

## Key Design Decisions

### 1. Call type is always auto-detected
The DeepSeek system prompt instructs the LLM to classify the call from context. The classifier module only validates — it passes through the LLM's decision (or defaults to `#appel-commercial` if the output is malformed). No human declares the call type. No keyword scoring.

### 2. One call = one destination
A call is either commercial (→ HubSpot) or technical (→ Ora Studio). The router enforces this; there's no cross-posting.

### 3. Difficulty → Model mapping lives in the pipeline, not in Ora Studio
When a tech task is created, CRM Vocal assigns a `model_hint` (`gpt-4o-mini`, `claude-sonnet-4-6`, or `claude-opus-4-6`) based on the difficulty level. Ora Studio uses this hint — it doesn't decide for itself.

### 4. Platform-agnostic input
The pipeline doesn't care where the transcript comes from. Phase 1 uses text files or inline strings. Phase 2 will add WebSocket. Phase 3 will add Twilio/Recall.ai. The summarizer interface stays the same.

### 5. Error isolation in routing
Each HubSpot/Ora Studio operation is wrapped in its own try/except. If creating a meeting fails, the note and tasks still go through. The full routing result (successes + failures) is returned in the response.

### 6. French-first
System prompts, sample transcripts, and the test UI are all in French — Ora Telecom operates in the Tunisian market.

### 7. Classification is LLM-first, not keyword-based
Keyword scoring was removed because Ora Telecom sells tech products — every commercial call mentions APIs, databases, and deployments. Every tech call touches billing, contracts, and clients. Only an LLM can distinguish "API integration for the client's contract renewal" (commercial) from "the payment API is throwing errors in production" (technical). The summarizer classifies from context as part of its output; the pipeline trusts it.

---

## Multi-Participant Meetings (3+ speakers)

> **Was the pipeline tolerant of more than 2 people in a meeting?** Originally **no** — it was hardcoded for exactly two participants. This is now fixed. This section records the test that exposed it and the changes made.

### The test that exposed it

1. **Generated a 4-person meeting transcript** — `tests/fixtures/sample_transcript_4person_meeting.txt`. A technical review with 2 Ora Telecom people (`kh` CTO, `Sami` backend) and 2 external people (`Lina` product manager, `Oussema` DevOps at the client "ACME Corp").
2. **Synthesized audio** with 4 distinct edge-tts voices:
   ```bash
   python scripts/generate_meeting_audio.py --file tests/fixtures/sample_transcript_4person_meeting.txt --format both
   ```
3. **Ran the realtime pipeline** on that audio:
   ```bash
   python scripts/live_replay.py --audio tests/fixtures/sample_transcript_4person_meeting.wav --speed 2
   ```

### What the test found (the bug)

The PV came back with only **two** participants — `Sami` and `Oussema` were dropped from the structure (they survived only as *action owners*, not as call participants), and `left`/`right` were even **inverted** (the client landed on `left`, the Ora CTO on `right`). Root cause: the schema, the summarizer prompt, and the routing all assumed exactly one `left` and one `right`.

### The fix

Backward-compatible — two-person calls are unchanged (`additional_participants` stays `[]`):

| File | Change |
|------|--------|
| `app/models/pv.py` | Added `PV.additional_participants: list[Participant]`. Made `Participant.phone_number`/`role` optional (the LLM returns `null` for meetings). |
| `app/models/call.py` | Added `additional_participants` to `CallStartRequest` and `CallSession`. |
| `app/agent/summarizer.py` | Prompt now instructs the LLM to list **every** speaker and put extras in `additional_participants` (with a `side` each). |
| `app/routing/hubspot/contacts.py` | New `create_contacts_for_additional_participants()` — external extras also become HubSpot contacts. |
| `app/routing/hubspot/deals.py` | Deal description lists extra participants; deal accepts multiple contact associations. |
| `app/routing/router.py` | Commercial path now resolves + associates extra external contacts. |
| `app/mcp/agenda.py` | RDV log lists all attendees, not just left/right. |
| `app/fallback_store.py` | `list_pvs` overview includes extra participant names. |
| `scripts/{live_replay,e2e_test,mock_call}.py` | Print extra participants. |
| `scripts/generate_meeting_audio.py` | Added voices for `Sami` and `Lina`. |
| `scripts/mock_call.py` | Fixed missing Windows UTF-8 console wrapper (crashed on emoji under cp1252). |
| `tests/test_multi_participant.py` | New hermetic tests locking in the behavior. |

After the fix, the same undiarized transcript produces a PV with all four people in `additional_participants`.

### Remaining limitation: speaker **side** accuracy without diarization

The realtime STT path (`stream_transcribe`) does **not** do speaker diarization — Mistral's realtime model rejects it, so `live_replay.py` receives one undiarized text blob. The summarizer must guess *who is Ora vs external* from content alone, and on multi-party calls it can still mis-assign `side` (in the test it inverted everyone). Everything is *captured* now, but `side` may be wrong.

To fix `side` properly, the speaker identity needs to come from upstream. Two paths now exist: enable diarization in the batch STT (`scripts/e2e_test.py --diarize`), or — the preferred approach — the WebRTC page declares each member's identity and (optionally) their `side` at connect (see the multi-member WebSocket contract above). With a declared `side`, the summarizer assigns participants deterministically via a `PARTICIPANTS:` manifest. Without it, treat `side` on multi-party calls as a hint, not ground truth.

---

## Multi-member (per-device) transcription

The WebRTC page gives each member their own device/track with a declared identity, so the pipeline can distinguish speakers **by device, not by diarization**. This is now supported end-to-end.

### How it works

Each member opens **one WebSocket** and streams their own mic:

```
ws://host/ws/call/{session_id}/{speaker_id}[?side=left|right&role=…]
```

The `side` query param is **optional but recommended** — it lets the client declare who is Ora (`left`) vs external (`right`) up front. When any member declares a side, the backend prepends a `PARTICIPANTS: …` manifest line to the transcript, so the summarizer assigns `left`/`right`/`additional_participants` and their `side` **deterministically** (instead of guessing from names, which is unreliable). Without it, the pipeline still captures everyone, but `side` may be wrong on multi-party calls.

| Direction | Frame | Meaning |
|-----------|-------|---------|
| client → server | binary PCM (S16LE, 16 kHz, mono) | the member's own mic audio |
| client → server | `{"type":"listen_start"}` | agent starts listening — this member's audio is now transcribed |
| client → server | `{"type":"listen_stop"}` | agent stops listening — audio is relayed but **not** transcribed |
| client → server | `{"type":"audio_end"}` | legacy alias for `listen_stop` |
| client → server | `{"type":"end_call"}` | force-end the whole call now (host override) |
| server → client | binary PCM (S16LE, 16 kHz, mono) | another member's mic audio, relayed so callers hear each other |
| server → client | `{"type":"transcript_delta","speaker_id":"…","text":"…"}` | live captions for that member |
| server → client | `{"type":"pv_draft","pv":{…}}` | live draft PV, refreshed mid-call |
| server → client | `{"type":"pv_result","pv":{…},"routing":{…}}` | the final PV, broadcast to all members |

The backend runs an **audio bridge** (every member's PCM is relayed verbatim to the others) plus an **independent realtime STT session per member** (`stream_transcribe` per socket). A member is transcribed only while they have signalled `listen_start`; each listen period is a *segment* whose authoritative transcript is committed on `listen_stop` (or disconnect). Segments are stamped with the speaker's name and arrival time and interleaved chronologically into one `[HH:MM:SS] Speaker : text` transcript (`app/transcription/merge.py`). When every member has disconnected, or an `end_call` is received, the normal pipeline (`summarize → classify → extract → route`) runs once and the PV is broadcast back.

### Interruption tolerance

Because each member's STT session is independent, two people talking at once are both transcribed by their own session and interleaved — nothing is dropped, and one member's connection dropping doesn't kill the others. Speaker labels come from the socket identity (the `speaker_id` in the URL), which the summarizer now trusts for `left`/`right`/`additional_participants` and their `side`.

### Real-time pipeline (live drafts)

The agent works **during** the call, not just at the end. A background task (`_incremental_loop` in `app/ws/call_handler.py`) re-runs `summarize → classify → extract` on the transcript-so-far every `PIPELINE_INTERVAL_SECONDS` (default 20s) and broadcasts `{"type":"pv_draft", …}` to members. At call end, if the transcript hasn't changed since the last draft, the cached PV is **reused** — so the final `pv_result` (with routing) is ready almost instantly. Routing is never run on drafts, only at finalization (it has side effects: HubSpot / fallback store).

### Components

| File | Role |
|------|------|
| `app/ws/call_handler.py` | `member_handler` — per-member STT + finalization |
| `app/ws/session_manager.py` | Tracks members per call; accumulates labeled segments |
| `app/transcription/merge.py` | Interleaves segments → `[HH:MM:SS] Speaker : text` |
| `app/transcription/realtime.py` | `stream_transcribe` gained an `on_segment` callback |
| `app/main.py` | Registers `@app.websocket("/ws/call/{session_id}/{speaker_id}")` |
| `scripts/live_replay_multispeaker.py` | Simulates the WebRTC page (no browser) for testing |
| `scripts/generate_meeting_audio.py` | `--split-speakers` emits one WAV per member |

### Testing without the WebRTC page

```bash
# 1. Per-member WAVs from a 4-person transcript
python scripts/generate_meeting_audio.py \
    --file tests/fixtures/sample_transcript_4person_meeting.txt \
    --format wav --split-speakers

# 2. Start the server
uvicorn app.main:app --port 8000

# 3. Simulate the members and print the PV
python scripts/live_replay_multispeaker.py \
    --dir tests/fixtures/sample_transcript_4person_meeting_speakers
```

---

## Long meetings (20–30 min) — current limits

**Not yet supported well.** The STT layer streams indefinitely, but the summarizer is the bottleneck:

- **Single-shot LLM call** — `summarize()` sends the entire transcript in one request (`app/agent/summarizer.py`).
- **4500-token output cap** — `max_tokens=4500` (`summarizer.py`) truncates the PV (compte rendu + actions) on very long calls.
- **Practical ceiling ≈ 10 minutes** — beyond that, action items start getting dropped. (`INPUT_SCHEMA.md` already warns "200–400 lines max".)
- **No STT reconnection** — a WebSocket drop mid-call loses the transcript.

**Recommended future work:** chunked map-reduce summarization — split the transcript into overlapping ~8k-char chunks, summarize each to a partial PV (speakers, actions, decisions, meetings), then a final reduce call merges them. This is the standard fix for arbitrary-length meetings but is deliberately out of scope for now.

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API key for LLM calls |
| `DEEPSEEK_BASE_URL` | No | Defaults to DeepSeek's endpoint |
| `DEEPSEEK_MODEL` | No | Defaults to `deepseek-chat` |
| `DATABASE_URL` | No | PostgreSQL async connection string |
| `REDIS_URL` | No | Redis connection string |
| `HUBSPOT_CLIENT_ID` | Phase 3 | HubSpot OAuth |
| `HUBSPOT_CLIENT_SECRET` | Phase 3 | HubSpot OAuth |
| `HUBSPOT_REFRESH_TOKEN` | Phase 3 | HubSpot OAuth |
| `HUBSPOT_PORTAL_ID` | Phase 3 | HubSpot portal |
| `ORA_STUDIO_API_URL` | Phase 3 | Ora Studio base URL |
| `ORA_STUDIO_API_KEY` | Phase 3 | Ora Studio API key |
| `APP_ENV` | No | `development` / `production` |
| `LOG_LEVEL` | No | Defaults to `INFO` |

---

## License

Proprietary — Ora Telecom. All rights reserved.

# Sprint — Agent Calling Page (Multi-member WebRTC/WS Frontend)

**Goal:** build `ui/call.html` (or `ui/live-call.html`), the page an Ora Telecom agent
opens to join a call session, hit **"Start Call"** to open the mic + audio bridge, then **"Start Agent"** to transcribe — streaming their mic into the
already-built `/ws/call/{session_id}/{speaker_id}` pipeline, watch live transcript +
PV drafts, and see the final routed PV when the call ends.

This sprint is **frontend-only**. Nothing in `app/ws/`, `app/transcription/`, or
`app/main.py` needs to change — the backend contract described in the README's
*"Multi-member (per-device) transcription"* section is already correct and this page
must honor it exactly.

> **One serving caveat:** `getUserMedia` only works in a secure context (`https` or
> `localhost`), so `ui/call.html` cannot be opened as `file://` — it must be served
> over HTTP. The FastAPI app currently serves only `ui/index.html` at `/`; to serve
> this page too, add a static mount in `app/main.py`
> (`app.mount("/ui", StaticFiles(directory=UI_DIR))` — a 2-line change) and open
> `http://localhost:8000/ui/call.html`. For quick local dev, `python -m http.server 5500`
> from the `ui/` directory also works. On production `https`, use `wss://` instead of `ws://`.

---

## 1. Backend contract this page must honor (no changes needed)

```
ws://host/ws/call/{session_id}/{speaker_id}[?side=left|right&role=…]
```

| Direction | Frame | Meaning |
|---|---|---|
| client → server | binary PCM, **S16LE, 16 kHz, mono** | this member's mic audio (relayed to the other members) |
| client → server | `{"type":"listen_start"}` | agent starts listening — transcribe this member's audio |
| client → server | `{"type":"listen_stop"}` | agent stops listening — relay continues, no transcription |
| client → server | `{"type":"audio_end"}` | legacy alias for `listen_stop` |
| client → server | `{"type":"end_call"}` | force-end the whole call (host override) |
| server → client | binary PCM, **S16LE, 16 kHz, mono** | another member's mic audio (the audio bridge) |
| server → client | `{"type":"transcript_delta","speaker_id":"…","text":"…"}` | live captions |
| server → client | `{"type":"pv_draft","pv":{…}}` | live PV, refreshed every `PIPELINE_INTERVAL_SECONDS` |
| server → client | `{"type":"pv_result","pv":{…},"routing":{…}}` | final PV + HubSpot/Ora Studio routing result |

**The one hard constraint that drives most of the sprint work:** the backend expects
**raw 16 kHz mono S16LE PCM**, not WebM/Opus blobs. Browsers give you 48 kHz Float32
by default via `getUserMedia`. Getting that conversion right, in-browser, in real
time, is the actual engineering task here — everything else is UI plumbing.

---

## 2. Scope

### In scope
- `ui/call.html` — agent-facing single page (reuse the dark-mode styling from `ui/index.html`)
- `session_id` generation client-side (`crypto.randomUUID()`) — no backend "start" call is needed; the WS handler creates the session on first member attach
- Mic capture → resample to 16 kHz mono PCM16 → stream over the WS above
- **"Start Call" / "Leave Call"** button — mic + audio bridge (callers hear each other)
- **"Start Agent" / "Stop Agent"** button — the agent only listens (transcribes) while active
- Live transcript panel (renders `transcript_delta` events, tagged by speaker)
- Live PV draft panel (renders `pv_draft`, refreshes in place)
- Final PV + routing result screen (renders `pv_result`)
- `side` selector (Ora agent = `left`, defaults on join) sent as a query param
- Basic connection-state UI (connecting / listening / muted / call ended / error)
- "End call" button → sends `{"type":"end_call"}`

### Out of scope (explicitly deferred)
- Multi-tab / multi-browser simulation of the 4-person meeting (already covered by `scripts/live_replay_multispeaker.py`)
- Real `RTCPeerConnection` / SFU transport (see **Optimized Option** below — this sprint uses the existing raw-PCM-over-WebSocket contract, which is simpler and already what the backend implements)
- Reconnection-on-drop logic (flag as fast-follow, see §5)
- Any HubSpot/Ora Studio UI — that stays server-side and mock

---

## 3. Page structure

```
ui/call.html
├── #session-panel      → session_id input/generate, side select, "Join" button
├── #controls            → "Start Call" / "Start Agent" / "Mute" / "Deafen" / "End Call"
├── #status-badge        → idle | connecting | listening | muted | ended | error
├── #transcript-feed      → live transcript_delta lines, speaker-tagged
├── #pv-draft-panel       → live-updating PV (subject, compte_rendu, actions)
└── #pv-result-panel      → final PV + routing result (hidden until pv_result)
```

### State machine (drives the buttons)

```
idle ──Start Call──▶ in call (mic + audio bridge)
                       │  ┌──Start Agent──▶ agent listening ──Stop Agent──┐
                       │  └───────────────────────────────────────────────┘
in call ──End Call / server pv_result──▶ ended
any state ── WS error/close ──▶ error
```

- **"Start Call"** on click:
  1. Opens the WebSocket (if not already open) to `/ws/call/{session_id}/{speaker_id}?side={side}`
  2. Starts the mic capture graph, begins sending PCM frames, and plays the relayed PCM from other members (the audio bridge)
- **"Start Agent"** sends `{"type":"listen_start"}` so the backend starts transcribing this member's audio; **"Stop Agent"** sends `{"type":"listen_stop"}` — the audio bridge keeps running either way.
- Both buttons must be disabled until `session_id` exists (generated client-side) and the mic permission has been granted.

---

## 4. Audio capture pipeline (the part to get right)

**Use `AudioWorkletNode`, not the deprecated `ScriptProcessorNode`.** It runs off the
main thread, so UI updates (transcript rendering) don't cause audio glitches or
dropped frames.

```js
// 1. Get mic
const stream = await navigator.mediaDevices.getUserMedia({ audio: {
  channelCount: 1, echoCancellation: true, noiseSuppression: true
}});

// 2. AudioContext at 16kHz where supported, else resample in the worklet
const ctx = new AudioContext({ sampleRate: 16000 });
await ctx.audioWorklet.addModule('pcm-worklet.js');
const source = ctx.createMediaStreamSource(stream);
const node = new AudioWorkletNode(ctx, 'pcm-downsampler');

node.port.onmessage = (e) => {
  // e.data is an Int16Array already at 16kHz mono
  if (ws.readyState === WebSocket.OPEN && listening) {
    ws.send(e.data.buffer); // binary frame, matches backend contract
  }
};
source.connect(node);
```

`pcm-worklet.js` (AudioWorkletProcessor) job:
1. Buffer incoming Float32 frames from whatever the browser's native rate is
2. Linear or polyphase resample down to 16 kHz
3. Convert Float32 [-1,1] → Int16 PCM (`sample * 32767`)
4. Post fixed-size chunks (e.g. 20–40 ms / 320–640 samples) back to the main thread via `port.postMessage`

Ship small chunks (20–40 ms) rather than buffering large blocks — it keeps
`transcript_delta` latency low without saturating the socket.

---

## 5. Task breakdown

| File | Task |
|---|---|
| `ui/call.html` | Page shell, panels, styling (reuse `ui/index.html` dark theme) |
| `ui/call.js` | State machine, WS lifecycle, button handlers, render `transcript_delta`/`pv_draft`/`pv_result` |
| `ui/pcm-worklet.js` | AudioWorkletProcessor — resample + Float32→Int16 |
| `ui/call.js` | Generate `session_id` (`crypto.randomUUID()`) and gate "Join" on it + mic permission |
| `ui/call.js` | Mic permission handling + error states (denied permission, no device, WS reject) |
| `ui/call.js` | "End Call" → send `{"type":"end_call"}`, disable Start Agent, await `pv_result` |
| *(fast-follow, not this sprint)* | WS reconnect-with-backoff if the socket drops mid-call |

No backend pipeline changes. `side` is optional — when omitted, the backend simply
doesn't emit a `PARTICIPANTS:` manifest and the summarizer guesses left/right from
content. So for a solo agent test, default the `side` selector to `left` in the page
(the default is page-side, not server-side).

---

## 6. Testing plan

1. **Solo smoke test** — one browser tab, `side=left`, talk into mic, confirm
   `transcript_delta` renders and a `pv_draft` arrives within `PIPELINE_INTERVAL_SECONDS`.
2. **Two-tab test** — open `ui/call.html` in two tabs with the same `session_id`,
   different `speaker_id`s, one `side=left` one `side=right`; confirm both streams
   interleave correctly (cross-check against `app/transcription/merge.py` output).
3. **Cross-check against the existing headless path** — run
   `scripts/live_replay_multispeaker.py` against the same session and diff the
   resulting PV against the one produced by the browser page, to confirm the audio
   pipeline (worklet resampling) isn't introducing STT-affecting artifacts.
4. **Mute/unmute cycling** — Start Agent → Stop Agent repeatedly, confirm no
   duplicate `listen_stop` side effects and that STT still finalizes cleanly each time.
5. **End call mid-sentence** — confirm `pv_result` still arrives and the draft-reuse
   optimization (cached PV if transcript unchanged) is visibly instant in the UI.

---

## Definition of Done

- [ ] Agent can join a session, click **Start Call** to open the audio bridge, then **Start Agent** and see their own speech transcribed live
- [ ] Two simultaneous browser sessions produce one correctly interleaved transcript server-side
- [ ] PV draft panel updates without a page refresh
- [ ] Final PV + routing result renders on `pv_result`
- [ ] No backend file touched
- [ ] Manual test checklist above passes

---

# Optimized Option (Phase 2.5 — production-hardening path)

Everything above ships something correct and compatible **today**. If you want to
harden it before Phase 3 (Twilio/Recall.ai), here's what to prioritize, roughly in
order of value-for-effort:

### 1. Voice Activity Detection (VAD) gating — highest ROI, cheapest to add
Only send PCM frames when the agent is actually speaking (simple energy-threshold
VAD in the worklet, or `@ricky0123/vad-web` if you want something more robust).
Cuts bandwidth and STT load dramatically on long calls, and reduces false
`transcript_delta` noise from silence/background. Directly helps the README's
"long meetings" bottleneck since less garbage text reaches the 4500-token
summarizer cap.

### 2. Adaptive chunking + backpressure
Check `ws.bufferedAmount` before sending; if it's climbing, the network can't keep
up — drop to a lower chunk rate or larger chunk size instead of queuing unbounded
audio in memory. Prevents the "transcript falls behind and never catches up" failure
mode on flaky agent wifi.

### 3. Reconnect-with-resume
On WS close, keep buffering PCM locally (capped ring buffer), attempt reconnect
with backoff, and on reconnect flush the buffer with a `resumed_at` timestamp so
`merge.py` can splice it back in without a transcript gap. This directly closes the
README's listed gap: *"No STT reconnection — a WebSocket drop mid-call loses the
transcript."*

### 4. Client-side partial transcript reconciliation
Right now `transcript_delta` is treated as append-only. A nicer UX diffs against the
last delta for that `speaker_id` and does an in-place update (so the agent sees their
own words firm up in real time rather than seeing duplicated fragments) — cosmetic,
but agents will feel this the most since they're staring at it live during the call.

### 5. Only if you outgrow raw-PCM-over-WS: real WebRTC transport
The current design (and this sprint) is **WebSocket + raw PCM**, not actual
`RTCPeerConnection` — that's fine and is what the backend already implements. True
WebRTC only earns its complexity if you need: NAT traversal for agents off the
corporate network, opus compression to cut bandwidth ~10x, or jitter-buffer
handling for lossy mobile connections. That means standing up an SFU (mediasoup,
LiveKit, or similar) between the browser and `app/ws/call_handler.py`, which is a
Phase 3 concern alongside Twilio/Recall.ai — not worth pulling into this sprint.

**Recommended order if pursuing the optimized path:** VAD gating first (cheap, big
win), then backpressure handling, then reconnect-with-resume. Leave real WebRTC/SFU
until Phase 3 planning, since it changes the backend contract and isn't needed to
ship a working agent page.



  What I added

  1. Lobby page (/ui/lobby.html) — the new entry point:
  - Create a call → enter your name + side → generates a session → redirects to call.html.
  - Join a call → enter session id + your name + side → redirects to call.html.
  - If opened from an invite link (?session=…), the join form is pre-filled.

  2. Invite (Proposal A) — done. On call.html there's now a "🔗 Copy invite link" button that copies
  http://<host>/ui/lobby.html?session=<id>. The invitee opens it, enters their own name, and joins.

  3. Backend work. Added POST /api/call/session (returns a session_id + join path). Everything else for multi-member
  was already there — the WS handler creates sessions on first attach and supports N members.

  4. call.html now reads ?session&speaker&side from the URL, so the lobby (or an invite link) pre-fills it
  automatically.

  Your questions

  Can I invite more than one person? Yes. The invite link is one URL that works for any number of people — each invitee
  just enters their own (distinct) name, so they get separate speaker_ids. The backend cap is MAX_MEMBERS_PER_CALL = 8
  (configurable in app/config.py). Just make sure each person uses a unique name.

  How to test a call with another person while on localhost

  You have three options, easiest first:

  Option 1 — two tabs on your own machine (fastest sanity check)
  - uvicorn app.main:app --reload --port 8000
  - Open http://localhost:8000/ui/lobby.html in two tabs, create a session in one, join it from the other with a
  different name. This exercises the full multi-member path, but both tabs share your one physical mic.

  Option 2 — another person on your same WiFi/LAN
  uvicorn app.main:app --host 0.0.0.0 --port 8000   # bind to all interfaces, not just localhost
  - Find your LAN IP: ipconfig → look for the IPv4 Address (e.g. 192.168.1.23).
  - The other person opens http://192.168.1.23:8000/ui/lobby.html.
  - Important: you'll likely need to allow Python/uvicorn through Windows Firewall (inbound TCP 8000).

  Option 3 — a remote person over the internet (tunnel)
  ngrok http 8000        # or: cloudflared tunnel --url http://localhost:8000
  - ngrok prints a public https://xxxx.ngrok.io URL. Share it; the other person opens
  https://xxxx.ngrok.io/ui/lobby.html.
  - WebSockets work over ngrok/cloudflared, and my call.js already auto-switches to wss:// for https, so it just works.

  No second person available? Use the headless simulator I already built:
  python scripts/live_replay_multispeaker.py --dir tests/fixtures/sample_transcript_4person_meeting_speakers --left
  "kh,Sami" --right "Lina,Oussema"

  Verified: 136 tests pass, both pages serve 200, and POST /api/call/session returns a valid session id.

  Want me to add the QR code (Option B) next to the invite link, so a phone can scan-to-join?



  Done. Both issues are fixed, and the full test suite (136 tests) still passes.
     
  What changed
     
  1. Callers now hear each other (audio bridge)

  The server previously only fed each member's mic audio into speech-to-text — it never forwarded audio between
  members. Now:

  - app/ws/session_manager.py — added relay_audio() which forwards every member's PCM frame verbatim to the other
  members (with a per-socket send_lock so concurrent fan-in can't interleave frames).
  - app/ws/call_handler.py — every incoming binary frame is relayed to everyone else.
  - ui/pcm-player.js (new) — an AudioWorkletProcessor that plays the relayed PCM locally.
  - ui/call.js — receives relayed binary frames and plays them; capture and playback share one 16 kHz AudioContext.

  2. "Start the call" and "agent listening" are now two separate buttons

  - 📞 Start Call / Leave Call — turns on the mic + audio bridge (everyone hears each other). Nothing is transcribed
  yet.
  - 🤖 Start Agent / Stop Agent — while active, sends {"type":"listen_start"} / {"type":"listen_stop"} so the backend
  only feeds that member's audio to STT during this window. Irrelevant chatter is relayed but never transcribed.
  - Mute / Deafen / End Call operate on the call as before.

  On the server, listening is gated per-member and split into transcription segments: each listen_start → listen_stop
  period commits its authoritative transcript, so gaps (the irrelevant talk) simply don't appear in the transcript.

  Files touched

  ┌──────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────┐
  │                   File                   │                                Change                                │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
  │ app/ws/session_manager.py                │ audio relay + live_text/authoritative-text split (commit_text)       │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
  │ app/ws/call_handler.py                   │ relay frames; gate STT behind listen_start/listen_stop               │
  │                                          │ (segment-based)                                                      │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
  │ ui/pcm-player.js                         │ new playback worklet                                                 │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
  │ ui/call.html / ui/call.js                │ split Call/Agent buttons, play relayed audio                         │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
  │ scripts/live_replay_multispeaker.py      │ send listen_start, use end_call, skip relayed binary frames          │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
  │ tests/integration/test_ws_multimember.py │ updated for the new control protocol                                 │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
  │ README.md                                │ updated protocol tables + button docs                                │
  └──────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────┘

  Worth knowing

  - Behavior change: audio_end is now a legacy alias for listen_stop (still accepted). The headless replay script was
  updated to listen_start + end_call.
  - Echo: with real playback there's now acoustic echo, so I kept/added echoCancellation + autoGainControl on the mic
  capture.
  - Not verified end-to-end here: the automated tests mock STT. The audio bridge/playback and the two-button flow need
  a real-browser smoke test (open two tabs with the same session id, Start Call in both, then Start Agent) — I couldn't
  drive a microphone from this environment.