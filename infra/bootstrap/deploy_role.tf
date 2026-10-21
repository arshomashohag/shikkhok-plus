# The DEPLOY role, separate from the infrastructure role.
#
# **Why two roles rather than one flag.** `trust_staging_environment`
# exists on the CI role and would have worked: one boolean, and
# deploy-staging could assume it. It is not taken, because that role
# carries ec2:*, rds:*, route53:*, autoscaling:*, ecr:* and IAM
# writes -- so a workflow whose job is pushing a container image
# would hold the permissions to destroy the database it deploys
# beside.
#
# The deploy needs four things: push an image, read two parameters,
# write two parameters, and run one command on one host. That list is
# short enough to enumerate, which is the test for when
# least-privilege is worth writing rather than a service-level
# wildcard that breaks on the next provider upgrade.
#
# The blast radius difference is the point: a compromised deploy
# workflow can ship a bad image. It cannot terminate the instance,
# repoint DNS, or delete the state bucket.

data "aws_iam_policy_document" "deploy_assume" {
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

    # Only the `staging` environment, and only from this repository.
    # Not `ref:refs/heads/main`: a deploy is an environment-gated
    # action, so a push to main must not be able to assume this.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.subject_prefix}:environment:staging"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "shikkhokplus-github-deploy"
  description        = "Assumed by deploy-staging. Pushes images and runs one SSM command."
  assume_role_policy = data.aws_iam_policy_document.deploy_assume.json

  max_session_duration = 3600
}

resource "aws_iam_role_policy" "deploy" {
  name = "deploy"
  role = aws_iam_role.deploy.id

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
        # The layer actions ARE scoped, and these decide which
        # repository this role can write to.
        Sid    = "EcrPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeRepositories",
          "ecr:GetDownloadUrlForLayer",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
        ]
        Resource = "arn:aws:ecr:*:${data.aws_caller_identity.current.account_id}:repository/shikkhokplus-*"
      },
      {
        # The deployment state a replaced instance reads at boot.
        # Scoped by path, so this role cannot read an unrelated
        # project's parameters.
        Sid    = "DeploymentState"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:PutParameter",
        ]
        Resource = "arn:aws:ssm:*:${data.aws_caller_identity.current.account_id}:parameter/shikkhokplus/*"
      },
      {
        # Encrypting the runtime env SecureString. Scoped by
        # ViaService so this role cannot decrypt anything but SSM
        # parameters.
        Sid      = "ParameterEncryption"
        Effect   = "Allow"
        Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
        Resource = "*"
        Condition = {
          StringLike = { "kms:ViaService" = "ssm.*.amazonaws.com" }
        }
      },
      {
        # Finding the host. Describe actions cannot be resource
        # scoped on either service.
        Sid    = "FindTheHost"
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "ec2:DescribeInstances",
        ]
        Resource = "*"
      },
      {
        # **The delivery itself, scoped to the document AND the
        # instance tag.** Without the tag condition this role could
        # run arbitrary shell on any instance in the account,
        # including another project's.
        Sid      = "RunTheDeploy"
        Effect   = "Allow"
        Action   = ["ssm:SendCommand"]
        Resource = "arn:aws:ssm:*::document/AWS-RunShellScript"
      },
      {
        Sid      = "RunTheDeployOnOurHostsOnly"
        Effect   = "Allow"
        Action   = ["ssm:SendCommand"]
        Resource = "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:instance/*"
        Condition = {
          StringLike = { "ssm:resourceTag/Name" = "shikkhokplus-*" }
        }
      },
      {
        # Reading back what the command did. These take a command id
        # that this role had to create, so they are self-scoping.
        Sid    = "ReadTheResult"
        Effect = "Allow"
        Action = [
          "ssm:GetCommandInvocation",
          "ssm:ListCommandInvocations",
        ]
        Resource = "*"
      },
    ]
  })
}
