from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    admin_key: str
    analytics_url: str
    data_dir: Path
    timeout_seconds: float
    max_retries: int

    @classmethod
    def from_env(cls, *, require_key: bool = False) -> "Settings":
        load_dotenv()
        key = os.getenv("OPENAI_ADMIN_KEY", "").strip()
        if require_key and not key:
            raise ValueError("OPENAI_ADMIN_KEY is not set. Copy .env.example to .env and set the Admin key.")
        return cls(
            admin_key=key,
            analytics_url=os.getenv(
                "OPENAI_ANALYTICS_URL", "https://api.chatgpt.com/v1/analytics/usage"
            ).strip(),
            data_dir=Path(os.getenv("DATA_DIR", "./data")),
            timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
        )

