from pathlib import Path

from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analytics import build_workspace_dashboard
from app.config import Settings
from app.csv_importer import CSVImportError, parse_and_join
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
    return build_workspace_dashboard(storage.load_workspace_usage(), storage.load_import_state())


MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@app.post("/api/import")
async def import_csv(
    active_users_file: UploadFile = File(...),
    tokens_file: UploadFile = File(...),
) -> dict:
    active_bytes = await active_users_file.read(MAX_UPLOAD_BYTES + 1)
    token_bytes = await tokens_file.read(MAX_UPLOAD_BYTES + 1)
    if len(active_bytes) > MAX_UPLOAD_BYTES or len(token_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSVは1ファイル5 MiB以下にしてください")
    try:
        rows = parse_and_join(active_bytes, token_bytes)
    except CSVImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage = LocalStorage(Settings.from_env().data_dir)
    run_id = storage.create_run()
    storage.save_raw_csv(run_id, "active-users.csv", active_bytes)
    storage.save_raw_csv(run_id, "tokens.csv", token_bytes)
    total_rows = storage.merge_workspace_usage(rows)
    now = datetime.now(timezone.utc).isoformat()
    state = {
        "status": "success",
        "completed_at": now,
        "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"],
        "imported_days": len(rows),
        "stored_days": total_rows,
        "run_id": run_id,
    }
    storage.save_import_state(state)
    return build_workspace_dashboard(storage.load_workspace_usage(), state)
