# Deployment Log: Unique usernames

## Status: NOT EXECUTED, by the person's decision

The person decided: "Record, don't deploy (Recommended)". In this stage:

- no workflow was triggered;
- no AWS API was called;
- no deploy script, smoke run or health check was run against any host;
- nothing was pushed.

What follows is the record the person will deploy from. Every step below is
the pipeline as built (`.github/workflows/deploy.yml`, `deploy/`,
`infra/modules/app/user_data.sh.tftpl`), read on 2026-11-15.

| Item | Value |
|---|---|
| Intent | `261113-unique-usernames` (U1 usernames-backend, U2 contacts-and-invites-backend, U3 android-identity, U4 web-identity) |
| Target environment | `staging` first. `production` is a separate, later, explicit dispatch |
| Commit to deploy | the squash-merge commit of this intent's PR on `main`. Not known yet: the PR is not merged |
| Image | `shikkhokplus-staging-backend:<that commit's full SHA>`. Never `latest`. The repository is IMMUTABLE |
| Expected migration head after deploy | **`0038`** (`migrations/versions/0038_usernames.py`) |
| Deploy executed | **No** |
| Smoke run | **No** (see `smoke-test-results.md`) |
| Health checked | **No** (see `health-check-report.md`) |

---

## 1. Preconditions, before dispatch

1. The PR is merged to `main`, after the merge of `main` (#80) into this
   branch, with the renumbered migrations 0037 and 0038.
2. `check.yml` has run on the squash commit on `main`. It triggers on
   `push: branches: [main]`, and all five jobs concluded `success`:
   `backend`, `image`, `android-unit`, `web`, `site`. This is enforced, not
   advisory. The `plan` job's step "CI passed on this commit" waits up to
   20 minutes for those check runs on the resolved SHA, then fails the
   deploy.
3. The time is outside Bangladesh classroom hours and away from the host's
   scheduled jobs at `0 1 * * *` (session generation) and `0 2 * * *` (fee
   generation), in the host's timezone. The workspace defines no clock range
   for "classroom hours".

## 2. The dispatch the person will run

In the Actions UI: **Actions → deploy → Run workflow**, then:

- `environment` = `staging`
- `ref` = `main`, or leave it empty. Empty uses the ref the workflow was
  dispatched from, which is `main` by default.

From a terminal, the equivalent is:

```bash
gh workflow run deploy.yml --ref main -f environment=staging -f ref=main
```

**There is no `migrate` input.** The workflow declares exactly two inputs,
`environment` and `ref`. A `skip_migrations` input was removed on 2026-10-25,
because it was referenced nowhere and skipped nothing. Migrations always run,
as a distinct logged step at host boot (§ 3, step 10).

team.md (Deployment) still says that whether to migrate is "chosen at the
time". That sentence is out of date against the built pipeline. It is
recorded here as an open question and has not been edited.

## 3. What `deploy.yml` does, in order

**Job `plan`** (environment `staging`, read-only role):

1. Checks that the inputs are plain names. The ref must match
   `[A-Za-z0-9._/-]`, with no leading `-` and no `..`.
2. Checks out `inputs.ref`, then **resolves the commit once**
   (`git rev-parse HEAD`). Every later job uses this SHA, and it tags the
   image.
3. **CI passed on this commit**: the precondition in § 1.2.
4. Production only: requires the commit to be on `main`, and blocks on
   dependency CVEs (`pip-audit` on `requirements.txt` with
   `.security-exceptions.md`). Staging skips both.
5. Fails early when the environment is not configured, then checks the JWT
   signing keyring and resolves the ECR registry and the ASG.
6. Runs `terraform init` and `terraform plan`. The plan is written to the job
   summary, stored, and its sha256 is recorded.

**Job `infrastructure`** (environment `staging-infra`) applies exactly the
stored plan, verified by its digest. This intent changes nothing under
`infra/`, so the plan should show no intent-driven change. Any drift it does
show is real.

**Job `release`** (environment `staging`):

7. Builds and pushes `shikkhokplus-staging-backend:<sha>` as linux/arm64. The
   build is skipped if that tag already exists. Production only: the ECR image
   CVE gate.
8. **Remembers the running release**: the current SSM `image-tag` and the
   `runtime-env`, held in a 0600 file on the runner.
9. **Snapshots the database**: `aws rds create-db-snapshot` as
   `shikkhokplus-staging-predeploy-<sha12>-<run>-<attempt>`, then waits for
   `db-snapshot-available`. The deploy fails, before any state is written, if
   the snapshot cannot be taken or does not become available. The newest seven
   pre-deploy snapshots are kept.
10. **Records the deployment state**. The runtime env is written first, then
    the image tag, both to SSM.
11. **Rolls the instance** (`deploy/roll.sh`). This is an ASG instance
    refresh: the new host launches before the old one terminates. The new
    host's `user_data` pulls the image, then runs **migrations as a
    distinct, logged step before anything serves**:
    `docker compose --profile migrate run --rm migrate python -m
    app.db.commands migrate-if-behind`. Output goes to
    `/var/log/shikkhokplus-provision.log`. The migration runs under
    `migrations/env.py`'s `SET LOCAL lock_timeout = '10s'`. A failed migration
    exits the boot non-zero, so the host never serves. Next comes
    `set-app-role-password`, then `docker compose up -d`. The host enters
    service only after it answers `/health` through nginx over verified TLS.
12. **Smokes through CloudFront**:
    `python3 deploy/smoke.py <api-url> --attempts 18 --interval 10`. It adds
    `--sign-in-phone` only when `SHIKKHOKPLUS_STAGING_OUTBOX=1` and
    `SHIKKHOKPLUS_SMOKE_PHONE` is set. See `smoke-test-results.md` for a known
    defect in that optional path.
13. **On failure or cancellation after step 10, rolls back automatically**
    (§ 6).
14. Moves the staging seeder Lambda to the new image. This step is
    non-blocking.

**After `release`**, three more jobs run:

- `web` builds `/ui/`, uploads, invalidates and smokes. It carries U4. It runs
  only after `release` succeeds, so a rolled-back API ships no UI.
- `site` (public site) needs only `plan` and `infrastructure`.
- `admin` (admin UI) runs after `release`.

## 4. Migrations this deploy applies

The chain on the merged tree is:

`0033 → 0034_hub_reader_role → 0035_bd_area → 0036_hub_listings →
0037_contacts_and_email_invites → 0038_usernames`

`deploy/smoke.py`'s `migration_head()` returns `0038` on this tree. If staging
is not yet at `0036`, this boot applies **main's hub migrations 0034–0036
first**, in the same step. Those three belong to #80, and their compatibility
is that change's record, not this intent's.

| Revision | Unit | What it does (read from the migration) | Forward-only and backward-compatible? |
|---|---|---|---|
| `0037` `contacts_and_email_invites` (written as 0034 before the renumbering) | U2 | Adds 5 nullable `VARCHAR(254)` email columns: `student.student_email`, `student.guardian_email`, `enrollment.student_email`, `enrollment.guardian_email`, `owner_member.invited_email`. Each has a lowercase CHECK. Adds partial indexes `uq_student_owner_email` (unique), `ix_enrollment_student_email`, `ix_enrollment_guardian_email`, `uq_owner_member_live_email` (unique) and `ix_owner_member_unlinked_email`. Makes **`owner_member.invited_phone` nullable**, under CHECK `ck_owner_member_has_contact`. Adds `otp_request.requested_by_account_id` (FK `ON DELETE SET NULL`) with its partial index. No row is updated | Additive DDL with no backfill. The schema is compatible with the previous image, which never writes the new columns, and its inserts satisfy every new CHECK. **One data caveat (U2 NFR7.3)**: once any email-only invitation exists (`invited_phone IS NULL`), the previous image's centre member list fails to serialise. `MemberResponse.phone: str` is built from `row.invited_phone` in `app/centres/service.py` on `main`. `downgrade()` refuses in that same state |
| `0038` `usernames` (written as 0035 before the renumbering) | U1 | Adds nullable `account.username`, `account.username_key`, `account.username_changed_at` and `account.username_reclaimed_at`. Adds unique `uq_account_username_key` and CHECKs `ck_account_username_both_or_neither`, `ck_account_username_key_lower` and `ck_account_username_key_shape`. Adds nullable `pending_signup.username`. Creates table `username_hold` (PK `key_digest`, FK `releasing_account_id` `ON DELETE SET NULL`, two indexes) and `GRANT SELECT, INSERT, UPDATE, DELETE` on it to `shikkhok_app`. No row is updated | Additive DDL with no backfill. The previous image neither reads nor writes these columns. Its account inserts leave both username columns NULL, which passes the both-or-neither CHECK. Costs accepted in U1 NFR6.3: a sign-up completed on the previous image yields an account with no username (`username_required` after the next roll-forward), and a deletion on the previous image places no hold. `downgrade()` refuses while any account has a username |

**Not to be used as rollback**: `alembic downgrade`. Both migrations refuse
to downgrade once data exists in the new shape, by design. U1 NFR7.3 states
that the downgrade is not exercised in production.

**Pre-migration backup**: team.md asks for a verified backup immediately
before any production migration. Its Phase 1 wording names a `pg_dump` to S3
with an existence and size check. The pipeline as built does something
stronger, on every deploy, staging included: step 9's **named RDS snapshot**.
It fails closed, and it is taken before any state is written or any host can
migrate. Restoring from it follows `infra/RESTORE.md`, which restores beside
the live instance and never over it.

The team.md wording predates the move to RDS; `deploy/README.md` was
rewritten on 2026-11-02 for the same reason. The record here follows the
built pipeline. Whether the restore path has been exercised at least once, as
team.md requires before launch, is not established by this stage.

## 5. Recording migration duration (U1 NFR7.2, U2 NFR7.2: ≤ 10 s each)

**Not yet checked. Nothing automated measures it.**

The NFRs name "the staging deploy log's migrate-step duration" as the
verifier. As built, the migration runs on the host inside `user_data`, not as
a GitHub Actions step. Its output goes to `/var/log/shikkhokplus-provision.log`,
whose lines carry **no timestamps**. The Actions log shows only the duration
of `roll.sh` as a whole.

So the named source does not contain the figure. A manual reading is needed.
Two options:

- After the deploy, use `aws ssm start-session` on the new host and check the
  `docker` events or journal timestamps around the `migrate` container
  (`docker events` is not retained after the fact; `journalctl -u docker`
  is).
- Rehearse the two revisions with `time` against a database restored from
  the pre-deploy snapshot (`infra/RESTORE.md`).

The `lock_timeout` of 10 s bounds lock waits, not total duration.

## 6. Rollback procedure

**The database is not rolled back.** Migrations are forward-only. The rollback
is the previous immutable image tag.

### 6a. Automatic, inside the same run

`deploy.yml` step "Roll back to the previous release" runs on `failure()` or
`cancelled()`, once the record step has run. It does the following:

1. Puts back the remembered SSM `image-tag` (the previous SHA) and the
   `runtime-env`.
2. If the refresh was interrupted, cancels it and waits.
3. If the smoke failed or the refresh was cancelled, runs `deploy/roll.sh`
   again, so a fresh host boots the previous image.

The previous image's boot runs `migrate-if-behind`. The database is at `0038`,
which is later than the previous image's head (`0036` if staging last ran
`main` after #80), so the command **skips the upgrade and serves**
(`app/db/commands.py`, `MigrationPlan.AHEAD`). The run then ends with
`::error::Deploy did not complete and was rolled back to <sha12>`.

**What rolling back the app leaves in the schema**: everything from 0037 and
0038, and from 0034–0036 if this deploy applied them. That means the 5 email
columns, their CHECKs and indexes, nullable `owner_member.invited_phone`,
`otp_request.requested_by_account_id`, the 4 username columns with their
unique key and 3 CHECKs, `pending_signup.username`, and the `username_hold`
table.

This is backward-compatible with the previous image, verified from the
migration code (§ 4), with one data-dependent exception: email-only
invitations (U2 NFR7.3). **Release-checklist rule**: once any email-only
centre invitation exists in an environment, a rollback there is a roll-forward
fix, not a tag rollback. Check before rolling back with:

```sql
SELECT count(*) FROM owner_member WHERE invited_phone IS NULL;
```

Run it under the named, logged non-superuser role team.md requires for
interactive production sessions.

### 6b. Manual, after a completed run

`deploy/README.md` § "Rolling back" says to dispatch `deploy` with the earlier
ref. **After a release that added migrations, that path cannot succeed as
built.** Rolling back to a pre-0037 ref will fail, and undo itself, for this
reason:

1. The earlier ref's checkout computes its own head (`0036` or lower) in
   `deploy/smoke.py`.
2. The live database reports `0038`.
3. `smoke.py` requires `migration_revision == head`, so the smoke fails after
   18 attempts.
4. Step 6a then restores the release it was dispatched to replace, the
   `0038` image.

This defect is not introduced by this intent. It is reached by any rollback
across a migration, and this intent's rollback is one.

Until `smoke.py` accepts a database that is ahead, the working manual
rollback is to do by hand what step 6a does:

1. Set SSM `/shikkhokplus/shikkhokplus-staging/image-tag` to the previous SHA.
2. Keep the current `runtime-env`. This intent adds no runtime variable that
   the previous image needs.
3. Run `deploy/roll.sh shikkhokplus-staging` with the deploy role.
4. Confirm `/health` shows `database: ok` and `migration_revision: 0038`.

This manual path is **not automated and not tested by this stage**.

The previous SHA is the one the run printed as "Running before this deploy",
or the image tag in SSM before the dispatch.

### 6c. Schema recovery, only if compatibility did not hold

Restore the pre-deploy snapshot from step 9, following `infra/RESTORE.md`.
Its RPO is exact for "undo this release's migration": anything written after
the snapshot is lost.

## 7. Production (not part of this stage)

Production is a separate explicit dispatch with `environment = production`.
Two things gate it mechanically: `plan` refuses commits not on `main`, and
`<env>-infra` approval sees the plan first.

The team.md checklist the person completes before dispatching:

- staging smoke passed;
- the Alembic migrations were reviewed as forward-safe (§ 4);
- no open Critical or High dependency finding without a dated exception;
- the manifest allowlist and DEX scan are green on the release build.

Production deploys go outside Bangladesh classroom hours. The sign-in smoke
does not run there; production smoke is health only.

## Sources

- The person's decision: "Record, don't deploy (Recommended)".
- `.github/workflows/deploy.yml`: inputs at lines 38–54; jobs `plan`,
  `infrastructure`, `release`, `web`, `site`, `admin`; steps "CI passed on
  this commit", "Snapshot the database", "Record the deployment state", "Roll
  the instance", "Smoke through CloudFront", "Roll back to the previous
  release".
- `.github/workflows/check.yml` (triggers and job names).
- `infra/modules/app/user_data.sh.tftpl`, lines 592–652 (the migration step)
  and the cron entries.
- `app/db/commands.py` (`migrate_if_behind`, `MigrationPlan.AHEAD`).
- `migrations/env.py` (`lock_timeout`).
- `migrations/versions/0037_contacts_and_email_invites.py`,
  `0038_usernames.py`, and main's `0034_hub_reader_role.py`,
  `0035_bd_area.py`, `0036_hub_listings.py`.
- `deploy/smoke.py`, `deploy/README.md` (including "Rolling back"),
  `deploy/roll.sh`, `infra/RESTORE.md`.
- `app/centres/service.py` and `app/schemas/centres.py` on `origin/main`
  (`MemberResponse.phone: str`).
- `construction/usernames-backend/nfr-requirements/reliability-requirements.md`
  (NFR6.3, NFR7.2, NFR7.3) and
  `construction/contacts-and-invites-backend/nfr-requirements/reliability-requirements.md`
  (NFR7.2, NFR7.3).
- `construction/build-and-test/build-and-test-summary.md`.
- `aidlc/spaces/default/memory/team.md` (Deployment) and `phases/operation.md`.

## Assumptions & Open Questions

- **Assumption**: the previous release on staging is a `main` build at or
  after `0036`. If it is older, the rollback image has a lower head, and
  `migrate-if-behind` still skips, because the database is ahead on the same
  numbered line. Staging's live tag and revision were not read: this stage
  contacts no environment.
- **Assumption**: no earlier staging deploy ran this branch with its
  pre-renumbering `0034`/`0035`, whose ids collide with main's. If one did,
  `migrate-if-behind` refuses the database ("unknown revision at or below
  head"), and recovery is the snapshot.
- **Open (structural)**: the documented manual rollback ("dispatch deploy with
  the earlier ref") fails after any migration, because `smoke.py` demands an
  exact head (§ 6b). It needs a fix to `deploy/smoke.py` (accept a later
  numbered revision) or to the README. Out of this stage's write scope.
- **Open (structural)**: the NFR7.2 migration-duration verifier names a log
  line that has no timestamp (§ 5).
- **Open**: team.md's "whether to migrate chosen at the time" and "`pg_dump`
  to S3" describe a pipeline that no longer exists. The built pipeline has no
  migrate choice and takes an RDS snapshot. Reconciling the practice text is
  the person's call.
- **Open (minor)**: `deploy/README.md` lists
  `SHIKKHOKPLUS_GLOBAL_HOURLY_USERNAME_LOOKUPS` as a GitHub "variable, default
  `1000`". But `deploy.yml`'s "Record the deployment state" step never writes
  it into `runtime-env`, so setting that variable changes nothing, and the
  deployed alert threshold is always the code default of 1000. Alert-only,
  never refuses.
