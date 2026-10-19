# Recovery when this module's local state is lost.
#
# **The three resources still exist in AWS; only the record of them is
# gone.** The next apply would then try to CREATE them and fail with
# `EntityAlreadyExists` and `BucketAlreadyOwnedByYou` -- errors that
# read like a bug in this module rather than a missing state file.
#
# These are `import` blocks rather than a paragraph telling you to run
# `terraform import`, because a documented command is one nobody can
# find under pressure and a block is one `terraform plan` checks.
#
# To recover:
#
#   1. terraform init
#   2. terraform plan -var recover_existing=true
#        -> "3 to import, 0 to add, 0 to change, 0 to destroy"
#      ANY "to add" or "to destroy" means the names below do not match
#      what is actually in the account. STOP and read them.
#   3. terraform apply -var recover_existing=true
#   4. Leave recover_existing at false afterwards.
#
# If the plan is clean, state is rebuilt and nothing in AWS changed.

import {
  for_each = var.recover_existing ? toset(["x"]) : toset([])

  to = aws_s3_bucket.state
  id = local.state_bucket
}

import {
  for_each = var.recover_existing ? toset(["x"]) : toset([])

  to = aws_iam_role.ci
  id = "shikkhokplus-github-actions"
}

import {
  for_each = var.recover_existing ? toset(["x"]) : toset([])

  to = aws_iam_openid_connect_provider.github
  id = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
}
