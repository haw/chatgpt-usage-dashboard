from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any

REQUIRED_COLUMNS = ["Start Time", "End Time", "Chat", "Codex", "Work"]
PRODUCTS = ("chat", "codex", "work")


class CSVImportError(ValueError):
    pass


def parse_and_join(active_bytes: bytes, token_bytes: bytes) -> list[dict[str, Any]]:
    active = _parse(active_bytes, "アクティブユーザーCSV")
    tokens = _parse(token_bytes, "トークンCSV")
    if set(active) != set(tokens):
        active_only = sorted(set(active) - set(tokens))
        token_only = sorted(set(tokens) - set(active))
        details = []
        if active_only:
            details.append(f"アクティブユーザーCSVのみ: {', '.join(active_only)}")
        if token_only:
            details.append(f"トークンCSVのみ: {', '.join(token_only)}")
        raise CSVImportError("2つのCSVの日付が一致しません（" + " / ".join(details) + "）")

    return [
        {
            "date": day,
            "end_date": active[day]["end_date"],
            "active_users": active[day]["values"],
            "tokens": {**tokens[day]["values"], "total": sum(tokens[day]["values"].values())},
        }
        for day in sorted(active)
    ]


def _parse(payload: bytes, label: str) -> dict[str, dict[str, Any]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVImportError(f"{label}はUTF-8で保存してください") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != REQUIRED_COLUMNS:
        raise CSVImportError(
            f"{label}の列は {', '.join(REQUIRED_COLUMNS)} の順である必要があります"
        )
    parsed: dict[str, dict[str, Any]] = {}
    for line_number, row in enumerate(reader, start=2):
        try:
            start = _date_value(row["Start Time"])
            end = _date_value(row["End Time"])
        except ValueError as exc:
            raise CSVImportError(f"{label}の{line_number}行目の日付が不正です") from exc
        if start in parsed:
            raise CSVImportError(f"{label}に日付 {start} が重複しています")
        values: dict[str, int] = {}
        for source, product in zip(("Chat", "Codex", "Work"), PRODUCTS):
            raw = (row[source] or "").strip()
            try:
                value = int(raw)
            except ValueError as exc:
                raise CSVImportError(f"{label}の{line_number}行目 {source} は整数ではありません") from exc
            if value < 0:
                raise CSVImportError(f"{label}の{line_number}行目 {source} は負数にできません")
            values[product] = value
        parsed[start] = {"end_date": end, "values": values}
    if not parsed:
        raise CSVImportError(f"{label}にデータ行がありません")
    return parsed


def _date_value(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("empty date")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw).date().isoformat()
    except ValueError:
        return date.fromisoformat(raw).isoformat()
