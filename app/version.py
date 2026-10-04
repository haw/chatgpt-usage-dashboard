"""Version of the API.

The semantic version lives in pyproject.toml (the single place to bump). A deployed build
appends the first 8 characters of the commit it was built from as SemVer build metadata:
``1.0.0+6095c825``. The revision arrives in APP_REVISION, baked into the image at build time.
In local development there is no build step per commit, so APP_GIT_DIR points at the mounted
repository's .git directory instead and the current HEAD is read from it.
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


def git_head(git_dir: Path) -> str | None:
    """The commit HEAD points at, read straight from a .git directory (the image has no git)."""
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head or None  # detached HEAD: the hash itself
        ref = head.removeprefix("ref: ")
        if (git_dir / ref).is_file():
            return (git_dir / ref).read_text(encoding="utf-8").strip() or None
        for line in (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(f" {ref}"):
                return line.split(" ", 1)[0]
    except OSError:
        pass
    return None


def revision() -> str | None:
    value = os.getenv("APP_REVISION", "").strip()
    git_dir = os.getenv("APP_GIT_DIR", "").strip()
    if not value and git_dir:
        value = git_head(Path(git_dir)) or ""
    return value[:REVISION_LENGTH] or None


def version_info() -> dict[str, str | None]:
    base, rev = semver(), revision()
    return {"version": f"{base}+{rev}" if rev else base, "semver": base, "revision": rev}
