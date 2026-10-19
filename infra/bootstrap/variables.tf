variable "region" {
  description = "AWS region. Mumbai is nearest to Bangladesh [TC-17]."
  type        = string
  default     = "ap-south-1"
}

variable "state_bucket_name" {
  description = <<-EOT
    The Terraform state bucket. Globally unique across all of AWS, so
    a plain "shikkhokplus-tfstate" may already be taken by somebody
    else entirely -- append your account id if apply reports a name
    conflict.
  EOT
  type        = string
  default     = "shikkhokplus-tfstate"
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
