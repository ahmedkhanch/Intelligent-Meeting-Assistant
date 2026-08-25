# Intelligent Meeting Assistant (CRM Vocal)

An AI-powered call-analysis pipeline for **Ora Telecom**. It takes a phone-call transcript (text file, REST, or live audio) and produces a structured **Procès-Verbal (PV)** report, then routes the resulting tasks automatically:

- **Commercial calls** → **HubSpot** (contact → deal → line items → note → appointment)
- **Technical calls** → **Ora Studio** (todo list with per-task AI-model routing hints)

The call type is **auto-detected by the LLM** — never declared manually.

> **Stack:** FastAPI · Python 3.13 · DeepSeek (OpenAI-compatible LLM) · Mistral VoxTral (STT) · PostgreSQL · Redis · WebSocket · Next.js fallback UI · Docker

---

## Pipeline

A call flows through four stages:

1. **Transcribe** — audio → text (VoxTral: batch upload or real-time streaming)
2. **Summarize** — transcript → structured PV JSON (DeepSeek)
3. **Classify & extract** — validate call type, extract validated action items → model hints
4. **Route** — commercial → HubSpot, technical → Ora Studio

**One call = one destination.**

---

## Getting started

### Prerequisites

- **Python 3.11+** (3.13 used in Docker)
- **Docker** — optional, for PostgreSQL + Redis
- **`DEEPSEEK_API_KEY`** — required for LLM summarization
- **`VOXTRAL_API_KEY`** — required for audio transcription

### Quick start

```bash
# 1. Create + activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Unix
# .venv\Scripts\activate         # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env             # then fill in DEEPSEEK_API_KEY and VOXTRAL_API_KEY

# 4. (Optional) Start PostgreSQL + Redis
docker compose up -d

# 5. Launch the API + test UI
uvicorn app.main:app --reload --port 8000
```

> **No API keys?** You can still run the full test suite (it mocks every external service). Real LLM/STT calls require the keys above.

---

## Run with Docker (dev, hot reload)

The whole stack — backend, frontend, Postgres, Redis, and a `tools` shell for the CLI
scripts and tests — runs in one command:

```bash
# Build and start everything
docker compose up -d --build

# Watch the logs
docker compose logs -f backend frontend
```

| Service | URL / port | Purpose |
|---------|-----------|---------|
| `backend` | http://localhost:8000 | FastAPI API + WebSocket + test UI (`/`) |
| `frontend` | http://localhost:3000 | Next.js fallback dashboard |
| `tools` | — (idle shell) | Run scripts, audio generation, and tests |
| `postgres` | localhost:5432 | PostgreSQL 16 |
| `redis` | localhost:6379 | Redis 7 |

Secrets are injected from `.env` (kept out of git). `docker-compose.yml` overrides the
DB/Redis/fallback-store hostnames to the container service names.

### Run scripts and tests inside Docker

```bash
# Run the full test suite (hermetic — no external calls)
docker compose exec tools python -m pytest -q

# Text transcript → full pipeline
docker compose exec tools python scripts/mock_call.py --file tests/fixtures/sample_transcript_tech.txt

# Generate meeting audio (ffmpeg + edge-tts are already in the image)
docker compose exec tools python scripts/generate_meeting_audio.py --file tests/fixtures/sample_transcript_tech.txt --format wav

# Audio file → batch STT → pipeline
docker compose exec tools python scripts/e2e_test.py --audio tech_meeting_test.wav

# Audio file → realtime stream → pipeline
docker compose exec tools python scripts/live_replay.py --audio tech_meeting_test.wav --speed 2
```

Stop the stack with `docker compose down` (add `-v` to also wipe the Postgres/Redis and
fallback-store volumes).

> **Note:** `uvicorn --reload` and `next dev` pick up edits from the bind-mounted
> source, so code changes reflect without rebuilding the image.

---

## How to run — full pipeline

The fastest way to see it end-to-end is the CLI — no server needed. There are three entry points depending on where you start:

### 1. From a text transcript (no STT)

```bash
python scripts/mock_call.py --file tests/fixtures/sample_transcript_tech.txt
python scripts/mock_call.py --file tests/fixtures/sample_transcript_commercial.txt
python scripts/mock_call.py --text "Ahmed: Bonjour... Kh: Bonjour..." --json
```

### 2. From an audio file (batch STT — upload whole file)

```bash
python scripts/e2e_test.py --audio tech_meeting_test.wav --language fr
python scripts/e2e_test.py --audio commercial_meeting_test.wav --language fr
```

### 3. From an audio file (real-time streaming STT)

```bash
python scripts/live_replay.py --audio tech_meeting_test.wav --speed 2
```

### 4. As a server (REST + WebSocket + UI)

```bash
uvicorn app.main:app --reload --port 8000
# open http://localhost:8000
```

---

## How to test with audio (batch vs stream)

There are **two STT paths**. Pick the one that matches what you're testing:

| Path | Script | How it works | Best for |
|------|--------|--------------|----------|
| **Batch** | `scripts/e2e_test.py --audio` | Uploads the whole file to VoxTral at once | Fast end-to-end checks, MP3 or WAV |
| **Stream** | `scripts/live_replay.py --audio` | Streams chunks in real time (as a live call would) | Real-time path, live captions, pacing |

### Batch (fast — uploads the whole file)

```bash
# Tech call → routes to Ora Studio
python scripts/e2e_test.py --audio tech_meeting_test.wav

# Commercial call → routes to HubSpot
python scripts/e2e_test.py --audio commercial_meeting_test.wav

# Options
python scripts/e2e_test.py --audio tech_meeting_test.wav --language fr --json   # JSON-only output
python scripts/e2e_test.py --audio tech_meeting_test.wav --diarize              # speaker diarization
python scripts/e2e_test.py --audio tech_meeting_test.wav --save-transcript out.txt  # dump STT text
python scripts/e2e_test.py --audio tech_meeting_test.wav --date "2026-08-25T09:00:00"
```

Batch accepts `.wav` **or** `.mp3`. `--transcript` skips STT entirely (same as `mock_call.py`).

### Stream (real-time — paced, with live captions)

```bash
# Full file, real-time speed
python scripts/live_replay.py --audio tech_meeting_test.wav

# Options
python scripts/live_replay.py --audio tech_meeting_test.wav --speed 2          # 2× faster
python scripts/live_replay.py --audio tech_meeting_test.wav --max-seconds 30   # first 30s only
python scripts/live_replay.py --audio tech_meeting_test.wav --chunk-ms 200     # chunk size
python scripts/live_replay.py --audio tech_meeting_test.wav --no-pipeline      # STT only (skip AI)
python scripts/live_replay.py --audio tech_meeting_test.wav --json             # JSON-only output
```

Streaming **requires a WAV** (PCM S16LE, 16 kHz, mono) — `generate_meeting_audio.py` produces exactly that.

### Sample audio

Two samples are committed in the repo root:

| File | Type | Size | Routes to |
|------|------|------|-----------|
| `tech_meeting_test.wav` | Technical call | ~6 MB | Ora Studio |
| `commercial_meeting_test.wav` | Commercial call | ~4 MB | HubSpot |

---

## How to generate audio

Synthesize a realistic meeting recording from any timestamped transcript (Microsoft Edge TTS — free, no API key).

```bash
# Extra deps (not in requirements.txt)
pip install edge-tts          # pydub optional

# ffmpeg must be on PATH  (Windows: winget install ffmpeg)
```

```bash
# Generate MP3 + WAV (WAV is 16 kHz mono — ready for STT)
python scripts/generate_meeting_audio.py --file tests/fixtures/sample_transcript_tech.txt --format both

# Generate a commercial-call sample
python scripts/generate_meeting_audio.py --file tests/fixtures/sample_transcript_commercial.txt --format both

# Custom output path / only MP3
python scripts/generate_meeting_audio.py --file tests/fixtures/sample_transcript_tech.txt -o my_meeting.mp3

# One WAV per speaker (for multi-member / per-device replay)
python scripts/generate_meeting_audio.py --file tests/fixtures/sample_transcript_4person_meeting.txt --split-speakers

# List available French voices
python scripts/generate_meeting_audio.py --list-voices
```

The transcript format is timestamped dialogue — one `[HH:MM:SS] Speaker: text` line per utterance (see the fixtures in `tests/fixtures/`).

---

## How to run the test suite

The suite is **hermetic** — an autouse fixture forces every external client into mock mode, so no test touches the real DeepSeek / HubSpot / Ora Studio / Mistral APIs regardless of what `.env` contains.

```bash
# Full suite
python -m pytest

# One area
python -m pytest tests/unit
python -m pytest tests/integration
python -m pytest tests/test_multi_participant.py
```

| Path | Coverage |
|------|----------|
| `tests/unit/` | Summarizer JSON parsing, classifier, action extractor, models, HubSpot formatting/timestamps, merge, transcription, fallback store, session manager, MCP agenda, Ora Studio |
| `tests/integration/` | REST endpoints, router dispatch, multi-member WebSocket — all in-process |
| `tests/test_multi_participant.py` | Regression: 3+ speaker meetings, `additional_participants` |
| `tests/fixtures/` | French transcripts (tech, commercial, ambiguous, 4-person) + audio + per-speaker WAVs |

Configuration lives in `pytest.ini` (`testpaths = tests`, `pythonpath = .`, `asyncio_mode = auto`).

---

## Scripts

| Script | Purpose |
|--------|---------|
| `mock_call.py` | Text transcript → full pipeline (no STT, no server) |
| `e2e_test.py` | Audio file → **batch** STT → pipeline |
| `live_replay.py` | Audio file → **real-time** STT → pipeline |
| `live_replay_multispeaker.py` | Simulate the multi-member WebRTC page (needs a running server) |
| `generate_meeting_audio.py` | Synthesize meeting audio from a transcript (edge-tts) |
| `list_fr_voices.py` | List available French TTS voices |
| `migrate.py` | Create DB tables |
| `seed_fallback.py` | Seed the fallback store with sample PVs |

---

## Configuration

All settings are read from `.env` (see `.env.example`). Required keys in **bold**.

| Variable | Required | Purpose |
|----------|----------|---------|
| **`DEEPSEEK_API_KEY`** | ✅ (for LLM) | DeepSeek key for summarization |
| `DEEPSEEK_BASE_URL` | — | defaults to `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | — | defaults to `deepseek-chat` |
| **`VOXTRAL_API_KEY`** | ✅ (for audio) | Mistral key for transcription |
| `VOXTRAL_MODEL` | — | batch STT model |
| `VOXTRAL_REALTIME_MODEL` | — | realtime STT model |
| `HUBSPOT_ACCESS_TOKEN` | Phase 3 | PAT (preferred over OAuth) |
| `ORA_STUDIO_API_URL` / `ORA_STUDIO_API_KEY` | Phase 3 | Ora Studio integration |
| `DATABASE_URL` | — | PostgreSQL (async) |
| `REDIS_URL` | — | Redis |

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | Test UI (`ui/index.html`) |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/call/start` | Register a call session |
| `POST` | `/api/call/process` | Run the full pipeline on a transcript → PV + routing |
| `WS` | `/ws/call/{session_id}/{speaker_id}` | Multi-member real-time call |

---

## Related docs

- **[`INPUT_SCHEMA.md`](INPUT_SCHEMA.md)** — the transcript format the summarizer expects.
- **[`README_DEV.md`](README_DEV.md)** — internal development notes and sprint logs.
- **[`README_ARCH.md`](README_ARCH.md)** — earlier architecture/design document.

---

*Intelligent Meeting Assistant (CRM Vocal) — Ora Telecom internal.*
