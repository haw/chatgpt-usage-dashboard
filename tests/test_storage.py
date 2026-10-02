from pathlib import Path
import hashlib
from io import BytesIO
from types import SimpleNamespace

from app.storage import LocalStorage, S3Storage, create_storage


def test_independent_workspace_metrics_and_single_file_history_on_both_stores(tmp_path):
    for storage in (LocalStorage(tmp_path), S3Storage("test", client=FakeS3Client())):
        storage.merge_workspace_usage([{"date": "2026-09-01", "tokens": {"total": 10}}])
        storage.merge_workspace_usage([{"date": "2026-09-01", "active_users": {"chat": 5}}])
        storage.merge_workspace_usage([{"date": "2026-09-01", "tokens": {"total": 0}}])
        assert storage.load_workspace_usage() == [
            {"date": "2026-09-01", "tokens": {"total": 0}, "active_users": {"chat": 5}},
        ]
        payload = b'{"rows":[{"Start Time":"2026-09-01"}]}'
        run_id = storage.create_run()
        storage.save_raw_json(run_id, "tokens.json", payload)
        history = storage.list_import_history()
        assert len(history) == 1
        assert history[0]["tokens_sha256"] == hashlib.sha256(payload).hexdigest()
        assert history[0]["active_users_bytes"] is None


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


def test_individual_merge_is_scoped_by_user_and_date(tmp_path: Path):
    storage = LocalStorage(tmp_path)
    base = {"date": "2026-09-01", "tokens": {"total": 10}}
    storage.merge_individual_usage([
        {**base, "user_id": "u1", "user_label": "User 1"},
        {**base, "user_id": "u2", "user_label": "User 2"},
    ])
    storage.merge_individual_usage([
        {**base, "user_id": "u1", "user_label": "User 1", "tokens": {"total": 20}},
    ])
    assert [(row["user_id"], row["tokens"]["total"]) for row in storage.load_individual_usage()] == [
        ("u1", 20), ("u2", 10)
    ]
    assert storage.load_individual_import_state() == {"status": "never_imported"}


def test_lists_individual_import_history_with_metadata(tmp_path: Path):
    storage = LocalStorage(tmp_path)
    run_id = storage.create_run()
    payload = b"Start Time,End Time,Chat,Codex,Work\n2026-09-01,2026-09-02,1,2,3\n"
    storage.save_raw_csv(run_id, "individual-tokens.csv", payload)
    storage.save_individual_import_metadata(run_id, {
        "user_id": "u1", "user_label": "User 1", "start_date": "2026-09-01",
        "end_date": "2026-09-01", "imported_days": 1,
    })
    history = storage.list_individual_import_history()
    assert history[0]["user_label"] == "User 1"
    assert history[0]["days"] == 1
    assert history[0]["sha256"] == hashlib.sha256(payload).hexdigest()


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


def test_s3_storage_persists_individual_usage():
    client = FakeS3Client()
    storage = S3Storage("usage-bucket", "dashboard", client)
    row = {"user_id": "u1", "user_label": "User", "date": "2026-09-01", "tokens": {"total": 5}}
    storage.merge_individual_usage([row])
    storage.save_individual_import_state({"status": "success"})
    assert storage.load_individual_usage() == [row]
    assert storage.load_individual_import_state() == {"status": "success"}


def test_s3_storage_lists_individual_import_history():
    client = FakeS3Client()
    storage = S3Storage("usage-bucket", "dashboard", client)
    run_id = "20260901T010203.000000Z"
    payload = b"Start Time,End Time,Chat,Codex,Work\n2026-09-01,2026-09-02,1,2,3\n"
    storage.save_raw_csv(run_id, "individual-tokens.csv", payload)
    storage.save_individual_import_metadata(run_id, {
        "user_id": "u1", "user_label": "User 1", "imported_days": 1,
    })
    history = storage.list_individual_import_history()
    assert history[0]["user_label"] == "User 1"
    assert history[0]["start_date"] == "2026-09-01"


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
