# The DEPLOY roles, separate from the infrastructure role -- and, since
# 2026-11-02, ONE PER ENVIRONMENT.
#
# **Why separate from the infrastructure role.** That role carries ec2:*,
# rds:*, autoscaling:* and IAM writes, so a workflow whose job is pushing
# a container image would hold the permissions to destroy the database
# it deploys beside. The deploy needs a short, enumerable list: push an
# image, snapshot the database, read and write its own deployment
# parameters, and roll its own host.
#
# **Why one per environment** [OPS-3]. There used to be one deploy role
# trusting both `environment:staging` and `environment:production`,
# with every grant on a `shikkhokplus-*` wildcard and a read of BOTH
# environments' Terraform state. A run approved for staging could push
# to production's repository, overwrite production's image tag and
# runtime env, roll production's host -- and read production's state,
# which holds the database master password. The GitHub environment's
# approval gate was therefore no boundary at all.
#
# Now each role trusts exactly one environment's subject and every grant
# is scoped to `shikkhokplus-<env>-*` names. A staging run can assume
# only the staging role, and the staging role can touch nothing of
# production's.
#
# **No Terraform state read, for either.** The ZAP scan used to read
# `api_url` from state; Terraform now publishes it to SSM under the
# environment's own path, which is the URL and nothing else.
#
# The blast radius of a compromised deploy run: it can ship a bad image
# to its own environment, which the smoke and the rollback then catch.
# It cannot terminate a host outside its environment, repoint DNS,
# delete a database or read a credential it is not already writing.

locals {
  deploy_environments = toset(["staging", "production"])

  # Staging keeps the role NAME it already had, so its ARN -- already
  # stored in the `staging` GitHub environment's AWS_DEPLOY_ROLE_ARN --
  # does not change and no workflow breaks on apply. The moved block
  # below carries the existing role into the map under that name.
  deploy_role_names = {
    staging    = "shikkhokplus-github-deploy"
    production = "shikkhokplus-github-deploy-production"
  }
}

moved {
  from = aws_iam_role.deploy
  to   = aws_iam_role.deploy["staging"]
}

moved {
  from = aws_iam_role_policy.deploy
  to   = aws_iam_role_policy.deploy["staging"]
}

data "aws_iam_policy_document" "deploy_assume" {
  for_each = local.deploy_environments

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

    # ONE environment, from this repository. Not `ref:refs/heads/main`:
    # a deploy is an environment-gated action, so a push to main must
    # not be able to assume this. StringLike only because of the
    # numeric-id wildcards in subject_prefix (see main.tf); the
    # environment name itself is exact.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.subject_prefix}:environment:${each.key}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  for_each = local.deploy_environments

  name               = local.deploy_role_names[each.key]
  description        = "Assumed by deploy.yml and security-scan.yml in the ${each.key} environment only."
  assume_role_policy = data.aws_iam_policy_document.deploy_assume[each.key].json

  max_session_duration = 3600
}

resource "aws_iam_role_policy" "deploy" {
  for_each = local.deploy_environments

  name = "deploy"
  role = aws_iam_role.deploy[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # ECR's auth action cannot be scoped to a repository --
        # GetAuthorizationToken is account-level by design, so
        # restricting it to a resource produces a policy that
        # silently denies every push.
        Sid      = "EcrAuth"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        # This environment's repository, by exact name.
        Sid    = "EcrPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeRepositories",
          # Checking whether this commit was already built, so a
          # redeploy skips the push rather than failing against
          # the IMMUTABLE tag.
          "ecr:DescribeImages",
          "ecr:GetDownloadUrlForLayer",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
        ]
        Resource = "arn:aws:ecr:*:${data.aws_caller_identity.current.account_id}:repository/shikkhokplus-${each.key}-backend"
      },
      {
        # **Moving the staging seeder to the release just shipped**
        # (modules/seeder), so it never writes against a schema its code
        # predates. UpdateFunctionCode only: NOT GetFunction or
        # GetFunctionConfiguration, whose responses carry the function's
        # environment -- its database URL. UpdateFunctionCode's response
        # carries it too, which is why deploy.yml prints one field of it.
        # This is no new reach: the role can already ship any image to a
        # host holding the same credential.
        Sid      = "MoveTheSeeder"
        Effect   = "Allow"
        Action   = ["lambda:UpdateFunctionCode"]
        Resource = "arn:aws:lambda:*:${data.aws_caller_identity.current.account_id}:function:shikkhokplus-${each.key}-seeder"
      },
      {
        # The deployment state: the image tag and the runtime env,
        # written by the release and read back for the rollback; and
        # the public URL, read by the smoke and the ZAP scan. NOT the
        # database parameters beside them -- this role never holds a
        # database credential.
        Sid    = "DeploymentState"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:PutParameter",
        ]
        Resource = [
          "arn:aws:ssm:*:${data.aws_caller_identity.current.account_id}:parameter/shikkhokplus/shikkhokplus-${each.key}/image-tag",
          "arn:aws:ssm:*:${data.aws_caller_identity.current.account_id}:parameter/shikkhokplus/shikkhokplus-${each.key}/runtime-env",
        ]
      },
      {
        # The public URLs, and the names the web, site and admin uploads
        # need, all published by Terraform so this role never reads state
        # [OPS-3].
        #
        # **One secret among them: `admin-edge-secret`**, a SecureString
        # (modules/admin). The release copies it into the runtime env as
        # SHIKKHOKPLUS_ADMIN_EDGE_SECRET, because the application must
        # know the X-Admin-Edge value the admin distribution sends. That
        # is no new reach: this role already writes the runtime env, which
        # holds the JWT and OTP keys. Decryption is the existing
        # ParameterEncryption grant below, usable only through SSM, and
        # SSM lets this role read only the parameters named here.
        Sid    = "PublicUrl"
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = [
          for name in [
            "api-url", "web-url", "web-bucket", "distribution-id",
            "site-url", "site-bucket", "site-distribution-id",
            "admin-url", "admin-bucket", "admin-distribution-id",
            "admin-edge-secret",
          ] :
          "arn:aws:ssm:*:${data.aws_caller_identity.current.account_id}:parameter/shikkhokplus/shikkhokplus-${each.key}/${name}"
        ]
      },
      {
        # **The web client upload**: this environment's web bucket, under
        # ui/ only. List is bucket-level, for `aws s3 sync` to compare;
        # Delete is for removing files the new build no longer has.
        Sid      = "WebBucketList"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::shikkhokplus-${each.key}-web-*"
      },
      {
        Sid    = "WebBucketObjects"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = "arn:aws:s3:::shikkhokplus-${each.key}-web-*/ui/*"
      },
      {
        # **The public site upload** (modules/site): this environment's
        # site bucket, which holds nothing but the site, so the whole
        # bucket rather than a prefix. List is for pruning files the new
        # build no longer has; Delete is the pruning.
        Sid      = "SiteBucketList"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::shikkhokplus-${each.key}-site-*"
      },
      {
        Sid    = "SiteBucketObjects"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = "arn:aws:s3:::shikkhokplus-${each.key}-site-*/*"
      },
      {
        # **The admin UI upload** (modules/admin): this environment's
        # admin bucket, which holds nothing but the admin UI, so the whole
        # bucket, on the site bucket's terms.
        Sid      = "AdminBucketList"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::shikkhokplus-${each.key}-admin-*"
      },
      {
        Sid    = "AdminBucketObjects"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = "arn:aws:s3:::shikkhokplus-${each.key}-admin-*/*"
      },
      {
        # **Invalidation after the upload**, for the web client's
        # distribution, the site's and the admin surface's, so a release is visible at once
        # rather than when edge copies expire. The distribution ids are
        # created by the main module, after this bootstrap, so they are
        # not known here: the grant is account-wide for these two
        # actions. An invalidation only empties caches -- the worst this
        # can do is make the next requests go to the origin.
        Sid    = "WebInvalidation"
        Effect = "Allow"
        Action = [
          "cloudfront:CreateInvalidation",
          "cloudfront:GetInvalidation",
        ]
        Resource = "arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/*"
      },
      {
        # Encrypting and decrypting the runtime env SecureString, and
        # decrypting the admin edge secret. Usable only through SSM, and
        # SSM lets this role touch only the parameters above.
        Sid      = "ParameterEncryption"
        Effect   = "Allow"
        Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
        Resource = "*"
        Condition = {
          StringLike = { "kms:ViaService" = "ssm.*.amazonaws.com" }
        }
      },
      {
        # Finding the group and following a refresh. Describe calls do
        # not support resource scoping.
        Sid    = "ReadTheGroup"
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:DescribeInstanceRefreshes",
          "autoscaling:DescribeScalingActivities",
        ]
        Resource = "*"
      },
      {
        # **Rolling THIS environment's group only.** The ARN carries a
        # generated id the policy cannot know, so it is wildcarded; the
        # group NAME is not, and `shikkhokplus-staging-` cannot match a
        # production group.
        Sid    = "RollTheInstance"
        Effect = "Allow"
        Action = [
          "autoscaling:StartInstanceRefresh",
          "autoscaling:CancelInstanceRefresh",
        ]
        Resource = "arn:aws:autoscaling:*:${data.aws_caller_identity.current.account_id}:autoScalingGroup:*:autoScalingGroupName/shikkhokplus-${each.key}-*"
      },
      {
        # **The pre-deploy snapshot** [OPS-7]: create one of this
        # environment's database, wait for it, and prune this
        # environment's older pre-deploy snapshots. No restore, no
        # modify, no delete of anything but a pre-deploy snapshot.
        Sid    = "PreDeploySnapshot"
        Effect = "Allow"
        Action = [
          "rds:CreateDBSnapshot",
          "rds:AddTagsToResource",
          "rds:DescribeDBSnapshots",
        ]
        Resource = [
          "arn:aws:rds:*:${data.aws_caller_identity.current.account_id}:db:shikkhokplus-${each.key}-db",
          "arn:aws:rds:*:${data.aws_caller_identity.current.account_id}:snapshot:shikkhokplus-${each.key}-predeploy-*",
        ]
      },
      {
        Sid      = "FindTheDatabase"
        Effect   = "Allow"
        Action   = ["rds:DescribeDBInstances"]
        Resource = "arn:aws:rds:*:${data.aws_caller_identity.current.account_id}:db:shikkhokplus-${each.key}-db"
      },
      {
        Sid      = "PruneOldSnapshots"
        Effect   = "Allow"
        Action   = ["rds:DeleteDBSnapshot"]
        Resource = "arn:aws:rds:*:${data.aws_caller_identity.current.account_id}:snapshot:shikkhokplus-${each.key}-predeploy-*"
      },
    ]
  })
}
