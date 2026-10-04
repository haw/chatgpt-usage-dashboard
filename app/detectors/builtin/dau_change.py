from __future__ import annotations

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.registry import register
from app.detectors.stats import count_baseline, period_history, rolling_history

PRODUCTS = ("chat", "codex", "work")


@register
class DauChange(Detector):
    id = "dau_change"
    label = "DAU急増・急減"
    description = (
        "Chat・Codex・Workそれぞれの日次アクティブユーザー数を、同じ区分（平日・休日）の直前期間の中央値とばらつき（MAD）で"
        "比較します。ばらつきは min_spread 人を下限にします（毎日同じ人数が続いたあとの±1〜2人を異常としないため）。"
        "製品間では人数を合算しません。"
    )
    group = "dau"
    default_params = {
        "z": 3.5, "info_z": 2.0, "window_days": 28, "min_history": 5, "min_change": 2, "min_spread": 1.0,
        "same_kind_only": True, "exclude_anomalies": False,
    }
    sensitivity_params = ("z", "info_z", "min_change")

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        rows = ctx.rows_with("active_users")
        kinds = ctx.day_kinds if self.params["same_kind_only"] else None
        for product in PRODUCTS:
            flagged: set[str] = set()
            for index, row in enumerate(rows):
                if ctx.period_wide:
                    history = period_history(rows, index, kinds)
                else:
                    history = rolling_history(rows, index, self.params["window_days"],
                                              flagged if self.params["exclude_anomalies"] else None, kinds)
                if not history or (not ctx.period_wide and len(history) < self.params["min_history"]):
                    continue
                center, spread = count_baseline(
                    [previous["active_users"][product] for previous in history], self.params["min_spread"])
                value = row["active_users"][product]
                score = (value - center) / spread
                if abs(value - center) < self.tuned("min_change", ctx):
                    continue
                is_anomaly = abs(score) >= self.tuned("z", ctx)
                if not is_anomaly and abs(score) < self.tuned("info_z", ctx):
                    continue
                if is_anomaly:
                    flagged.add(row["date"])
                kind_label = "休日" if ctx.kind(row["date"]) == "holiday" else "平日"
                signals.append(Signal(
                    detector=self.id, type=("dau_spike" if value > center else "dau_drop") + ("" if is_anomaly else "_notable"),
                    severity="medium" if is_anomaly else "info",
                    metric="DAU", product=product, date=row["date"], value=value, baseline=round(center, 1),
                    score=round(score, 2),
                    reason=(f"選択期間の{kind_label}中央値 {center:,.1f} から大きく変化" if ctx.period_wide
                            else f"直前{len(history)}{kind_label}の中央値 {center:,.1f} から大きく変化"),
                ))
        return signals
