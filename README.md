# Language Tutor

An English-learning app. An AI tutor runs a spoken or written conversation lesson on a topic you choose (e.g. "job interview preparation"), corrects your mistakes, teaches vocabulary and remembers your progress across lessons.

- **Backend:** Python 3.12, FastAPI, LangGraph + LangChain, Claude Haiku 5.5
- **Frontend:** Next.js 16, React, TypeScript, Tailwind CSS
- **Speech:** Whisper `large-v3-turbo` (speech to text; locally on the GPU, or hosted by Groq), Kokoro-82M (text to speech, self-hosted). Replies are read aloud sentence by sentence while they stream.
- **Memory:** SQLite. Short-term memory is the LangGraph checkpointer; long-term memory is the LangGraph Store.

Design details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Deployment (Vercel + Oracle Cloud, CI/CD with GitHub Actions) is described in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Running locally

Requirements: [uv](https://docs.astral.sh/uv/), Node.js 22+, an [Anthropic API key](https://console.anthropic.com). An NVIDIA GPU is recommended for speech. On the first run the speech models (≈ 2 GB) are downloaded from Hugging Face.

```bash
# Backend (http://localhost:8000)
cd backend
cp .env.example .env      # then set ANTHROPIC_API_KEY
uv sync --extra gpu       # NVIDIA GPU; use --extra cpu without one
uv run uvicorn app.main:app --reload --port 8000
```

```bash
# Frontend (http://localhost:3000)
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000. The browser asks for microphone access the first time you click **Speak**.

Checks:

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run lint && npx tsc --noEmit
```

## Backend API

The backend exposes **13 endpoints** in 5 groups (routers), all under the `/api` prefix. Request and response shapes are defined by **Pydantic models**; FastAPI uses them to validate data and to generate the API docs. Interactive docs, where every endpoint can be called by hand, are at **http://localhost:8000/docs**.

### Endpoints

#### 1. Health: [`health.py`](backend/app/api/health.py)

| Endpoint | What it does |
|---|---|
| `GET /api/health` | Checks that the backend is alive and returns `{"status": "ok"}`. Used by the "Backend online" indicator. |

Every endpoint except health requires `Authorization: Bearer <ACCESS_KEY>` when `ACCESS_KEY` is set (always on a public server). Without it, for local development, the API is open.

#### 2. Auth: [`auth.py`](backend/app/api/auth.py)

| Endpoint | What it does |
|---|---|
| `GET /api/auth/check` | Returns 204 when the request may use the API (valid access key, or none configured) and 401 otherwise. The frontend calls it to decide whether to ask for the key. |

#### 3. Profiles: [`profiles.py`](backend/app/api/profiles.py)

| Endpoint | Request | Response | What it does |
|---|---|---|---|
| `GET /api/profiles` | – | list of `Profile` | All profiles, for the "Who is learning today?" screen. |
| `POST /api/profiles` | `ProfileCreate` | `Profile` (201) | Creates a profile from the onboarding form. |
| `GET /api/profiles/{user_id}` | – | `Profile` | One profile (404 if it does not exist). |
| `GET /api/profiles/{user_id}/progress` | – | `Progress` or `null` | The progress profile for the "Your progress" card; `null` until the first lesson is summarized. |

#### 4. Lessons: [`lessons.py`](backend/app/api/lessons.py)

| Endpoint | Request | Response | What it does |
|---|---|---|---|
| `POST /api/lessons` | `LessonCreate` | `Lesson` (201) | Creates a lesson. Without a topic, the profile's main topic is used. |
| `GET /api/lessons?user_id=…` | query parameter | list of `Lesson` | A user's lessons, newest first. |
| `GET /api/lessons/{lesson_id}` | – | `LessonDetail` | Full lesson state (conversation, corrections, vocabulary), used when a lesson page is opened or reloaded. |
| `POST /api/lessons/{lesson_id}/messages` | `SendMessageRequest` | **SSE stream** | One conversation turn with the tutor. |
| `POST /api/lessons/{lesson_id}/end` | – | `Lesson` | Ends the lesson: writes the summary and updates the progress profile. Safe to call twice. |

`/messages` does not return a single JSON object but a stream of **Server-Sent Events**, so the reply appears word by word:

| Event | Payload | Meaning |
|---|---|---|
| `token` | `{text}` | The next piece of the reply text. |
| `mistake` | `{original, corrected, explanation}` | The tutor recorded a mistake; it appears in the corrections panel right away. |
| `vocabulary` | `{word, meaning, example}` | A new word or phrase. |
| `error` | `{message}` | The turn failed. |
| `done` | `{}` | The turn is complete. |

Sending `content: null` **starts the lesson**: the tutor greets the learner and asks the first question.

#### 5. Speech: [`speech.py`](backend/app/api/speech.py)

| Endpoint | Request | Response | What it does |
|---|---|---|---|
| `POST /api/speech/transcribe` | audio file (`multipart/form-data`, field `audio`) | `TranscriptionResponse` | Microphone recording → text (Whisper, local or Groq per `STT_PROVIDER`). Learner mistakes are kept verbatim. |
| `POST /api/speech/synthesize` | `SynthesisRequest` | **WAV** file | Text → the tutor's voice (Kokoro). The frontend calls it once per sentence. |

#### Error codes

| Code | When |
|---|---|
| **401** | Missing or wrong access key. |
| **404** | The profile or lesson does not exist. |
| **409** | The lesson has already ended, or the tutor is still answering (one turn at a time per lesson). |
| **422** | Invalid input, e.g. an empty message or an empty recording. |
| **413** | The recording is larger than 10 MB. |
| **429** | Rate limit hit (`RATE_LIMIT_PER_MINUTE` per client IP, counted separately for tutor turns (`/messages` + `/end`), `/speech/transcribe` and `/speech/synthesize`). |
| **502** | The lesson summary could not be generated; the lesson stays open and can be ended again. |
| **503** | Speech is disabled (`SPEECH_ENABLED=false`). |

### Data models (Pydantic)

#### Profile: [`memory.py`](backend/app/storage/memory.py)

| Model | Fields |
|---|---|
| `ProfileCreate` | `name` (1–50 chars), `level`, `main_topic`, `goal` (optional), `preferences` (optional dict) |
| `Profile` | `ProfileCreate` fields + server-assigned `id` and `created_at` |
| `EnglishLevel` | enum `A1`–`C2`; any other value is rejected with 422 |

The "*Create* model + full model" pattern is common: the client sends only what the user entered, and the server adds the id and timestamps.

#### Lesson: [`memory.py`](backend/app/storage/memory.py), [`lessons.py`](backend/app/api/lessons.py), [`transcript.py`](backend/app/agent/transcript.py)

| Model | Fields |
|---|---|
| `LessonCreate` | `user_id`, `topic` (optional) |
| `Lesson` | `id`, `user_id`, `topic`, `status`, `created_at`, `ended_at`, `summary` |
| `LessonStatus` | `active` (in progress), `summarized` (ended with a summary), `discarded` (ended before the learner wrote anything) |
| `LessonSummary` | `summary` (2–3 sentences), `practiced`, `recurring_mistakes`, `vocabulary`, `next_steps` |
| `LessonDetail` | `lesson`, `messages`, `mistakes`, `vocabulary` |
| `ChatMessage` | `role` (`user` / `assistant`), `content`: the visible conversation, without internal messages |
| `SendMessageRequest` | `content`: the message (max 4000 chars), or `null` to start the lesson |

`LessonSummary` is also the output schema for Claude, so every summary is guaranteed to have these fields.

#### Corrections and vocabulary: [`state.py`](backend/app/agent/state.py)

| Model | Fields |
|---|---|
| `Mistake` | `original` (the learner's wording), `corrected`, `explanation` |
| `VocabularyItem` | `word`, `meaning`, `example` |

These two are `TypedDict`s rather than Pydantic classes, because they are part of the LangGraph lesson state, where plain dicts are the natural format. FastAPI documents them the same way.

#### Other models

| Model | Fields |
|---|---|
| `Progress` | `text` (cumulative description of the learner), `updated_at` |
| `TranscriptionResponse` | `text` (the recognized speech) |
| `SynthesisRequest` | `text` to read aloud (1–4000 chars) |
| `HealthResponse` | `status` |

### How it fits together

- **AI models behind the endpoints:**

  | Endpoint | Model | Notes |
  |---|---|---|
  | `/messages` | Claude Haiku 5.5 | The tutor; `low` effort, for fast replies. |
  | `/end` | Claude Haiku 5.5 | Summaries; `medium` effort. |
  | `/speech/transcribe` | Whisper `large-v3-turbo` | Locally on the GPU, or hosted by Groq (`STT_PROVIDER=groq`, used on the server) with local Whisper as the fallback. |
  | `/speech/synthesize` | Kokoro-82M | Self-hosted: GPU locally, CPU on the server. |

- **Where data is stored:**
  - Profiles, lessons and progress are long-term memory, in `backend/data/memory.db` (LangGraph Store).
  - Conversation content is short-term memory, in `backend/data/checkpoints.db` (LangGraph checkpointer).
- **Shared dependencies:** endpoints do not create the database, the agent or the speech models themselves. They receive them through FastAPI's `Depends` (see [`deps.py`](backend/app/api/deps.py)), which lets tests swap in fake models without calling paid APIs.
- **Frontend types:** the frontend does not define these models by hand. `npm run gen:api` generates TypeScript types from the backend's OpenAPI schema, so both sides always match.

## Configuration

Backend settings are read from `backend/.env` (see [`backend/.env.example`](backend/.env.example)):

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | Required. |
| `LLM_MODEL` | `anthropic:claude-haiku-5-5` | LangChain model id (`provider:model`). |
| `TUTOR_EFFORT` / `SUMMARY_EFFORT` | `low` / `medium` | Reasoning effort for tutor replies and summaries. |
| `STALE_LESSON_HOURS` | `6` | Lessons idle for longer are summarized automatically at startup. |
| `SPEECH_ENABLED` | `true` | Turns the speech endpoints on or off. |
| `STT_PROVIDER` | `local` | Speech to text: `local` (Whisper in the backend) or `groq` (Groq's hosted Whisper; local Whisper is the fallback). |
| `GROQ_API_KEY` / `GROQ_STT_MODEL` | – / `whisper-large-v3-turbo` | Groq API key ([console.groq.com](https://console.groq.com/keys)) and model, used when `STT_PROVIDER=groq`. |
| `WHISPER_MODEL` / `WHISPER_DEVICE` | `large-v3-turbo` / `auto` | Local speech-to-text model and device (`auto`, `cuda`, `cpu`). |
| `TTS_VOICE` | `af_heart` | Kokoro voice; the first letter is the accent (`a` = American, `b` = British). |
| `ACCESS_KEY` | empty | Shared secret required as `Authorization: Bearer <key>`. Empty disables auth (local only). |
| `RATE_LIMIT_PER_MINUTE` | `30` | Requests per minute per client IP, for each group: tutor turns, transcription, synthesis; `0` = unlimited. |
| `CORS_ORIGINS` / `CORS_ORIGIN_REGEX` | `["http://localhost:3000"]` / none | Origins allowed to call the API from a browser. |
