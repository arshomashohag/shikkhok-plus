variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "vpc_id" {
  description = "The VPC to place the instance in."
  type        = string
}

variable "subnet_id" {
  description = "The public subnet for the instance."
  type        = string
}

variable "instance_type" {
  description = <<-EOT
    t4g.small is 2 GB on Graviton, ~USD 13.43/month on demand. The 2 GB
    figure is LOAD-BEARING rather than a default: it is the size every
    performance decision in this project assumed [team.md], and it is
    why lens resolution memoizes per request instead of caching across
    them. Changing it is a performance-model change.

    arm64: the backend image must be built for it, or `docker run`
    fails with an exec format error that does not mention architecture.
  EOT
  type        = string
  default     = "t4g.small"
}

variable "root_volume_gb" {
  description = "Root volume size. Holds the containerised database in Phase 1."
  type        = number
  default     = 30
}

variable "ecr_repository_arn" {
  description = <<-EOT
    The image repository this host may pull from. Null grants no ECR
    access at all, which is correct for a host that does not run the
    application.
  EOT
  type        = string
  default     = null
}

variable "ecr_repository_url" {
  description = <<-EOT
    The repository URL, passed to the host so its compose file can
    reference the image without the deploy step having to compose the
    registry hostname itself.
  EOT
  type        = string
  default     = null
}
