from __future__ import annotations

from statistics import median

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.registry import register


@register
class HolidayUsage(Detector):
    id = "holiday_usage"
    label = "休日の高利用"
    description = (
        "休日（週末・推定休日・手動設定）の総トークンが、平日の中央値に対して ratio 以上だった日を検出します。"
        "業務時間外の利用は不正の兆候になりやすいため、休日の基準データが足りない時期でも判定できる単純な比率で判定します。"
    )
    group = "tokens"
    default_params = {"ratio": 0.5, "min_workdays": 5, "min_tokens": 1_000_000, "severity": "medium"}
    sensitivity_params = ("ratio", "min_tokens")

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        rows = ctx.rows_with("tokens")
        workday_totals = [row["tokens"]["total"] for row in rows if ctx.kind(row["date"]) == "workday"]
        if len(workday_totals) < self.params["min_workdays"]:
            return []
        reference = float(median(workday_totals))
        threshold = max(reference * self.tuned("ratio", ctx), self.tuned("min_tokens", ctx))
        return [
            Signal(
                detector=self.id, type="holiday_usage", severity=self.params["severity"], metric="総トークン",
                date=row["date"], value=row["tokens"]["total"], baseline=round(reference), threshold=round(threshold),
                reason=f"休日に平日中央値 {reference:,.0f} の {row['tokens']['total'] / reference:.0%}",
            )
            for row in rows
            if ctx.kind(row["date"]) == "holiday" and row["tokens"]["total"] >= threshold
        ]
