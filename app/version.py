"""Version of the API.

The semantic version lives in pyproject.toml (the single place to bump). A deployed build
appends the first 8 characters of the commit it was built from as SemVer build metadata:
``1.0.0+6095c825``. The revision arrives in APP_REVISION, baked into the image at build time.
"""
from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from importlib import metadata
from pathlib import Path

PACKAGE = "chatgpt-usage-dashboard"
REVISION_LENGTH = 8


@lru_cache(maxsize=1)
def semver() -> str:
    try:
        return metadata.version(PACKAGE)
    except metadata.PackageNotFoundError:  # running from a checkout that was never installed
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]


def revision() -> str | None:
    value = os.getenv("APP_REVISION", "").strip()
    return value[:REVISION_LENGTH] or None


def version_info() -> dict[str, str | None]:
    base, rev = semver(), revision()
    return {"version": f"{base}+{rev}" if rev else base, "semver": base, "revision": rev}
