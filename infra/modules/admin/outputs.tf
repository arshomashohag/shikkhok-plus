output "bucket" {
  description = "Where deploy.yml uploads the built admin UI, at the bucket root."
  value       = aws_s3_bucket.admin.id
}

output "distribution_id" {
  description = "The distribution deploy.yml invalidates after an upload."
  value       = aws_cloudfront_distribution.admin.id
}

output "distribution_domain" {
  description = "The *.cloudfront.net hostname. Usable before DNS propagates."
  value       = aws_cloudfront_distribution.admin.domain_name
}

output "url" {
  description = "The admin surface's origin, with no trailing slash."
  value       = "https://${local.admin_fqdn}"
}

output "edge_secret_parameter" {
  description = "The SSM SecureString holding X-Admin-Edge. deploy.yml copies it into the runtime env."
  value       = aws_ssm_parameter.edge_secret.name
}
