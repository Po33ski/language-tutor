from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    # Long lessons: when a model call would exceed this many input tokens, the oldest
    # turns reach the model as a summary (the saved transcript stays whole). 0 = never.
    # A normal 30-minute lesson stays well below it.
    lesson_compact_tokens: int = 30_000
    # How many tokens of the most recent conversation are kept word for word.
    lesson_keep_tokens: int = 10_000
    # Active lessons idle for longer than this are summarized automatically at startup.
    stale_lesson_hours: float = 6
    cors_origins: list[str] = ["http://localhost:3000"]
    # Optional regex for more allowed origins, e.g. Vercel preview deployments.
    cors_origin_regex: str | None = None

    # Requests per minute per account to each group of endpoints that call the LLM or the
    # speech models. 0 = unlimited.
    rate_limit_per_minute: int = 30

    # Accounts. Sessions expire after this many idle days, and after the absolute maximum
    # even when used every day (then the user signs in again).
    session_idle_days: int = 30
    session_max_days: int = 90
    # Reject passwords found in known data breaches (Have I Been Pwned, k-anonymity API:
    # only the first 5 characters of the password's SHA-1 hash leave the server).
    password_breach_check: bool = True
    # New accounts per client IP per hour (signup is open to anyone).
    signups_per_ip_per_hour: int = 5
    # Daily cost limits, because anyone can sign up. 0 = unlimited.
    user_daily_tutor_turns: int = 200
    daily_tutor_turns_total: int = 2000
    user_daily_transcriptions: int = 200

    # Speech (local models, downloaded from Hugging Face on first use).
    speech_enabled: bool = True
    # Speech to text: "local" (Whisper in this process) or "groq" (Whisper hosted by Groq;
    # local Whisper stays the fallback when a Groq request fails).
    stt_provider: Literal["local", "groq"] = "local"
    groq_api_key: str = ""
    groq_stt_model: str = "whisper-large-v3-turbo"
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "auto"  # "auto" | "cuda" | "cpu"
    # Kokoro voice; the first letter is the accent: "a" = American, "b" = British.
    tts_voice: str = "af_heart"

    # Moderation: a local toxicity classifier (Hugging Face) checks every learner message
    # before the tutor sees it; threats, hate, sexual messages and targeted insults are
    # blocked (app/domain/moderation/policy.py).
    moderation_enabled: bool = True
    moderation_model: str = "unitary/unbiased-toxic-roberta"

    @property
    def checkpoints_db_path(self) -> Path:
        return self.data_dir / "checkpoints.db"

    @property
    def memory_db_path(self) -> Path:
        return self.data_dir / "memory.db"

    @property
    def users_db_path(self) -> Path:
        """Accounts, sessions and usage counters, kept apart from the learning data."""
        return self.data_dir / "users.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
