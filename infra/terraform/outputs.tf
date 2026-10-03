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

output "apprunner_service_url" {
  description = "The API's own URL (CloudFront origin; not used by people)."
  value       = aws_apprunner_service.api.service_url
}

output "apprunner_service_arn" {
  description = "App Runner service (CI variable APPRUNNER_SERVICE_ARN)."
  value       = aws_apprunner_service.api.arn
}

output "deploy_role_arn" {
  description = "Role the GitHub Actions deploy workflow assumes (repository variable AWS_ROLE_ARN)."
  value       = aws_iam_role.deploy.arn
}

output "ssm_parameter_names" {
  description = "Secrets to set once with `aws ssm put-parameter --type SecureString --overwrite`."
  value       = [for p in aws_ssm_parameter.secret : p.name]
}
