variable "name_prefix" {
  description = "Prefix for resource names and comments, e.g. shikkhokplus-staging."
  type        = string
}

variable "domain_name" {
  description = <<-EOT
    This environment's project zone, e.g. shikkhokplus.nirmatabd.com. The
    admin surface is served at <admin_subdomain>.<this>.
  EOT
  type        = string
}

variable "zone_id" {
  description = <<-EOT
    The Route53 zone for domain_name, holding the alias record and the ACM
    validation records. Passed in rather than looked up: on a first apply
    the zone is created in the same run, and a lookup would race it.
  EOT
  type        = string
}

variable "admin_subdomain" {
  description = "Host part of the admin hostname, e.g. \"admin\" for admin.shikkhokplus.nirmatabd.com."
  type        = string
  default     = "admin"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.admin_subdomain))
    error_message = "admin_subdomain must be a single DNS label: lower-case letters, digits and hyphens."
  }
}

variable "admin_allowed_cidrs" {
  description = <<-EOT
    IPv4 CIDRs allowed to reach the admin hostname at all, e.g.
    ["203.0.113.7/32"]. Checked at the edge by a CloudFront Function on
    the viewer's address. IPv4 only, because the distribution serves
    IPv4 only. Empty lets nobody in.
  EOT
  type        = list(string)
  default     = []
  # The repository is public, and a plan is printed to its public
  # Actions logs: an administrator's address stays out of them.
  sensitive = true

  validation {
    condition = alltrue([
      for cidr in var.admin_allowed_cidrs :
      can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/[0-9]{1,2}$", cidr)) && can(cidrhost(cidr, 0))
    ])
    error_message = "Every admin_allowed_cidrs entry must be an IPv4 CIDR such as 203.0.113.7/32 (no IPv6: the admin distribution serves IPv4 only)."
  }
}

variable "origin_fqdn" {
  description = <<-EOT
    The API origin's name, e.g. origin.shikkhokplus.nirmatabd.com: the same
    custom origin the API distribution forwards to, so /v1/admin/* reaches
    the same nginx and the same application.
  EOT
  type        = string
}

variable "origin_secret" {
  description = <<-EOT
    The X-Origin-Secret value nginx requires on every request (modules/app).
    Sensitive: anyone holding it can bypass the CDN and reach the origin.
  EOT
  type        = string
  sensitive   = true
}
