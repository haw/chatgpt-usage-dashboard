"""Detector registration, configuration loading and execution."""
from __future__ import annotations

import importlib
import logging
import sys
import tomllib
from pathlib import Path
from typing import Any

from app.detectors.base import DetectionContext, Detector, Signal

log = logging.getLogger(__name__)

_REGISTRY: dict[str, type[Detector]] = {}


def register(cls: type[Detector]) -> type[Detector]:
    """Class decorator: make a Detector subclass available under ``cls.id``."""
    if not cls.id:
        raise ValueError(f"{cls.__name__} must define a non-empty id")
    _REGISTRY[cls.id] = cls
    return cls


def registered() -> dict[str, type[Detector]]:
    _load_builtin()
    return dict(_REGISTRY)


def _load_builtin() -> None:
    importlib.import_module("app.detectors.builtin")


class DetectorSet:
    """The configured, instantiated detectors plus any configuration errors."""

    def __init__(self, detectors: list[Detector], errors: list[str]) -> None:
        self.detectors = detectors
        self.errors = errors

    def for_scope(self, scope: str) -> list[Detector]:
        return [detector for detector in self.detectors if scope in detector.scopes]

    def run(self, ctx: DetectionContext) -> list[dict[str, Any]]:
        signals: list[Signal] = []
        for detector in self.for_scope(ctx.scope):
            try:
                signals.extend(detector.detect(ctx))
            except Exception as exc:  # a broken plugin must not take the dashboard down
                log.exception("detector %s failed", detector.id)
                self.errors.append(f"{detector.id}: {exc}")
        order = {"high": 0, "medium": 1, "info": 2}
        signals.sort(key=lambda s: (s.date, -order[s.severity], s.metric), reverse=True)
        return [signal.to_dict() for signal in signals]

    def series(self, ctx: DetectionContext) -> list[dict[str, Any]]:
        for detector in self.for_scope(ctx.scope):
            result = detector.series(ctx)
            if result is not None:
                return result
        return []

    def describe(self) -> list[dict[str, Any]]:
        return [detector.describe() for detector in self.detectors]


def load_config(path: Path) -> list[dict[str, Any]]:
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    entries = document.get("detectors", [])
    if not isinstance(entries, list):
        raise ValueError("detectors must be an array of tables")
    return entries


def build_detector_set(config_path: Path | None, plugins_dir: Path | None = None) -> DetectorSet:
    """Instantiate detectors from config; without a config file use every builtin."""
    _load_builtin()
    errors: list[str] = []
    if plugins_dir and plugins_dir.is_dir() and str(plugins_dir) not in sys.path:
        sys.path.insert(0, str(plugins_dir))
    if config_path is None or not config_path.is_file():
        return DetectorSet([cls() for cls in _REGISTRY.values()], errors)
    try:
        entries = load_config(config_path)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"設定ファイルを読み込めません: {exc}")
        return DetectorSet([cls() for cls in _REGISTRY.values()], errors)
    detectors: list[Detector] = []
    seen: set[str] = set()
    for entry in entries:
        instance_id = str(entry.get("id", "")).strip()
        if not instance_id:
            errors.append("id のない検知器設定をスキップしました")
            continue
        if instance_id in seen:
            errors.append(f"{instance_id}: id が重複しています")
            continue
        seen.add(instance_id)
        if not entry.get("enabled", True):
            continue
        module = entry.get("module")
        if module:
            try:
                importlib.import_module(str(module))
            except Exception as exc:
                errors.append(f"{instance_id}: モジュール {module} を読み込めません ({exc})")
                continue
        class_id = str(entry.get("use", instance_id))
        cls = _REGISTRY.get(class_id)
        if cls is None:
            errors.append(f"{instance_id}: 検知器 {class_id} は登録されていません")
            continue
        try:
            detector = cls(entry.get("params") or {})
        except Exception as exc:
            errors.append(f"{instance_id}: {exc}")
            continue
        detector.id = instance_id  # instance id may differ from the class id via `use`
        detectors.append(detector)
    return DetectorSet(detectors, errors)
