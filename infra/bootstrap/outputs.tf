output "account_id" {
  description = "The account this was applied to. Check it is the one you meant."
  value       = data.aws_caller_identity.current.account_id
}

output "state_bucket" {
  description = "Pass to ../ as -backend-config=\"bucket=<this>\"."
  value       = aws_s3_bucket.state.id
}

output "ci_role_arn" {
  description = "Set as the AWS_ROLE_ARN repository variable in GitHub."
  value       = aws_iam_role.ci.arn
}

output "next_steps" {
  description = "What to do with the two values above."
  value       = <<-EOT

    1. GitHub -> Settings -> Secrets and variables -> Actions -> Variables:
         AWS_ROLE_ARN     = ${aws_iam_role.ci.arn}
         TF_STATE_BUCKET  = ${aws_s3_bucket.state.id}

    2. Uncomment the backend "s3" block in ../versions.tf and set the
       bucket to ${aws_s3_bucket.state.id}.

    3. From infra/:  terraform init -migrate-state

    After that, every apply runs in GitHub Actions and this directory
    is never needed again.
  EOT
}

output "project_domain" {
  description = <<-EOT
    Set this as the TF_DOMAIN_NAME GitHub variable. The API is then
    served at `api.<this>`.
  EOT
  value       = var.create_dns_zone ? var.project_domain : null
}

output "project_zone_nameservers" {
  description = <<-EOT
    The new zone's nameservers. The NS delegation in the parent zone
    is created here too, so there is nothing to copy by hand -- this
    is for verifying the delegation resolves:

      dig +short NS <project_domain> @8.8.8.8
  EOT
  value = (
    var.create_dns_zone
    ? aws_route53_zone.project[0].name_servers
    : null
  )
}
