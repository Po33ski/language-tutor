# Architecture

Local-only English tutor: Next.js frontend, FastAPI backend, LangGraph agent on Claude Haiku 5.5, local speech models (Whisper for STT, Kokoro for TTS).

## Overview

```
┌──────────────── Next.js (localhost:3000) ────────────────┐
│ /  (profiles, lessons, progress)  /onboarding  /lesson/[id] │
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
- **Middleware:** `tutor_prompt` builds the system prompt from lesson state; `end_turn_if_already_replied` skips the model call after tool results when the tutor already wrote its reply together with the tool calls (otherwise Haiku sometimes repeats the reply, or ends with an empty one).
- **Correction quality:** rules in the prompt (one natural version, smallest change, check prepositions/articles/collocations, ask instead of guessing) were checked on 15 typical learner sentences, 7 of them not mentioned in the prompt and 1 already correct.
- **Corrections UX:** the tutor mentions a correction briefly and naturally in its reply; full details (original, corrected, explanation) are shown in a side panel fed by `mistakes`.

### End of lesson (summarization)

Done by the same model (Claude Haiku 5.5, effort `medium`) in `app/agent/summarizer.py`, orchestrated by `app/agent/wrapup.py`; ≈ 10 s and ≈ $0.003 per lesson.

**Triggers**
- The user clicks "End lesson" → `POST /api/lessons/{id}/end` (idempotent; returns the updated lesson).
- Fallback: at startup a background task ends every active lesson idle for more than `STALE_LESSON_HOURS` (default 6; last activity = the lesson's latest checkpoint). The threshold keeps `uvicorn --reload` restarts from closing lessons that are in progress.
- A lesson where the learner never wrote anything gets status `discarded` and no summary (no LLM call).
- If the summary call fails, the lesson stays `active` (502) so it can be retried. A failed progress update is logged and does not undo the saved summary.

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
| Long-term: lessons | Store | namespace `("lessons",)`, key `lesson_id`; value has `user_id`, `topic`, `status` (`active` / `summarized` / `discarded`), `ended_at`, `summary` |
| Long-term: progress profile | Store | namespace `("users", user_id)`, key `"progress"` |

Checkpointer and store use separate SQLite files so their writes never contend for the same lock. Moving to Postgres = swapping to `PostgresSaver` / `PostgresStore`.

## Lesson API

| Endpoint | Purpose |
|---|---|
| `POST /api/lessons` | create a lesson (topic defaults to the profile's main topic) |
| `GET /api/lessons?user_id=` | list a user's lessons, newest first |
| `GET /api/lessons/{id}` | visible chat history + mistakes + vocabulary |
| `POST /api/lessons/{id}/messages` | run one tutor turn, streamed as SSE: `token`, `mistake`, `vocabulary`, `error`, `done` |
| `POST /api/lessons/{id}/end` | end the lesson: summary + progress profile update |
| `GET /api/profiles/{id}/progress` | the learner's progress profile (null before the first summary) |

- `content: null` starts the lesson: learner context is copied from long-term memory into the lesson state together with a hidden `[START_LESSON]` message, and the tutor speaks first.
- One turn at a time per lesson (per-lesson lock; a second request gets 409).
- The system prompt is built from lesson state, so it stays byte-identical for the whole lesson (required by Haiku's thinking-block binding, and good for prompt caching). The model runs with `prefix_mismatch_behavior: "drop_block"` so a lesson survives code changes to the prompt or tools.

## Voice flow

1. The learner clicks **Speak**; the browser records with MediaRecorder (webm/opus) until **Stop**.
2. `POST /api/speech/transcribe` (multipart `audio`) → Whisper (`faster-whisper`, `large-v3-turbo`, English, VAD on, no `initial_prompt`) → `{text}`.
3. The text is sent immediately as a chat message (no confirmation step).
4. `POST /api/lessons/{id}/messages` → tutor reply streamed via SSE.
5. When the reply is complete and **Voice on** is set, `POST /api/speech/synthesize` → Kokoro (`af_heart`) → WAV played in the browser. Every tutor message also has a replay button.

- A text input is always available as an alternative to the microphone.
- Whisper keeps learner mistakes verbatim (tested: "I am work as developer since five years", "she have", "I have went"). An `initial_prompt` made it correct grammar, so none is used.
- Both models run in the backend process on the GPU (`app/speech/`); blocking calls run in threads, and the models load in a background task at startup (first run downloads them from Hugging Face, ≈ 2 GB). Speed on an RTX 5070 Ti: ≈ 0.05 s to synthesize a reply, ≈ 1 s to transcribe an answer.
- CUDA: PyTorch (Kokoro) ships CUDA 13 libraries, but CTranslate2 (Whisper) needs CUDA 12 cuBLAS, provided by `nvidia-cublas-cu12` and preloaded in `app/speech/cuda.py`. `av` is pinned below 16 for `faster-whisper` 1.2.
- `SPEECH_ENABLED=false` turns speech off (the endpoints return 503).
- Later: sentence-by-sentence TTS while the reply streams, to cut the wait before the voice starts.

## Repo layout

```
backend/   app/{api, agent, speech, storage, config.py, main.py}, tests/   (uv, ruff, pytest)
frontend/  src/{app/{onboarding, lesson/[id]}, components, hooks, lib/api}  (Next.js 16, Tailwind 4)
docs/      ARCHITECTURE.md
```

- Frontend calls `localhost:8000` directly with CORS enabled (no Next.js proxy, which can buffer SSE).
- TypeScript API types are generated from the FastAPI OpenAPI schema (`openapi-typescript`).

## Environment notes

- Python 3.12+ via `uv` (system Python is 3.9).
- GPU: RTX 5070 Ti (Blackwell) — needs recent PyTorch/CUDA builds; verify on first speech model run.
