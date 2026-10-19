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

  # a-zone, deterministically. Lightsail AZs are region + letter, and
  # pinning one keeps a replacement instance in the same place as its
  # static IP.
  availability_zone = "${var.region}a"
}

module "app" {
  source = "./modules/app"

  name_prefix       = local.name_prefix
  availability_zone = local.availability_zone
  bundle_id         = var.instance_bundle
  ssh_key_pair_name = var.ssh_key_pair_name
  operator_ip_cidr  = var.operator_ip_cidr
}

# The staging host. team.md requires one: staging is where a migration
# is rehearsed before it touches real teacher and child data, and there
# is no multi-AZ database to fail over to if it goes wrong.
module "staging_app" {
  source = "./modules/app"
  count  = var.enable_staging_instance ? 1 : 0

  name_prefix       = "shikkhokplus-staging-rehearsal"
  availability_zone = local.availability_zone
  bundle_id         = var.instance_bundle
  ssh_key_pair_name = var.ssh_key_pair_name
  operator_ip_cidr  = var.operator_ip_cidr
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
}
