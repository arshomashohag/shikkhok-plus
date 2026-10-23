# Infrastructure Design — Questions

**Stage**: infrastructure-design (3.4)
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

## How this stage was answered

**D2 is the first unit of this record that touches the database schema not at
all.** Its backend change is two response fields and one aggregate; its client
change is four screens and a package. There is nothing to provision, nothing
to migrate, and nothing to rehearse.

That makes this stage short, and the short version is the useful one — but
"no infrastructure change" is also what a unit says when nobody checked. Each
answer below is verified against `infra/` and `.github/workflows/` rather than
assumed from the unit's type.

---

## Q1. Does D2 need any new infrastructure?

[Answer]: **No.** Verified: no new service, datastore, queue, cache, job or
environment. The `Infrastructure Services` table in D1's specification is
unchanged, and D2 adds no row to it.

[NFR7.5 of D1, inherited] [logical-components § 5]

## Q2. Does D2 add a migration?

[Answer]: **No, and this is the first unit of this record for which that is
true.** `migrations/versions/` ends at `0004_acceptance_and_address.py`, which
is D1's. D2 reads the two columns `0004` added and writes neither.

The consequence is worth naming rather than skipping: **D2's deploy needs no
rehearsal, no backup checkpoint and no rollback question about the schema.**
Its deploy risk is the risk of any application change.

[code: `migrations/versions/`] [logical-components § 3]

## Q3. Does D2 make D1's two handed-forward gaps worse?

[Answer]: **No, and one of them does not apply to this unit at all.**

| Gap | D2's relationship |
|---|---|
| Staging instance switched off [NFR19.4] | **Does not apply.** Staging exists to rehearse a migration, and D2 has none |
| No pre-migration backup assertion [NFR19.3] | **Does not apply.** Same reason |
| `rate_limit_counter` purge | Unaffected — D2 adds no row; its routes are authenticated |
| `auth_audit_log` purge | Unaffected — D2 adds no audit event |

**Both D1 gaps remain open and remain D1's**, and a reader should not take
"does not apply to D2" as "closed". They block D1's production deploy, not
this unit's.

[D1 `infrastructure-specification.md` Gaps] [code: `infra/variables.tf`]

## Q4. Does the budget change?

[Answer]: No. D2 adds no Terraform resource, so the estimate the budget guard
checks is unchanged at **USD 32.62** against the acknowledged USD 50 —
staging off, RDS on, per the variable defaults verified at D1.

[code: `infra/main.tf:60-85`] [OC-4]

## Q5. Does the CI pipeline need a stage?

[Answer]: **No stage, and one prediction to check.** D2's new tests are pytest
and JUnit/Robolectric, so they run inside `make check` without a pipeline
change.

What D2 *does* carry is the first real test of the Compose coverage exclusion
D1 made: four new screens against a ratchet floor of 45.84. Build and Test is
where that is confirmed or falsified, and the action differs by outcome —
if the floor drops, the fix is to narrow `**/ui/*Kt*`, not to lower the floor.

[tech-stack-decisions.md] [code: `android/coverage.gradle.kts`]

## Q6. Does the deploy path change?

[Answer]: No. SHA-tagged image, immutable registry, ASG instance refresh,
`/health` over SSM. D2 inherits all of it and depends on none of the
migration-specific properties D1 needed.

The **post-deploy smoke gap** D1 named is unchanged: `/health` proves the
process answers, not that a person can use the product. D2 adds screens over
endpoints that already worked, so it neither widens nor narrows that gap.

[D1 `cicd-pipeline.md`] [code: `.github/workflows/deploy.yml`]

## Q7. Does the widened schema need a version bump?

[Answer]: **No.** `/v1/` stays additive and the client handles unknown fields
rather than failing to parse [D-26]. Two response shapes gaining fields is
exactly the additive case that policy exists for.

What makes it safe to do silently is the **schema-diff gate**: the committed
`openapi.json` must match the generated one, so the widening appears as a
reviewable diff rather than as a surprise in a client.

[D-26] [NFR16] [team: Both surfaces]

## Assumptions & Open Questions

- **Assumed**: the two new response fields flow through the committed OpenAPI
  document and its diff gate without any pipeline change, as D1's did.
- **Assumed**: no observability change. D2 adds no audit event, no alert and
  no metric beyond what the existing logs already carry.
- **Open, and D1's**: the staging instance and the pre-migration backup
  assertion. Named here so the handoff is not lost between units, not because
  D2 can close either.
