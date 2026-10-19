# Every input, with the reasoning for the defaults that carry one.
#
# **Defaults are chosen so a fresh `terraform apply` is the CHEAP,
# SAFE configuration**, and every departure from it costs money or
# widens exposure deliberately. A default that silently provisions a
# managed database is a default that bills.

variable "region" {
  description = "AWS region. Mumbai is nearest to Bangladesh [TC-17]."
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "staging or production. Drives naming and tagging."
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "apex_domain" {
  description = <<-EOT
    The apex domain whose Route53 zone already exists, e.g.
    "nirmatabd.com". Looked up, never created, and never modified
    except for this project's one NS delegation record -- it serves
    other projects too.
  EOT
  type        = string
}

variable "project_subdomain" {
  description = <<-EOT
    The label this project's own zone takes under the apex. With
    apex_domain = "nirmatabd.com" and this = "shikkhokplus", the zone
    is shikkhokplus.nirmatabd.com and the API is
    api.shikkhokplus.nirmatabd.com.

    A dedicated zone rather than records in the apex: the apex serves
    other projects, and the CDN module's `allow_overwrite` would take
    a name from one of them with the plan showing only a create.
  EOT
  type        = string
  default     = "shikkhokplus"
}

variable "api_subdomain" {
  description = "Host part of the API record, e.g. api -> api.example.com."
  type        = string
  default     = "api"
}

variable "instance_type" {
  description = <<-EOT
    t4g.small: 2 GB on Graviton, ~USD 13.43/month on demand. The 2 GB
    figure is LOAD-BEARING rather than a default -- it is the size
    every performance decision in this project assumed [team.md], and
    why lens resolution memoizes per request instead of caching across
    them.

    arm64: the backend image must be built for it, or `docker run`
    fails with an exec format error that does not mention
    architecture.
  EOT
  type        = string
  default     = "t4g.small"
}

variable "root_volume_gb" {
  description = <<-EOT
    Root volume size in GB. Holds the containerised PostgreSQL in
    Phase 1, which is why 30 rather than the 8 GB default: a database
    that fills its disk stops accepting writes, and recovering that on
    a live host is worse than paying USD 2 more a month.
  EOT
  type        = number
  default     = 30
}

# **There is deliberately no operator IP variable, and no SSH key.**
#
# The earlier design restricted port 22 to an operator IP held as a CI
# secret. A home IP is dynamic, so recovering access after a router
# restart meant editing a secret, dispatching a workflow, waiting for
# approval and waiting for an apply -- and that friction is precisely
# what makes somebody widen the rule to 0.0.0.0/0 once "just to get
# in", after which it stays.
#
# SSM Session Manager removes the question entirely: no inbound port,
# no key pair, no address to track. Access is an IAM-authenticated API
# call, and CloudTrail records who opened a session -- which is what
# team.md's "named, logged and bounded" rule asks for and nothing
# previously enforced.
#
#   aws ssm start-session --target $(terraform output -raw app_instance_id)

variable "acknowledged_monthly_budget" {
  description = <<-EOT
    The ceiling an apply may not silently cross. project.md: always
    keep infrastructure spend under USD 50/month [OC-4].

    A PRECONDITION rather than a comment, because the arithmetic
    caught a real overrun: staging plus RDS is USD 50.20. Raising this
    is a deliberate act with a diff, which is the point.
  EOT
  type        = number
  default     = 50.00
}

variable "enable_staging_instance" {
  description = <<-EOT
    A second host for staging. team.md requires one, because staging
    is where a migration is rehearsed before it touches real teacher
    and child data, and there is no multi-AZ database to fail over to
    if it goes wrong. Costs ~USD 16.17/month.
  EOT
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------
# Phase 2. Written now, disabled now.
#
# The module EXISTS so Phase 2 is a variable flip rather than an
# architecture change -- but it defaults OFF, because a default that
# provisions a managed database is a default that bills USD 17/month
# the first time somebody runs apply to see what happens.
# ---------------------------------------------------------------------

variable "enable_rds" {
  description = <<-EOT
    Provision RDS PostgreSQL instead of the containerised database.

    **Phase 1 runs Postgres in a container on the app host**, bound to
    127.0.0.1 and exposed to nothing. Turn this on in Phase 2, when
    automated backups and point-in-time recovery outweigh ~USD
    17/month.

    Moving to EC2 made this clean: the database's ingress rule
    references the app's SECURITY GROUP, so "only the app host" is
    exact rather than a CIDR guess. On Lightsail that was impossible
    -- instances live outside your VPC and have no group to name --
    which is why the original "RDS in a public subnet with ingress
    only from Lightsail" could not be built as asked.
  EOT
  type        = bool
  default     = false
}

variable "rds_instance_class" {
  description = "RDS instance class, Phase 2. db.t4g.micro is ~USD 14.60/month."
  type        = string
  default     = "db.t4g.micro"
}

variable "rds_allocated_storage" {
  description = "RDS storage in GB, Phase 2. gp3 at ~USD 0.138/GB."
  type        = number
  default     = 20
}
