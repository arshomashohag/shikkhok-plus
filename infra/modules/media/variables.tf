variable "name_prefix" {
  description = "Prefix for resource names, e.g. shikkhokplus-staging. The role is <this>-media; the bucket <this>-media-<account id>."
  type        = string
}

variable "permissions_boundary_arn" {
  description = <<-EOT
    This environment's workload boundary, created by infra/bootstrap. The
    infrastructure role may create a role only under it, and it caps the
    media role at this bucket's objects whatever is attached later.
  EOT
  type        = string
}

variable "instance_role_arn" {
  description = <<-EOT
    The primary app host's instance role, the ONLY principal the media role
    trusts. The host's cron job assumes the media role with it and writes
    the short-lived credentials the API container reads [H3 deviation 1].
  EOT
  type        = string
}

variable "site_distribution_arn" {
  description = <<-EOT
    The public site's distribution, the only reader of public/* (Origin
    Access Control). It serves approved photos at /m/*.
  EOT
  type        = string
}

variable "web_app_origin" {
  description = <<-EOT
    The web app's origin, https://<host> with no path: the only origin the
    bucket's CORS rule lets POST an upload. Derived from web-url exactly as
    deploy.yml derives SHIKKHOKPLUS_WEB_APP_URL.
  EOT
  type        = string

  validation {
    condition     = can(regex("^https://[a-z0-9.-]+$", var.web_app_origin))
    error_message = "web_app_origin must be a bare https origin, e.g. https://app.example.com."
  }
}

variable "log_retention_days" {
  description = <<-EOT
    How long the image sanitiser's logs are kept: 30 days, as the app's
    container logs. Its lines carry a media id and an outcome, never image
    bytes, metadata or anything a person typed.
  EOT
  type        = number
  default     = 30
}
