# Language Tutor — backend

FastAPI + LangGraph backend.

## Setup

```bash
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
uv sync
```

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

## Checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```
