# RDS PostgreSQL. **Phase 2, and disabled by default.**
#
# This module exists so Phase 2 is a variable flip rather than an
# architecture change. It provisions nothing until `enable_rds = true`.
#
# **Ingress is a SECURITY GROUP reference, not a CIDR**, and that is
# what moving the app host from Lightsail to EC2 bought.
#
# The earlier design could not express "only the app host" at all.
# Lightsail instances live outside your VPC and have no security group
# for a database to name, so the options were a public endpoint
# allowing one /32 -- routing children-identifying traffic out of AWS
# and back over the internet -- or VPC peering, which grants the whole
# peered range rather than one instance.
#
# With the app in our own VPC the rule is exact:
# `source_security_group_id = <the app's group>`. No CIDR to maintain,
# no range wider than intended, and it follows the instance if its IP
# changes.
#
# `publicly_accessible = false`: the endpoint resolves only inside the
# VPC. The subnets are public (they route to an internet gateway) but
# the database has no public address and no ingress from anywhere but
# the app's security group.

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

resource "aws_db_subnet_group" "main" {
  count = var.enabled ? 1 : 0

  name = "${var.name_prefix}-db"
  # Two AZs, which RDS requires even for a Single-AZ instance. The
  # network module creates both for this reason.
  subnet_ids = var.subnet_ids

  tags = { Role = "database" }
}

resource "aws_security_group" "database" {
  count = var.enabled ? 1 : 0

  name        = "${var.name_prefix}-db"
  description = "PostgreSQL, reachable only from the app security group"
  vpc_id      = var.vpc_id

  ingress {
    description = "PostgreSQL from the app security group ONLY"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    # EXACT. Not a CIDR, not a range -- the app's security group. This
    # follows the instance if its address changes and cannot be wider
    # than the hosts in that group.
    security_groups = [var.app_security_group_id]
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
