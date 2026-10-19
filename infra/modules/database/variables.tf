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

variable "vpc_id" {
  description = "The VPC the database lives in."
  type        = string
  default     = ""
}

variable "subnet_ids" {
  description = "Two subnets in different AZs. RDS requires two even Single-AZ."
  type        = list(string)
  default     = []
}

variable "app_security_group_id" {
  description = <<-EOT
    The app host's security group, and the ONLY source permitted to
    reach port 5432. An exact reference rather than a CIDR: it follows
    the instance if its address changes and cannot be wider than the
    hosts in that group.
  EOT
  type        = string
  default     = ""
}
