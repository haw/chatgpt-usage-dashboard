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
    storage_backend: str
    s3_bucket: str
    s3_prefix: str
    aws_region: str | None

    @classmethod
    def from_env(cls, *, require_key: bool = False) -> "Settings":
        load_dotenv()
        key = os.getenv("OPENAI_ADMIN_KEY", "").strip()
        if require_key and not key:
            raise ValueError("OPENAI_ADMIN_KEY is not set. Copy .env.example to .env and set the Admin key.")
        storage_backend = os.getenv("STORAGE_BACKEND", "local").strip().lower()
        if storage_backend not in {"local", "s3"}:
            raise ValueError("STORAGE_BACKEND must be 'local' or 's3'")
        s3_bucket = os.getenv("S3_BUCKET", "").strip()
        if storage_backend == "s3" and not s3_bucket:
            raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        return cls(
            admin_key=key,
            analytics_url=os.getenv(
                "OPENAI_ANALYTICS_URL", "https://api.chatgpt.com/v1/analytics/usage"
            ).strip(),
            data_dir=Path(os.getenv("DATA_DIR", "./data")),
            timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            storage_backend=storage_backend,
            s3_bucket=s3_bucket,
            s3_prefix=os.getenv("S3_PREFIX", "chatgpt-dashboard").strip().strip("/"),
            aws_region=os.getenv("AWS_REGION", "").strip() or None,
        )
