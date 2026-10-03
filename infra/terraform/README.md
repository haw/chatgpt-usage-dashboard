# 本番環境（Terraform）

本番環境は HAW の AWS に Terraform で構築し、GitHub Actions から OIDC でデプロイします。構成・対象・使い方・判断事項はこのファイルにまとめます（アプリ本体の説明は [リポジトリの README](../../README.md)）。

## 構成

```
利用者 ── HTTPS ── CloudFront（*.cloudfront.net または独自ドメイン）
                   ├─ /api/*, /login/google, /auth/*, /logout, /health → 既存 ALB（相乗り）→ Fargate タスク 1（API、ECR の画像）
                   └─ それ以外（React の画面）                          → S3（ビルド成果物、OAC で非公開）
API の環境変数: STORAGE_BACKEND=s3 / AUTH_MODE=google / 許可ドメイン / SESSION_SECURE
シークレット（Google OAuth の ID・Secret、セッション鍵）: SSM Parameter Store（SecureString）
データ: S3 バケット（raw・正規化 JSONL・状態・確認済み記録）
GitHub Actions: main への push → API 画像を ECR へ push し ECS サービスを再デプロイ、画面を S3 へ同期 → CloudFront 無効化
```

| 管理するもの | ファイル |
|---|---|
| データ用 S3 バケット、GitHub OIDC デプロイロール（ECR push / S3 同期 / CloudFront 無効化 / ECS サービス更新） | `main.tf` |
| ECR リポジトリ（直近 10 画像を保持） | `ecr.tf` |
| SSM Parameter Store のシークレット 3 つ（値は Terraform 管理外） | `secrets.tf` |
| 既存 ALB への相乗り（API 用ホスト名の Route53 レコードと ACM 証明書をリスナーに追加、ホスト名＋秘密ヘッダーのリスナールール、ターゲットグループ）、ECS クラスター、タスク定義、サービス（0.25 vCPU / 0.5 GB の Fargate タスク 1 固定、`/health`、ログ保持 90 日）、実行・タスクロール、タスクの SG | `ecs.tf` |
| 画面用 S3 バケット、CloudFront（2 オリジン、API パスはキャッシュなし、SPA 用と転送ヘッダ用の CloudFront Functions） | `frontend.tf` |
| 独自ドメイン（任意）: ACM 証明書（us-east-1、DNS 検証）と Route53 の別名レコード | `domain.tf` |

管理しないもの: 相乗り先の ALB 本体と VPC・サブネット（`shared_alb_arn` で指定した ALB から VPC・サブネット・SG を読み取る）、GitHub OIDC プロバイダ（アカウントに登録済みのものを参照）、Google Cloud の OAuth クライアント、ローカル開発環境（Docker Compose）。

### 実行基盤の選び方
- App Runner は 2026 年 3 月末にメンテナンスモード入りが発表され、4 月 30 日以降は新規顧客が利用できないため使いません。
- AWS の後継案内は ECS Express Mode ですが、Express 同士でしか ALB を共有できず ALB の固定費（月 $18〜20）が乗ります。費用を抑えるため、**既存の ALB に相乗りする標準の ECS Fargate サービス**にしました。追加費用は Fargate 1 タスク分だけです。
- ALB に足すのは、API 用ホスト名（`api_hostname`）の証明書（ACM、無料、DNS 検証）、そのホスト名と秘密ヘッダー（CloudFront だけが付ける `x-origin-verify`）で振り分けるリスナールール、ターゲットグループの 3 つです。既存のルールには触れません。

### 証明書について
- CloudFront は既定ドメイン（`*.cloudfront.net`）なら AWS 管理の証明書付きです。独自ドメインと、ALB 上の API 用ホスト名には ACM 証明書を使います。
- 独自ドメイン（`domain_name` と `route53_zone_id` を指定）のときだけ ACM 証明書を発行します。無料で、Route53 の DNS 検証により自動で発行・更新されます。

### 設計上の要点
- **タスクは 1 つ**: 正規化データは取込時に全体を書き戻す方式のため、`desired_count = 1` とし、デプロイ時も 2 タスクが同時に動かないよう「止めてから起動」（最小 0% / 最大 100%）にしています。入れ替え中は数十秒ほど API が応答しません。
- **画像の更新**: タスク定義は `latest` を参照し、デプロイのワークフローが push 後に `update-service --force-new-deployment` で入れ替えます。
- **ALB を迂回できない**: リスナールールは CloudFront が付ける秘密ヘッダーを要求するため、ALB のホスト名を直接叩いても API には届きません。タスクの SG も ALB の SG からの 8000 番しか許可しません。
- **NAT なし**: タスクはパブリックサブネットでパブリック IP を持ち、ECR・SSM・ログへの到達に NAT を使いません（受信は ALB からのみ）。
- **同一オリジン**: 画面と API を同じ CloudFront ドメインで配信するので、セッション Cookie と OAuth のリダイレクトは開発時と同じ仕組みで動きます。CloudFront Function が `X-Forwarded-Host` / `X-Forwarded-Proto` を API に渡し、API はそれからコールバック URL を組み立てます（`BASE_URL` は不要）。
- **SPA のパス**: 拡張子のないパス（`/insights/2026-09-22` など）は CloudFront Function が `index.html` に書き換えます。API パスには適用しません。
- **キャッシュ**: ハッシュ付きの `assets/*` は 1 年、`index.html` は `no-cache`。API はキャッシュしません。

## 前提

- Docker と Docker Compose だけ。Terraform と AWS CLI はホストに入れず、専用コンテナ（`terraform` サービス。Terraform 1.13.4 + AWS CLI v2、[Dockerfile](Dockerfile)）で実行します。
- HAW の AWS アカウント（ALB のあるアカウント）の IAM ユーザーのアクセスキー。キーはこのコンテナ専用の Docker ボリューム（`aws_credentials`）だけに保存します。ホストの `~/.aws` はマウントしないので、ホスト側にキーは残らず、コンテナからホストの他のプロファイルも見えません。リポジトリ内のファイル（`.env`、`*.tfvars` など）には書かないでください。
- GitHub OIDC プロバイダ `token.actions.githubusercontent.com` がアカウントに登録済み（HAW のアカウントには登録済み）。state 用 S3 バケットは `make tf-bootstrap` が作ります（「初回だけ行うこと」参照）。

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
| `make tf-first-image` | 初回だけ。ECR だけ作って API の画像を 1 度 push |
| `make tf-fmt` / `make tf-check` | 整形 / CI と同じ検査（`fmt -check`・`validate`。AWS 認証不要） |
| `make tf ARGS="…"` / `make aws ARGS="…"` | 上にない terraform / aws のコマンド（例: `make tf ARGS="state list"`） |
| `make tf-shell` | コンテナのシェルに入る（terraform、aws、jq、openssl が使えます） |

- 追加の引数は `ARGS` で渡します（例: `make tf-plan ARGS="-target=aws_ecs_service.api"`）。
- 環境は `ENV` で切り替えます（既定は `prod`。例: `make tf-plan ENV=staging`）。
- キーを消すときは `docker volume rm chatgpt_dashboard_aws_credentials`（`docker compose down -v` でも消えます）。入れ替えるときは `make aws-configure` をもう一度実行します。

## 使い方

```bash
cp infra/terraform/envs/prod.tfvars.example infra/terraform/envs/prod.tfvars   # 許可ドメイン、ドメイン、ALB などを編集
make tf-init
make tf-plan
make tf-apply
make tf-output
```

### 初回だけ行うこと（順番どおりに）

1. **コンテナと認証**: `make tf-build`、`make aws-configure`、`make aws-whoami` でアカウントを確認。
2. **state バケット**を作る: `make tf-bootstrap`。このプロジェクト専用のバケット `chatgpt-usage-dashboard-terraform-state-<アカウント ID>`（バージョニング・暗号化・パブリックアクセスブロック・TLS 必須）を [bootstrap/](bootstrap/main.tf) の Terraform で作り、`envs/prod.backend.hcl` を書き出します。作成内容が表示されるので `yes` で確定します。再実行しても変更は出ません。
   - bootstrap 自身の state はローカルの `bootstrap/terraform.tfstate`（git 管理外）です。なくしても `make tf ARGS="-chdir=bootstrap import aws_s3_bucket.state <バケット名>"` で戻せます。
3. **GitHub OIDC プロバイダ** `token.actions.githubusercontent.com` が IAM にあることを確認: `make aws ARGS="iam list-open-id-connect-providers"`（HAW のアカウントには登録済み。なければ `make aws ARGS="iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com"`）。
4. **設定ファイル**: `envs/prod.tfvars.example` を `envs/prod.tfvars` にコピーし、相乗り先の ALB `haw-dev-load-balancer`（`ken.haw.biz` や `*.dev.haw.biz` の各アプリが相乗りしている HTTPS:443 リスナー付きの ALB）の ARN などを記入。タスクは既定で ALB と同じサブネットを使うので、サブネットの指定は不要です。続けて `make tf-init`。
5. **ECR を先に作る**: `make tf-first-image`。ECS サービスは作成時に画像が必要なので、ECR だけ適用し（`yes` で確定）、ホストの `docker` で API の画像を作って 1 度 push します。以後は CI が push します。
6. **全体を適用**: `make tf-plan` で内容を確認し、`make tf-apply`（ACM の DNS 検証を含むので数分かかります）。
7. **シークレットを設定**（Terraform は値を上書きしません）。値を打ち込むので `make tf-shell` でコンテナに入って実行します:
   ```bash
   P=/chatgpt-usage-dashboard/prod
   aws ssm put-parameter --name $P/GOOGLE_CLIENT_ID     --type SecureString --overwrite --value '<クライアント ID>'
   aws ssm put-parameter --name $P/GOOGLE_CLIENT_SECRET --type SecureString --overwrite --value '<クライアント シークレット>'
   aws ssm put-parameter --name $P/SESSION_SECRET       --type SecureString --overwrite --value "$(openssl rand -hex 32)"
   aws ecs update-service --cluster $(terraform output -raw ecs_cluster) --service $(terraform output -raw ecs_service) --force-new-deployment   # 新しい値でタスクを入れ替える
   ```
8. **Google Cloud** の OAuth クライアントに `make -s tf-output ARGS="-raw oauth_redirect_uri"` の値を「承認済みのリダイレクト URI」として追加。
9. **GitHub のリポジトリ変数**を設定（アプリの配信 `deploy.yml` 用）。値は `make tf-output` の一覧にあります:

   | 変数 | `make tf-output` の項目 |
   |---|---|
   | `AWS_ROLE_ARN` | `deploy_role_arn` |
   | `ECR_REPOSITORY` | `ecr_repository` |
   | `FRONTEND_BUCKET` | `frontend_bucket` |
   | `CLOUDFRONT_DISTRIBUTION_ID` | `cloudfront_distribution_id` |
   | `ECS_SERVICE` | `ecs_service` |
   | `ECS_CLUSTER` | `ecs_cluster` |

   配信の前に人の承認を挟みたい場合は、GitHub の `prod` Environment に承認者を設定します（任意）。

10. `main` に push すると `deploy.yml` が画像と画面を配信します（初回は `workflow_dispatch` で手動実行も可）。`make tf-output` の `dashboard_url` を開いて確認。

別環境（staging など）は `envs/staging.tfvars` を用意して `environment = "staging"` にし、`make tf-bootstrap ENV=staging` で `envs/staging.backend.hcl` を書き出します（バケットは共通で、`key` だけが変わります）。以後のコマンドにも `ENV=staging` を付けます。

## CI/CD

| ワークフロー | きっかけ | 実行内容 | 必要なもの |
|---|---|---|---|
| `ci.yml` | PR / main | pytest、Docker ビルド、画面の typecheck・build・テスト | なし |
| `terraform.yml` | `infra/terraform/**` の変更 | `fmt -check` / `validate` だけ（AWS には触らない） | なし |
| `deploy.yml` | main への push / 手動 | API 画像を ECR へ push し、ECS サービスを再デプロイして安定するまで待機。画面をビルドして S3 へ同期、CloudFront を無効化 | 上の表の変数すべて |

`deploy.yml` は変数が未設定の間ジョブがスキップされるので、土台だけの状態でも CI は通ります。

Terraform の `plan` / `apply` は CI では行いません。担当者が手元のコンテナから `make tf-plan` / `make tf-apply` で実行します。CI が使うロール（`deploy_role_arn`）の権限はアプリの配信（ECR への push、画面用 S3 の更新、CloudFront の無効化、ECS の再デプロイ）だけで、インフラを変更する権限は持たせていません。

## 費用の目安（東京、月額）
Fargate 0.25 vCPU / 0.5 GB × 1 タスク 約 $9、CloudFront・S3・ECR・SSM・ログは利用量が小さく合計 $1〜2。ALB は既存のものに相乗り（ルール・証明書は無料）、ACM 証明書も無料。合計 **約 $10〜11/月**。

## 決定事項

| 項目 | 決定 | 理由 |
|---|---|---|
| IaC | Terraform。state は S3、ロックは `use_lockfile` | 要望 |
| リージョン | ap-northeast-1 | 利用者が国内 |
| 実行基盤 | 既存 ALB に相乗りする ECS Fargate（API）、S3 + CloudFront（画面） | 画面と API を分離。App Runner は新規利用不可、ECS Express Mode は ALB の固定費が乗るため |
| 認証 | アプリ内の Google Workspace OAuth（社内の TARO・KEN と同じ型）。シークレットは SSM | 社内実績あり |
| ドメイン | `chatgpt-dashboard.dev.haw.biz`（`dev.haw.biz` は Route53 の委任済みゾーン） | 要望 |
| デプロイ | アプリの配信は GitHub Actions OIDC → IAM ロール（鍵を置かない）。インフラの `apply` は CI に任せず担当者が実行 | CI に強い権限を持たせない |
| データ | S3 バケット 1 つ。アプリは `STORAGE_BACKEND=s3` | 既存アダプター |

## 参考にした社内リポジトリ

| リポジトリ | 何を参考にしたか |
|---|---|
| haw/taro、haw/daily_report（KEN） | Google Workspace OAuth をアプリ内で行う型、環境変数・credentials の扱い |
| chaintope/tapyrus-terraform-modules、chaintope/chocolateshop-terraform | `dashboard_cdn`（CloudFront + S3 + ACM + Route53）、backend と state の規約、タグ戦略 |
| haw/cognito-alb-auth-demo | CloudFront で静的配信と API を同一ドメインにまとめる構成 |
