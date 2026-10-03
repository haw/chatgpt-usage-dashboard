from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    storage_backend: str
    s3_bucket: str
    s3_prefix: str
    aws_region: str | None
    detectors_config: Path
    plugins_dir: Path
    auth_mode: str = "none"
    google_client_id: str = ""
    google_client_secret: str = ""
    session_secret: str = ""
    auth_allowed_domains: tuple[str, ...] = ()
    base_url: str = ""
    session_secure: bool = False
    frontend_dist: Path | None = None
    origin_verify_secret: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        storage_backend = os.getenv("STORAGE_BACKEND", "local").strip().lower()
        if storage_backend not in {"local", "s3"}:
            raise ValueError("STORAGE_BACKEND must be 'local' or 's3'")
        s3_bucket = os.getenv("S3_BUCKET", "").strip()
        if storage_backend == "s3" and not s3_bucket:
            raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        auth_mode = os.getenv("AUTH_MODE", "none").strip().lower()
        if auth_mode not in {"none", "google"}:
            raise ValueError("AUTH_MODE must be 'none' or 'google'")
        domains = tuple(d.strip().lower() for d in os.getenv("AUTH_ALLOWED_DOMAINS", "").split(",") if d.strip())
        if auth_mode == "google":
            missing = [name for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET") if not os.getenv(name, "").strip()]
            if missing:
                raise ValueError(f"AUTH_MODE=google requires {', '.join(missing)}")
            if not domains:
                raise ValueError("AUTH_MODE=google requires AUTH_ALLOWED_DOMAINS (e.g. haw.co.jp)")
        frontend_dist = os.getenv("FRONTEND_DIST", "").strip()
        base_url = os.getenv("BASE_URL", "").strip()
        session_secure = os.getenv("SESSION_SECURE", "").strip().lower() in {"1", "true", "yes"} or base_url.startswith("https://")
        return cls(
            data_dir=Path(os.getenv("DATA_DIR", "./data")),
            storage_backend=storage_backend,
            s3_bucket=s3_bucket,
            s3_prefix=os.getenv("S3_PREFIX", "chatgpt-dashboard").strip().strip("/"),
            aws_region=os.getenv("AWS_REGION", "").strip() or None,
            detectors_config=Path(os.getenv("DETECTORS_CONFIG", "./config/detectors.toml")),
            plugins_dir=Path(os.getenv("PLUGINS_DIR", "./plugins")),
            auth_mode=auth_mode,
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
            session_secret=os.getenv("SESSION_SECRET", "").strip(),
            auth_allowed_domains=domains,
            base_url=base_url,
            session_secure=session_secure,
            frontend_dist=Path(frontend_dist) if frontend_dist else None,
            origin_verify_secret=os.getenv("ORIGIN_VERIFY_SECRET", "").strip(),
        )
