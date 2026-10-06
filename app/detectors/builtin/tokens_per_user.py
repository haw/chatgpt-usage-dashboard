from __future__ import annotations

from statistics import median

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.builtin.token_spike import workspace_scale
from app.detectors.registry import register
from app.detectors.stats import period_history, ratio_baseline, ratio_score, ratio_threshold, rolling_history

PRODUCTS = ("chat", "codex", "work")


@register
class TokensPerUser(Detector):
    id = "tokens_per_user"
    label = "1人あたりトークン急増"
    description = (
        "製品ごとのトークン量をその製品のDAUで割った「1人あたりトークン」を、同じ区分の直前期間と倍率（対数）で比べます。"
        "少人数で大量に消費するパターン（認証情報の流出、自動化による乱用など）を捉えます。DAUとトークンの両方がある日だけ判定します。"
        "小さい量どうしの倍率を過大に扱わないよう、比べる両方に「平日1日分の総トークン中央値 × scale_share ÷ その製品の普段の人数」を足してから倍率を求めます。"
    )
    group = "tokens"
    default_params = {
        "z": 3.5, "high_z": 7.0, "info_z": 2.0, "window_days": 28, "min_history": 5,
        "min_tokens_per_user": 5_000_000, "same_kind_only": True, "exclude_anomalies": False,
        "scale_share": 1.0, "min_spread": 0.25,
    }
    sensitivity_params = ("z", "high_z", "info_z", "min_tokens_per_user")

    @staticmethod
    def _per_user(row: dict, product: str) -> float | None:
        users = row["active_users"].get(product, 0)
        return row["tokens"][product] / users if users else None

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        kinds = ctx.day_kinds if self.params["same_kind_only"] else None
        complete = [row for row in ctx.rows if row.get("tokens") is not None and row.get("active_users") is not None]
        position = {row["date"]: index for index, row in enumerate(complete)}
        for product in PRODUCTS:
            rows = [row for row in complete if self._per_user(row, product) is not None]
            flagged: set[str] = set()
            for index, row in enumerate(rows):
                if ctx.period_wide:
                    history = period_history(rows, index, kinds)
                    reference = complete
                else:
                    excluded = flagged if self.params["exclude_anomalies"] else None
                    history = rolling_history(rows, index, self.params["window_days"], excluded, kinds)
                    reference = rolling_history(complete, position[row["date"]], self.params["window_days"], excluded)
                if not history or (not ctx.period_wide and len(history) < self.params["min_history"]):
                    continue
                usual_users = max(float(median(previous["active_users"][product] for previous in history)), 1.0)
                scale = max(workspace_scale(reference, ctx.day_kinds) * self.params["scale_share"] / usual_users, 1.0)
                center, spread = ratio_baseline(
                    [self._per_user(previous, product) for previous in history], scale, self.params["min_spread"])
                value = self._per_user(row, product)
                score = ratio_score(value, center, spread, scale)
                threshold = ratio_threshold(center, spread, scale, self.tuned("z", ctx))
                if value <= center or value < self.tuned("min_tokens_per_user", ctx):
                    continue
                is_anomaly = value >= threshold
                if not is_anomaly and score < self.tuned("info_z", ctx):
                    continue
                if is_anomaly:
                    flagged.add(row["date"])
                kind_label = "休日" if ctx.kind(row["date"]) == "holiday" else "平日"
                signals.append(Signal(
                    detector=self.id, type="tokens_per_user_spike" if is_anomaly else "tokens_per_user_notable",
                    severity=("info" if not is_anomaly else
                              "high" if score >= self.tuned("high_z", ctx) else "medium"),
                    metric="1人あたりトークン", product=product, date=row["date"],
                    value=round(value), baseline=round(center), threshold=round(threshold),
                    score=round(score, 2),
                    reason=(f"{row['active_users'][product]}人で {row['tokens'][product]:,} tokens。"
                            f"{'選択期間' if ctx.period_wide else f'直前{len(history)}{kind_label}'}の1人あたり中央値 {center:,.0f} の"
                            f"{value / center:.1f}倍" if center >= 1 else
                            f"{row['active_users'][product]}人で {row['tokens'][product]:,} tokens（基準期間はほぼ利用なし）"),
                ))
        return signals
