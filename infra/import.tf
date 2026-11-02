# Adopting resources an earlier failed STAGING apply created.
#
# **Why this exists.** Several staging applies failed partway -- on a
# permission, then on the security-group rule quota. CloudFront had
# already been created by the time the later error aborted the run,
# but the state write never happened, so Terraform did not know it
# owned a distribution that existed. The next apply then tried to
# CREATE one and AWS refused with `CNAMEAlreadyExists`, because the
# alias was already attached to the distribution Terraform forgot.
#
# **Staging only, by construction** [OPS-10]. The block used to be
# unconditional, and the state key is per environment -- so the first
# production apply would have imported STAGING's distribution into
# production's state, and the two environments' applies would then
# have fought over one distribution. `for_each` on the environment
# makes it impossible for this block to touch any other state.
#
# For a resource already in state the import is a no-op, which is what
# it now is in staging; it stays only because removing it is a change
# nobody can verify from here, and it is harmless where it applies.

import {
  for_each = var.environment == "staging" ? toset(["E1WAMR4H60DX9V"]) : toset([])

  to = module.cdn.aws_cloudfront_distribution.api
  id = each.key
}

# **Only the distribution.** The `api.` alias records did not exist --
# verified against the zone, which held only the ACM validation CNAME
# and the instance's self-registered `origin.` A record.
#
# A second hosted zone for staging's domain also exists
# (Z0757622VSB8RDYIC86I), created by one of the same failed applies.
# It is not delegated -- the parent points at Z047640733UWE123SQI2U,
# which is the one in state -- so it resolves for nobody and costs USD
# 0.50/month. Delete it separately; it is not referenced here.
