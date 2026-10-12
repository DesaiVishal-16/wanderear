from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_SECONDS = 8.0


def _data_home() -> Path:
    env = os.environ.get("WANDEREAR_HOME")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).expanduser() / "wanderear"
    return Path.home() / ".local" / "share" / "wanderear"


@dataclass
class Settings:
    home: Path = field(default_factory=_data_home)
    sample_rate: int = DEFAULT_SAMPLE_RATE
    seconds: float = DEFAULT_SECONDS
    classifier: str = "auto"
    narrator: str = "auto"
    ollama_url: str = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.environ.get("WANDEREAR_MODEL", "gemma3:4b")
    min_confidence: float = 0.25
    top_k: int = 5
    mongo_uri: str | None = os.environ.get("WANDEREAR_MONGO_URI")

    @property
    def media_dir(self) -> Path:
        return self.home / "media"

    @property
    def index_path(self) -> Path:
        return self.home / "index.jsonl"

    def ensure_dirs(self) -> None:
        self.media_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()