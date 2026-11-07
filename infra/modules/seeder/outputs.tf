output "function_name" {
  description = "The function to invoke, or null when disabled."
  value       = var.enabled ? aws_lambda_function.seeder[0].function_name : null
}

output "security_group_id" {
  description = "The function's security group, which the database admits; null when disabled."
  value       = var.enabled ? aws_security_group.seeder[0].id : null
}
