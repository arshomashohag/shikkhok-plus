variable "enabled" {
  description = "Create the seeder. Off by default; the root refuses it in production."
  type        = bool
  default     = false
}

variable "name_prefix" {
  description = "Prefix for resource names, e.g. shikkhokplus-staging."
  type        = string
}

variable "environment" {
  description = "staging or production. Becomes SHIKKHOKPLUS_ENVIRONMENT, which the seeder itself checks."
  type        = string
}

variable "aws_region" {
  description = "Region the function runs in."
  type        = string
}

variable "account_id" {
  description = "This account's id, for exact ARNs."
  type        = string
}

variable "permissions_boundary_arn" {
  description = "The workload boundary bootstrap created; every role here carries it."
  type        = string
}

variable "image_repository" {
  description = "The backend repository the function's image comes from: the API's own."
  type = object({
    arn  = string
    name = string
    url  = string
  })
}

variable "image_tag" {
  description = "The tag deployed when the function is created. Deploys update it afterwards."
  type        = string
}

variable "vpc_id" {
  description = "The VPC the database lives in."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets for the function's network interfaces."
  type        = list(string)
}

variable "database_security_group_id" {
  description = "The database's security group: the ONLY destination the function may reach."
  type        = string
}

variable "database_url" {
  description = "SHIKKHOKPLUS_DATABASE_URL for the restricted shikkhok_app role."
  type        = string
  sensitive   = true
}

variable "log_retention_days" {
  description = "How long the function's logs are kept."
  type        = number
  default     = 14
}
