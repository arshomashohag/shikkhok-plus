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

# ---------------------------------------------------------------------
# State
# ---------------------------------------------------------------------

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name

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

# The thumbprint is no longer verified by AWS for this provider, but
# the argument remains required. Any valid-looking value is accepted;
# this is GitHub's long-published one.
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "ci_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
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
    # Scoped to this repository AND to either the default branch or a
    # named environment. A pull request from a fork runs with
    # `pull_request` in the subject and matches neither, which is what
    # stops a drive-by PR from applying infrastructure.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:ref:refs/heads/main",
        "repo:${var.github_repository}:environment:*",
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
