output "bucket" {
  description = "Where deploy.yml uploads the built site, at the bucket root."
  value       = aws_s3_bucket.site.id
}

output "distribution_id" {
  description = "The distribution deploy.yml invalidates after an upload."
  value       = aws_cloudfront_distribution.site.id
}

output "distribution_domain" {
  description = "The *.cloudfront.net hostname. Usable before DNS propagates."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "url" {
  description = "The site's canonical origin, with no trailing slash: the SITE_URL it is built with."
  value       = "https://${local.site_fqdn}"
}
