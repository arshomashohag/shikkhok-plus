variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "vpc_cidr" {
  description = "The VPC CIDR. /16 leaves room the project will not need."
  type        = string
  default     = "10.20.0.0/16"
}
