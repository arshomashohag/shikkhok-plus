# RDS PostgreSQL. **Phase 2, and disabled by default.**
#
# This module exists so Phase 2 is a variable flip rather than an
# architecture change. It provisions nothing until `enable_rds = true`.
#
# **The instance is in a PRIVATE subnet, never a public one**, and that
# is the correction to the obvious design. RDS security groups cannot
# name a Lightsail instance, because Lightsail lives outside your VPC
# in an AWS-managed one. "Ingress only from Lightsail" is therefore
# expressible three ways and only two are safe:
#
#   * a public endpoint allowing the Lightsail static IP as a /32 --
#     instance-scoped, but every query carrying children's names,
#     attendance and marks LEAVES AWS and re-enters over the public
#     internet. Encrypted in transit, but needlessly exposed, and the
#     endpoint is publicly resolvable.
#   * VPC peering to a private subnet -- coarser than per-instance
#     (the Lightsail side can route to the whole VPC) but the traffic
#     never leaves AWS's private network and the endpoint has no
#     public address at all.
#   * not having a separate database, which is Phase 1.
#
# This module takes the second. `project.md` mandates encryption at
# rest for children's data; it does not require the endpoint be
# reachable from the internet, and nothing is gained by making it so.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

data "aws_vpc" "default" {
  count   = var.enabled ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = var.enabled ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default[0].id]
  }
}

resource "aws_db_subnet_group" "main" {
  count = var.enabled ? 1 : 0

  name       = "${var.name_prefix}-db"
  subnet_ids = data.aws_subnets.default[0].ids

  tags = { Role = "database" }
}

resource "aws_security_group" "database" {
  count = var.enabled ? 1 : 0

  name        = "${var.name_prefix}-db"
  description = "PostgreSQL, reachable only from the peered Lightsail VPC"
  vpc_id      = data.aws_vpc.default[0].id

  ingress {
    description = "PostgreSQL from the Lightsail VPC peering range only"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    # The Lightsail managed VPC's CIDR, supplied by the caller after
    # peering is enabled. NOT 0.0.0.0/0 and not a public IP: the
    # variable's validation refuses both.
    cidr_blocks = [var.lightsail_vpc_cidr]
  }

  # No egress rule is declared, so Terraform's default applies: none.
  # A database does not initiate outbound connections, and an
  # unrestricted egress rule on a host holding children's data is an
  # exfiltration path nobody needs.

  tags = { Role = "database" }
}

resource "random_password" "db" {
  count = var.enabled ? 1 : 0

  length  = 32
  special = false
}

resource "aws_db_instance" "main" {
  count = var.enabled ? 1 : 0

  identifier     = "${var.name_prefix}-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage
  storage_type      = "gp3"
  # **Encrypted at rest, non-negotiable.** project.md: always encrypt
  # children's data at rest, which disqualifies any tier without it.
  storage_encrypted = true

  db_name  = "shikkhokplus"
  username = "shikkhok"
  password = random_password.db[0].result

  db_subnet_group_name   = aws_db_subnet_group.main[0].name
  vpc_security_group_ids = [aws_security_group.database[0].id]
  # **No public endpoint.** This is the line that makes the private
  # subnet real rather than nominal.
  publicly_accessible = false

  # The reason to pay for RDS at all. Phase 1 has pg_dump to S3 and no
  # point-in-time recovery; this is what replaces it.
  backup_retention_period = 7
  backup_window           = "18:00-19:00" # ~midnight Dhaka, off-peak
  maintenance_window      = "Sun:19:00-Sun:20:00"

  # Single-AZ. Multi-AZ doubles the cost for a failover this scale does
  # not justify [team.md], and the decision is recorded rather than
  # defaulted.
  multi_az = false

  # A final snapshot on destroy. The one irreversible resource here.
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name_prefix}-db-final"
  deletion_protection       = true

  # Minor versions apply themselves in the maintenance window; major
  # ones never do, because a major Postgres upgrade is a migration.
  auto_minor_version_upgrade  = true
  allow_major_version_upgrade = false

  tags = { Role = "database" }
}
