# syntax=docker/dockerfile:1
# Backend image for a CPU-only server (built on the server itself, e.g. Oracle Cloud ARM).
FROM python:3.12-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    # Persistent volumes: SQLite databases and the Hugging Face model cache.
    DATA_DIR=/data \
    HF_HOME=/models \
    WHISPER_DEVICE=cpu

WORKDIR /app

# Dependencies first, so a code change does not reinstall them. Keep the venv path short:
# espeak-ng (used by Kokoro) fails when its data path is longer than ~160 characters.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --extra cpu --no-install-project

COPY app ./app

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data /models \
    && chown app:app /data /models
USER app

EXPOSE 8000

# One process only: speech models, per-lesson locks and the rate limiter live in memory.
# --proxy-headers: take the client IP from the reverse proxy's X-Forwarded-For.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
