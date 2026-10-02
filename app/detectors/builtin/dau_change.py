from __future__ import annotations

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.registry import register
from app.detectors.stats import period_history, robust_baseline, robust_score, rolling_history

PRODUCTS = ("chat", "codex", "work")


@register
class DauChange(Detector):
    id = "dau_change"
    label = "DAU急増・急減"
    description = (
        "Chat・Codex・Workそれぞれの日次アクティブユーザー数を、同じ区分（平日・休日）の直前期間の中央値とMADによる"
        "ロバストZスコアで比較します。製品間では人数を合算しません。異常と判定した日は以後の基準から除外します。"
    )
    group = "dau"
    default_params = {
        "z": 3.5, "info_z": 2.0, "window_days": 28, "min_history": 5, "min_change": 2,
        "same_kind_only": True, "exclude_anomalies": True,
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
                center, mad, _ = robust_baseline([previous["active_users"][product] for previous in history])
                value = row["active_users"][product]
                score = robust_score(value, center, mad)
                ratio_outlier = mad == 0 and (
                    (center == 0 and value >= 2) or (center > 0 and (value >= center * 2 or value <= center * .5)))
                if abs(value - center) < self.tuned("min_change", ctx):
                    continue
                is_anomaly = (score is not None and abs(score) >= self.tuned("z", ctx)) or ratio_outlier
                if not is_anomaly and (score is None or abs(score) < self.tuned("info_z", ctx)):
                    continue
                if is_anomaly:
                    flagged.add(row["date"])
                kind_label = "休日" if ctx.kind(row["date"]) == "holiday" else "平日"
                signals.append(Signal(
                    detector=self.id, type=("dau_spike" if value > center else "dau_drop") + ("" if is_anomaly else "_notable"),
                    severity="medium" if is_anomaly else "info",
                    metric="DAU", product=product, date=row["date"], value=value, baseline=round(center, 1),
                    score=round(score, 2) if score is not None else None,
                    reason=(f"選択期間の{kind_label}中央値 {center:,.1f} から大きく変化" if ctx.period_wide
                            else f"直前{len(history)}{kind_label}の中央値 {center:,.1f} から大きく変化"),
                ))
        return signals
