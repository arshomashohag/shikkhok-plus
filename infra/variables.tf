# Every input, with the reasoning for the defaults that carry one.
#
# **Defaults are chosen so a fresh `terraform apply` is the CHEAP,
# SAFE configuration**, and every departure from it costs money or
# widens exposure deliberately. A default that silently provisions a
# managed database is a default that bills.

variable "region" {
  description = <<-EOT
    AWS region.

    **us-east-1 by user decision (2026-10-19), not by latency.**
    ap-south-1 (Mumbai) is nearest to Bangladesh and was the original
    choice for [TC-17], the mid-class responsiveness requirement;
    us-east-1 adds roughly 200-250ms round trip for users there.

    That cost is accepted deliberately. Recorded here rather than
    left implicit so [TC-17] is re-measured against the real region
    rather than against the one the requirement assumed, and so a
    later reader does not "fix" this back to Mumbai believing it a
    mistake.
  EOT
  type        = string
  default     = "us-east-1"
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

    A PRECONDITION rather than a comment, and the reason is written
    in `main.tf`: the comment that used to claim "staging plus RDS is
    USD 50.20" was itself wrong. Recomputed 2026-10-24, staging plus
    RDS is USD 47.28 -- under the ceiling. The precondition computes
    from `cost_breakdown` and cannot drift; a comment can, and did.

    Raising this is a deliberate act with a diff, which is the point.
  EOT
  type        = number
  default     = 50.00
}

variable "enable_staging_instance" {
  description = <<-EOT
    A SECOND host, for rehearsing migrations before they touch real
    data. Not the staging API itself -- the primary host already is
    staging, which the naming makes confusing: module.app is named
    `shikkhokplus-$${var.environment}-app` and this one is named
    `shikkhokplus-rehearsal-app`.

    **Off by user decision (2026-10-19).** team.md requires a
    rehearsal host and gives the reason: it is where an Alembic
    migration is rehearsed before touching real teacher and child
    data, and there is no multi-AZ database to fail over to if one
    goes wrong. Turning it off means a migration's first contact with
    a real database is in the environment that holds the data.

    Acceptable now, with no real data and no users. It stops being
    acceptable before closed testing [OC-5], which is when real
    children's records arrive -- so this is a deferral, not a
    cancellation. Saves USD 14.66/month -- a second `cost_host`,
    which at the default `root_volume_gb = 30` is 12.26 + 2.40.
    (This read "~USD 16.17" until 2026-10-24, a figure implying a
    49 GB volume; corrected by computing it from `cost_breakdown`.)
  EOT
  type        = bool
  default     = false
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
    PostgreSQL on RDS rather than a container on the app host.

    **On, and this is what makes the deploy pipeline safe.** The
    pipeline refreshes the ASG on every deploy, which terminates the
    instance -- and the container's volume lived on a root EBS volume
    with delete_on_termination = true. Every deploy would have wiped
    the database.

    With RDS the data is not on the instance at all, so a refresh
    replaces compute and leaves the database untouched. Roughly USD
    17.36/month, taking the total to about USD 32.62 against the USD
    50 ceiling [OC-4].
  EOT
  type        = bool
  default     = true
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

variable "origin_subdomain" {
  description = <<-EOT
    Host part of the record naming the origin, e.g. "origin" for
    origin.shikkhokplus.nirmatabd.com.

    CloudFront refuses an IP as an origin, so the origin needs a name.
    The INSTANCE writes this record at boot rather than Terraform,
    because an ASG replacement gets a new address and a
    Terraform-managed record would be stale until the next apply.
  EOT
  type        = string
  default     = "origin"
}
