# The API on App Runner: one small instance (the normalized data is rewritten as a whole
# on import, so the service must never run two instances), HTTPS on the service's own
# domain which CloudFront uses as its origin.

# Role App Runner itself uses to pull the image from ECR.
data "aws_iam_policy_document" "apprunner_build_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["build.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apprunner_access" {
  name               = "${local.name}-apprunner-access"
  assume_role_policy = data.aws_iam_policy_document.apprunner_build_assume.json
}

resource "aws_iam_role_policy_attachment" "apprunner_access" {
  role       = aws_iam_role.apprunner_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

# Role the running container uses: the data bucket and the SSM secrets.
data "aws_iam_policy_document" "apprunner_task_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["tasks.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apprunner_instance" {
  name               = "${local.name}-apprunner-instance"
  assume_role_policy = data.aws_iam_policy_document.apprunner_task_assume.json
}

data "aws_iam_policy_document" "apprunner_instance" {
  statement {
    sid       = "DataObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data.arn}/chatgpt-dashboard/*"]
  }
  statement {
    sid       = "DataList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["chatgpt-dashboard/*"]
    }
  }
  statement {
    sid       = "Secrets"
    effect    = "Allow"
    actions   = ["ssm:GetParameters", "ssm:GetParameter"]
    resources = [for p in aws_ssm_parameter.secret : p.arn]
  }
}

resource "aws_iam_role_policy" "apprunner_instance" {
  name   = "data-and-secrets"
  role   = aws_iam_role.apprunner_instance.id
  policy = data.aws_iam_policy_document.apprunner_instance.json
}

# Exactly one instance: imports rewrite the normalized files, so concurrency must be avoided.
resource "aws_apprunner_auto_scaling_configuration_version" "single" {
  auto_scaling_configuration_name = "${local.name}-single"
  max_concurrency                 = 100
  min_size                        = 1
  max_size                        = 1
}

resource "aws_apprunner_service" "api" {
  service_name                   = "${local.name}-api"
  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.single.arn

  source_configuration {
    auto_deployments_enabled = true # a new :latest in ECR rolls the service
    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_access.arn
    }
    image_repository {
      image_repository_type = "ECR"
      image_identifier      = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
      image_configuration {
        port = "8000"
        runtime_environment_variables = {
          STORAGE_BACKEND      = "s3"
          S3_BUCKET            = aws_s3_bucket.data.bucket
          S3_PREFIX            = "chatgpt-dashboard"
          AWS_REGION           = var.aws_region
          DATA_DIR             = "/app/data"
          AUTH_MODE            = "google"
          AUTH_ALLOWED_DOMAINS = join(",", var.auth_allowed_domains)
          SESSION_SECURE       = "true"
          # BASE_URL is left unset: the CloudFront function forwards the public host in X-Forwarded-Host.
        }
        runtime_environment_secrets = { for name, p in aws_ssm_parameter.secret : name => p.arn }
      }
    }
  }

  instance_configuration {
    cpu               = var.apprunner_cpu
    memory            = var.apprunner_memory
    instance_role_arn = aws_iam_role.apprunner_instance.arn
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/health"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 5
  }

  depends_on = [aws_iam_role_policy_attachment.apprunner_access]
}
