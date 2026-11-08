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


# ---------------------------------------------------------------------
# Per-environment CI roles [C-09]
# ---------------------------------------------------------------------
#
# **One infrastructure role per environment, and one PLAN role per
# environment beside it.** There used to be a single infrastructure role
# trusting both `staging-infra` and `production-infra`, with read, write
# and delete on the whole state bucket and ec2:*, rds:* across both
# environments' resources. `staging-infra` has no reviewer, so any job
# that could run in it -- a dispatch of a modified workflow, or a
# compromised action -- held credentials that could read production's
# state (the database master password, the origin secret) and disable
# deletion protection on production's database. The only human gate on
# production infrastructure could be walked around.
#
# Now, for each environment:
#
#   * the INFRASTRUCTURE role trusts exactly `<env>-infra`, reads and
#     writes only `<env>/` in the state bucket, may create roles only
#     under that environment's own boundary, and is explicitly denied
#     the other environment's database, repository, group, parameters,
#     logs, alarms, buckets and every resource tagged with the other
#     environment's name;
#   * the PLAN role trusts exactly `<env>` -- the job that already runs
#     in that environment, which for production has a required reviewer
#     -- and can read, never write: it renders the plan the reviewer
#     reads BEFORE approving `<env>-infra` [C-11], and stores the plan
#     file for the apply under `plans/<env>/`.
#
# **What this does not scope, stated rather than implied.** CloudFront
# distributions and Route53 hosted zones are addressed by generated ids
# and support no tag condition, so `cloudfront:*` and the zone-level
# Route53 actions stay account-wide on both infrastructure roles. Record
# changes ARE scoped, by name, per environment (OnlyOurRecordNames). The
# remaining exposure -- the staging infrastructure role reconfiguring
# production's distribution -- is closed only by putting production in
# its own AWS account, which is the long-term recommendation.
#
# Staging keeps the role NAME the single role had, so the ARN already
# set as AWS_ROLE_ARN for `staging-infra` keeps working. Production's
# role is new: set its ARN as AWS_ROLE_ARN in the `production-infra`
# environment ONLY (see outputs.tf). A repository-level AWS_ROLE_ARN
# would hand production-infra the staging role, which it cannot assume
# -- a failure at role assumption, not a widening.

locals {
  environments = toset(["staging", "production"])

  infra_role_names = {
    staging    = "shikkhokplus-github-actions"
    production = "shikkhokplus-github-infra-production"
  }

  plan_role_names = {
    staging    = "shikkhokplus-github-plan-staging"
    production = "shikkhokplus-github-plan-production"
  }

  other_environment = {
    staging    = "production"
    production = "staging"
  }

  account_id = data.aws_caller_identity.current.account_id
}

moved {
  from = aws_iam_role.ci
  to   = aws_iam_role.ci["staging"]
}

moved {
  from = aws_iam_role_policy.ci_state
  to   = aws_iam_role_policy.ci_state["staging"]
}

moved {
  from = aws_iam_role_policy.ci_infrastructure
  to   = aws_iam_role_policy.ci_infrastructure["staging"]
}

data "aws_iam_policy_document" "ci_assume" {
  for_each = local.environments

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
    # this role -- the OIDC provider trusts GitHub, not your repo.
    #
    # ONE environment, by name. A pull request from a fork runs with
    # `pull_request` in the subject and matches nothing. Named rather
    # than `environment:*`, because a wildcard means any string somebody
    # writes after `environment:` in a workflow file.
    #
    # **The `@*` segments are required, not a typo.** This account has
    # GitHub's OIDC customization enabled, so the subject carries a
    # numeric id after the owner AND after the repository:
    #
    #   repo:arshomashohag@20051700/shop-360@1310170125:ref:refs/heads/main
    #
    # Verified against CloudTrail. `*` after a literal `@` still cannot
    # match a different owner or repository, because the names in front
    # of it are exact.
    #
    # **No `ref:refs/heads/main`** [OPS-2]: it let any workflow on main
    # assume the role that applies production infrastructure without
    # the environment's reviewer. The break-glass path is the laptop
    # that runs this bootstrap, with a human's own credentials.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.subject_prefix}:environment:${each.key}-infra"]
    }
  }
}

resource "aws_iam_role" "ci" {
  for_each = local.environments

  name               = local.infra_role_names[each.key]
  description        = "Applies ${each.key} infrastructure. Assumed via OIDC from ${each.key}-infra only."
  assume_role_policy = data.aws_iam_policy_document.ci_assume[each.key].json

  # One hour. A run that takes longer than this is a run that has hung,
  # and the token expiring is the correct outcome.
  max_session_duration = 3600
}

data "aws_iam_policy_document" "ci_state" {
  for_each = local.environments

  # **This environment's state and nothing else's.** The key is
  # `<env>/terraform.tfstate` (deploy.yml's -backend-config), and its
  # S3-native lock file sits beside it, so `<env>/*` covers both.
  statement {
    sid    = "StateObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.state.arn}/${each.key}/*"]
  }

  # The saved plan the plan role wrote, read back so exactly that plan
  # is applied, and removed afterwards [C-11].
  statement {
    sid       = "SavedPlans"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/plans/${each.key}/*"]
  }

  # Listing reveals key names, not contents; the backend lists to find
  # workspaces.
  statement {
    sid       = "StateBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
  }

  # **The app's own buckets**, which the main module creates and owns:
  # the config bucket (the compose file the host fetches at boot), the
  # web bucket (the built web client CloudFront serves under /ui/), the
  # site bucket (the public site, modules/site) and the admin bucket (the
  # platform admin UI, modules/admin).
  #
  # Scoped by THIS environment's name prefix [C-09]: this role can create
  # and destroy `shikkhokplus-<env>-config-*`, `-web-*`, `-site-*` and
  # `-admin-*` and nothing else, so it cannot touch the state bucket's
  # siblings, the other environment's buckets, or another project's data.
  # It writes no object into the web, site or admin bucket -- the deploy
  # role uploads those builds.
  #
  # The site's and the admin surface's other resources -- distributions,
  # certificates, cache and headers policies, CloudFront Functions, alias
  # records and SSM parameters (the admin edge secret included) -- are
  # covered by the infrastructure policy below.
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
      "arn:aws:s3:::shikkhokplus-${each.key}-*config-*",
      "arn:aws:s3:::shikkhokplus-${each.key}-web-*",
      "arn:aws:s3:::shikkhokplus-${each.key}-site-*",
      "arn:aws:s3:::shikkhokplus-${each.key}-admin-*",
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
    resources = ["arn:aws:s3:::shikkhokplus-${each.key}-*config-*/*"]
  }
}

resource "aws_iam_role_policy" "ci_state" {
  for_each = local.environments

  name   = "terraform-state"
  role   = aws_iam_role.ci[each.key].id
  policy = data.aws_iam_policy_document.ci_state[each.key].json
}

# **Saved plans expire.** The apply deletes the plan it applied; one
# whose apply was never approved is removed here rather than kept
# beside the state forever. A plan holds the same secrets the state does.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-saved-plans"
    status = "Enabled"

    filter {
      prefix = "plans/"
    }

    expiration {
      days = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }
}

# ---------------------------------------------------------------------
# The workload permissions boundaries
# ---------------------------------------------------------------------
#
# **A ceiling on every role the CI role creates** [OPS-2]. A boundary
# does not grant anything: a role's effective permissions are the
# intersection of its own policies and its boundary. So even if a
# compromised workflow attached a wide policy to a role it made, that
# role could do no more than this document lists -- which is what an
# app host does and nothing else.
#
# **One per environment** [C-08]. The single boundary allowed reading
# every parameter under /shikkhokplus/, and the host also carried
# AmazonSSMManagedInstanceCore, whose ssm:GetParameter is on `*` -- so a
# STAGING host could read production's runtime env (the JWT signing
# keys, the OTP HMAC key), its owner database URL and its origin secret.
# Each environment's boundary now names only that environment's
# parameters, repository, buckets, log groups, group and metric
# namespace, and each environment's infrastructure role may create
# roles only under its own. The host also no longer carries the managed
# policy (modules/app/main.tf).
#
# Created here rather than by the main module so that the CI role --
# which the main module runs as -- cannot edit the ceiling that bounds
# it. The CI role has no IAM policy-level write action at all.
resource "aws_iam_policy" "environment_boundary" {
  for_each = local.environments

  name        = "shikkhokplus-workload-boundary-${each.key}"
  path        = "/shikkhokplus/"
  description = "Permissions boundary for every role the ${each.key} infrastructure role creates."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # The SSM agent's control channels and instance bookkeeping,
        # WITHOUT ssm:GetParameter(s): a parameter read is granted below,
        # per environment, and the agent does not need one. Listed, not
        # ssm:*, because ssm:* includes SendCommand.
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
        # This environment's parameters: the primary host's path and
        # the rehearsal host's (`shikkhokplus-<env>-rehearsal`).
        Sid    = "OwnParameters"
        Effect = "Allow"
        Action = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = [
          "arn:aws:ssm:*:${local.account_id}:parameter/shikkhokplus/shikkhokplus-${each.key}/*",
          "arn:aws:ssm:*:${local.account_id}:parameter/shikkhokplus/shikkhokplus-${each.key}-*",
        ]
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
        Resource = "arn:aws:ecr:*:${local.account_id}:repository/shikkhokplus-${each.key}-*"
      },
      {
        Sid      = "ConfigRead"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:aws:s3:::shikkhokplus-${each.key}-*config-*/*"
      },
      {
        Sid      = "CertificateWrite"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "arn:aws:s3:::shikkhokplus-${each.key}-*config-*/tls/*"
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
            "route53:ChangeResourceRecordSetsNormalizedRecordNames" = var.record_name_patterns[each.key]
          }
        }
      },
      {
        Sid      = "Readiness"
        Effect   = "Allow"
        Action   = ["autoscaling:CompleteLifecycleAction"]
        Resource = "arn:aws:autoscaling:*:${local.account_id}:autoScalingGroup:*:autoScalingGroupName/shikkhokplus-${each.key}-*"
      },
      {
        # **The staging seeder's network interfaces** (modules/seeder):
        # what a Lambda function in a VPC calls to attach to it. EC2
        # does not scope these by resource. A ceiling, not a grant: the
        # app host's role does not hold them, and the CI role that
        # creates roles already holds ec2:* itself.
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
        Sid    = "Logs"
        Effect = "Allow"
        Action = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
        Resource = [
          "arn:aws:logs:*:${local.account_id}:log-group:/shikkhokplus/shikkhokplus-${each.key}/*",
          "arn:aws:logs:*:${local.account_id}:log-group:/shikkhokplus/shikkhokplus-${each.key}-*",
        ]
      },
      {
        Sid      = "Metrics"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*"
        Condition = {
          StringLike = { "cloudwatch:namespace" = "Shikkhokplus/shikkhokplus-${each.key}*" }
        }
      },
    ]
  })
}

# **The SES sender's boundary, per environment** (infra/modules/email).
#
# The main module creates one IAM user per environment whose SMTP
# credentials the API container holds -- a long-lived key, because the
# container cannot reach the instance role (IMDS hop limit 1). This is the
# ceiling on that user: ses:SendRawEmail, the action SES's SMTP interface
# authorizes, on this environment's identity and configuration sets, and
# nothing else. The infrastructure role may create a user, or give one a
# policy, only under it (GrantUserOnlyWithinTheSenderBoundary), so the
# worst a compromised apply can mint is a key that sends mail as this
# environment's domain -- not a key into the account.
#
# The identity is the environment's project zone, named by the same
# patterns that scope its DNS records, so staging's ceiling cannot match
# production's domain.
resource "aws_iam_policy" "email_sender_boundary" {
  for_each = local.environments

  name        = "shikkhokplus-email-sender-boundary-${each.key}"
  path        = "/shikkhokplus/"
  description = "Permissions boundary for the ${each.key} SES SMTP user: send through this environment's identity only."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "SendThroughOurIdentityOnly"
      Effect   = "Allow"
      Action   = ["ses:SendRawEmail"]
      Resource = local.email_resource_arns[each.key]
    }]
  })
}

locals {
  # This environment's SES identity (its project zone, by the record-name
  # patterns) and configuration sets (`shikkhokplus-<env>-*`).
  email_resource_arns = {
    for env in local.environments : env => concat(
      [for pattern in var.record_name_patterns[env] : "arn:aws:ses:*:${local.account_id}:identity/${pattern}"],
      ["arn:aws:ses:*:${local.account_id}:configuration-set/shikkhokplus-${env}-*"],
    )
  }
}

# **The retired single boundary**, kept UNCHANGED only because roles
# still carry it until each environment's main module has been applied
# once with the per-environment boundary above. IAM refuses to delete a
# policy in use as a boundary, and narrowing it first would cut a
# running host off from its own parameters, image and log group before
# the apply that moves it. No CI role may grant under it any more
# (GrantOnlyWithinTheBoundary names the per-environment one). Delete this
# resource in the first bootstrap apply AFTER both environments have
# deployed.
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

# The infrastructure permissions, per environment.
#
# **Scoped by SERVICE where Terraform's action set is wide and changes
# with the provider** -- EC2, CloudFront, ACM, Route53, RDS, ECR, Auto
# Scaling. Enumerating every action across those produces a policy that
# breaks on the next provider upgrade and gets widened under deadline
# pressure. That trade is kept, deliberately -- and since C-09 it is
# paired with explicit DENIES on the other environment's resources, by
# name where the ARN carries one and by the Environment tag the
# provider's default_tags put on everything else.
#
# What else bounds it [OPS-2]:
#
#   * **Every role it creates or edits must carry ITS environment's
#     boundary**, and removing a boundary is explicitly denied.
#   * **No managed policy may be attached at all** [C-08]: the one it
#     could attach, AmazonSSMManagedInstanceCore, granted
#     ssm:GetParameter on `*`.
#   * **PassRole only to EC2**, for its own environment's roles.
#   * **SSM is parameter management only**, under its own path.
#   * **Route53 record changes only for its own environment's names.**
resource "aws_iam_role_policy" "ci_infrastructure" {
  for_each = local.environments

  name = "terraform-infrastructure"
  role = aws_iam_role.ci[each.key].id

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
          # Includes the event subscription [C-33]; the other
          # environment's database is denied below.
          "rds:*",
          "ecr:*",
          # The service-linked role AWSServiceRoleForAutoScaling already
          # exists in this account, so iam:CreateServiceLinkedRole is
          # deliberately NOT here -- a fresh account needs it added once.
          "autoscaling:*",
          "tag:GetResources",
        ]
        Resource = "*"
      },
      {
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
        Resource = [
          "arn:aws:ssm:*:${local.account_id}:parameter/shikkhokplus/shikkhokplus-${each.key}/*",
          "arn:aws:ssm:*:${local.account_id}:parameter/shikkhokplus/shikkhokplus-${each.key}-*",
        ]
      },
      {
        # Unscopable: DescribeParameters lists by filter, not resource.
        Sid      = "ParameterDiscovery"
        Effect   = "Allow"
        Action   = ["ssm:DescribeParameters"]
        Resource = "*"
      },
      {
        # **The staging seeder** (modules/seeder), by this
        # environment's function names only. ListVersionsByFunction and
        # the rest are what aws_lambda_function reads back on every plan.
        Sid      = "SeederFunction"
        Effect   = "Allow"
        Action   = ["lambda:*"]
        Resource = "arn:aws:lambda:*:${local.account_id}:function:shikkhokplus-${each.key}-*"
      },
      {
        # **The SES identity and configuration set** (modules/email), by
        # this environment's names only. Enumerated rather than ses:*, so
        # the role that applies infrastructure is not also a sender. The
        # Put* wildcards are the per-attribute setters Terraform calls on
        # an update (DKIM, MAIL FROM, reputation, suppression, delivery).
        Sid    = "EmailIdentity"
        Effect = "Allow"
        Action = [
          "ses:CreateEmailIdentity",
          "ses:DeleteEmailIdentity",
          "ses:GetEmailIdentity",
          "ses:PutEmailIdentity*",
          "ses:CreateConfigurationSet",
          "ses:DeleteConfigurationSet",
          "ses:GetConfigurationSet",
          "ses:PutConfigurationSet*",
          "ses:TagResource",
          "ses:UntagResource",
          "ses:ListTagsForResource",
        ]
        Resource = local.email_resource_arns[each.key]
      },
      {
        # **The SES SMTP user** (modules/email): reading, tagging,
        # deleting, its access keys, and edits that can only reduce what it
        # holds. Under /shikkhokplus/ and named for this environment.
        # Giving it a policy is GrantUserOnlyWithinTheSenderBoundary below.
        # The List* calls are what Terraform reads back, and what deleting
        # a user checks first. No login profile, no MFA, no group, no
        # managed policy: none is granted.
        Sid    = "ManageOurSender"
        Effect = "Allow"
        Action = [
          "iam:GetUser",
          "iam:DeleteUser",
          "iam:TagUser",
          "iam:UntagUser",
          "iam:ListUserTags",
          "iam:ListUserPolicies",
          "iam:GetUserPolicy",
          "iam:DeleteUserPolicy",
          "iam:ListAttachedUserPolicies",
          "iam:ListGroupsForUser",
          "iam:ListAccessKeys",
          "iam:CreateAccessKey",
          "iam:DeleteAccessKey",
          "iam:UpdateAccessKey",
          "iam:ListSSHPublicKeys",
          "iam:ListServiceSpecificCredentials",
          "iam:ListSigningCertificates",
          "iam:ListMFADevices",
          "iam:GetLoginProfile",
        ]
        Resource = "arn:aws:iam::${local.account_id}:user/shikkhokplus/shikkhokplus-${each.key}-*"
      },
      {
        # **A user is created, or given a policy, only under the sender
        # boundary**: a ceiling of ses:SendRawEmail on this environment's
        # identity. So this role cannot mint a long-lived key that reaches
        # anything else, whatever policy it writes.
        Sid    = "GrantUserOnlyWithinTheSenderBoundary"
        Effect = "Allow"
        Action = [
          "iam:CreateUser",
          "iam:PutUserPolicy",
          "iam:PutUserPermissionsBoundary",
        ]
        Resource = "arn:aws:iam::${local.account_id}:user/shikkhokplus/shikkhokplus-${each.key}-*"
        Condition = {
          StringEquals = { "iam:PermissionsBoundary" = aws_iam_policy.email_sender_boundary[each.key].arn }
        }
      },
      {
        Sid      = "OnlyTheSenderBoundary"
        Effect   = "Deny"
        Action   = ["iam:CreateUser", "iam:PutUserPolicy", "iam:PutUserPermissionsBoundary"]
        Resource = "*"
        Condition = {
          StringNotEquals = { "iam:PermissionsBoundary" = aws_iam_policy.email_sender_boundary[each.key].arn }
        }
      },
      {
        # **Logs, alarms and the alert topic** [OPS-11], each scoped to
        # this environment's names.
        Sid    = "Observability"
        Effect = "Allow"
        Action = [
          "logs:*",
          "sns:*",
          "cloudwatch:*",
        ]
        Resource = [
          "arn:aws:logs:*:${local.account_id}:log-group:/shikkhokplus/shikkhokplus-${each.key}/*",
          "arn:aws:logs:*:${local.account_id}:log-group:/shikkhokplus/shikkhokplus-${each.key}-*",
          "arn:aws:sns:*:${local.account_id}:shikkhokplus-${each.key}-*",
          "arn:aws:cloudwatch:*:${local.account_id}:alarm:shikkhokplus-${each.key}-*",
        ]
      },
      {
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
        # **Records only for this environment's names**. A Deny rather
        # than a narrower Allow because route53:* above is what lets
        # Terraform manage the zone itself.
        Sid      = "OnlyOurRecordNames"
        Effect   = "Deny"
        Action   = ["route53:ChangeResourceRecordSets"]
        Resource = "*"
        Condition = {
          "ForAnyValue:StringNotLike" = {
            "route53:ChangeResourceRecordSetsNormalizedRecordNames" = var.record_name_patterns[each.key]
          }
        }
      },
      {
        # **Not the other environment's database, snapshots, subnet
        # group or event subscription** -- by name, because RDS ARNs
        # carry one. Reading stays allowed so a plan can describe.
        Sid       = "NotTheOtherDatabase"
        Effect    = "Deny"
        NotAction = ["rds:Describe*", "rds:List*"]
        Resource = [
          for kind in ["db", "snapshot", "subgrp", "es", "pg"] :
          "arn:aws:rds:*:${local.account_id}:${kind}:shikkhokplus-${local.other_environment[each.key]}-*"
        ]
      },
      {
        # Not its repository or its group, by name.
        Sid    = "NotTheOtherRegistryOrGroup"
        Effect = "Deny"
        NotAction = [
          "ecr:Describe*",
          "ecr:List*",
          "autoscaling:Describe*",
        ]
        Resource = [
          "arn:aws:ecr:*:${local.account_id}:repository/shikkhokplus-${local.other_environment[each.key]}-*",
          "arn:aws:autoscaling:*:${local.account_id}:autoScalingGroup:*:autoScalingGroupName/shikkhokplus-${local.other_environment[each.key]}-*",
        ]
      },
      {
        # **Nothing tagged with the other environment's name**, for the
        # resources whose ARNs carry generated ids -- instances, launch
        # templates, VPCs, security groups, certificates. The provider's
        # default_tags put `Environment` on every resource either
        # environment creates. Changing that tag is itself denied here,
        # because CreateTags and DeleteTags on such a resource are
        # actions on a resource tagged with the other environment.
        Sid    = "NotTheOtherEnvironmentByTag"
        Effect = "Deny"
        NotAction = [
          "ec2:Describe*",
          "ec2:Get*",
          "acm:Describe*",
          "acm:List*",
          "autoscaling:Describe*",
          "rds:Describe*",
          "rds:List*",
        ]
        Resource = "*"
        Condition = {
          StringEquals = { "aws:ResourceTag/Environment" = local.other_environment[each.key] }
        }
      },
      {
        # Roles and instance profiles under /shikkhokplus/ named for this
        # environment: reading, tagging, deleting, and edits that can
        # only REDUCE what a role holds.
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
          # Detaching, so the apply that drops the managed policy from
          # the instance role [C-08] can complete. Attaching is not
          # granted at all.
          "iam:DetachRolePolicy",
          "iam:ListInstanceProfilesForRole",
          "iam:CreateInstanceProfile",
          "iam:DeleteInstanceProfile",
          "iam:GetInstanceProfile",
          "iam:AddRoleToInstanceProfile",
          "iam:RemoveRoleFromInstanceProfile",
          "iam:TagInstanceProfile",
          "iam:UntagInstanceProfile",
          "iam:ListInstanceProfileTags",
        ]
        Resource = [
          "arn:aws:iam::${local.account_id}:role/shikkhokplus/shikkhokplus-${each.key}-*",
          "arn:aws:iam::${local.account_id}:instance-profile/shikkhokplus/shikkhokplus-${each.key}-*",
        ]
      },
      {
        # **Anything that can ADD permission requires this environment's
        # boundary.** The condition reads the boundary the role will
        # carry (for CreateRole and PutRolePermissionsBoundary, the one in
        # the request; for PutRolePolicy, the role's own).
        Sid    = "GrantOnlyWithinTheBoundary"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:PutRolePolicy",
          "iam:PutRolePermissionsBoundary",
        ]
        Resource = "arn:aws:iam::${local.account_id}:role/shikkhokplus/shikkhokplus-${each.key}-*"
        Condition = {
          StringEquals = { "iam:PermissionsBoundary" = aws_iam_policy.environment_boundary[each.key].arn }
        }
      },
      {
        # Passing a role to EC2 -- the launch template's instance
        # profile -- and to Lambda, for the staging seeder's execution
        # role. To nothing else, and only this environment's roles,
        # every one of which carries this environment's boundary. No
        # managed policy is attachable at all [C-08]: the seeder's role
        # lists its grants inline.
        Sid      = "PassOnlyToEc2AndLambda"
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = "arn:aws:iam::${local.account_id}:role/shikkhokplus/shikkhokplus-${each.key}-*"
        Condition = {
          StringEquals = { "iam:PassedToService" = ["ec2.amazonaws.com", "lambda.amazonaws.com"] }
        }
      },
      {
        # **A boundary, once set, stays.**
        Sid      = "KeepTheBoundary"
        Effect   = "Deny"
        Action   = ["iam:DeleteRolePermissionsBoundary", "iam:DeleteUserPermissionsBoundary"]
        Resource = "*"
      },
      {
        Sid      = "OnlyOurBoundary"
        Effect   = "Deny"
        Action   = ["iam:PutRolePermissionsBoundary", "iam:CreateRole"]
        Resource = "*"
        Condition = {
          StringNotEquals = { "iam:PermissionsBoundary" = aws_iam_policy.environment_boundary[each.key].arn }
        }
      },
      {
        Sid    = "ReadOwnIdentity"
        Effect = "Allow"
        Action = [
          "iam:GetRole",
          "iam:ListRolePolicies",
          "iam:GetRolePolicy",
          "iam:GetPolicy",
          "iam:GetPolicyVersion",
          "sts:GetCallerIdentity",
        ]
        Resource = "*"
      },
    ]
  })
}

# ---------------------------------------------------------------------
# The plan roles [C-11]
# ---------------------------------------------------------------------
#
# **Read-only, and trusted by the environment the deploy's first job
# already runs in.** The reviewer of `production-infra` used to approve a
# job whose plan did not exist yet, and the apply followed in the same
# job. The plan now runs first, as this role, in the `<env>` job --
# production's is behind that environment's required reviewer -- and
# the plan file it stores is the only thing the `<env>-infra` job
# applies.
#
# Every read is enumerated and scoped to this environment where the
# service allows it, so the plan role is not a second way to read the
# other environment's state or secrets: the state object, the
# parameters, the buckets and the roles are all `<env>`-named. It holds
# no write of any kind outside `plans/<env>/` in the state bucket, and
# it plans with -lock=false, so it never takes the state lock.
data "aws_iam_policy_document" "plan_assume" {
  for_each = local.environments

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

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.subject_prefix}:environment:${each.key}"]
    }
  }
}

resource "aws_iam_role" "plan" {
  for_each = local.environments

  name                 = local.plan_role_names[each.key]
  description          = "Renders the ${each.key} Terraform plan. Read-only. Assumed via OIDC from ${each.key} only."
  assume_role_policy   = data.aws_iam_policy_document.plan_assume[each.key].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "plan" {
  for_each = local.environments

  name = "terraform-plan"
  role = aws_iam_role.plan[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadState"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.state.arn}/${each.key}/*"
      },
      {
        Sid      = "StorePlan"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.state.arn}/plans/${each.key}/*"
      },
      {
        Sid      = "ListState"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.state.arn
      },
      {
        # The describe and list calls Terraform's refresh makes, for the
        # services whose resources carry generated ids or that do not
        # scope reads by resource.
        Sid    = "Refresh"
        Effect = "Allow"
        Action = [
          "ec2:Describe*",
          "ec2:GetManagedPrefixListEntries",
          "autoscaling:Describe*",
          "rds:Describe*",
          "rds:ListTagsForResource",
          "ecr:DescribeRepositories",
          "ecr:GetLifecyclePolicy",
          "ecr:GetRepositoryPolicy",
          "ecr:ListTagsForResource",
          "cloudfront:Get*",
          "cloudfront:List*",
          "cloudfront:Describe*",
          "acm:DescribeCertificate",
          "acm:ListCertificates",
          "acm:ListTagsForCertificate",
          "route53:Get*",
          "route53:List*",
          "logs:DescribeLogGroups",
          "logs:DescribeMetricFilters",
          "logs:ListTagsForResource",
          "logs:ListTagsLogGroup",
          "sns:GetTopicAttributes",
          "sns:GetSubscriptionAttributes",
          "sns:ListSubscriptionsByTopic",
          "sns:ListTagsForResource",
          "cloudwatch:DescribeAlarms",
          "cloudwatch:ListTagsForResource",
          "ssm:DescribeParameters",
          "tag:GetResources",
          "sts:GetCallerIdentity",
          "iam:GetPolicy",
          "iam:GetPolicyVersion",
        ]
        Resource = "*"
      },
      {
        # **The staging seeder, read back** (modules/seeder): what
        # aws_lambda_function's refresh reads, and what the deploy's
        # "Can the seeder be created on this run?" step asks. This
        # environment's functions only. GetFunctionConfiguration returns
        # the function's environment -- the restricted role's database
        # URL -- which a refresh cannot avoid reading; the deploy step
        # prints only the function's name.
        Sid    = "ReadOurFunctions"
        Effect = "Allow"
        Action = [
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration",
          "lambda:GetFunctionCodeSigningConfig",
          "lambda:GetFunctionConcurrency",
          "lambda:GetPolicy",
          "lambda:ListVersionsByFunction",
          "lambda:ListTags",
        ]
        Resource = "arn:aws:lambda:*:${local.account_id}:function:shikkhokplus-${each.key}-*"
      },
      {
        # Whether the running image is a single manifest Lambda accepts,
        # for the same deploy step. Metadata only; no layer download.
        Sid      = "ReadOurImages"
        Effect   = "Allow"
        Action   = ["ecr:DescribeImages"]
        Resource = "arn:aws:ecr:*:${local.account_id}:repository/shikkhokplus-${each.key}-backend"
      },
      {
        # This environment's parameters, SecureStrings included: the
        # refresh reads them back to detect drift.
        Sid    = "ReadOurParameters"
        Effect = "Allow"
        Action = ["ssm:GetParameter", "ssm:GetParameters", "ssm:ListTagsForResource"]
        Resource = [
          "arn:aws:ssm:*:${local.account_id}:parameter/shikkhokplus/shikkhokplus-${each.key}/*",
          "arn:aws:ssm:*:${local.account_id}:parameter/shikkhokplus/shikkhokplus-${each.key}-*",
        ]
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
        # Every bucket this environment's stack manages: the config and
        # web buckets (modules/app, modules/cdn), the public site
        # (modules/site) and the admin UI (modules/admin). Bucket ARNs
        # only, so no object in any of them is readable -- the refresh
        # reads bucket configuration, not contents. A bucket missing here
        # fails the plan at the first GetBucket* call, as the site and
        # admin buckets did; tests/gates/test_plan_role_reads_every_bucket.py
        # keeps this list in step with the modules.
        Sid    = "ReadOurBuckets"
        Effect = "Allow"
        Action = ["s3:Get*", "s3:List*"]
        Resource = [
          "arn:aws:s3:::shikkhokplus-${each.key}-*config-*",
          "arn:aws:s3:::shikkhokplus-${each.key}-web-*",
          "arn:aws:s3:::shikkhokplus-${each.key}-site-*",
          "arn:aws:s3:::shikkhokplus-${each.key}-admin-*",
        ]
      },
      {
        # The one object Terraform manages in the config bucket. NOT the
        # rest of it: tls/ holds the origin certificate's private key,
        # which no plan needs to read.
        Sid      = "ReadTheComposeFile"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectTagging"]
        Resource = "arn:aws:s3:::shikkhokplus-${each.key}-*config-*/docker-compose.yml"
      },
      {
        # **The SES identity and configuration set**, read back
        # (modules/email). No send action.
        Sid    = "ReadOurEmail"
        Effect = "Allow"
        Action = [
          "ses:GetEmailIdentity",
          "ses:GetConfigurationSet",
          "ses:ListTagsForResource",
        ]
        Resource = local.email_resource_arns[each.key]
      },
      {
        # **The SES SMTP user, read back** (modules/email): the user, its
        # inline policy and its access key's id and status. Never a secret
        # -- the SMTP password exists only at key creation, in state and
        # in the SSM SecureString this role reads above, as it reads every
        # SecureString of this environment to detect drift.
        Sid    = "ReadOurSender"
        Effect = "Allow"
        Action = [
          "iam:GetUser",
          "iam:ListUserTags",
          "iam:GetUserPolicy",
          "iam:ListUserPolicies",
          "iam:ListAttachedUserPolicies",
          "iam:ListAccessKeys",
        ]
        Resource = "arn:aws:iam::${local.account_id}:user/shikkhokplus/shikkhokplus-${each.key}-*"
      },
      {
        Sid    = "ReadOurRoles"
        Effect = "Allow"
        Action = [
          "iam:GetRole",
          "iam:GetRolePolicy",
          "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies",
          "iam:ListRoleTags",
          "iam:GetInstanceProfile",
          "iam:ListInstanceProfilesForRole",
          "iam:ListInstanceProfileTags",
        ]
        Resource = [
          "arn:aws:iam::${local.account_id}:role/shikkhokplus/shikkhokplus-${each.key}-*",
          "arn:aws:iam::${local.account_id}:instance-profile/shikkhokplus/shikkhokplus-${each.key}-*",
        ]
      },
    ]
  })
}
