import re

from fastapi.testclient import TestClient

from app.licenses import third_party_licenses
from app.version import git_head, semver, version_info

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def test_version_is_semver_and_appends_the_first_8_characters_of_the_revision(monkeypatch):
    assert SEMVER.match(semver())
    monkeypatch.delenv("APP_REVISION", raising=False)
    assert version_info() == {"version": semver(), "semver": semver(), "revision": None}
    monkeypatch.setenv("APP_REVISION", "6095c825695add27bb50b54ebd234978db309d45")
    assert version_info() == {"version": f"{semver()}+6095c825", "semver": semver(), "revision": "6095c825"}


def test_local_development_reads_the_revision_from_a_git_directory(tmp_path, monkeypatch):
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text("1111111122222222333333334444444455555555\n")
    assert git_head(git) == "1111111122222222333333334444444455555555"

    (git / "refs" / "heads" / "main").unlink()  # after `git gc` the branch lives in packed-refs
    (git / "packed-refs").write_text("# pack-refs with: peeled fully-peeled sorted\naaaaaaaabbbbbbbbccccccccddddddddeeeeeeee refs/heads/main\n")
    assert git_head(git) == "aaaaaaaabbbbbbbbccccccccddddddddeeeeeeee"

    (git / "HEAD").write_text("9999999988888888777777776666666655555555\n")  # detached HEAD
    assert git_head(git) == "9999999988888888777777776666666655555555"
    assert git_head(tmp_path / "missing") is None

    monkeypatch.setenv("APP_REVISION", "")
    monkeypatch.setenv("APP_GIT_DIR", str(git))
    assert version_info()["version"] == f"{semver()}+99999999"
    monkeypatch.setenv("APP_REVISION", "abcdef0123456789")  # a deploy's revision wins over the git directory
    assert version_info()["revision"] == "abcdef01"


def test_version_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APP_REVISION", "abcdef0123456789")
    from app.web import app

    body = TestClient(app).get("/api/version").json()
    assert body["version"] == f"{semver()}+abcdef01"
    assert app.version == semver()


def test_licenses_list_installed_packages_with_their_license_text(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.web import app

    packages = TestClient(app).get("/api/licenses").json()["packages"]
    by_name = {p["name"].lower(): p for p in packages}
    assert "chatgpt-usage-dashboard" not in by_name  # our own package is not third party
    assert [p["name"].lower() for p in packages] == sorted(by_name)
    fastapi = by_name["fastapi"]
    assert fastapi["version"] and "MIT" in fastapi["license"]
    assert "Permission is hereby granted" in fastapi["text"]
    assert packages == third_party_licenses()
