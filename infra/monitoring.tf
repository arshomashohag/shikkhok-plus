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

# **Production refuses to exist with alarms that reach nobody** [C-34].
# An unset address was allowed everywhere and reported only in the
# alert_email_status output, so a production stack could fire every
# alarm below into a topic with no subscriber. Staging may still run
# without one; production may not plan.
resource "terraform_data" "alert_routing_guard" {
  lifecycle {
    precondition {
      condition     = var.environment != "production" || local.alert_email != ""
      error_message = <<-EOT
        production requires alert_email (in CI, the ALERT_EMAIL variable
        of the production environment).

        Without it every alarm fires into an SNS topic with no
        subscriber, and nothing reaches a human.
      EOT
    }
  }
}

locals {
  db_identifier = "${local.name_prefix}-db"

  # Alarms notify on the way back to OK as well, so a page that cleared
  # by itself says so rather than leaving the reader to guess.
  alert_actions = [aws_sns_topic.alerts.arn]
}

# **RDS failure, deletion and storage events** [C-33]. RDS emits no
# "automated backup failed" event: its `backup` category is the routine
# start and finish of each nightly backup, which would mail every day
# and teach the reader to ignore this topic. What it does emit for a
# database in trouble is in these categories -- failure, low storage,
# availability (shutdown, restart, an inaccessible encryption key),
# configuration change (including automated backups being DISABLED),
# deletion, and recovery and restoration.
resource "aws_db_event_subscription" "database" {
  count = var.enable_rds ? 1 : 0

  name      = "${local.name_prefix}-db-events"
  sns_topic = aws_sns_topic.alerts.arn

  source_type = "db-instance"
  source_ids  = [local.db_identifier]
  event_categories = [
    "availability",
    "configuration change",
    "deletion",
    "failure",
    "low storage",
    "recovery",
    "restoration",
  ]

  depends_on = [module.database]
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
  dimensions          = { DBInstanceIdentifier = local.db_identifier }
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 2 * 1024 * 1024 * 1024
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = local.alert_actions
  ok_actions          = local.alert_actions
}

# **The database running out of CPU, credits, memory or connections**
# [C-34]. The slow endpoints the audit measured fail here first, and
# before this nothing signalled it until a teacher did. A burstable
# instance that has spent its CPU credits is throttled to its baseline,
# which looks like the application becoming slow for no reason, so the
# credit balance is alarmed separately from the CPU it pays for.
#
# Each threshold is set for the default instance class; recheck them
# when rds_instance_class changes. Each is a standard alarm, counted in
# the cost model through alarm_names below.
locals {
  rds_alarms = var.enable_rds ? {
    cpu-high = {
      description = "RDS CPU over 80% for 15 minutes."
      metric      = "CPUUtilization"
      statistic   = "Average"
      threshold   = 80
      comparison  = "GreaterThanThreshold"
    }
    cpu-credits-low = {
      description = "RDS CPU credit balance low: the instance is about to be throttled to its baseline."
      metric      = "CPUCreditBalance"
      statistic   = "Minimum"
      threshold   = 20
      comparison  = "LessThanThreshold"
    }
    memory-low = {
      description = "RDS freeable memory under 64 MiB for 15 minutes."
      metric      = "FreeableMemory"
      statistic   = "Minimum"
      threshold   = 64 * 1024 * 1024
      comparison  = "LessThanThreshold"
    }
    connections-high = {
      # RDS derives the default max_connections from instance memory;
      # this sits below the default instance class's limit, so the
      # alarm fires before a new connection is refused.
      description = "RDS connections over 80 for 15 minutes."
      metric      = "DatabaseConnections"
      statistic   = "Maximum"
      threshold   = 80
      comparison  = "GreaterThanThreshold"
    }
  } : {}
}

resource "aws_cloudwatch_metric_alarm" "rds" {
  for_each = local.rds_alarms

  alarm_name          = "${local.name_prefix}-db-${each.key}"
  alarm_description   = each.value.description
  namespace           = "AWS/RDS"
  metric_name         = each.value.metric
  dimensions          = { DBInstanceIdentifier = local.db_identifier }
  statistic           = each.value.statistic
  period              = 300
  evaluation_periods  = 3
  threshold           = each.value.threshold
  comparison_operator = each.value.comparison
  # No data means no database, which the free-storage alarm above
  # already reports as breaching; these stay quiet rather than paging
  # four times for one outage.
  treat_missing_data = "notBreaching"
  alarm_actions      = local.alert_actions
  ok_actions         = local.alert_actions
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
  alarm_actions       = local.alert_actions
  ok_actions          = local.alert_actions
}

locals {
  # Every standard alarm this configuration creates, for the cost model.
  alarm_names = concat(
    module.app.alarm_names,
    flatten([for m in module.staging_app : m.alarm_names]),
    aws_cloudwatch_metric_alarm.rds_free_storage[*].alarm_name,
    aws_cloudwatch_metric_alarm.cloudfront_5xx[*].alarm_name,
    [for alarm in aws_cloudwatch_metric_alarm.rds : alarm.alarm_name],
  )
}
