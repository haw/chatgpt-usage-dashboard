# 本番環境（Terraform）

本番環境は AWS に Terraform で構築し、GitHub Actions から OIDC でデプロイします。構成・対象・使い方・判断事項はこのファイルにまとめます（アプリ本体の説明は [リポジトリの README](../../README.md)）。

## 対象

| 管理するもの | 状態 |
|---|---|
| データ用 S3 バケット（raw 取込、正規化 JSONL、取込状態、確認済み記録） | あり |
| GitHub Actions が引き受けるデプロイ用 IAM ロール（OIDC） | あり |
| コンテナの実行基盤（App Runner / ECS Fargate / Lambda のいずれか） | 未決（下記） |
| 入口（ドメイン・証明書・CloudFront or ALB）と認証（Cognito） | 未決（下記） |
| ECR リポジトリと画像の push | 次の PR |
| ログ保持・監視・アラート | 未決（下記） |

管理しないもの: Terraform の state バケットと GitHub OIDC プロバイダ（1 回だけ手動で作成。「手動で 1 回だけ行うこと」参照）、ローカル開発環境（Docker Compose）。

## 構成

```
infra/terraform/
  versions.tf          Terraform >= 1.9、AWS provider 6.x、S3 backend（設定は -backend-config で渡す）
  variables.tf         aws_region、environment、name_prefix、github_repository、data_retention_days
  main.tf              データ用 S3 バケット、GitHub OIDC 用デプロイロール
  outputs.tf           data_bucket、deploy_role_arn
  .terraform.lock.hcl  provider のバージョン固定（コミット対象）
  envs/                環境ごとの tfvars と backend 設定。*.example をコピーして使い、実体は git に含めない
  modules/             実行基盤・入口・認証を決めたらモジュールとして追加する
```

リソース名は `<name_prefix>-<environment>`（既定 `chatgpt-usage-dashboard-prod`）を接頭辞にし、全リソースに `Project` / `Environment` / `ManagedBy` タグを付けます。

### データ用バケット
- バージョニング有効、SSE-S3 で暗号化、パブリックアクセスをすべてブロック。
- `data_retention_days` を 0 より大きくすると、`chatgpt-dashboard/raw/` 配下の取込元 JSON をその日数で期限切れにします（正規化データと状態は残ります）。
- アプリは `STORAGE_BACKEND=s3` でこのバケットに書きます（「アプリ側の設定」参照）。

### デプロイロール
- GitHub の OIDC プロバイダを信頼し、`repo:haw/chatgpt-usage-dashboard:ref:refs/heads/main` と `repo:haw/chatgpt-usage-dashboard:environment:prod` からのみ引き受けられます。
- 今はバケットの `s3:ListBucket` だけを持ちます。ECR への push や実行基盤の更新権限は、実行基盤のモジュールと一緒に追加します。

## 前提

- Terraform 1.13 系（CI と同じ版）。
- AWS 認証（ローカルでは `aws sso login` 等。アクセスキーをファイルに置かない）。
- state 用 S3 バケットと GitHub OIDC プロバイダがアカウントに登録済み。

## 使い方

```bash
cd infra/terraform
cp envs/prod.tfvars.example envs/prod.tfvars              # 変数（必要なら保持期間などを変更）
cp envs/prod.backend.hcl.example envs/prod.backend.hcl    # state バケット名を記入
terraform init -backend-config=envs/prod.backend.hcl
terraform plan -var-file=envs/prod.tfvars
terraform apply -var-file=envs/prod.tfvars
terraform output                                          # data_bucket と deploy_role_arn
```

別環境（staging など）を作る場合は `envs/staging.tfvars` と `envs/staging.backend.hcl`（`key` を変える）を用意し、`environment = "staging"` にします。同じ構成が名前だけ変えて複製されます。

整形と検証だけなら AWS 認証なしで実行できます。

```bash
terraform fmt -check -recursive
terraform init -backend=false && terraform validate
```

## CI/CD

ワークフローは [.github/workflows/terraform.yml](../../.github/workflows/terraform.yml)。

| きっかけ | 実行内容 | 必要なもの |
|---|---|---|
| Pull Request（`infra/terraform/**` の変更） | `terraform fmt -check`、`terraform validate` | なし |
| `main` への push | OIDC でデプロイロールを引き受け `terraform plan` → GitHub Environment `prod` の承認 → `terraform apply` | リポジトリ変数 `AWS_ROLE_ARN`、`TF_STATE_BUCKET`、Environment `prod` の承認者 |

変数が未設定の間は `plan` ジョブがスキップされるので、土台だけの状態でも CI は通ります。

アプリのデプロイ（pytest → docker build → ECR push → サービス更新）は実行基盤が決まってから同じワークフローに追加します。目標の流れ:

```
PR:    pytest + docker build + terraform fmt/validate
main:  pytest → docker build → ECR push → terraform plan → [prod 承認] → terraform apply → サービス更新
```

## アプリ側の設定

本番のコンテナには次の環境変数を渡します（値は `terraform output` から）。

```env
STORAGE_BACKEND=s3
S3_BUCKET=<data_bucket>
S3_PREFIX=chatgpt-dashboard
AWS_REGION=ap-northeast-1
DATA_DIR=/app/data
```

- AWS アクセスキーはアプリに渡さず、実行基盤のロール（タスクロール / インスタンスロール）で認証します。ロールには対象プレフィックスへの `s3:GetObject`、`s3:PutObject` と、バケットへの `s3:ListBucket`（`chatgpt-dashboard/raw/*`）が必要です。この権限は実行基盤のモジュールで付与します。
- S3 上のキーは `raw/<run-id>/...`、`normalized/*.jsonl`、`state/*.json`。正規化データは読込後に全体を書き戻す方式なので、**アプリのインスタンスは 1 つ**にします（同時実行すると取込が競合します）。
- 認証（Cognito）が決まるまで、本番の URL は公開しないでください。アプリ自体には認証がありません。

## 決定事項

| 項目 | 決定 | 理由 |
|---|---|---|
| IaC | Terraform。state は S3、ロックは `use_lockfile`（DynamoDB 不要） | 要望 |
| リージョン | ap-northeast-1 | 利用者が国内 |
| デプロイ認証 | GitHub Actions OIDC → IAM ロール | アクセスキーを置かない |
| データ保存 | S3 バケット 1 つ。アプリは `STORAGE_BACKEND=s3` | 既存の S3 アダプターをそのまま使う |
| 画像 | GitHub Actions で build → ECR に push（タグは commit SHA と `latest`） | 既存 Dockerfile を流用 |

## 未決事項

### 1. 実行基盤
アプリは FastAPI と静的ファイルを 1 コンテナで配信し、処理は日次集計の手動アップロードだけで負荷は極めて軽い。利用者は 1〜数名。

| 案 | 月額の目安（東京） | 利点 | 欠点 |
|---|---|---|---|
| **App Runner** | 約 $5〜10（アイドル時はメモリ課金のみ） | 手数が最少。HTTPS と自動デプロイ込み。VPC 不要 | 認証は前段（CloudFront + Lambda@Edge）かアプリ内で行う必要がある |
| ECS Fargate + ALB | ALB 約 $20〜25 + タスク約 $10 | ALB の Cognito 認証が使える（アプリ改修なし） | 常時起動で最も高い。VPC・サブネット・SG が必要 |
| Lambda Web Adapter + API Gateway + CloudFront | ほぼ従量（$1 未満〜） | 最安 | コールドスタート。5 MiB アップロードは API Gateway の上限 10 MB 内だが要確認 |

推奨: **App Runner**（運用の手数とコストの均衡）。

### 2. 認証
- Cognito User Pool（社内メール。必要なら Google / Microsoft とフェデレーション）。
- 検証する場所: (a) ALB（ECS 案のみ）、(b) CloudFront + Lambda@Edge / CloudFront Functions、(c) アプリ内ミドルウェア（Authorization Code + PKCE、セッション Cookie）。
- App Runner 案なら (c) が最小。アプリに `AUTH_MODE=cognito` を追加し、ローカルは `none` のまま。

### 3. ドメインと証明書
- 社内 DNS かパブリックドメインか。ACM 証明書は CloudFront を使うなら us-east-1、それ以外は ap-northeast-1。

### 4. データ保持と監視
- raw 取込の保持期間（`data_retention_days`）。
- CloudWatch Logs の保持日数、エラー率アラーム、通知先（メール / Slack）。

### 5. 環境
- prod のみか、staging も持つか。

## 手動で 1 回だけ行うこと

1. state 用 S3 バケットを作成（バージョニング有効、パブリックアクセスをブロック）。
2. GitHub OIDC プロバイダ `token.actions.githubusercontent.com` を IAM に登録（サムプリントは AWS が管理）。
3. 初回 `terraform apply` 後、`deploy_role_arn` をリポジトリ変数 `AWS_ROLE_ARN`、state バケット名を `TF_STATE_BUCKET` に設定し、GitHub Environment `prod` に承認者を設定。
