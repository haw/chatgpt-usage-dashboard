import hashlib
from pathlib import Path

from datetime import date, datetime, timezone

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analytics import build_individual_dashboard, build_workspace_dashboard, default_detectors
from app.config import Settings
from app.detectors.calendar import parse_override_list
from app.csv_importer import CSVImportError, parse_and_join, parse_token_csv
from app.json_importer import JSONImportError, parse_token_json, parse_workspace_json
from app.storage import create_storage
from app.triage import DISPOSITION_KINDS, build_triage, checked_dates

STATIC_DIR = Path(__file__).parent / "static"
app = FastAPI(title="ChatGPT Usage Dashboard", docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


SENSITIVITY_RANGE = (0.25, 4.0)


def _sensitivity(value: float | None) -> float:
    if value is None:
        return 1.0
    if not (SENSITIVITY_RANGE[0] <= value <= SENSITIVITY_RANGE[1]):
        raise HTTPException(status_code=400, detail=f"感度は {SENSITIVITY_RANGE[0]}〜{SENSITIVITY_RANGE[1]} で指定してください")
    return value


def _day_overrides(holidays: str | None, workdays: str | None) -> dict[str, str]:
    """Viewer-specific holiday/workday overrides, sent from the browser's localStorage."""
    try:
        return parse_override_list(holidays, workdays)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/dashboard")
def dashboard(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    holidays: str | None = Query(default=None),
    workdays: str | None = Query(default=None),
    sensitivity: float | None = Query(default=None),
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
        day_overrides=_day_overrides(holidays, workdays),
        sensitivity=_sensitivity(sensitivity),
    )


@app.get("/api/triage")
def triage(
    holidays: str | None = Query(default=None),
    workdays: str | None = Query(default=None),
) -> dict:
    """Ranked days worth looking at, independent of the viewer's sensitivity."""
    storage = create_storage(Settings.from_env())
    return build_triage(
        storage.load_workspace_usage(), storage.load_import_state(), default_detectors(),
        storage.load_dispositions(), day_overrides=_day_overrides(holidays, workdays),
    )


@app.post("/api/dispositions")
def record_disposition(payload: dict = Body(...)) -> dict:
    """Mark a day as checked (or clear the mark) so it leaves the triage list."""
    try:
        day = date.fromisoformat(str(payload.get("date", ""))).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日付の形式が不正です") from exc
    kind = str(payload.get("kind", ""))
    if kind not in DISPOSITION_KINDS:
        raise HTTPException(status_code=400, detail=f"kind は {', '.join(DISPOSITION_KINDS)} のいずれかにしてください")
    disposition = {"date": day, "kind": kind, "recorded_at": datetime.now(timezone.utc).isoformat()}
    storage = create_storage(Settings.from_env())
    storage.append_disposition(disposition)
    return {"disposition": disposition}


@app.post("/api/dispositions/reset")
def reset_dispositions() -> dict:
    """Clear every checked mark (the log stays append-only: one "cleared" record per date)."""
    storage = create_storage(Settings.from_env())
    now = datetime.now(timezone.utc).isoformat()
    days = checked_dates(storage.load_dispositions())
    for day in days:
        storage.append_disposition({"date": day, "kind": "cleared", "recorded_at": now})
    return {"cleared": days}


@app.get("/api/detectors")
def detectors() -> dict:
    """List configured detectors (id, label, parameters) and configuration errors."""
    configured = default_detectors()
    return {"detectors": configured.describe(), "errors": configured.errors}


@app.get("/api/imports")
def import_history() -> dict:
    storage = create_storage(Settings.from_env())
    return {"imports": storage.list_import_history()}


@app.get("/api/individual")
def individual_dashboard(
    user_id: str | None = Query(default=None),
    holidays: str | None = Query(default=None),
    workdays: str | None = Query(default=None),
    sensitivity: float | None = Query(default=None),
) -> dict:
    storage = create_storage(Settings.from_env())
    return build_individual_dashboard(
        storage.load_individual_usage(), storage.load_individual_import_state(), user_id,
        day_overrides=_day_overrides(holidays, workdays), sensitivity=_sensitivity(sensitivity),
    )


@app.get("/api/individual/imports")
def individual_import_history() -> dict:
    storage = create_storage(Settings.from_env())
    return {"imports": storage.list_individual_import_history()}


MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@app.post("/api/import")
async def import_json(
    files: list[UploadFile] | None = File(default=None),
    active_users_file: UploadFile | None = File(default=None),
    tokens_file: UploadFile | None = File(default=None),
    holidays: str | None = Form(default=None),
    workdays: str | None = Form(default=None),
    sensitivity: float | None = Form(default=None),
) -> dict:
    overrides = _day_overrides(holidays, workdays)
    sensitivity_value = _sensitivity(sensitivity)
    payloads: dict[str, bytes] = {}
    upload_format = "json"
    if files is None:
        legacy = [upload for upload in (active_users_file, tokens_file) if upload is not None]
        if not legacy:
            raise HTTPException(status_code=400, detail="JSONファイルを選択してください")
        if any(Path(upload.filename or "").suffix.lower() == ".csv" for upload in legacy):
            if len(legacy) != 2 or any(Path(upload.filename or "").suffix.lower() != ".csv" for upload in legacy):
                raise HTTPException(status_code=400, detail="旧CSV形式は2種類を同時に指定してください")
            active_bytes = await active_users_file.read(MAX_UPLOAD_BYTES + 1)
            token_bytes = await tokens_file.read(MAX_UPLOAD_BYTES + 1)
            if max(len(active_bytes), len(token_bytes)) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="1ファイル5 MiB以下にしてください")
            try:
                rows = parse_and_join(active_bytes, token_bytes)
            except CSVImportError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            payloads = {"active-users": active_bytes, "tokens": token_bytes}
            upload_format = "csv"
        else:
            files = legacy
    if files is not None:
        if len(files) not in {1, 2}:
            raise HTTPException(status_code=400, detail="JSONは1ファイルずつ、または2ファイルまとめて選択してください")
        daily: dict[str, dict] = {}
        try:
            for upload in files:
                payload = await upload.read(MAX_UPLOAD_BYTES + 1)
                if len(payload) > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="JSONは1ファイル5 MiB以下にしてください")
                chart_key, parsed = parse_workspace_json(payload)
                if chart_key in payloads:
                    raise HTTPException(status_code=400, detail=f"{chart_key} のJSONが重複しています")
                payloads[chart_key] = payload
                metric = "active_users" if chart_key == "active-users" else "tokens"
                for day, source in parsed.items():
                    row = daily.setdefault(day, {"date": day, "end_date": source["end_date"]})
                    row[metric] = dict(source["values"])
                    if metric == "tokens":
                        row[metric]["total"] = sum(source["values"].values())
        except JSONImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        rows = [daily[day] for day in sorted(daily)]

    storage = create_storage(Settings.from_env())
    run_id = storage.create_run()
    for chart_key, payload in payloads.items():
        if upload_format == "csv":
            storage.save_raw_csv(run_id, f"{chart_key}.csv", payload)
        else:
            storage.save_raw_json(run_id, f"{chart_key}.json", payload)
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
    return build_workspace_dashboard(storage.load_workspace_usage(), state, day_overrides=overrides,
                                     sensitivity=sensitivity_value)


@app.post("/api/individual/import")
async def import_individual_json(
    user_label: str = Form(...),
    tokens_file: UploadFile = File(...),
    holidays: str | None = Form(default=None),
    workdays: str | None = Form(default=None),
    sensitivity: float | None = Form(default=None),
) -> dict:
    overrides = _day_overrides(holidays, workdays)
    sensitivity_value = _sensitivity(sensitivity)
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
    return build_individual_dashboard(storage.load_individual_usage(), state, user_id, day_overrides=overrides,
                                      sensitivity=sensitivity_value)
