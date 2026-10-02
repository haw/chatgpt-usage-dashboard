from __future__ import annotations

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.registry import register
from app.detectors.stats import period_history, robust_baseline, robust_score, rolling_history

PRODUCTS = ("chat", "codex", "work")


@register
class TokensPerUser(Detector):
    id = "tokens_per_user"
    label = "1人あたりトークン急増"
    description = (
        "製品ごとのトークン量をその製品のDAUで割った「1人あたりトークン」を、同じ区分の直前期間の中央値とMADと比較します。"
        "少人数で大量に消費するパターン（認証情報の流出、自動化による乱用など）を捉えます。DAUとトークンの両方がある日だけ判定します。"
    )
    group = "tokens"
    default_params = {
        "z": 3.5, "high_z": 6.0, "info_z": 2.0, "window_days": 28, "min_history": 5,
        "min_tokens_per_user": 5_000_000, "same_kind_only": True, "exclude_anomalies": True,
    }
    sensitivity_params = ("z", "high_z", "info_z", "min_tokens_per_user")

    @staticmethod
    def _per_user(row: dict, product: str) -> float | None:
        users = row["active_users"].get(product, 0)
        return row["tokens"][product] / users if users else None

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        kinds = ctx.day_kinds if self.params["same_kind_only"] else None
        for product in PRODUCTS:
            rows = [row for row in ctx.rows
                    if row.get("tokens") is not None and row.get("active_users") is not None
                    and self._per_user(row, product) is not None]
            flagged: set[str] = set()
            for index, row in enumerate(rows):
                if ctx.period_wide:
                    history = period_history(rows, index, kinds)
                else:
                    history = rolling_history(rows, index, self.params["window_days"],
                                              flagged if self.params["exclude_anomalies"] else None, kinds)
                if not history or (not ctx.period_wide and len(history) < self.params["min_history"]):
                    continue
                center, mad, threshold = robust_baseline(
                    [self._per_user(previous, product) for previous in history], self.tuned("z", ctx))
                value = self._per_user(row, product)
                score = robust_score(value, center, mad)
                if value <= center or value < self.tuned("min_tokens_per_user", ctx):
                    continue
                is_anomaly = value >= threshold
                if not is_anomaly and (score is None or score < self.tuned("info_z", ctx)):
                    continue
                if is_anomaly:
                    flagged.add(row["date"])
                kind_label = "休日" if ctx.kind(row["date"]) == "holiday" else "平日"
                signals.append(Signal(
                    detector=self.id, type="tokens_per_user_spike" if is_anomaly else "tokens_per_user_notable",
                    severity=("info" if not is_anomaly else
                              "high" if score is None or score >= self.tuned("high_z", ctx) else "medium"),
                    metric="1人あたりトークン", product=product, date=row["date"],
                    value=round(value), baseline=round(center), threshold=round(threshold),
                    score=round(score, 2) if score is not None else None,
                    reason=(f"{row['active_users'][product]}人で {row['tokens'][product]:,} tokens。"
                            f"{'選択期間' if ctx.period_wide else f'直前{len(history)}{kind_label}'}の1人あたり中央値 {center:,.0f} の"
                            f"{value / center:.1f}倍" if center else
                            f"{row['active_users'][product]}人で {row['tokens'][product]:,} tokens（基準期間は利用なし）"),
                ))
        return signals
