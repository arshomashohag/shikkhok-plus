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

  # **The ceiling, created by bootstrap** [OPS-2]. The CI role may
  # create or extend a role under /shikkhokplus/ only when it carries
  # this boundary, so this line is what lets the apply succeed at all --
  # and what caps this role at an app host's calls whatever is attached
  # to it later.
  permissions_boundary = var.permissions_boundary_arn

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

# **The CloudFront origin-facing prefix list, maintained by AWS.**
#
# An earlier version left 443 open to 0.0.0.0/0, reasoning that
# CloudFront publishes 214 origin-facing ranges and keeping that list
# current in a security group fails silently when AWS adds one. That
# reasoning was right about the ranges and wrong about the options:
# AWS publishes them AS a managed prefix list, which a rule
# references by id and AWS keeps current. It is free.
#
# **It does NOT count as one rule.** A prefix list consumes its ENTRY
# COUNT against the security group's rule quota -- 49 entries for the
# IPv4 list here, against a default limit of 60. An earlier version
# added the IPv6 list beside it (38 more) and the apply failed with
# RulesPerSecurityGroupLimitExceeded: 87 rules into a 60 quota.
#
# **Only the IPv4 list, because the origin has no IPv6 address.** The
# instance registers an A record and no AAAA, so CloudFront cannot
# reach it over IPv6 whatever the distribution's viewer-facing
# `is_ipv6_enabled` says -- that setting governs the VIEWER hop, not
# the origin hop. The IPv6 rule was 38 rules of pure waste.
#
# So the shared-secret header nginx checks is now the SECOND layer
# rather than the only one. A direct request to the instance's
# address is refused by the security group and never reaches nginx at
# all.
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.app.id
  description       = "HTTPS from CloudFront only"

  prefix_list_id = data.aws_ec2_managed_prefix_list.cloudfront.id
  from_port      = 443
  to_port        = 443
  ip_protocol    = "tcp"
}

# **No port 80 rule.** It existed so a plain-http request got a
# redirect rather than a timeout, which reads as an outage. But
# CloudFront talks to this origin over https only, so the rule served
# nobody except someone hitting the instance address directly -- and
# that is exactly what this change closes.

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

  # **Comments stripped at render, kept in the file.** They were 54%
  # of the script -- 7.6KB of explanation shipped to every instance,
  # against a hard 16KB user_data limit the apply had already hit.
  # The reasoning belongs in the repository, not in the launch
  # template.
  #
  # Whole-line comments only, and never the shebang: an inline `#`
  # may be inside a string, and a heredoc body is content rather than
  # script.
  user_data = base64encode(join("\n", [
    for line in split("\n", templatefile("${path.module}/user_data.sh.tftpl", {
      # **No secret is passed here** [OPS-4]. The origin secret and the
      # database credentials used to be interpolated into this script,
      # where ec2:DescribeLaunchTemplateVersions and IMDS both hand them
      # out in plaintext. The host now reads them from SSM at boot --
      # see secrets.tf -- and this template sees only parameter paths
      # derived from name_prefix.
      ecr_repository_url = try(var.image_repository.url, "")
      ecr_registry       = try(split("/", var.image_repository.url)[0], "")
      name_prefix        = var.name_prefix
      aws_region         = var.aws_region
      dns_zone_id        = var.dns_zone_id
      origin_fqdn        = var.origin_fqdn
      # Read from git at apply time, so a replaced instance does not
      # depend on a previous deploy having written this file to a disk
      # that no longer exists.
      config_bucket = aws_s3_bucket.config.id
      # The boot script answers this hook once the host is ready.
      lifecycle_hook_name = local.lifecycle_hook_name
    }))
    : line if !startswith(trimspace(line), "#") || startswith(trimspace(line), "#!")
  ]))

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
    # **Hop limit 1, so no container can reach IMDS at all** [OPS-4].
    # It was 2, on the reasoning that the application runs in a
    # container -- but nothing in the container calls AWS: the image
    # carries no AWS SDK, and every AWS call (SSM reads, ECR pulls via
    # the credential helper, Route53, S3, the awslogs driver in dockerd)
    # is made by a HOST process. At 2, an SSRF in the API could fetch the
    # instance role's credentials and the user data; at 1 the IMDSv2
    # token response dies one hop short of any container.
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1
    # So the boot script can read its own group's name from the
    # aws:autoscaling:groupName tag to answer the lifecycle hook. The
    # launch template cannot name the group that uses it.
    instance_metadata_tags = "enabled"
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

  # **Desired one, with room for one more DURING A REPLACEMENT only.**
  #
  # This was min = max = 1 so that nothing could produce two hosts,
  # because two would each have run their own containerised Postgres.
  # The database is RDS now and two hosts share it, so that reason is
  # gone -- and max = 1 is what forced every deploy to terminate the
  # only host before launching its replacement, an outage on every
  # release with nothing to fall back to [OPS-6]. No scaling policy
  # exists, so desired stays one; max = 2 is used only by the
  # launch-before-terminate replacement below.
  min_size         = 1
  max_size         = 2
  desired_capacity = 1

  # EC2 health, plus the launch lifecycle hook below as the readiness
  # gate. An ELB health check would need an ELB (USD 16/month); the
  # hook gives the same "not in service until it serves" property for
  # free, because the boot script answers it only after the origin
  # answers /health over verified TLS.
  health_check_type         = "EC2"
  health_check_grace_period = 300

  # **Launch before terminate, for EVERY replacement** -- a failed host
  # replaced by the ASG as well as a deploy's refresh.
  instance_maintenance_policy {
    min_healthy_percentage = 100
    max_healthy_percentage = 200
  }

  # CloudWatch group metrics, free at this granularity: the alarm on
  # "no host in service" reads GroupInServiceInstances.
  enabled_metrics = ["GroupInServiceInstances", "GroupPendingInstances"]

  launch_template {
    id      = aws_launch_template.app.id
    version = "$Latest"
  }

  instance_refresh {
    # Started by the deploy workflow, never by an apply: `triggers` is
    # empty and the launch template is referenced as $Latest, so a
    # template change alone does not roll the host. These preferences
    # apply only if a refresh is ever started from Terraform; the
    # workflow passes the same values explicitly.
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 100
      max_healthy_percentage = 200
      instance_warmup        = 120
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

# **The readiness gate** [OPS-6]. Every launch waits here, out of
# service, until the boot script completes the action with CONTINUE --
# after migrating, starting the API and proving the origin answers
# /health over verified TLS. ABANDON, or silence for 20 minutes, and
# the ASG terminates the new instance; during a refresh the old one is
# still serving, because nothing is terminated until its replacement
# is in service.
#
# 20 minutes covers a cold boot -- apt, the AWS CLI, an image pull and
# the migrations -- with margin; a boot that takes longer than that has
# hung.
#
# A separate resource rather than `initial_lifecycle_hook`, which the
# provider applies only when CREATING a group: the existing staging
# group would never have received it.
locals {
  lifecycle_hook_name = "${var.name_prefix}-ready"
}

resource "aws_autoscaling_lifecycle_hook" "ready" {
  name                   = local.lifecycle_hook_name
  autoscaling_group_name = aws_autoscaling_group.app.name
  lifecycle_transition   = "autoscaling:EC2_INSTANCE_LAUNCHING"
  heartbeat_timeout      = 1200
  default_result         = "ABANDON"
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
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = local.boot_parameter_arns
      },
      {
        # The compose file, which used to be baked into user_data
        # until the script crossed EC2's 16KB limit. Scoped to this
        # host's own prefix.
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.config.arn}/*"
      },
      {
        # **The persisted origin certificate** [OPS-8]. Write access to
        # the tls/ prefix only, so the host can save a renewed lineage
        # and cannot overwrite the compose file Terraform uploads.
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.config.arn}/tls/*"
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
        # Answering its own launch lifecycle hook [OPS-6]. Scoped to
        # this host's group by name prefix; the ARN carries a generated
        # id the policy cannot know, hence the wildcard before it.
        Effect   = "Allow"
        Action   = ["autoscaling:CompleteLifecycleAction"]
        Resource = "arn:aws:autoscaling:${var.aws_region}:${var.account_id}:autoScalingGroup:*:autoScalingGroupName/${var.name_prefix}-*"
      },
      {
        # **Scoped to this zone, and this zone only.** A host that can
        # write any Route53 record is a host that can repoint someone
        # else's domain if it is ever compromised.
        #
        # **And to its own two names within it** [OPS-18]. The zone
        # also holds the API alias and the ACM validation records, and
        # a compromised host able to rewrite `api.` could send every
        # client somewhere else. It needs its A record and certbot's
        # DNS-01 TXT record, and nothing more.
        Effect   = "Allow"
        Action   = ["route53:ChangeResourceRecordSets"]
        Resource = "arn:aws:route53:::hostedzone/${var.dns_zone_id}"
        Condition = {
          "ForAllValues:StringEquals" = {
            "route53:ChangeResourceRecordSetsNormalizedRecordNames" = [
              lower(var.origin_fqdn),
              "_acme-challenge.${lower(var.origin_fqdn)}",
            ]
          }
        }
      },
      {
        # Read-only, and unscopable: Route53 does not support resource
        # scoping on these, so they are account-level by design.
        #
        # `ListHostedZones` is here for certbot's DNS-01 challenge,
        # which looks the zone up by name before it can write the
        # `_acme-challenge` record. Without it the plugin fails at
        # `AccessDenied ... ListHostedZones` before reaching the write
        # that IS zone-scoped above, so the narrow write permission
        # alone does not make DNS-01 work. Listing zones discloses
        # zone names and nothing within them.
        Effect = "Allow"
        Action = [
          "route53:GetChange",
          "route53:ListResourceRecordSets",
          "route53:ListHostedZones",
        ]
        Resource = "*"
      },
    ]
  })
}
