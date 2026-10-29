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

### End of lesson

A `summarize` step produces a structured summary (Pydantic): practiced skills, recurring mistakes, vocabulary, recommendations for the next lesson. It is saved to long-term memory.

## Memory

| Type | Storage | Key |
|---|---|---|
| Short-term | checkpointer (SQLite) | `thread_id = lesson_id` |
| Long-term: profile | Store (SQLite) | namespace `("users", user_id)`, key `"profile"` |
| Long-term: lessons | Store (SQLite) | namespace `("users", user_id, "lessons")`, key `lesson_id` |

One SQLite file for both. Moving to Postgres = swapping to `PostgresSaver` / `PostgresStore`.

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
