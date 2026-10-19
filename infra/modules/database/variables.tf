variable "enabled" {
  description = "Provision RDS. False in Phase 1: the database runs on the app host."
  type        = bool
  default     = false
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Storage in GB."
  type        = number
  default     = 20
}

variable "lightsail_vpc_cidr" {
  description = <<-EOT
    The Lightsail managed VPC's CIDR, after peering is enabled. Find it
    with `aws lightsail get-active-names` and the VPC peering page.
    Refusing 0.0.0.0/0 below is the point of this variable existing
    rather than being inlined.
  EOT
  type        = string
  default     = "172.26.0.0/16"

  validation {
    condition     = var.lightsail_vpc_cidr != "0.0.0.0/0"
    error_message = "Refusing 0.0.0.0/0 for a database holding children's data."
  }
}
