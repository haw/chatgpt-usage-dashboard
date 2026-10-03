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
