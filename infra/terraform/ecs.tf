# The API as one Fargate task. It has no load balancer: API Gateway reaches it through a VPC link
# and finds it in Cloud Map (api_gateway.tf). The service runs exactly one task because imports
# rewrite the normalized files as a whole.

# CloudFront adds this secret to every API request and the API rejects requests without it,
# so the public API Gateway endpoint cannot be used to go around the CDN.
resource "random_password" "origin_verify" {
  length  = 32
  special = false
}

resource "aws_ssm_parameter" "origin_verify" {
  name  = "${local.ssm_prefix}/ORIGIN_VERIFY_SECRET"
  type  = "SecureString"
  value = random_password.origin_verify.result
}

# --- ECS: cluster, roles, task definition, service -----------------------------

resource "aws_ecs_cluster" "api" {
  name = local.name
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name}/api"
  retention_in_days = var.log_retention_days
}

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

# Execution role: pull the image, write logs, read the SSM secrets at task start.
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
    resources = concat([for p in aws_ssm_parameter.secret : p.arn], [aws_ssm_parameter.origin_verify.arn])
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "ssm-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
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
  # No s3:prefix condition: reading a key that does not exist yet (first import, no saved state)
  # only returns "not found" when the caller may list the bucket; with a prefix condition S3
  # answers 403 AccessDenied instead and the API fails with 500. The bucket holds nothing else.
  statement {
    sid       = "DataList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "data-bucket"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# Only API Gateway's VPC link may talk to the task.
resource "aws_security_group" "task" {
  name        = "${local.name}-api"
  description = "API task: ingress from the API Gateway VPC link only"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.vpc_link.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # A changed name or description replaces the group; the running task must move to the new one first.
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_cpu
  memory                   = var.ecs_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name         = "api"
    image        = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
    essential    = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = [for name, value in {
      STORAGE_BACKEND      = "s3"
      S3_BUCKET            = aws_s3_bucket.data.bucket
      S3_PREFIX            = "chatgpt-dashboard"
      AWS_REGION           = var.aws_region
      DATA_DIR             = "/app/data"
      AUTH_MODE            = "google"
      AUTH_ALLOWED_DOMAINS = join(",", var.auth_allowed_domains)
      SESSION_SECURE       = "true"
      BASE_URL             = local.dashboard_url # the public address; OAuth callbacks point back here
    } : { name = name, value = value }]
    secrets = concat(
      [for name, p in aws_ssm_parameter.secret : { name = name, valueFrom = p.arn }],
      [{ name = "ORIGIN_VERIFY_SECRET", valueFrom = aws_ssm_parameter.origin_verify.arn }],
    )
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 20
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "${local.name}-api"
  cluster         = aws_ecs_cluster.api.id
  task_definition = aws_ecs_task_definition.api.arn
  launch_type     = "FARGATE"
  desired_count   = 1

  # Replace the single task in place (brief downtime) rather than run two at once.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  force_new_deployment               = true

  network_configuration {
    subnets          = var.task_subnet_ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true # public subnets, no NAT; ingress is still limited to the VPC link
  }

  # Registers the task's address and port in Cloud Map, where API Gateway looks it up.
  service_registries {
    registry_arn = aws_service_discovery_service.api.arn
    port         = 8000
  }

  depends_on = [aws_iam_role_policy_attachment.execution, aws_iam_role_policy.execution_secrets, aws_iam_role_policy.task]
}
