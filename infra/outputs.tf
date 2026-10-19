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
  description = <<-EOT
    Published list prices, us-east-1, USD/month. Queried from the AWS
    Price List API on 2026-10-19, not estimated.

    Shares one model with the budget precondition in main.tf, so the
    guard and the report cannot disagree -- they did before, by USD
    4.67 on the instance alone.
  EOT
  value = merge(local.cost_breakdown, {
    total = local.monthly_cost
  })
}

output "image_repository" {
  description = <<-EOT
    Where the deploy workflow pushes and the host pulls. The tag is a
    commit SHA; `latest` is never deployed.
  EOT
  value       = module.registry.repository_url
}
