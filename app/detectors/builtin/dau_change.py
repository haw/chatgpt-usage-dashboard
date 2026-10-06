from __future__ import annotations

from app.detectors.base import DetectionContext, Detector, Signal
from app.detectors.levels import CountScale, Point, follow
from app.detectors.registry import register

PRODUCTS = ("chat", "codex", "work")


@register
class DauChange(Detector):
    id = "dau_change"
    label = "DAU急増・急減"
    description = (
        "Chat・Codex・Workそれぞれの日次アクティブユーザー数を、同じ区分（平日・休日）の直前期間の中央値とばらつき（MAD）で"
        "比較します。ばらつきは min_spread 人を下限にします（毎日同じ人数が続いたあとの±1〜2人を異常としないため）。"
        "製品間では人数を合算しません。1日ごとの判定ラインは超えなくても普段より多い日が続いた場合は、"
        "日々の上振れを積み上げて「水準の変化」として始まりの日に1回だけ知らせ、以後は新しい人数を基準にします"
        "（閲覧者が「続く変化も判定」を有効にしたときだけ）。"
    )
    group = "dau"
    default_params = {
        "z": 3.5, "info_z": 2.0, "window_days": 28, "min_history": 5, "min_change": 2, "min_spread": 1.0,
        "same_kind_only": True, "exclude_anomalies": False,
        "shift_limit": 5.0, "shift_slack": 0.5, "shift_cap": 3.0,
    }
    sensitivity_params = ("z", "info_z", "min_change", "shift_limit")

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        rows = ctx.rows_with("active_users")
        z, min_change = self.tuned("z", ctx), self.tuned("min_change", ctx)

        def is_anomalous(point: Point) -> bool:
            return abs(point.value - point.baseline) >= min_change and abs(point.score) >= z

        for product in PRODUCTS:
            points, shifts = follow(
                rows, lambda row: row["active_users"][product], ctx.kind, CountScale(self.params["min_spread"]),
                window_days=self.params["window_days"], min_history=self.params["min_history"],
                same_kind_only=self.params["same_kind_only"], period_wide=ctx.period_wide,
                excluded=is_anomalous if self.params["exclude_anomalies"] else None,
                shift_slack=self.params["shift_slack"], shift_limit=self.shift_limit(ctx),
                shift_cap=self.params["shift_cap"],
            )
            for point in points:
                if point.score is None or abs(point.value - point.baseline) < min_change:
                    continue
                is_anomaly = abs(point.score) >= z
                if not is_anomaly and abs(point.score) < self.tuned("info_z", ctx):
                    continue
                kind_label = "休日" if point.kind == "holiday" else "平日"
                signals.append(Signal(
                    detector=self.id,
                    type=("dau_spike" if point.value > point.baseline else "dau_drop") + ("" if is_anomaly else "_notable"),
                    severity="medium" if is_anomaly else "info",
                    metric="DAU", product=product, date=point.date, value=point.value, baseline=round(point.baseline, 1),
                    score=round(point.score, 2),
                    reason=(f"選択期間の{kind_label}中央値 {point.baseline:,.1f} から大きく変化" if ctx.period_wide
                            else f"直前{point.history}{kind_label}の中央値 {point.baseline:,.1f} から大きく変化"),
                ))
            for shift in shifts:
                if shift.after - shift.before < min_change:  # same floor as a single day's change
                    continue
                kind_label = "休日" if shift.kind == "holiday" else "平日"
                signals.append(Signal(
                    detector=self.id, type="dau_level_shift", severity="medium", metric="DAU", product=product,
                    date=shift.start, value=round(shift.after, 1), baseline=round(shift.before, 1),
                    score=round(shift.score, 2), span_days=shift.days,
                    reason=(f"この日から{kind_label}{shift.days}日続けて多く、{shift.confirmed} に水準の変化と判定。"
                            f"1日あたり {shift.before:,.1f}人 → {shift.after:,.1f}人"),
                ))
        return signals
