from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any


class JSONImportError(ValueError):
    pass


def identify_chart_key(payload: bytes) -> str:
    try:
        document = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JSONImportError("正しいUTF-8 JSONではありません") from exc
    if not isinstance(document, dict):
        raise JSONImportError("JSONの最上位はオブジェクトである必要があります")
    chart_key = document.get("chart_key")
    if chart_key not in {"active-users", "tokens"}:
        raise JSONImportError("chart_key が active-users または tokens ではありません")
    return chart_key


def parse_and_join_json(active_bytes: bytes, token_bytes: bytes) -> list[dict[str, Any]]:
    active = _parse(active_bytes, "active-users", "アクティブユーザーJSON")
    tokens = _parse(token_bytes, "tokens", "トークンJSON")
    if set(active) != set(tokens):
        active_only = sorted(set(active) - set(tokens))
        token_only = sorted(set(tokens) - set(active))
        details = []
        if active_only:
            details.append(f"アクティブユーザーJSONのみ: {', '.join(active_only)}")
        if token_only:
            details.append(f"トークンJSONのみ: {', '.join(token_only)}")
        raise JSONImportError("2つのJSONの日付が一致しません（" + " / ".join(details) + "）")

    return [
        {
            "date": day,
            "end_date": active[day]["end_date"],
            "active_users": active[day]["values"],
            "tokens": {**tokens[day]["values"], "total": sum(tokens[day]["values"].values())},
        }
        for day in sorted(active)
    ]


def parse_token_json(token_bytes: bytes) -> list[dict[str, Any]]:
    tokens = _parse(token_bytes, "tokens", "個人別トークンJSON")
    return [
        {
            "date": day,
            "end_date": tokens[day]["end_date"],
            "tokens": {**tokens[day]["values"], "total": sum(tokens[day]["values"].values())},
        }
        for day in sorted(tokens)
    ]


def _parse(payload: bytes, expected_key: str, label: str) -> dict[str, dict[str, Any]]:
    try:
        document = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JSONImportError(f"{label}が正しいUTF-8 JSONではありません") from exc
    if not isinstance(document, dict):
        raise JSONImportError(f"{label}の最上位はJSONオブジェクトである必要があります")
    if document.get("chart_key") != expected_key:
        expected = "active-users" if expected_key == "active-users" else "tokens"
        raise JSONImportError(f"{label}の種類を判定できません（chart_key は {expected} が必要です）")

    series = document.get("series")
    required_columns = {"Chat", "Codex", "Work"}
    if not isinstance(series, list) or any(not isinstance(item, dict) for item in series):
        raise JSONImportError(f"{label}にseries配列がありません")
    columns = [item.get("column") for item in series]
    if len(columns) != len(required_columns) or set(columns) != required_columns:
        raise JSONImportError(f"{label}のseriesにはChat・Codex・Workが各1つ必要です")

    source_rows = document.get("rows")
    if not isinstance(source_rows, list) or not source_rows:
        raise JSONImportError(f"{label}にrowsデータがありません")
    parsed: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(source_rows, start=1):
        if not isinstance(row, dict):
            raise JSONImportError(f"{label}のrows {index}件目はオブジェクトである必要があります")
        try:
            start = _date_value(row.get("Start Time"))
            end = _date_value(row.get("End Time"))
        except (TypeError, ValueError) as exc:
            raise JSONImportError(f"{label}のrows {index}件目の日付が不正です") from exc
        if end < start:
            raise JSONImportError(f"{label}のrows {index}件目でEnd TimeがStart Timeより前です")
        if start in parsed:
            raise JSONImportError(f"{label}に日付 {start} が重複しています")

        values: dict[str, int] = {}
        for column, product in (("Chat", "chat"), ("Codex", "codex"), ("Work", "work")):
            value = row.get(column)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise JSONImportError(f"{label}のrows {index}件目 {column} は0以上の整数である必要があります")
            values[product] = value
        parsed[start] = {"end_date": end, "values": values}
    return parsed


def _date_value(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("empty date")
    raw = value.strip()
    if len(raw) == 10:
        return date.fromisoformat(raw).isoformat()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw).date().isoformat()
