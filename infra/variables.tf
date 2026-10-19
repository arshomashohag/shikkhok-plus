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

variable "domain_name" {
  description = <<-EOT
    The apex domain whose Route53 zone already exists, e.g.
    "shikkhokplus.com". The zone is LOOKED UP, never created: creating
    one for a domain whose nameservers point elsewhere produces a zone
    that resolves for nobody and bills USD 0.50/month regardless.
  EOT
  type        = string
}

variable "api_subdomain" {
  description = "Host part of the API record, e.g. api -> api.example.com."
  type        = string
  default     = "api"
}

variable "instance_bundle" {
  description = <<-EOT
    The Lightsail bundle. `small_2_0` is 2 GB RAM at USD 12/month, and
    that figure is LOAD-BEARING rather than a default: it is the size
    every performance decision in this project assumed [team.md], and
    it is why lens resolution memoizes per request instead of caching
    across them. Changing it is a performance-model change.
  EOT
  type        = string
  default     = "small_2_0"
}

variable "ssh_key_pair_name" {
  description = <<-EOT
    An EXISTING Lightsail key pair name. Terraform does not create one:
    creating a key pair puts the private key in state, and state is a
    file on disk. Create it once in the console and name it here.
  EOT
  type        = string
}

variable "operator_ip_cidr" {
  description = <<-EOT
    Your IP as a /32, for SSH. **Not 0.0.0.0/0**, and the validation
    below refuses that: an SSH port open to the internet on a host
    holding children's data is the single cheapest mistake to make
    here. Find yours with `curl -s https://checkip.amazonaws.com`.
  EOT
  type        = string

  validation {
    condition     = var.operator_ip_cidr != "0.0.0.0/0"
    error_message = "Refusing 0.0.0.0/0 for SSH. Use your own IP as a /32."
  }

  validation {
    condition     = can(cidrhost(var.operator_ip_cidr, 0))
    error_message = "operator_ip_cidr must be valid CIDR, e.g. 203.0.113.4/32."
  }
}

variable "enable_staging_instance" {
  description = <<-EOT
    A second Lightsail host for staging. team.md requires one, because
    staging is where a migration is rehearsed before it touches real
    teacher and child data and there is no multi-AZ database to fail
    over to. Costs USD 12/month.
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

    **Phase 1 runs Postgres on the Lightsail host**, and that is a
    privacy decision as much as a cost one: RDS security groups cannot
    name a Lightsail instance, because Lightsail lives outside your
    VPC. "Ingress only from Lightsail" is therefore expressible only
    as a public /32 allowlist -- which routes children-identifying
    traffic over the public internet -- or as VPC peering. A database
    on localhost is exposed to nothing at all.

    Turn this on in Phase 2, when automated backups and
    point-in-time recovery outweigh USD 17/month. The module places it
    in a PRIVATE subnet reached by VPC peering, never a public one.
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
