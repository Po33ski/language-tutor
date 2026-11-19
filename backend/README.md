# Language Tutor — backend

FastAPI + LangGraph backend.

## Setup

```bash
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
uv sync --extra gpu    # PyTorch with CUDA + cuBLAS for an NVIDIA GPU
# or: uv sync --extra cpu   (CPU-only PyTorch, much smaller; used by the server and CI)
```

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

## Checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```
