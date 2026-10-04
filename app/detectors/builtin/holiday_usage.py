from __future__ import annotations

from statistics import median

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.registry import register
from app.detectors.stats import rolling_history


@register
class HolidayUsage(Detector):
    id = "holiday_usage"
    label = "休日の高利用"
    description = (
        "休日（週末・推定休日・手動設定）の総トークンが、直前期間の平日の中央値に対して ratio 以上だった日を検出します。"
        "休日どうしの比較（トークン急増）は休日の実績がたまるまで判定できないため、休日が平日並みに使われた日を"
        "単純な比率で補います。期間指定時は選択期間の平日全体を基準にします。"
    )
    group = "tokens"
    default_params = {"ratio": 1.5, "window_days": 28, "min_workdays": 5, "min_tokens": 1_000_000, "severity": "medium"}
    sensitivity_params = ("ratio", "min_tokens")

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        rows = ctx.rows_with("tokens")
        signals: list[Signal] = []
        for index, row in enumerate(rows):
            if ctx.kind(row["date"]) != "holiday":
                continue
            history = rows if ctx.period_wide else rolling_history(rows, index, self.params["window_days"])
            workday_totals = [previous["tokens"]["total"] for previous in history if ctx.kind(previous["date"]) == "workday"]
            if len(workday_totals) < self.params["min_workdays"]:
                continue
            reference = float(median(workday_totals))
            threshold = max(reference * self.tuned("ratio", ctx), self.tuned("min_tokens", ctx))
            if row["tokens"]["total"] < threshold:
                continue
            signals.append(Signal(
                detector=self.id, type="holiday_usage", severity=self.params["severity"], metric="総トークン",
                date=row["date"], value=row["tokens"]["total"], baseline=round(reference), threshold=round(threshold),
                reason=(f"休日に{'選択期間' if ctx.period_wide else f'直前{len(workday_totals)}平日'}の中央値 {reference:,.0f} の "
                        f"{row['tokens']['total'] / reference:.0%}" if reference else "休日に利用（基準期間の平日は利用なし）"),
            ))
        return signals
