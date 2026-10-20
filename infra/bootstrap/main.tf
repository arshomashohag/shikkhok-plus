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
    # Scoped to this repository AND to either the default branch or
    # one of the two environments BY NAME. A pull request from a fork
    # runs with `pull_request` in the subject and matches none of
    # them, which is what stops a drive-by PR applying infrastructure.
    #
    # **The environments are named rather than wildcarded**, and that
    # is the load-bearing part. `environment:*` reads like "our
    # environments" but means "any string somebody puts after
    # `environment:` in a workflow file" — so anyone able to push a
    # branch could add `environment: whatever` and assume this role,
    # walking straight around the main-branch restriction above. The
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
      values = concat(
        [
          "${local.subject_prefix}:ref:refs/heads/main",
          "${local.subject_prefix}:environment:terraform-plan",
          "${local.subject_prefix}:environment:terraform-apply",
        ],
        # `deploy-staging.yml` runs in the `staging` environment and
        # does NOT assume this role today -- it only builds an image.
        # When the SSM delivery step lands it will need AWS access,
        # and it will fail at role assumption until this is enabled.
        #
        # That failure is deliberate. Under the old `environment:*`
        # the deploy job would have quietly inherited the full
        # infrastructure policy -- ec2:*, rds:*, route53:*, IAM writes
        # -- to push one container. A deploy credential should be its
        # own narrow role, so turning this on is a decision to make
        # with that in view, not a line to flip past.
        var.trust_staging_environment
        ? ["${local.subject_prefix}:environment:staging"]
        : [],
      )
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
}

resource "aws_iam_role_policy" "ci_state" {
  name   = "terraform-state"
  role   = aws_iam_role.ci.id
  policy = data.aws_iam_policy_document.ci_state.json
}

# The infrastructure permissions.
#
# **Scoped by SERVICE, not least-privilege per action**, and that is a
# deliberate trade stated rather than hidden. Enumerating every action
# Terraform needs across EC2, CloudFront, ACM, Route53, RDS and SSM
# produces a policy that breaks on the next provider upgrade and gets
# widened under deadline pressure — which ends at the `*` this was
# meant to avoid, having cost a day.
#
# **It DOES hold IAM write permissions, and an earlier version of this
# comment claimed otherwise.** SSM needs an instance profile, which
# means creating a role and attaching a policy; there is no way around
# that, and pretending there is would only mean the apply fails.
#
# What bounds it instead: the IAM actions are restricted by PATH to
# /shikkhokplus/, so the CI role cannot touch an unrelated role and
# cannot modify ITSELF — it lives at the IAM root path. And the role is
# assumable only from this repository, on main or through an
# environment with manual approval.
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
          # EC2 covers the instances, VPC, subnets, security groups,
          # Elastic IPs and EBS volumes -- they are all one API.
          "ec2:*",
          "cloudfront:*",
          "acm:*",
          "route53:*",
          "rds:*",
          # SSM, for Session Manager. The instance PROFILE grants the
          # agent's side; this is what lets Terraform read and manage
          # the association.
          "ssm:*",
          # ECR, for the image repository and its lifecycle policy.
          # Service-level like the rest, for the reason the README
          # gives: enumerating CreateRepository, PutLifecyclePolicy,
          # TagResource, PutImageScanningConfiguration and the
          # describes produces a list that breaks on the next
          # provider upgrade and gets widened under deadline
          # pressure.
          #
          # Note this is TERRAFORM's grant, not the host's. The
          # instance profile holds a far narrower ECR policy -- the
          # auth token plus layer reads, scoped to one repository --
          # because the host only ever pulls.
          "ecr:*",
          "tag:GetResources",
        ]
        Resource = "*"
      },
      {
        # **The instance profile EC2 needs for SSM.** Terraform must
        # create a role and attach AmazonSSMManagedInstanceCore to it,
        # which means real IAM write permissions -- there is no way
        # around that and pretending otherwise would just mean the
        # apply fails.
        #
        # Bounded by PATH instead: these actions work only on roles
        # under /shikkhokplus/, so the CI role cannot touch an
        # unrelated role and cannot modify ITSELF (which lives at the
        # IAM root path).
        Sid    = "InstanceProfilesForSSM"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:GetRole",
          "iam:PassRole",
          "iam:TagRole",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:ListAttachedRolePolicies",
          "iam:ListRolePolicies",
          "iam:CreateInstanceProfile",
          "iam:DeleteInstanceProfile",
          "iam:GetInstanceProfile",
          "iam:AddRoleToInstanceProfile",
          "iam:RemoveRoleFromInstanceProfile",

          # **The tag actions, as a complete set for both resource
          # types.** The provider's `default_tags` tags everything it
          # creates, so a missing tag permission fails the CREATE --
          # which is how this was found: CreateInstanceProfile
          # returned AccessDenied on iam:TagInstanceProfile, naming
          # an action nobody had thought to grant.
          #
          # All six rather than the one that failed. Granting only
          # TagInstanceProfile would let the create succeed and then
          # fail on the NEXT apply, when Terraform reads tags back to
          # detect drift -- a second identical debugging session for
          # the same root cause, one apply later.
          "iam:TagInstanceProfile",
          "iam:UntagInstanceProfile",
          "iam:ListInstanceProfileTags",
          "iam:UntagRole",
          "iam:ListRoleTags",
        ]
        Resource = [
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/shikkhokplus/*",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:instance-profile/shikkhokplus/*",
        ]
      },
      {
        Sid    = "ReadOwnIdentity"
        Effect = "Allow"
        Action = [
          "iam:GetRole",
          "iam:ListRolePolicies",
          "iam:GetRolePolicy",
          "sts:GetCallerIdentity",
        ]
        Resource = "*"
      },
    ]
  })
}
