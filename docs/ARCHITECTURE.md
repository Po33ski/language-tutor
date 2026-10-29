# Architecture

Local-only English tutor: Next.js frontend, FastAPI backend, LangGraph agent on Claude Haiku 5.5, local speech models (Whisper for STT, Kokoro for TTS).

## Overview

```
┌──────────────── Next.js (localhost:3000) ────────────────┐
│ /profiles  /onboarding  /lesson/[id]  /history           │
│ chat + microphone (MediaRecorder) + audio playback       │
└───────────────┬──────────────────────────────────────────┘
                │ REST + SSE (streamed replies)
┌───────────────▼──────── FastAPI (localhost:8000) ────────┐
│ api/      profiles · lessons · chat (SSE) · stt · tts    │
│ agent/    LangGraph graph (tutor + summarizer)           │
│ speech/   Whisper (STT) + Kokoro (TTS), loaded once at   │
│           startup on GPU                                 │
│ storage/  SQLite: checkpointer (short-term)              │
│                   + Store (long-term)                    │
└───────────────┬──────────────────────────────────────────┘
                ▼
        Anthropic API (claude-haiku-5-5)
```

## Users

- Multiple local profiles, no login. The user picks or creates a profile on start; the selected `user_id` is kept in browser storage.
- Auth can be added later without changing the data model (everything is already keyed by `user_id`).

## Onboarding questionnaire

- A form, filled once per profile: name, English level, main topic, goal, optional preferences.
- Starting a new lesson only asks for the lesson topic (defaults to the main topic).

## Agent (LangGraph)

### Lesson state (short-term memory)

| Field | Description |
|---|---|
| `messages` | conversation history (`add_messages` reducer) |
| `profile` | snapshot of name, level, preferences, loaded at lesson start |
| `topic` | lesson topic |
| `previous_summaries` | last N lesson summaries, loaded at lesson start |
| `mistakes` | append-only list of recorded mistakes |
| `vocabulary` | append-only list of new vocabulary |

### Turn flow

```
START → tutor ──(tool calls?)──► tools ──► tutor → END
```

- **`tutor`** — Haiku with a system prompt built from profile, topic and previous summaries. Drives the lesson; reply is streamed.
- **Tools:**
  - `record_mistake(original, corrected, explanation)` — appends to `mistakes`.
  - `add_vocabulary(word, meaning, example)` — appends to `vocabulary`.
  - `save_preference(key, value)` — writes to the long-term profile.
- **Corrections UX:** the tutor mentions a correction briefly and naturally in its reply; full details (original, corrected, explanation) are shown in a side panel fed by `mistakes`.

### End of lesson (summarization)

Done by the same model (Claude Haiku 5.5); cost ≈ $0.003 per lesson.

**Triggers**
- The user clicks "End lesson".
- Fallback: lessons left unfinished (tab closed) are summarized automatically the next time the app starts, so no lesson is lost from long-term memory.

**Input**
- The full lesson transcript (checkpointer state).
- `mistakes` and `vocabulary` already recorded by the tutor's tools — the summarizer does not have to re-extract them.

**Output 1 — lesson summary** (Pydantic `LessonSummary`):
`topic`, `date`, `summary` (2–3 sentences), `practiced`, `recurring_mistakes`, `vocabulary`, `next_steps`.

**Output 2 — progress profile update.** A short cumulative text describing the learner (strengths, persistent problems, estimated level). After each lesson Haiku *updates* the previous version with the new summary instead of rewriting it from scratch.

**What the tutor sees at lesson start** (prompt size stays constant regardless of lesson count):
- profile (name, level, preferences),
- progress profile,
- the 3 most recent lesson summaries.

**Implementation note:** Haiku 5.5 uses adaptive thinking by default, and Anthropic rejects forced tool use together with thinking. LangChain's default `with_structured_output` relies on forced tool use, so use the native structured output mode (`with_structured_output(..., method="json_schema")`) and cover it with a test.

## Memory

| Type | Storage | Key |
|---|---|---|
| Short-term | checkpointer (`data/checkpoints.db`) | `thread_id = lesson_id` |
| Long-term: profiles | Store (`data/memory.db`) | namespace `("profiles",)`, key `user_id` |
| Long-term: lessons | Store | namespace `("lessons",)`, key `lesson_id`; value has `user_id`, `topic`, `status` (`active` / `summarized`), `summary` |
| Long-term: progress profile | Store | namespace `("users", user_id)`, key `"progress"` |

Checkpointer and store use separate SQLite files so their writes never contend for the same lock. Moving to Postgres = swapping to `PostgresSaver` / `PostgresStore`.

## Lesson API

| Endpoint | Purpose |
|---|---|
| `POST /api/lessons` | create a lesson (topic defaults to the profile's main topic) |
| `GET /api/lessons?user_id=` | list a user's lessons, newest first |
| `GET /api/lessons/{id}` | visible chat history + mistakes + vocabulary |
| `POST /api/lessons/{id}/messages` | run one tutor turn, streamed as SSE: `token`, `mistake`, `vocabulary`, `error`, `done` |

- `content: null` starts the lesson: learner context is copied from long-term memory into the lesson state together with a hidden `[START_LESSON]` message, and the tutor speaks first.
- One turn at a time per lesson (per-lesson lock; a second request gets 409).
- The system prompt is built from lesson state, so it stays byte-identical for the whole lesson (required by Haiku's thinking-block binding, and good for prompt caching). The model runs with `prefix_mismatch_behavior: "drop_block"` so a lesson survives code changes to the prompt or tools.

## Voice flow (MVP)

1. Push-to-talk: browser records audio (MediaRecorder).
2. `POST /api/stt` → Whisper (`faster-whisper`, large-v3-turbo) → text.
3. Text is sent immediately as a chat message (no confirmation step).
4. `POST /api/lessons/{id}/messages` → tutor reply streamed via SSE.
5. `POST /api/tts` → Kokoro → audio played in the browser.

- A text input is always available as an alternative to the microphone.
- Known risk: Whisper may "auto-correct" learner grammar in transcripts. Test with intentionally wrong sentences; fall back to NVIDIA Parakeet if needed.
- Later: sentence-by-sentence TTS to reduce latency.

## Repo layout

```
backend/   app/{api, agent, speech, storage, config.py, main.py}, tests/   (uv, ruff, pytest)
frontend/  src/{app/{profiles, onboarding, lesson/[id], history}, components, lib/api}  (Next.js 16, Tailwind 4 + shadcn/ui)
docs/      ARCHITECTURE.md
```

- Frontend calls `localhost:8000` directly with CORS enabled (no Next.js proxy, which can buffer SSE).
- TypeScript API types are generated from the FastAPI OpenAPI schema (`openapi-typescript`).

## Environment notes

- Python 3.12+ via `uv` (system Python is 3.9).
- GPU: RTX 5070 Ti (Blackwell) — needs recent PyTorch/CUDA builds; verify on first speech model run.
