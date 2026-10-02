from __future__ import annotations

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.registry import register
from app.detectors.stats import robust_baseline, robust_score, rolling_history

PRODUCTS = ("chat", "codex", "work")


@register
class DauChange(Detector):
    id = "dau_change"
    label = "DAU急増・急減"
    description = (
        "Chat・Codex・Workそれぞれの日次アクティブユーザー数を、直前期間の中央値とMADによる"
        "ロバストZスコアで比較します。製品間では人数を合算しません。"
    )
    group = "dau"
    default_params = {"z": 3.5, "window_days": 7, "min_history": 5, "min_change": 2}

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        rows = ctx.rows_with("active_users")
        for product in PRODUCTS:
            for index, row in enumerate(rows):
                history = rows if ctx.period_wide else rolling_history(rows, index, self.params["window_days"])
                if (not ctx.period_wide and len(history) < self.params["min_history"]) or not history:
                    continue
                center, mad, _ = robust_baseline([previous["active_users"][product] for previous in history])
                value = row["active_users"][product]
                score = robust_score(value, center, mad)
                ratio_outlier = mad == 0 and (
                    (center == 0 and value >= 2) or (center > 0 and (value >= center * 2 or value <= center * .5)))
                if abs(value - center) < self.params["min_change"]:
                    continue
                if not ((score is not None and abs(score) >= self.params["z"]) or ratio_outlier):
                    continue
                signals.append(Signal(
                    detector=self.id, type="dau_spike" if value > center else "dau_drop", severity="medium",
                    metric="DAU", product=product, date=row["date"], value=value, baseline=round(center, 1),
                    score=round(score, 2) if score is not None else None,
                    reason=(f"選択期間の中央値 {center:,.1f} から大きく変化" if ctx.period_wide
                            else f"直前{len(history)}日の中央値 {center:,.1f} から大きく変化"),
                ))
        return signals
