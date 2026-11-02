# The USD 50 ceiling, watched by AWS rather than by a comment [OPS-11].
#
# The main module refuses to PLAN a configuration whose list-price
# estimate crosses the ceiling. That catches a configuration change; it
# cannot catch what the estimate does not model -- data transfer, a
# forgotten snapshot, logs growing faster than assumed, an instance left
# running after a failed refresh. This budget reads the actual bill.
#
# **Here, in bootstrap, because a budget is account-wide** and created
# once, not per environment -- and so the CI role needs no Budgets
# permission at all.
#
# **Filtered to this project by the CostCenter tag** the main module's
# provider puts on every resource, because the account also runs other
# projects. AWS only filters on a tag once it is ACTIVATED as a cost
# allocation tag (Billing -> Cost allocation tags -> `CostCenter` ->
# Activate); until then this budget reads zero. That is a human step,
# and `budget_status` says so.

resource "aws_budgets_budget" "monthly" {
  count = local.budget_email == "" ? 0 : 1

  name         = "shikkhokplus-monthly"
  budget_type  = "COST"
  limit_amount = format("%.2f", var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:CostCenter$shikkhokplus-backend"]
  }

  # 80% of actual spend: there is still most of a month to act.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [local.budget_email]
  }

  # Forecast over the ceiling: AWS projects the month will end above it.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [local.budget_email]
  }
}

locals {
  budget_email = var.alert_email == null ? "" : trimspace(var.alert_email)
}

output "budget_status" {
  description = "Whether the cost ceiling is being watched, and what still needs a human."
  value = (
    local.budget_email == ""
    ? "NO BUDGET: set alert_email to create the USD ${var.monthly_budget_usd} budget."
    : "Budget shikkhokplus-monthly emails ${local.budget_email}. It reads zero until the CostCenter cost allocation tag is activated in Billing."
  )
}
