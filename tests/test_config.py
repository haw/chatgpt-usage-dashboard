import pytest

from app.config import Settings


def test_s3_backend_requires_bucket(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    with pytest.raises(ValueError, match="S3_BUCKET"):
        Settings.from_env()


def test_s3_settings_are_normalized(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "S3")
    monkeypatch.setenv("S3_BUCKET", "usage-bucket")
    monkeypatch.setenv("S3_PREFIX", "/company/dashboard/")
    monkeypatch.setenv("AWS_REGION", "ap-northeast-1")
    settings = Settings.from_env()
    assert settings.storage_backend == "s3"
    assert settings.s3_bucket == "usage-bucket"
    assert settings.s3_prefix == "company/dashboard"
    assert settings.aws_region == "ap-northeast-1"
