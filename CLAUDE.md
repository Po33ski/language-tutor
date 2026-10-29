# Language Tutor — Project Guidelines

An English-learning app. An AI agent (LangGraph) runs a conversational lesson with the user on a topic chosen in an onboarding questionnaire (e.g. "preparing for a job interview") and adapts its teaching to the user based on memory from previous lessons.

## Language

- **Everything in the project is in English:** code, comments, docstrings, commit messages, docs, UI copy, file names.
- (Chat with the developer happens in Polish — that does not apply to project files.)

## Stack

- **Backend:** Python 3.12+, FastAPI, LangGraph 1.x (+ LangChain for model integrations)
- **Frontend:** Next.js (App Router) + React + TypeScript
- **LLM:** external provider, plugged in through a LangChain integration (`init_chat_model("provider:model")`), so the provider can be swapped via configuration. Start with Claude Haiku 5.5 (`anthropic:claude-haiku-5-5`) via an Anthropic API key; may switch later.
- **Deployment:** local only for now (no cloud hosting).

## Core features

1. **Onboarding questionnaire:** name, English level, lesson topic, goal, optional preferences (e.g. "correct me immediately", "more industry vocabulary").
2. **Lesson = conversation with the agent:** the agent drives the conversation on the chosen topic, corrects mistakes, introduces vocabulary, asks questions and gradually raises difficulty.
3. **Lesson wrap-up:** the agent writes a summary (what was practiced, recurring mistakes, new vocabulary, recommendations for the next lesson) and saves it to long-term memory.

## Memory

| Type | What it stores | LangGraph mechanism |
|---|---|---|
| **Short-term** | the current conversation (lesson messages) | checkpointer, 1 `thread_id` = 1 lesson |
| **Long-term** | user name, main topic, preferences, summaries of all previous lessons | `Store` (BaseStore), one namespace per user |

- At lesson start the agent loads the profile and recent summaries from long-term memory into its context.
- Preferences detected during the conversation (e.g. "I prefer shorter answers") are saved to the profile.
- Dev: SQLite (`SqliteSaver`, simple store); prod: PostgreSQL (`PostgresSaver`, `PostgresStore`).

## Repo conventions

- Backend in `backend/`, frontend in `frontend/`.
- LangGraph: use the `.claude/skills/langgraph` skill; use current 1.x APIs (`create_agent`, `InMemorySaver`, `interrupt`); always pass a `thread_id`.
- React/Next: use the `.claude/skills/vercel-react-best-practices` skill.
- Agent responses are streamed to the frontend (SSE).
- API keys only in `.env` (never committed); provide `.env.example` with variable names.
- Typing: Pydantic on the backend, strict TypeScript on the frontend.
- Architecture (agent graph, memory layout, voice flow, repo layout): see `docs/ARCHITECTURE.md` — keep it up to date when the design changes.
- Speech: Whisper (`faster-whisper`, STT) and Kokoro-82M (TTS), both run locally.
- Next.js is version 16 — read `frontend/AGENTS.md` and the bundled docs in `frontend/node_modules/next/dist/docs/` before writing Next.js code.

## Commands

| Task | Command |
|---|---|
| Backend dev server | `cd backend && uv run uvicorn app.main:app --reload --port 8000` |
| Backend checks | `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest` |
| Frontend dev server | `cd frontend && npm run dev` |
| Frontend checks | `cd frontend && npm run lint && npx tsc --noEmit` |
