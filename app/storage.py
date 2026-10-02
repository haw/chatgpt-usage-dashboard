from __future__ import annotations

import csv
import hashlib
import json
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


def _existing_path(directory: Path, preferred: str, legacy: str) -> Path:
    current = directory / preferred
    return current if current.exists() else directory / legacy


def _existing_name(names: set[str], preferred: str, legacy: str) -> str | None:
    if preferred in names:
        return preferred
    return legacy if legacy in names else None


def _import_dates(path: Path) -> list[str]:
    return _import_dates_from_bytes(path.read_bytes(), path.name)


def _import_dates_from_bytes(payload: bytes, name: str) -> list[str]:
    if name.endswith(".json"):
        document = json.loads(payload.decode("utf-8-sig"))
        rows = document.get("rows", []) if isinstance(document, dict) else []
        return [str(row["Start Time"])[:10] for row in rows if isinstance(row, dict) and row.get("Start Time")]
    text = payload.decode("utf-8-sig")
    return [(row.get("Start Time") or "").strip()[:10]
            for row in csv.DictReader(StringIO(text))
            if (row.get("Start Time") or "").strip()]


class Storage(Protocol):
    def create_run(self) -> str: ...
    def save_raw_page(self, run_id: str, page_number: int, payload: Any) -> Any: ...
    def save_raw_csv(self, run_id: str, name: str, payload: bytes) -> Any: ...
    def save_raw_json(self, run_id: str, name: str, payload: bytes) -> Any: ...
    def list_import_history(self) -> list[dict[str, Any]]: ...
    def load_workspace_usage(self) -> list[dict[str, Any]]: ...
    def merge_workspace_usage(self, incoming: list[dict[str, Any]]) -> int: ...
    def save_import_state(self, state: dict[str, Any]) -> None: ...
    def load_import_state(self) -> dict[str, Any]: ...
    def load_usage(self) -> list[dict[str, Any]]: ...
    def merge_usage(self, incoming: list[dict[str, Any]]) -> int: ...
    def save_state(self, state: dict[str, Any]) -> None: ...
    def load_state(self) -> dict[str, Any]: ...
    def load_individual_usage(self) -> list[dict[str, Any]]: ...
    def merge_individual_usage(self, incoming: list[dict[str, Any]]) -> int: ...
    def save_individual_import_state(self, state: dict[str, Any]) -> None: ...
    def load_individual_import_state(self) -> dict[str, Any]: ...
    def save_individual_import_metadata(self, run_id: str, metadata: dict[str, Any]) -> Any: ...
    def list_individual_import_history(self) -> list[dict[str, Any]]: ...
    def load_dispositions(self) -> list[dict[str, Any]]: ...
    def append_disposition(self, disposition: dict[str, Any]) -> None: ...


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
        if name not in {"active-users.csv", "tokens.csv", "individual-tokens.csv"}:
            raise ValueError("unsupported raw CSV name")
        path = self.raw_dir / run_id / name
        path.write_bytes(payload)
        return path

    def save_raw_json(self, run_id: str, name: str, payload: bytes) -> Path:
        if name not in {"active-users.json", "tokens.json", "individual-tokens.json"}:
            raise ValueError("unsupported raw JSON name")
        path = self.raw_dir / run_id / name
        path.write_bytes(payload)
        return path

    def list_import_history(self) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for run_dir in self.raw_dir.iterdir():
            if not run_dir.is_dir():
                continue
            active_path = _existing_path(run_dir, "active-users.json", "active-users.csv")
            token_path = _existing_path(run_dir, "tokens.json", "tokens.csv")
            if not active_path.exists() and not token_path.exists():
                continue
            try:
                dates = [day for path in (active_path, token_path) if path.exists() for day in _import_dates(path)]
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
                "active_users_bytes": active_path.stat().st_size if active_path.exists() else None,
                "tokens_bytes": token_path.stat().st_size if token_path.exists() else None,
                "active_users_sha256": hashlib.sha256(active_path.read_bytes()).hexdigest() if active_path.exists() else None,
                "tokens_sha256": hashlib.sha256(token_path.read_bytes()).hexdigest() if token_path.exists() else None,
            })
        return sorted(history, key=lambda item: item["run_id"], reverse=True)

    def save_individual_import_metadata(self, run_id: str, metadata: dict[str, Any]) -> Path:
        path = self.raw_dir / run_id / "individual-import.json"
        self._write_json(path, metadata)
        return path

    def list_individual_import_history(self) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        latest_state = self.load_individual_import_state()
        for run_dir in self.raw_dir.iterdir():
            if not run_dir.is_dir():
                continue
            import_path = _existing_path(run_dir, "individual-tokens.json", "individual-tokens.csv")
            if not import_path.exists():
                continue
            try:
                payload = import_path.read_bytes()
                dates = _import_dates(import_path)
                imported_at = datetime.strptime(run_dir.name, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc).isoformat()
                metadata_path = run_dir / "individual-import.json"
                metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
                if not metadata and latest_state.get("run_id") == run_dir.name:
                    metadata = latest_state
            except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
                continue
            history.append({
                "run_id": run_dir.name, "imported_at": imported_at,
                "user_id": metadata.get("user_id"),
                "user_label": metadata.get("user_label") or "不明（旧データ）",
                "start_date": metadata.get("start_date") or (min(dates) if dates else None),
                "end_date": metadata.get("end_date") or (max(dates) if dates else None),
                "days": metadata.get("imported_days") or len(set(dates)),
                "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            })
        return sorted(history, key=lambda item: item["run_id"], reverse=True)

    def load_workspace_usage(self) -> list[dict[str, Any]]:
        path = self.normalized_dir / "workspace-usage.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def load_individual_usage(self) -> list[dict[str, Any]]:
        path = self.normalized_dir / "individual-usage.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def merge_individual_usage(self, incoming: list[dict[str, Any]]) -> int:
        merged = {(row["user_id"], row["date"]): row for row in self.load_individual_usage()}
        merged.update({(row["user_id"], row["date"]): row for row in incoming})
        rows = [merged[key] for key in sorted(merged)]
        target = self.normalized_dir / "individual-usage.jsonl"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        temporary.replace(target)
        return len(rows)

    def save_individual_import_state(self, state: dict[str, Any]) -> None:
        self._write_json(self.state_dir / "individual-import.json", state)

    def load_individual_import_state(self) -> dict[str, Any]:
        path = self.state_dir / "individual-import.json"
        if not path.exists():
            return {"status": "never_imported"}
        return json.loads(path.read_text(encoding="utf-8"))

    def load_dispositions(self) -> list[dict[str, Any]]:
        path = self.normalized_dir / "dispositions.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def append_disposition(self, disposition: dict[str, Any]) -> None:
        # Append-only: the analysts' decisions are a record, the latest one per date wins when read.
        path = self.normalized_dir / "dispositions.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(disposition, ensure_ascii=False, sort_keys=True) + "\n")

    def merge_workspace_usage(self, incoming: list[dict[str, Any]]) -> int:
        merged = {row["date"]: row for row in self.load_workspace_usage()}
        for row in incoming:
            merged[row["date"]] = {**merged.get(row["date"], {}), **row}
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
        if name not in {"active-users.csv", "tokens.csv", "individual-tokens.csv"}:
            raise ValueError("unsupported raw CSV name")
        digest = hashlib.sha256(payload).hexdigest()
        return self._put(f"raw/{run_id}/{name}", payload, "text/csv", {"sha256": digest})

    def save_raw_json(self, run_id: str, name: str, payload: bytes) -> str:
        if name not in {"active-users.json", "tokens.json", "individual-tokens.json"}:
            raise ValueError("unsupported raw JSON name")
        digest = hashlib.sha256(payload).hexdigest()
        return self._put(f"raw/{run_id}/{name}", payload, "application/json", {"sha256": digest})

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
            active_name = _existing_name(names, "active-users.json", "active-users.csv")
            token_name = _existing_name(names, "tokens.json", "tokens.csv")
            if not active_name and not token_name:
                continue
            try:
                active = self._get(f"raw/{run_id}/{active_name}") if active_name else None
                tokens = self._get(f"raw/{run_id}/{token_name}") if token_name else None
                if active is None and tokens is None:
                    continue
                dates = [day for payload, name in ((active, active_name), (tokens, token_name))
                         if payload is not None and name for day in _import_dates_from_bytes(payload, name)]
                imported_at = datetime.strptime(run_id, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc).isoformat()
            except (UnicodeDecodeError, ValueError):
                continue
            history.append({
                "run_id": run_id, "imported_at": imported_at,
                "start_date": min(dates) if dates else None,
                "end_date": max(dates) if dates else None,
                "days": len(set(dates)),
                "active_users_bytes": len(active) if active is not None else None,
                "tokens_bytes": len(tokens) if tokens is not None else None,
                "active_users_sha256": hashlib.sha256(active).hexdigest() if active is not None else None,
                "tokens_sha256": hashlib.sha256(tokens).hexdigest() if tokens is not None else None,
            })
        return sorted(history, key=lambda item: item["run_id"], reverse=True)

    def save_individual_import_metadata(self, run_id: str, metadata: dict[str, Any]) -> str:
        self._save_json(f"raw/{run_id}/individual-import.json", metadata)
        return self._key(f"raw/{run_id}/individual-import.json")

    def list_individual_import_history(self) -> list[dict[str, Any]]:
        root = self._key("raw/")
        paginator = self.client.get_paginator("list_objects_v2")
        runs: dict[str, set[str]] = {}
        for page in paginator.paginate(Bucket=self.bucket, Prefix=root):
            for item in page.get("Contents", []):
                relative = item["Key"][len(root):]
                parts = relative.split("/", 1)
                if len(parts) == 2:
                    runs.setdefault(parts[0], set()).add(parts[1])
        latest_state = self.load_individual_import_state()
        history: list[dict[str, Any]] = []
        for run_id, names in runs.items():
            import_name = _existing_name(names, "individual-tokens.json", "individual-tokens.csv")
            if not import_name:
                continue
            try:
                payload = self._get(f"raw/{run_id}/{import_name}")
                if payload is None:
                    continue
                dates = _import_dates_from_bytes(payload, import_name)
                imported_at = datetime.strptime(run_id, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc).isoformat()
                metadata_body = self._get(f"raw/{run_id}/individual-import.json")
                metadata = json.loads(metadata_body.decode()) if metadata_body else {}
                if not metadata and latest_state.get("run_id") == run_id:
                    metadata = latest_state
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                continue
            history.append({
                "run_id": run_id, "imported_at": imported_at,
                "user_id": metadata.get("user_id"),
                "user_label": metadata.get("user_label") or "不明（旧データ）",
                "start_date": metadata.get("start_date") or (min(dates) if dates else None),
                "end_date": metadata.get("end_date") or (max(dates) if dates else None),
                "days": metadata.get("imported_days") or len(set(dates)),
                "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
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

    def load_individual_usage(self) -> list[dict[str, Any]]:
        return self._load_jsonl("normalized/individual-usage.jsonl")

    def load_dispositions(self) -> list[dict[str, Any]]:
        return self._load_jsonl("normalized/dispositions.jsonl")

    def append_disposition(self, disposition: dict[str, Any]) -> None:
        self._save_jsonl("normalized/dispositions.jsonl", [*self.load_dispositions(), disposition])

    def merge_individual_usage(self, incoming: list[dict[str, Any]]) -> int:
        merged = {(row["user_id"], row["date"]): row for row in self.load_individual_usage()}
        merged.update({(row["user_id"], row["date"]): row for row in incoming})
        rows = [merged[key] for key in sorted(merged)]
        self._save_jsonl("normalized/individual-usage.jsonl", rows)
        return len(rows)

    def save_individual_import_state(self, state: dict[str, Any]) -> None:
        self._save_json("state/individual-import.json", state)

    def load_individual_import_state(self) -> dict[str, Any]:
        return self._load_json("state/individual-import.json", {"status": "never_imported"})

    def merge_workspace_usage(self, incoming: list[dict[str, Any]]) -> int:
        merged = {row["date"]: row for row in self.load_workspace_usage()}
        for row in incoming:
            merged[row["date"]] = {**merged.get(row["date"], {}), **row}
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
