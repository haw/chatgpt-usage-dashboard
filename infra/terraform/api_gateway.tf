# How CloudFront reaches the API: API Gateway (HTTP API) -> VPC link -> the Fargate task, located
# through Cloud Map. No load balancer is involved, so nothing is paid for one and the API does not
# depend on anyone else's. API Gateway is billed per request (a few cents a month at this scale).

# Where the running task is registered. API Gateway needs the port as well as the address, which
# ECS only publishes with SRV records, hence a private DNS namespace.
resource "aws_service_discovery_private_dns_namespace" "api" {
  name        = "${local.name}.internal"
  description = "Service discovery for ${local.name}"
  vpc         = var.vpc_id
}

resource "aws_service_discovery_service" "api" {
  name = "api"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.api.id
    routing_policy = "MULTIVALUE"

    dns_records {
      type = "SRV"
      ttl  = 10
    }
  }
  # No health check block: ECS registers the task when it starts and removes it when it stops.
  # (An empty health_check_custom_config is not stored by the provider and would replace the
  # service on every apply.)
}

# The network interfaces API Gateway uses inside the VPC.
resource "aws_security_group" "vpc_link" {
  name        = "${local.name}-api-vpc-link"
  description = "API Gateway VPC link: may only call the API task"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_apigatewayv2_vpc_link" "api" {
  name               = "${local.name}-api"
  subnet_ids         = var.task_subnet_ids
  security_group_ids = [aws_security_group.vpc_link.id]
}

resource "aws_apigatewayv2_api" "api" {
  name          = "${local.name}-api"
  description   = "Private integration to the dashboard API; only meant to be called by CloudFront"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = aws_service_discovery_service.api.arn
  connection_type        = "VPC_LINK"
  connection_id          = aws_apigatewayv2_vpc_link.api.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 30000
}

# Every path goes to the API unchanged.
resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  # The endpoint is public; cap what anyone can send (far above what a few analysts need).
  default_route_settings {
    throttling_rate_limit  = 50
    throttling_burst_limit = 100
  }
}
