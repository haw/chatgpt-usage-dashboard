output "dashboard_url" {
  description = "Where people open the dashboard."
  value       = local.use_domain ? "https://${var.domain_name}" : "https://${aws_cloudfront_distribution.dashboard.domain_name}"
}

output "oauth_redirect_uri" {
  description = "Register this in the Google Cloud OAuth client as an authorized redirect URI."
  value       = "${local.use_domain ? "https://${var.domain_name}" : "https://${aws_cloudfront_distribution.dashboard.domain_name}"}/auth/callback"
}

output "data_bucket" {
  description = "S3 bucket the API writes to."
  value       = aws_s3_bucket.data.bucket
}

output "frontend_bucket" {
  description = "S3 bucket the React build is synced to."
  value       = aws_s3_bucket.frontend.bucket
}

output "cloudfront_distribution_id" {
  description = "Distribution to invalidate after a frontend deploy."
  value       = aws_cloudfront_distribution.dashboard.id
}

output "ecr_repository" {
  description = "ECR repository URL for the API image."
  value       = aws_ecr_repository.api.repository_url
}

output "api_origin" {
  description = "Host name CloudFront uses for the API on the shared ALB (not used by people; direct requests are rejected)."
  value       = "https://${var.api_hostname}"
}

output "ecs_service" {
  description = "ECS service name."
  value       = aws_ecs_service.api.name
}

output "ecs_cluster" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.api.name
}

output "codebuild_project" {
  description = "CodeBuild project that deploys every push to the deploy branch (`make deploy`, `make deploy-status`)."
  value       = aws_codebuild_project.deploy.name
}

output "github_connection_arn" {
  description = "Connection CodeBuild uses to read the GitHub repository; a new one must be authorised once in the AWS console."
  value       = local.github_connection_arn
}

output "ssm_parameter_names" {
  description = "Secrets to set once with `aws ssm put-parameter --type SecureString --overwrite`."
  value       = [for p in aws_ssm_parameter.secret : p.name]
}
