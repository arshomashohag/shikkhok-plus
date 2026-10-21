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
# **The count tests whether the OBJECT is null, not a value inside
# it.** Terraform knows at plan time whether the caller passed an
# object at all, even when the arn inside it is
# `(known after apply)`. `var.image_repository.arn == null` would NOT
# work -- that reads an unknown value, and count must be known at
# plan time. The distinction is the whole reason this is one object
# rather than separate arn and url inputs.
resource "aws_iam_role_policy" "ecr_pull" {
  count = var.image_repository == null ? 0 : 1

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
        Resource = var.image_repository.arn
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

# ---------------------------------------------------------------------
# The launch template and the group of one
# ---------------------------------------------------------------------
#
# **An ASG with desired_capacity 1, not an auto-scaler.** Nothing here
# scales: min, max and desired are all one. The group exists for a
# single property -- an instance that dies is replaced without a human
# -- and `main.tf` is explicit that one instance is the design.
#
# **No load balancer.** An ALB is roughly USD 16/month against a USD 50
# ceiling, for 100 teachers on one host. The instance registers its own
# DNS at boot instead, so CloudFront follows the replacement within one
# 60-second TTL.
#
# **No Elastic IP.** A replaced instance gets a new address, and
# re-attaching an EIP needs a lifecycle hook that can fail halfway and
# leave a running instance unreachable. Self-registration has nothing
# to re-attach.

resource "aws_launch_template" "app" {
  name_prefix   = "${var.name_prefix}-"
  image_id      = data.aws_ami.ubuntu_arm64.id
  instance_type = var.instance_type

  vpc_security_group_ids = [aws_security_group.app.id]

  iam_instance_profile {
    name = aws_iam_instance_profile.instance.name
  }

  # **No key_name.** A key pair would be a way in that bypasses IAM
  # and CloudTrail, which is what Session Manager exists to replace.

  user_data = base64encode(templatefile("${path.module}/user_data.sh.tftpl", {
    origin_secret      = random_password.origin_secret.result
    ecr_repository_url = try(var.image_repository.url, "")
    ecr_registry       = try(split("/", var.image_repository.url)[0], "")
    name_prefix        = var.name_prefix
    aws_region         = var.aws_region
    dns_zone_id        = var.dns_zone_id
    origin_fqdn        = var.origin_fqdn
    # Read from git at apply time, so a replaced instance does not
    # depend on a previous deploy having written this file to a disk
    # that no longer exists.
    compose_file = file("${path.root}/../deploy/docker-compose.staging.yml")

    # **The connection string is built HERE, not on the host.** The
    # endpoint and password come from the database module, so the
    # instance never has to assemble them from parts it might get
    # wrong -- and the password reaches the host only through
    # user_data, which is itself only readable from IMDS with a valid
    # IMDSv2 token.
    database_url = (
      var.database_endpoint == null
      ? ""
      : "postgresql+psycopg://shikkhok:${var.database_password}@${var.database_endpoint}/shikkhokplus"
    )
  }))

  block_device_mappings {
    device_name = "/dev/sda1"

    ebs {
      volume_size = var.root_volume_gb
      volume_type = "gp3"
      # project.md mandates encryption at rest for children's data,
      # and in Phase 1 the database lives on this volume.
      encrypted             = true
      delete_on_termination = true
    }
  }

  metadata_options {
    # IMDSv2 required. v1 is reachable by any SSRF in the application
    # and hands out the instance's IAM credentials.
    #
    # The hop limit is 2, not 1: a request from inside a Docker
    # container traverses one extra network hop, and at 1 the
    # container cannot reach IMDS at all. The boot script runs on the
    # host, but the application does not.
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 2
  }

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "${var.name_prefix}-app" }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_autoscaling_group" "app" {
  name_prefix         = "${var.name_prefix}-"
  vpc_zone_identifier = var.subnet_ids

  # **Pinned at one, deliberately.** Not a scaling range that happens
  # to start at one: min and max are both one, so no policy and no
  # accidental edit can produce two hosts. Two would each run their
  # own containerised Postgres and each register the same DNS name.
  min_size         = 1
  max_size         = 1
  desired_capacity = 1

  # EC2 health only. An ELB health check would need an ELB; the
  # instance's own boot script already fails loudly when the app does
  # not answer, and CloudFront surfaces an origin that stops
  # responding.
  health_check_type         = "EC2"
  health_check_grace_period = 300

  launch_template {
    id      = aws_launch_template.app.id
    version = "$Latest"
  }

  instance_refresh {
    # A user_data change replaces the instance, which in Phase 1
    # destroys the containerised database with it. Manual, so that is
    # always a decision rather than a side effect of an apply.
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 0
    }
    triggers = []
  }

  tag {
    key                 = "Name"
    value               = "${var.name_prefix}-app"
    propagate_at_launch = true
  }

  lifecycle {
    create_before_destroy = true
  }
}

# The instance id, for SSM. Looked up rather than held, because the
# ASG replaces instances and a stored id goes stale.
data "aws_instances" "app" {
  instance_tags = { Name = "${var.name_prefix}-app" }

  instance_state_names = ["running"]

  depends_on = [aws_autoscaling_group.app]
}

# Reading the deployment state at boot, and writing the instance's own
# DNS record. Both are scoped: one parameter, one zone.
resource "aws_iam_role_policy" "self_registration" {
  name = "self-registration"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = [
          aws_ssm_parameter.image_tag.arn,
          aws_ssm_parameter.runtime_env.arn,
        ]
      },
      {
        # Decrypting the SecureString. The account default key, so no
        # key policy to manage; scoped by the ViaService condition so
        # this role cannot decrypt anything but SSM parameters.
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "ssm.${var.aws_region}.amazonaws.com"
          }
        }
      },
      {
        # **Scoped to this zone, and this zone only.** A host that can
        # write any Route53 record is a host that can repoint someone
        # else's domain if it is ever compromised.
        Effect   = "Allow"
        Action   = ["route53:ChangeResourceRecordSets"]
        Resource = "arn:aws:route53:::hostedzone/${var.dns_zone_id}"
      },
      {
        # Read-only, and unscopable: Route53 does not support resource
        # scoping on these, so they are account-level by design.
        Effect   = "Allow"
        Action   = ["route53:GetChange", "route53:ListResourceRecordSets"]
        Resource = "*"
      },
    ]
  })
}
