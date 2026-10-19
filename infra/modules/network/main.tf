# The VPC.
#
# **This exists because of SSM, and it pays for itself twice.** Moving
# the app host into our own VPC is what lets Session Manager work --
# but it also removes the reason RDS could never be properly scoped.
# A Lightsail instance has no security group for a database to
# reference; an EC2 instance does. Phase 2 stops needing a CIDR guess
# or VPC peering and gets `source_security_group_id` instead.
#
# **Public subnets with public IPs, and no NAT gateway.** A NAT is USD
# 32/month -- more than both compute instances combined -- and it buys
# nothing here: the host needs outbound internet for the SMS gateway
# and package updates either way, and SSM reaches it over that same
# outbound channel. Private subnets plus a NAT would be the textbook
# answer and the wrong one at this budget.
#
# Inbound is closed by the security group regardless of the subnet
# being public. "Public subnet" means a route to an internet gateway,
# not an open door.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block         = var.vpc_cidr
  enable_dns_support = true
  # Required for SSM: the agent resolves the SSM endpoints by name.
  enable_dns_hostnames = true

  tags = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.name_prefix}-igw" }
}

# TWO subnets in different AZs. One instance runs in the first; the
# second exists because an RDS subnet group REQUIRES two AZs even for
# a Single-AZ instance. Creating it now costs nothing and means Phase 2
# is a flag rather than a network change.
resource "aws_subnet" "public" {
  count = 2

  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "${var.name_prefix}-public-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${var.name_prefix}-public" }
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
