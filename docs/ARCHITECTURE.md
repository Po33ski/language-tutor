# Architecture

English tutor: Next.js frontend, FastAPI backend, LangGraph agent on Claude Haiku 5.5, self-hosted speech models (Whisper for STT, Kokoro for TTS). Developed locally (speech on the GPU); deployed to Vercel + an Oracle Cloud ARM VM (speech on the CPU), see [DEPLOYMENT.md](DEPLOYMENT.md).

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

## Accounts and authentication

Open signup with email and password; **one account = one learner profile**. Chosen after comparing the usual options (research: OWASP Password Storage and Session Management cheat sheets, NIST SP 800-63B-4, FastAPI's security docs).

```
signup/login ──► Argon2id check ──► session token (random 256 bit) ──► client keeps it in localStorage
every request: Authorization: Bearer <token> ──► SHA-256(token) looked up in users.db ──► User
```

| Decision | Why |
|---|---|
| **Opaque session tokens in the database, not JWT** | One backend: a DB lookup is cheap, and logout, password change or expiry revoke a session instantly by deleting its row. JWTs stay valid until they expire unless you add blocklists and refresh tokens. |
| **Bearer header, not a cookie** | The frontend (`*.vercel.app`) and the API (`*.sslip.io`) are different sites, so a session cookie would be a third-party cookie, which Safari blocks outright (even `SameSite=None`). The same header also suits a future mobile app. With an own domain (`app.` + `api.`), an `HttpOnly` cookie would become possible. |
| **Only the token's hash is stored** | A copy of `users.db` contains no working tokens. |
| **Argon2id via `pwdlib`** | OWASP's first choice; pwdlib's defaults (m=64 MiB, t=3, p=4) exceed OWASP's minimum (19 MiB, t=2, p=1). Hashes are rehashed on login if the parameters ever change. Hashing runs in a thread. |
| **NIST password rules** | At least 15 characters (single-factor), up to 128, NFKC-normalized, no composition rules, rejected if breached (Have I Been Pwned range API: only 5 hex characters of the SHA-1 hash are sent; skipped if the service is down), too repetitive, or containing the email's local part. |
| **No user enumeration at login** | Same 401 message for an unknown email and a wrong password, and an unknown email still verifies a dummy hash so the timing matches. Signup does say "email taken" (unavoidable without email verification). |
| **Ownership checks** | Every profile and lesson endpoint works on the signed-in account's `profile_id`; another account's lesson answers 404 (not 403), so ids cannot be probed. |

- **Sessions:** expire after `SESSION_IDLE_DAYS` (30) without use and after `SESSION_MAX_DAYS` (90) in any case; using a session slides its expiry (written at most hourly). Logout deletes the session; a password change deletes all other sessions of the account.
- **Abuse limits** (signup is open, and each turn costs LLM tokens):
  - per account and per UTC day: tutor turns (`USER_DAILY_TUTOR_TURNS`, 200) and transcriptions (`USER_DAILY_TRANSCRIPTIONS`, 200); for the whole app: `DAILY_TUTOR_TURNS_TOTAL` (2000). Counted atomically in `users.db` (`daily_usage`);
  - in memory per IP: `SIGNUPS_PER_IP_PER_HOUR` (5, successful signups), 30 failed logins per 15 min; per email: 10 failed logins per 15 min (also guards the current-password check);
  - per IP per minute and endpoint group (`RATE_LIMIT_PER_MINUTE`, 30): tutor turns (`/messages`, `/end`), `/speech/transcribe`, `/speech/synthesize`.
- **No email yet:** no verification and no reset links. A forgotten password is reset with an admin command on the server (`python -m app.auth.cli reset-password EMAIL`), which sets a temporary password and signs out every session.
- **Profiles from before accounts** stay in the store unlinked; `python -m app.auth.cli claim-profile EMAIL` links the most recently used one (with its lessons and progress) to an account.
- **Frontend:** `AuthGate` (in the root layout) shows the sign-in / create-account screen until a stored token is confirmed by `GET /api/auth/me`, then provides the account through `useAccount()`. A new account goes straight to onboarding. Any 401 clears the token, which brings the sign-in screen back. `/account` changes the password and signs out.
- **Browser hardening:** a Content-Security-Policy (`next.config.ts`) whose `connect-src` allows only the site and the API, so even injected script could not send the token elsewhere; no nonces, because nonces need fully dynamic rendering and Partial Prerendering is on. React escapes all rendered text.

## Onboarding questionnaire

- A form, filled once per profile: name, English level, main topic, lesson length (5–30 minutes), goal, optional preferences.
- The same form, prefilled, is the edit-profile page (`/profile`, `PUT /api/profile`). It also lists the preferences the tutor saved during lessons, so the learner can remove them. Changes apply from the next lesson.
- Starting a new lesson only asks for the lesson topic (defaults to the main topic).

## Agent (LangGraph)

### Lesson state (short-term memory)

| Field | Description |
|---|---|
| `messages` | conversation history (`add_messages` reducer) |
| `user_id` | owner of the lesson (used by `save_preference`) |
| `profile` | snapshot of name, level, preferences, loaded at lesson start |
| `topic` | lesson topic |
| `lesson_minutes` | planned length, copied from the lesson (missing for lessons from before lesson lengths) |
| `progress` | progress profile text, loaded at lesson start |
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
- **Middleware:** `tutor_prompt` builds the system prompt from lesson state; `LessonClockNotes` puts each learner message's clock note in front of it for the model (see "Lesson length" below); `end_turn_if_already_replied` skips the model call after tool results when the tutor already wrote its reply together with the tool calls (otherwise Haiku sometimes repeats the reply, or ends with an empty one).
- **Correction quality:** rules in the prompt (one natural version, smallest change, check prepositions/articles/collocations, ask instead of guessing) were checked on 15 typical learner sentences, 7 of them not mentioned in the prompt and 1 already correct.
- **Corrections UX:** the tutor mentions a correction briefly and naturally in its reply; full details (original, corrected, explanation) are shown in a side panel fed by `mistakes`.

### Lesson length (the lesson clock)

The learner picks a lesson length (5–30 minutes, default 15) in the onboarding form and can change it later on the edit-profile page. A new lesson copies it into `Lesson.duration_minutes`; the clock runs from `Lesson.created_at` (the tutor's opening turn follows at once) on wall-clock time, with no pause.

- **The tutor's view.** The system prompt must stay byte-identical for the whole lesson (thinking-block binding), so it holds only the fixed part: "This lesson lasts N minutes" and the rules for each phase. The ticking time travels with the learner's messages instead: `send_message` stores a clock note in each `HumanMessage.additional_kwargs["lesson_clock"]` (e.g. `[Lesson clock: 6 of 15 minutes used, about 9 left.]`), and the `LessonClockNotes` middleware shows it to the model in front of the message. The note is stored with its message, so earlier turns look the same on every call; the chat, `to_chat_messages` and the summarizer never see it. Logic: `app/agent/clock.py`.
- **Phases** (computed by the server when a turn runs):
  - on track: normal lesson;
  - wrap up, the last 20% of the lesson (1–3 minutes): no new topics, finish the exchange, one thing done well and one to practice, at most one short final question;
  - time up: the tutor's reply is its goodbye (thanks, a one-sentence recap, no question). The stream then sends a `time_up` event, and the client ends the lesson, which writes the summary.
- **If the learner is silent** when the time runs out, the tutor does not interrupt. The lesson page shows "Time's up" with an "End lesson now" button; the next answer gets the goodbye.
- **The countdown** in the lesson header starts from `LessonDetail.time_left_seconds`, counted by the server, so a wrong device clock does not matter. The page uses the same wrap-up rule as the backend to show "time to wrap up".
- Lessons created before lesson lengths existed have no clock: the prompt says the lesson has no fixed length.

### End of lesson (summarization)

Done by the same model (Claude Haiku 5.5, effort `medium`) in `app/agent/summarizer.py`, orchestrated by `app/agent/wrapup.py`; ≈ 10 s and ≈ $0.003 per lesson.

**Triggers**
- The user clicks "End lesson" → `POST /api/lessons/{id}/end` (idempotent; returns the updated lesson).
- The lesson's time is over: after the tutor's goodbye (`time_up` event) the client calls the same endpoint.
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
| Accounts | `data/users.db` (plain SQLite, `app/auth/store.py`) | tables `users` (email, Argon2id hash, `profile_id`), `sessions` (SHA-256 of the token, expiry), `daily_usage` |

The store's `user_id` is the account's `profile_id`, so the learning data did not change shape when accounts were added.

Checkpointer and store use separate SQLite files so their writes never contend for the same lock. Moving to Postgres = swapping to `PostgresSaver` / `PostgresStore`.

## Lesson API

| Endpoint | Purpose |
|---|---|
| `POST /api/lessons` | create a lesson (topic defaults to the profile's main topic) |
| `GET /api/lessons?user_id=` | list a user's lessons, newest first |
| `GET /api/lessons/{id}` | visible chat history + mistakes + vocabulary |
| `POST /api/lessons/{id}/messages` | run one tutor turn, streamed as SSE: `token`, `mistake`, `vocabulary`, `error`, `done` |
| `POST /api/lessons/{id}/end` | end the lesson: summary + progress profile update |
| `GET /api/profile/progress` | the learner's progress profile (null before the first summary) |

- `content: null` starts the lesson: learner context is copied from long-term memory into the lesson state together with a hidden `[START_LESSON]` message, and the tutor speaks first.
- One turn at a time per lesson (per-lesson lock; a second request gets 409).
- The system prompt is built from lesson state, so it stays byte-identical for the whole lesson (required by Haiku's thinking-block binding, and good for prompt caching). The model runs with `prefix_mismatch_behavior: "drop_block"` so a lesson survives code changes to the prompt or tools.

## Voice flow

1. The learner clicks **Speak**; the browser records with MediaRecorder (webm/opus) until **Stop**.
2. `POST /api/speech/transcribe` (multipart `audio`) → Whisper `large-v3-turbo`, English, no prompt → `{text}`. Where it runs depends on `STT_PROVIDER`:
   - `local`: `faster-whisper` in the backend process (VAD on);
   - `groq`: Groq's hosted Whisper (`app/speech/groq_stt.py`), ≈ 1 s instead of 4–6 s on the server's CPU. If a Groq request fails, local Whisper (`WHISPER_MODEL`, `small` on the server) transcribes instead. Groq picks the format from the file name, so the upload is named after its magic bytes (`.webm` from Chrome/Android, `.mp4` from Safari/iOS).
3. The text is sent immediately as a chat message (no confirmation step).
4. `POST /api/lessons/{id}/messages` → tutor reply streamed via SSE.
5. With **Voice on**, the reply is read aloud **while it streams**: the frontend splits the streamed text into sentences (`lib/sentences.ts`) and `useSpeaker` sends each finished sentence to `POST /api/speech/synthesize` → Kokoro (`af_heart`) → WAV. Synthesis requests run one at a time, in order, so the server always works on the earliest sentence; playback follows in the same order through one reused `<audio>` element. The first sentence plays about a second after it is written instead of after the whole reply is synthesized. Every tutor message also has a replay button (same sentence pipeline).

- A text input is always available as an alternative to the microphone.
- Whisper keeps learner mistakes verbatim (tested: "I am work as developer since five years", "she have", "I have went"). An `initial_prompt` made it correct grammar, so none is used.
- Both models run in the backend process on the GPU (`app/speech/`); blocking calls run in threads, and the models load in a background task at startup (first run downloads them from Hugging Face, ≈ 2 GB). Speed on an RTX 5070 Ti: ≈ 0.05 s to synthesize a reply, ≈ 1 s to transcribe an answer.
- CUDA: PyTorch (Kokoro) ships CUDA 13 libraries, but CTranslate2 (Whisper) needs CUDA 12 cuBLAS, provided by `nvidia-cublas-cu12` and preloaded in `app/speech/cuda.py`. `av` is pinned below 16 for `faster-whisper` 1.2.
- `SPEECH_ENABLED=false` turns speech off (the endpoints return 503).

## Deployment

```
Vercel (Next.js) ──HTTPS + Bearer key──► Oracle VM: Caddy :443 ──► backend container :8000
                                                                    ├─ volume tutor-data (SQLite)
                                                                    └─ volume tutor-models (HF cache)
```

- The backend image is CPU-only (`uv sync --extra cpu`, ≈ 0.6 s TTS / ≈ 1 s STT per turn on a desktop CPU with Whisper `small`) and is built on the ARM server itself, so no registry is needed.
- GitHub Actions: path-filtered `backend.yml` / `frontend.yml` run the checks on every push and PR, then deploy `main` (SSH + `deploy/deploy.sh`; `vercel build` + `vercel deploy --prebuilt`).
- Full setup: [DEPLOYMENT.md](DEPLOYMENT.md).

## Repo layout

```
backend/   app/{api, agent, speech, storage, config.py, main.py}, tests/, Dockerfile   (uv, ruff, pytest)
frontend/  src/{app/{onboarding, lesson/[id]}, components, hooks, lib/api}  (Next.js 16, Tailwind 4)
deploy/    compose.yaml, Caddyfile, deploy.sh, backup.sh, .env.example     (server side)
.github/   workflows/{backend,frontend}.yml                                 (CI/CD)
docs/      ARCHITECTURE.md, DEPLOYMENT.md
```

- Frontend calls the backend (`NEXT_PUBLIC_API_URL`) directly with CORS enabled (no Next.js proxy, which can buffer SSE).
- TypeScript API types are generated from the FastAPI OpenAPI schema (`openapi-typescript`).

## Environment notes

- Python 3.12+ via `uv` (system Python is 3.9).
- GPU: RTX 5070 Ti (Blackwell) — needs recent PyTorch/CUDA builds; verify on first speech model run.
