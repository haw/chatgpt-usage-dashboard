from __future__ import annotations

import csv
import hashlib
import json
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.raw_dir = root / "raw"
        self.normalized_dir = root / "normalized"
        self.state_dir = root / "state"
        for directory in (self.raw_dir, self.normalized_dir, self.state_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def create_run(self) -> str:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        (self.raw_dir / run_id).mkdir(parents=True, exist_ok=False)
        return run_id

    def save_raw_page(self, run_id: str, page_number: int, payload: Any) -> Path:
        path = self.raw_dir / run_id / f"page-{page_number:04d}.json"
        self._write_json(path, payload)
        return path

    def save_raw_csv(self, run_id: str, name: str, payload: bytes) -> Path:
        if name not in {"active-users.csv", "tokens.csv"}:
            raise ValueError("unsupported raw CSV name")
        path = self.raw_dir / run_id / name
        path.write_bytes(payload)
        return path

    def list_import_history(self) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for run_dir in self.raw_dir.iterdir():
            if not run_dir.is_dir():
                continue
            active_path = run_dir / "active-users.csv"
            token_path = run_dir / "tokens.csv"
            if not active_path.exists() or not token_path.exists():
                continue
            try:
                text = active_path.read_text(encoding="utf-8-sig")
                dates = [
                    (row.get("Start Time") or "").strip()[:10]
                    for row in csv.DictReader(StringIO(text))
                    if (row.get("Start Time") or "").strip()
                ]
                imported_at = datetime.strptime(
                    run_dir.name, "%Y%m%dT%H%M%S.%fZ"
                ).replace(tzinfo=timezone.utc).isoformat()
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            history.append({
                "run_id": run_dir.name,
                "imported_at": imported_at,
                "start_date": min(dates) if dates else None,
                "end_date": max(dates) if dates else None,
                "days": len(set(dates)),
                "active_users_bytes": active_path.stat().st_size,
                "tokens_bytes": token_path.stat().st_size,
                "active_users_sha256": hashlib.sha256(active_path.read_bytes()).hexdigest(),
                "tokens_sha256": hashlib.sha256(token_path.read_bytes()).hexdigest(),
            })
        return sorted(history, key=lambda item: item["run_id"], reverse=True)

    def load_workspace_usage(self) -> list[dict[str, Any]]:
        path = self.normalized_dir / "workspace-usage.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def merge_workspace_usage(self, incoming: list[dict[str, Any]]) -> int:
        merged = {row["date"]: row for row in self.load_workspace_usage()}
        merged.update({row["date"]: row for row in incoming})
        rows = [merged[key] for key in sorted(merged)]
        target = self.normalized_dir / "workspace-usage.jsonl"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        temporary.replace(target)
        return len(rows)

    def save_import_state(self, state: dict[str, Any]) -> None:
        self._write_json(self.state_dir / "import.json", state)

    def load_import_state(self) -> dict[str, Any]:
        path = self.state_dir / "import.json"
        if not path.exists():
            return {"status": "never_imported"}
        return json.loads(path.read_text(encoding="utf-8"))

    def load_usage(self) -> list[dict[str, Any]]:
        path = self.normalized_dir / "usage.jsonl"
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def merge_usage(self, incoming: list[dict[str, Any]]) -> int:
        existing = self.load_usage()
        merged = {
            (row["date"], row["user_id"], row["product"]): row
            for row in existing
        }
        for row in incoming:
            merged[(row["date"], row["user_id"], row["product"])] = row
        rows = sorted(merged.values(), key=lambda row: (row["date"], row["user_id"], row["product"]))
        target = self.normalized_dir / "usage.jsonl"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        temporary.replace(target)
        return len(rows)

    def save_state(self, state: dict[str, Any]) -> None:
        self._write_json(self.state_dir / "collection.json", state)

    def load_state(self) -> dict[str, Any]:
        path = self.state_dir / "collection.json"
        if not path.exists():
            return {"status": "never_collected"}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
