terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Remote state. The bucket and lock table are created once by hand (or by
  # infra/terraform/bootstrap) and passed in with -backend-config, so this file
  # stays environment-agnostic:
  #   terraform init -backend-config=envs/prod.backend.hcl
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "chatgpt-usage-dashboard"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
