terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Remote state. The bucket is created once by hand and passed in with -backend-config,
  # so this file stays environment-agnostic:
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

# CloudFront only accepts ACM certificates issued in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "chatgpt-usage-dashboard"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
