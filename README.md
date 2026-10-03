# ChatGPT Usage Dashboard

ChatGPT管理画面から出力した集計JSONをアップロードし、ワークスペース全体と指定した個人の利用推移・異常兆候を確認するローカルダッシュボードです。監査ログと会話本文は扱いません。

## 構成

- `frontend/`: 画面（React + TypeScript + MUI + ECharts、Vite）。本番では S3 + CloudFront から配信します。
- `app/`: API（FastAPI）。取込・保存・判定・ログインだけを担当し、画面は配信しません。API ドキュメントは http://localhost:8000/api/docs（Swagger UI）と `/api/redoc`、仕様は `/api/openapi.json`（ログイン必須モードでは社内アカウントでのログイン後に閲覧可）（`FRONTEND_DIST` を指定した場合のみビルド済みの画面を同じコンテナから配信）。
- `config/detectors.toml`、`plugins/`: 判定の設定と独自検知器。
- `infra/terraform/`: 本番環境（AWS）。

## 起動と取込

必要なものはDocker EngineとDocker Compose v2です。Admin APIキーは不要です。

```bash
docker compose up -d --build dashboard frontend
```

API（8000）と画面の開発サーバー（5180。`/api` などは API へプロキシ）が起動します。[http://localhost:5180](http://localhost:5180) を開くと「推移」画面が出ます。`frontend/` を編集すると即時に反映されます（初回は `npm ci` のため1〜2分かかります。進捗は `docker compose logs -f frontend`）。Docker を使わない場合は `cd frontend && npm ci && npm run dev`。

上部の「アップロードして分析」ボタンからJSONを1つずつ、または2つまとめて選びます。DAU・トークンは独立しており、1つだけでもすぐグラフ・分析に反映されます。期間が異なるファイルも取り込めます。2つまとめて選ぶ場合、選択順は問いません。

1. 1日のアクティブユーザー数JSON
2. トークンJSON

アップロードした指標だけを日付単位で更新し、もう一方の指標は保持します。未登録の指標は「—」で表示し、平均・異常判定から除外します。停止は `docker compose down`、ログ確認は `docker compose logs -f dashboard` です。

コンテナは非rootユーザーで動作します。ローカルの `data/` をホストユーザーの所有に合わせるため、Composeは既定でUID/GID `1000:1000` を使います。異なる場合は起動前に `LOCAL_UID` と `LOCAL_GID` を設定してください（例: `LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose up -d --build dashboard`）。

ローカルの保存データだけを削除する場合は、プロジェクトルートで `make clear-data` を実行し、確認に `y` と入力します。`./data` の中身だけをホストユーザー権限で削除し、S3には接続しません。`data/.gitkeep` は残ります。

## 画面構成

各画面にはパスがあり（`/` 推移、`/insights` インサイト、`/insights/2026-09-22` のように日付を付けると観点パネルを開いた状態、`/individual` 個人別、`/settings` 取込と設定）、ブラウザの戻る・進むで画面と観点パネルを行き来できます。

画面は「答える問い」ごとに4つに分かれています（調査レポート [docs/research/異常検知アラートのUX原則.md](docs/research/異常検知アラートのUX原則.md) に基づく構成です）。

| 画面 | 問い | 内容 |
|---|---|---|
| インサイト | 今日、見るべき日はあるか | 最終データ日と取込状態、「優先して確認」「次に確認」「参考」の3段に分けた日の順位表。各日は観点ごとの1文（実測・普段・倍率・判定ライン）と、「確認済みにする」「グラフで見る」（観点ごとに、同じ区分の直前28日の点・中央値・判定ラインをどう超えたかを示す小グラフをフローティング表示） |
| 推移（起動時） | 最近の傾向はどうか | JSON取込、KPI（右端の「インサイト（優先）」をクリックするとインサイトへ）、製品別DAU・トークンの折れ線、ドラッグによる期間指定、判定ライン付きの総トークン異常分析グラフ、感度スライダー、日次表（区分・兆候件数つき） |
| 個人別 | この人の使い方はどうか | 個人別トークンJSONの取込、推移、異常分析、利用枠到達の目安 |
| 取込と設定 | 判定の調整は要るか | 休日・平日の手動設定一覧、判定に使っている観点とパラメータ、個人別の参考上限 |

### インサイトの順位

反応した観点（独立した検知器）の数を主に、その日に始まった変化か前日からの継続か、初めて見るパターンかを加味して並べ、上位5日までを「優先して確認」、それ以外の非参考を「次に確認」、参考のみ・説明済みの日を「参考」にします。順位は感度の設定に影響されません。「確認済みにする」でその日は参考へ下がり（「未確認に戻す」で戻せます）、記録はサーバー側（`data/normalized/dispositions.jsonl` またはS3）に追記保存されます。データが3日以上更新されていない場合は観点ではなく画面上部の警告として表示します。

製品別DAUには同じ利用者が重複する可能性があるため合算しません。表示は統計的な兆候であり、不正利用を断定するものではありません。閾値はどこまでも目安で、最終判断は複数の兆候・休日・全社イベント・製品展開などを合わせて行う分析担当者に委ねる設計です。

### 検知器

判定は `config/detectors.toml` で設定する検知器の集まりです。組み込みは次の6つで、`GET /api/detectors` で一覧と現在のパラメータを確認できます。

| id | 内容 | 既定の重要度 |
|---|---|---|
| `token_spike` | 総トークン・製品別トークンが同じ区分（平日/休日）の直前28日の中央値+MAD判定ライン以上 | 中（Zが大きいと高） |
| `tokens_per_user` | 製品別トークン÷DAU（1人あたり）が同じ区分の基準から急増。少人数で大量消費する不正の典型を捉える | 高/中 |
| `dau_change` | 製品別DAUがロバストZスコアで急増・急減（2人以上の差） | 中 |
| `dau_increase` | 製品別の利用者数が同じ区分の直前28日で最多になった（+1人でも） | 参考 |
| `holiday_usage` | 休日の総トークンが平日中央値の50%以上 | 中 |
| `stale_data` | 最終データ日から3日以上経過（監視が止まっていないかの確認） | 参考 |

ロバストZスコアを使う検知器は、判定ライン未満でもZ≥2の上振れを「参考」として出します。異常と判定した日は以後の基準期間から除外し、基準が汚染されて連続する異常を見逃すことを防ぎます。同じ区分の基準が5日に満たない日は「判定保留」として件数を表示します。

### 平日・休日の区分

土日は休日、平日はその日のDAU（DAUがなければトークン）が平日中央値の半分以下なら休日と推定します（祝日カレンダーは持ちません）。「推移」の日次表の区分をクリックすると手動で切り替えられ、設定はブラウザの `localStorage` にだけ保存され、リクエスト時に `holidays`・`workdays` として送られます。「取込と設定」で一覧と解除ができます。

### 感度

「推移」の異常分析グラフにある感度（低・やや低・標準・やや高・高）は、各検知器の判定値（Zスコア、最小量、比率）をまとめて割る探索用の設定です。動かすと判定ラインが即座に引き直され、「標準 → 高: +3日（新たに…）」のように出なくなった日・新たに出た日を示します。ブラウザごとに保存され、サーバー側の設定や「検出された日」の順位は変わりません。

選択期間はKPI、グラフ、日次表、アラートへ共通適用され、選択期間全体（同じ区分の日）の中央値とMADで分析値を再計算します。「期間をリセット」で取込済みの全期間へ戻せます。各見出しの `?` にマウスを重ねるか、キーボードでフォーカスすると判定条件を確認できます。

### 検知器の追加・削除・差し替え

`config/detectors.toml` はコンテナへ読み取り専用でマウントされ、編集は次のリクエストから反映されます（再ビルド不要）。

- 無効化: 該当の `enabled = false`
- パラメータ変更: `[detectors.params]` の値を編集（省略した項目は既定値）
- 同じ検知器を別設定で併用: `id` を変えて `use = "token_spike"` のようにクラスを指定
- 独自検知器: `plugins/` に `app.detectors.Detector` を継承したクラスを `@register` 付きで置き、設定に `module = "ファイル名"` を書く。サンプルは `plugins/example_rule.py`

設定の誤りはその検知器だけをスキップし、画面とAPI（`detector_errors`）に理由を表示します。

## AIによる読み取り（試験導入）

インサイトの「グラフで見る」パネルに「読み取り」枠があり、「AIに問い合わせる」を押すとその日の判定を文章で説明します（押すまでは何も表示されません。初回はモデルの取得に時間がかかります）。AIはブラウザ内で動き、判定に使った数値（JSON）だけを渡すため、データは外部へ送られません。

使うモデルと、AIに渡すプロンプト（システムプロンプトと指示文。指示文の `{facts}` にその日の判定データが入ります。「統計の知識がない人向け」「統計に詳しい人向け」のプリセットから読み込んで編集できます）は「取込と設定」で変更でき、ブラウザに保存されます（既定は Qwen。試験では Gemini Nano より説明の内容が良好でした）。

- Chrome 内蔵の Gemini Nano（Prompt API）。Chrome 148 以降は標準で、それ以前は `chrome://flags/#optimization-guide-on-device-model`（BypassPerfRequirement）と `chrome://flags/#prompt-api-for-gemini-nano` を有効にし、初回にモデルを取得します（空き容量 22GB 以上、GPU 4GB 超または RAM 16GB＋4コア）。
- WebLLM（Qwen2.5-1.5B-Instruct、WebGPU、約1GB、初回のみ取得しブラウザにキャッシュ）。
- どちらも無い場合はボタンが無効になります。

AIの文は判断の材料であり、数値で確認してください。

## ログイン（Google Workspace）

既定（`AUTH_MODE=none`）はログインなしで、ローカル専用です。本番では `AUTH_MODE=google` にすると、社内の他システム（TARO、日報）と同じ Google Workspace アカウントでの OpenID Connect ログインが必須になります。

```env
AUTH_MODE=google
GOOGLE_CLIENT_ID=...          # Google Cloud の OAuth クライアント（ウェブ アプリケーション）
GOOGLE_CLIENT_SECRET=...
SESSION_SECRET=...            # セッション Cookie の署名鍵（長いランダム文字列）
AUTH_ALLOWED_DOMAINS=haw.co.jp  # カンマ区切り。これ以外のドメインのアカウントは 403
BASE_URL=https://dashboard.example.com  # プロキシ配下で外部 URL が内部と異なるとき
```

- Google Cloud 側で「承認済みのリダイレクト URI」に `<BASE_URL>/auth/callback` を登録します（ローカル開発は `http://localhost:5180/auth/callback`。開発サーバーのプロキシは Host ヘッダを通すので、コールバック先は 5180 になります）。組織内のみのクライアントにしておくと、他組織のアカウントは Google 側で弾かれます。
- `/health`・`/login/google`・`/auth/callback`・`/logout`・`/api/me` 以外の API はすべてログイン必須で、未ログインなら 401 を返します。ログイン画面（`/login`）は React 側のページです。
- 「Google でログイン」で `/login/google` → Google のアカウント選択（毎回表示）→ `/auth/callback` → 画面に戻ります。許可外ドメインや OAuth のエラーはログイン画面にメッセージとして表示します。
- ログイン後、画面右上にメールアドレスと「ログアウト」が表示されます。ログアウトはこのアプリのセッションだけを終了し（Google は `end_session_endpoint` を持たないため）、ログイン画面に戻ります。セッションは12時間で切れます。

## JSON要件

管理画面のAnalytics JSONを受け付けます。アクティブユーザーJSONは `chart_key` が `active-users`、トークンJSONは `tokens` である必要があります。どちらも `series` にChat・Codex・Workが各1系列あり、`rows` に日別データを含む形式です。取込例:

```json
{
  "chart_key": "tokens",
  "series": [
    {"column": "Chat"}, {"column": "Codex"}, {"column": "Work"}
  ],
  "rows": [
    {"Start Time": "2026-09-03", "End Time": "2026-09-04", "Chat": 100, "Codex": 200, "Work": 50}
  ]
}
```

取込時はJSON構文、`chart_key`、系列、開始・終了日、日付の重複、0以上の整数を検証します。日付は `YYYY-MM-DD` とISO形式の日時を受け付けます。1ファイル5 MiB以下です。不正なJSONで既存の分析データは変更されません。`summary` は部分集計を含む場合があるため、日次分析には `rows` だけを使います。

画面ではJSONを受け付けます。旧CSV形式も既存の取込APIとの互換性のため、2ファイルを同じ形式に揃えた場合に限りサーバー側で受け付けます。

個人別分析では、対象ユーザーで絞り込んだ `chart_key: "tokens"` のJSONを1ファイルずつ取り込みます。入力したユーザー名またはメールアドレスを識別子に使い、同じユーザー・日付の再取込は最新値へ置換します。

## 利用枠への到達回数目安

個人別分析では、Chatを除く `Codex + Work` のトークン数から5時間枠・週次枠への到達相当回数を推定します。初期値は公開された非公式な利用実測を参考にしています。

- 5時間参考上限: 26,300,000 tokens
- 週次参考上限: 173,000,000 tokens

5時間値は、[Business/Teamの5時間枠1回が週次枠の約15.2%だった公開測定](https://agentsroom.dev/usage-limits-tracker)を、[Business Standardの週次約1.73億トークンという公開実測](https://www.reddit.com/r/codex/comments/1w1613f/did_openai_just_quietly_cut_actual_codex_usage/)へ掛けた換算値です。設定画面から変更でき、「初期値にリセット」で上記へ戻せます。設定はブラウザの `localStorage` だけへ保存され、サーバー、S3、他の閲覧者とは共有されません。

5時間枠は各日の `Codex + Work` 合計を5時間参考上限で割った整数部分、週次枠は月曜始まりの各週合計を週次参考上限で割った整数部分を合計します。実際の5時間窓、ユーザー固有の週次リセット日時、モデルや推論量による重みは日次JSONに含まれないため、実際の制限到達回数ではありません。

個人別の日次表には、その日の `Codex + Work`、5時間参考上限に対する消費率、到達相当回数を表示します。週次表は月曜から日曜で集計し、製品別トークン、`Codex + Work`、週次参考上限に対する消費率、到達相当回数を表示します。80%以上は「接近」、100%以上は「到達相当」として色分けします。

右上の「保存データ履歴」はどちらの分析タブでも利用でき、同じ画面に全体データと個人データを分けて表示します。個人データでは取込日時、ユーザー、対象期間、日数、元JSONのサイズとSHA-256を確認できます。SHA-256はクリックでコピーできます。以前のCSV取込履歴も表示します。ユーザー情報を特定できない旧データは「不明（旧データ）」と表示します。

## 保存データ

すべて `./data` に保存され、Git管理対象外です。

```text
data/
├── raw/<run-id>/active-users.json
├── raw/<run-id>/tokens.json
├── raw/<run-id>/individual-tokens.json
├── raw/<run-id>/individual-import.json
├── normalized/workspace-usage.jsonl
├── normalized/individual-usage.jsonl
├── state/import.json
└── state/individual-import.json
```

同じ日付を再取込した場合、正規化データは最新値へ置換されます。元JSONはrunごとに保存されます。既存のCSV取込履歴も読み込みます。

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
docker compose run --rm --no-deps test        # API: pytest
cd frontend && npm run typecheck && npm test  # 画面: 型検査と、実 API に接続するコンポーネントテスト（BACKEND=http://localhost:8001 で向き先を指定）
```

API のテストは実データやネットワークを使わず、合成 fixture に対して JSON 検証、冪等保存、異常判定、アップロード API、ログインを検証します。画面のテストは CI では AUTH_MODE=none の API を起動して合成 fixture を投入してから実行します。

## ドキュメント

- [MVP仕様書](docs/SPECIFICATION.md)
- [タスクリスト](docs/TASKS.md)

## 本番化の方針

本番では環境変数でS3保存へ切り替え、Cognito等の認証を追加します。取込頻度が低く速度要件も高くないため、常時起動のECS Serviceより、S3 + Lambda/API Gateway + CloudFrontのサーバーレス構成の方が一般に低コストです。定期取得手段を用意できた場合のみEventBridge Schedulerを追加します。
