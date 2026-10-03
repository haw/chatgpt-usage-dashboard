# 本番環境（Terraform）

本番環境は HAW の AWS に Terraform で構築し、GitHub Actions から OIDC でデプロイします。構成・対象・使い方・判断事項はこのファイルにまとめます（アプリ本体の説明は [リポジトリの README](../../README.md)）。

## 構成

```
利用者 ── HTTPS ── CloudFront（*.cloudfront.net または独自ドメイン）
                   ├─ /api/*, /login/google, /auth/*, /logout, /health → App Runner（API。ECR の画像、インスタンス 1）
                   └─ それ以外（React の画面）                          → S3（ビルド成果物、OAC で非公開）
App Runner の環境変数: STORAGE_BACKEND=s3 / AUTH_MODE=google / 許可ドメイン / SESSION_SECURE
シークレット（Google OAuth の ID・Secret、セッション鍵）: SSM Parameter Store（SecureString）
データ: S3 バケット（raw・正規化 JSONL・状態・確認済み記録）
GitHub Actions: main への push → API 画像を ECR へ（App Runner が自動反映）、画面を S3 へ同期 → CloudFront 無効化
```

| 管理するもの | ファイル |
|---|---|
| データ用 S3 バケット、GitHub OIDC デプロイロール（ECR push / S3 同期 / CloudFront 無効化 / App Runner 参照） | `main.tf` |
| ECR リポジトリ（直近 10 画像を保持） | `ecr.tf` |
| SSM Parameter Store のシークレット 3 つ（値は Terraform 管理外） | `secrets.tf` |
| App Runner サービス（0.25 vCPU / 0.5 GB、最大 1 インスタンス、`/health` で監視、ECR の `latest` を自動デプロイ）とロール | `apprunner.tf` |
| 画面用 S3 バケット、CloudFront（2 オリジン、API パスはキャッシュなし、SPA 用と転送ヘッダ用の CloudFront Functions） | `frontend.tf` |
| 独自ドメイン（任意）: ACM 証明書（us-east-1、DNS 検証）と Route53 の別名レコード | `domain.tf` |

管理しないもの: Terraform の state バケットと GitHub OIDC プロバイダ（1 回だけ手動で作成）、Google Cloud の OAuth クライアント、ローカル開発環境（Docker Compose）。

### 証明書について
- CloudFront と App Runner は既定ドメインで AWS 管理の証明書付き HTTPS を提供するため、**独自ドメインを使わなければ証明書の用意は不要**です。App Runner の既定ドメインは CloudFront のオリジンとしてそのまま使います。
- 独自ドメイン（`domain_name` と `route53_zone_id` を指定）のときだけ ACM 証明書を発行します。無料で、Route53 の DNS 検証により自動で発行・更新されます。

### 設計上の要点
- **インスタンスは 1 つ**: 正規化データは取込時に全体を書き戻す方式のため、App Runner の自動スケーリングを最大 1 に固定しています。
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
3. **ECR を先に作る**: App Runner はサービス作成時に画像が必要なので、まず ECR だけ適用し、画像を 1 度 push します。
   ```bash
   terraform apply -var-file=envs/prod.tfvars -target=aws_ecr_repository.api -target=aws_iam_role.deploy
   # 手元から初回の画像を push（以後は CI が push）
   aws ecr get-login-password | docker login --username AWS --password-stdin $(terraform output -raw ecr_repository | cut -d/ -f1)
   docker build -t $(terraform output -raw ecr_repository):latest . && docker push $(terraform output -raw ecr_repository):latest
   ```
4. **全体を適用**: `terraform apply -var-file=envs/prod.tfvars`。
5. **シークレットを設定**（Terraform は値を上書きしません）:
   ```bash
   P=/chatgpt-usage-dashboard/prod
   aws ssm put-parameter --name $P/GOOGLE_CLIENT_ID     --type SecureString --overwrite --value '<クライアント ID>'
   aws ssm put-parameter --name $P/GOOGLE_CLIENT_SECRET --type SecureString --overwrite --value '<クライアント シークレット>'
   aws ssm put-parameter --name $P/SESSION_SECRET       --type SecureString --overwrite --value "$(openssl rand -hex 32)"
   aws apprunner start-deployment --service-arn $(terraform output -raw apprunner_service_arn)   # 新しい値で再起動
   ```
6. **Google Cloud** の OAuth クライアントに `terraform output -raw oauth_redirect_uri` を「承認済みのリダイレクト URI」として追加。
7. **GitHub のリポジトリ変数**を設定し、`prod` Environment に承認者を設定:

   | 変数 | 値 |
   |---|---|
   | `AWS_ROLE_ARN` | `terraform output -raw deploy_role_arn` |
   | `TF_STATE_BUCKET` | state バケット名 |
   | `ECR_REPOSITORY` | `terraform output -raw ecr_repository` |
   | `FRONTEND_BUCKET` | `terraform output -raw frontend_bucket` |
   | `CLOUDFRONT_DISTRIBUTION_ID` | `terraform output -raw cloudfront_distribution_id` |
   | `APPRUNNER_SERVICE_ARN` | `terraform output -raw apprunner_service_arn` |

8. `main` に push すると `deploy.yml` が画像と画面を配信します（初回は `workflow_dispatch` で手動実行も可）。`terraform output -raw dashboard_url` を開いて確認。

別環境（staging など）は `envs/staging.tfvars` と `envs/staging.backend.hcl`（`key` を変える）を用意し、`environment = "staging"` にします。

整形と検証だけなら AWS 認証なしで実行できます: `terraform fmt -check -recursive && terraform init -backend=false && terraform validate`。

## CI/CD

| ワークフロー | きっかけ | 実行内容 | 必要なもの |
|---|---|---|---|
| `ci.yml` | PR / main | pytest、Docker ビルド、画面の typecheck・build・テスト | なし |
| `terraform.yml` | `infra/terraform/**` の変更 | PR: `fmt -check` / `validate`。main: OIDC で `plan` → `prod` 承認 → `apply` | `AWS_ROLE_ARN`、`TF_STATE_BUCKET` |
| `deploy.yml` | main への push / 手動 | API 画像を ECR へ push（App Runner が `latest` を自動反映、RUNNING まで待機）。画面をビルドして S3 へ同期、CloudFront を無効化 | 上の表の変数すべて |

変数が未設定の間はジョブがスキップされるので、土台だけの状態でも CI は通ります。

## 費用の目安（東京、月額）
App Runner 最小構成 約 $5〜10（アイドル時はメモリ課金のみ）、CloudFront・S3・ECR・SSM は利用量が小さく合計 $1 前後。独自ドメインの ACM 証明書は無料。

## 決定事項

| 項目 | 決定 | 理由 |
|---|---|---|
| IaC | Terraform。state は S3、ロックは `use_lockfile` | 要望 |
| リージョン | ap-northeast-1 | 利用者が国内 |
| 実行基盤 | App Runner（API）、S3 + CloudFront（画面） | 画面と API を分離。負荷が極小で運用の手数が最少 |
| 認証 | アプリ内の Google Workspace OAuth（社内の TARO・KEN と同じ型）。シークレットは SSM | ALB 不要、社内実績あり |
| デプロイ | GitHub Actions OIDC → IAM ロール。鍵を置かない | 標準的 |
| データ | S3 バケット 1 つ。アプリは `STORAGE_BACKEND=s3` | 既存アダプター |

## 参考にした社内リポジトリ

| リポジトリ | 何を参考にしたか |
|---|---|
| haw/taro、haw/daily_report（KEN） | Google Workspace OAuth をアプリ内で行う型、環境変数・credentials の扱い |
| chaintope/tapyrus-terraform-modules、chaintope/chocolateshop-terraform | `dashboard_cdn`（CloudFront + S3 + ACM + Route53）、backend と state の規約、タグ戦略 |
| haw/cognito-alb-auth-demo | CloudFront で静的配信と API を同一ドメインにまとめる構成 |
