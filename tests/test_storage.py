from pathlib import Path
import hashlib

from app.storage import LocalStorage


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
