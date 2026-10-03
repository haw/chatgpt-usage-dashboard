# The API on ECS Express Mode (AWS's successor to App Runner, which stopped taking new
# customers in April 2026). One Express service provisions the Fargate task, an ALB with an
# HTTPS listener (host-header routing), target group, security groups, auto scaling and the
# log group. We pin it to a single task: imports rewrite the normalized files as a whole.

resource "aws_ecs_cluster" "api" {
  name = local.name
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name}/api"
  retention_in_days = var.log_retention_days
}

# Execution role: pull the image, write logs, read the SSM secrets at task start.
data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    effect    = "Allow"
    actions   = ["ssm:GetParameters", "ssm:GetParameter"]
    resources = [for p in aws_ssm_parameter.secret : p.arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "ssm-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# Infrastructure role: lets ECS create and manage the ALB, target groups and security groups.
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "infrastructure" {
  name               = "${local.name}-ecs-infrastructure"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "infrastructure" {
  role       = aws_iam_role.infrastructure.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"
}

# Task role: what the running API may touch — the data bucket only.
resource "aws_iam_role" "task" {
  name               = "${local.name}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "task" {
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
}

resource "aws_iam_role_policy" "task" {
  name   = "data-bucket"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

resource "aws_ecs_express_gateway_service" "api" {
  service_name            = "${local.name}-api"
  cluster                 = aws_ecs_cluster.api.name
  execution_role_arn      = aws_iam_role.execution.arn
  infrastructure_role_arn = aws_iam_role.infrastructure.arn
  task_role_arn           = aws_iam_role.task.arn
  cpu                     = var.ecs_cpu
  memory                  = var.ecs_memory
  health_check_path       = "/health"
  wait_for_steady_state   = true

  primary_container {
    image          = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
    container_port = 8000

    aws_logs_configuration {
      log_group         = aws_cloudwatch_log_group.api.name
      log_stream_prefix = "api"
    }

    dynamic "environment" {
      for_each = {
        STORAGE_BACKEND      = "s3"
        S3_BUCKET            = aws_s3_bucket.data.bucket
        S3_PREFIX            = "chatgpt-dashboard"
        AWS_REGION           = var.aws_region
        DATA_DIR             = "/app/data"
        AUTH_MODE            = "google"
        AUTH_ALLOWED_DOMAINS = join(",", var.auth_allowed_domains)
        SESSION_SECURE       = "true"
        # BASE_URL stays unset: the CloudFront function forwards the public host in X-Forwarded-Host.
      }
      content {
        name  = environment.key
        value = environment.value
      }
    }

    dynamic "secret" {
      for_each = aws_ssm_parameter.secret
      content {
        name       = secret.key
        value_from = secret.value.arn
      }
    }
  }

  # Exactly one task (see the note at the top).
  scaling_target {
    min_task_count = 1
    max_task_count = 1
  }

  # The deploy workflow moves the service to each new image tag; Terraform only sets the initial one.
  lifecycle {
    ignore_changes = [primary_container[0].image]
  }

  depends_on = [
    aws_iam_role_policy_attachment.execution,
    aws_iam_role_policy.execution_secrets,
    aws_iam_role_policy_attachment.infrastructure,
    aws_iam_role_policy.task,
  ]
}

locals {
  # The service's own HTTPS endpoint (host-header routed on the shared ALB); CloudFront's origin.
  api_endpoint = aws_ecs_express_gateway_service.api.ingress_paths[0].endpoint
  api_host     = trimsuffix(replace(replace(local.api_endpoint, "https://", ""), "http://", ""), "/")
}
