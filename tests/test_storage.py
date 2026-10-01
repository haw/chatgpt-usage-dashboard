from pathlib import Path
import hashlib
from io import BytesIO
from types import SimpleNamespace

from app.storage import LocalStorage, S3Storage, create_storage


class FakeS3Client:
    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self):
        self.objects: dict[tuple[str, str], dict] = {}

    def put_object(self, **kwargs):
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs

    def get_object(self, *, Bucket, Key):
        try:
            item = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise self.exceptions.NoSuchKey() from exc
        return {"Body": BytesIO(item["Body"]), "Metadata": item.get("Metadata", {})}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        client = self

        class Paginator:
            def paginate(self, *, Bucket, Prefix):
                contents = [
                    {"Key": key} for bucket, key in client.objects
                    if bucket == Bucket and key.startswith(Prefix)
                ]
                return [{"Contents": contents}]

        return Paginator()


def row(activity: int) -> dict:
    return {"date": "2026-09-01", "user_id": "u1", "user_name": "User",
            "product": "chatgpt", "activity": activity, "metrics": {"messages": activity}}


def test_merge_is_idempotent(tmp_path: Path):
    storage = LocalStorage(tmp_path)
    storage.merge_usage([row(10)])
    storage.merge_usage([row(12)])

    saved = storage.load_usage()
    assert len(saved) == 1
    assert saved[0]["activity"] == 12


def test_state_defaults_before_collection(tmp_path: Path):
    assert LocalStorage(tmp_path).load_state() == {"status": "never_collected"}


def test_workspace_merge_replaces_same_date(tmp_path: Path):
    storage = LocalStorage(tmp_path)
    first = {"date": "2026-09-01", "tokens": {"total": 10}}
    second = {"date": "2026-09-01", "tokens": {"total": 20}}
    storage.merge_workspace_usage([first])
    storage.merge_workspace_usage([second])
    assert storage.load_workspace_usage() == [second]
    assert storage.load_import_state() == {"status": "never_imported"}


def test_lists_saved_csv_import_history(tmp_path: Path):
    storage = LocalStorage(tmp_path)
    run_id = storage.create_run()
    active = b"Start Time,End Time,Chat,Codex,Work\n2026-09-01,2026-09-02,1,2,3\n"
    storage.save_raw_csv(run_id, "active-users.csv", active)
    storage.save_raw_csv(run_id, "tokens.csv", active)

    history = storage.list_import_history()
    assert len(history) == 1
    assert history[0]["run_id"] == run_id
    assert history[0]["start_date"] == "2026-09-01"
    assert history[0]["end_date"] == "2026-09-01"
    assert history[0]["days"] == 1
    assert history[0]["active_users_sha256"] == hashlib.sha256(active).hexdigest()
    assert history[0]["tokens_sha256"] == hashlib.sha256(active).hexdigest()


def test_s3_storage_persists_workspace_data_state_and_history():
    client = FakeS3Client()
    storage = S3Storage("usage-bucket", "company/dashboard", client)
    run_id = "20260901T010203.000000Z"
    active = b"Start Time,End Time,Chat,Codex,Work\n2026-09-01,2026-09-02,1,2,3\n"

    storage.save_raw_csv(run_id, "active-users.csv", active)
    storage.save_raw_csv(run_id, "tokens.csv", active)
    storage.merge_workspace_usage([{"date": "2026-09-01", "tokens": {"total": 10}}])
    storage.merge_workspace_usage([{"date": "2026-09-01", "tokens": {"total": 20}}])
    storage.save_import_state({"status": "success", "run_id": run_id})

    assert storage.load_workspace_usage() == [
        {"date": "2026-09-01", "tokens": {"total": 20}}
    ]
    assert storage.load_import_state() == {"status": "success", "run_id": run_id}
    history = storage.list_import_history()
    assert history[0]["run_id"] == run_id
    assert history[0]["days"] == 1
    assert history[0]["active_users_sha256"] == hashlib.sha256(active).hexdigest()
    assert ("usage-bucket", "company/dashboard/normalized/workspace-usage.jsonl") in client.objects


def test_storage_factory_selects_local_or_s3(tmp_path: Path):
    common = {
        "data_dir": tmp_path, "s3_bucket": "bucket", "s3_prefix": "prefix",
        "aws_region": "ap-northeast-1",
    }
    assert isinstance(create_storage(SimpleNamespace(storage_backend="local", **common)), LocalStorage)
    assert isinstance(
        create_storage(SimpleNamespace(storage_backend="s3", **common), s3_client=FakeS3Client()),
        S3Storage,
    )
