from __future__ import annotations

from typing import Any

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.registry import register
from app.detectors.stats import period_history, robust_baseline, robust_score, rolling_history

PRODUCTS = ("chat", "codex", "work")
MIN_TOKENS_KEY = {"total": "min_tokens_total", "chat": "min_tokens_chat", "codex": "min_tokens_codex", "work": "min_tokens_work"}


@register
class TokenSpike(Detector):
    id = "token_spike"
    label = "トークン急増"
    description = (
        "全製品合計とChat・Codex・Workそれぞれの日次トークン量を、同じ区分（平日・休日）の直前期間の中央値とMADから"
        "計算した判定ライン（中央値 + z × MAD ÷ 0.6745）と比較します。異常と判定した日は以後の基準から除外します。"
        "期間指定時は選択期間全体を基準にします。"
    )
    group = "tokens"
    scopes = ("workspace", "individual")
    default_params = {
        "z": 3.5, "window_days": 28, "min_history": 5, "high_z": 7.0, "same_kind_only": True,
        "exclude_anomalies": True,
        "min_tokens_total": 0, "min_tokens_chat": 0, "min_tokens_codex": 0, "min_tokens_work": 0,
    }

    def _observations(self, ctx: DetectionContext, product: str) -> list[dict[str, Any]]:
        rows = ctx.rows_with("tokens")
        kinds = ctx.day_kinds if self.params["same_kind_only"] else None
        flagged: set[str] = set()
        result = []
        for index, row in enumerate(rows):
            center = mad = threshold = None
            if ctx.period_wide:
                history = period_history(rows, index, kinds)
            else:
                history = rolling_history(rows, index, self.params["window_days"],
                                          flagged if self.params["exclude_anomalies"] else None, kinds)
            if history and (ctx.period_wide or len(history) >= self.params["min_history"]):
                center, mad, threshold = robust_baseline(
                    [previous["tokens"][product] for previous in history], self.params["z"])
            value = row["tokens"][product]
            is_anomaly = (threshold is not None and value > center and value >= threshold
                          and value >= self.params[MIN_TOKENS_KEY[product]])
            if is_anomaly:
                flagged.add(row["date"])
            result.append({
                "date": row["date"], "value": value, "baseline": center, "mad": mad,
                "threshold": threshold, "history": len(history), "is_anomaly": is_anomaly,
                "kind": ctx.kind(row["date"]),
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
                kind_label = "休日" if point["kind"] == "holiday" else "平日"
                signals.append(Signal(
                    detector=self.id, type="token_spike",
                    severity="high" if score is not None and score >= self.params["high_z"] else "medium",
                    metric="総トークン" if product == "total" else "トークン",
                    product=None if product == "total" else product,
                    date=point["date"], value=point["value"],
                    baseline=round(point["baseline"], 1), threshold=round(point["threshold"], 1),
                    score=round(score, 2) if score is not None else None,
                    reason=(f"選択期間の{kind_label}中央値 {point['baseline']:,.1f} から大きく変化" if ctx.period_wide
                            else f"直前{point['history']}{kind_label}の中央値 {point['baseline']:,.1f} から大きく変化"),
                ))
        return signals

    def series(self, ctx: DetectionContext) -> list[dict[str, Any]]:
        return [{
            "date": point["date"], "value": point["value"], "kind": point["kind"],
            "baseline": round(point["baseline"], 1) if point["baseline"] is not None else None,
            "threshold": round(point["threshold"], 1) if point["threshold"] is not None else None,
            "is_anomaly": point["is_anomaly"],
        } for point in self._observations(ctx, "total")]
