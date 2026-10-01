# ChatGPT Usage Dashboard

ChatGPT管理画面から出力した集計CSVをアップロードし、ワークスペース全体の利用推移と異常兆候を確認するローカルダッシュボードです。個人情報、監査ログ、会話本文は扱いません。

## 起動と取込

必要なものはDocker EngineとDocker Compose v2です。Admin APIキーは不要です。

```bash
docker compose up -d --build dashboard
```

[http://localhost:8000](http://localhost:8000) を開き、同じ期間について管理画面から出力した次の2ファイルを選択します。

1. 1日のアクティブユーザー数CSV
2. トークン消費量CSV

「アップロードして分析」を押すと、既存データへ日付単位で上書き保存されます。停止は `docker compose down`、ログ確認は `docker compose logs -f dashboard` です。

## 表示と異常検知

- Chat、Codex、Work別の日次アクティブユーザー
- 製品別の日次トークンと期間集計
- 直前7日間の中央値・MADに基づくトークン急増とDAU急増／急減
- 日次の元データ一覧

製品別DAUには同じ利用者が重複する可能性があるため合算しません。KPIは「最新日の製品別最大DAU」を参考値として表示します。検出結果は統計的な兆候であり、不正利用を断定するものではありません。休日、全社イベント、製品展開などと合わせて確認してください。

## CSV要件

両ファイルとも次の列をこの順序で持つUTF-8 CSVを受け付けます。BOM付きUTF-8にも対応します。

```csv
Start Time,End Time,Chat,Codex,Work
2026-09-01,2026-09-02,5,3,1
```

- 数値は0以上の整数
- 日付の重複なし
- 両ファイルの日付集合が一致
- 1ファイル5 MiB以下

入力全体の検証に成功した後だけ保存するため、不正なCSVで既存の正規化データは変更されません。

## 保存データ

すべて `./data` に保存され、Git管理対象外です。

```text
data/
├── raw/<run-id>/active-users.csv
├── raw/<run-id>/tokens.csv
├── normalized/workspace-usage.jsonl
└── state/import.json
```

同じ日付を再取込した場合、正規化データは最新値へ置換されます。元CSVはrunごとに保存されます。

## テスト

```bash
docker compose run --rm --no-deps test
```

実データやネットワークを使わず、fixtureに対してCSV検証、冪等保存、異常判定、アップロードAPIを検証します。

## ドキュメント

- [MVP仕様書](docs/SPECIFICATION.md)
- [タスクリスト](docs/TASKS.md)

## 本番化の方針

本番ではLocalStorageをS3実装へ差し替え、Cognito等の認証を追加します。取込頻度が低く速度要件も高くないため、常時起動のECS Serviceより、S3 + Lambda/API Gateway + CloudFrontのサーバーレス構成の方が一般に低コストです。CSVの定期取得手段を用意できた場合のみEventBridge Schedulerを追加します。
