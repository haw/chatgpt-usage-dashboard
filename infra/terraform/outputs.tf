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
  description = "S3 bucket the React build is synced to (CI variable FRONTEND_BUCKET)."
  value       = aws_s3_bucket.frontend.bucket
}

output "cloudfront_distribution_id" {
  description = "Distribution to invalidate after a frontend deploy (CI variable CLOUDFRONT_DISTRIBUTION_ID)."
  value       = aws_cloudfront_distribution.dashboard.id
}

output "ecr_repository" {
  description = "ECR repository URL for the API image (CI variable ECR_REPOSITORY)."
  value       = aws_ecr_repository.api.repository_url
}

output "api_origin" {
  description = "Host name CloudFront uses for the API on the shared ALB (not used by people; direct requests are rejected)."
  value       = "https://${var.api_hostname}"
}

output "ecs_service" {
  description = "ECS service name (CI variable ECS_SERVICE)."
  value       = aws_ecs_service.api.name
}

output "ecs_cluster" {
  description = "ECS cluster name (CI variable ECS_CLUSTER)."
  value       = aws_ecs_cluster.api.name
}

output "deploy_role_arn" {
  description = "Role the GitHub Actions deploy workflow assumes (repository variable AWS_ROLE_ARN)."
  value       = aws_iam_role.deploy.arn
}

output "ssm_parameter_names" {
  description = "Secrets to set once with `aws ssm put-parameter --type SecureString --overwrite`."
  value       = [for p in aws_ssm_parameter.secret : p.name]
}
