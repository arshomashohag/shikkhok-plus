output "static_ip" {
  description = "The Elastic IP. CloudFront's origin, and the address to allowlist at the SMS gateway."
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  description = "For `aws ssm start-session --target <this>`."
  value       = aws_instance.app.id
}

output "security_group_id" {
  description = <<-EOT
    What Phase 2's RDS references as its ingress source. This is the
    thing Lightsail could not provide: a real security group, so the
    database rule becomes source_security_group_id rather than a CIDR
    guess or a VPC peering range.
  EOT
  value       = aws_security_group.app.id
}

output "origin_secret" {
  description = "The CDN-to-origin shared secret. Sensitive."
  value       = random_password.origin_secret.result
  sensitive   = true
}
