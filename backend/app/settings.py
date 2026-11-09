"""Settings for the API and the worker, read from environment variables (and an optional .env)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["anthropic", "offline"]

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # AI provider. Empty picks Anthropic when a key is present, otherwise the offline mock.
    llm_provider: Literal["anthropic", "offline", "mock", ""] = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    anthropic_max_tokens: int = 16000
    provider_timeout_seconds: float = 120.0

    # Storage: one SQLite file holds runs, steps, events and the job queue.
    data_dir: Path = BACKEND_DIR / "data"

    # HTTP
    cors_origins: str = "http://localhost:3050"

    # Worker
    lease_seconds: float = 30.0
    poll_interval_seconds: float = 0.25
    retry_base_seconds: float = 2.0
    retry_max_seconds: float = 60.0

    # Webhook delivery. The default target is the mock receiver built into the API.
    webhook_url: str = "http://localhost:8050/api/receiver/hooks"
    webhook_secret: str = "local-dev-secret"
    webhook_timeout_seconds: float = 10.0

    # Pacing so a demo run is watchable. Set to 0 in tests.
    step_delay_seconds: float = 1.0

    # SSE
    sse_poll_seconds: float = 0.3
    sse_keepalive_seconds: float = 15.0

    @property
    def provider(self) -> ProviderName:
        if self.llm_provider in ("offline", "mock"):
            return "offline"
        if self.llm_provider == "anthropic":
            return "anthropic"
        return "anthropic" if self.anthropic_api_key else "offline"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "runner.db"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
