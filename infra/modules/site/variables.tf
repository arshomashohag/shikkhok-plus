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

variable "zone_id" {
  description = <<-EOT
    The Route53 zone for domain_name, holding the alias records and the ACM
    validation records. Passed in rather than looked up: on a first apply
    the zone is created in the same run, and a lookup would race it.
  EOT
  type        = string
}
