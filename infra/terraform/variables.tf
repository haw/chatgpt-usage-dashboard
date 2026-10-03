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
  description = "ECR image tag the task runs. The deploy workflow pushes this tag and forces a new deployment."
  type        = string
  default     = "latest"
}

variable "shared_alb_arn" {
  description = "Existing internet-facing Application Load Balancer the API rides on (its HTTPS listener gets a host-name rule)."
  type        = string
}

variable "task_subnet_ids" {
  description = "Subnets for the Fargate task, in the ALB's VPC. Empty uses the ALB's own (public) subnets, which avoids NAT costs; the task gets a public IP but only the ALB may reach it."
  type        = list(string)
  default     = []
}

variable "api_hostname" {
  description = "Host name CloudFront uses to reach the API through the shared ALB; a record in route53_zone_id and an ACM certificate are created for it."
  type        = string
  default     = "api.chatgpt-dashboard.dev.haw.biz"
}

variable "ecs_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU, plenty for a few analysts)."
  type        = string
  default     = "256"
}

variable "ecs_memory" {
  description = "Fargate task memory in MiB."
  type        = string
  default     = "512"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the API."
  type        = number
  default     = 90
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
