# Transcription Module — Mistral VoxTral STT

> **Package:** `app/transcription/`  
> **Provider:** [Mistral AI VoxTral](https://console.mistral.ai/api-keys)  
> **Model:** `voxtral-mini-transcribe-realtime-2602`  
> **Phase:** Phase 2 — Speech-to-Text

---

## What it does

Converts raw call audio into text. It's the first step in the pipeline — before summarization, classification, or routing can happen, the spoken words must become a transcript.

Two modes are provided:

| Mode | Function | Input | Output | Use case |
|------|----------|-------|--------|----------|
| **Batch** | `transcribe_file()` | Audio file (bytes) | Full text | Pre-recorded calls, testing |
| **Realtime** | `stream_transcribe()` | Audio chunks (stream) | Text deltas | Live calls over WebSocket |

---

## Where it fits in the pipeline

```
[ Audio source ]         [ Transcription ]        [ AI Agent ]
     │                        │                        │
     │  raw PCM audio         │                        │
     │  (mic / WS / file)     │                        │
     ├───────────────────────▶│                        │
     │                        │  transcribe_file()     │
     │                        │  or                    │
     │                        │  stream_transcribe()   │
     │                        │                        │
     │                        ├───────────────────────▶│
     │                        │  transcript text       │  summarize()
     │                        │                        │  classify()
     │                        │                        │  extract()
     │                        │                        │  route()
```

This module replaces the Phase 1 mock transcript input. Where Phase 1 used `scripts/mock_call.py` to inject pre-written text, Phase 2 feeds real transcribed text from live audio.

---

## File structure (split architecture)

Each file does exactly one thing:

```
app/transcription/
├── __init__.py       (24 lines)  Public API — re-exports all symbols
├── errors.py         ( 9 lines)  TranscribeError — single exception class
├── client.py         (64 lines)  REST batch client — upload file, get text
├── realtime.py       (140 lines) WebSocket streaming — push chunks, yield deltas
└── formats.py        (126 lines) Audio format definitions + optional conversion
```

Plus the WebSocket handler that wires everything together:

```
app/ws/
├── __init__.py
└── call_handler.py   (96 lines)  Audio WS endpoint — stream → transcribe → pipeline
```

### Why split this way

- **Debug fast.** If a transcription fails, you know whether the problem is in `client.py` (REST/HTTP) or `realtime.py` (WebSocket/streaming).
- **Read fast.** Each file fits on one screen. No scrolling through 300-line monoliths.
- **Test fast.** Each module is independently testable — mock the other one, not an entire subsystem.

### `__init__.py`
Re-exports. All consumers import from one place:
```python
from app.transcription import transcribe_file, stream_transcribe, TranscribeError
```

### `errors.py`
One exception type. Carries an optional `status_code` for HTTP-level debugging:
```python
raise TranscribeError("Mistral returned 401", status_code=401)
```

### `formats.py` — audio format handling
Defines the target format VoxTral expects (PCM S16LE, 16 kHz, mono) and provides optional conversion from other formats.

```python
from app.transcription import AudioFormat, target, matches_target, convert

# Check if your audio source matches
fmt = AudioFormat(encoding="pcm_s16le", sample_rate=16000, channels=1)
assert matches_target(fmt)  # True → no conversion needed

# Convert if needed
raw = convert(audio_bytes, from_format=AudioFormat("pcm_f32le", 44100, 2))
```

Conversion tries `pydub` (best quality, needs ffmpeg), then `numpy` (basic resampling), then pass-through with a warning. No required dependencies — if the source is already PCM S16LE 16kHz, it's instant.

### `client.py` — batch transcription
Sends a complete audio file to `POST /v1/audio/transcriptions` via `httpx`.
Supports optional `language` (ISO code like `"fr"`) and `diarize` (speaker identification).

```python
from app.transcription import transcribe_file

audio = Path("call_recording.wav").read_bytes()
text = await transcribe_file(audio, language="fr")
# text → "[14:05:03] Ahmed : Bonjour Mehdi..."
```

### `realtime.py` — streaming transcription
Opens a WebSocket to `wss://api.mistral.ai/v1/realtime/transcription`, pushes PCM audio chunks, and yields text deltas as the server transcribes them.

```python
from app.transcription import stream_transcribe

async def mic_chunks():
    while chunk := await audio_source.read():
        yield chunk  # PCM S16LE, 16 kHz

async for text_delta in stream_transcribe(mic_chunks()):
    print(text_delta, end="", flush=True)  # real-time display
```

#### WebSocket protocol (client → server)

| Message | When | Purpose |
|---------|------|---------|
| `session.update` | After handshake | Configures model + audio format |
| `input_audio_buffer.append` | Per audio chunk | Sends base64-encoded PCM audio |
| `input_audio_buffer.end` | Audio stream done | Signals no more data |

#### WebSocket protocol (server → client)

| Event | Meaning |
|-------|---------|
| `session.created` | Handshake complete |
| `transcription.text.delta` | New partial text — **yield this** |
| `transcription.segment` | Complete segment — **yield this** |
| `transcription.done` | Stream finished |
| `error` | Server error — logged as error |

---

## How it's wired — end-to-end flow

The WebSocket handler (`app/ws/call_handler.py`) is the integration point. It connects the transcription module to the existing AI pipeline:

```
[Client WS]                [call_handler]                  [Mistral STT]
     │                           │                               │
     │── binary audio chunk ────▶│                               │
     │                           │── PCM bytes ─────────────────▶│
     │                           │◀─ text delta ─────────────────│
     │◀─ {"type":"transcript_    │                               │
     │    delta","text":"..."} ──│                               │
     │                           │   (repeat for each chunk)     │
     │── client disconnects ────▶│                               │
     │                           │                               │
     │                           │  transcript = "".join(deltas) │
     │                           │       │                       │
     │                           │       ▼                       │
     │                           │  summarize(transcript)        │
     │                           │  → classify(call_type)        │
     │                           │  → extract(actions)            │
     │                           │  → route(pv)                  │
     │                           │       │                       │
     │◀─ {"type":"pv_result",    │◀──────┘                       │
     │    "pv":{...},            │                               │
     │    "routing":{...}}       │                               │
```

### What the handler does, step by step

1. **Receives audio** — `websocket.iter_bytes()` yields raw PCM chunks from the client
2. **Streams to VoxTral** — passes chunks to `stream_transcribe()`, which opens its own WS to Mistral
3. **Relays partial text** — each `transcript_delta` is sent back to the client for live captions
4. **Accumulates** — all deltas are collected into a single transcript string
5. **Runs the pipeline** — on disconnect: `summarize()` → `classify()` → `extract()` → `route()`
6. **Returns the PV** — sends the full structured result back as `pv_result`

### Graceful failure

| Scenario | Behavior |
|----------|----------|
| Client disconnects mid-call | Pipeline still runs on whatever was transcribed |
| Silent call (no speech) | Returns `error` — skips the LLM call entirely |
| Transcription API fails | Returns `error` with the Mistral error message |
| Pipeline crash | Returns `error`, logged with full traceback |

---

### Multi-member (per-device) mode

When each meeting member is a separate device with a declared identity, the
handler runs **one realtime STT session per member** instead of a single mixed
stream:

- Each member connects to `ws://host/ws/call/{session_id}/{speaker_id}`.
- `stream_transcribe` gained an `on_segment` callback — completed utterances
  are stamped with the speaker's name and arrival time.
- `app/transcription/merge.py` interleaves those labeled segments into one
  `[HH:MM:SS] Speaker : text` transcript for the summarizer.

This is the interruption-tolerant path: overlapping speech is captured by every
speaker's own session and interleaved, and no diarization is needed. See the
main `README.md` ("Multi-member (per-device) transcription") for the full
WebSocket contract.

---

## Configuration (.env)

All config comes from `app.config.settings` (loaded from `.env`):

```bash
# --- VoxTral (Mistral STT — transcription) ---
VOXTRAL_API_KEY=your-voxtral-api-key
VOXTRAL_BASE_URL=https://api.mistral.ai
VOXTRAL_MODEL=voxtral-mini-transcribe-realtime-2602
```

| Variable | Config field | Default |
|----------|-------------|---------|
| `VOXTRAL_API_KEY` | `settings.voxtral_api_key` | `""` |
| `VOXTRAL_BASE_URL` | `settings.voxtral_base_url` | `https://api.mistral.ai` |
| `VOXTRAL_MODEL` | `settings.voxtral_model` | `voxtral-mini-transcribe-realtime-2602` |

No new dependencies. Both `httpx` and `websockets` were already in `requirements.txt`.

---

## Tutorial — testing the pipeline end-to-end

### Prerequisites

```bash
# 1. Make sure .env is configured
cat .env | grep VOXTRAL
# VOXTRAL_API_KEY=<your-key>
# VOXTRAL_BASE_URL=https://api.mistral.ai
# VOXTRAL_MODEL=voxtral-mini-transcribe-realtime-2602

# 2. Install dependencies (already done)
pip install httpx websockets
```

### Test 1: Import check

```bash
python -c "
from app.transcription import (
    transcribe_file, stream_transcribe,
    TranscribeError, AudioFormat,
    target, matches_target, convert,
)
from app.ws.call_handler import call_handler
print('All imports OK')
"
```

### Test 2: Batch transcription (REST)

Transcribe a pre-recorded audio file:

```python
# scripts/test_batch_transcribe.py
import asyncio
from pathlib import Path
from app.transcription import transcribe_file, TranscribeError

async def main():
    audio = Path("test_call.wav").read_bytes()
    try:
        text = await transcribe_file(audio, language="fr")
        print("Transcript:\n", text)
    except TranscribeError as e:
        print(f"Error ({e.status_code}): {e}")

asyncio.run(main())
```

```bash
python scripts/test_batch_transcribe.py
```

### Test 3: Realtime streaming (WebSocket)

Pipe a WAV file through the realtime streamer (simulates a live call):

```python
# scripts/test_realtime_transcribe.py
import asyncio
import wave
from app.transcription import stream_transcribe, TranscribeError

async def wav_chunks(path: str, chunk_ms: int = 100):
    """Read a WAV file and yield PCM chunks simulating real-time audio."""
    with wave.open(path, "rb") as wf:
        # Must be 16kHz mono PCM for raw pass-through
        assert wf.getframerate() == 16000
        assert wf.getnchannels() == 1
        chunk_size = wf.getframerate() * chunk_ms // 1000 * 2  # 16-bit = 2 bytes
        while True:
            data = wf.readframes(chunk_size // 2)
            if not data:
                break
            yield data
            await asyncio.sleep(chunk_ms / 1000)  # real-time pacing

async def main():
    print("Streaming audio to VoxTral...")
    full = []
    try:
        async for text in stream_transcribe(wav_chunks("test_call.wav")):
            print(text, end="", flush=True)
            full.append(text)
    except TranscribeError as e:
        print(f"\nError: {e}")
        return

    print(f"\n\nDone — {len(''.join(full))} chars")

asyncio.run(main())
```

```bash
python scripts/test_realtime_transcribe.py
```

### Test 4: Full WebSocket end-to-end

Start the server, then pipe audio through a WS client:

```bash
# Terminal 1 — start the server
uvicorn app.main:app --reload --port 8000
```

```python
# scripts/test_ws_call.py
import asyncio
import wave
import websockets
import json

async def main():
    uri = "ws://localhost:8000/ws/call/test-session-001"

    async with websockets.connect(uri) as ws:
        # Read WAV and send in chunks (like a real client would)
        with wave.open("test_call.wav", "rb") as wf:
            chunk_size = wf.getframerate() * 100 // 1000 * 2  # 100ms chunks
            while True:
                data = wf.readframes(chunk_size // 2)
                if not data:
                    break
                await ws.send(data)
                await asyncio.sleep(0.1)

        # Server will process on disconnect
        print("Audio sent — waiting for PV...")

    # Receive response after disconnect
    async for msg in ws:
        print(json.dumps(json.loads(msg), indent=2))

asyncio.run(main())
```

```bash
python scripts/test_ws_call.py
```

Expected output:
```json
{"type": "transcript_delta", "session_id": "test-session-001", "text": "Bonjour "}
{"type": "transcript_delta", "session_id": "test-session-001", "text": "Mehdi, "}
...
{"type": "pv_result", "session_id": "test-session-001", "pv": {...}, "routing": {...}}
```

### Quick smoke test (no audio file needed)

Test that the module loads and config is correct:

```bash
python -c "
from app.config import settings
print('Model:', settings.voxtral_model)
print('Base URL:', settings.voxtral_base_url)
print('API key set:', bool(settings.voxtral_api_key))
"
```

Expected:
```
Model: voxtral-mini-transcribe-realtime-2602
Base URL: https://api.mistral.ai
API key set: True
```
