import re

from fastapi.testclient import TestClient

from app.licenses import third_party_licenses
from app.version import semver, version_info

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def test_version_is_semver_and_appends_the_first_8_characters_of_the_revision(monkeypatch):
    assert SEMVER.match(semver())
    monkeypatch.delenv("APP_REVISION", raising=False)
    assert version_info() == {"version": semver(), "semver": semver(), "revision": None}
    monkeypatch.setenv("APP_REVISION", "6095c825695add27bb50b54ebd234978db309d45")
    assert version_info() == {"version": f"{semver()}+6095c825", "semver": semver(), "revision": "6095c825"}


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
