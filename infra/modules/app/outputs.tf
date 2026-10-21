# **No static_ip output.** There is no Elastic IP: the instance
# registers its own DNS at boot, so the address changes on every
# replacement and nothing should depend on a fixed one.
#
# If the SMS gateway ever needs an allowlisted source address, that
# reintroduces a requirement for a stable IP and the answer is a NAT
# gateway or an EIP with a lifecycle hook -- a decision, not an
# oversight to patch quietly.

output "origin_fqdn" {
  description = "The name the instance registers itself as. CloudFront's origin."
  value       = var.origin_fqdn
}

output "instance_id" {
  description = <<-EOT
    For `aws ssm start-session --target <this>`.

    Looked up from the running instance rather than held, because the
    ASG replaces instances and a stored id goes stale. Empty between a
    termination and its replacement.
  EOT
  value       = try(data.aws_instances.app.ids[0], "")
}

output "autoscaling_group_name" {
  description = "For `aws autoscaling start-instance-refresh` and for the deploy to resolve the current host."
  value       = aws_autoscaling_group.app.name
}

output "image_tag_parameter" {
  description = "SSM parameter the deploy writes and a replaced instance reads at boot."
  value       = aws_ssm_parameter.image_tag.name
}

output "runtime_env_parameter" {
  description = "SSM SecureString holding the host's .env. Written by the deploy."
  value       = aws_ssm_parameter.runtime_env.name
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
