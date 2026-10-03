output "data_bucket" {
  description = "S3 bucket the app writes to (set S3_BUCKET to this)."
  value       = aws_s3_bucket.data.bucket
}

output "deploy_role_arn" {
  description = "Role the GitHub Actions deploy workflow assumes (set the AWS_ROLE_ARN repository variable to this)."
  value       = aws_iam_role.deploy.arn
}
