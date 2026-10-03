# 本番環境（Terraform）

本番環境は HAW の AWS に Terraform で構築します。アプリの配信は AWS 側（CodeBuild）が GitHub のリポジトリを取りに行って行います。構成・対象・使い方・判断事項はこのファイルにまとめます（アプリ本体の説明は [リポジトリの README](../../README.md)）。

## 構成

```
利用者 ── HTTPS ── CloudFront（*.cloudfront.net または独自ドメイン）
                   ├─ /api/*, /login/google, /auth/*, /logout, /health → API Gateway（HTTP API）→ VPC リンク → Fargate タスク 1（API、ECR の画像）
                   └─ それ以外（React の画面）                          → S3（ビルド成果物、OAC で非公開）
API の環境変数: STORAGE_BACKEND=s3 / AUTH_MODE=google / 許可ドメイン / SESSION_SECURE
シークレット（Google OAuth の ID・Secret、セッション鍵）: SSM Parameter Store（SecureString）
データ: S3 バケット（raw・正規化 JSONL・状態・確認済み記録）
配信: main への push → CodeBuild がリポジトリを取得 → API 画像を ECR へ push し ECS サービスを再デプロイ、画面を S3 へ同期 → CloudFront 無効化
```

| 管理するもの | ファイル |
|---|---|
| データ用 S3 バケット | `main.tf` |
| 配信: GitHub への接続（CodeConnections）、CodeBuild プロジェクトと push の Webhook、その実行ロール（ECR push / S3 同期 / CloudFront 無効化 / ECS サービス更新）、ビルドログ | `cicd.tf` |
| ECR リポジトリ（直近 10 画像を保持） | `ecr.tf` |
| SSM Parameter Store のシークレット 3 つ（値は Terraform 管理外） | `secrets.tf` |
| API Gateway（HTTP API、既定ルートを API へ転送、流量制限）、VPC リンクとその SG、Cloud Map（タスクの居場所の登録） | `api_gateway.tf` |
| ECS クラスター、タスク定義、サービス（0.25 vCPU / 0.5 GB の Fargate タスク 1 固定、コンテナのヘルスチェック `/health`、ログ保持 90 日）、実行・タスクロール、タスクの SG、CloudFront だけが知る秘密ヘッダーの値 | `ecs.tf` |
| 画面用 S3 バケット、CloudFront（2 オリジン、API パスはキャッシュなし、SPA 用と転送ヘッダ用の CloudFront Functions） | `frontend.tf` |
| 独自ドメイン（任意）: ACM 証明書（us-east-1、DNS 検証）と Route53 の別名レコード | `domain.tf` |

管理しないもの: VPC とサブネット（`vpc_id`・`task_subnet_ids` で既存のものを指定）、GitHub 接続の承認（コンソールで 1 回）、Google Cloud の OAuth クライアント、ローカル開発環境（Docker Compose）。ロードバランサーは使いません。

### 実行基盤の選び方
- App Runner は 2026 年 3 月末にメンテナンスモード入りが発表され、4 月 30 日以降は新規顧客が利用できないため使いません。
- AWS の後継案内は ECS Express Mode ですが、ALB の固定費（月 $18〜20）が乗ります。
- 社内の共有 ALB への相乗りも試しましたが、接続元が限定されていて CloudFront から届きません。制限を緩めると同じ ALB に乗る他のアプリの防御も弱まるため、使わないことにしました。
- そこで **API Gateway（HTTP API）から VPC リンク経由で Fargate タスクに直接つなぐ**形にしました。ロードバランサーが不要で、API Gateway はリクエスト数課金（$1.29 / 100 万件）なので、この規模では月数円〜数十円です。タスクの居場所は Cloud Map に登録され、API Gateway がそこを引きます。
- API Gateway の制約: リクエスト本体は 10MB まで（アプリの上限は 5MB）、応答は 30 秒まで。

### 証明書について
- CloudFront は既定ドメイン（`*.cloudfront.net`）なら AWS 管理の証明書付きです。API Gateway のエンドポイントも AWS 管理の証明書付きなので、API 側で証明書を用意する必要はありません。
- 独自ドメイン（`domain_name` と `route53_zone_id` を指定）のときだけ ACM 証明書を発行します。無料で、Route53 の DNS 検証により自動で発行・更新されます。

### 設計上の要点
- **タスクは 1 つ**: 正規化データは取込時に全体を書き戻す方式のため、`desired_count = 1` とし、デプロイ時も 2 タスクが同時に動かないよう「止めてから起動」（最小 0% / 最大 100%）にしています。入れ替え中は数十秒ほど API が応答しません。
- **画像の更新**: タスク定義は `latest` を参照し、CodeBuild が push 後に `update-service --force-new-deployment` で入れ替えます。
- **CloudFront を迂回できない**: API Gateway のエンドポイント自体は公開されていますが、CloudFront がリクエストに付ける秘密ヘッダー（`x-origin-verify`）を API が照合し、付いていないリクエストは 403 で拒否します（`ORIGIN_VERIFY_SECRET`。`/health` だけは対象外）。タスクの SG も VPC リンクからの 8000 番しか許可しません。
- **NAT なし**: タスクはパブリックサブネットでパブリック IP を持ち、ECR・SSM・ログへの到達に NAT を使いません（受信は VPC リンクからのみ）。
- **同一オリジン**: 画面と API を同じ CloudFront ドメインで配信するので、セッション Cookie と OAuth のリダイレクトは開発時と同じ仕組みで動きます。API には公開 URL を `BASE_URL` として渡し、OAuth のコールバック URL はそこから作ります。
- **公開範囲**: 社外からも開けます。守りは Google ログイン（許可ドメイン限定）です。API Gateway には流量制限（毎秒 50 件）を掛けています。
- **SPA のパス**: 拡張子のないパス（`/insights/2026-09-22` など）は CloudFront Function が `index.html` に書き換えます。API パスには適用しません。
- **キャッシュ**: ハッシュ付きの `assets/*` は 1 年、`index.html` は `no-cache`。API はキャッシュしません。

## 前提

- Docker と Docker Compose だけ。Terraform と AWS CLI はホストに入れず、専用コンテナ（`terraform` サービス。Terraform 1.13.4 + AWS CLI v2、[Dockerfile](Dockerfile)）で実行します。
- HAW の AWS アカウントの IAM ユーザーのアクセスキー。キーはこのコンテナ専用の Docker ボリューム（`aws_credentials`）だけに保存します。ホストの `~/.aws` はマウントしないので、ホスト側にキーは残らず、コンテナからホストの他のプロファイルも見えません。リポジトリ内のファイル（`.env`、`*.tfvars` など）には書かないでください。
- state 用 S3 バケットは `make tf-bootstrap` が作ります（「初回だけ行うこと」参照）。
- GitHub の `haw` 組織に AWS の連携アプリ（AWS Connector for GitHub）を入れられる権限（組織のオーナー）。初回の接続承認で 1 回だけ使います。

## コマンド（make）

Terraform と AWS CLI はすべて `make` 経由で、コンテナの中で実行します。リポジトリのルートで打ちます。コンテナの作業ディレクトリは `infra/terraform`、実行ユーザーはホストの UID です（`.terraform/` などが root 所有になりません）。

| コマンド | すること |
|---|---|
| `make tf-build` | コンテナのイメージを作る（初回とバージョン更新時） |
| `make aws-configure` | 初回だけ。アクセスキー ID / シークレット / リージョン `ap-northeast-1` を入力（コンテナ専用ボリュームに保存） |
| `make aws-whoami` | どのアカウント・ユーザーで操作しているか確認 |
| `make tf-bootstrap` | 初回だけ。state バケットを作り `envs/prod.backend.hcl` を書き出す |
| `make tf-init` | `terraform init -backend-config=envs/prod.backend.hcl` |
| `make tf-plan` | `terraform plan -var-file=envs/prod.tfvars` |
| `make tf-apply` | `terraform apply -var-file=envs/prod.tfvars` |
| `make tf-output` | `terraform output`。1 つだけ取り出すときは `make -s tf-output ARGS="-raw ecr_repository"` |
| `make tf-first-image` | 初回だけ。ECR と GitHub 接続（承認待ち）だけ作り、API の画像を 1 度 push |
| `make deploy` / `make deploy-status` | 配信を手動で開始 / 直近 5 回の配信結果を表示 |
| `make tf-fmt` / `make tf-check` | 整形 / CI と同じ検査（`fmt -check`・`validate`。AWS 認証不要） |
| `make tf ARGS="…"` / `make aws ARGS="…"` | 上にない terraform / aws のコマンド（例: `make tf ARGS="state list"`） |
| `make tf-shell` | コンテナのシェルに入る（terraform、aws、jq、openssl が使えます） |

- 追加の引数は `ARGS` で渡します（例: `make tf-plan ARGS="-target=aws_ecs_service.api"`）。
- 環境は `ENV` で切り替えます（既定は `prod`。例: `make tf-plan ENV=staging`）。
- キーを消すときは `docker volume rm chatgpt_dashboard_aws_credentials`（`docker compose down -v` でも消えます）。入れ替えるときは `make aws-configure` をもう一度実行します。

## 使い方

```bash
cp infra/terraform/envs/prod.tfvars.example infra/terraform/envs/prod.tfvars   # 許可ドメイン、ドメイン、VPC・サブネットなどを編集
make tf-init
make tf-plan
make tf-apply
make tf-output
```

### 初回だけ行うこと（順番どおりに）

1. **コンテナと認証**: `make tf-build`、`make aws-configure`、`make aws-whoami` でアカウントを確認。
2. **state バケット**を作る: `make tf-bootstrap`。このプロジェクト専用のバケット `chatgpt-usage-dashboard-terraform-state-<アカウント ID>`（バージョニング・暗号化・パブリックアクセスブロック・TLS 必須）を [bootstrap/](bootstrap/main.tf) の Terraform で作り、`envs/prod.backend.hcl` を書き出します。作成内容が表示されるので `yes` で確定します。再実行しても変更は出ません。
   - bootstrap 自身の state はローカルの `bootstrap/terraform.tfstate`（git 管理外）です。なくしても `make tf ARGS="-chdir=bootstrap import aws_s3_bucket.state <バケット名>"` で戻せます。
3. **設定ファイル**: `envs/prod.tfvars.example` を `envs/prod.tfvars` にコピーし、ドメイン、ホストゾーン ID、タスクを置く VPC とパブリックサブネット（2 つ以上、別々のアベイラビリティゾーン）を記入。サブネットの調べ方は example のコメントにあります。続けて `make tf-init`。
4. **ECR と GitHub 接続を先に作る**: `make tf-first-image`。ECS サービスは作成時に画像が必要なので、ECR と GitHub 接続だけ適用し（`yes` で確定）、ホストの `docker` で API の画像を作って 1 度 push します。以後は CodeBuild が push します。
5. **GitHub 接続を承認**（コンソールでの手作業はここだけ）: AWS コンソールの「デベロッパー用ツール」→「設定」→「接続」で `chatgpt-dashboard-prod`（状態: 保留中）を開き、「保留中の接続を更新」→ GitHub の `haw` 組織に AWS Connector for GitHub を入れて（導入済みなら選んで）このリポジトリへのアクセスを許可します。状態が「利用可能」になれば完了です。確認: `make aws ARGS="codeconnections list-connections --query Connections[].[ConnectionName,ConnectionStatus] --output table"`。
   - 承認済みの接続がすでにあり、このリポジトリを読めるなら、`envs/prod.tfvars` の `github_connection_arn` にその ARN を書けばこの手順は不要です。
6. **全体を適用**: `make tf-plan` で内容を確認し、`make tf-apply`（ACM の DNS 検証を含むので数分かかります）。接続が未承認のままだと CodeBuild 側（Webhook の登録）で失敗するはずなので、手順 5 を先に済ませます。
7. **シークレットを設定**（Terraform は値を上書きしません）。値を打ち込むので `make tf-shell` でコンテナに入って実行します:
   ```bash
   P=/chatgpt-usage-dashboard/prod
   aws ssm put-parameter --name $P/GOOGLE_CLIENT_ID     --type SecureString --overwrite --value '<クライアント ID>'
   aws ssm put-parameter --name $P/GOOGLE_CLIENT_SECRET --type SecureString --overwrite --value '<クライアント シークレット>'
   aws ssm put-parameter --name $P/SESSION_SECRET       --type SecureString --overwrite --value "$(openssl rand -hex 32)"
   aws ecs update-service --cluster $(terraform output -raw ecs_cluster) --service $(terraform output -raw ecs_service) --force-new-deployment   # 新しい値でタスクを入れ替える
   ```
8. **Google Cloud** の OAuth クライアントに `make -s tf-output ARGS="-raw oauth_redirect_uri"` の値を「承認済みのリダイレクト URI」として追加。
9. **最初の配信**: `make deploy` で CodeBuild を 1 回動かし（画面が S3 に入ります）、`make deploy-status` で `SUCCEEDED` を確認。`make tf-output` の `dashboard_url` を開いて確認します。以後は `main` に push するたびに自動で配信されます。GitHub 側に設定するもの（変数・シークレット）はありません。

別環境（staging など）は `envs/staging.tfvars` を用意して `environment = "staging"` にし、`make tf-bootstrap ENV=staging` で `envs/staging.backend.hcl` を書き出します（バケットは共通で、`key` だけが変わります）。以後のコマンドにも `ENV=staging` を付けます。

## CI/CD

| 何が | きっかけ | 実行内容 | どこで動く |
|---|---|---|---|
| `ci.yml` | PR / main | pytest、Docker ビルド、画面の typecheck・build・テスト | GitHub Actions |
| `terraform.yml` | `infra/terraform/**` の変更 | `fmt -check` / `validate` だけ（AWS には触らない） | GitHub Actions |
| 配信（[buildspec.yml](../../buildspec.yml)） | main への push / `make deploy` | API 画像を ECR へ push し、ECS サービスを再デプロイして安定するまで待機。画面をビルドして S3 へ同期、CloudFront を無効化 | AWS CodeBuild |

- **配信は AWS が取りに行く形**です。CodeBuild が GitHub への接続（CodeConnections）でリポジトリを取得するので、GitHub には AWS のロール・変数・シークレットを置きません。GitHub Actions は AWS に一切触りません。
- **結果の確認**: `make deploy-status`（直近 5 回）。ログは CloudWatch Logs の `/aws/codebuild/chatgpt-usage-dashboard-prod-deploy` です。リポジトリが公開で、結果のリンクに AWS アカウント ID が含まれるため、GitHub のコミットには結果を表示しません。
- **動くのは main への push だけ**です。PR（フォークからのものを含む）では配信は動きません。
- **CodeBuild の権限**はアプリの配信（ECR への push、画面用 S3 の更新、CloudFront の無効化、ECS の再デプロイ）だけで、インフラを変更する権限は持たせていません。
- Terraform の `plan` / `apply` は CI では行いません。担当者が手元のコンテナから `make tf-plan` / `make tf-apply` で実行します。

## 費用の目安（東京、月額）

AWS の公開価格表（2026 年 10 月時点）での試算です。合計 **約 $15〜16/月**。

| 項目 | 単価 | 月額 |
|---|---|---|
| Fargate 0.25 vCPU | $0.05056 / vCPU・時 | $9.23 |
| Fargate メモリ 0.5 GB | $0.00553 / GB・時 | $2.02 |
| パブリック IPv4 アドレス 1 個（タスク） | $0.005 / 時 | $3.65 |
| Cloud Map（内部 DNS ゾーン $0.50、登録 $0.10、問い合わせ $1.00 / 100 万回） | | 約 $0.6〜0.7 |
| API Gateway（HTTP API） | $1.29 / 100 万リクエスト | 月 10 万件で $0.13 |
| CodeBuild（general1.small） | $0.005 / 分 | 1 回 4 分 × 20 回で $0.40（無料枠 月 100 分内なら $0） |
| ECR（直近 10 画像、約 0.8GB） | $0.10 / GB | $0.08 |
| CloudFront、S3、ログ、SSM、証明書、VPC リンク | 無料枠内または無料 | $0.05 未満 |

1 か月は 730 時間で計算。費用の大半は常時動かすタスク（$14.90）で、利用量による部分は月 $1 前後です。

## 決定事項

| 項目 | 決定 | 理由 |
|---|---|---|
| IaC | Terraform。state は S3、ロックは `use_lockfile` | 要望 |
| リージョン | ap-northeast-1 | 利用者が国内 |
| 実行基盤 | ECS Fargate（API）を API Gateway + VPC リンクで公開、S3 + CloudFront（画面） | 画面と API を分離。App Runner は新規利用不可、ALB は固定費が高く、社内の共有 ALB は接続元が限定されていて CloudFront から届かない |
| 認証 | アプリ内の Google Workspace OAuth（社内の TARO・KEN と同じ型）。シークレットは SSM | 社内実績あり |
| ドメイン | `chatgpt-dashboard.dev.haw.biz`（`dev.haw.biz` は Route53 の委任済みゾーン） | 要望 |
| デプロイ | アプリの配信は AWS CodeBuild が GitHub から取得して実行（main への push が契機）。インフラの `apply` は担当者が実行 | 公開リポジトリと GitHub 側に AWS の情報や権限を置かない |
| データ | S3 バケット 1 つ。アプリは `STORAGE_BACKEND=s3` | 既存アダプター |

## 参考にした社内リポジトリ

| リポジトリ | 何を参考にしたか |
|---|---|
| haw/taro、haw/daily_report（KEN） | Google Workspace OAuth をアプリ内で行う型、環境変数・credentials の扱い |
| chaintope/tapyrus-terraform-modules、chaintope/chocolateshop-terraform | `dashboard_cdn`（CloudFront + S3 + ACM + Route53）、backend と state の規約、タグ戦略 |
| haw/cognito-alb-auth-demo | CloudFront で静的配信と API を同一ドメインにまとめる構成 |
