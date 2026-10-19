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
