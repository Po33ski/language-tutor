# Language Tutor — Project Guidelines

An English-learning app, developed locally and deployed to Vercel (frontend) and an Oracle Cloud VM (backend). An AI tutor (a LangGraph agent on Claude Haiku 5.5) holds a spoken or written conversation lesson on a topic the learner chose, such as job interview preparation. During the lesson it corrects mistakes, teaches vocabulary and raises difficulty gradually. It remembers each learner across lessons through long-term memory.

More detail lives in other docs:
- `docs/ARCHITECTURE.md`: the design (agent, memory layout, voice flow). Update it whenever the design changes.
- `docs/DEPLOYMENT.md`: hosting, Docker, CI/CD, server setup and backups. Update it whenever deployment changes.
- `README.md`: setup instructions and the full API reference (endpoints, SSE events, models, error codes). Update it whenever the API changes.

## Working rules

- **Language:** every project file is in English: code, comments, docstrings, commit messages, docs, UI copy, file names. Chat with the developer happens in **Polish**.
- **Secrets:** API keys go only in `backend/.env`, which is never committed. Never ask the developer to paste a key into chat. Every new setting goes into `.env.example` with its name only.
- **Git:** commit and push only when the developer asks. Before every push, check that no `.env`, `*.db` or `sk-ant-` string is tracked.
- **Verify before reporting done:** run the backend and frontend checks (see Commands). For UI changes, also run the app and test the flow in a browser.
- **Skills:** use `.claude/skills/langgraph` for agent code and `.claude/skills/vercel-react-best-practices` for React/Next code (both in the repo, pinned in `skills-lock.json`). For CI/CD work (`.github/workflows/`, `deploy/`, `backend/Dockerfile`) use the `building-cicd-pipelines` skill.
  - `building-cicd-pipelines` is installed globally on the developer's machine (`~/.claude/skills/`), not in the repo: `npx skills add jeremylongshore/claude-code-plugins-plus-skills --skill building-cicd-pipelines --agent claude-code --copy --global`.
  - It is generic (it suggests staging, registries, Slack and so on). The settled design in `docs/DEPLOYMENT.md` wins: no staging, images built on the VM, no registry, deploy only from `main` after the checks pass.

## Product decisions (settled; do not re-ask)

| Topic | Decision |
|---|---|
| Users | Multiple local profiles, no login. The selected `user_id` is kept in localStorage. All data is keyed by `user_id`, so auth can be added later. |
| Onboarding | A form, filled once per profile: name, CEFR level (A1–C2), main topic, goal, optional preferences. A new lesson asks only for its topic, which defaults to the main topic. |
| Lesson | The tutor speaks first. It drives the topic with role-play, asks one question at a time and keeps replies to 2–4 sentences of plain text, because replies are read aloud. |
| Corrections | Mentioned briefly and naturally in the reply. Full details (original → corrected + explanation) appear in a side panel. Each correction gives one natural version, never "A / B". |
| Voice | Mic button (Speak/Stop). The transcript is **sent immediately**, with no edit step. Tutor replies are read aloud when "Voice on" is set (the default). Every tutor message has a replay button. Typing is always available too. |
| Lesson end | An "End lesson" button triggers a summary and a progress update. Lessons left open are ended automatically at backend startup. |
| Framework | Stay on LangGraph via LangChain's `create_agent`, not a hand-written graph and not plain LangChain. |
| Hosting | Frontend on Vercel Hobby; backend in Docker (CPU only) on an Oracle Cloud Always Free ARM VM behind Caddy (HTTPS). GitHub Actions deploys `main` after tests pass. Details: `docs/DEPLOYMENT.md`. |
| Access | A shared `ACCESS_KEY` (Bearer token) guards every endpoint except health; the frontend asks for it once (`AccessGate`) and keeps it in localStorage. LLM and speech endpoints are rate-limited per IP. Empty key = open API, local dev only. |

## Backend (`backend/`)

### Stack

| Area | Technology |
|---|---|
| Language / tooling | Python 3.12 (`uv`; the system Python is 3.9, so always use `uv run`), ruff (line length 100), pytest |
| Web | FastAPI, uvicorn, Pydantic v2, pydantic-settings (`app/config.py` reads `.env`) |
| Agent | LangGraph 1.2.x + LangChain 1.4.x (`create_agent`, middleware, tools), `langchain-anthropic` |
| Persistence | SQLite: `AsyncSqliteSaver` (checkpointer) + `AsyncSqliteStore` (store), from `langgraph-checkpoint-sqlite`. Planned for prod: `PostgresSaver` / `PostgresStore`. |
| Speech | `faster-whisper` (STT), `kokoro` + spaCy `en_core_web_sm` (TTS), torch (extra `gpu`: CUDA build, local dev; extra `cpu`: CPU-only build, server and CI), `soundfile`, `av` |

### AI models

| Role | Model | Runs | Settings |
|---|---|---|---|
| Tutor (each lesson turn) | Claude Haiku 5.5, `anthropic:claude-haiku-5-5` | Anthropic API | `LLM_MODEL`, `TUTOR_EFFORT=low` (fast replies; an eval of 15 sentences showed `low` corrects well) |
| Lesson summary + progress profile | Claude Haiku 5.5 | Anthropic API | `SUMMARY_EFFORT=medium`; ≈ 10 s and ≈ $0.003 per lesson |
| Speech to text | Whisper `large-v3-turbo` locally, `small` on the server (faster-whisper / CTranslate2) | local GPU, float16; server CPU, int8 | `WHISPER_MODEL`, `WHISPER_DEVICE=auto` (`cpu` in the image) |
| Text to speech | Kokoro-82M (`hexgrad/Kokoro-82M`), 24 kHz WAV | local GPU; server CPU | `TTS_VOICE=af_heart` (first letter = accent: `a` American, `b` British) |

- The LLM is created with `init_chat_model("provider:model")`, so the provider can change through configuration alone. Haiku was chosen for cost; it may be replaced later.
- The speech models download from Hugging Face on first run (≈ 2 GB). They load in a background task at startup. Calls block, so they run through `asyncio.to_thread`.

### Module map (`backend/app/`)

| Path | Responsibility |
|---|---|
| `main.py` | `create_app(settings, model, summarizer, speech_service)`. The lifespan opens persistence, builds the tutor and summarizer, creates per-lesson locks and starts the background tasks (end stale lessons, warm up speech). Tests inject fakes through its parameters. |
| `config.py` | `Settings` + `get_settings()`. Data lives in `data/checkpoints.db` and `data/memory.db`. |
| `api/deps.py` | FastAPI `Depends` aliases: `SettingsDep`, `StoreDep`, `TutorDep`, `SummarizerDep`, `SpeechDep` (503 when speech is disabled), `LessonLocksDep`. Endpoints never build resources themselves. |
| `api/security.py` | `require_access_key` (Bearer `ACCESS_KEY`, applied to every router but health in `main.py`) and the in-memory per-IP `RateLimiter` / `rate_limit` dependency (on `/messages`, `/end`, speech) |
| `api/{health,auth,profiles,lessons,speech}.py` | Routers, all under the `/api` prefix. `lessons.py` holds the SSE turn endpoint and `_initial_state`, which copies long-term memory into a new lesson. |
| `agent/graph.py` | `build_model`, `build_tutor_agent` (`create_agent` + middleware `tutor_prompt` and `end_turn_if_already_replied`) |
| `agent/state.py` | `TutorState(AgentState)`: `user_id`, `profile`, `topic`, `progress`, `previous_summaries`, plus append-only `mistakes` and `vocabulary` lists. `Mistake` and `VocabularyItem` are TypedDicts. |
| `agent/prompts.py` | `TUTOR_SYSTEM_PROMPT`, `build_system_prompt(state)`, and `KICKOFF_MESSAGE = "[START_LESSON]"` |
| `agent/tools.py` | `record_mistake` and `add_vocabulary` return `Command(update=...)` with a `ToolMessage`. `save_preference` writes to the store. |
| `agent/transcript.py` | `thread_config(lesson_id)` and `to_chat_messages`, which hides the kickoff and tool messages and merges consecutive assistant texts |
| `agent/summarizer.py` | `Summarizer` protocol and `LlmSummarizer`, which produces a structured `LessonSummary` and a progress text of at most 120 words |
| `agent/wrapup.py` | `end_lesson` (idempotent; discards a lesson with no learner messages) and `end_stale_lessons` |
| `storage/memory.py` | All long-term memory models and store access: profiles, lessons, progress |
| `storage/persistence.py` | `open_persistence(settings)` yields the checkpointer and the store |
| `speech/` | `stt.py` (`WhisperTranscriber`), `tts.py` (`KokoroSynthesizer`), `service.py` (`SpeechService` protocol, `LocalSpeechService`), `cuda.py` (CUDA 12 preload) |

### Memory

| Type | Storage | Key | Contents |
|---|---|---|---|
| Short-term | checkpointer, `data/checkpoints.db` | `thread_id = lesson_id` | Full lesson state after every graph step: messages, mistakes, vocabulary |
| Long-term: profile | store, `data/memory.db` | `("profiles",)` / `user_id` | Name, level, main topic, goal, preferences |
| Long-term: lesson | store | `("lessons",)` / `lesson_id` | `user_id`, `topic`, `status` (`active` / `summarized` / `discarded`), dates, `summary` |
| Long-term: progress | store | `("users", user_id)` / `"progress"` | A cumulative learner description, rewritten by Haiku after each lesson |

- **Reads:** when a lesson starts (`content: null`), `_initial_state` copies the profile, the progress text and the 3 most recent summaries into the lesson state. The agent never searches the store mid-lesson.
- **Writes:**
  - The onboarding form creates the profile.
  - The `save_preference` tool writes during a lesson.
  - `end_lesson` writes the summary, then the progress update.
- The checkpointer and the store use separate SQLite files so their writes never compete for the same lock. `backend/data/` is gitignored. To reset all data, stop the backend and delete that folder.

### API conventions

- One lesson turn is `POST /api/lessons/{id}/messages`. It streams SSE events: `token`, `mistake`, `vocabulary`, `error`, `done`. `content: null` starts the lesson.
- Only one turn runs per lesson at a time, enforced by an `asyncio.Lock` per lesson. A request while the tutor is still answering, or for an ended lesson, gets 409.
- The frontend calls the backend at `NEXT_PUBLIC_API_URL` directly (`localhost:8000` in dev, the production API in prod), with CORS enabled. There is no Next.js proxy, because a proxy can buffer SSE.
- Every endpoint except `GET /api/health` needs `Authorization: Bearer <ACCESS_KEY>` when a key is set; the frontend adds it in `apiFetch` (`lib/api/client.ts`).
- After changing any Pydantic model or endpoint, regenerate the frontend types with `npm run gen:api` while the backend is running. Also update `README.md`.

### Gotchas (hard-won; do not regress)

- **Thinking-block binding (Haiku 5.5):**
  - The system prompt must stay byte-identical for a whole lesson. That is why it is built from lesson state, never from live store reads.
  - `build_model` sets `thinking.block_binding.prefix_mismatch_behavior = "drop_block"` and passes the beta header `thinking-binding-controls-2026-08-01`. Without them, any change to the prompt or tools breaks lessons that are already in progress with a 400 error.
- **Structured output:** use `with_structured_output(..., method="json_schema")`. The default method forces tool use, and the API rejects forced tool use when thinking is on.
- **Duplicate or empty replies:** Haiku sometimes writes its reply alongside the tool calls and then again after the tool results. The `end_turn_if_already_replied` middleware jumps to the end in that case. Keep it, and keep its test.
- **Kickoff:** a hidden `HumanMessage("[START_LESSON]")` whose id starts with `kickoff-`. `to_chat_messages` removes it from everything the UI shows.
- **Whisper:** use `language="en"`, `vad_filter=True` and **no `initial_prompt`**. A prompt made Whisper fix the learner's grammar, and the mistakes must be kept verbatim.
- **CUDA:** torch (Kokoro) ships CUDA 13, but CTranslate2 (Whisper) needs CUDA 12 cuBLAS. That library comes from `nvidia-cublas-cu12` and is preloaded with `RTLD_GLOBAL` in `speech/cuda.py`.
- **torch extras:** install with `uv sync --extra gpu` (local) or `--extra cpu` (server, CI); they conflict by design. A bare `uv sync` drops cuBLAS. In CI, `uv run` needs `UV_NO_SYNC=1`, or it re-syncs to the CUDA build.
- **espeak-ng path limit:** Kokoro's espeak-ng fails when its data path (inside the venv) is longer than ~160 characters. Keep venvs at short paths (the image uses `/app/.venv`).
- **Pinned dependencies:**
  - `av` is pinned `>=14,<16`, because version 16+ breaks faster-whisper 1.2.
  - `en-core-web-sm` is a URL dependency in `pyproject.toml`, because otherwise misaki pip-installs it at runtime.
- **Auto-ending stale lessons:** lessons are ended automatically only after `STALE_LESSON_HOURS` (6) of inactivity. The threshold keeps `uvicorn --reload` restarts from closing lessons that are in progress.

### Tests (`backend/tests/`)

- Tests never call paid APIs or load real speech models. `conftest.py` provides these fakes:
  - `FakeTutorModel`: a `GenericFakeChatModel` subclass with `bind_tools` returning self and `disable_streaming=True`;
  - `FakeSummarizer`;
  - `FakeSpeech`;
  - the `make_client` fixture, which uses a temporary data dir.
- The SSE token filter must accept both `AIMessageChunk` and `AIMessage`, because the fake model does not stream.

## Frontend (`frontend/`)

### Stack

| Area | Technology |
|---|---|
| Framework | **Next.js 16.4.6** (App Router, Turbopack, `cacheComponents` and `partialPrefetching` on). `next` and `eslint-config-next` are pinned to exact versions. |
| UI | React 19.3, TypeScript 5 (`strict`), Tailwind CSS 4. No component library: shared class names live in `src/components/ui.ts`. |
| API types | `openapi-typescript` generates `src/lib/api/schema.d.ts` from the backend's OpenAPI schema. Never hand-write API types. |
| Browser APIs | `MediaRecorder` (webm/opus, mp4 fallback) for the mic; an `Audio` element for TTS playback |
| Runtime | Node 22 |

### Structure (`frontend/src/`)

| Path | Responsibility |
|---|---|
| `app/page.tsx`, `app/onboarding/page.tsx`, `app/lesson/[id]/page.tsx` | Routes: home (profiles, progress, lessons), onboarding form, lesson |
| `components/home/`, `components/onboarding/` | Home screen and onboarding form |
| `components/lesson/` | `lesson-view` (orchestrates a lesson), `message-list` (bubbles + replay), `message-composer` (textarea, Speak/Stop, Send), `feedback-panel` (corrections + vocabulary), `lesson-summary-card` |
| `components/backend-status.tsx` | The "Backend online" indicator |
| `hooks/use-recorder.ts`, `hooks/use-speaker.ts` | Mic recording; TTS playback with a generation counter, so stale audio never plays |
| `lib/api/client.ts` | The `api` object (REST calls), `streamTutorTurn` (SSE parser), `ApiError` |
| `lib/stored-value.ts` | `createStoredValue(key)`: localStorage plus `useSyncExternalStore`. Used by `current-user.ts`, `voice-settings.ts` and `access-key.ts`. |
| `components/access-gate.tsx`, `lib/access-key.ts` | Wraps the app in `layout.tsx`: calls `GET /api/auth/check`, asks for the access key on 401 and stores it. Any later 401 clears the key, so the gate asks again. |

### Conventions and gotchas

- **Next 16 differs from older versions.** Read `frontend/AGENTS.md` and the guides in `frontend/node_modules/next/dist/docs/` before writing Next code. `next dev` rewrites `frontend/AGENTS.md`, so commit that file as it is.
- **Route params:** with `cacheComponents`, the page passes `props.params` (a Promise) into a client component rendered inside `<Suspense>`, which reads it with `use(params)`. Reading params outside Suspense fails with a "runtime data during prerendering" error.
- **Data access:** everything is client-side (`"use client"`) and talks to the backend at `NEXT_PUBLIC_API_URL` (`frontend/.env.local`). There are no Server Actions or route handlers.
- **Overlay placement:** the Next dev overlay and security toast sit at the bottom left, so keep important controls on the right side of the composer.
- **npm audit:** the remaining audit findings are dev-only, in the lint dependencies. Do not run `npm audit fix --force`: it downgrades `eslint-config-next`.
- **No frontend test suite yet.** To verify UI flows, use an ad-hoc `playwright-core` script with headless Chromium. Chromium flags `--use-fake-device-for-media-stream` and `--use-file-for-fake-audio-capture=<wav>` stand in for the microphone. These scripts are not committed.

## Commands

| Task | Command |
|---|---|
| Backend dev server | `cd backend && uv run uvicorn app.main:app --reload --port 8000` |
| Backend checks | `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest` |
| Frontend dev server | `cd frontend && npm run dev` (http://localhost:3000) |
| Backend setup | `cd backend && uv sync --extra gpu` (`--extra cpu` without an NVIDIA GPU) |
| Frontend checks | `cd frontend && npm run lint && npx tsc --noEmit` (on a clean checkout run `npx next typegen` first) |
| Regenerate API types (backend running) | `cd frontend && npm run gen:api` |
| Interactive API docs | http://localhost:8000/docs |

## Production deployment

Full setup guide: `docs/DEPLOYMENT.md`. Live state:

| What | Where |
|---|---|
| Frontend | https://language-tutor-sigma.vercel.app (Vercel Hobby, project `language-tutor`, scope `tutor-16ad`). Per-deployment URLs change every deploy; always use this alias. |
| Backend | https://92-5-78-54.sslip.io (Caddy → backend container). `GET /api/health` is public; everything else needs the access key. |
| Server | Oracle Cloud Always Free, `VM.Standard.A1.Flex` (ARM, 4 OCPU, 12 GB, 100 GB disk), Ubuntu 24.04 aarch64, IP `92.5.78.54`, user `ubuntu`. Network: VCN `tutor-vcn`, public subnet; ports 80/443 open in its *Default Security List* and in iptables. |
| Code on the server | `~/language-tutor`, a clone over a read-only deploy key (`~/.ssh/github_deploy`). CI checks out the deployed commit detached. |
| Server secrets | `~/language-tutor/deploy/.env` (mode 600): `API_DOMAIN`, `ANTHROPIC_API_KEY`, `ACCESS_KEY`, `CORS_ORIGINS=["https://language-tutor-sigma.vercel.app"]`, `WHISPER_MODEL=small`. Never print it or read secrets from it into the chat. |
| Data | Docker volumes `tutor-data` (SQLite) and `tutor-models` (HF cache); `caddy-data` holds the TLS certificate (Let's Encrypt, auto-renewed). |
| GitHub Actions | Secrets `SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`, `SSH_HOST`, `SSH_USER`, `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`; variable `API_URL`. Vercel env: `NEXT_PUBLIC_API_URL` (production). |

- **Flow:** push to `main` → path-filtered `backend.yml` (`backend/**`, `deploy/**`) / `frontend.yml` (`frontend/**`) run the checks, then deploy. PRs and other branches only run the checks. Manual redeploy: Actions → Run workflow on `main`.
- **Server access from this machine:** `ssh -i ~/.ssh/language-tutor-ci -o IdentitiesOnly=yes ubuntu@92.5.78.54` works non-interactively (the CI key). The developer's own key (`~/.ssh/id_ed25519`) has a passphrase. Ask before changing anything on the server.
- **Manual on the server:** changes to `deploy/.env` (then `cd ~/language-tutor/deploy && docker compose up -d`), OS updates, a new setting that needs a value. Logs: `docker compose logs -f backend`.
- **Not set up yet:** the nightly backup cron (`deploy/backup.sh`) and an Anthropic spend limit.
- **Gotchas:**
  - `NEXT_PUBLIC_API_URL` is inlined at build time: change it in Vercel, then redeploy the frontend.
  - `CORS_ORIGINS` must list the Vercel production alias, not a per-deployment URL.
  - Oracle's instance wizard cannot give a public IP when it creates the VCN itself: create the VCN first ("Create VCN with Internet Connectivity"), then pick its public subnet.
  - Ingress rules go into the public subnet's *Default Security List*; the wizard also creates a private-subnet list that looks similar (SSH only from `10.0.0.0/16`).
  - iptables: the `REJECT` rule is at a different position on different image builds; insert the HTTP/HTTPS rules above it (see `docs/DEPLOYMENT.md`).
  - Free Oracle accounts reclaim instances idle (CPU, network and memory all < 20%) for 7 days; 12 GB RAM keeps memory use above that with the speech models loaded.
  - `astral-sh/setup-uv` has no floating major tag: pin a full version (`v10.3.3`).

## Environment

- Windows + WSL2 (Linux). GPU: NVIDIA RTX 5070 Ti (Blackwell, sm_120), which needs recent torch/CUDA builds.
- Speed on this machine: Whisper ≈ 1 s per answer, Kokoro ≈ 0.05 s per reply once warm. On a desktop CPU only: Kokoro ≈ 0.6 s per 5 s reply, Whisper `small` ≈ 1.1 s, `large-v3-turbo` ≈ 2.5 s; expect 2–4× slower on the server's 4 Ampere cores.

## Not done yet (ideas, only on request)

- PostgreSQL for prod, real user accounts (instead of one shared access key)
- A mobile app (React Native/Expo or a PWA) on top of the same API
- Sentence-by-sentence TTS while the reply streams
- Prompt caching
- Retry after a failed tutor turn
- Profile edit/delete
- Frontend tests (CI runs lint, tsc and build only)
