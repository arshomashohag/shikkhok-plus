output "endpoint" {
  description = "The RDS endpoint, or null when disabled."
  value       = var.enabled ? aws_db_instance.main[0].endpoint : null
}

output "password" {
  description = "The generated database password. Sensitive."
  value       = var.enabled ? random_password.db[0].result : null
  sensitive   = true
}
