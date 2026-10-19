output "state_bucket" {
  description = "Put this in the backend block in ../versions.tf."
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
