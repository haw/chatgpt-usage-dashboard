"""独自検知器のサンプル。config/detectors.toml で module = "example_rule" を指定すると有効になります。

必要なのは Detector を継承し、@register を付け、detect() で Signal のリストを返すことだけです。
"""
from app.detectors import DetectionContext, Detector, Signal, register


@register
class ExampleRule(Detector):
    id = "example_rule"
    label = "固定上限超過（サンプル）"
    description = "総トークンが params.limit を超えた日を検出します。"
    group = "tokens"
    scopes = ("workspace",)
    default_params = {"limit": 500_000_000}

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        return [
            Signal(
                detector=self.id, type="fixed_limit", severity="high", metric="総トークン",
                date=row["date"], value=row["tokens"]["total"], threshold=self.params["limit"],
                reason=f"固定上限 {self.params['limit']:,} を超過",
            )
            for row in ctx.rows_with("tokens")
            if row["tokens"]["total"] > self.params["limit"]
        ]
