# CRM Vocal — Architecture & Project Structure

> **Stack:** FastAPI · Python 3.13 · WebSocket · Redis · PostgreSQL · Claude API · HubSpot API · Ora Studio API
> **Team:** kh (AI core / routing) · Ahmed (WebSocket server) · Oussema (infra / Ora Studio API)

---

## How it works — big picture

```
[ Phone Call ]
      |
      | (button click)
      v
[ WebSocket Server ]  ← Ahmed builds this
      |
      | real-time transcript stream
      v
[ AI Agent ]          ← kh builds this
   - text input (mock transcript for now, STT plugged in later)
   - summarization → PV generation
   - classification (auto-detected from content)
      |
      |----[ #appel-commercial ]----> [ HubSpot ]
      |                                  note + compte rendu + tasks + meeting
      |
      '----[ #appel-tech ]----------> [ Ora Studio ]
                                         todo list + difficulty scoring
```

**Key decisions:**
- Call type is auto-detected by the AI from the content — never declared manually by the user.
- One call = one destination. No cross-routing.
- Call platform (VoIP / SIP / GSM) is not yet defined — the pipeline is platform-agnostic.
- A simple test UI will be built locally to trigger and inspect the pipeline without curl.

---

## Development phases

The full pipeline has three phases. **We are starting with Phase 1.**
Phases 2 and 3 are fully designed and documented below — they come after Phase 1 is solid.

```
╔══════════════════════════════════════════════════════════════════╗
║  PHASE 1 — START HERE  ← current focus                           ║
║                                                                  ║
║  Input : mock text transcript (no live call, no audio)           ║
║  Goal  : build and validate the full AI + routing pipeline       ║
║                                                                  ║
║  summarizer → classifier → action_extractor → router             ║
║                                    ↓                             ║
║                        HubSpot  |  Ora Studio                    ║
╚══════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════╗
║  PHASE 2 — WebSocket + transcription  (pending Ahmed)            ║
║                                                                  ║
║  Input : real call audio stream via Ahmed's WebSocket            ║
║  Add   : transcriber.py (Whisper / Deepgram)                     ║
║          call_handler.py wired to agent pipeline                 ║
║  Test  : Recall.ai sandbox (free, Google Meet link)              ║
╚══════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════╗
║  PHASE 3 — production entry point  (pending encadrant)           ║
║                                                                  ║
║  Decide : call platform (VoIP / SIP / GSM / Recall.ai)           ║
║  Build  : trigger button location                                ║
║           (HubSpot embedded / Ora UI / standalone interface)     ║
║  Wire   : full end-to-end with real credentials                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## File structure

> Legend: `[P1]` = Phase 1 (build now) · `[P2]` = Phase 2 (WebSocket + STT) · `[P3]` = Phase 3 (production entry point)

```
crm-vocal/
│
├── app/
│   │
│   ├── main.py                        # [P1] FastAPI app entry point, router registration
│   │
│   ├── ws/
│   │   ├── __init__.py
│   │   └── call_handler.py            # [P2] WebSocket endpoint — Ahmed connects here
│   │                                  #      receives live transcript stream, triggers agent
│   │                                  #      Phase 1: replaced by mock_call.py script
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── transcriber.py             # [P2] STT: audio bytes → transcript text
│   │   │                              #      Whisper (free, self-hosted) or Deepgram API
│   │   │                              #      Phase 1: not needed, input is already text
│   │   ├── summarizer.py              # [P1] transcript text → structured PV JSON (Claude)
│   │   ├── classifier.py              # [P1] auto-detects #appel-tech vs #appel-commercial
│   │   └── action_extractor.py        # [P1] pulls tasks / owners / deadlines / difficulty
│   │
│   ├── routing/
│   │   ├── __init__.py
│   │   ├── router.py                  # [P1] reads call_type → dispatches to one destination
│   │   ├── hubspot/
│   │   │   ├── __init__.py
│   │   │   ├── client.py              # [P1] HubSpot HTTP client (OAuth2, base requests)
│   │   │   ├── notes.py               # [P1] POST /crm/v3/objects/notes
│   │   │   ├── tasks.py               # [P1] POST /crm/v3/objects/tasks
│   │   │   ├── deals.py               # [P1] PATCH /crm/v3/objects/deals/{id}
│   │   │   └── meetings.py            # [P1] POST /crm/v3/objects/meetings
│   │   │
│   │   └── ora_studio/
│   │       ├── __init__.py
│   │       ├── client.py              # [P1] Ora Studio HTTP client
│   │       └── todo.py                # [P1] POST /api/crm/tasks (Oussema's endpoint)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── pv.py                      # [P1] PV Pydantic schema — central data contract
│   │   ├── call.py                    # [P1] Call session schema
│   │   └── task.py                    # [P1] TaskItem schema
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py                 # [P1] Async SQLAlchemy session
│   │   └── models.py                  # [P1] ORM models (PVReport, CallLog)
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   └── agenda.py                  # [P1] MCP Tool reused from last year — creates RDVs
│   │
│   └── config.py                      # [P1] loads .env, exposes settings object
│
├── ui/
│   ├── index.html                     # [P1] test UI — trigger button + PV display
│   └── README.md                      # how to run locally
│   │                                  # [P3] evolves into production UI or HubSpot embed
│
├── tests/
│   ├── __init__.py
│   ├── test_summarizer.py             # [P1]
│   ├── test_classifier.py             # [P1]
│   ├── test_router.py                 # [P1]
│   ├── test_hubspot.py                # [P1]
│   └── fixtures/
│       ├── sample_transcript_tech.txt        # [P1] mock tech call
│       └── sample_transcript_commercial.txt  # [P1] mock commercial call
│
├── scripts/
│   ├── migrate.py                     # [P1] run DB migrations
│   └── mock_call.py                   # [P1] feed a transcript file → full pipeline
│                                      #      simulates Ahmed's WS during Phase 1
│
├── docker-compose.yml                 # [P1] PostgreSQL + Redis
├── Dockerfile
├── requirements.txt
├── .env.example
├── .env                               # never committed
├── .gitignore
└── README.md
```

---

## Module responsibilities

---

### ⚡ Phase 1 — build now

---

### `app/agent/summarizer.py` — kh

Takes a raw text transcript and sends it to Claude. Returns a fully structured PV JSON.
This is the most important file in the project — the prompt engineering happens here.

```python
async def summarize(transcript: str) -> dict:
    response = anthropic.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": SUMMARIZE_PROMPT.format(transcript=transcript)
        }]
    )
    return json.loads(response.content[0].text)
```

---

### `app/agent/classifier.py` — kh

Reads the generated PV content and auto-detects the call type.
Never relies on a user input — always inferred from what was actually said.

```python
async def classify(pv: dict) -> str:
    # returns "#appel-commercial" or "#appel-tech"
    # based on keywords, topics, and context in compte_rendu + subject
```

---

### `app/agent/action_extractor.py` — kh

Pulls structured tasks from the PV. For commercial calls: action items with owner + deadline.
For tech calls: same + difficulty level.

---

### `app/routing/router.py` — kh

One call, one destination. Reads `call_type` from the PV and dispatches.

```python
async def route(pv: PV):
    if pv.call_type == "#appel-commercial":
        await hubspot.create_note(pv)
        await hubspot.create_tasks(pv)
        if pv.meeting_created:
            await hubspot.create_meeting(pv)

    elif pv.call_type == "#appel-tech":
        await ora_studio.post_todo(pv)
        if pv.meeting_created:
            await mcp_agenda.create_rdv(pv)
```

---

### `app/routing/hubspot/` — kh

One file per HubSpot object. Only triggered for commercial calls.

| File | HubSpot endpoint | What it does |
|------|-----------------|--------------|
| `notes.py` | `POST /crm/v3/objects/notes` | Full PV as note on the contact |
| `tasks.py` | `POST /crm/v3/objects/tasks` | Action items as HubSpot tasks |
| `deals.py` | `PATCH /crm/v3/objects/deals/{id}` | Update deal stage if mentioned |
| `meetings.py` | `POST /crm/v3/objects/meetings` | Schedule follow-up if detected |

---

### `app/routing/ora_studio/` — kh (waiting on Oussema's API)

Only triggered for tech calls. Sends the extracted todo list — not the full PV.

```json
POST /api/crm/tasks
{
  "pv_id": "...",
  "call_date": "2026-06-18T14:00:00Z",
  "subject": "...",
  "participants": ["kh", "Oussema"],
  "tasks": [
    { "title": "Create dev + prod environments", "owner": "Oussema", "difficulty": "facile", "deadline": "2026-06-20" },
    { "title": "Implement POST /api/crm/tasks", "owner": "Oussema", "difficulty": "difficile", "deadline": "2026-06-25" }
  ]
}
```

---

### `scripts/mock_call.py` — kh

Simulates Ahmed's WebSocket during Phase 1. Feeds a text file through the full pipeline.

```powershell
python scripts/mock_call.py --file tests/fixtures/sample_transcript_tech.txt
# → runs summarizer → classifier → action_extractor → router → Ora Studio
```

---

### 🕐 Phase 2 — WebSocket + transcription (pending Ahmed)

---

### `app/ws/call_handler.py` — Ahmed

WebSocket endpoint. Ahmed's server connects here when a user clicks the trigger button.
Receives the live call stream and hands it to the agent pipeline.

```python
@app.websocket("/ws/call/{session_id}")
async def call_handler(websocket: WebSocket, session_id: str):
    await websocket.accept()
    async for chunk in websocket.iter_text():
        # chunk is either raw audio bytes or a transcript segment
        # depending on what Ahmed's WS server delivers
        await agent_pipeline.process(session_id, chunk)
```

> **Open question for encadrant:** does Ahmed's WS deliver raw audio or already-transcribed text?
> Answer determines if `transcriber.py` is needed in Phase 2 or can be skipped entirely.

---

### `app/agent/transcriber.py` — kh (Phase 2 only if audio)

Converts raw audio stream to text. Only needed if Ahmed's WebSocket sends audio bytes.
If Ahmed delivers text directly, this file is not needed.

```python
# Option A — Whisper (free, self-hosted, no API cost)
async def transcribe_whisper(audio_bytes: bytes) -> str:
    ...

# Option B — Deepgram (real-time streaming API, free tier available)
async def transcribe_deepgram(audio_stream) -> AsyncIterator[str]:
    ...
```

**Recommended for Phase 2 testing:** Recall.ai (free sandbox)
→ point it at a Google Meet link, it joins and returns a text transcript automatically.
No audio handling needed on our side.

---

### 🕐 Phase 3 — production entry point (pending encadrant decision)

---

### Call platform

The platform where the actual phone call takes place. Not yet decided.

| Option | How it works | Effort |
|--------|-------------|--------|
| Recall.ai | Bot joins a Meet/Teams/Zoom link, returns transcript | Low — already handles STT |
| Twilio + Whisper | Intercepts GSM/VoIP call, streams audio | Medium — need STT layer |
| Vapi.ai | Voice agent platform, WebSocket native | Low — built for this use case |
| Custom VoIP/SIP | Full control, more setup | High |

---

### Trigger button location

Where the user clicks to invite the agent into a call. Three options pending encadrant decision:

| Option | What to build |
|--------|--------------|
| Embedded in HubSpot | HubSpot custom card (no separate UI) |
| Ora Studio interface | Button inside Ora Studio dashboard |
| Standalone web UI | The `ui/` folder we already have — promoted to production |

---

## PV Template — Procès-Verbal

Every call produces one PV. The AI fills all fields automatically from the transcript.

### Human-readable form

```
┌─────────────────────────────────────────────────────────────────┐
│                        PROCÈS-VERBAL                            │
├─────────────────────────────────────────────────────────────────┤
│  Date         │  2026-06-18  17:30                              │
│  Call type    │  #appel-commercial  |  #appel-tech              │
├────────────────────────────┬────────────────────────────────────┤
│           LEFT             │              RIGHT                 │
│  Name   │  Ahmed           │  Name   │  Client Contact          │
│  Number │  +216 00 000 000 │  Number │  +00 0 00 00 00 00       │
│  Role   │  Ora Telecom     │  Role   │  ACME Corp         │
├────────────────────────────┴────────────────────────────────────┤
│  Subject      │  Q3 partnership proposal follow-up              │
├─────────────────────────────────────────────────────────────────┤
│  Compte rendu                                                   │
│                                                                 │
│  [Full AI-generated narrative of the call — what was            │
│   discussed, decisions made, context from each side]           │
├─────────────────────────────────────────────────────────────────┤
│  Action items                                          (commercial calls only)
│  □  Send revised proposal       →  Ahmed    │  2026-06-20       │
│  □  Prepare data handling doc   →  kh       │  2026-06-21       │
├─────────────────────────────────────────────────────────────────┤
│  Todo list (tech calls only)                                    │
│  □  Create dev environment      →  Oussema  │  facile           │
│  □  Implement API endpoint      →  Oussema  │  difficile        │
├─────────────────────────────────────────────────────────────────┤
│  Meeting scheduled  │  Yes / No                                 │
│  If yes             │  2026-06-23  10:00                        │
└─────────────────────────────────────────────────────────────────┘
```

### Pydantic schema (`app/models/pv.py`)

```python
class Participant(BaseModel):
    name: str
    phone_number: str
    role: str
    side: Literal["left", "right"]

class TaskItem(BaseModel):
    title: str
    owner: str
    deadline: date | None
    difficulty: Literal["facile", "difficile", "très difficile"] | None
    # difficulty is None for commercial calls, always set for tech calls

class PV(BaseModel):
    pv_id: str
    call_date: datetime
    call_type: Literal["#appel-commercial", "#appel-tech"]
    left: Participant
    right: Participant
    subject: str
    compte_rendu: str
    actions: list[TaskItem]       # commercial: action items with owner + deadline
                                  # tech: todo list with owner + deadline + difficulty
    meeting_created: bool
    meeting_datetime: datetime | None
```

### Example — commercial call PV

```json
{
  "pv_id": "a3f2c1d4-...",
  "call_date": "2026-06-18T17:30:00Z",
  "call_type": "#appel-commercial",
  "left": {
    "name": "Ahmed",
    "phone_number": "+216 00 000 000",
    "role": "Ora Telecom",
    "side": "left"
  },
  "right": {
    "name": "Client Contact",
    "phone_number": "+00 0 00 00 00 00",
    "role": "ACME Corp",
    "side": "right"
  },
  "subject": "Q3 partnership proposal follow-up",
  "compte_rendu": "Ahmed presented the updated pricing structure. Mehdi confirmed interest but requested a phased delivery timeline. Both agreed a formal offer should be sent before end of week. Legal review of data handling clauses required before sign-off.",
  "actions": [
    { "title": "Send revised proposal with phased timeline", "owner": "Ahmed", "deadline": "2026-06-20", "difficulty": null },
    { "title": "Prepare data handling clause documentation", "owner": "kh", "deadline": "2026-06-21", "difficulty": null }
  ],
  "meeting_created": true,
  "meeting_datetime": "2026-06-23T10:00:00Z"
}
```

### Example — tech call PV

```json
{
  "pv_id": "b7e1a9f0-...",
  "call_date": "2026-06-18T14:00:00Z",
  "call_type": "#appel-tech",
  "left": {
    "name": "kh",
    "phone_number": "+216 00 000 000",
    "role": "Ora Telecom — Dev",
    "side": "left"
  },
  "right": {
    "name": "Oussema",
    "phone_number": "+216 00 000 000",
    "role": "Ora Studio — Infra",
    "side": "right"
  },
  "subject": "Ora CRM environment setup and API contract",
  "compte_rendu": "kh and Oussema aligned on the Ora Studio API contract. Oussema confirmed dev environment ready by Friday. POST /api/crm/tasks payload structure agreed. Open: auth method (API key vs JWT) and error response format.",
  "actions": [
    { "title": "Create dev + prod environments on GitLab", "owner": "Oussema", "deadline": "2026-06-20", "difficulty": "facile" },
    { "title": "Define API auth method", "owner": "Oussema", "deadline": "2026-06-19", "difficulty": "facile" },
    { "title": "Implement POST /api/crm/tasks endpoint", "owner": "Oussema", "deadline": "2026-06-25", "difficulty": "difficile" }
  ],
  "meeting_created": false,
  "meeting_datetime": null
}
```

---

## Difficulty-based model selection (tech calls)

> This applies **now in Phase 1** for the internal pipeline, and **later in Ora Studio** when tasks are assigned to AI agents.

Every task extracted from a tech call has a difficulty level. This difficulty is not just informational — it drives **which AI model handles that task** both inside the CRM Vocal pipeline and inside Ora Studio.

### The logic

```
Task difficulty     →     Model used
─────────────────────────────────────────────────────
facile              →     GPT-4o-mini  (fast, cheap, good enough)
difficile           →     Claude Sonnet (balanced — reasoning + cost)
très difficile      →     Claude Opus  (most capable, complex reasoning)
```

### Why this matters

Ora Studio receives a todo list after every tech call. Each task has a difficulty score. When Ora Studio assigns an AI agent to work on or analyze a task, it uses this score to pick the right model — instead of using the most expensive model for everything.

This is the note from the call: *"dans ora studio pour enchainer quel model pour quel endroit"* — that is exactly this. The difficulty field is the bridge between CRM Vocal and Ora Studio's model routing.

### Where difficulty appears in the pipeline

```
action_extractor.py
    → assigns difficulty to each task (facile / difficile / très difficile)
    → based on: technical complexity signals in the transcript
                keywords like "refactor", "architecture", "intégration", "bug critique"

router.py → ora_studio/todo.py
    → sends difficulty with each task in the payload

Ora Studio (Phase 1+)
    → reads difficulty per task
    → routes to GPT-4o-mini / Claude Sonnet / Claude Opus accordingly
```

### TaskItem schema (updated)

```python
class TaskItem(BaseModel):
    title: str
    owner: str
    deadline: date | None
    difficulty: Literal["facile", "difficile", "très difficile"] | None
    model_hint: Literal[                       # derived from difficulty — sent to Ora Studio
        "gpt-4o-mini",
        "claude-sonnet-4-6",
        "claude-opus-4-6"
    ] | None

    @property
    def resolve_model(self) -> str:
        return {
            "facile": "gpt-4o-mini",
            "difficile": "claude-sonnet-4-6",
            "très difficile": "claude-opus-4-6"
        }.get(self.difficulty, "claude-sonnet-4-6")
```

### Example — tech call todo list with model hints

```json
"tasks": [
  {
    "title": "Update README with new env variables",
    "owner": "kh",
    "deadline": "2026-06-20",
    "difficulty": "facile",
    "model_hint": "gpt-4o-mini"
  },
  {
    "title": "Implement HubSpot OAuth2 flow",
    "owner": "kh",
    "deadline": "2026-06-22",
    "difficulty": "difficile",
    "model_hint": "claude-sonnet-4-6"
  },
  {
    "title": "Design multi-tenant architecture for Ora CRM",
    "owner": "Oussema",
    "deadline": "2026-06-28",
    "difficulty": "très difficile",
    "model_hint": "claude-opus-4-6"
  }
]
```

---

## Data flow — step by step

```
1.  User fills in participants (left / right) + subject in the test UI
        → POST /api/call/start  { session_id, left, right, subject }

2.  Ahmed's WS server connects (or mock_call.py feeds a transcript file)
        → ws://localhost:8000/ws/call/{session_id}

3.  Transcript text streams in during the call

4.  On call end signal:
        → summarizer.py      sends transcript to Claude → gets PV JSON
        → classifier.py      reads PV content → assigns call_type (auto)
        → action_extractor   pulls tasks out of compte_rendu

5.  router.py reads call_type:
        #appel-commercial → hubspot/ (note + tasks + meeting)
        #appel-tech       → ora_studio/ todo list + mcp/agenda.py if meeting

6.  PV saved to PostgreSQL
    Test UI displays the generated PV for inspection
```

---

## Database schema

### `call_logs`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `session_id` | VARCHAR | WebSocket session ID |
| `started_at` | TIMESTAMP | Call start time |
| `ended_at` | TIMESTAMP | Call end time |
| `left_participant` | JSONB | Name, number, role |
| `right_participant` | JSONB | Name, number, role |
| `call_type` | VARCHAR | `#appel-tech` or `#appel-commercial` |

### `pv_reports`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `call_id` | UUID | FK → call_logs |
| `subject` | TEXT | Call subject |
| `compte_rendu` | TEXT | AI-generated summary |
| `actions` | JSONB | Extracted tasks (with difficulty for tech) |
| `raw_transcript` | TEXT | Full transcript text |
| `created_at` | TIMESTAMP | Generation timestamp |
| `routed_to` | VARCHAR | `hubspot` or `ora_studio` |

---

## Open questions (ask encadrant)

| # | Question | Impact |
|---|----------|--------|
| 1 | Where does the trigger button live? (HubSpot / Ora UI / standalone) | Defines if UI needs to be built or just an API endpoint |
| 2 | What does Ahmed's WS deliver — raw audio or text transcript? | Determines if transcriber.py is needed now or later |
| 3 | Call platform decision (VoIP / SIP / GSM / Recall.ai) | Determines WebSocket input format |
| 4 | HubSpot credentials + portal access for ACME Corp | Blocking HubSpot integration |
| 5 | Ora Studio API auth method (API key vs JWT) | Blocking Ora Studio integration |

---

## What can be built right now (no blockers)

| Task | File |
|------|------|
| PV Pydantic schema | `app/models/pv.py` |
| Claude summarization prompt | `app/agent/summarizer.py` |
| Auto-classification logic | `app/agent/classifier.py` |
| Action / todo extractor | `app/agent/action_extractor.py` |
| Router dispatch (1 call = 1 destination) | `app/routing/router.py` |
| Mock transcript fixtures | `tests/fixtures/` |
| Mock call script | `scripts/mock_call.py` |
| Test UI (trigger + PV display) | `ui/` |

---

*CRM Vocal — Ora Telecom internal — June 2026*
