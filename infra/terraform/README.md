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

管理しないもの: 相乗り先の ALB 本体と VPC・サブネット（`shared_alb_arn` で指定した ALB から VPC・サブネット・SG を読み取る）、Terraform の state バケットと GitHub OIDC プロバイダ（1 回だけ手動で作成）、Google Cloud の OAuth クライアント、ローカル開発環境（Docker Compose）。

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

- Terraform 1.13 系（CI と同じ版）。
- HAW の AWS アカウントへの認証（`aws sso login` 等。アクセスキーをファイルに置かない）。
- state 用 S3 バケットと GitHub OIDC プロバイダがアカウントに登録済み（「初回だけ行うこと」参照）。

## 使い方

```bash
cd infra/terraform
cp envs/prod.tfvars.example envs/prod.tfvars              # 許可ドメイン、独自ドメインなどを編集
cp envs/prod.backend.hcl.example envs/prod.backend.hcl    # state バケット名を記入
terraform init -backend-config=envs/prod.backend.hcl
terraform plan -var-file=envs/prod.tfvars
terraform apply -var-file=envs/prod.tfvars
terraform output
```

### 初回だけ行うこと（順番どおりに）

1. **state バケット**を作成（バージョニング有効、パブリックアクセスをブロック）し、`envs/prod.backend.hcl` に記入。
2. **GitHub OIDC プロバイダ** `token.actions.githubusercontent.com` を IAM に登録（未登録なら）。
3. **相乗り先の ALB** `haw-dev-load-balancer`（`ken.haw.biz` や `*.dev.haw.biz` の各アプリが相乗りしている HTTPS:443 リスナー付きの ALB）の ARN を `envs/prod.tfvars` に記入。タスクは既定で ALB と同じサブネットを使うので、サブネットの指定は不要です。
4. **ECR を先に作る**: ECS サービスは作成時に画像が必要なので、まず ECR だけ適用し、画像を 1 度 push します。
   ```bash
   terraform apply -var-file=envs/prod.tfvars -target=aws_ecr_repository.api -target=aws_iam_role.deploy
   # 手元から初回の画像を push（以後は CI が push）
   aws ecr get-login-password | docker login --username AWS --password-stdin $(terraform output -raw ecr_repository | cut -d/ -f1)
   docker build -t $(terraform output -raw ecr_repository):latest . && docker push $(terraform output -raw ecr_repository):latest
   ```
5. **全体を適用**: `terraform apply -var-file=envs/prod.tfvars`。
6. **シークレットを設定**（Terraform は値を上書きしません）:
   ```bash
   P=/chatgpt-usage-dashboard/prod
   aws ssm put-parameter --name $P/GOOGLE_CLIENT_ID     --type SecureString --overwrite --value '<クライアント ID>'
   aws ssm put-parameter --name $P/GOOGLE_CLIENT_SECRET --type SecureString --overwrite --value '<クライアント シークレット>'
   aws ssm put-parameter --name $P/SESSION_SECRET       --type SecureString --overwrite --value "$(openssl rand -hex 32)"
   aws ecs update-service --cluster $(terraform output -raw ecs_cluster) --service $(terraform output -raw ecs_service) --force-new-deployment   # 新しい値でタスクを入れ替える
   ```
7. **Google Cloud** の OAuth クライアントに `terraform output -raw oauth_redirect_uri` を「承認済みのリダイレクト URI」として追加。
8. **GitHub のリポジトリ変数**を設定し、`prod` Environment に承認者を設定:

   | 変数 | 値 |
   |---|---|
   | `AWS_ROLE_ARN` | `terraform output -raw deploy_role_arn` |
   | `TF_STATE_BUCKET` | state バケット名 |
   | `ECR_REPOSITORY` | `terraform output -raw ecr_repository` |
   | `FRONTEND_BUCKET` | `terraform output -raw frontend_bucket` |
   | `CLOUDFRONT_DISTRIBUTION_ID` | `terraform output -raw cloudfront_distribution_id` |
   | `ECS_SERVICE` | `terraform output -raw ecs_service` |
   | `ECS_CLUSTER` | `terraform output -raw ecs_cluster` |

9. `main` に push すると `deploy.yml` が画像と画面を配信します（初回は `workflow_dispatch` で手動実行も可）。`terraform output -raw dashboard_url` を開いて確認。

別環境（staging など）は `envs/staging.tfvars` と `envs/staging.backend.hcl`（`key` を変える）を用意し、`environment = "staging"` にします。

整形と検証だけなら AWS 認証なしで実行できます: `terraform fmt -check -recursive && terraform init -backend=false && terraform validate`。

## CI/CD

| ワークフロー | きっかけ | 実行内容 | 必要なもの |
|---|---|---|---|
| `ci.yml` | PR / main | pytest、Docker ビルド、画面の typecheck・build・テスト | なし |
| `terraform.yml` | `infra/terraform/**` の変更 | PR: `fmt -check` / `validate`。main: OIDC で `plan` → `prod` 承認 → `apply` | `AWS_ROLE_ARN`、`TF_STATE_BUCKET` |
| `deploy.yml` | main への push / 手動 | API 画像を ECR へ push し、ECS サービスを再デプロイして安定するまで待機。画面をビルドして S3 へ同期、CloudFront を無効化 | 上の表の変数すべて |

変数が未設定の間はジョブがスキップされるので、土台だけの状態でも CI は通ります。

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
| デプロイ | GitHub Actions OIDC → IAM ロール。鍵を置かない | 標準的 |
| データ | S3 バケット 1 つ。アプリは `STORAGE_BACKEND=s3` | 既存アダプター |

## 参考にした社内リポジトリ

| リポジトリ | 何を参考にしたか |
|---|---|
| haw/taro、haw/daily_report（KEN） | Google Workspace OAuth をアプリ内で行う型、環境変数・credentials の扱い |
| chaintope/tapyrus-terraform-modules、chaintope/chocolateshop-terraform | `dashboard_cdn`（CloudFront + S3 + ACM + Route53）、backend と state の規約、タグ戦略 |
| haw/cognito-alb-auth-demo | CloudFront で静的配信と API を同一ドメインにまとめる構成 |
