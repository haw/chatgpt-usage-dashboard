import hashlib
from pathlib import Path

from datetime import date, datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analytics import build_individual_dashboard, build_workspace_dashboard
from app.config import Settings
from app.csv_importer import CSVImportError, parse_and_join, parse_token_csv
from app.json_importer import JSONImportError, parse_and_join_json, parse_token_json
from app.storage import create_storage

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
def dashboard(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> dict:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="開始日は終了日以前にしてください")
    settings = Settings.from_env()
    storage = create_storage(settings)
    return build_workspace_dashboard(
        storage.load_workspace_usage(),
        storage.load_import_state(),
        start_date.isoformat() if start_date else None,
        end_date.isoformat() if end_date else None,
    )


@app.get("/api/imports")
def import_history() -> dict:
    storage = create_storage(Settings.from_env())
    return {"imports": storage.list_import_history()}


@app.get("/api/individual")
def individual_dashboard(user_id: str | None = Query(default=None)) -> dict:
    storage = create_storage(Settings.from_env())
    return build_individual_dashboard(
        storage.load_individual_usage(), storage.load_individual_import_state(), user_id
    )


@app.get("/api/individual/imports")
def individual_import_history() -> dict:
    storage = create_storage(Settings.from_env())
    return {"imports": storage.list_individual_import_history()}


MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@app.post("/api/import")
async def import_json(
    active_users_file: UploadFile = File(...),
    tokens_file: UploadFile = File(...),
) -> dict:
    active_suffix = Path(active_users_file.filename or "").suffix.lower()
    token_suffix = Path(tokens_file.filename or "").suffix.lower()
    if active_suffix not in {".json", ".csv"}:
        raise HTTPException(status_code=400, detail="アクティブユーザーJSON（.json）を選択してください")
    if token_suffix not in {".json", ".csv"}:
        raise HTTPException(status_code=400, detail="トークンJSON（.json）を選択してください")
    if active_suffix != token_suffix:
        raise HTTPException(status_code=400, detail="2つのファイルは同じ形式に揃えてください")
    active_bytes = await active_users_file.read(MAX_UPLOAD_BYTES + 1)
    token_bytes = await tokens_file.read(MAX_UPLOAD_BYTES + 1)
    if len(active_bytes) > MAX_UPLOAD_BYTES or len(token_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="1ファイル5 MiB以下にしてください")
    if active_suffix == ".csv":
        try:
            rows = parse_and_join(active_bytes, token_bytes)
        except CSVImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        try:
            rows = parse_and_join_json(active_bytes, token_bytes)
        except JSONImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage = create_storage(Settings.from_env())
    run_id = storage.create_run()
    if active_suffix == ".csv":
        storage.save_raw_csv(run_id, "active-users.csv", active_bytes)
        storage.save_raw_csv(run_id, "tokens.csv", token_bytes)
    else:
        storage.save_raw_json(run_id, "active-users.json", active_bytes)
        storage.save_raw_json(run_id, "tokens.json", token_bytes)
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


@app.post("/api/individual/import")
async def import_individual_json(
    user_label: str = Form(...),
    tokens_file: UploadFile = File(...),
) -> dict:
    label = " ".join(user_label.split())
    if not label or len(label) > 200:
        raise HTTPException(status_code=400, detail="ユーザー名またはメールアドレスを200文字以内で指定してください")
    suffix = Path(tokens_file.filename or "").suffix.lower()
    if suffix not in {".json", ".csv"}:
        raise HTTPException(status_code=400, detail="トークンJSON（.json）を選択してください")
    token_bytes = await tokens_file.read(MAX_UPLOAD_BYTES + 1)
    if len(token_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="ファイルは5 MiB以下にしてください")
    if suffix == ".csv":
        try:
            parsed = parse_token_csv(token_bytes)
        except CSVImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        try:
            parsed = parse_token_json(token_bytes)
        except JSONImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_id = hashlib.sha256(label.casefold().encode()).hexdigest()[:20]
    rows = [{**row, "user_id": user_id, "user_label": label} for row in parsed]
    storage = create_storage(Settings.from_env())
    run_id = storage.create_run()
    if suffix == ".csv":
        storage.save_raw_csv(run_id, "individual-tokens.csv", token_bytes)
    else:
        storage.save_raw_json(run_id, "individual-tokens.json", token_bytes)
    total_rows = storage.merge_individual_usage(rows)
    state = {
        "status": "success", "completed_at": datetime.now(timezone.utc).isoformat(),
        "start_date": rows[0]["date"], "end_date": rows[-1]["date"],
        "imported_days": len(rows), "stored_rows": total_rows,
        "run_id": run_id, "user_id": user_id, "user_label": label,
    }
    storage.save_individual_import_metadata(run_id, state)
    storage.save_individual_import_state(state)
    return build_individual_dashboard(storage.load_individual_usage(), state, user_id)
