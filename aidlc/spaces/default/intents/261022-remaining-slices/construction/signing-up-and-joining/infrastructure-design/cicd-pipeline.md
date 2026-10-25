# CI/CD Pipeline — D1 `signing-up-and-joining`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> **D1 adds no pipeline stage.** Its new obligations are pytest tests, and the
> gate is one command — `make check` — run identically locally and in CI. That
> is the design working as intended rather than an absence.
>
> What this document carries that is not already in the workflows: which
> existing gates D1's work lands behind, the one deploy-side gap D1 is
> directly implicated in, and the properties of this pipeline that D1's
> migration depends on.

## Sources

- [upstream] `construction/signing-up-and-joining/nfr-design/security-design.md` § 6
  — the verification design
- [upstream] `construction/signing-up-and-joining/nfr-design/reliability-design.md` § 4, § 6
  — the migration and smoke design
- [upstream] `construction/signing-up-and-joining/nfr-requirements/` — NFR19.x, NFR23.x
- [upstream] `construction/signing-up-and-joining/functional-design/functional-spec.md`
  — § 2 W1 and W2 (the signup path a smoke step would drive), § 5 (the migration)
- [upstream] this stage's `infrastructure-specification.md` — the gaps table
- [code] `.github/workflows/check.yml`, `deploy.yml`, `Makefile`, read 2026-10-23

---

## Build and test pipeline (`check.yml`)

Two jobs, split so a Kotlin build does not gate a backend PR, with
concurrency groups and `cancel-in-progress` on checks.

### `backend` — 10-minute timeout

| # | Stage | Blocking | D1's relationship |
|---|---|---|---|
| 1 | History depth assertion | **Yes** | Inherited |
| 2 | Secrets scan (Gitleaks) | **Yes**, no severity threshold | Inherited |
| 3 | Install from the lockfile | **Yes** | Inherited |
| 4 | Lockfile is current | **Yes** | Inherited |
| 5 | Dependency CVEs | **No** — annotates | Inherited |
| 6 | `make check` | **Yes** | **Where every D1 test lands** |

### `android-unit` — 15-minute timeout

| # | Stage | Blocking |
|---|---|---|
| 1 | Kotlin money boundary (`NoFloatingPointTest`) | **Yes** |
| 2 | Kotlin format (spotless) | **Yes** |
| 3 | Kotlin static analysis (detekt) | **Yes** |
| 4 | Android Lint | **Yes** |
| 5 | Kotlin coverage ratchet | **Yes**, no decrease |
| 6 | Report upload | No |

The Android release gates — the merged-manifest permission allowlist, the
minified-release DEX scan, and the download-size assertion — live in
`release-android.yml` and are unchanged by D1 [NFR2.1, NFR2.2].

### What `make check` actually runs

`lint → typecheck → test → android → android-quality`, so one command is the
whole gate. For D1 specifically:

| D1 obligation | Lands in | Requirement |
|---|---|---|
| Adversarial lens test (must fail first) | `test` | NFR23.2 |
| Acceptance transition tests, test-first | `test` | NFR23.1 |
| `address` privacy-set membership | `test` | BR3.4, NFR14.25 |
| Schema-wide teacher-lens invariant | `test` | NFR14.25 |
| Authorization **branch** coverage | `test` | NFR23.3 |
| Removability and dormancy predicates | `test` | BR7.1, BR7.2 |
| `app.authz` strict typing | `typecheck` | — |
| OpenAPI schema diff | `test` | — |

**No new pipeline stage, and that is the point.** The one-command property is
what the team practice calls the single most important property of the gate
for a solo build: a gate reproducible only by pushing is a gate that gets
bypassed.

### Two gates worth naming, because D1 extends what they protect

**The Gitleaks precondition assertion.** Step 1 asserts the clone has real
history *before* the scan runs, because Gitleaks reports "no leaks found in
partial scan" after reading zero bytes in a shallow clone. The workflow's own
comment puts it exactly right: a scanner whose clean verdict can come from an
empty scan is one commit of upstream behaviour away from passing while
checking nothing.

That habit is the model for the obligation this project recorded on
2026-10-22 — assert a suite's precondition held before reading its pass as
evidence. D1 inherits the habit directly: its privacy-boundary tests run
against a real PostgreSQL container as a **restricted non-superuser role**,
and a meta-test asserts `current_user` is not a superuser and row-level
security is in force before the privacy suite runs. A superuser bypasses RLS
entirely, so without that assertion D1's strongest test would certify nothing.

**The lockfile check.** `requirements.txt` is an *output*, compared against a
fresh compile; the Makefile's comment notes that hand-editing it to turn a red
check green inverts the control. D1 adds no dependency, so this is inherited
unchanged — and it is the precondition that makes the CVE annotation report on
the build rather than on a version range.

---

## Deploy pipeline (`deploy.yml`)

**Explicit dispatch, never on merge.** Three jobs, each environment-gated. The
dispatch model is what lets a deploy be scheduled outside Bangladesh classroom
hours rather than firing whenever a branch merges [NFR18.2].

| Job | Timeout | Environment | Role |
|---|---|---|---|
| `plan` | 15 min | `<env>` | Validate config; print what is about to be applied |
| `infrastructure` | 45 min | `<env>-infra` | Terraform init, plan, apply |
| `release` | 30 min | `<env>` | Build, push, roll the ASG, verify |

`concurrency: cancel-in-progress: false` on deploys — correctly, because
cancelling a deploy mid-roll leaves an ASG in an unknown state.

### The release job's shape

| Step | What it gives D1 |
|---|---|
| What identity is being presented | OIDC, not long-lived keys |
| Is this commit already built? | Idempotent re-deploys |
| Build and push | SHA-tagged, immutable registry |
| Record the deployment state | |
| Roll the instance | Recreate-style refresh |
| **The API responds** | SSM to the new instance: provisioning log + `curl /health`, fails the deploy on no answer |

### Properties D1's migration depends on

| Property | Why D1 needs it |
|---|---|
| Migration runs before the new container serves traffic | NFR19.1 |
| The SHA tag **is** the artifact | A rollback is a redeploy, not a revert [NFR19.1] |
| ECR tags immutable | What makes the previous tag still mean what it meant |
| The database is not on the instance | An ASG refresh replaces compute and leaves data alone |

**That last row is load-bearing and was nearly the opposite.** `enable_rds`
defaults to `true` and its description records why: with the database in a
container on a root EBS volume with `delete_on_termination = true`, **every
deploy would have wiped it**. D1's migration is the first to touch live rows
under the old model's data, so it is the first unit for which that decision
has consequences rather than just being correct.

---

## The one deploy-side gap D1 is implicated in

**The post-deploy check is `/health`, not the named smoke set.**

| | Exists | Named by the practice |
|---|---|---|
| Process up, database reachable | **Yes** — `curl /health` over SSM | ✓ |
| OTP issue and verify against the real gateway | **No** | ✓ |
| Authenticated lens resolution | **No** | ✓ |
| One read of a fee cycle | **No** | ✓ (D3's data) |

`/health` proves the process answers and the database is reachable. It does
not prove a person can sign up, receive a code, verify it and reach their
batch list — which is **exactly what D1 builds**.

So D1 is the unit that makes the difference between those two visible, and it
is also the first unit able to close part of it: signup, OTP issue and verify,
and authenticated lens resolution are all D1's path. The fee-cycle read is
D3's and waits for D3.

**Recommendation, not a decision taken here:** extend the existing step to
drive the signup path end to end against staging's sandbox gateway
credentials. It is an extension of a step that exists, not a new stage.

The path it would drive is already written down: `functional-spec.md` § 2's
W1 is signup with no prior seat, through the already-added lookup, the
ceilings, the one-transaction create, the OTP trigger, and the fork at step 11
where a teacher reaches an empty batch list and an unaccepted student reaches
no lens. A smoke step that exercises W1 to that fork proves exactly what
`/health` cannot.

---

## Rollback

| Scenario | Procedure | Reversible? |
|---|---|---|
| Bad application code | Re-dispatch with the previous SHA tag | **Yes**, fully |
| Failed health check | Deploy fails; the ASG keeps the prior instance | Yes |
| Bad migration | **Not by rollback** — the schema does not revert with the tag | **No** |

**The additive migration is what makes the first row true for D1, and the
claim rests on a premise worth stating rather than assuming.**

Redeploying the old tag is a complete application rollback against the new
schema **because the previous image's ORM models do not declare the new
columns**. SQLAlchemy selects the columns a mapped class declares, so the old
image never names `student_decision`, `guardian_decision` or
`profile.address` in any query — it is not tolerating unknown fields, it is
unaware of them. The columns are `NOT NULL` after the backfill and carry no
default, which affects **inserts**: the old image's `INSERT` statements name
neither column and would therefore fail.

So the precise property is: **the old image reads safely and cannot create an
enrollment or profile.** For a rollback that is sufficient — the point of
rolling back is to stop new behaviour, and D1's own write paths are what is
being rolled back. It is not sufficient to run the old image indefinitely on
the new schema.

Three conditions would each break this, and none applies to D1's migration:
a column that is `NOT NULL` with no default **on a table the old image
inserts into on its ordinary paths**; a renamed or dropped column; a changed
type. Recorded because none of it is visible in the pipeline configuration —
it lives in the migration's shape.

**The third row is why NFR19.3's verification half matters** [see
`infrastructure-specification.md` gaps]. Rollback does not undo a migration,
so the backup taken immediately before it is the only floor. RDS automated
backups cover the data; nothing asserts a recoverable one exists at that
moment.

---

## Assumptions & Open Questions

- **Assumed**: D1 adds no CI stage and no Terraform change, so neither the
  pipeline's timeouts nor the budget guard's estimate move.
- **Assumed**: staging holds the gateway's sandbox credentials, which is what
  would make a signup smoke step safe to run there.
- **Open, and the human's**: whether D1 extends the post-deploy check to its
  own signup path now, or leaves `/health` as the gate until a later unit.
- **Open, and the human's**: whether a snapshot-and-assert step precedes the
  migration step on the production deploy.
