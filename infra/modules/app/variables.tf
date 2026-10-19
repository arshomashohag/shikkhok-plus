variable "name_prefix" {
  description = "Prefix for resource names, e.g. shikkhokplus-staging."
  type        = string
}

variable "availability_zone" {
  description = "The AZ to place the instance in."
  type        = string
}

variable "bundle_id" {
  description = "Lightsail bundle. small_2_0 is 2 GB at USD 12/month."
  type        = string
}

variable "ssh_key_pair_name" {
  description = "An existing Lightsail key pair name."
  type        = string
}

variable "operator_ip_cidr" {
  description = "The operator's IP as a /32, for SSH."
  type        = string
}
