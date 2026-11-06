output "endpoint" {
  description = "The RDS endpoint, or null when disabled."
  value       = var.enabled ? aws_db_instance.main[0].endpoint : null
}

output "password" {
  description = "The generated database password. Sensitive."
  value       = var.enabled ? random_password.db[0].result : null
  sensitive   = true
}

output "security_group_id" {
  description = "The database's security group, or null when disabled."
  value       = var.enabled ? aws_security_group.database[0].id : null
}
