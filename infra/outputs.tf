output "api_url" {
  description = "The URL to build the Android client against."
  value       = module.cdn.api_url
}

output "cloudfront_domain" {
  description = "Usable immediately, before the DNS record propagates."
  value       = module.cdn.distribution_domain
}

output "app_static_ip" {
  description = "SSH here to deploy. Also the address to allowlist at the SMS gateway."
  value       = module.app.static_ip
}

output "staging_static_ip" {
  description = "The rehearsal host, when enabled."
  value       = var.enable_staging_instance ? module.staging_app[0].static_ip : null
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
