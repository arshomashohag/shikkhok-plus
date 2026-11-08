variable "name_prefix" {
  description = "Prefix for resource names, e.g. shikkhokplus-staging. Also the SSM path segment."
  type        = string
}

variable "domain_name" {
  description = <<-EOT
    This environment's project zone, e.g. shikkhokplus.nirmatabd.com, and
    the domain mail is sent from: no-reply@<this>. Per environment, so
    staging and production each own a separate SES identity and never
    contend for one resource.
  EOT
  type        = string
}

variable "zone_id" {
  description = <<-EOT
    The Route53 zone for domain_name, which receives the DKIM, MAIL FROM
    and DMARC records. Passed in rather than looked up: on a first apply
    the zone is created in the same run, and a lookup would race it.
  EOT
  type        = string
}

variable "aws_region" {
  description = "The SES region: where the identity lives and whose SMTP endpoint the app uses."
  type        = string
}

variable "account_id" {
  description = "The account id, for the ARNs in the sender's policy."
  type        = string
}

variable "sender_boundary_arn" {
  description = <<-EOT
    The permissions boundary the SMTP user must carry,
    shikkhokplus-email-sender-boundary-<env>, created by infra/bootstrap.
    The infrastructure role may create or edit a user only under it.
  EOT
  type        = string
}

variable "alarm_topic_arn" {
  description = "The environment's alert topic (infra/monitoring.tf), which emails ALERT_EMAIL."
  type        = string
}

variable "from_local_part" {
  description = "The local part of the From address. The SMTP user may send from this address only."
  type        = string
  default     = "no-reply"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$", var.from_local_part))
    error_message = "from_local_part must be a plain lower-case local part, e.g. no-reply."
  }
}

variable "from_display_name" {
  description = "The display name in the From header."
  type        = string
  default     = "ShikkhokPlus"
}
