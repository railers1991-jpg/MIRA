from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MIRA_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 7842

    data_dir: Path = Path.home() / ".mira"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-7"

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Self-learning scheduler. Set distill_interval_s = 0 to disable.
    distill_interval_s: int = 86_400  # daily
    distill_limit: int = 200
    decay_half_life_days: float = 30.0
    decay_prune_below: float = 0.05

    @property
    def mcp_config_path(self) -> Path:
        return self.data_dir / "mcp.json"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "chroma").mkdir(exist_ok=True)
        (self.data_dir / "logs").mkdir(exist_ok=True)


settings = Settings()
