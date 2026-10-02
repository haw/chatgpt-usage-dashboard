"""Detector plugin contract.

A detector inspects daily usage rows and returns signals. Detectors are
registered by id, configured from ``config/detectors.toml`` and can be
added, disabled or replaced without touching the dashboard code.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

SEVERITIES = ("high", "medium", "info")


@dataclass
class Signal:
    """One detected observation. ``type`` is the detector-specific kind."""

    detector: str
    type: str
    severity: str
    metric: str
    date: str
    value: float
    product: str | None = None
    baseline: float | None = None
    threshold: float | None = None
    score: float | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}: {self.severity!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DetectionContext:
    """Rows are sorted by date and already limited to the selected period.

    ``period_wide`` is set when the viewer selected a period; detectors then
    compare each day against the whole selected period instead of a rolling
    window. ``day_kinds`` maps each date to ``"workday"`` or ``"holiday"``.
    """

    rows: list[dict[str, Any]]
    scope: str = "workspace"
    period_wide: bool = False
    day_kinds: dict[str, str] = field(default_factory=dict)
    today: str | None = None

    def rows_with(self, group: str) -> list[dict[str, Any]]:
        return [row for row in self.rows if row.get(group) is not None]

    def kind(self, day: str) -> str:
        return self.day_kinds.get(day, "workday")


class Detector:
    """Base class. Subclasses set the class attributes and implement ``detect``."""

    id: ClassVar[str] = ""
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""
    group: ClassVar[str] = "tokens"
    scopes: ClassVar[tuple[str, ...]] = ("workspace",)
    default_params: ClassVar[dict[str, Any]] = {}

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        unknown = set(params or {}) - set(self.default_params)
        if unknown:
            raise ValueError(f"{self.id}: unknown parameters {sorted(unknown)}")
        self.params = {**self.default_params, **(params or {})}

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        raise NotImplementedError

    def series(self, ctx: DetectionContext) -> list[dict[str, Any]] | None:
        """Optional per-day baseline/threshold series for charting."""
        return None

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "group": self.group,
            "scopes": list(self.scopes),
            "params": dict(self.params),
        }
