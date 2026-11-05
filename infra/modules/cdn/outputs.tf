output "distribution_domain" {
  description = "The *.cloudfront.net hostname. Usable before DNS propagates."
  value       = aws_cloudfront_distribution.api.domain_name
}

output "api_url" {
  description = "The URL the Android client is built against."
  value       = "https://${var.api_subdomain}.${var.domain_name}"
}

output "distribution_id" {
  description = "For cache invalidation, once anything is cached."
  value       = aws_cloudfront_distribution.api.id
}

output "web_bucket" {
  description = "Where the deploy uploads the built web client, under ui/."
  value       = aws_s3_bucket.web.id
}

output "web_url" {
  description = "The web client's address: its own hostname when it has one, else the API host's /ui/."
  value       = "https://${local.ui_fqdn == "" ? local.api_fqdn : local.ui_fqdn}/ui/"
}
