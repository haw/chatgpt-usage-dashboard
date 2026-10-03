# 本番環境（Terraform）

本番環境は HAW の AWS に Terraform で構築し、GitHub Actions から OIDC でデプロイします。構成・対象・使い方・判断事項はこのファイルにまとめます（アプリ本体の説明は [リポジトリの README](../../README.md)）。

## 構成

```
利用者 ── HTTPS ── CloudFront（*.cloudfront.net または独自ドメイン）
                   ├─ /api/*, /login/google, /auth/*, /logout, /health → ECS Express Mode（API。Fargate タスク 1 + ALB、ECR の画像）
                   └─ それ以外（React の画面）                          → S3（ビルド成果物、OAC で非公開）
API の環境変数: STORAGE_BACKEND=s3 / AUTH_MODE=google / 許可ドメイン / SESSION_SECURE
シークレット（Google OAuth の ID・Secret、セッション鍵）: SSM Parameter Store（SecureString）
データ: S3 バケット（raw・正規化 JSONL・状態・確認済み記録）
GitHub Actions: main への push → API 画像を ECR へ push し ECS Express サービスをその画像に更新、画面を S3 へ同期 → CloudFront 無効化
```

| 管理するもの | ファイル |
|---|---|
| データ用 S3 バケット、GitHub OIDC デプロイロール（ECR push / S3 同期 / CloudFront 無効化 / ECS サービス更新） | `main.tf` |
| ECR リポジトリ（直近 10 画像を保持） | `ecr.tf` |
| SSM Parameter Store のシークレット 3 つ（値は Terraform 管理外） | `secrets.tf` |
| ECS Express Mode サービス（クラスター、0.25 vCPU / 0.5 GB の Fargate タスク 1 固定、`/health`、ログ保持 90 日）と実行・インフラ・タスクの各ロール | `ecs.tf` |
| 画面用 S3 バケット、CloudFront（2 オリジン、API パスはキャッシュなし、SPA 用と転送ヘッダ用の CloudFront Functions） | `frontend.tf` |
| 独自ドメイン（任意）: ACM 証明書（us-east-1、DNS 検証）と Route53 の別名レコード | `domain.tf` |

管理しないもの: Terraform の state バケットと GitHub OIDC プロバイダ（1 回だけ手動で作成）、Google Cloud の OAuth クライアント、ローカル開発環境（Docker Compose）。ECS Express Mode が自動で作る ALB・ターゲットグループ・セキュリティグループ・スケーリング設定は、サービスに付随して管理されます。

### App Runner ではなく ECS Express Mode にした理由
App Runner は 2026 年 3 月末にメンテナンスモード入りが発表され、4 月 30 日以降は新規顧客が利用できません。AWS が後継として案内する ECS Express Mode は、コンテナ画像と 2 つのロールを渡すだけで Fargate・ALB（HTTPS リスナー、ホスト名ルーティング）・ログ・スケーリングを 1 リソースで構成します。社内（chaintope の Terraform モジュール）の ECS + ALB の型にも揃います。

### 証明書について
- CloudFront は既定ドメイン（`*.cloudfront.net`）で、ECS Express Mode の ALB はサービスごとの HTTPS エンドポイントで、どちらも AWS 管理の証明書付きです。**独自ドメインを使わなければ証明書の用意は不要**で、Express のエンドポイントは CloudFront のオリジンとしてそのまま使います。
- 独自ドメイン（`domain_name` と `route53_zone_id` を指定）のときだけ ACM 証明書を発行します。無料で、Route53 の DNS 検証により自動で発行・更新されます。

### 設計上の要点
- **タスクは 1 つ**: 正規化データは取込時に全体を書き戻す方式のため、スケーリングの最小・最大を 1 に固定しています。
- **画像の更新**: Express サービスは画像タグをダイジェストに固定するため、`latest` を push しただけでは入れ替わりません。デプロイのワークフローが `update-express-gateway-service` で各コミットのタグへ更新し、Terraform は初期値以外の画像変更を無視します（`ignore_changes`）。
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
3. **ECR を先に作る**: ECS サービスは作成時に画像が必要なので、まず ECR だけ適用し、画像を 1 度 push します。
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
   aws ecs update-express-gateway-service --service-arn $(terraform output -raw ecs_service_arn) \
     --primary-container "image=$(terraform output -raw ecr_repository):latest"   # 新しい値でタスクを入れ替える
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
   | `ECS_SERVICE_ARN` | `terraform output -raw ecs_service_arn` |
   | `ECS_CLUSTER` | `terraform output -raw ecs_cluster` |

8. `main` に push すると `deploy.yml` が画像と画面を配信します（初回は `workflow_dispatch` で手動実行も可）。`terraform output -raw dashboard_url` を開いて確認。

別環境（staging など）は `envs/staging.tfvars` と `envs/staging.backend.hcl`（`key` を変える）を用意し、`environment = "staging"` にします。

整形と検証だけなら AWS 認証なしで実行できます: `terraform fmt -check -recursive && terraform init -backend=false && terraform validate`。

## CI/CD

| ワークフロー | きっかけ | 実行内容 | 必要なもの |
|---|---|---|---|
| `ci.yml` | PR / main | pytest、Docker ビルド、画面の typecheck・build・テスト | なし |
| `terraform.yml` | `infra/terraform/**` の変更 | PR: `fmt -check` / `validate`。main: OIDC で `plan` → `prod` 承認 → `apply` | `AWS_ROLE_ARN`、`TF_STATE_BUCKET` |
| `deploy.yml` | main への push / 手動 | API 画像を ECR へ push し、ECS Express サービスをそのタグに更新して安定するまで待機。画面をビルドして S3 へ同期、CloudFront を無効化 | 上の表の変数すべて |

変数が未設定の間はジョブがスキップされるので、土台だけの状態でも CI は通ります。

## 費用の目安（東京、月額）
Fargate 0.25 vCPU / 0.5 GB × 1 タスク 約 $9、ALB 約 $18〜20（固定分。同じ VPC の Express サービス最大 25 個で共有可）、CloudFront・S3・ECR・SSM・ログは利用量が小さく合計 $1〜2。独自ドメインの ACM 証明書は無料。合計 **約 $30/月**。

## 決定事項

| 項目 | 決定 | 理由 |
|---|---|---|
| IaC | Terraform。state は S3、ロックは `use_lockfile` | 要望 |
| リージョン | ap-northeast-1 | 利用者が国内 |
| 実行基盤 | ECS Express Mode（API）、S3 + CloudFront（画面） | 画面と API を分離。App Runner は新規利用不可のため AWS 推奨の後継を採用 |
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
