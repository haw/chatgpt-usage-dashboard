"""Keep the suite independent of the developer's .env (load_dotenv never overrides real env vars)."""
import os

os.environ["AUTH_MODE"] = "none"
os.environ["STORAGE_BACKEND"] = "local"
for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET", "AUTH_ALLOWED_DOMAINS", "BASE_URL", "S3_BUCKET", "ORIGIN_VERIFY_SECRET", "APP_REVISION", "APP_GIT_DIR"):
    os.environ[name] = ""
