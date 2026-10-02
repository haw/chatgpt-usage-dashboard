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
        "期間指定時は選択期間全体を基準にします。判定ライン未満でもZスコアが info_z 以上の上振れは「参考」として表示します。"
    )
    group = "tokens"
    scopes = ("workspace", "individual")
    default_params = {
        "z": 3.5, "window_days": 28, "min_history": 5, "high_z": 7.0, "info_z": 2.0, "same_kind_only": True,
        "exclude_anomalies": True,
        "min_tokens_total": 0, "min_tokens_chat": 0, "min_tokens_codex": 0, "min_tokens_work": 0,
    }
    sensitivity_params = ("z", "high_z", "info_z", "min_tokens_total", "min_tokens_chat", "min_tokens_codex", "min_tokens_work")

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
                    [previous["tokens"][product] for previous in history], self.tuned("z", ctx))
            value = row["tokens"][product]
            score = robust_score(value, center, mad) if threshold is not None else None
            floor = self.tuned(MIN_TOKENS_KEY[product], ctx)
            above_floor = value >= floor
            if threshold is not None:
                threshold = max(threshold, floor)  # the line the viewer sees is the effective one
            is_anomaly = threshold is not None and value > center and value >= threshold and above_floor
            is_notable = (not is_anomaly and above_floor and score is not None
                          and score >= self.tuned("info_z", ctx))
            if is_anomaly:
                flagged.add(row["date"])
            result.append({
                "date": row["date"], "value": value, "baseline": center, "mad": mad, "score": score,
                "threshold": threshold, "history": len(history), "is_anomaly": is_anomaly,
                "is_notable": is_notable, "kind": ctx.kind(row["date"]),
            })
        return result

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        products = ("total", *PRODUCTS) if ctx.scope == "workspace" else ("total",)
        for product in products:
            for point in self._observations(ctx, product):
                if not (point["is_anomaly"] or point["is_notable"]):
                    continue
                score = point["score"]
                kind_label = "休日" if point["kind"] == "holiday" else "平日"
                if not point["is_anomaly"]:
                    severity = "info"
                elif score is not None and score >= self.tuned("high_z", ctx):
                    severity = "high"
                else:
                    severity = "medium"
                signals.append(Signal(
                    detector=self.id, type="token_spike" if point["is_anomaly"] else "token_notable",
                    severity=severity,
                    metric="総トークン" if product == "total" else "トークン",
                    product=None if product == "total" else product,
                    date=point["date"], value=point["value"],
                    baseline=round(point["baseline"], 1), threshold=round(point["threshold"], 1),
                    score=round(score, 2) if score is not None else None,
                    reason=((f"選択期間の{kind_label}中央値 {point['baseline']:,.1f} " if ctx.period_wide
                             else f"直前{point['history']}{kind_label}の中央値 {point['baseline']:,.1f} ")
                            + ("から大きく変化" if point["is_anomaly"] else "より上振れ（判定ライン未満）")),
                ))
        return signals

    def series(self, ctx: DetectionContext) -> list[dict[str, Any]]:
        return [{
            "date": point["date"], "value": point["value"], "kind": point["kind"],
            "baseline": round(point["baseline"], 1) if point["baseline"] is not None else None,
            "threshold": round(point["threshold"], 1) if point["threshold"] is not None else None,
            "is_anomaly": point["is_anomaly"], "is_notable": point["is_notable"],
            "score": round(point["score"], 2) if point["score"] is not None else None,
        } for point in self._observations(ctx, "total")]
