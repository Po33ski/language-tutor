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
    data_dir: Path = Path("data")
    # How many recent lesson summaries the tutor sees at lesson start.
    recent_summaries_count: int = 3
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def checkpoints_db_path(self) -> Path:
        return self.data_dir / "checkpoints.db"

    @property
    def memory_db_path(self) -> Path:
        return self.data_dir / "memory.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
