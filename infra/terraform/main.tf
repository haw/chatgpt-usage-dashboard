# Production infrastructure for the dashboard.
#
# This first step only lays out the pieces that every runtime option needs:
# the data bucket the app writes to (STORAGE_BACKEND=s3) and the GitHub OIDC
# deploy role. The runtime (where the container runs), the entry point
# (CloudFront / ALB) and authentication (Cognito) are added once the choices
# in README.md are made; each will become its own module under modules/.

data "aws_caller_identity" "current" {}

locals {
  name = "${var.name_prefix}-${var.environment}"
}

# --- Data bucket: raw imports, normalized JSONL, state, dispositions -------

resource "aws_s3_bucket" "data" {
  bucket = "${local.name}-data-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  count  = var.data_retention_days > 0 ? 1 : 0
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "expire-raw-imports"
    status = "Enabled"
    filter {
      prefix = "chatgpt-dashboard/raw/"
    }
    expiration {
      days = var.data_retention_days
    }
  }
}

# --- GitHub Actions OIDC: the deploy workflow assumes this role, no keys ----

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main", "repo:${var.github_repository}:environment:${var.environment}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "${local.name}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

# Permissions are attached per runtime module (ECR push, ECS deploy, ...);
# the bucket policy below is the only one needed by every option.
data "aws_iam_policy_document" "deploy_state" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
  }
}

resource "aws_iam_role_policy" "deploy_state" {
  name   = "data-bucket-read"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy_state.json
}
