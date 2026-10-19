variable "name_prefix" {
  description = "Prefix for resource names and comments."
  type        = string
}

variable "domain_name" {
  description = "The apex domain whose Route53 zone already exists."
  type        = string
}

variable "api_subdomain" {
  description = "Host part of the API record."
  type        = string
}

variable "origin_ip" {
  description = "The Lightsail static IP CloudFront points at."
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
