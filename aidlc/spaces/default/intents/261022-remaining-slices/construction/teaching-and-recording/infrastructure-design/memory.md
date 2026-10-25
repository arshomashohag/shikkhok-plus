# Stage diary — infrastructure-design (3.4), D4 `teaching-and-recording`

## What I verified rather than inherited

- **Cost, recomputed from `infra/main.tf`'s own `cost_breakdown`** at
  `infra/variables.tf` values: `cost_instance = 12.26`,
  `cost_storage = 30 x 0.08 = 2.40`, `cost_host = 14.66`, `route53 = 0.50`,
  `ecr = 0.10`, `rds = 17.36`. App only 15.26; +staging 29.92; +RDS 32.62;
  both 47.28. Ceiling 50 [OC-4]. The stale "USD 50.20" is corrected in
  `main.tf:41-51` and I did not quote it.
- **`enable_rds` default**: confirmed `variables.tf:166`; `terraform.tfvars.example:30`
  sets `false`, `:21` sets `enable_staging_instance = true`. State the
  configuration beside any figure.
- **The fee cron entry exists** at `user_data.sh.tftpl:425-443`, and the
  **freshness check is a `Restart=always` systemd service**, `:457-500`, not a
  second cron entry. Both hardcode `app.fees.commands`.
- **`app/fees/commands.py` is parameterised by `job_name` at the FUNCTION
  level** (`stamp_heartbeat:92`, `check_generation_freshness:170`) but the
  **CLI entry points are not**: `main_check_freshness:251` hardcodes
  `FEE_GENERATION_JOB`, and `main():269` dispatches on a verb with no job
  argument. This is the real D4 infrastructure finding.
- **`deploy.yml` has no Alembic step.** Searched the whole file for
  `alembic`/`migrat`: only comments and the unused `skip_migrations` input at
  `:39`. The input is referenced nowhere. Migration runs at boot only,
  `user_data.sh.tftpl:394-412`.
- **Dispositions**: 19 entries in `app/governance/dispositions.py`; none of
  D4's six tables declared. `RETENTION` is derived (`:279-281`).
- **Grants**: `0005_fee_system.py:127-133` `NEW_TABLES` + loop at `:356`.
  No `ALTER DEFAULT PRIVILEGES` anywhere.
- **Reachability tests already exist**: `tests/db/test_governance.py:171`
  and `:191`. I did not propose rebuilding them.
- **No metrics backend, no CloudWatch alarm, no SNS topic, no log shipping.**

## Decisions

- D4 adds **one cron entry and one parameterisation change**, nothing else.
  Said plainly, in D2's register.
- The conflict rate: the **applied** side is answerable from
  `attendance_submission`; the **refused** side writes no row and exists only
  as a counter. Monitoring doc states where that counter goes and that nothing
  reads it.
- No latency mechanism for the attendance path. PU-3.6 carries no V1
  obligation (dropped at Q14.3); `team.md`'s D5 Macrobenchmark line is stale
  and not inherited.

## Late findings, after the first three sections were drafted

- **`team.md` is stale on the toolchain gaps it assigns to "before D1".**
  `requirements.txt` (hash-pinned), `android/gradle.lockfile`,
  `gradle/verification-metadata.xml`, `.security-exceptions.md`,
  `.github/dependabot.yml`, `android/lint.xml`, spotless, detekt and
  `verifyCoverageRatchet` all exist now. Checked each by opening the file.
  Recorded in `cicd-pipeline.md` § 4 because a stale "absent" misleads as
  much as a stale number.
- **The Docker precondition assertion is still genuinely missing**, and it
  is the one that matters most to D4: seven of this unit's guarantees are
  tested only in the integration suite that silently skips without Docker.
- **`app.authz` is still not a strict island**, and D4 is lens-heavy.

## Sensor results

All three pass. `traceability` needed two corrections: five rows I first
wrote as `GAP` are `Deferred` (each is designed and costed, awaiting a human
choice — `GAP` would have claimed they were unaddressed), and ten ids the
resolver finds are **citations of D3's numbering** which this unit's own
requirement documents flag as "never an id defined here". Enumerated as
`N/A` with that reason rather than suppressed.

## One citation I got wrong and fixed

I wrote `main_check_freshness()` at `commands.py:241`; the call is at `:244`
and `:241` is a docstring line. Caught by re-reading every cited line rather
than trusting the first grep.

## Open for the human

- **Not optional**: how the freshness check learns D4's job name. Three
  options costed in spec § 3.3. Unchosen means D4's only alert does not fire.
- Where the conflict/replay counter lives. The refused side writes no row, so
  it is unanswerable from data; option A (a log line) answers nothing after
  the pilot and is the default outcome of doing nothing.
- The `skip_migrations` input that skips nothing.
- Staging for the six-table rehearsal; the pre-migration `pg_dump`.
- The Bangla verifier for seven screens; the Docker precondition assertion.

## Review outcome and the three corrections, 2026-10-25

Verdict **READY** (advisory). One Major, one Minor, both answered before close.

**Major — `app.authz` was claimed unconfigured and is configured.** I wrote
§ 2.3 saying the strict island was still missing and listed it twice more as
an open item for the human. `pyproject.toml:222-226` has set `strict = true`
and `disallow_any_explicit = true` on `app.authz.*` since **2026-10-22**, two
days before this stage's own stated evidence date, and the comment above the
override explains that it closed exactly this gap.

The lesson is not "check the file", which this record has written five times
already. It is narrower and it has a name here: **`team.md` is a snapshot that
reads as current policy, and it reaches every stage through the rule bundle.**
Its Code Style section still says the island "was never configured ... Assigned
to: before D1". I read that, treated it as the state of the repository, and
wrote it into three places. A stale practice file does not merely fail to help;
it supplies a confident wrong answer to a stage that had no reason to doubt it.
Where a practice asserts built state, the practice is a claim like any other.

**Minor — `skip_migrations` was described as present.** Correct when drafted;
I removed the input from `deploy.yml` during this same session. Both documents
now record the removal **and** that it closed nothing: there is still no
pipeline-side Alembic step and no preview of what is about to be applied.
Deleting a control that did nothing is not the same as building one that does
something, and D4's six tables are the largest thing that distinction touches.

**The freshness check: the human chose option B**, enumerate every registered
job. The deciding property was that `user_data` takes effect only on instance
replacement, so any option requiring a `user_data` edit is one a later unit can
silently fail to apply. Option B's accepted cost — a retired job's row alerting
forever — is now written as a rule in spec § 3.3: the migration that retires a
job deletes its row. Nothing enforces that and nothing retires a job in D4; it
is recorded so the first retirement does not rediscover it.

What the reviewer verified independently and I did not have to re-check: all
four cost figures recomputed from `infra/main.tf`'s own locals; the
NFR24.15 roster-logging prohibition against the proposed counter shape; 19
disposition entries with none of D4's six among them; `traceability.json` at
32 OK / 15 Deferred / 83 N/A / 0 GAP with four Deferred rows spot-checked; and
**8 of 9 toolchain items `team.md` calls absent are present on disk** — which
is the same stale-snapshot finding as the Major, reached from the other side.
