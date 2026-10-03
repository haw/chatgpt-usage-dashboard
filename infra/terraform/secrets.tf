# Secrets the API reads at start-up, kept in SSM Parameter Store (SecureString).
# Terraform creates the parameters with a placeholder and never overwrites the real
# values; set them once with the CLI after the first apply:
#   aws ssm put-parameter --name /chatgpt-usage-dashboard/prod/GOOGLE_CLIENT_SECRET --type SecureString --overwrite --value '...'

locals {
  secret_names = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET"]
  ssm_prefix   = "/${var.name_prefix}/${var.environment}"
}

resource "aws_ssm_parameter" "secret" {
  for_each = toset(local.secret_names)

  name  = "${local.ssm_prefix}/${each.key}"
  type  = "SecureString"
  value = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}
