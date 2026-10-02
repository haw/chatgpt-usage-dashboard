# 独自検知器の置き場

このディレクトリはコンテナへ `/app/plugins` として読み取り専用でマウントされ、`PLUGINS_DIR`（既定 `./plugins`）として `sys.path` に追加されます。

1. `app.detectors.Detector` を継承したクラスを `@register` 付きで書く（`example_rule.py` 参照）。
2. `config/detectors.toml` に次を追加する。

```toml
[[detectors]]
id = "example_rule"
module = "example_rule"   # このディレクトリのファイル名（拡張子なし）
enabled = true
[detectors.params]
limit = 500000000
```

3. 次のリクエストから反映されます。読み込みに失敗した場合は画面のSIGNALSパネルと `GET /api/detectors` にエラーが表示され、他の検知器は動き続けます。

検知器が返す `Signal` の `severity` は `high`・`medium`・`info` のいずれかです。`DetectionContext` から `rows`（選択期間の日次行）、`day_kinds`（平日/休日）、`sensitivity`、`period_wide` を参照できます。判定値をユーザーの感度に連動させるには `sensitivity_params` に名前を挙げ、`self.tuned("名前", ctx)` で取得してください。
