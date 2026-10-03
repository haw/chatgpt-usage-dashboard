variable "aws_region" {
  description = "Region every resource lives in."
  type        = string
  default     = "ap-northeast-1"
}

variable "environment" {
  description = "Environment name used in resource names and tags (prod, staging)."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.environment))
    error_message = "environment must be lowercase letters, digits or dashes."
  }
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "chatgpt-usage-dashboard"
}

variable "github_repository" {
  description = "GitHub repository (owner/name) allowed to assume the deploy role through OIDC."
  type        = string
  default     = "haw/chatgpt-usage-dashboard"
}

variable "data_retention_days" {
  description = "Days before raw import objects expire. 0 keeps them forever."
  type        = number
  default     = 0
}

variable "auth_allowed_domains" {
  description = "Google Workspace domains allowed to sign in (comma separated in the app)."
  type        = list(string)
  default     = ["haw.co.jp"]
}

variable "image_tag" {
  description = "ECR image tag App Runner runs. CI pushes 'latest' and App Runner auto-deploys on each push."
  type        = string
  default     = "latest"
}

variable "apprunner_cpu" {
  description = "App Runner instance CPU (the smallest size is plenty for a few analysts)."
  type        = string
  default     = "256"
}

variable "apprunner_memory" {
  description = "App Runner instance memory in MB."
  type        = string
  default     = "512"
}

variable "domain_name" {
  description = "Custom domain for the dashboard (e.g. chatgpt-usage.haw.biz). Empty uses the CloudFront domain."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Hosted zone that owns domain_name; required when domain_name is set (ACM validation and the alias record)."
  type        = string
  default     = ""
}
