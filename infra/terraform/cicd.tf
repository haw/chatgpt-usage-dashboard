# Deploy pipeline, pulled from AWS: a CodeBuild project watches the GitHub repository and, on
# every push to the deploy branch, runs buildspec.yml (API image -> ECR, ECS rollout, React
# build -> S3, CloudFront invalidation). GitHub holds no AWS role, variables or secrets.

# The link to GitHub. A new connection starts as PENDING and must be authorised once in the
# AWS console (Developer Tools > Settings > Connections); Terraform cannot do the handshake.
resource "aws_codeconnections_connection" "github" {
  count = var.github_connection_arn == "" ? 1 : 0

  name          = substr("chatgpt-dashboard-${var.environment}", 0, 32)
  provider_type = "GitHub"
}

locals {
  github_connection_arn = var.github_connection_arn != "" ? var.github_connection_arn : aws_codeconnections_connection.github[0].arn
}

resource "aws_cloudwatch_log_group" "deploy" {
  name              = "/aws/codebuild/${local.name}-deploy"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "codebuild_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codebuild" {
  name               = "${local.name}-codebuild-deploy"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume.json
}

# What a deploy does: read the repository, push the API image, roll the service,
# publish the React build, invalidate the CDN. Nothing that changes infrastructure.
data "aws_iam_policy_document" "codebuild" {
  statement {
    sid       = "Logs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.deploy.arn}:*"]
  }
  statement {
    sid    = "GitHubSource"
    effect = "Allow"
    actions = [
      "codeconnections:GetConnection", "codeconnections:GetConnectionToken",
      "codestar-connections:GetConnection", "codestar-connections:GetConnectionToken",
    ]
    resources = [local.github_connection_arn]
  }
  statement {
    sid       = "EcrLogin"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid    = "EcrPush"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:DescribeImages",
    ]
    resources = [aws_ecr_repository.api.arn]
  }
  statement {
    sid       = "FrontendList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.frontend.arn]
  }
  statement {
    sid       = "FrontendWrite"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]
  }
  statement {
    sid       = "CdnInvalidate"
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
    resources = [aws_cloudfront_distribution.dashboard.arn]
  }
  statement {
    sid       = "EcsRollout"
    effect    = "Allow"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices"]
    resources = [aws_ecs_service.api.id]
  }
}

resource "aws_iam_role_policy" "codebuild" {
  name   = "deploy"
  role   = aws_iam_role.codebuild.id
  policy = data.aws_iam_policy_document.codebuild.json
}

resource "aws_codebuild_project" "deploy" {
  name          = "${local.name}-deploy"
  description   = "Deploys ${var.github_repository} (${var.deploy_branch}) to ${var.environment}."
  service_role  = aws_iam_role.codebuild.arn
  build_timeout = 30

  source {
    type            = "GITHUB"
    location        = "https://github.com/${var.github_repository}.git"
    buildspec       = "buildspec.yml"
    git_clone_depth = 1
    # The repository is public and the status link contains the AWS account id, so build
    # results are not reported back to GitHub; see them with `make deploy-status`.
    report_build_status = false

    auth {
      type     = "CODECONNECTIONS"
      resource = local.github_connection_arn
    }
  }
  source_version = var.deploy_branch

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    type            = "LINUX_CONTAINER"
    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/amazonlinux-x86_64-standard:5.0"
    privileged_mode = true # docker build

    environment_variable {
      name  = "ECR_REPOSITORY"
      value = aws_ecr_repository.api.repository_url
    }
    environment_variable {
      name  = "ECS_CLUSTER"
      value = aws_ecs_cluster.api.name
    }
    environment_variable {
      name  = "ECS_SERVICE"
      value = aws_ecs_service.api.name
    }
    environment_variable {
      name  = "FRONTEND_BUCKET"
      value = aws_s3_bucket.frontend.bucket
    }
    environment_variable {
      name  = "CLOUDFRONT_DISTRIBUTION_ID"
      value = aws_cloudfront_distribution.dashboard.id
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name = aws_cloudwatch_log_group.deploy.name
    }
  }

  depends_on = [aws_iam_role_policy.codebuild]
}

# Only pushes to the deploy branch start a build. Pull requests (including those from forks
# of this public repository) never do.
resource "aws_codebuild_webhook" "deploy" {
  project_name = aws_codebuild_project.deploy.name
  build_type   = "BUILD"

  filter_group {
    filter {
      type    = "EVENT"
      pattern = "PUSH"
    }
    filter {
      type    = "HEAD_REF"
      pattern = "^refs/heads/${var.deploy_branch}$"
    }
  }
}
