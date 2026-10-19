output "static_ip" {
  description = "The instance's static public IP. CloudFront's origin."
  value       = aws_lightsail_static_ip.app.ip_address
}

output "instance_name" {
  description = "The Lightsail instance name, for CLI access."
  value       = aws_lightsail_instance.app.name
}

output "origin_secret" {
  description = <<-EOT
    The shared secret CloudFront sends and the origin requires.
    Sensitive: printing it would put a bypass credential in a terminal
    scrollback and in CI logs.
  EOT
  value       = random_password.origin_secret.result
  sensitive   = true
}
