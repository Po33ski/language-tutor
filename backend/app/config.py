from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables and `backend/.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    llm_model: str = "anthropic:claude-haiku-5-5"
    # Reasoning effort for the tutor's replies; "low" keeps chat fast and cheap.
    tutor_effort: str = "low"
    # Summaries run once per lesson, so they can afford a bit more reasoning.
    summary_effort: str = "medium"
    data_dir: Path = Path("data")
    # How many recent lesson summaries the tutor sees at lesson start.
    recent_summaries_count: int = 3
    # Active lessons idle for longer than this are summarized automatically at startup.
    stale_lesson_hours: float = 6
    cors_origins: list[str] = ["http://localhost:3000"]
    # Optional regex for more allowed origins, e.g. Vercel preview deployments.
    cors_origin_regex: str | None = None

    # Shared secret that clients send as "Authorization: Bearer <key>". Empty = no auth,
    # for local development only: always set it when the backend is reachable online.
    access_key: str = ""
    # Requests per minute per client IP to the endpoints that call the LLM or the speech
    # models. 0 = unlimited.
    rate_limit_per_minute: int = 30

    # Speech (local models, downloaded from Hugging Face on first use).
    speech_enabled: bool = True
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "auto"  # "auto" | "cuda" | "cpu"
    # Kokoro voice; the first letter is the accent: "a" = American, "b" = British.
    tts_voice: str = "af_heart"

    @property
    def checkpoints_db_path(self) -> Path:
        return self.data_dir / "checkpoints.db"

    @property
    def memory_db_path(self) -> Path:
        return self.data_dir / "memory.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
