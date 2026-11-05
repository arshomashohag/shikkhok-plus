variable "name_prefix" {
  description = "Prefix for resource names and comments."
  type        = string
}

variable "domain_name" {
  description = "The apex domain whose Route53 zone already exists."
  type        = string
}

variable "zone_id" {
  description = <<-EOT
    The Route53 zone holding the API record and the ACM validation
    records. Passed in rather than looked up: on a first apply the
    zone is created in the same run, and a lookup would race it.
  EOT
  type        = string
}

variable "api_subdomain" {
  description = "Host part of the API record."
  type        = string
}


variable "origin_secret" {
  description = <<-EOT
    The shared secret CloudFront sends as X-Origin-Secret and the
    origin's nginx requires. Sensitive: anyone holding it can bypass
    the CDN and reach the origin directly.
  EOT
  type        = string
  sensitive   = true
}

variable "origin_subdomain" {
  description = <<-EOT
    Host part of the record naming the origin, e.g. "origin" for
    origin.shikkhokplus.nirmatabd.com.

    Exists because CloudFront refuses an IP as an origin
    (`InvalidArgument: The parameter origin name cannot be an IP
    address`). It also decouples the distribution from the host's
    address: repointing this record moves the origin without a
    distribution update.
  EOT
  type        = string
  default     = "origin"
}

variable "ui_subdomain" {
  description = <<-EOT
    Host part of the web client's own hostname, e.g. "app" for
    app.shikkhokplus.nirmatabd.com, added as a second alias on this
    distribution. Empty for none: the web client is then served only at
    https://<api host>/ui/. Changing it replaces the certificate.
  EOT
  type        = string
  default     = "app"

  validation {
    condition     = can(regex("^([a-z0-9]([a-z0-9-]*[a-z0-9])?)?$", var.ui_subdomain))
    error_message = "ui_subdomain must be a single DNS label (lower-case letters, digits, hyphens) or empty."
  }
}
