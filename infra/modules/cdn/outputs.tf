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
