output "api_url" {
  description = "The URL to build the Android client against."
  value       = module.cdn.api_url
}

output "cloudfront_domain" {
  description = "Usable immediately, before the DNS record propagates."
  value       = module.cdn.distribution_domain
}

output "app_static_ip" {
  description = <<-EOT
    The Elastic IP. CloudFront's origin, and the address to allowlist
    at the SMS gateway. **Not an SSH target**: there is no SSH.
  EOT
  value       = module.app.static_ip
}

output "app_instance_id" {
  description = <<-EOT
    How you get a shell:

      aws ssm start-session --target <this>

    No key, no port, no IP to allowlist. CloudTrail records who opened
    the session, which is what team.md's "named, logged and bounded"
    rule asks for.
  EOT
  value       = module.app.instance_id
}

output "staging_static_ip" {
  description = "The rehearsal host's Elastic IP, when enabled."
  value       = var.enable_staging_instance ? module.staging_app[0].static_ip : null
}

output "staging_instance_id" {
  description = "The rehearsal host, for `aws ssm start-session --target`."
  value       = var.enable_staging_instance ? module.staging_app[0].instance_id : null
}

output "origin_secret_command" {
  description = <<-EOT
    How to read the origin secret when you need it. NOT the value:
    printing a bypass credential into a terminal scrollback and a CI
    log is how it leaks.
  EOT
  value       = "terraform output -raw origin_secret"
}

output "origin_secret" {
  description = "The CDN-to-origin shared secret."
  value       = module.app.origin_secret
  sensitive   = true
}

output "monthly_cost_estimate" {
  description = "Published list prices, ap-south-1, USD/month."
  value = {
    app_instance     = 12.00
    staging_instance = var.enable_staging_instance ? 12.00 : 0.00
    route53_zone     = 0.50
    cloudfront       = 0.00
    acm              = 0.00
    rds              = var.enable_rds ? 17.36 : 0.00
    total            = 12.50 + (var.enable_staging_instance ? 12.00 : 0.00) + (var.enable_rds ? 17.36 : 0.00)
  }
}
