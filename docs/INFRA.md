# 本番環境とCI/CD

本番は AWS に Terraform（[infra/terraform/](../infra/terraform/)）で構築し、GitHub Actions から OIDC でデプロイする。この文書は構成の判断事項を記録する。決まったものから「決定」に移す。

## 決定

| 項目 | 決定 | 理由 |
|---|---|---|
| IaC | Terraform（state は S3、ロックは S3 の `use_lockfile`） | 要望。DynamoDB ロックは不要になった |
| リージョン | ap-northeast-1 | 利用者が国内 |
| デプロイ認証 | GitHub Actions OIDC → IAM ロール（`main` ブランチと `prod` Environment からのみ） | アクセスキーを置かない |
| データ保存 | S3 バケット 1 つ（バージョニング、SSE-S3、公開ブロック）。アプリは `STORAGE_BACKEND=s3` | 既存の S3 アダプターをそのまま使う |
| 画像 | GitHub Actions で build → ECR に push（タグは commit SHA と `latest`） | 既存 Dockerfile を流用 |

## 未決（PR で決める）

### 1. 実行基盤
アプリは FastAPI + 静的ファイルを 1 コンテナで配信し、処理は日次取込の手動アップロードのみで負荷は極めて軽い。利用者は 1〜数名。

| 案 | 月額の目安（東京） | 利点 | 欠点 |
|---|---|---|---|
| **App Runner** | 最小構成で約 $5〜10（アイドル時はメモリ課金のみ） | 最も手数が少ない。HTTPS・自動デプロイ込み。VPC 不要 | カスタム認証は前段が必要（Cognito をアプリ側で検証、または CloudFront + Lambda@Edge） |
| ECS Fargate + ALB | ALB だけで約 $20〜25 + タスク約 $10 | ALB の Cognito 認証が使える（アプリ改修なし） | 常時起動で最も高い。VPC・サブネット・SG が必要 |
| Lambda Web Adapter + API Gateway + CloudFront | ほぼ従量（$1 未満〜） | 最安 | コールドスタート。5 MiB アップロードは API Gateway の上限（10 MB）内だが要確認。認証は Cognito authorizer |

推奨: **App Runner**。理由は運用の手数とコストの均衡。認証は下記 2 で決める。

### 2. 認証
- Cognito User Pool（社内メール、必要なら Google/Microsoft とのフェデレーション）
- 検証の場所: (a) ALB（ECS 案のみ）、(b) CloudFront + Lambda@Edge/CloudFront Functions、(c) アプリ内ミドルウェア（Authorization Code + PKCE、セッション Cookie）
- App Runner 案なら (c) が最小。アプリに `AUTH_MODE=cognito` を追加し、ローカルは `none` のままにする。

### 3. ドメインと証明書
- 社内 DNS かパブリックドメインか。ACM 証明書は us-east-1（CloudFront 使用時）か ap-northeast-1。

### 4. データ保持と監視
- raw インポートの保持期間（`data_retention_days`）。
- CloudWatch Logs の保持日数、エラー率アラーム、通知先（メール／Slack）。

### 5. 環境
- prod のみか、staging も持つか。staging を持つ場合は `environment` 変数で同一構成を複製する。

## CI/CD の流れ（目標）

```
PR:      pytest + docker build + terraform fmt/validate
main:    pytest → docker build → ECR push → terraform plan → [prod 承認] → terraform apply → サービス更新
```

- `prod` は GitHub Environment で保護し、apply と本番デプロイは承認者の承認後に実行する。
- Terraform の plan は PR コメントに出す（AWS 認証がある場合のみ）。

## 手動で1回だけ行うこと

1. state 用 S3 バケットの作成（バージョニング有効）。
2. GitHub OIDC プロバイダの登録（`token.actions.githubusercontent.com`、サムプリントは AWS が管理）。
3. 初回 `terraform apply` の後、出力 `deploy_role_arn` をリポジトリ変数 `AWS_ROLE_ARN` に設定。
