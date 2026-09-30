from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analytics import build_dashboard
from app.config import Settings
from app.storage import LocalStorage

STATIC_DIR = Path(__file__).parent / "static"
app = FastAPI(title="ChatGPT Usage Dashboard", docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard() -> dict:
    settings = Settings.from_env()
    storage = LocalStorage(settings.data_dir)
    return build_dashboard(storage.load_usage(), storage.load_state())

