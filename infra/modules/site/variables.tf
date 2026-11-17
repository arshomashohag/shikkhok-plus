variable "name_prefix" {
  description = "Prefix for resource names and comments, e.g. shikkhokplus-staging."
  type        = string
}

variable "domain_name" {
  description = <<-EOT
    This environment's project zone, e.g. shikkhokplus.nirmatabd.com. The
    site is served at its apex and at www.<this>, which redirects to it.
  EOT
  type        = string
}

variable "api_origin_fqdn" {
  description = <<-EOT
    The API host's origin name, the same FQDN the API distribution uses.
    The /hub/* behaviour reaches the public hub pages there, https-only.
  EOT
  type        = string
}

variable "origin_secret" {
  description = <<-EOT
    The value of the origin-secret header the origin requires on every
    request. The hub origin sends it exactly as the API distribution does.
  EOT
  type        = string
  sensitive   = true
}

variable "zone_id" {
  description = <<-EOT
    The Route53 zone for domain_name, holding the alias records and the ACM
    validation records. Passed in rather than looked up: on a first apply
    the zone is created in the same run, and a lookup would race it.
  EOT
  type        = string
}
