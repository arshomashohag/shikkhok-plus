# Logs and alarms for one app host [OPS-11].
#
# **Before this, nothing reached a human.** The SMS cost ceiling's
# breach was a CRITICAL line on a container's stdout, in a json-file log
# with no rotation, on a root volume every deploy deletes. A host that
# stopped serving, a certificate about to expire, a scheduler that
# stopped running: each was visible only to someone already looking.
#
# Now the containers -- the API, the migrate runs and every scheduled
# job, which are `docker compose run` containers -- ship to one
# CloudWatch log group through Docker's awslogs driver (dockerd on the
# host holds the credentials; no container can reach IMDS), and the
# boot log is shipped there too. Retention is bounded so the log bill
# is too.
#
# Cost at this volume, counted in main.tf's cost_breakdown from the
# `alarm_names` output below: USD 0.10 per standard alarm, and log
# ingestion at USD 0.50/GB.

resource "aws_cloudwatch_log_group" "app" {
  name              = "/shikkhokplus/${var.name_prefix}/app"
  retention_in_days = var.log_retention_days
}

locals {
  metric_namespace = "Shikkhokplus/${var.name_prefix}"
  alarm_actions    = var.alarm_topic_arn == null ? [] : [var.alarm_topic_arn]
}

# **CRITICAL means a human must look.** The application logs at
# CRITICAL for exactly the events that need one -- the SMS daily
# ceiling breached, a job that cannot run -- with the level first on
# the line (`CRITICAL:<logger>:<message>`, app/logging_setup.py).
resource "aws_cloudwatch_log_metric_filter" "critical" {
  name           = "${var.name_prefix}-critical"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "\"CRITICAL:\""

  metric_transformation {
    name          = "CriticalLogLines"
    namespace     = local.metric_namespace
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "critical" {
  alarm_name          = "${var.name_prefix}-critical-log-lines"
  alarm_description   = "The application logged at CRITICAL. Read the log group ${aws_cloudwatch_log_group.app.name}."
  namespace           = local.metric_namespace
  metric_name         = "CriticalLogLines"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
}

# **No host in service.** The group is desired-one; zero in service for
# ten minutes means every replacement is being abandoned at the
# readiness hook, or none can launch. The boot log for each attempt is
# in the log group under `boot-<instance-id>`.
resource "aws_cloudwatch_metric_alarm" "no_host" {
  alarm_name          = "${var.name_prefix}-no-host-in-service"
  alarm_description   = "No app host in service. Check the ASG's activity and the boot-* log streams."
  namespace           = "AWS/AutoScaling"
  metric_name         = "GroupInServiceInstances"
  dimensions          = { AutoScalingGroupName = aws_autoscaling_group.app.name }
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  # Group metrics stop when the group has nothing to report, which is
  # itself the condition this alarm is for.
  treat_missing_data = "breaching"
  alarm_actions      = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "status_check" {
  alarm_name          = "${var.name_prefix}-status-check-failed"
  alarm_description   = "An app host is failing its EC2 status checks."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  dimensions          = { AutoScalingGroupName = aws_autoscaling_group.app.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  # The no-host alarm above covers absence; this one covers a host
  # that is present and impaired.
  treat_missing_data = "notBreaching"
  alarm_actions      = local.alarm_actions
}

# **The origin certificate's remaining life**, published daily by the
# host (and once at boot). Under 14 days means renewal has been failing
# for two weeks; NO data means the host is not publishing -- no
# certificate at all, or no host -- and is treated as breaching for the
# same reason: either way CloudFront is about to 502.
resource "aws_cloudwatch_metric_alarm" "certificate" {
  alarm_name          = "${var.name_prefix}-origin-certificate-expiring"
  alarm_description   = "The origin's Let's Encrypt certificate has under 14 days left, or its age is not being reported."
  namespace           = local.metric_namespace
  metric_name         = "OriginCertificateDaysRemaining"
  statistic           = "Minimum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 14
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_actions
}

# Every alarm this module creates. main.tf prices the alarms from the
# length of this list, so an alarm added above and not here is an alarm
# the budget does not count.
output "alarm_names" {
  description = "The alarms this host's module creates."
  value = [
    aws_cloudwatch_metric_alarm.critical.alarm_name,
    aws_cloudwatch_metric_alarm.no_host.alarm_name,
    aws_cloudwatch_metric_alarm.status_check.alarm_name,
    aws_cloudwatch_metric_alarm.certificate.alarm_name,
  ]
}

output "log_group" {
  description = "Where the containers and the boot log ship."
  value       = aws_cloudwatch_log_group.app.name
}
