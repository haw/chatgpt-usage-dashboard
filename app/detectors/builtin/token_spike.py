from __future__ import annotations

from typing import Any

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.registry import register
from app.detectors.stats import robust_baseline, robust_score, rolling_history

PRODUCTS = ("chat", "codex", "work")


@register
class TokenSpike(Detector):
    id = "token_spike"
    label = "トークン急増"
    description = (
        "全製品合計とChat・Codex・Workそれぞれの日次トークン量を、直前期間の中央値とMADから"
        "計算した判定ライン（中央値 + z × MAD ÷ 0.6745）と比較します。期間指定時は選択期間全体を基準にします。"
    )
    group = "tokens"
    scopes = ("workspace", "individual")
    default_params = {"z": 3.5, "window_days": 7, "min_history": 5, "high_z": 7.0}

    def _observations(self, ctx: DetectionContext, product: str) -> list[dict[str, Any]]:
        rows = ctx.rows_with("tokens")
        period: tuple[float, float, float] | None = None
        if ctx.period_wide and rows:
            period = robust_baseline([row["tokens"][product] for row in rows], self.params["z"])
        result = []
        for index, row in enumerate(rows):
            center = mad = threshold = None
            history_size = 0
            if period:
                center, mad, threshold = period
                history_size = len(rows)
            else:
                history = rolling_history(rows, index, self.params["window_days"])
                if len(history) >= self.params["min_history"]:
                    center, mad, threshold = robust_baseline(
                        [previous["tokens"][product] for previous in history], self.params["z"])
                    history_size = len(history)
            value = row["tokens"][product]
            result.append({
                "date": row["date"], "value": value, "baseline": center, "mad": mad,
                "threshold": threshold, "history": history_size,
                "is_anomaly": threshold is not None and value > (center or 0) and value >= threshold,
            })
        return result

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        products = ("total", *PRODUCTS) if ctx.scope == "workspace" else ("total",)
        for product in products:
            for point in self._observations(ctx, product):
                if not point["is_anomaly"]:
                    continue
                score = robust_score(point["value"], point["baseline"], point["mad"])
                signals.append(Signal(
                    detector=self.id, type="token_spike",
                    severity="high" if score is not None and score >= self.params["high_z"] else "medium",
                    metric="総トークン" if product == "total" else "トークン",
                    product=None if product == "total" else product,
                    date=point["date"], value=point["value"],
                    baseline=round(point["baseline"], 1), threshold=round(point["threshold"], 1),
                    score=round(score, 2) if score is not None else None,
                    reason=(f"選択期間の中央値 {point['baseline']:,.1f} から大きく変化" if ctx.period_wide
                            else f"直前{point['history']}日の中央値 {point['baseline']:,.1f} から大きく変化"),
                ))
        return signals

    def series(self, ctx: DetectionContext) -> list[dict[str, Any]]:
        return [{
            "date": point["date"], "value": point["value"],
            "baseline": round(point["baseline"], 1) if point["baseline"] is not None else None,
            "threshold": round(point["threshold"], 1) if point["threshold"] is not None else None,
            "is_anomaly": point["threshold"] is not None and point["value"] >= point["threshold"],
        } for point in self._observations(ctx, "total")]
