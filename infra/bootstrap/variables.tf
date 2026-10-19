variable "region" {
  description = "AWS region. Mumbai is nearest to Bangladesh [TC-17]."
  type        = string
  default     = "ap-south-1"
}

variable "state_bucket_name" {
  description = <<-EOT
    The Terraform state bucket, or null to derive one.

    S3 names are globally unique across EVERY AWS account, so the
    derived default appends your account id:
    `shikkhokplus-tfstate-<account>`. Without that, a plain
    `shikkhokplus-tfstate` is very likely taken by a stranger and the
    failure reads like a bug here rather than a namespace collision.
  EOT
  type        = string
  default     = null
}

variable "expected_account_id" {
  description = <<-EOT
    The AWS account this is meant to run against. Null skips the check.

    Set it once you know the number: running the bootstrap against the
    wrong account creates an OIDC provider and a role somewhere
    unintended, and the first symptom is a CI run failing to assume a
    role that exists -- in a different account.

      aws sts get-caller-identity --query Account --output text
    EOT
  type        = string
  default     = null

  validation {
    condition     = var.expected_account_id == null || can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "An AWS account id is exactly 12 digits."
  }
}

variable "github_repository" {
  description = <<-EOT
    owner/repo exactly as GitHub spells it. **This string is the whole
    security boundary**: the OIDC provider trusts GitHub, not your
    repository, so a wrong or over-broad value here lets another repo
    assume the role.
  EOT
  type        = string
  default     = "arshomashohag/shikkhok-plus"

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repository))
    error_message = "Must be exactly owner/repo, e.g. arshomashohag/shikkhok-plus."
  }

  validation {
    condition     = !can(regex("\\*", var.github_repository))
    error_message = "Refusing a wildcard: any repository could then assume this role."
  }
}

variable "recover_existing" {
  description = <<-EOT
    Rebuild state for resources that already exist, after a lost
    terraform.tfstate.

    Normally false. Set it true ONLY to recover, read the plan (it
    must say 3 to import and nothing to add or destroy), apply, then
    set it back.
  EOT
  type        = bool
  default     = false
}

variable "create_github_oidc_provider" {
  description = <<-EOT
    Create the GitHub OIDC provider, or reference an existing one.

    **An AWS account can hold only one provider per URL.** Most
    accounts that have ever run a GitHub deploy already have it, and
    other roles will be trusting it -- so the default REFERENCES it.
    Owning a shared resource means a `terraform destroy` here breaks
    every project that depends on it.

    Set true only for an account that has none:
      aws iam list-open-id-connect-providers
  EOT
  type        = bool
  default     = false
}

variable "trust_staging_environment" {
  description = <<-EOT
    Let the `staging` environment assume the CI role.

    Off, and the default is the point. `deploy-staging.yml` does not
    assume this role yet; when its SSM delivery step lands it will,
    and the honest fix is a separate deploy role scoped to SSM and
    ECR rather than widening this one -- which carries ec2:*, rds:*,
    route53:* and IAM writes.

    Turning this on is the expedient path. It works, and it hands a
    container push the same permissions as a `terraform destroy`.
  EOT
  type        = bool
  default     = false
}
