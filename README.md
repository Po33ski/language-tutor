# Language Tutor

An English-learning app. An AI tutor runs a spoken or written conversation lesson on a topic you choose (e.g. "job interview preparation"), corrects your mistakes, teaches vocabulary and remembers your progress across lessons.

- **Backend:** Python 3.12, FastAPI, LangGraph + LangChain, Claude Haiku 5.5
- **Frontend:** Next.js 16, React, TypeScript, Tailwind CSS
- **Speech:** Whisper `large-v3-turbo` (speech to text; locally on the GPU, or hosted by Groq), Kokoro-82M (text to speech, self-hosted; the full PyTorch model by default, with a quantized ONNX build available for testing and as an alternative). Replies are read aloud sentence by sentence while they stream.
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

The backend exposes **17 endpoints** in 5 groups (routers), all under the `/api` prefix. Request and response shapes are defined by **Pydantic models**; FastAPI uses them to validate data and to generate the API docs. Interactive docs, where every endpoint can be called by hand, are at **http://localhost:8000/docs**.

### Endpoints

#### 1. Health: [`health.py`](backend/app/api/health.py)

| Endpoint | What it does |
|---|---|
| `GET /api/health` | Checks that the backend is alive and returns `{"status": "ok"}`. The home screen uses it to warn when the server cannot be reached. |

Every endpoint except health, signup and login requires a session: `Authorization: Bearer <token>`, with the token from signup or login. Profiles and lessons are always the signed-in account's own; someone else's lesson answers 404.

#### 2. Auth: [`auth.py`](backend/app/api/auth.py)

| Endpoint | Request | Response | What it does |
|---|---|---|---|
| `POST /api/auth/signup` | `Credentials` | `AuthResponse` (201) | Creates an account and signs in. Password: at least 15 characters, not breached, not containing the email (NIST SP 800-63B-4). 409 if the email is taken. |
| `POST /api/auth/login` | `Credentials` | `AuthResponse` | Signs in. Wrong email and wrong password give the same 401, so it does not reveal which emails have accounts. |
| `POST /api/auth/logout` | – | 204 | Ends this session. |
| `GET /api/auth/me` | – | `Account` | The signed-in account; `has_profile` says whether onboarding is done. |
| `POST /api/auth/password` | `PasswordChange` | 204 | Changes the password (403 if the current one is wrong) and signs out every other session. |

#### 3. Profile: [`profiles.py`](backend/app/api/profiles.py)

One learner profile per account.

| Endpoint | Request | Response | What it does |
|---|---|---|---|
| `GET /api/profile` | – | `Profile` | The account's profile; 404 until onboarding is done. |
| `POST /api/profile` | `ProfileCreate` | `Profile` (201) | Creates it from the onboarding form; 409 if it exists. |
| `PUT /api/profile` | `ProfileCreate` | `Profile` | Replaces the main preferences (the edit-profile page sends every field); 404 before onboarding. Lessons in progress keep the settings they started with. |
| `GET /api/profile/progress` | – | `Progress` or `null` | The progress profile for the "Your progress" card; `null` until the first lesson is summarized. |

#### 4. Lessons: [`lessons.py`](backend/app/api/lessons.py)

| Endpoint | Request | Response | What it does |
|---|---|---|---|
| `POST /api/lessons` | `LessonCreate` | `Lesson` (201) | Creates a lesson. Without a topic, the profile's main topic is used. |
| `GET /api/lessons` | – | list of `Lesson` | The account's lessons, newest first. |
| `GET /api/lessons/{lesson_id}` | – | `LessonDetail` | Full lesson state (conversation, corrections, vocabulary, time left), used when a lesson page is opened or reloaded. |
| `POST /api/lessons/{lesson_id}/messages` | `SendMessageRequest` | **SSE stream** | One conversation turn with the tutor. |
| `POST /api/lessons/{lesson_id}/end` | – | `Lesson` | Ends the lesson: writes the summary and updates the progress profile. Safe to call twice. |

`/messages` does not return a single JSON object but a stream of **Server-Sent Events**, so the reply appears word by word:

| Event | Payload | Meaning |
|---|---|---|
| `token` | `{text}` | The next piece of the reply text. |
| `mistake` | `{original, corrected, explanation}` | The tutor recorded a mistake; it appears in the corrections panel right away. |
| `vocabulary` | `{word, meaning, example}` | A new word or phrase. |
| `error` | `{message}` | The turn failed. |
| `time_up` | `{}` | The lesson's time was over, so this reply was the tutor's goodbye; the client ends the lesson. |
| `blocked` | `{message, category}` | Moderation stopped the learner's message (see [Moderation](#moderation)): the tutor never saw it and it is not stored. Followed by `done`. |
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
| **401** | Not signed in (no, unknown or expired session), or wrong email/password at login. |
| **403** | Wrong current password when changing it. |
| **404** | The profile or lesson does not exist. |
| **409** | The lesson has already ended, or the tutor is still answering (one turn at a time per lesson). |
| **422** | Invalid input, e.g. an empty message or an empty recording. |
| **413** | The recording is larger than 10 MB. |
| **429** | Daily limit reached (per account or for the whole app), too many signups from one network or failed logins, or a rate limit hit (`RATE_LIMIT_PER_MINUTE` per account, counted separately for tutor turns (`/messages` + `/end`), `/speech/transcribe` and `/speech/synthesize`). |
| **502** | The lesson summary could not be generated; the lesson stays open and can be ended again. |
| **503** | Speech is disabled (`SPEECH_ENABLED=false`). |

### Data models (Pydantic)

#### Accounts: [`auth.py`](backend/app/api/auth.py)

| Model | Fields |
|---|---|
| `Credentials` | `email` (validated, stored lowercase), `password` |
| `AuthResponse` | `token` (the session token; send it as `Authorization: Bearer <token>`), `account` |
| `Account` | `id`, `email`, `created_at`, `has_profile` |
| `PasswordChange` | `current_password`, `new_password` |

#### Profile: [`models.py`](backend/app/domain/learners/models.py)

| Model | Fields |
|---|---|
| `ProfileCreate` | `name` (1–50 chars), `level`, `main_topic`, `goal` (optional), `preferences` (optional dict: `notes` from the form, other keys saved by the tutor), `lesson_minutes` (5–30, default 15) |
| `Profile` | `ProfileCreate` fields + server-assigned `id` and `created_at` |
| `EnglishLevel` | enum `A1`–`C2`; any other value is rejected with 422 |

The "*Create* model + full model" pattern is common: the client sends only what the user entered, and the server adds the id and timestamps.

#### Lesson: [`models.py`](backend/app/domain/lessons/models.py), [`lessons.py`](backend/app/api/lessons.py), [`transcript.py`](backend/app/infra/agent/transcript.py)

| Model | Fields |
|---|---|
| `LessonCreate` | `topic` (optional); the lesson belongs to the signed-in account |
| `Lesson` | `id`, `user_id`, `topic`, `status`, `created_at` (the lesson clock starts here), `duration_minutes` (copied from the profile; `null` for older lessons), `ended_at`, `summary` |
| `LessonStatus` | `active` (in progress), `summarized` (ended with a summary), `discarded` (ended before the learner wrote anything) |
| `LessonSummary` | `summary` (2–3 sentences), `practiced`, `recurring_mistakes`, `vocabulary`, `next_steps` |
| `LessonDetail` | `lesson`, `messages`, `mistakes`, `vocabulary`, `time_left_seconds` (counted by the server; `null` for ended or untimed lessons) |
| `ChatMessage` | `role` (`user` / `assistant`), `content`: the visible conversation, without internal messages |
| `SendMessageRequest` | `content`: the message (max 4000 chars), or `null` to start the lesson |

`LessonSummary` is also the output schema for Claude, so every summary is guaranteed to have these fields.

#### Corrections and vocabulary: [`models.py`](backend/app/domain/lessons/models.py)

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
  | `/messages` (before the tutor) | `unitary/unbiased-toxic-roberta` | Moderation; self-hosted on the CPU, about 30 ms per message. |

- **Where data is stored:**
  - Profiles, lessons and progress are long-term memory, in `backend/data/memory.db` (LangGraph Store).
  - Conversation content is short-term memory, in `backend/data/checkpoints.db` (LangGraph checkpointer).
  - Accounts, sessions (only token hashes) and daily usage counters are in a separate `backend/data/users.db`.
- **Admin commands** (reset a password, link a profile from before accounts existed): see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#accounts).
- **Shared dependencies:** endpoints do not create the database, the agent or the speech models themselves. They receive them through FastAPI's `Depends` (see [`deps.py`](backend/app/api/deps.py)), which lets tests swap in fake models without calling paid APIs.
- **Frontend types:** the frontend does not define these models by hand. `npm run gen:api` generates TypeScript types from the backend's OpenAPI schema, so both sides always match.

### Moderation

Every learner message, typed or spoken, is checked before the tutor sees it ([`policy.py`](backend/app/domain/moderation/policy.py)). A blocked message is not sent to the tutor and not stored; the learner sees why it was not sent.

- **Classifier:** [`unitary/unbiased-toxic-roberta`](https://huggingface.co/unitary/unbiased-toxic-roberta), the "unbiased" [Detoxify](https://github.com/unitaryai/detoxify) model, downloaded from Hugging Face on the first start (≈ 500 MB) and run in the backend on the CPU. About 30 ms per message, free, and the text does not leave the server for the check. It is trained on English, which is what learners write in the app.
- **What is blocked:** threats, attacks on a group of people, sexual messages, and insults aimed at someone ("you idiot", "you are a stupid bot").
- **What goes through:** swearing out of frustration ("this is so damn hard"), insults not aimed at anyone ("this exercise is stupid"), and quoted words ("what does 'damn' mean?"): quoted text is mentioned, not used, so it is left out of the check. The tutor's prompt tells it to answer rudeness calmly and to explain rude words neutrally.
- **Thresholds:** threat ≥ 0.7, identity attack ≥ 0.5, sexual ≥ 0.2, severe toxicity ≥ 0.5, insult ≥ 0.9 when the message addresses someone ("you are…", "…, you idiot"). They were picked on 37 typical learner messages (all classified as intended); borderline cases still happen, e.g. a threat phrased like an idiom.
- **If the check fails** (for example, the model is still downloading), the message goes through and the error is logged, so a broken check never stops a lesson. Blocked messages are logged with their category and scores, not their text.
- **Turning it off:** `MODERATION_ENABLED=false`.

**Alternative: an LLM classifier.** The local model can be replaced with a classifier on an LLM, e.g. a short Claude Haiku call with structured output that returns the category. It understands context better (sarcasm, threats without threatening words, the difference between a question about a word and an insult) and other languages, including Polish, but it adds about 0.5–1 s of delay to every message, on top of the tutor's reply, and a small cost per message (≈ $0.00006 with Haiku 5.5). To switch, implement the `Moderator` protocol in `moderation.py` with an LLM call and pass it to `create_app`.

## Text-to-speech engines

> **The full PyTorch model is the default and the engine used in production.**
> The quantized ONNX build is included **for testing and as an alternative**. It is off unless you set `TTS_ENGINE=onnx`.

| | Full model (default) | Quantized ONNX (testing / alternative) |
|---|---|---|
| Setting | `TTS_ENGINE=torch` | `TTS_ENGINE=onnx` |
| Model | [`hexgrad/Kokoro-82M`](https://huggingface.co/hexgrad/Kokoro-82M) | `model_quantized.onnx` from the community conversion [`onnx-community/Kokoro-82M-v1.0-ONNX`](https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX), pinned to one revision and verified by SHA-256 |
| Runtime | PyTorch (GPU locally, CPU on the server) | ONNX Runtime (CPU) |
| One 4.5 s sentence on the server (4 ARM cores) | 2.57 s | 1.12 s |
| Five sentences requested at once | 12.8 s until the last one | 5.6 s until the last one |
| Model memory | 717 MB | 233 MB |

Both engines use the same phonemes, the same voice and the same synthesis queue.

**Before relying on the quantized build:**

- It was compared on only three sentences and one voice (`af_heart`). Whisper read them the same as the full model's audio, but quantization can still change how the voice sounds, so listen to it first.
- The speed-up was measured on the ARM server. On the x86 development CPU it was not faster, and locally the GPU runs the full model anyway.
- On the server it uses about 0.5 GB less RAM, which moves the VM further below Oracle's idle-reclaim threshold (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).
- Do not use `model_q8f16.onnx` from the same repository: it produces broken audio.

To try it, add `TTS_ENGINE=onnx` to `backend/.env` (locally) or `deploy/.env` (on the server, then run `docker compose up -d`). The first start downloads about 92 MB. To go back, set `TTS_ENGINE=torch` or remove the line.

## Configuration

Backend settings are read from `backend/.env` (see [`backend/.env.example`](backend/.env.example)):

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | Required. |
| `LLM_MODEL` | `anthropic:claude-haiku-5-5` | LangChain model id (`provider:model`). |
| `TUTOR_EFFORT` / `SUMMARY_EFFORT` | `low` / `medium` | Reasoning effort for tutor replies and summaries. |
| `LESSON_COMPACT_TOKENS` / `LESSON_KEEP_TOKENS` | `30000` / `10000` | Above the first value, the oldest turns reach the model as a summary (`0` = never); the second is how much recent conversation stays word for word. The saved transcript stays whole. |
| `STALE_LESSON_HOURS` | `6` | Lessons idle for longer are summarized automatically at startup. |
| `SPEECH_ENABLED` | `true` | Turns the speech endpoints on or off. |
| `STT_PROVIDER` | `local` | Speech to text: `local` (Whisper in the backend) or `groq` (Groq's hosted Whisper; local Whisper is the fallback). |
| `GROQ_API_KEY` / `GROQ_STT_MODEL` | – / `whisper-large-v3-turbo` | Groq API key ([console.groq.com](https://console.groq.com/keys)) and model, used when `STT_PROVIDER=groq`. |
| `WHISPER_MODEL` / `WHISPER_DEVICE` | `large-v3-turbo` / `auto` | Local speech-to-text model and device (`auto`, `cuda`, `cpu`). |
| `TTS_VOICE` | `af_heart` | Kokoro voice; the first letter is the accent (`a` = American, `b` = British). |
| `TTS_ENGINE` | `torch` | Kokoro engine: `torch` (the full model) or `onnx` (its quantized build, about 2.3× faster on the 4-core ARM server, with a third of the memory). |
| `MODERATION_ENABLED` / `MODERATION_MODEL` | `true` / `unitary/unbiased-toxic-roberta` | Checks every learner message before the tutor sees it (see [Moderation](#moderation)). |
| `SESSION_IDLE_DAYS` / `SESSION_MAX_DAYS` | `30` / `90` | A session ends after this many idle days, and after the maximum in any case. |
| `PASSWORD_BREACH_CHECK` | `true` | Reject passwords known from breaches (Have I Been Pwned; only 5 characters of the SHA-1 hash leave the server). |
| `USER_DAILY_TUTOR_TURNS` / `DAILY_TUTOR_TURNS_TOTAL` | `200` / `2000` | Tutor turns per account and for the whole app per UTC day; `0` = unlimited. |
| `USER_DAILY_TRANSCRIPTIONS` | `200` | Speech-to-text requests per account per day. |
| `SIGNUPS_PER_IP_PER_HOUR` | `5` | New accounts per network per hour. |
| `RATE_LIMIT_PER_MINUTE` | `30` | Requests per minute per account, for each group: tutor turns, transcription, synthesis; `0` = unlimited. |
| `CORS_ORIGINS` / `CORS_ORIGIN_REGEX` | `["http://localhost:3000"]` / none | Origins allowed to call the API from a browser. |
