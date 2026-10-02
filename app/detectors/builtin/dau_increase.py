from __future__ import annotations

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.registry import register
from app.detectors.stats import period_history, rolling_history

PRODUCTS = ("chat", "codex", "work")


@register
class DauIncrease(Detector):
    id = "dau_increase"
    label = "DAU新規最大"
    description = (
        "製品別のアクティブユーザー数が、同じ区分の直前期間の最大値を上回った日を検出します。"
        "小規模ワークスペースで不正なアカウントが1つ増えたような、+1人の変化を取りこぼさないための補助判定です。"
    )
    group = "dau"
    default_params = {"window_days": 28, "min_history": 5, "same_kind_only": True, "severity": "info"}

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        rows = ctx.rows_with("active_users")
        kinds = ctx.day_kinds if self.params["same_kind_only"] else None
        for product in PRODUCTS:
            for index, row in enumerate(rows):
                if ctx.period_wide:
                    history = [previous for previous in period_history(rows, index, kinds) if previous is not row]
                else:
                    history = rolling_history(rows, index, self.params["window_days"], None, kinds)
                if len(history) < self.params["min_history"]:
                    continue
                previous_max = max(previous["active_users"][product] for previous in history)
                value = row["active_users"][product]
                if value <= previous_max:
                    continue
                kind_label = "休日" if ctx.kind(row["date"]) == "holiday" else "平日"
                signals.append(Signal(
                    detector=self.id, type="dau_new_max", severity=self.params["severity"],
                    metric="DAU", product=product, date=row["date"], value=value, baseline=previous_max,
                    reason=f"直前{len(history)}{kind_label}の最大 {previous_max}人 を {value - previous_max}人 上回りました",
                ))
        return signals
