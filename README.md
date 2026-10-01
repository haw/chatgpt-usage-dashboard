# ChatGPT Usage Dashboard

ChatGPT管理画面から出力した集計CSVをアップロードし、ワークスペース全体と指定した個人の利用推移・異常兆候を確認するローカルダッシュボードです。監査ログと会話本文は扱いません。

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
- 両方の折れ線グラフ上をドラッグして分析期間を指定
- 直前7日間の中央値・MADに基づくトークン急増とDAU急増／急減
- 実測値、中央値、判定ラインを重ねた総トークン異常分析グラフ
- 日次の元データ一覧
- 「全体分析」と「個人別分析」のタブ切り替え
- 個人を指定したトークンCSVの取込、ユーザー切り替え、日次推移、異常分析
- 個人ごとの5時間枠・週次枠への到達相当回数と声かけ目安
- 個人の日次・週次消費表と、行ごとの利用枠消費率・到達情報
- 全体・個人CSVを同じ画面で確認できる保存履歴、ファイルサイズ、SHA-256確認・コピー

製品別DAUには同じ利用者が重複する可能性があるため合算しません。KPIは「最新日の製品別最大DAU」を参考値として表示します。検出結果は統計的な兆候であり、不正利用を断定するものではありません。休日、全社イベント、製品展開などと合わせて確認してください。

選択期間はKPI、グラフ、日次表、アラートへ共通適用され、選択期間全体の中央値とMADで分析値を再計算します。全期間表示では各日の直前最大7日を基準にします。「期間をリセット」で取込済みの全期間へ戻せます。

異常分析グラフ見出しの `?` にマウスを重ねるか、キーボードでフォーカスすると判定条件を確認できます。

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

個人別分析では、管理画面で対象ユーザーを絞り込んだ「トークン消費量」CSVを1ファイルずつ取り込みます。列形式は上記と同じです。アップロード時に入力したユーザー名またはメールアドレスを個人の識別子として使用し、同じ識別子・日付の再取込は最新値へ置換します。

## 利用枠への到達回数目安

個人別分析では、Chatを除く `Codex + Work` のトークン数から5時間枠・週次枠への到達相当回数を推定します。初期値は公開された非公式な利用実測を参考にしています。

- 5時間参考上限: 26,300,000 tokens
- 週次参考上限: 173,000,000 tokens

5時間値は、[Business/Teamの5時間枠1回が週次枠の約15.2%だった公開測定](https://agentsroom.dev/usage-limits-tracker)を、[Business Standardの週次約1.73億トークンという公開実測](https://www.reddit.com/r/codex/comments/1w1613f/did_openai_just_quietly_cut_actual_codex_usage/)へ掛けた換算値です。設定画面から変更でき、「初期値にリセット」で上記へ戻せます。設定はブラウザの `localStorage` だけへ保存され、サーバー、S3、他の閲覧者とは共有されません。

5時間枠は各日の `Codex + Work` 合計を5時間参考上限で割った整数部分、週次枠は月曜始まりの各週合計を週次参考上限で割った整数部分を合計します。実際の5時間窓、ユーザー固有の週次リセット日時、モデルや推論量による重みはCSVに含まれないため、実際の制限到達回数ではありません。

個人別の日次表には、その日の `Codex + Work`、5時間参考上限に対する消費率、到達相当回数を表示します。週次表は月曜から日曜で集計し、製品別トークン、`Codex + Work`、週次参考上限に対する消費率、到達相当回数を表示します。80%以上は「接近」、100%以上は「到達相当」として色分けします。

右上の「保存データ履歴」はどちらの分析タブでも利用でき、同じ画面に全体データと個人データを分けて表示します。個人データでは取込日時、ユーザー、対象期間、日数、元CSVのサイズとSHA-256を確認できます。SHA-256はクリックでコピーできます。新しい取込ではユーザー情報をraw CSVと同じrunへ保存します。機能追加前のraw CSVでユーザーを特定できないものは「不明（旧データ）」と表示します。

## 保存データ

すべて `./data` に保存され、Git管理対象外です。

```text
data/
├── raw/<run-id>/active-users.csv
├── raw/<run-id>/tokens.csv
├── raw/<run-id>/individual-tokens.csv
├── raw/<run-id>/individual-import.json
├── normalized/workspace-usage.jsonl
├── normalized/individual-usage.jsonl
├── state/import.json
└── state/individual-import.json
```

同じ日付を再取込した場合、正規化データは最新値へ置換されます。元CSVはrunごとに保存されます。

## 保存先の切り替え

ローカル開発では既定で `LocalStorage` を使い、Docker Composeの `./data:/app/data` ボリュームへ保存します。

AWSでは次の環境変数をECSタスク定義などへ設定すると、同じデータ構造をS3へ保存します。

```env
STORAGE_BACKEND=s3
S3_BUCKET=your-private-bucket
S3_PREFIX=chatgpt-dashboard
AWS_REGION=ap-northeast-1
```

AWSアクセスキーは設定せず、ECSタスクロールを利用してください。タスクロールには、対象プレフィックスへの `s3:GetObject`、`s3:PutObject` と、対象バケットへの `s3:ListBucket` が必要です。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::your-private-bucket/chatgpt-dashboard/*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::your-private-bucket",
      "Condition": {
        "StringLike": {"s3:prefix": "chatgpt-dashboard/raw/*"}
      }
    }
  ]
}
```

S3上のキーは `raw/<run-id>/...`、`normalized/*.jsonl`、`state/*.json` です。正規化データの更新は読込後に全体を書き戻す方式のため、アップロード処理を同時実行せず、ECSタスク数は1にするか外部で直列化してください。

## テスト

```bash
docker compose run --rm --no-deps test
```

実データやネットワークを使わず、fixtureに対してCSV検証、冪等保存、異常判定、アップロードAPIを検証します。

## ドキュメント

- [MVP仕様書](docs/SPECIFICATION.md)
- [タスクリスト](docs/TASKS.md)

## 本番化の方針

本番では環境変数でS3保存へ切り替え、Cognito等の認証を追加します。取込頻度が低く速度要件も高くないため、常時起動のECS Serviceより、S3 + Lambda/API Gateway + CloudFrontのサーバーレス構成の方が一般に低コストです。CSVの定期取得手段を用意できた場合のみEventBridge Schedulerを追加します。
