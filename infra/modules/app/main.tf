# The application host.
#
# **EC2 with SSM Session Manager, and port 22 closed entirely.**
#
# The previous design was Lightsail with SSH restricted to an operator
# IP held as a CI secret. That was wrong, and the reason is worth
# keeping: a home IP is dynamic, so recovering access after a router
# restart meant editing a GitHub secret, dispatching a workflow,
# waiting for an approval and waiting for an apply. That friction is
# exactly what makes somebody widen the rule to 0.0.0.0/0 once "just
# to get in" -- after which it stays. A control painful to use
# correctly gets used incorrectly.
#
# Session Manager removes the question. There is no inbound port, no
# key pair, no IP to track. Access is an AWS API call authenticated by
# IAM, and `team.md` asks for production access to be "named, logged
# and bounded" -- CloudTrail records who opened a session and when,
# which nothing enforced before.
#
# **t4g.small is Graviton (arm64).** Cheaper per vCPU than x86, and the
# backend image must be built for arm64 -- noted here because a
# silently-x86 image fails at `docker run` with an exec format error
# that does not mention architecture.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# The CDN-to-origin shared secret. CloudFront's 214 origin-facing CIDRs
# do not fit a practical security-group rule either, so the header
# check in nginx remains how "through the CDN only" is enforced.
resource "random_password" "origin_secret" {
  length  = 48
  special = false
}

data "aws_ami" "ubuntu_arm64" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ---------------------------------------------------------------------
# IAM: what makes SSM work
# ---------------------------------------------------------------------

resource "aws_iam_role" "instance" {
  name = "${var.name_prefix}-instance"
  # **The path is a permission boundary, not decoration.** The CI role
  # can create and attach roles only under /shikkhokplus/, so it
  # cannot touch an unrelated role and cannot modify itself -- the CI
  # role lives at the IAM root path.
  path = "/shikkhokplus/"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

# The AWS-managed policy, not a hand-rolled one. SSM's required action
# set changes with the agent, and a hand-maintained copy drifts into
# "Session Manager stopped working after an agent update" with no
# obvious cause.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Pulling the application image. **Two statements, because ECR's
# auth action cannot be scoped to a repository**:
# GetAuthorizationToken is account-level by design, so restricting it
# to a resource produces a policy that silently denies every pull.
# The layer-reading actions ARE scoped, and those are the ones that
# decide which images this host can actually read.
#
# **`count` keys off a static bool, not off the ARN.** Deriving it as
# `var.ecr_repository_arn == null ? 0 : 1` fails the plan with
# "Invalid count argument": the ARN comes from a repository that does
# not exist yet on a first apply, so its value is unknown at plan
# time and count must be known then. The caller states the intent
# instead, which it knows statically.
resource "aws_iam_role_policy" "ecr_pull" {
  count = var.enable_ecr_pull ? 1 : 0

  name = "ecr-pull"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability",
        ]
        Resource = var.ecr_repository_arn
      },
    ]
  })
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.name_prefix}-instance"
  path = "/shikkhokplus/"
  role = aws_iam_role.instance.name
}

# ---------------------------------------------------------------------
# Network boundary
# ---------------------------------------------------------------------

resource "aws_security_group" "app" {
  name        = "${var.name_prefix}-app"
  description = "App host: inbound web only, no SSH"
  vpc_id      = var.vpc_id

  tags = { Name = "${var.name_prefix}-app" }
}

# **No ingress rule for port 22 exists in this file.** That is the
# whole point: there is no SSH rule to misconfigure, widen or forget to
# close, because there is no SSH.

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.app.id
  description       = "HTTPS from CloudFront; the origin secret is the real gate"

  # Open, because CloudFront publishes 214 origin-facing ranges and
  # keeping that list current in a security group is a maintenance
  # burden that fails silently when AWS adds a range. nginx rejects
  # anything without the shared secret header.
  cidr_ipv4   = "0.0.0.0/0"
  from_port   = 443
  to_port     = 443
  ip_protocol = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.app.id
  description       = "HTTP, redirected to HTTPS. A timeout reads as an outage"

  cidr_ipv4   = "0.0.0.0/0"
  from_port   = 80
  to_port     = 80
  ip_protocol = "tcp"
}

# Outbound: everything. The host needs it for the SMS gateway, package
# updates, and -- critically -- for the SSM agent, which reaches AWS
# over an OUTBOUND connection. That is why no inbound port is needed
# for a shell.
resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.app.id
  description       = "Outbound: SMS gateway, updates, and the SSM agent"

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "-1"
}

# ---------------------------------------------------------------------
# The instance
# ---------------------------------------------------------------------

resource "aws_instance" "app" {
  ami           = data.aws_ami.ubuntu_arm64.id
  instance_type = var.instance_type
  subnet_id     = var.subnet_id

  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name

  # **No key_name.** A key pair would be a way in that bypasses IAM
  # and CloudTrail, which is the thing Session Manager exists to
  # replace.

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    origin_secret = random_password.origin_secret.result
    # Empty for a host with no registry access, which keeps the
    # template valid rather than failing on an unset variable.
    ecr_repository_url = coalesce(var.ecr_repository_url, "")
    ecr_registry = (
      var.ecr_repository_url == null
      ? ""
      : split("/", var.ecr_repository_url)[0]
    )
  })
  # Changing user_data does NOT replace the instance. It runs once at
  # first boot; replacing a running host to re-run a provisioning
  # script would destroy the containerised database with it.
  user_data_replace_on_change = false

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
    # The database lives on this volume. project.md mandates
    # encryption at rest for children's data, and an unencrypted root
    # volume would hold it in plaintext.
    encrypted = true
  }

  metadata_options {
    # IMDSv2 required. v1 is reachable by any SSRF in the application
    # and hands out the instance's IAM credentials; v2's token
    # requirement makes that a much harder attack.
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1
  }

  tags = { Name = "${var.name_prefix}-app" }
}

# An Elastic IP, so the address survives a stop/start. CloudFront
# points here, and the SMS gateway may need it allowlisted.
resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"

  tags = { Name = "${var.name_prefix}-app-ip" }
}
