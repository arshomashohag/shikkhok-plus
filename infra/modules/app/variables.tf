variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "aws_region" {
  description = "Region, for the SSM endpoint the boot script calls."
  type        = string
}

variable "dns_zone_id" {
  description = <<-EOT
    The zone this instance writes its own A record into at boot.
    Scoped: the instance role can change records in this zone and no
    other.
  EOT
  type        = string
}

variable "origin_fqdn" {
  description = <<-EOT
    The name this instance registers itself as, e.g.
    origin.shikkhokplus.nirmatabd.com. CloudFront's origin.

    **Terraform does not own this record.** The instance writes it, so
    a replacement repoints it without an apply. A Terraform-managed
    record would be stale the moment the ASG replaced the box.
  EOT
  type        = string
}

variable "vpc_id" {
  description = "The VPC to place the instance in."
  type        = string
}

variable "subnet_ids" {
  description = <<-EOT
    Subnets the ASG may launch into. Plural, and across AZs: a group
    of one that can only launch in a single AZ cannot replace its
    instance when that AZ is the thing that failed.
  EOT
  type        = list(string)
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

variable "image_repository" {
  description = <<-EOT
    The ECR repository this host pulls its application image from,
    as `{ arn, url }`. Supplied by the root module from
    `module.registry`, since sibling modules cannot reference each
    other directly.

    Null means this host runs no application -- it still boots, still
    has SSM, and simply has no pull permission and no registry in its
    docker config.

    **One object rather than three separate inputs**, because the arn
    and the url are not independent: a host given one without the
    other either has permission it cannot use or a registry it cannot
    read. The object makes that combination unrepresentable.
  EOT
  type = object({
    arn = string
    url = string
  })
  default = null
}
