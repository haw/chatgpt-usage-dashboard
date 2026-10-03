# The API as one Fargate task behind an existing, shared Application Load Balancer.
#
# Nothing new is paid for except the task: the ALB gets a certificate for the API's own host
# name, a host-name listener rule and a target group. The rule also requires a secret header
# that only CloudFront sends, so the API cannot be reached by going around the CDN.
# The service runs exactly one task because imports rewrite the normalized files as a whole.

data "aws_lb" "shared" {
  arn = var.shared_alb_arn
}

data "aws_lb_listener" "https" {
  load_balancer_arn = var.shared_alb_arn
  port              = 443
}

resource "random_password" "origin_verify" {
  length  = 32
  special = false
}

# --- Name and certificate for the API origin on the shared ALB ---------------

resource "aws_route53_record" "api" {
  zone_id = var.route53_zone_id
  name    = var.api_hostname
  type    = "A"

  alias {
    name                   = data.aws_lb.shared.dns_name
    zone_id                = data.aws_lb.shared.zone_id
    evaluate_target_health = false
  }
}

resource "aws_acm_certificate" "api" {
  domain_name       = var.api_hostname
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "api_validation" {
  for_each = {
    for option in aws_acm_certificate.api.domain_validation_options : option.domain_name => {
      name   = option.resource_record_name
      record = option.resource_record_value
      type   = option.resource_record_type
    }
  }

  zone_id         = var.route53_zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 60
  records         = [each.value.record]
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "api" {
  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [for record in aws_route53_record.api_validation : record.fqdn]
}

resource "aws_lb_listener_certificate" "api" {
  listener_arn    = data.aws_lb_listener.https.arn
  certificate_arn = aws_acm_certificate_validation.api.certificate_arn
}

# --- Target group and listener rule --------------------------------------------

resource "aws_lb_target_group" "api" {
  name        = substr("${local.name}-api", 0, 32)
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = data.aws_lb.shared.vpc_id

  health_check {
    path                = "/health"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  deregistration_delay = 10
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = data.aws_lb_listener.https.arn

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    host_header {
      values = [var.api_hostname]
    }
  }

  condition {
    http_header {
      http_header_name = "x-origin-verify"
      values           = [random_password.origin_verify.result]
    }
  }
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
    resources = [for p in aws_ssm_parameter.secret : p.arn]
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

# Only the shared ALB may talk to the task.
resource "aws_security_group" "task" {
  name        = "${local.name}-api-task"
  description = "API task: ingress from the shared ALB only"
  vpc_id      = data.aws_lb.shared.vpc_id

  dynamic "ingress" {
    for_each = data.aws_lb.shared.security_groups
    content {
      from_port       = 8000
      to_port         = 8000
      protocol        = "tcp"
      security_groups = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
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
      # BASE_URL stays unset: the CloudFront function forwards the public host in X-Forwarded-Host.
    } : { name = name, value = value }]
    secrets = [for name, p in aws_ssm_parameter.secret : { name = name, valueFrom = p.arn }]
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
  health_check_grace_period_seconds  = 60
  force_new_deployment               = true

  network_configuration {
    subnets          = length(var.task_subnet_ids) > 0 ? var.task_subnet_ids : tolist(data.aws_lb.shared.subnets)
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true # the ALB's public subnets, no NAT; ingress is still limited to the ALB
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener_rule.api, aws_iam_role_policy_attachment.execution, aws_iam_role_policy.execution_secrets, aws_iam_role_policy.task]
}
