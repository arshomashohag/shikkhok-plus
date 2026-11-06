# The performance-test data seeder: a Lambda function. **Staging only,
# and off by default** -- the root refuses `enable_seeder` in production
# at plan time, and the function refuses again at run time when
# SHIKKHOKPLUS_ENVIRONMENT is production.
#
# What it does is `app/seed`: given a teacher's phone number, it writes
# three months of realistic history into that account through the
# application's own services. Invoke it as deploy/README.md describes.
#
# Four decisions worth reading before changing anything:
#
# 1. **The image is the API's image.** Same repository, same commit SHA,
#    same lockfile. The function overrides only the command, to a
#    stdlib-only Lambda Runtime API loop (app/seed/lambda_runtime.py),
#    so there is no second base image to pin and no second dependency
#    set. deploy.yml moves the function to each new release after the
#    smoke passes, so the seeder never writes against a schema its code
#    predates. That is why `image_uri` is ignored below: Terraform sets
#    the first tag, deploys own it afterwards -- the same two-writer
#    split as the image-tag parameter.
#
# 2. **It reaches the database and nothing else.** Its security group
#    has ONE egress rule, to the database's group on 5432, and the
#    database admits this group by reference, not by CIDR. In public
#    subnets a Lambda interface still gets no public address, so it has
#    no route to the internet either: nothing it could exfiltrate to.
#
# 3. **It connects as the restricted `shikkhok_app` role**, never the
#    owner. Row-level security applies to it exactly as to the API, which
#    is the point: it can write only what the application can.
#
# 4. **The credential is an environment variable, and that is a stated
#    trade-off, not an oversight.** The function cannot read SSM: it is
#    in the VPC, there is no NAT gateway (USD 32/month), and an SSM
#    interface endpoint (about USD 7/month) would also repoint SSM
#    resolution for the app hosts, whose boot depends on it. So the URL
#    is set on the function, encrypted at rest under the account's
#    `aws/lambda` key -- and readable in plaintext by anyone holding
#    lambda:GetFunctionConfiguration on it, the same exposure OPS-4
#    removed from user_data for the hosts. Accepted here because the
#    function exists only in staging, only while `enable_seeder` is on,
#    and the role is the restricted one. The way out, if that changes, is
#    RDS IAM authentication: a token minted from the function's own role,
#    no stored secret at all, at the cost of a second database login
#    role and enabling IAM auth on the instance.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

locals {
  function_name = "${var.name_prefix}-seeder"
  function_arn  = "arn:aws:lambda:${var.aws_region}:${var.account_id}:function:${local.function_name}"
}

# ---------------------------------------------------------------------
# Network: one way out, to the database.
# ---------------------------------------------------------------------

resource "aws_security_group" "seeder" {
  count = var.enabled ? 1 : 0

  name        = local.function_name
  description = "Seeder Lambda: egress to the database only"
  vpc_id      = var.vpc_id

  # No inline rules. Terraform deletes AWS's default allow-all egress
  # from a group it creates, and the one rule below is standalone --
  # mixing inline and standalone rules on one group makes each apply
  # remove the other's.

  tags = { Role = "seeder" }
}

resource "aws_vpc_security_group_egress_rule" "to_database" {
  count = var.enabled ? 1 : 0

  security_group_id            = aws_security_group.seeder[0].id
  description                  = "PostgreSQL, to the database security group ONLY"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = var.database_security_group_id
}

# ---------------------------------------------------------------------
# Identity: network interfaces and its own log group, nothing more.
# ---------------------------------------------------------------------

resource "aws_iam_role" "seeder" {
  count = var.enabled ? 1 : 0

  name = local.function_name
  # Under /shikkhokplus/ and carrying the workload boundary, as every
  # role the CI role creates must [OPS-2].
  path                 = "/shikkhokplus/"
  permissions_boundary = var.permissions_boundary_arn

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
      # Only this account's Lambda service may assume it -- the
      # confused-deputy guard.
      Condition = { StringEquals = { "aws:SourceAccount" = var.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "seeder" {
  count = var.enabled ? 1 : 0

  name = "seeder"
  role = aws_iam_role.seeder[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # What AWSLambdaVPCAccessExecutionRole grants, listed rather
        # than attached: the CI role may attach only the policies
        # bootstrap names, and listing them keeps the grant readable.
        # EC2 does not scope these by resource.
        Sid    = "VpcNetworkInterfaces"
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeSubnets",
          "ec2:DeleteNetworkInterface",
          "ec2:AssignPrivateIpAddresses",
          "ec2:UnassignPrivateIpAddresses",
        ]
        Resource = "*"
      },
      {
        Sid      = "OwnLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.seeder[0].arn}:*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "seeder" {
  count = var.enabled ? 1 : 0

  # Under /shikkhokplus/, not /aws/lambda/: the workload boundary and
  # the CI role's grants are both scoped to this project's log groups.
  name              = "/shikkhokplus/${var.name_prefix}/seeder"
  retention_in_days = var.log_retention_days
}

# **Lambda pulls the image itself**, so the repository must say it may
# -- and only for this function. Created explicitly rather than left
# for Lambda to add on first create, so the grant is in code and in
# review. The repository had no policy before this one.
resource "aws_ecr_repository_policy" "lambda_pull" {
  count = var.enabled ? 1 : 0

  repository = var.image_repository.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "LambdaPullForTheSeederOnly"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
      Condition = { StringLike = { "aws:sourceArn" = local.function_arn } }
    }]
  })
}

# ---------------------------------------------------------------------
# The function
# ---------------------------------------------------------------------

resource "aws_lambda_function" "seeder" {
  count = var.enabled ? 1 : 0

  function_name = local.function_name
  description   = "Seeds a teacher account with realistic test history. Staging only."
  role          = aws_iam_role.seeder[0].arn

  package_type  = "Image"
  image_uri     = "${var.image_repository.url}:${var.image_tag}"
  architectures = ["arm64"] # the image is built for the t4g hosts

  image_config {
    command           = ["python", "-m", "app.seed.lambda_runtime"]
    working_directory = "/srv"
  }

  # A three-month seed takes well under a minute against RDS; the
  # ceiling is Lambda's own, so a twelve-month run still finishes.
  timeout     = 900
  memory_size = 1024

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [aws_security_group.seeder[0].id]
  }

  environment {
    variables = {
      SHIKKHOKPLUS_ENVIRONMENT  = var.environment
      SHIKKHOKPLUS_DATABASE_URL = var.database_url
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.seeder[0].name
  }

  lifecycle {
    # deploy.yml moves the function to each release; an apply resetting
    # it to the tag it was created with would roll the seeder back
    # behind the schema.
    ignore_changes = [image_uri]

    precondition {
      condition     = var.image_tag != "none"
      error_message = "Nothing has been deployed yet (image-tag is \"none\"). Deploy once, then enable the seeder."
    }
  }

  depends_on = [
    aws_ecr_repository_policy.lambda_pull,
    aws_iam_role_policy.seeder,
    aws_cloudwatch_log_group.seeder,
  ]
}
