# **Secrets the host needs at boot, held in SSM rather than in user_data.**
#
# The database master password and the CDN origin secret used to be
# interpolated into the launch template's user_data [OPS-4]. user_data
# is not a secret store: anyone with ec2:DescribeLaunchTemplateVersions
# -- the CI role, any read-only auditor role -- reads it in plaintext,
# every version is kept, and any process that can reach IMDS on the
# host can fetch it. Rotating the password meant replacing the instance.
#
# Now the launch template names only the PARAMETER PATHS. The host reads
# the values at boot with its instance role, which may read exactly
# these parameters and decrypt only through SSM. They are SecureStrings
# under the account's default `aws/ssm` key: free, and the same pattern
# the runtime-env parameter already uses (team.md names SSM over Secrets
# Manager because it costs nothing).
#
# **What this does NOT fix, stated rather than implied.** Terraform
# state still holds every one of these values, as it holds every
# generated password; the state bucket is the control for that, and is
# why it is encrypted, versioned, private and TLS-only.

# The CDN-to-origin shared secret, for nginx's header check.
resource "aws_ssm_parameter" "origin_secret" {
  name        = "/shikkhokplus/${var.name_prefix}/origin-secret"
  type        = "SecureString"
  value       = random_password.origin_secret.result
  description = "X-Origin-Secret value nginx requires. Read by the host at boot."
}

# **The restricted application role's password** [OPS-5].
#
# The API used to connect as `shikkhok`, the RDS master user: owner of
# every table and a member of rds_superuser, so it could run DDL, create
# roles, and UPDATE or DELETE audit and ledger rows. project.md mandates
# the restricted non-superuser role for the privacy suite precisely
# because owners bypass row-level security; running PRODUCTION as the
# owner voided every grant-based restriction the migrations declare.
#
# `shikkhok_app` is created by the migrations without a password. The
# boot script sets it from this value with
# `python -m app.db.commands set-app-role-password`, connected as the
# owner, after migrating and before the API starts.
resource "random_password" "app_db" {
  count = var.managed_database ? 1 : 0

  length  = 32
  special = false
}

locals {
  # Host and port from RDS, e.g. `x.rds.amazonaws.com:5432`.
  database_host = var.managed_database ? var.database_endpoint : ""
}

# What the API and the scheduled jobs connect with: the restricted role.
resource "aws_ssm_parameter" "database_url" {
  count = var.managed_database ? 1 : 0

  name        = "/shikkhokplus/${var.name_prefix}/database-url"
  type        = "SecureString"
  value       = "postgresql+psycopg://shikkhok_app:${random_password.app_db[0].result}@${local.database_host}/shikkhokplus"
  description = "SHIKKHOKPLUS_DATABASE_URL: the restricted shikkhok_app role."
}

# **What ONLY the migration step connects with: the owner.** Never
# written to the host's .env and never in the API container's
# environment -- the boot script exports it for the two one-shot
# commands that need it and nothing else.
resource "aws_ssm_parameter" "migration_database_url" {
  count = var.managed_database ? 1 : 0

  name        = "/shikkhokplus/${var.name_prefix}/migration-database-url"
  type        = "SecureString"
  value       = "postgresql+psycopg://shikkhok:${var.database_password}@${local.database_host}/shikkhokplus"
  description = "SHIKKHOKPLUS_MIGRATION_DATABASE_URL: the owner, for alembic only."
}

resource "aws_ssm_parameter" "app_db_password" {
  count = var.managed_database ? 1 : 0

  name        = "/shikkhokplus/${var.name_prefix}/app-db-password"
  type        = "SecureString"
  value       = random_password.app_db[0].result
  description = "SHIKKHOKPLUS_APP_DB_PASSWORD: set on shikkhok_app at boot."
}

locals {
  # Everything the instance role may read. The deploy role reads none
  # of the database parameters: it writes the image tag and the runtime
  # env, and has no reason to hold a database credential.
  boot_parameter_arns = concat(
    [
      aws_ssm_parameter.image_tag.arn,
      aws_ssm_parameter.runtime_env.arn,
      aws_ssm_parameter.origin_secret.arn,
    ],
    aws_ssm_parameter.database_url[*].arn,
    aws_ssm_parameter.migration_database_url[*].arn,
    aws_ssm_parameter.app_db_password[*].arn,
  )
}
