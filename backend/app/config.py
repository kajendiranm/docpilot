"""All settings come from the repo-root .env file (or real environment variables)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # Gemini. SecretStr hides the key in logs, reprs and tracebacks.
    gemini_api_key: SecretStr = SecretStr("")
    gemini_chat_model: str = "gemini-3.5-flash-lite"
    gemini_thinking_level: str = "MINIMAL"
    gemini_embed_model: str = "gemini-embedding-001"
    embed_dimensions: int = 768

    # Postgres
    database_url: str = "postgresql://docpilot:docpilot@localhost:5433/docpilot"
    readonly_database_url: str = "postgresql://docpilot_reader:reader@localhost:5433/docpilot"

    # Retrieval
    search_score_threshold: float = 0.65  # tuned: relevant >= 0.71, off-topic <= 0.6

    # GitHub
    github_token: SecretStr = SecretStr("")
    github_repo: str = "kajendiranm/docpilot-demo-docs"
    dry_run: bool = True

    # Agent
    max_tool_iterations: int = 5


@lru_cache
def get_settings() -> Settings:
    """One shared Settings instance; tests can call get_settings.cache_clear()."""
    return Settings()
