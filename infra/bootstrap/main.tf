# Bootstrap: the three things that must exist before CI can run
# Terraform at all.
#
# **This is the ONLY Terraform you run from a laptop**, and it is run
# once. It creates the state bucket, the GitHub OIDC trust, and the
# role CI assumes — the chicken-and-egg that no CI-only setup can
# solve, because CI needs state and credentials before it can create
# state and credentials.
#
# Its own state stays local, and that is fine: it describes three
# resources that never change. If it is lost, `terraform import` on
# three known names rebuilds it, which is cheaper than securing a
# second state bucket to hold the state of the first.
#
# **No long-lived AWS access keys anywhere.** A key in GitHub secrets
# never expires, cannot be rotated without a human remembering, and is
# usable by anyone who can edit a workflow file. OIDC issues a
# one-hour token per run, scoped to this repository and this branch.

terraform {
  required_version = "~> 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "shikkhokplus"
      ManagedBy = "terraform-bootstrap"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  # **Account-suffixed, because S3 bucket names are globally unique
  # across every AWS account on earth.** A plain "shikkhokplus-tfstate"
  # is very likely already taken by somebody else entirely, and the
  # failure is `BucketAlreadyExists` -- which reads like a bug in this
  # module rather than a namespace collision with a stranger.
  #
  # An explicit state_bucket_name still wins, for the case where you
  # want a name you chose.
  state_bucket = coalesce(
    var.state_bucket_name,
    "shikkhokplus-tfstate-${data.aws_caller_identity.current.account_id}",
  )
}

# **A precondition, not a comment.** Running this against the wrong
# account creates an OIDC provider and a role somewhere unintended, and
# the first sign would be a CI run failing to assume a role that exists
# in a different account.
#
# Leave expected_account_id null to skip the check; set it once you
# know the number and the mistake becomes impossible.
resource "terraform_data" "account_guard" {
  input = data.aws_caller_identity.current.account_id

  lifecycle {
    precondition {
      condition = (
        var.expected_account_id == null ||
        var.expected_account_id == data.aws_caller_identity.current.account_id
      )
      error_message = <<-EOT
        Credentials are for account ${data.aws_caller_identity.current.account_id}
        but expected_account_id is ${coalesce(var.expected_account_id, "unset")}.

        Nothing was created. Check `aws sts get-caller-identity`.
      EOT
    }
  }
}

# ---------------------------------------------------------------------
# State
# ---------------------------------------------------------------------

resource "aws_s3_bucket" "state" {
  bucket = local.state_bucket

  # The state holds the CDN origin secret and, in Phase 2, the database
  # password in plaintext. Deleting it is not a recoverable mistake:
  # without state, Terraform no longer knows which resources it owns
  # and a subsequent apply would try to CREATE an instance that
  # already exists.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    # Versioning is the recovery path for a corrupted or truncated
    # state write. Without it, a failed upload mid-apply leaves a state
    # file describing half an infrastructure.
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  # All four, because the state file is a credential store. A public
  # state bucket is a published database password.
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# **TLS only** [OPS-4]. The state file holds every generated secret in
# plaintext -- the origin secret, the RDS master password and the
# shikkhok_app password -- so a request over plain HTTP is refused
# outright. Terraform's S3 backend and the AWS CLI already use HTTPS;
# this removes the possibility rather than relying on the default.
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.state]
}

# ---------------------------------------------------------------------
# GitHub OIDC
# ---------------------------------------------------------------------

# **An account can hold only ONE provider per URL, and this account
# already has it** -- created 2026-04-02, with six other roles already
# trusting it (GitHubDeployRole-staging, ism_ci_cd, portfolio-deploy,
# securemsg-dev-gha-deploy, shop360-prod-deploy,
# shop360-staging-deploy).
#
# So it is REFERENCED, never managed here. Importing it would put a
# resource six unrelated projects depend on under this module's
# control, and a `terraform destroy` would then break all of them --
# a blast radius far outside what this module should own.
#
# `create_github_oidc_provider = true` creates one for a fresh account
# that has none. Terraform cannot conditionally import, so the choice
# is explicit rather than inferred.
data "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # No longer verified by AWS, but the argument remains required.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

locals {
  github_oidc_arn = (
    var.create_github_oidc_provider
    ? aws_iam_openid_connect_provider.github[0].arn
    : data.aws_iam_openid_connect_provider.github[0].arn
  )

  # The `repo:...` portion every trusted subject starts with, built
  # once so the three (or four) subject patterns below cannot drift
  # apart -- which is precisely how this broke before: the ref
  # pattern was corrected to the account's real claim format while
  # the two environment patterns were left in the documented default
  # shape, so main worked and every environment job failed.
  #
  # See the long note on the `sub` condition for why the `@*`
  # segments are here. In short: this account has GitHub's OIDC
  # subject customization enabled, so owner and repo each carry a
  # GitHub-assigned numeric id.
  subject_prefix = (
    var.github_subject_has_numeric_ids
    ? "repo:${local.github_owner}@*/${local.github_repo}@*"
    : "repo:${var.github_repository}"
  )

  github_owner = split("/", var.github_repository)[0]
  github_repo  = split("/", var.github_repository)[1]
}

data "aws_iam_policy_document" "ci_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # **The subject claim is the whole security boundary.** Without
    # this condition ANY GitHub repository in the world could assume
    # this role — the OIDC provider trusts GitHub, not your repo.
    #
    # Scoped to this repository AND to one of the two `-infra`
    # environments BY NAME. A pull request from a fork
    # runs with `pull_request` in the subject and matches none of
    # them, which is what stops a drive-by PR applying infrastructure.
    #
    # **The environments are named rather than wildcarded**, and that
    # is the load-bearing part. `environment:*` reads like "our
    # environments" but means "any string somebody puts after
    # `environment:` in a workflow file" — so anyone able to push a
    # branch could add `environment: whatever` and assume this role,
    # walking straight around the environment's required reviewer. The
    # named form costs one line per environment and closes that.
    #
    # Adding an environment therefore means adding it here. That is a
    # feature: a new environment is a new way into this account, and
    # it should take a bootstrap change rather than a workflow edit.
    #
    # **The `@*` segments are required, not a typo.** This account has
    # GitHub's OIDC customization enabled, so the subject carries a
    # numeric id after the owner AND after the repository:
    #
    #   repo:arshomashohag@20051700/shop-360@1310170125:ref:refs/heads/main
    #
    # not the documented default `repo:<owner>/<repo>:...`. A policy
    # written in the default shape matches NOTHING here and every run
    # fails at role assumption -- which is exactly what happened.
    # Verified against CloudTrail: every successful
    # AssumeRoleWithWebIdentity in this account, across four repos and
    # both `ref:` and `environment:` subjects, carries this format.
    #
    # The ids are wildcarded rather than pinned because they are
    # GitHub-assigned and would silently break the trust policy if
    # they ever changed. `*` after a literal `@` still cannot match a
    # different owner or repository, because the names in front of it
    # are exact -- `shikkhok-plus@*` does not match
    # `shikkhok-plus-evil@...`, since the `@` must come directly after
    # the name.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        # **`<env>-infra`, matching the environments the deploy
        # pipeline actually uses.** These were `terraform-plan` and
        # `terraform-apply`, named for a workflow that no longer
        # exists -- so after the pipelines were unified this role
        # trusted two environments nothing runs in, and the
        # infrastructure job failed at role assumption.
        #
        # Named rather than `environment:*`: a wildcard means any
        # string somebody writes after `environment:` in a workflow
        # file, so anyone able to push a branch could add
        # `environment: whatever` and assume the role that can
        # destroy this infrastructure.
        "${local.subject_prefix}:environment:staging-infra",
        "${local.subject_prefix}:environment:production-infra",

        # **No `ref:refs/heads/main`** [OPS-2]. It was kept "so a
        # terraform apply can still be run from main if the pipeline is
        # ever unavailable" -- and it meant ANY workflow running on
        # main, or a compromised action in one, could assume the role
        # that applies production infrastructure without passing the
        # `production-infra` environment's required reviewer. No
        # workflow used it. The break-glass path is the laptop that
        # runs this bootstrap, with a human's own credentials.
      ]
    }
  }
}

resource "aws_iam_role" "ci" {
  name               = "shikkhokplus-github-actions"
  description        = "Assumed by GitHub Actions via OIDC. No long-lived keys."
  assume_role_policy = data.aws_iam_policy_document.ci_assume.json

  # One hour. A run that takes longer than this is a run that has hung,
  # and the token expiring is the correct outcome.
  max_session_duration = 3600
}

data "aws_iam_policy_document" "ci_state" {
  statement {
    sid    = "StateBucketObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.state.arn}/*"]
  }

  statement {
    sid       = "StateBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
  }

  # **The app's own buckets**, which the main module creates and owns:
  # the config bucket (the compose file the host fetches at boot), the
  # web bucket (the built web client CloudFront serves under /ui/) and
  # the site bucket (the public site, modules/site).
  #
  # Scoped by NAME PREFIX rather than granted account-wide: this role
  # can create and destroy `shikkhokplus-*-config-*`,
  # `shikkhokplus-*-web-*` and `shikkhokplus-*-site-*` and nothing else,
  # so it cannot touch the state bucket's siblings or another project's
  # data. It writes no object into the web or site bucket -- the deploy
  # role uploads those builds.
  #
  # The site's other resources -- its distribution, certificate, cache
  # and headers policies, CloudFront Function and the apex and www
  # records -- need nothing new: cloudfront:*, acm:* and route53:* in
  # the infrastructure policy below already cover them, and every record
  # name they write contains `shikkhokplus`.
  #
  # Both halves are needed and neither is obvious from the create
  # alone: the Get* actions are how Terraform reads a bucket back to
  # detect drift, and without them a second apply fails on a bucket
  # the first one made. The Delete* actions are what `terraform
  # destroy` needs.
  statement {
    sid    = "ConfigBucket"
    effect = "Allow"
    actions = [
      "s3:CreateBucket",
      "s3:DeleteBucket",
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:GetBucketPolicy",
      # The config bucket's TLS-only policy [OPS-4].
      "s3:PutBucketPolicy",
      "s3:DeleteBucketPolicy",
      "s3:GetBucketPolicyStatus",
      "s3:GetBucketAcl",
      "s3:GetBucketCORS",
      "s3:GetBucketWebsite",
      "s3:GetBucketVersioning",
      "s3:GetBucketLogging",
      "s3:GetBucketTagging",
      "s3:GetAccelerateConfiguration",
      "s3:GetBucketRequestPayment",
      "s3:GetLifecycleConfiguration",
      "s3:GetReplicationConfiguration",
      "s3:GetEncryptionConfiguration",
      "s3:PutEncryptionConfiguration",
      "s3:GetBucketPublicAccessBlock",
      "s3:PutBucketPublicAccessBlock",
      "s3:GetBucketObjectLockConfiguration",
      "s3:PutBucketTagging",
    ]
    resources = [
      "arn:aws:s3:::shikkhokplus-*-config-*",
      "arn:aws:s3:::shikkhokplus-*-web-*",
      "arn:aws:s3:::shikkhokplus-*-site-*",
    ]
  }

  statement {
    sid    = "ConfigBucketObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:GetObjectTagging",
      "s3:PutObjectTagging",
    ]
    resources = ["arn:aws:s3:::shikkhokplus-*-config-*/*"]
  }
}

resource "aws_iam_role_policy" "ci_state" {
  name   = "terraform-state"
  role   = aws_iam_role.ci.id
  policy = data.aws_iam_policy_document.ci_state.json
}

# ---------------------------------------------------------------------
# The workload permissions boundary
# ---------------------------------------------------------------------
#
# **A ceiling on every role the CI role creates** [OPS-2]. A boundary
# does not grant anything: a role's effective permissions are the
# intersection of its own policies and its boundary. So even if a
# compromised workflow attached AdministratorAccess to a role it made,
# that role could do no more than this document lists -- which is what
# an app host does and nothing else.
#
# Created here rather than by the main module so that the CI role --
# which the main module runs as -- cannot edit the ceiling that bounds
# it. The CI role has no IAM policy-level write action at all.
#
# Kept to the host's real calls (modules/app/main.tf, user_data):
#
#   * the SSM agent's channel and its parameter reads, the latter only
#     under /shikkhokplus/;
#   * pulling from this project's ECR repositories;
#   * reading its config bucket and writing its persisted certificate;
#   * decrypting through SSM only;
#   * its own DNS record and its certbot challenge, by name;
#   * answering its own launch lifecycle hook;
#   * shipping logs to /shikkhokplus/ groups and a metric to the
#     project's namespace.
resource "aws_iam_policy" "workload_boundary" {
  name        = "shikkhokplus-workload-boundary"
  path        = "/shikkhokplus/"
  description = "Permissions boundary for every role the shikkhokplus CI role creates."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # What AmazonSSMManagedInstanceCore grants the agent: its
        # control channels and instance bookkeeping. Listed, not
        # ssm:*, because ssm:* includes SendCommand -- a host able to
        # run commands on every other instance in the account.
        Sid    = "SsmAgent"
        Effect = "Allow"
        Action = [
          "ssm:DescribeAssociation",
          "ssm:GetDeployablePatchSnapshotForInstance",
          "ssm:GetDocument",
          "ssm:DescribeDocument",
          "ssm:GetManifest",
          "ssm:ListAssociations",
          "ssm:ListInstanceAssociations",
          "ssm:PutInventory",
          "ssm:PutComplianceItems",
          "ssm:PutConfigurePackageResult",
          "ssm:UpdateAssociationStatus",
          "ssm:UpdateInstanceAssociationStatus",
          "ssm:UpdateInstanceInformation",
          "ssmmessages:*",
          "ec2messages:*",
        ]
        Resource = "*"
      },
      {
        Sid      = "OwnParameters"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:*:${data.aws_caller_identity.current.account_id}:parameter/shikkhokplus/*"
      },
      {
        Sid      = "DecryptThroughSsmOnly"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = "*"
        Condition = {
          StringLike = { "kms:ViaService" = "ssm.*.amazonaws.com" }
        }
      },
      {
        Sid      = "EcrAuth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "EcrPull"
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability",
        ]
        Resource = "arn:aws:ecr:*:${data.aws_caller_identity.current.account_id}:repository/shikkhokplus-*"
      },
      {
        Sid      = "ConfigRead"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:aws:s3:::shikkhokplus-*-config-*/*"
      },
      {
        Sid      = "CertificateWrite"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "arn:aws:s3:::shikkhokplus-*-config-*/tls/*"
      },
      {
        Sid      = "DnsRead"
        Effect   = "Allow"
        Action   = ["route53:GetChange", "route53:ListResourceRecordSets", "route53:ListHostedZones"]
        Resource = "*"
      },
      {
        Sid      = "DnsWriteOurNames"
        Effect   = "Allow"
        Action   = ["route53:ChangeResourceRecordSets"]
        Resource = "*"
        Condition = {
          "ForAllValues:StringLike" = {
            "route53:ChangeResourceRecordSetsNormalizedRecordNames" = ["*shikkhokplus*"]
          }
        }
      },
      {
        Sid      = "Readiness"
        Effect   = "Allow"
        Action   = ["autoscaling:CompleteLifecycleAction"]
        Resource = "arn:aws:autoscaling:*:${data.aws_caller_identity.current.account_id}:autoScalingGroup:*:autoScalingGroupName/shikkhokplus-*"
      },
      {
        # **The staging seeder's network interfaces** (modules/seeder):
        # what a Lambda function in a VPC calls to attach to it. EC2
        # does not scope these by resource. A ceiling, not a grant: the
        # app host's role does not hold them, and the CI role that
        # creates roles already holds ec2:* itself, so no role it makes
        # can reach further than the CI role already does.
        Sid    = "LambdaVpcNetworking"
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
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
        Resource = "arn:aws:logs:*:${data.aws_caller_identity.current.account_id}:log-group:/shikkhokplus/*"
      },
      {
        Sid      = "Metrics"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*"
        Condition = {
          StringLike = { "cloudwatch:namespace" = "Shikkhokplus/*" }
        }
      },
    ]
  })
}

locals {
  # The ONLY managed policies the CI role may attach to a role. Each
  # must be something the app module actually attaches; adding one is a
  # bootstrap change, run from a laptop, on purpose.
  attachable_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
  ]
}

# The infrastructure permissions.
#
# **Scoped by SERVICE where Terraform's action set is wide and changes
# with the provider** -- EC2, CloudFront, ACM, Route53, RDS, ECR, Auto
# Scaling. Enumerating every action across those produces a policy that
# breaks on the next provider upgrade and gets widened under deadline
# pressure. That trade is kept, deliberately, and stated.
#
# **What changed on 2026-11-02, and why** [OPS-2]. The audit showed this
# role could mint an account administrator: CreateRole, PutRolePolicy,
# AttachRolePolicy and PassRole on /shikkhokplus/ roles with no
# permissions boundary and no limit on WHICH policy could be attached,
# so a workflow running as this role could create a role with
# AdministratorAccess, put it on an instance profile, launch an
# instance with it and reach it through ssm:SendCommand. And the trust
# accepted `ref:refs/heads/main`, so any workflow on main could do that
# without passing the `*-infra` environment's approval.
#
# What bounds it now:
#
#   * **Every role it creates or edits must carry the workload
#     boundary** (iam:PermissionsBoundary on CreateRole, PutRolePolicy,
#     AttachRolePolicy, PutRolePermissionsBoundary), and removing a
#     boundary is explicitly denied. A boundary is a CEILING on the
#     role's effective permissions whatever is attached, and the
#     workload boundary allows only what an app host does.
#   * **AttachRolePolicy is limited by iam:PolicyARN** to the one
#     managed policy the app module attaches.
#   * **PassRole only to EC2** (iam:PassedToService), for the instance
#     profile in the launch template.
#   * **SSM is parameter management only.** ssm:* included SendCommand,
#     which is how a shell would have reached the instance; Terraform
#     here manages parameters and nothing else in SSM.
#   * **Route53 record changes only for names containing
#     `shikkhokplus`**, so this role cannot repoint another project's
#     record in the shared apex zone.
#   * **The ref subject is gone** (above): only the `*-infra`
#     environments can assume this role.
resource "aws_iam_role_policy" "ci_infrastructure" {
  name = "terraform-infrastructure"
  role = aws_iam_role.ci.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Infrastructure"
        Effect = "Allow"
        Action = [
          # EC2 covers the instances, VPC, subnets, security groups and
          # EBS volumes -- they are all one API.
          "ec2:*",
          "cloudfront:*",
          "acm:*",
          "route53:*",
          "rds:*",
          # ECR, for the image repository and its lifecycle policy.
          # TERRAFORM's grant, not the host's: the instance profile
          # holds only the auth token and layer reads.
          "ecr:*",
          # Auto Scaling, for the group of one and its lifecycle hook.
          # The service-linked role AWSServiceRoleForAutoScaling already
          # exists in this account, so iam:CreateServiceLinkedRole is
          # deliberately NOT here -- a fresh account needs it added once.
          "autoscaling:*",
          "tag:GetResources",
        ]
        Resource = "*"
      },
      {
        # **Parameters under /shikkhokplus/ and nothing else in SSM.**
        # These are the calls aws_ssm_parameter makes: create and update
        # (Put), read back (Get, including SecureString values), delete,
        # and tags.
        Sid    = "Parameters"
        Effect = "Allow"
        Action = [
          "ssm:PutParameter",
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:DeleteParameter",
          "ssm:AddTagsToResource",
          "ssm:RemoveTagsFromResource",
          "ssm:ListTagsForResource",
        ]
        Resource = "arn:aws:ssm:*:${data.aws_caller_identity.current.account_id}:parameter/shikkhokplus/*"
      },
      {
        # Unscopable: DescribeParameters lists by filter, not resource.
        Sid      = "ParameterDiscovery"
        Effect   = "Allow"
        Action   = ["ssm:DescribeParameters"]
        Resource = "*"
      },
      {
        # **The staging seeder** (modules/seeder), by this project's
        # function names only. ListVersionsByFunction and the rest are
        # what aws_lambda_function reads back on every plan.
        Sid      = "SeederFunction"
        Effect   = "Allow"
        Action   = ["lambda:*"]
        Resource = "arn:aws:lambda:*:${data.aws_caller_identity.current.account_id}:function:shikkhokplus-*"
      },
      {
        # **Logs, alarms and the alert topic** [OPS-11], each scoped to
        # this project's names.
        Sid    = "Observability"
        Effect = "Allow"
        Action = [
          "logs:*",
          "sns:*",
          "cloudwatch:*",
        ]
        Resource = [
          "arn:aws:logs:*:${data.aws_caller_identity.current.account_id}:log-group:/shikkhokplus/*",
          "arn:aws:logs:*:${data.aws_caller_identity.current.account_id}:log-group:/shikkhokplus/*:*",
          "arn:aws:sns:*:${data.aws_caller_identity.current.account_id}:shikkhokplus-*",
          "arn:aws:cloudwatch:*:${data.aws_caller_identity.current.account_id}:alarm:shikkhokplus-*",
        ]
      },
      {
        # The describe/list calls these services do not scope by
        # resource; Terraform needs them to read its own resources back.
        Sid    = "ObservabilityDiscovery"
        Effect = "Allow"
        Action = [
          "logs:DescribeLogGroups",
          "logs:DescribeMetricFilters",
          "sns:ListTopics",
          "cloudwatch:DescribeAlarms",
        ]
        Resource = "*"
      },
      {
        # **Records only for this project's names.** Normalised names
        # are lowercase with no trailing dot; every name this module
        # writes -- the delegation, the API alias and AAAA, the ACM
        # validation CNAMEs -- contains `shikkhokplus`. A Deny rather
        # than a narrower Allow because route53:* above is what lets
        # Terraform manage the zone itself.
        Sid      = "OnlyOurRecordNames"
        Effect   = "Deny"
        Action   = ["route53:ChangeResourceRecordSets"]
        Resource = "*"
        Condition = {
          "ForAnyValue:StringNotLike" = {
            "route53:ChangeResourceRecordSetsNormalizedRecordNames" = ["*shikkhokplus*"]
          }
        }
      },
      {
        # Roles and instance profiles under /shikkhokplus/: reading,
        # tagging, deleting, and edits that can only REDUCE what a role
        # holds. The CI role lives at the IAM root path, so none of
        # this can touch it.
        Sid    = "ManageOurRoles"
        Effect = "Allow"
        Action = [
          "iam:GetRole",
          "iam:DeleteRole",
          "iam:TagRole",
          "iam:UntagRole",
          "iam:ListRoleTags",
          "iam:UpdateRole",
          "iam:UpdateAssumeRolePolicy",
          "iam:UpdateRoleDescription",
          "iam:ListAttachedRolePolicies",
          "iam:ListRolePolicies",
          "iam:GetRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:DetachRolePolicy",
          # What DeleteRole calls first: the reverse lookup from a role
          # to the profiles holding it.
          "iam:ListInstanceProfilesForRole",
          "iam:CreateInstanceProfile",
          "iam:DeleteInstanceProfile",
          "iam:GetInstanceProfile",
          "iam:AddRoleToInstanceProfile",
          "iam:RemoveRoleFromInstanceProfile",
          # The full tag set for profiles: default_tags tags everything
          # the provider creates, and a missing tag permission fails the
          # CREATE, then the drift read on the next apply.
          "iam:TagInstanceProfile",
          "iam:UntagInstanceProfile",
          "iam:ListInstanceProfileTags",
        ]
        Resource = [
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/shikkhokplus/*",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:instance-profile/shikkhokplus/*",
        ]
      },
      {
        # **Anything that can ADD permission requires the boundary.**
        # The condition reads the boundary the role will carry (for
        # CreateRole and PutRolePermissionsBoundary, the one in the
        # request; for PutRolePolicy, the role's own), so a role without
        # it can be neither created nor given a policy.
        Sid    = "GrantOnlyWithinTheBoundary"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:PutRolePolicy",
          "iam:PutRolePermissionsBoundary",
        ]
        Resource = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/shikkhokplus/*"
        Condition = {
          StringEquals = { "iam:PermissionsBoundary" = aws_iam_policy.workload_boundary.arn }
        }
      },
      {
        # And only the managed policy the app module actually attaches.
        Sid      = "AttachOnlyKnownPolicies"
        Effect   = "Allow"
        Action   = ["iam:AttachRolePolicy"]
        Resource = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/shikkhokplus/*"
        Condition = {
          StringEquals = { "iam:PermissionsBoundary" = aws_iam_policy.workload_boundary.arn }
          ArnEquals    = { "iam:PolicyARN" = local.attachable_policy_arns }
        }
      },
      {
        # Passing a role to EC2 -- the launch template's instance
        # profile -- and to Lambda, for the staging seeder's execution
        # role. To nothing else. Every role passable here is under
        # /shikkhokplus/ and so carries the workload boundary.
        Sid      = "PassOnlyToEc2AndLambda"
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/shikkhokplus/*"
        Condition = {
          StringEquals = { "iam:PassedToService" = ["ec2.amazonaws.com", "lambda.amazonaws.com"] }
        }
      },
      {
        # **A boundary, once set, stays.** Removing it, or replacing it
        # with any other policy, would lift the ceiling.
        Sid      = "KeepTheBoundary"
        Effect   = "Deny"
        Action   = ["iam:DeleteRolePermissionsBoundary"]
        Resource = "*"
      },
      {
        Sid      = "OnlyOurBoundary"
        Effect   = "Deny"
        Action   = ["iam:PutRolePermissionsBoundary", "iam:CreateRole"]
        Resource = "*"
        Condition = {
          StringNotEquals = { "iam:PermissionsBoundary" = aws_iam_policy.workload_boundary.arn }
        }
      },
      {
        Sid    = "ReadOwnIdentity"
        Effect = "Allow"
        Action = [
          "iam:GetRole",
          "iam:ListRolePolicies",
          "iam:GetRolePolicy",
          # Reading the boundary policy back, for the app module's
          # `permissions_boundary` argument and drift detection.
          "iam:GetPolicy",
          "iam:GetPolicyVersion",
          "sts:GetCallerIdentity",
        ]
        Resource = "*"
      },
    ]
  })
}
