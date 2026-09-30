# ChatGPT Usage Dashboard

ChatGPTワークスペースのAnalytics APIから直近7日間の利用集計を手動取得し、ユーザー別の利用状況と異常兆候を確認するローカルダッシュボードです。

> このダッシュボードはAnalytics APIの集計データを扱います。監査ログ、会話本文、情報漏えいの検査を代替するものではありません。

## 必要なもの

- Docker Engine
- Docker Compose v2
- ChatGPTのworkspace-scoped Admin APIキー
- キーの `enterprise.analytics.usage.read` 権限
- ワークスペースでのDaily Usage Analytics API有効化

## セットアップ

```bash
cp .env.example .env
```

`.env` にAdminキーを設定します。

```dotenv
OPENAI_ADMIN_KEY=your-admin-key
```

認証済みChatGPT Admin APIリファレンスに記載されたURLが既定値と異なる場合だけ、次も変更します。

```dotenv
OPENAI_ANALYTICS_URL=https://api.chatgpt.com/v1/analytics/usage
```

## 利用方法

初回ビルド:

```bash
make build
```

過去7日分を手動収集:

```bash
make collect
```

収集範囲は「UTCで今日の0時を終端とした、完了済みの直近7日間」です。コマンドを再実行しても、同一の日付・ユーザー・製品の正規化レコードは重複しません。

ダッシュボード起動:

```bash
make up
```

[http://localhost:8000](http://localhost:8000) を開きます。停止は `make down`、ログ確認は `make logs` です。

任意の日数を収集する場合:

```bash
docker compose run --rm collector collect --days 14
```

## 保存データ

すべて `./data` に保存されます。

```text
data/
├── raw/<run-id>/page-0001.json  # APIの未加工応答
├── normalized/usage.jsonl       # 画面用の正規化データ
└── state/collection.json        # 最終収集状態
```

`.env` と `data/` の内容はGit管理対象外です。

## エラー時の確認

- `401` / `403`: キーがworkspace-scopedか、`enterprise.analytics.usage.read` があるか、APIが有効か確認
- `404`: 認証済みAdmin APIリファレンスでURLを確認し、`OPENAI_ANALYTICS_URL` を更新
- 「no rows matched」: `data/raw/<run-id>/` のフィールド構成を確認し、正規化処理のfixtureを更新

APIのURL・スキーマ・利用可否はOpenAI側で変更され得ます。公式の認証済みAdmin APIリファレンスを正としてください。

## テスト

```bash
make test
```

Adminキーやネットワークを使わず、fixtureに対してAPIクライアント、正規化、保存、異常判定を検証します。

## ドキュメント

- [MVP仕様書](docs/SPECIFICATION.md)
- [タスクリスト](docs/TASKS.md)

## ローカルコミット履歴

この実行環境では予約済みの `.git` が読み取り専用だったため、履歴は `.git-local` に保存しています。

```bash
./git-local.sh log --oneline
./git-local.sh status
```

通常のGit環境へ移した後は、標準の `.git` を利用できます。

## 本番化の方針

収集コンテナは同じ `python -m app collect --days 7` をECSタスクとして実行できます。本番化ではLocalStorageをS3実装へ差し替え、EventBridge Scheduler、Cognito認証、CloudFront/API Gatewayを追加します。
