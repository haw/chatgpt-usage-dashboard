"""Licenses of the Python packages installed next to the API, read from their own metadata."""
from __future__ import annotations

import re
from functools import lru_cache
from importlib import metadata

from app.version import PACKAGE

LICENSE_FILE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS)([.\-_].*)?$", re.IGNORECASE)
MAX_TEXT = 200_000  # per package; the longest common texts (Apache-2.0 plus NOTICE) are a tenth of this


def _license_name(meta: metadata.PackageMetadata) -> str:
    expression = (meta.get("License-Expression") or "").strip()
    if expression:
        return expression
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    classifiers = [c for c in classifiers if c not in {"OSI Approved"}]
    if classifiers:
        return " / ".join(dict.fromkeys(classifiers))
    declared = (meta.get("License") or "").strip()
    # Older packages put the whole license text in this field; only a short value is a name.
    return declared if declared and "\n" not in declared and len(declared) <= 80 else ""


def _homepage(meta: metadata.PackageMetadata) -> str:
    urls = {}
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        urls[label.strip().lower()] = url.strip()
    for label in ("homepage", "source", "repository", "source code", "documentation"):
        if urls.get(label):
            return urls[label]
    return (meta.get("Home-page") or "").strip() or next(iter(urls.values()), "")


def _license_text(dist: metadata.Distribution) -> str:
    parts = []
    for file in dist.files or []:
        if ".dist-info" not in str(file) or not LICENSE_FILE.match(file.name):
            continue
        try:
            parts.append(file.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeDecodeError):
            continue
    return "\n\n".join(parts)[:MAX_TEXT]


@lru_cache(maxsize=1)
def third_party_licenses() -> list[dict[str, str]]:
    packages: dict[str, dict[str, str]] = {}
    for dist in metadata.distributions():
        meta = dist.metadata
        name = meta.get("Name")
        if not name or name.lower() == PACKAGE:
            continue
        packages[name.lower()] = {
            "name": name,
            "version": dist.version,
            "license": _license_name(meta),
            "homepage": _homepage(meta),
            "text": _license_text(dist),
        }
    return [packages[key] for key in sorted(packages)]
