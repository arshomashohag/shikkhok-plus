# Where alarms go, and the alarms that belong to no single host [OPS-11].
#
# One SNS topic per environment, with an email subscription when
# `alert_email` is set. The address is a variable with NO default --
# a committed address would page whoever wrote it forever -- and AWS
# sends a confirmation mail that must be clicked before anything is
# delivered. Until then every alarm below fires into nothing, which is
# why `alert_email_status` is an output.
#
# The host's own alarms (CRITICAL log lines, no host in service, status
# checks, certificate age) live in modules/app/monitoring.tf. The cost
# ceiling's alert is an AWS Budget in infra/bootstrap, because a budget
# is account-wide and is created once.

resource "aws_sns_topic" "alerts" {
  name = "${local.name_prefix}-alerts"
}

locals {
  alert_email = var.alert_email == null ? "" : trimspace(var.alert_email)
}

resource "aws_sns_topic_subscription" "email" {
  count = local.alert_email == "" ? 0 : 1

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = local.alert_email
}

# **The database filling its disk** stops every write, including
# attendance during a live class. 2 GiB of 20 is the point at which
# there is still a day to act.
resource "aws_cloudwatch_metric_alarm" "rds_free_storage" {
  count = var.enable_rds ? 1 : 0

  alarm_name          = "${local.name_prefix}-db-free-storage-low"
  alarm_description   = "RDS free storage under 2 GiB. Writes stop when it reaches zero."
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  dimensions          = { DBInstanceIdentifier = "${local.name_prefix}-db" }
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 2 * 1024 * 1024 * 1024
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# **What a teacher actually sees.** CloudFront's 5xx rate covers every
# failure between the edge and the application -- the origin
# certificate, nginx, the origin secret, DNS, the API -- in one number.
# More than 5% of requests for fifteen minutes; no traffic is not an
# outage.
#
# CloudFront publishes its metrics in us-east-1 only, and an alarm can
# notify only a topic in its own region. The stack runs in us-east-1
# today; in any other region this alarm is not created, and the
# no-host alarm is what remains -- stated here so the absence is not
# mistaken for coverage.
resource "aws_cloudwatch_metric_alarm" "cloudfront_5xx" {
  count    = var.region == "us-east-1" ? 1 : 0
  provider = aws.us_east_1

  alarm_name          = "${local.name_prefix}-cloudfront-5xx-rate"
  alarm_description   = "Over 5% of API requests returned 5xx at the edge for 15 minutes."
  namespace           = "AWS/CloudFront"
  metric_name         = "5xxErrorRate"
  dimensions          = { DistributionId = module.cdn.distribution_id, Region = "Global" }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

locals {
  # Every standard alarm this configuration creates, for the cost model.
  alarm_names = concat(
    module.app.alarm_names,
    flatten([for m in module.staging_app : m.alarm_names]),
    aws_cloudwatch_metric_alarm.rds_free_storage[*].alarm_name,
    aws_cloudwatch_metric_alarm.cloudfront_5xx[*].alarm_name,
  )
}
