# The Phase 1 backend, composed.
#
# **One production host, one staging host, a CDN in front, and a
# database that is not on the network at all.** Measured at USD
# 24.50/month against the USD 50 ceiling [OC-4]; the Phase 2 path to
# RDS is written and disabled, costing USD 41.86 when enabled.
#
# What is deliberately NOT here, so nobody reads the absence as an
# oversight:
#
#   * **No ALB.** It would consume a third of the budget before any
#     compute, for 100 teachers on one instance [D-29].
#   * **No SSH, and no bastion.** Session Manager replaces both: a
#     shell over an IAM-authenticated outbound channel, logged to
#     CloudTrail by name. There is no inbound port to misconfigure.
#   * **No NAT gateway.** USD 32/month -- more than both instances
#     combined -- to avoid public IPs on hosts whose inbound is closed
#     by the security group anyway.
#   * **No RDS in Phase 1.** See modules/database -- a managed database
#     reachable only from one IP routes children-identifying traffic
#     over the public internet, which is weaker than localhost.
#   * **No auto-scaling group.** One instance is the design; a group of
#     one is machinery that implies a capability we do not have.
#   * **No WAF.** USD 5/month plus per-rule charges to protect an API
#     that is authenticated on 10 of 11 routes, where the OTP ceilings
#     already live in the application and survive a worker restart.

locals {
  name_prefix = "shikkhokplus-${var.environment}"

  # The zone this project owns, e.g. shikkhokplus.nirmatabd.com.
  # The API is served at `${var.api_subdomain}.${this}`.
  project_domain = "${var.project_subdomain}.${var.apex_domain}"
}

# **The budget is a precondition, checked before anything is created.**
#
# Computed rather than asserted, and it caught a real overrun: staging
# plus RDS is USD 50.20 against a USD 50 ceiling [OC-4]. Twenty cents,
# which is exactly the kind of number a comment gets wrong and an
# expression does not.
#
# Phase 2 therefore requires a choice -- retire the rehearsal host, or
# raise the ceiling deliberately -- rather than discovering it on a
# bill. Set `acknowledged_monthly_budget` higher to proceed anyway.
locals {
  monthly_cost = (
    16.67 +
    # The project's own hosted zone. Small, and counted: the Phase 2
    # total was already USD 50.20 against a USD 50 ceiling, so an
    # uncounted 50 cents is the difference between a precondition
    # that holds and one that is quietly wrong.
    0.50 +
    (var.enable_staging_instance ? 16.17 : 0.00) +
    (var.enable_rds ? 17.36 : 0.00)
  )
}

resource "terraform_data" "budget_guard" {
  lifecycle {
    precondition {
      condition     = local.monthly_cost <= var.acknowledged_monthly_budget
      error_message = <<-EOT
        Estimated USD ${local.monthly_cost}/month exceeds the
        acknowledged budget of USD ${var.acknowledged_monthly_budget}
        [OC-4: always keep infrastructure spend under USD 50/month].

        Staging and RDS together are USD 50.20. Either set
        enable_staging_instance = false, or raise
        acknowledged_monthly_budget deliberately.
      EOT
    }
  }
}

module "network" {
  source = "./modules/network"

  name_prefix = local.name_prefix
}

module "registry" {
  source = "./modules/registry"

  name_prefix = local.name_prefix
}

module "app" {
  source = "./modules/app"

  ecr_repository_arn = module.registry.repository_arn
  ecr_repository_url = module.registry.repository_url

  name_prefix    = local.name_prefix
  vpc_id         = module.network.vpc_id
  subnet_id      = module.network.public_subnet_ids[0]
  instance_type  = var.instance_type
  root_volume_gb = var.root_volume_gb
}

# The staging host. team.md requires one: staging is where a migration
# is rehearsed before it touches real teacher and child data, and there
# is no multi-AZ database to fail over to if it goes wrong.
module "staging_app" {
  source = "./modules/app"
  count  = var.enable_staging_instance ? 1 : 0

  name_prefix    = "shikkhokplus-rehearsal"
  vpc_id         = module.network.vpc_id
  subnet_id      = module.network.public_subnet_ids[1]
  instance_type  = var.instance_type
  root_volume_gb = var.root_volume_gb
}

module "cdn" {
  source = "./modules/cdn"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix   = local.name_prefix
  domain_name   = local.project_domain
  zone_id       = aws_route53_zone.project.zone_id
  api_subdomain = var.api_subdomain
  origin_ip     = module.app.static_ip
  origin_secret = module.app.origin_secret
}

module "database" {
  source = "./modules/database"

  enabled           = var.enable_rds
  name_prefix       = local.name_prefix
  instance_class    = var.rds_instance_class
  allocated_storage = var.rds_allocated_storage
  vpc_id            = module.network.vpc_id
  subnet_ids        = module.network.public_subnet_ids
  # **A real security group, not a CIDR.** This is what moving to EC2
  # bought: Lightsail had no security group for a database to
  # reference, so "ingress only from the app" could only ever be a
  # CIDR guess or a VPC peering range. Now it is exact.
  app_security_group_id = module.app.security_group_id
}

# ---------------------------------------------------------------------
# DNS: this project's own zone, delegated from the apex
# ---------------------------------------------------------------------
#
# **Here rather than in bootstrap, so the zone and the certificate
# that validates against it live in one module.** ACM validation
# writes CNAME records into this zone, and splitting the two meant a
# bootstrap apply had to precede every certificate change.
#
# **A dedicated subdomain rather than the apex.** The apex zone
# already serves other projects, and the CDN module sets
# `allow_overwrite = true` -- correct for ACM validation records it
# was added for, and fatal for an API A record, because the plan then
# shows a create rather than a destroy. Claiming a name another
# project holds would have silently repointed a running application
# with nothing in the plan to show it.
#
# USD 0.50/month for the hosted zone. Counted in the budget below.

resource "aws_route53_zone" "project" {
  name    = local.project_domain
  comment = "ShikhokPlus. Delegated from ${var.apex_domain}."
}

# The apex zone, looked up rather than created: it already exists and
# belongs to other projects too. Nothing here modifies it except the
# single NS record below.
data "aws_route53_zone" "apex" {
  name         = var.apex_domain
  private_zone = false
}

# The delegation. Without it the zone exists and resolves for nobody:
# ACM validation then hangs for its full timeout and fails with a
# message about validation timing out rather than about delegation,
# which is a slow and confusing way to find this.
resource "aws_route53_record" "delegation" {
  zone_id = data.aws_route53_zone.apex.zone_id
  name    = local.project_domain
  type    = "NS"
  ttl     = 172800
  records = aws_route53_zone.project.name_servers

  # No allow_overwrite. If something already holds this name the
  # apply must FAIL rather than quietly take it -- which is the exact
  # mistake the comment above describes avoiding.
}
