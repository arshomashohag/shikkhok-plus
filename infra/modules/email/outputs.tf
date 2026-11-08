output "alarm_names" {
  description = "The reputation alarms, for the cost model in infra/main.tf."
  value       = [for alarm in aws_cloudwatch_metric_alarm.reputation : alarm.alarm_name]
}

output "from_address" {
  description = "The one address the SMTP user may send from."
  value       = local.from_address
}

output "configuration_set_name" {
  description = "The configuration set every message from the identity goes through."
  value       = aws_sesv2_configuration_set.email.configuration_set_name
}

output "smtp_host" {
  description = "The SES SMTP endpoint (STARTTLS on 587)."
  value       = local.smtp_host
}

output "smtp_user_name" {
  description = "The IAM user whose SMTP credentials the application holds."
  value       = aws_iam_user.smtp.name
}

output "smtp_credential_parameters" {
  description = "The SSM SecureStrings deploy.yml copies into the runtime env. Names, not values."
  value = {
    username = aws_ssm_parameter.smtp_username.name
    password = aws_ssm_parameter.smtp_password.name
  }
}
