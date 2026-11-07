output "account_id" {
  description = "The account this was applied to. Check it is the one you meant."
  value       = data.aws_caller_identity.current.account_id
}

output "state_bucket" {
  description = "Pass to ../ as -backend-config=\"bucket=<this>\"."
  value       = aws_s3_bucket.state.id
}

output "infra_role_arns" {
  description = <<-EOT
    One infrastructure role per environment [C-09]. Set each as the
    AWS_ROLE_ARN variable of THAT `-infra` environment only:

      Settings -> Environments -> staging-infra    -> AWS_ROLE_ARN = staging value
      Settings -> Environments -> production-infra -> AWS_ROLE_ARN = production value

    and delete any repository-level AWS_ROLE_ARN. The staging ARN is
    unchanged from the single role that preceded these.
  EOT
  value       = { for env, role in aws_iam_role.ci : env => role.arn }
}

output "plan_role_arns" {
  description = <<-EOT
    One read-only plan role per environment [C-11]. Set each as the
    AWS_PLAN_ROLE_ARN variable of the deploy environment of the same
    name (`staging`, `production`), where deploy.yml's first job runs.
  EOT
  value       = { for env, role in aws_iam_role.plan : env => role.arn }
}

output "next_steps" {
  description = "What to do with the values above."
  value       = <<-EOT

    1. GitHub -> Settings -> Secrets and variables -> Actions -> Variables:
         TF_STATE_BUCKET  = ${aws_s3_bucket.state.id}
       and per environment, AWS_ROLE_ARN (the `-infra` environments)
       and AWS_PLAN_ROLE_ARN (`staging`, `production`) from the
       infra_role_arns and plan_role_arns outputs.

    2. Uncomment the backend "s3" block in ../versions.tf and set the
       bucket to ${aws_s3_bucket.state.id}.

    3. From infra/:  terraform init -migrate-state

    After that, every apply runs in GitHub Actions and this directory
    is never needed again.
  EOT
}



output "deploy_role_arns" {
  description = <<-EOT
    One deploy role per GitHub environment. Set each as the
    AWS_DEPLOY_ROLE_ARN variable of THAT environment only:

      Settings -> Environments -> staging    -> AWS_DEPLOY_ROLE_ARN = staging value
      Settings -> Environments -> production -> AWS_DEPLOY_ROLE_ARN = production value

    Each trusts only its own environment's OIDC subject and can touch
    only `shikkhokplus-<env>-*` resources, so putting the production
    ARN into the staging environment would simply fail at role
    assumption. The staging ARN is unchanged from the single role that
    preceded these.

    Separate from AWS_ROLE_ARN deliberately: that role can destroy the
    infrastructure; these push an image, snapshot their own database
    and roll their own host.
  EOT
  value       = { for env, role in aws_iam_role.deploy : env => role.arn }
}
