# Deployment Execution: Pre-Deployment Questions

Intent `261113-unique-usernames`. Scope `refactor`. Deployment Pipeline and
Environment Provisioning are skipped in this plan, so this stage uses the real
workspace pipeline: `.github/workflows/deploy.yml`, `.github/workflows/check.yml`,
`deploy/`, `infra/` and the `Makefile`. Where the person did not answer a
question directly, the answer comes from the evidence named under it. In those
questions, option A is the recommendation.

---

## Q1. Deployment decision

What happens in this stage?

A. Record, don't deploy (Recommended). Merge the PR once CI is green, then the
   person dispatches the staging deploy later.
B. Dispatch the staging deploy from this stage once the PR has merged.
C. Dispatch staging, then production, from this stage.
X. Other (please specify)

[Answer]: Record, don't deploy (Recommended)

The person's answer is quoted verbatim. Nothing was deployed in this stage. No
workflow was triggered, no AWS API was called, no script was run against a
host, and nothing was pushed.

---

## Q2. Are all pre-deployment checks passing?

A. Locally yes, except three checks only CI can run. CI on the PR decides
   them, and `deploy.yml` will not deploy a commit until `check.yml` has passed
   on that exact SHA. (Recommended)
B. Yes, every check is green, CI included.
C. No. A blocking check is failing.
X. Other (please specify)

[Answer]: A.

Evidence, from `construction/build-and-test/build-and-test-summary.md`:

- **Backend**: 3101 passed, 0 failed, 0 skipped, against PostgreSQL 16 as
  `shikkhok_app`.
- **Android**: 2099 passed. One earlier forced run failed once
  (`UsernameGateRoutingTest`). Its wall-clock bound was later raised from 5 s
  to 20 s, and the test then passed 7/7 three times.
- **Web**: 1148 passed.
- **Coverage**: backend 96% line against the 80% floor. Android 90.39%
  against the 90.05% ratchet.
- **Schema gates**: schema-diff and schema parity are green.

Three checks were not reproduced locally: Gitleaks, osv-scanner and the
`check.yml` `image` job. The `image` job builds the image, migrates a
throwaway PostgreSQL 16 and runs `deploy/smoke.py`.

These results predate the merge of `main` (#80, public hub) into this branch.
The merged tree must go green on the PR's CI run before merge. The `plan` job
in `deploy.yml` enforces this mechanically. Its step "CI passed on this
commit" refuses the deploy unless the latest run of each of `backend`,
`image`, `android-unit`, `web` and `site` concluded `success` on the resolved
SHA.

---

## Q3. Are database migrations required, and are they tested?

A. Yes, two in this intent: `0037_contacts_and_email_invites` (U2) and
   `0038_usernames` (U1). Both are additive and nullable, and the deploy runs
   them as a distinct boot step. They are tested in CI against PostgreSQL 16.
   Staging rehearsal and timing are still open. (Recommended)
B. Yes, and they have already been rehearsed on staging.
C. No migrations.
X. Other (please specify)

[Answer]: A.

The migration chain after the merge of `main` is
`0033 → 0034_hub_reader_role → 0035_bd_area → 0036_hub_listings →
0037_contacts_and_email_invites → 0038_usernames`. The single head is
**`0038`**. The 0034–0036 migrations are main's public-hub migrations, not
this intent's. If staging is not yet at `0036`, the staging deploy applies
them first, in the same boot step.

The intent's migrations are exercised in CI in four ways:

- the schema-parity test;
- the index-usability tests (U1 NFR8.2, U2 NFR8.3, NFR8.8);
- the restricted-role integration suite, which runs from an empty database
  up to head;
- the `image` job, which migrates a fresh PostgreSQL 16 and asserts that
  `/health` reports the head.

Not yet checked, and nothing automated does it: a rehearsal against
staging's real data, and the ≤ 10 s duration (U1 NFR7.2, U2 NFR7.2).

---

## Q4. Are dependent services available and healthy?

A. Unknown from here, deliberately. This stage contacts no environment. The
   deploy checks the dependencies itself and fails before changing anything,
   so this does not block. (Recommended)
B. Yes, verified now.
C. No, a dependency is known to be down.
X. Other (please specify)

[Answer]: A.

`deploy.yml` reads or creates the following before it writes any deployment
state, and fails closed if one is missing:

- the RDS instance `shikkhokplus-staging-db`, which "Snapshot the database"
  fails without;
- the admin edge secret in SSM;
- the five SES sender parameters (`infra/modules/email`);
- the signing keyring (the "Check the signing keyring" step);
- the ECR repository.

The SMS gateway credentials come from GitHub secrets and variables. Staging
uses `SHIKKHOKPLUS_STAGING_OUTBOX` only when it is explicitly enabled.

This intent adds no new external dependency. Email codes use the SES path
that already exists from revision 0032.

---

## Q5. What is the deployment window?

A. The person chooses the time when dispatching. Use staging outside
   Bangladesh classroom hours and away from the host's scheduled jobs (01:00
   and 02:00 host time). Production is a separate later dispatch with the
   team.md checklist. (Recommended)
B. Immediately on merge.
C. A fixed maintenance window, defined now.
X. Other (please specify)

[Answer]: A.

team.md (Deployment) sets the rule: staging deploys on an explicit dispatch,
and production deploys are scheduled outside Bangladesh classroom hours. No
artifact in the workspace defines those hours as a clock range, so this file
does not invent one.

The host's cron runs session generation at `0 1 * * *` and fee generation at
`0 2 * * *` (`infra/modules/app/user_data.sh.tftpl`). The host timezone is not
set there, so it is the AMI default. Avoid deploying across those minutes.

---

## Sources

- Person's decision, as relayed in the dispatch brief: "Record, don't deploy
  (Recommended)".
- `.claude/aidlc-common/stages/operation/deployment-execution.md` (the four
  pre-deployment questions; Deployment Pipeline skipped means the stage uses
  the workspace pipeline).
- `construction/build-and-test/build-and-test-summary.md`,
  `performance-test-instructions.md`, `test-results.md`.
- `.github/workflows/deploy.yml`: jobs `plan`, `infrastructure`, `release`,
  `web`, `site`, `admin`; step "CI passed on this commit".
- `.github/workflows/check.yml`: triggers `push: [main]`, `pull_request`,
  `workflow_dispatch`; jobs `backend`, `image`, `android-unit`, `web`, `site`.
- `migrations/versions/0034_hub_reader_role.py` through `0038_usernames.py`;
  `deploy/smoke.py` `migration_head()`, which returns `0038` on the current
  tree.
- `infra/modules/app/user_data.sh.tftpl` (migration step, cron entries).
- `aidlc/spaces/default/memory/team.md` (Deployment).

## Assumptions & Open Questions

- **Assumption**: the renumbering to 0037/0038, done by the agent merging
  `main` into this branch, is what merges. The deploy records use those names.
  When this file was written, the working tree already showed
  `0037_contacts_and_email_invites.py` (`down_revision "0036"`) and
  `0038_usernames.py` (`down_revision "0037"`).
- **Assumption**: no staging deploy ever ran this branch's earlier,
  pre-renumbering `0034`/`0035`. Those ids collide with main's hub
  migrations. A staging database stamped with them would be on another line,
  and `migrate-if-behind` refuses that. This was not checked, because this
  stage contacts no environment.
- **Open**: what revision staging is at now, and which image tag it runs.
  Neither was read, because this stage contacts no environment.
- **Open**: the classroom-hours clock range is undefined in the workspace.
