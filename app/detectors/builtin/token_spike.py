from __future__ import annotations

from statistics import median
from typing import Any

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.levels import LevelShift, Point, RatioScale, follow
from app.detectors.registry import register

PRODUCTS = ("chat", "codex", "work")
MIN_TOKENS_KEY = {"total": "min_tokens_total", "chat": "min_tokens_chat", "codex": "min_tokens_codex", "work": "min_tokens_work"}
SHIFT_DEFAULTS = {"shift_limit": 5.0, "shift_slack": 0.5, "shift_cap": 3.0}


def workspace_scale(history: list[dict[str, Any]], day_kinds: dict[str, str]) -> float:
    """Typical daily total of the baseline period: its workdays, or every day when it has none."""
    workdays = [row["tokens"]["total"] for row in history if day_kinds.get(row["date"], "workday") == "workday"]
    totals = workdays or [row["tokens"]["total"] for row in history]
    return float(median(totals)) if totals else 0.0


@register
class TokenSpike(Detector):
    id = "token_spike"
    label = "トークン急増"
    description = (
        "全製品合計とChat・Codex・Workそれぞれの日次トークン量を、同じ区分（平日・休日）の直前期間と「倍率」で比べます。"
        "トークン量は日によって数割〜数倍ふれるのが普通なので、差ではなく対数（倍率）で中央値とばらつき（MAD）を求め、"
        "普段のばらつきの z 倍を超えて多い日を検出します。小さい量どうしの倍率を過大に扱わないよう、"
        "比べる両方に「直前期間の平日1日分（総トークン中央値 × scale_share）」を足してから倍率を求めます。"
        "1日ごとの判定ラインは超えなくても多めの日が続いた場合は、日々の上振れを積み上げて「水準の変化」として"
        "始まりの日に1回だけ知らせ、以後はその新しい水準を基準にします（shift_limit を 0 にすると無効）。"
        "期間指定時は選択期間全体を基準にします。判定ライン未満でも info_z 以上の上振れは「参考」として表示します。"
    )
    group = "tokens"
    scopes = ("workspace", "individual")
    default_params = {
        "z": 3.5, "window_days": 28, "min_history": 5, "high_z": 7.0, "info_z": 2.0, "same_kind_only": True,
        "exclude_anomalies": False, "scale_share": 1.0, "min_spread": 0.25, **SHIFT_DEFAULTS,
        "min_tokens_total": 0, "min_tokens_chat": 0, "min_tokens_codex": 0, "min_tokens_work": 0,
    }
    sensitivity_params = ("z", "high_z", "info_z", "shift_limit",
                          "min_tokens_total", "min_tokens_chat", "min_tokens_codex", "min_tokens_work")

    def _follow(self, ctx: DetectionContext, product: str) -> tuple[list[Point], list[LevelShift]]:
        z, floor = self.tuned("z", ctx), self.tuned(MIN_TOKENS_KEY[product], ctx)

        def is_spike(point: Point) -> bool:
            return point.value > point.baseline and point.value >= max(point.line(z), floor)

        return follow(
            ctx.rows_with("tokens"), lambda row: row["tokens"][product], ctx.kind,
            RatioScale(self.params["min_spread"]),
            scale_of=lambda index, history: workspace_scale(history, ctx.day_kinds) * self.params["scale_share"],
            window_days=self.params["window_days"], min_history=self.params["min_history"],
            same_kind_only=self.params["same_kind_only"],
            period_wide=ctx.period_wide, excluded=is_spike if self.params["exclude_anomalies"] else None,
            shift_slack=self.params["shift_slack"], shift_limit=self.tuned("shift_limit", ctx),
            shift_cap=self.params["shift_cap"],
        )

    def _observations(self, ctx: DetectionContext, product: str) -> tuple[list[dict[str, Any]], list[LevelShift]]:
        points, shifts = self._follow(ctx, product)
        floor = self.tuned(MIN_TOKENS_KEY[product], ctx)
        result = []
        for point in points:
            threshold = None
            if point.score is not None:
                threshold = max(point.line(self.tuned("z", ctx)), floor)  # the line the viewer sees is the effective one
            above_floor = point.value >= floor
            is_anomaly = threshold is not None and point.value > point.baseline and point.value >= threshold and above_floor
            is_notable = (not is_anomaly and above_floor and point.score is not None
                          and point.score >= self.tuned("info_z", ctx))
            result.append({
                "date": point.date, "value": point.value, "baseline": point.baseline, "spread": point.spread,
                "score": point.score, "threshold": threshold, "history": point.history, "is_anomaly": is_anomaly,
                "is_notable": is_notable, "kind": point.kind,
            })
        return result, shifts

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        products = ("total", *PRODUCTS) if ctx.scope == "workspace" else ("total",)
        for product in products:
            observations, shifts = self._observations(ctx, product)
            metric = "総トークン" if product == "total" else "トークン"
            for point in observations:
                if not (point["is_anomaly"] or point["is_notable"]):
                    continue
                score = point["score"]
                kind_label = "休日" if point["kind"] == "holiday" else "平日"
                if not point["is_anomaly"]:
                    severity = "info"
                elif score >= self.tuned("high_z", ctx):
                    severity = "high"
                else:
                    severity = "medium"
                signals.append(Signal(
                    detector=self.id, type="token_spike" if point["is_anomaly"] else "token_notable",
                    severity=severity, metric=metric, product=None if product == "total" else product,
                    date=point["date"], value=point["value"],
                    baseline=round(point["baseline"], 1), threshold=round(point["threshold"], 1),
                    score=round(score, 2),
                    reason=((f"選択期間の{kind_label}中央値 {point['baseline']:,.1f} " if ctx.period_wide
                             else f"直前{point['history']}{kind_label}の中央値 {point['baseline']:,.1f} ")
                            + ("から大きく変化" if point["is_anomaly"] else "より上振れ（判定ライン未満）")),
                ))
            floor = self.tuned(MIN_TOKENS_KEY[product], ctx)
            for shift in shifts:
                if shift.after < floor:
                    continue
                kind_label = "休日" if shift.kind == "holiday" else "平日"
                signals.append(Signal(
                    detector=self.id, type="level_shift",
                    severity="high" if shift.score >= self.tuned("z", ctx) else "medium",
                    metric=metric, product=None if product == "total" else product,
                    date=shift.start, value=round(shift.after), baseline=round(shift.before, 1),
                    score=round(shift.score, 2), span_days=shift.days,
                    reason=(f"この日から{kind_label}{shift.days}日続けて多く、{shift.confirmed} に水準の変化と判定。"
                            f"1日あたり {shift.before:,.0f} → {shift.after:,.0f}"),
                ))
        return signals

    def series(self, ctx: DetectionContext) -> list[dict[str, Any]]:
        return [{
            "date": point["date"], "value": point["value"], "kind": point["kind"],
            "baseline": round(point["baseline"], 1) if point["baseline"] is not None else None,
            "threshold": round(point["threshold"], 1) if point["threshold"] is not None else None,
            "is_anomaly": point["is_anomaly"], "is_notable": point["is_notable"],
            "score": round(point["score"], 2) if point["score"] is not None else None,
        } for point in self._observations(ctx, "total")[0]]
