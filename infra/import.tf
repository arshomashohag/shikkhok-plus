# Adopting resources an earlier failed apply created.
#
# **Why these exist.** Several applies failed partway -- on a
# permission, then on the security-group rule quota. CloudFront had
# already been created by the time the later error aborted the run,
# but the state write never happened, so Terraform does not know it
# owns a distribution that exists. The next apply then tries to
# CREATE one and AWS refuses with `CNAMEAlreadyExists`, because the
# alias is already attached to the distribution Terraform forgot.
#
# Importing is the cheap fix: the distribution is correct -- right
# origin, right certificate, Deployed -- and deleting it would mean
# disabling, waiting for propagation, and recreating, which is
# 30-40 minutes to arrive back where we already are.
#
# **Delete this file once the apply has run.** An import block for a
# resource already in state is a no-op, so leaving it is harmless --
# but it describes a one-time recovery and reads as permanent
# configuration.

import {
  to = module.cdn.aws_cloudfront_distribution.api
  id = "E1WAMR4H60DX9V"
}

# **Only the distribution.** The `api.` alias records do NOT exist --
# verified against the zone, which holds only the ACM validation
# CNAME and the instance's self-registered `origin.` A record. The
# apply failed before reaching them, so Terraform creating them is
# correct rather than a conflict.
#
# A second hosted zone for this domain also exists
# (Z0757622VSB8RDYIC86I), created by one of the same failed applies.
# It is not delegated -- the parent points at
# Z047640733UWE123SQI2U, which is the one in state -- so it resolves
# for nobody and costs USD 0.50/month. Delete it separately; it is
# not referenced here.
