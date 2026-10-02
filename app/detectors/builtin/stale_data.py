from __future__ import annotations

from datetime import date

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.registry import register


@register
class StaleData(Detector):
    id = "stale_data"
    label = "データ途絶"
    description = (
        "最後に取り込んだ日からの経過日数が max_age_days を超えると警告します。"
        "データが止まると検知も止まるため、監視が続いているかを確認するための判定です。"
    )
    group = "operations"
    scopes = ("workspace",)
    default_params = {"max_age_days": 3, "severity": "info"}

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        if ctx.period_wide or not ctx.rows:
            return []  # a narrowed period says nothing about freshness
        latest = ctx.rows[-1]["date"]
        today = date.fromisoformat(ctx.today) if ctx.today else date.today()
        age = (today - date.fromisoformat(latest)).days
        if age <= self.params["max_age_days"]:
            return []
        return [Signal(
            detector=self.id, type="stale_data", severity=self.params["severity"], metric="取込状況",
            date=latest, value=age, threshold=self.params["max_age_days"],
            reason=f"最終データ日 {latest} から {age}日 経過。新しいJSONを取り込んでください",
        )]
