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
from app.licenses import third_party_licenses
from app.triage import DISPOSITION_KINDS, build_triage, checked_dates
from app.version import semver, version_info

from app import auth

# The API only. The React app in frontend/ is served separately (Vite in development,
# S3 + CloudFront in production); FRONTEND_DIST optionally serves a built copy from here.
API_DESCRIPTION = """
ChatGPT 管理画面から出力した日次集計 JSON を取り込み、平日/休日を区別した基準で「普段と違う日」を判定する API。
画面（React）はこの API だけを使います。`AUTH_MODE=google` のときは `/health`・ログイン関連以外は社内 Google アカウントの
セッション Cookie が必要です（この docs も同じ）。

- 閲覧者ごとの設定は各リクエストのパラメータで渡します: `sensitivity`（0.25〜4、既定 1）、`holidays` / `workdays`（カンマ区切りの日付で区分を上書き）、`level_shifts`（true で「続く変化も判定」。既定 false）。
- 判定の中身（検知器）は `config/detectors.toml` で設定し、`GET /api/detectors` で確認できます。
"""
TAGS = [
    {"name": "dashboard", "description": "推移: 保存済みデータの集計、検出点、判定ライン"},
    {"name": "insights", "description": "インサイト: 確認する日の順位付け、観点ごとの判定、確認済みの記録"},
    {"name": "import", "description": "取込: 管理画面 JSON のアップロードと履歴"},
    {"name": "individual", "description": "個人別: ユーザーを絞り込んだトークン JSON"},
    {"name": "auth", "description": "ログイン状態（Google OIDC は /login/google から開始）"},
    {"name": "ops", "description": "ヘルスチェックと設定"},
]
app = FastAPI(
    title="ChatGPT Usage Dashboard API",
    version=semver(),
    description=API_DESCRIPTION,
    openapi_tags=TAGS,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
_settings = Settings.from_env()
# AUTH_MODE=google installs Google OIDC login and protects every route; AUTH_MODE=none (default) leaves it open.
oauth = auth.install(app, _settings)
auth.install_origin_check(app, _settings.origin_verify_secret)  # added last, so it runs first


@app.get("/health", tags=["ops"], summary="ヘルスチェック")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/version", tags=["ops"], summary="サーバーのバージョン")
def version() -> dict:
    """Semantic version of the API plus the first 8 characters of the deployed revision (`1.0.0+6095c825`)."""
    return version_info()


@app.get("/api/licenses", tags=["ops"], summary="サーバーが利用しているライブラリのライセンス")
def licenses() -> dict:
    """Name, version, license and license text of every Python package installed with the API."""
    return {"packages": third_party_licenses()}


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


@app.get("/api/dashboard", tags=["dashboard"], summary="推移: 集計・検出点・判定ライン", description="保存済みの日次データを期間で絞り、KPI、日次行（区分つき）、検出シグナル、総トークンの分析系列、設定済み検知器を返します。")
def dashboard(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    holidays: str | None = Query(default=None),
    workdays: str | None = Query(default=None),
    sensitivity: float | None = Query(default=None),
    level_shifts: bool = Query(default=False, description="続く変化（水準の変化）も判定に含める"),
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
        level_shifts=level_shifts,
    )


@app.get("/api/triage", tags=["insights"], summary="インサイト: 確認する日の順位表", description="反応した観点の数・その日に始まった変化か・初めてのパターンかで日を並べ、today / week / reference に分けて返します。感度には依存しません。")
def triage(
    holidays: str | None = Query(default=None),
    workdays: str | None = Query(default=None),
    level_shifts: bool = Query(default=False, description="続く変化（水準の変化）も判定に含める"),
) -> dict:
    """Ranked days worth looking at, independent of the viewer's sensitivity."""
    storage = create_storage(Settings.from_env())
    return build_triage(
        storage.load_workspace_usage(), storage.load_import_state(), default_detectors(),
        storage.load_dispositions(), day_overrides=_day_overrides(holidays, workdays), level_shifts=level_shifts,
    )


@app.get("/api/context", tags=["insights"], summary="指定日の前後の日次行（区分つき）", description="観点ごとの箱ひげ図・推移グラフのために、date の前後（既定 35 日前〜7 日後）の行を返します。")
def context(
    date_: date = Query(alias="date"),
    before: int = Query(default=35, ge=1, le=120),
    after: int = Query(default=7, ge=0, le=60),
    holidays: str | None = Query(default=None),
    workdays: str | None = Query(default=None),
) -> dict:
    """Daily rows around one date with their day kind, for the per-observation mini charts."""
    from datetime import timedelta

    from app.detectors.calendar import classify_days

    storage = create_storage(Settings.from_env())
    rows = sorted(storage.load_workspace_usage(), key=lambda row: row["date"])
    days = classify_days(rows, _day_overrides(holidays, workdays))
    start = (date_ - timedelta(days=before)).isoformat()
    end = (date_ + timedelta(days=after)).isoformat()
    window = [{**row, "day_kind": days[row["date"]]["kind"]} for row in rows if start <= row["date"] <= end]
    return {"date": date_.isoformat(), "rows": window}


@app.post("/api/dispositions", tags=["insights"], summary="確認済みの記録", description="`{\"date\": \"YYYY-MM-DD\", \"kind\": \"checked\" | \"cleared\"}` を追記保存します。日付ごとに最新の記録が有効です。")
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


@app.post("/api/dispositions/reset", tags=["insights"], summary="確認済みをすべて解除")
def reset_dispositions() -> dict:
    """Clear every checked mark (the log stays append-only: one "cleared" record per date)."""
    storage = create_storage(Settings.from_env())
    now = datetime.now(timezone.utc).isoformat()
    days = checked_dates(storage.load_dispositions())
    for day in days:
        storage.append_disposition({"date": day, "kind": "cleared", "recorded_at": now})
    return {"cleared": days}


@app.get("/api/detectors", tags=["ops"], summary="設定済み検知器の一覧と設定エラー")
def detectors() -> dict:
    """List configured detectors (id, label, parameters) and configuration errors."""
    configured = default_detectors()
    return {"detectors": configured.describe(), "errors": configured.errors}


@app.get("/api/imports", tags=["import"], summary="全体データの取込履歴")
def import_history() -> dict:
    storage = create_storage(Settings.from_env())
    return {"imports": storage.list_import_history()}


@app.get("/api/individual", tags=["individual"], summary="個人別: ユーザー一覧と選択ユーザーの集計")
def individual_dashboard(
    user_id: str | None = Query(default=None),
    holidays: str | None = Query(default=None),
    workdays: str | None = Query(default=None),
    sensitivity: float | None = Query(default=None),
    level_shifts: bool = Query(default=False),
) -> dict:
    storage = create_storage(Settings.from_env())
    return build_individual_dashboard(
        storage.load_individual_usage(), storage.load_individual_import_state(), user_id,
        day_overrides=_day_overrides(holidays, workdays), sensitivity=_sensitivity(sensitivity), level_shifts=level_shifts,
    )


@app.get("/api/individual/imports", tags=["individual"], summary="個人別データの取込履歴")
def individual_import_history() -> dict:
    storage = create_storage(Settings.from_env())
    return {"imports": storage.list_individual_import_history()}


MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@app.post("/api/import", tags=["import"], summary="全体データの取込（JSON 1〜2 ファイル）", description="`files` に active-users / tokens の Analytics JSON を 1 つずつ、または 2 つまとめて指定します。各 JSON を独立して検証し、日付・指標ごとに保存済みデータへ統合します。")
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


@app.post("/api/individual/import", tags=["individual"], summary="個人別トークン JSON の取込", description="`user_label`（氏名またはメール）と、対象ユーザーで絞り込んだ tokens JSON を指定します。")
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


def serve_frontend(dist: Path) -> None:
    """Serve a built copy of the React app with SPA fallback (single-container deployments)."""
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = dist / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


if _settings.frontend_dist and _settings.frontend_dist.is_dir():
    serve_frontend(_settings.frontend_dist)
