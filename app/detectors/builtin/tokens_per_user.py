from __future__ import annotations

from statistics import median

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.builtin.token_spike import SHIFT_DEFAULTS, workspace_scale
from app.detectors.levels import Point, RatioScale, follow
from app.detectors.registry import register

PRODUCTS = ("chat", "codex", "work")


@register
class TokensPerUser(Detector):
    id = "tokens_per_user"
    label = "1人あたりトークン急増"
    description = (
        "製品ごとのトークン量をその製品のDAUで割った「1人あたりトークン」を、同じ区分の直前期間と倍率（対数）で比べます。"
        "少人数で大量に消費するパターン（認証情報の流出、自動化による乱用など）を捉えます。DAUとトークンの両方がある日だけ判定します。"
        "小さい量どうしの倍率を過大に扱わないよう、比べる両方に「平日1日分の総トークン中央値 × scale_share ÷ その製品の普段の人数」を足してから倍率を求めます。"
        "多めの日が続いて水準が変わったと判断したら、以後は新しい水準を基準にします（その知らせはトークン急増の「水準の変化」が担当します）。"
    )
    group = "tokens"
    default_params = {
        "z": 3.5, "high_z": 7.0, "info_z": 2.0, "window_days": 28, "min_history": 5,
        "min_tokens_per_user": 5_000_000, "same_kind_only": True, "exclude_anomalies": False,
        "scale_share": 1.0, "min_spread": 0.25, **SHIFT_DEFAULTS,
    }
    sensitivity_params = ("z", "high_z", "info_z", "min_tokens_per_user", "shift_limit")

    @staticmethod
    def _per_user(row: dict, product: str) -> float | None:
        users = row["active_users"].get(product, 0)
        return row["tokens"][product] / users if users else None

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        complete = [row for row in ctx.rows if row.get("tokens") is not None and row.get("active_users") is not None]
        z, floor = self.tuned("z", ctx), self.tuned("min_tokens_per_user", ctx)

        def is_spike(point: Point) -> bool:
            return point.value > point.baseline and point.value >= max(point.line(z), floor)

        for product in PRODUCTS:
            rows = [row for row in complete if self._per_user(row, product) is not None]
            by_date = {row["date"]: row for row in rows}

            def scale(index: int, window: list[dict]) -> float:
                # the workspace's typical workday, shared among the people who use this product on such a day
                kind = ctx.kind(rows[index]["date"])
                same = [row for row in window if ctx.kind(row["date"]) == kind] if self.params["same_kind_only"] else window
                usual_users = max(float(median(row["active_users"][product] for row in same or window)), 1.0) if window else 1.0
                period = [row for row in complete if window and window[0]["date"] <= row["date"] <= window[-1]["date"]]
                return workspace_scale(period, ctx.day_kinds) * self.params["scale_share"] / usual_users

            points, _ = follow(
                rows, lambda row: self._per_user(row, product), ctx.kind, RatioScale(self.params["min_spread"]),
                scale_of=scale, window_days=self.params["window_days"], min_history=self.params["min_history"],
                same_kind_only=self.params["same_kind_only"], period_wide=ctx.period_wide,
                excluded=is_spike if self.params["exclude_anomalies"] else None,
                shift_slack=self.params["shift_slack"], shift_limit=self.shift_limit(ctx),
                shift_cap=self.params["shift_cap"],
            )
            for point in points:
                if point.score is None or point.value <= point.baseline or point.value < floor:
                    continue
                threshold = point.line(z)
                is_anomaly = point.value >= threshold
                if not is_anomaly and point.score < self.tuned("info_z", ctx):
                    continue
                row = by_date[point.date]
                kind_label = "休日" if point.kind == "holiday" else "平日"
                signals.append(Signal(
                    detector=self.id, type="tokens_per_user_spike" if is_anomaly else "tokens_per_user_notable",
                    severity=("info" if not is_anomaly else
                              "high" if point.score >= self.tuned("high_z", ctx) else "medium"),
                    metric="1人あたりトークン", product=product, date=point.date,
                    value=round(point.value), baseline=round(point.baseline), threshold=round(threshold),
                    score=round(point.score, 2),
                    reason=(f"{row['active_users'][product]}人で {row['tokens'][product]:,} tokens。"
                            f"{'選択期間' if ctx.period_wide else f'直前{point.history}{kind_label}'}の1人あたり中央値 {point.baseline:,.0f} の"
                            f"{point.value / point.baseline:.1f}倍" if point.baseline >= 1 else
                            f"{row['active_users'][product]}人で {row['tokens'][product]:,} tokens（基準期間はほぼ利用なし）"),
                ))
        return signals
