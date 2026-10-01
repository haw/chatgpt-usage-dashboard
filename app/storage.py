from __future__ import annotations

import csv
import hashlib
import json
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


class Storage(Protocol):
    def create_run(self) -> str: ...
    def save_raw_page(self, run_id: str, page_number: int, payload: Any) -> Any: ...
    def save_raw_csv(self, run_id: str, name: str, payload: bytes) -> Any: ...
    def list_import_history(self) -> list[dict[str, Any]]: ...
    def load_workspace_usage(self) -> list[dict[str, Any]]: ...
    def merge_workspace_usage(self, incoming: list[dict[str, Any]]) -> int: ...
    def save_import_state(self, state: dict[str, Any]) -> None: ...
    def load_import_state(self) -> dict[str, Any]: ...
    def load_usage(self) -> list[dict[str, Any]]: ...
    def merge_usage(self, incoming: list[dict[str, Any]]) -> int: ...
    def save_state(self, state: dict[str, Any]) -> None: ...
    def load_state(self) -> dict[str, Any]: ...


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


class S3Storage:
    def __init__(self, bucket: str, prefix: str = "chatgpt-dashboard", client: Any = None):
        if not bucket:
            raise ValueError("S3 bucket is required")
        if client is None:
            import boto3
            client = boto3.client("s3")
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def _key(self, path: str) -> str:
        return f"{self.prefix}/{path}" if self.prefix else path

    def _put(self, path: str, body: bytes, content_type: str, metadata: dict[str, str] | None = None) -> str:
        key = self._key(path)
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket, "Key": key, "Body": body, "ContentType": content_type,
        }
        if metadata:
            kwargs["Metadata"] = metadata
        self.client.put_object(**kwargs)
        return key

    def _get(self, path: str) -> bytes | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(path))
        except self.client.exceptions.NoSuchKey:
            return None
        return response["Body"].read()

    def create_run(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")

    def save_raw_page(self, run_id: str, page_number: int, payload: Any) -> str:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode()
        return self._put(f"raw/{run_id}/page-{page_number:04d}.json", body, "application/json")

    def save_raw_csv(self, run_id: str, name: str, payload: bytes) -> str:
        if name not in {"active-users.csv", "tokens.csv"}:
            raise ValueError("unsupported raw CSV name")
        digest = hashlib.sha256(payload).hexdigest()
        return self._put(f"raw/{run_id}/{name}", payload, "text/csv", {"sha256": digest})

    def list_import_history(self) -> list[dict[str, Any]]:
        root = self._key("raw/")
        paginator = self.client.get_paginator("list_objects_v2")
        runs: dict[str, set[str]] = {}
        for page in paginator.paginate(Bucket=self.bucket, Prefix=root):
            for item in page.get("Contents", []):
                relative = item["Key"][len(root):]
                parts = relative.split("/", 1)
                if len(parts) == 2:
                    runs.setdefault(parts[0], set()).add(parts[1])
        history: list[dict[str, Any]] = []
        for run_id, names in runs.items():
            if not {"active-users.csv", "tokens.csv"}.issubset(names):
                continue
            try:
                active = self._get(f"raw/{run_id}/active-users.csv")
                tokens = self._get(f"raw/{run_id}/tokens.csv")
                if active is None or tokens is None:
                    continue
                text = active.decode("utf-8-sig")
                dates = [(row.get("Start Time") or "").strip()[:10]
                         for row in csv.DictReader(StringIO(text))
                         if (row.get("Start Time") or "").strip()]
                imported_at = datetime.strptime(run_id, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc).isoformat()
            except (UnicodeDecodeError, ValueError):
                continue
            history.append({
                "run_id": run_id, "imported_at": imported_at,
                "start_date": min(dates) if dates else None,
                "end_date": max(dates) if dates else None,
                "days": len(set(dates)),
                "active_users_bytes": len(active), "tokens_bytes": len(tokens),
                "active_users_sha256": hashlib.sha256(active).hexdigest(),
                "tokens_sha256": hashlib.sha256(tokens).hexdigest(),
            })
        return sorted(history, key=lambda item: item["run_id"], reverse=True)

    def _load_jsonl(self, path: str) -> list[dict[str, Any]]:
        body = self._get(path)
        if body is None:
            return []
        return [json.loads(line) for line in body.decode().splitlines() if line.strip()]

    def _save_jsonl(self, path: str, rows: list[dict[str, Any]]) -> None:
        body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode()
        self._put(path, body, "application/x-ndjson")

    def load_workspace_usage(self) -> list[dict[str, Any]]:
        return self._load_jsonl("normalized/workspace-usage.jsonl")

    def merge_workspace_usage(self, incoming: list[dict[str, Any]]) -> int:
        merged = {row["date"]: row for row in self.load_workspace_usage()}
        merged.update({row["date"]: row for row in incoming})
        rows = [merged[key] for key in sorted(merged)]
        self._save_jsonl("normalized/workspace-usage.jsonl", rows)
        return len(rows)

    def _save_json(self, path: str, payload: Any) -> None:
        self._put(path, json.dumps(payload, ensure_ascii=False, indent=2).encode(), "application/json")

    def _load_json(self, path: str, default: dict[str, Any]) -> dict[str, Any]:
        body = self._get(path)
        return default if body is None else json.loads(body.decode())

    def save_import_state(self, state: dict[str, Any]) -> None:
        self._save_json("state/import.json", state)

    def load_import_state(self) -> dict[str, Any]:
        return self._load_json("state/import.json", {"status": "never_imported"})

    def load_usage(self) -> list[dict[str, Any]]:
        return self._load_jsonl("normalized/usage.jsonl")

    def merge_usage(self, incoming: list[dict[str, Any]]) -> int:
        merged = {(row["date"], row["user_id"], row["product"]): row for row in self.load_usage()}
        for row in incoming:
            merged[(row["date"], row["user_id"], row["product"])] = row
        rows = sorted(merged.values(), key=lambda row: (row["date"], row["user_id"], row["product"]))
        self._save_jsonl("normalized/usage.jsonl", rows)
        return len(rows)

    def save_state(self, state: dict[str, Any]) -> None:
        self._save_json("state/collection.json", state)

    def load_state(self) -> dict[str, Any]:
        return self._load_json("state/collection.json", {"status": "never_collected"})


def create_storage(settings: Any, *, s3_client: Any = None) -> Storage:
    if settings.storage_backend == "s3":
        if s3_client is None:
            import boto3
            s3_client = boto3.client("s3", region_name=settings.aws_region)
        return S3Storage(settings.s3_bucket, settings.s3_prefix, s3_client)
    return LocalStorage(settings.data_dir)
