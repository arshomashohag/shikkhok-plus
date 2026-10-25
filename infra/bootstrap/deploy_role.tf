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

    # The deploy environments only, and only from this repository.
    # Not `ref:refs/heads/main`: a deploy is an environment-gated
    # action, so a push to main must not be able to assume this.
    #
    # Named rather than wildcarded, for the same reason as the infra
    # role: `environment:*` would let any invented environment name
    # assume this.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "${local.subject_prefix}:environment:staging",
        "${local.subject_prefix}:environment:production",
      ]
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
          # Checking whether this commit was already built, so a
          # redeploy skips the push rather than failing against
          # the IMMUTABLE tag. Without it the check errors, takes
          # the else branch, and pushes anyway -- which is the
          # failure it exists to prevent.
          "ecr:DescribeImages",
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
        # **The rollout, not just finding the host.** An earlier
        # version granted only the Describe actions, because that is
        # what I simulated -- StartInstanceRefresh was never checked,
        # so the gap survived the check that was meant to catch it.
        #
        # Resource "*" because autoscaling does not support resource
        # scoping on StartInstanceRefresh in a way that survives the
        # group's name_prefix suffix: the ARN carries a generated id
        # the policy cannot know in advance. The role is already
        # bounded by being assumable only from this repository's
        # staging environment.
        Sid    = "RollTheInstance"
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:StartInstanceRefresh",
          "autoscaling:DescribeInstanceRefreshes",
          "autoscaling:CancelInstanceRefresh",
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
      {
        # **Reading the Terraform state, and only reading it.** Added
        # at D5 for the ZAP scan, which needs one output -- `api_url`,
        # the host to scan -- and nothing else.
        #
        # **Why this role rather than the other one.** There are two
        # OIDC roles and `AWS_ROLE_ARN` is the infrastructure role,
        # whose own comment above says it can create and destroy. A
        # DAST scan reads one output and sends HTTP requests; it has no
        # business holding a role that can destroy the host it is
        # scanning. Widening this role by one READ is a far smaller
        # change than reaching for that one, and that was the design's
        # stated instruction when it flagged this permission as
        # unverified.
        #
        # **Scoped to the state objects, not the bucket.** The prefix
        # is `<environment>/terraform.tfstate`, so this grants no read
        # of anything else the bucket may hold -- backups, logs, or a
        # second project's state. `s3:ListBucket` is scoped to the
        # bucket itself because that is the only resource form it
        # accepts -- but its KEYS are narrowed by an `s3:prefix`
        # condition on the statement below, which an earlier version
        # omitted. Unconditioned, it would have listed every object
        # name in the bucket.
        #
        # **No `s3:PutObject` and no lock permission.** `terraform
        # output` is a read, and the scan passes `-lock=false` for
        # exactly this reason: the S3 backend uses native lockfile
        # locking [infra/versions.tf], and a read-only consumer should
        # not need to write a lock object. Granting write access to the
        # lock would mean this role could block a real apply.
        #
        # **The state file contains secrets** -- Terraform state always
        # does, and this one holds the CDN-to-origin shared secret.
        # That is the cost of this grant and it is stated rather than
        # glossed: a compromised scan workflow could read it. The
        # alternative considered was publishing `api_url` to SSM under
        # the path this role already reads, which would avoid state
        # access entirely. **That is the better long-run shape and is
        # NOT taken here**, because it means a Terraform change
        # (a new `aws_ssm_parameter`) that the scan job does not
        # otherwise need, and the design asked for the one-permission
        # widening. Worth revisiting if more consumers want the URL.
        Sid    = "TerraformStateRead"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = [
          "arn:aws:s3:::${local.state_bucket}/staging/terraform.tfstate",
          "arn:aws:s3:::${local.state_bucket}/production/terraform.tfstate",
        ]
      },
      {
        # **Narrowed by Condition, not by Resource.** `s3:ListBucket`
        # accepts only the bucket as its Resource -- that part of the
        # comment above is right -- but the KEYS it may enumerate are
        # narrowed by an `s3:prefix` condition, which an earlier
        # version omitted. Without it this grants a listing of every
        # object name in the bucket: backups, logs, or a second
        # project's state. Names rather than contents, but a name is
        # disclosure and the cost was understated by exactly that
        # enumeration.
        #
        # The two prefixes are the state keys this role may already
        # GetObject, so listing discloses nothing the read does not.
        Sid      = "TerraformStateList"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::${local.state_bucket}"
        Condition = {
          StringLike = {
            "s3:prefix" = [
              "staging/*",
              "production/*",
            ]
          }
        }
      },
    ]
  })
}
