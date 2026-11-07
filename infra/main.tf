# The Phase 1 backend, composed.
#
# **One app host per environment in an auto-scaling group of one, a
# CDN in front, and RDS behind it.** The monthly figure against the USD
# 50 ceiling [OC-4] is `terraform output monthly_cost_estimate`, computed
# by the same expression the budget precondition below enforces -- it
# is deliberately not restated here, because restated figures in this
# file have been wrong before.
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
#   * **No database on the host.** The host is replaced on every deploy
#     and its root volume with it, so the database is RDS, reachable
#     only from the app's security group (modules/database), and
#     production refuses to plan without it [OPS-7].
#   * **No scaling.** The auto-scaling group is desired-one with no
#     policy; it exists so a failed host is replaced, and so a deploy
#     can launch the new host before terminating the old [OPS-6].
#   * **No WAF.** USD 5/month plus per-rule charges to protect an API
#     that is authenticated on 10 of 11 routes, where the OTP ceilings
#     already live in the application and survive a worker restart.

data "aws_caller_identity" "current" {}

locals {
  name_prefix = "shikkhokplus-${var.environment}"

  # Created by infra/bootstrap, which this configuration cannot read
  # (its state is local to whoever ran it), so the ARN is derived from
  # the fixed name and path rather than looked up. A mismatch fails the
  # apply at CreateRole with AccessDenied, not silently.
  #
  # **This environment's boundary** [C-08]: it allows reading only this
  # environment's parameters, so a staging host cannot read
  # production's signing keys, and this environment's infrastructure
  # role may create roles under no other.
  permissions_boundary_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/shikkhokplus/shikkhokplus-workload-boundary-${var.environment}"

  # **The zone label is per ENVIRONMENT** [OPS-10]. It was one label
  # for every environment, so a production apply would have created a
  # second zone with staging's name, failed on the NS delegation staging
  # already holds in the apex, and asked for CloudFront aliases staging's
  # distribution already owns -- production could not exist beside
  # staging at all.
  #
  # Staging keeps exactly the names it was created with, so its state
  # does not churn: zone shikkhokplus.<apex>, API api.shikkhokplus.<apex>.
  # Production gets a sibling zone directly under the apex -- NOT a
  # child of staging's zone, whose delegation would then live in
  # staging's state. Override with `project_subdomain` to choose the
  # production name; the label must contain "shikkhokplus", because the
  # CI role may only change record names that do [OPS-2].
  default_project_subdomain = {
    staging    = "shikkhokplus"
    production = "shikkhokplus-prod"
  }
  project_subdomain = coalesce(var.project_subdomain, local.default_project_subdomain[var.environment])

  # The zone this environment owns, e.g. shikkhokplus.nirmatabd.com.
  # The API is served at `${var.api_subdomain}.${this}`.
  project_domain = "${local.project_subdomain}.${var.apex_domain}"
}

# **The budget is a precondition, checked before anything is created.**
#
# Computed rather than asserted. This comment used to list the totals
# for each configuration, and those figures were wrong twice: once
# because the defaults moved under them, and again because the model
# had no line for public IPv4 at all [OPS-12]. The totals now live in
# one place -- `terraform output monthly_cost_estimate`, which is the
# same expression the precondition checks -- and this comment states
# none of them.
#
# Note what the IPv4 line does: with RDS on, adding the rehearsal host
# now crosses the ceiling, so Phase 2 with a rehearsal host is a
# deliberate choice -- retire it, or raise `acknowledged_monthly_budget`
# -- rather than something discovered on a bill.
locals {
  # **One cost model, used by BOTH the precondition below and the
  # monthly_cost_estimate output.** A budget guard computing from a
  # number nobody checks is decoration.
  #
  # Unit prices, us-east-1, from the AWS Price List API (2026-10-19)
  # and AWS's published pricing pages:
  #   t4g.small on-demand   USD 0.0168/hr x 730 = USD 12.26
  #   gp3 storage           USD 0.08/GB-month
  #   public IPv4 address   USD 0.005/hr x 730 = USD 3.65 per host.
  #                         Charged since 2024-02 for EVERY public
  #                         IPv4 address, attached or not; each host has
  #                         one because there is no NAT gateway [OPS-12]
  #   Route53 hosted zone   USD 0.50
  #   CloudWatch alarm      USD 0.10 per standard alarm
  #   CloudWatch Logs       USD 0.50/GB ingested; 1 GB/month assumed
  #   CloudFront, ACM, SNS email, Budgets (first two)  USD 0.00
  cost_instance    = 12.26
  cost_storage     = var.root_volume_gb * 0.08
  cost_public_ipv4 = 3.65
  cost_host        = local.cost_instance + local.cost_storage + local.cost_public_ipv4

  cost_breakdown = {
    app_instance     = local.cost_host
    staging_instance = var.enable_staging_instance ? local.cost_host : 0.00
    route53_zone     = 0.50
    ecr              = 0.10
    cloudfront       = 0.00
    acm              = 0.00
    # The public site (modules/site): a second distribution, certificate
    # and CloudFront Function, all inside their free tiers, and a bucket
    # holding under a megabyte -- a fraction of a cent.
    site = 0.00
    # The admin surface (modules/admin): a third distribution, certificate
    # and CloudFront Function, all inside their free tiers, a bucket of a
    # few hundred kilobytes, and Standard SSM parameters, which are free.
    # No WAF: the IP allowlist is a CloudFront Function, which is why it
    # costs nothing.
    admin  = 0.00
    rds    = var.enable_rds ? 17.36 : 0.00
    alarms = length(local.alarm_names) * 0.10
    logs   = 0.50
    # Pay per invocation: a three-month seed is about 60 GB-seconds on
    # arm64, a fraction of a cent, and inside the free tier anyway.
    seeder = 0.00
  }

  monthly_cost = sum(values(local.cost_breakdown))
}

resource "terraform_data" "budget_guard" {
  lifecycle {
    precondition {
      condition     = local.monthly_cost <= var.acknowledged_monthly_budget
      error_message = <<-EOT
        Estimated USD ${local.monthly_cost}/month exceeds the
        acknowledged budget of USD ${var.acknowledged_monthly_budget}
        [OC-4: always keep infrastructure spend under USD 50/month].

        Breakdown: ${jsonencode(local.cost_breakdown)}

        Either disable what you do not need
        (enable_staging_instance, enable_rds), or raise
        acknowledged_monthly_budget deliberately.
      EOT
    }
  }
}

# **Production refuses a database that lives on the host** [OPS-7].
#
# The deploy pipeline replaces the app host on every release, and the
# root volume is delete_on_termination = true. With enable_rds = false
# the database would be on that volume -- so the next deploy, or any
# failure replacement, deletes every teacher's and child's record with
# no backup. That configuration is not a cheaper production; it is one
# deploy away from data loss, so it is refused before anything is
# created rather than documented and hoped about.
#
# Staging is not refused here, because a staging stack with no database
# is a legitimate way to stand up the network and CDN alone. The deploy
# workflow refuses to RELEASE to any environment without RDS -- it
# cannot take the pre-migration snapshot -- so data is never put on a
# host that is about to be replaced.
resource "terraform_data" "durable_database_guard" {
  lifecycle {
    precondition {
      condition     = var.environment != "production" || var.enable_rds
      error_message = <<-EOT
        production requires enable_rds = true.

        The deploy replaces the app host on every release and its root
        volume is deleted with it, so a database on the host would be
        destroyed by the next deploy. See infra/RESTORE.md.
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

locals {
  # Built once and passed to every host, so a second host cannot
  # silently end up without pull access -- which is what happened to
  # the rehearsal host when these were three separate arguments it
  # simply did not pass.
  image_repository = {
    arn = module.registry.repository_arn
    url = module.registry.repository_url
  }
}

module "app" {
  source = "./modules/app"

  image_repository = local.image_repository

  # Self-registration: the instance writes its own A record here at
  # boot, which is why no Elastic IP and no Terraform-owned record
  # exist. CloudFront points at the name; the address behind it moves
  # with every replacement.
  aws_region  = var.region
  account_id  = data.aws_caller_identity.current.account_id
  dns_zone_id = aws_route53_zone.project.zone_id
  origin_fqdn = "${var.origin_subdomain}.${local.project_domain}"

  # Null when RDS is off, which makes the host fall back to a
  # containerised Postgres -- the Phase 1 shape, kept working rather
  # than deleted, so enable_rds stays a genuine switch.
  database_endpoint = module.database.endpoint
  database_password = module.database.password
  managed_database  = var.enable_rds

  permissions_boundary_arn = local.permissions_boundary_arn
  alarm_topic_arn          = aws_sns_topic.alerts.arn

  name_prefix    = local.name_prefix
  vpc_id         = module.network.vpc_id
  subnet_ids     = module.network.public_subnet_ids
  instance_type  = var.instance_type
  root_volume_gb = var.root_volume_gb
}

# The staging host. team.md requires one: staging is where a migration
# is rehearsed before it touches real teacher and child data, and there
# is no multi-AZ database to fail over to if it goes wrong.
module "staging_app" {
  source = "./modules/app"
  count  = var.enable_staging_instance ? 1 : 0

  # **The same repository as the primary host.** Without this the
  # rehearsal host boots with nginx up and no API, unable to pull --
  # exactly the silent half-working state that cost an afternoon to
  # diagnose on the primary host. A rehearsal host that cannot run
  # the image cannot rehearse anything.
  image_repository = local.image_repository

  # **A DIFFERENT name from the primary host.** Both register
  # themselves at boot, and two instances writing one A record would
  # overwrite each other on every replacement -- CloudFront would then
  # reach whichever booted last.
  aws_region  = var.region
  account_id  = data.aws_caller_identity.current.account_id
  dns_zone_id = aws_route53_zone.project.zone_id
  origin_fqdn = "rehearsal-${var.origin_subdomain}.${local.project_domain}"

  permissions_boundary_arn = local.permissions_boundary_arn
  alarm_topic_arn          = aws_sns_topic.alerts.arn

  # Per environment, so a staging and a production rehearsal host
  # cannot collide on a role, bucket or group name, and so each falls
  # inside its environment's `shikkhokplus-<env>-*` deploy-role scope.
  name_prefix    = "${local.name_prefix}-rehearsal"
  vpc_id         = module.network.vpc_id
  subnet_ids     = module.network.public_subnet_ids
  instance_type  = var.instance_type
  root_volume_gb = var.root_volume_gb
}

module "cdn" {
  source = "./modules/cdn"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix      = local.name_prefix
  domain_name      = local.project_domain
  zone_id          = aws_route53_zone.project.zone_id
  api_subdomain    = var.api_subdomain
  origin_subdomain = var.origin_subdomain
  origin_secret    = module.app.origin_secret
  ui_subdomain     = var.ui_subdomain
}

# **The public URL, published where the workflows can read it without
# Terraform state.** The deploy's post-release smoke and the ZAP scan
# both need it. Reading it from state meant granting the deploy role
# s3:GetObject on a state file that holds every generated secret
# [OPS-3]; a plain String parameter under the environment's own path is
# the URL and nothing else. Terraform owns the value -- unlike the image
# tag, there is no second writer.
resource "aws_ssm_parameter" "api_url" {
  name        = "/shikkhokplus/${local.name_prefix}/api-url"
  type        = "String"
  value       = module.cdn.api_url
  description = "The public API URL. Read by deploy.yml's smoke and security-scan.yml."
}

# **Where deploy.yml puts the web client, on the same terms** [OPS-3]:
# the deploy role reads these three parameters instead of Terraform
# state. The bucket and distribution are not secrets, but they are the
# only two names the upload and the invalidation need.
resource "aws_ssm_parameter" "web_bucket" {
  name        = "/shikkhokplus/${local.name_prefix}/web-bucket"
  type        = "String"
  value       = module.cdn.web_bucket
  description = "Bucket deploy.yml uploads the built web client to, under ui/."
}

resource "aws_ssm_parameter" "distribution_id" {
  name        = "/shikkhokplus/${local.name_prefix}/distribution-id"
  type        = "String"
  value       = module.cdn.distribution_id
  description = "The distribution deploy.yml invalidates after uploading the web client."
}

resource "aws_ssm_parameter" "web_url" {
  name        = "/shikkhokplus/${local.name_prefix}/web-url"
  type        = "String"
  value       = module.cdn.web_url
  description = "The web client's public URL. Read by deploy.yml's web smoke."
}

# ---------------------------------------------------------------------
# The public site: the zone apex and www, on a distribution of its own
# ---------------------------------------------------------------------
#
# modules/site carries the design. The apex of the project zone was free:
# the zone holds only its NS and SOA there, and every other record is a
# sub-name (api., app., origin., the ACM validation CNAMEs). Always on --
# no toggle, since it costs nothing and every environment wants its site.
module "site" {
  source = "./modules/site"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix = local.name_prefix
  domain_name = local.project_domain
  zone_id     = aws_route53_zone.project.zone_id
}

# **Where deploy.yml puts the site, on the same terms as the web client**
# [OPS-3]: three plain String parameters the deploy role reads instead of
# Terraform state.
resource "aws_ssm_parameter" "site_bucket" {
  name        = "/shikkhokplus/${local.name_prefix}/site-bucket"
  type        = "String"
  value       = module.site.bucket
  description = "Bucket deploy.yml uploads the built public site to, at the root."
}

resource "aws_ssm_parameter" "site_distribution_id" {
  name        = "/shikkhokplus/${local.name_prefix}/site-distribution-id"
  type        = "String"
  value       = module.site.distribution_id
  description = "The public site's distribution, invalidated by deploy.yml after an upload."
}

resource "aws_ssm_parameter" "site_url" {
  name        = "/shikkhokplus/${local.name_prefix}/site-url"
  type        = "String"
  value       = module.site.url
  description = "The public site's origin. deploy.yml builds the site with it as SITE_URL and smokes it."
}

# ---------------------------------------------------------------------
# The platform admin surface: its own hostname, behind an IP allowlist
# ---------------------------------------------------------------------
#
# modules/admin carries the design. The admin API (/v1/admin/*) is served
# only here; the public API distribution answers it 404 (modules/cdn), and
# the application refuses it without the X-Admin-Edge header this
# distribution adds. Always on, like the site: it costs nothing, and with
# admin_allowed_cidrs empty (the default) it lets nobody in, so an
# environment nobody has allowlisted is closed rather than open.
module "admin" {
  source = "./modules/admin"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix     = local.name_prefix
  domain_name     = local.project_domain
  zone_id         = aws_route53_zone.project.zone_id
  admin_subdomain = var.admin_subdomain

  admin_allowed_cidrs = var.admin_allowed_cidrs

  # The same origin and origin secret the API distribution uses: one
  # nginx, one application, reached by two distributions.
  origin_fqdn   = module.app.origin_fqdn
  origin_secret = module.app.origin_secret
}

# **Where deploy.yml puts the admin UI, on the same terms as the site**
# [OPS-3]: plain String parameters the deploy role reads instead of
# Terraform state. The fourth, the edge secret, is a SecureString the
# module publishes itself (modules/admin), beside the value it generates.
resource "aws_ssm_parameter" "admin_bucket" {
  name        = "/shikkhokplus/${local.name_prefix}/admin-bucket"
  type        = "String"
  value       = module.admin.bucket
  description = "Bucket deploy.yml uploads the built admin UI to, at the root."
}

resource "aws_ssm_parameter" "admin_distribution_id" {
  name        = "/shikkhokplus/${local.name_prefix}/admin-distribution-id"
  type        = "String"
  value       = module.admin.distribution_id
  description = "The admin distribution, invalidated by deploy.yml after an upload."
}

resource "aws_ssm_parameter" "admin_url" {
  name        = "/shikkhokplus/${local.name_prefix}/admin-url"
  type        = "String"
  value       = module.admin.url
  description = "The admin surface's origin. deploy.yml smokes it (403 from off the allowlist)."
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
  # The staging seeder, when on: also an exact group reference.
  client_security_group_ids = compact([module.seeder.security_group_id])
}

# ---------------------------------------------------------------------
# The performance-test seeder: staging only, off by default
# ---------------------------------------------------------------------
#
# A Lambda function that writes months of realistic history into one
# teacher's account through the application's own services, for load
# and performance testing. modules/seeder carries the design; this is
# only the two refusals and the wiring.

resource "terraform_data" "seeder_guard" {
  lifecycle {
    # Refused in production at plan time; the function refuses again
    # at run time on SHIKKHOKPLUS_ENVIRONMENT. Two independent checks,
    # because a seeder creates accounts and money records.
    precondition {
      condition     = !var.enable_seeder || var.environment != "production"
      error_message = "enable_seeder is refused in production: it creates accounts and money records."
    }
    # The Phase 1 database listens on the host's 127.0.0.1, which no
    # Lambda can reach.
    precondition {
      condition     = !var.enable_seeder || var.enable_rds
      error_message = "enable_seeder needs enable_rds = true: the function reaches RDS, not a database on the host."
    }
  }
}

# The tag deployed right now, read where the deploy wrote it. Only at
# creation: deploy.yml moves the function to each release afterwards.
data "aws_ssm_parameter" "deployed_image_tag" {
  count = var.enable_seeder ? 1 : 0
  name  = module.app.image_tag_parameter
}

module "seeder" {
  source = "./modules/seeder"

  enabled     = var.enable_seeder && var.environment != "production" && var.enable_rds
  name_prefix = local.name_prefix
  environment = var.environment
  aws_region  = var.region
  account_id  = data.aws_caller_identity.current.account_id

  permissions_boundary_arn = local.permissions_boundary_arn

  image_repository = {
    arn  = module.registry.repository_arn
    name = module.registry.repository_name
    url  = module.registry.repository_url
  }
  image_tag = var.enable_seeder ? data.aws_ssm_parameter.deployed_image_tag[0].insecure_value : "none"

  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.public_subnet_ids
  database_security_group_id = coalesce(module.database.security_group_id, "none")
  database_url               = coalesce(module.app.database_url, "none")
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
