# infra/terraform

本番環境の Terraform 構成です。設計の判断事項と全体像は [docs/INFRA.md](../../docs/INFRA.md) を参照してください。

## 構成

```
infra/terraform/
  versions.tf      Terraform / provider のバージョンと S3 backend（設定は -backend-config で渡す）
  variables.tf     入力変数
  main.tf          データ用 S3 バケット、GitHub Actions OIDC 用デプロイロール
  outputs.tf       アプリと CI/CD に渡す値
  envs/            環境ごとの tfvars と backend 設定（*.example をコピーして使う。実体は git に含めない）
  modules/         実行基盤・入口・認証を決めたら、モジュールとして追加する
```

## 使い方

```bash
cd infra/terraform
cp envs/prod.tfvars.example envs/prod.tfvars
cp envs/prod.backend.hcl.example envs/prod.backend.hcl   # state バケット名を記入
terraform init -backend-config=envs/prod.backend.hcl
terraform plan -var-file=envs/prod.tfvars
terraform apply -var-file=envs/prod.tfvars
```

前提: state 用の S3 バケットと、GitHub の OIDC プロバイダ（`token.actions.githubusercontent.com`）がアカウントに登録済みであること。どちらも1回だけ手動（または別の bootstrap 構成）で作成します。

## CI

- Pull Request: `terraform fmt -check` と `terraform validate`（backend なし）。AWS 認証は不要。
- `main` への push: リポジトリ変数 `AWS_ROLE_ARN` が設定されていれば OIDC でロールを引き受け `terraform plan` を実行。`apply` は GitHub Environment `prod` の承認後に実行（ワークフローの有効化は実行基盤が決まってから）。
