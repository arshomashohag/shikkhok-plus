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

module "app" {
  source = "./modules/app"

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
  domain_name   = var.domain_name
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
