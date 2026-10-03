# Production infrastructure for the dashboard.
#
#   viewer ── HTTPS ── CloudFront ──┬── /api/*, /login/google, /auth/*, /logout, /health ── API Gateway ── Fargate task (API image)
#                                   └── everything else ──────────────────────────────── S3 (built React app, private)
#
# This file holds what every piece shares: naming and the data bucket the API writes to.
# See ecr.tf, ecs.tf, api_gateway.tf, frontend.tf, secrets.tf, domain.tf and cicd.tf (the CodeBuild deploy).

data "aws_caller_identity" "current" {}

locals {
  name = "${var.name_prefix}-${var.environment}"
  # Paths CloudFront sends to the API; everything else is the React app.
  api_paths = ["/api/*", "/login/google", "/auth/*", "/logout", "/health"]
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
