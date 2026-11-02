# Restoring the database

**Status: written 2026-11-02, NOT yet exercised.** Nobody has run these
steps against a real snapshot. team.md says the restore path must be
exercised once before launch, because an untested backup is not a
backup. Until somebody has done it on staging, and timed it, treat every
command here as a plan, not a proven procedure. When it has been
exercised, replace this paragraph with the date, the environment, how
long each step took, and what had to change.

## What exists to restore from

| Source | Made by | Granularity | Kept |
|---|---|---|---|
| Pre-deploy snapshot `shikkhokplus-<env>-predeploy-<sha12>-<run>-<attempt>` | `deploy.yml`, "Snapshot the database", before any host can migrate | One per deploy, named by the commit being deployed | Newest 7 per environment |
| RDS automated backups | RDS, `backup_retention_period = 7` | Point in time, to about 5 minutes | 7 days |
| Final snapshot `shikkhokplus-<env>-db-final` | RDS, if the instance is ever destroyed | One | Until deleted by hand |

There is **no** backup of a database that lives on the app host
(`enable_rds = false`). Production refuses that configuration at plan
time and the deploy workflow refuses to release to it, because the host
is replaced on every deploy and its root volume is deleted with it.

- **RPO**: the pre-deploy snapshot is exact for "undo this release's
  migration"; anything written after it is lost if you restore it.
  Point-in-time recovery narrows that to about five minutes.
- **RTO**: unmeasured. Restoring a `db.t4g.micro` with 20 GB is
  typically tens of minutes, but that figure is not from this project.

## Before you start

1. Stop new writes, so what you restore is not immediately stale:
   dispatch nothing, and on the app host stop the API and the
   scheduled jobs.

   ```bash
   aws ssm start-session --target <instance-id>
   cd /srv/shikkhokplus && sudo -u ubuntu docker compose stop
   sudo systemctl stop shikkhokplus-freshness cron
   ```

2. Decide which point you are restoring to and write it down. For a bad
   migration, it is the pre-deploy snapshot of the release that ran it:

   ```bash
   aws rds describe-db-snapshots \
     --db-instance-identifier shikkhokplus-<env>-db --snapshot-type manual \
     --query 'reverse(sort_by(DBSnapshots,&SnapshotCreateTime))[].[DBSnapshotIdentifier,SnapshotCreateTime]' \
     --output table
   ```

## Restore beside the live database

Never restore over the instance you are recovering from: keep it until
the restored copy is verified.

```bash
ENV=staging                                   # or production
DB=shikkhokplus-$ENV-db
SG=$(aws rds describe-db-instances --db-instance-identifier $DB \
  --query 'DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' --output text)

aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier $DB-restored \
  --db-snapshot-identifier <snapshot-id> \
  --db-instance-class db.t4g.micro \
  --db-subnet-group-name $DB \
  --vpc-security-group-ids $SG \
  --no-publicly-accessible \
  --deletion-protection
aws rds wait db-instance-available --db-instance-identifier $DB-restored
```

For point-in-time instead, replace the first command with
`aws rds restore-db-instance-to-point-in-time --source-db-instance-identifier $DB --target-db-instance-identifier $DB-restored --restore-time <UTC ISO-8601>` and the same network flags.

The restored instance keeps the snapshot's master password, which is
the one Terraform generated, so the owner URL and the `shikkhok_app`
password in SSM still work against it.

## Swap it in under the original name

The endpoint hostname is derived from the instance identifier, so
giving the restored instance the original identifier leaves every URL
in SSM correct.

```bash
aws rds modify-db-instance --db-instance-identifier $DB \
  --new-db-instance-identifier $DB-replaced --apply-immediately
aws rds wait db-instance-available --db-instance-identifier $DB-replaced
aws rds modify-db-instance --db-instance-identifier $DB-restored \
  --new-db-instance-identifier $DB --apply-immediately
aws rds wait db-instance-available --db-instance-identifier $DB
```

## Bring the application back, and verify

Start a fresh host so the boot runs migrations and sets the
`shikkhok_app` password against the restored database. If you restored
to undo a release, first put the previous release back in SSM (the
`image-tag` and `runtime-env` parameters) -- the deploy workflow's
rollback step does exactly this and shows the commands.

```bash
deploy/roll.sh shikkhokplus-$ENV
python3 deploy/smoke.py "$(aws ssm get-parameter \
  --name /shikkhokplus/shikkhokplus-$ENV/api-url \
  --query Parameter.Value --output text)"
```

Then check the data, not just the health endpoint: sign in as a known
teacher and read a batch, a fee cycle and an attendance record whose
values you know.

## Hand the instance back to Terraform

Terraform tracks the database by its RDS resource id, which belongs to
the instance now named `$DB-replaced`. Point state at the restored one
before the next apply, or the apply will try to rename them back:

```bash
cd infra
terraform init -backend-config="bucket=<state bucket>" \
  -backend-config="key=$ENV/terraform.tfstate"
terraform state rm 'module.database.aws_db_instance.main[0]'
terraform import 'module.database.aws_db_instance.main[0]' $DB
TF_VAR_environment=$ENV TF_VAR_apex_domain=<apex> terraform plan
```

The plan should show no replacement of the database. When it does not,
and the application has been verified, delete `$DB-replaced` (disable
its deletion protection first; take a final snapshot).
