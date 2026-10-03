# One-time bootstrap: the S3 bucket that holds this project's Terraform state.
#
# The bucket cannot store the state of its own creation, so this small configuration keeps
# a local state file (bootstrap/terraform.tfstate, ignored by git). Losing that file is
# harmless: `terraform import aws_s3_bucket.state <bucket>` brings it back.
#
#   make tf-bootstrap        # creates the bucket and writes envs/prod.backend.hcl

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

variable "aws_region" {
  description = "Region of the state bucket."
  type        = string
  default     = "ap-northeast-1"
}

variable "name_prefix" {
  description = "Project name; the bucket is <name_prefix>-terraform-state-<account id>."
  type        = string
  default     = "chatgpt-usage-dashboard"
}

variable "environment" {
  description = "Environment whose backend config is printed (the bucket itself is shared by every environment of this project)."
  type        = string
  default     = "prod"
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "chatgpt-usage-dashboard"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "state" {
  bucket = "${var.name_prefix}-terraform-state-${data.aws_caller_identity.current.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Every state write keeps the previous version, so a bad apply can be rolled back.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_iam_policy_document" "state_tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket     = aws_s3_bucket.state.id
  policy     = data.aws_iam_policy_document.state_tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.state]
}

output "state_bucket" {
  description = "Bucket holding the Terraform state (also the TF_STATE_BUCKET repository variable)."
  value       = aws_s3_bucket.state.id
}

output "backend_config" {
  description = "Contents of envs/<environment>.backend.hcl."
  value       = <<-EOT
    # Written by `make tf-bootstrap` (ignored by git).
    bucket       = "${aws_s3_bucket.state.id}"
    key          = "${var.name_prefix}/${var.environment}/terraform.tfstate"
    region       = "${var.aws_region}"
    use_lockfile = true
    encrypt      = true
  EOT
}
