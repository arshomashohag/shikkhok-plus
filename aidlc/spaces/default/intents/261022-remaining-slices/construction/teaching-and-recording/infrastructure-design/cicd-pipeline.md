# CI/CD Pipeline — D4 `teaching-and-recording`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **D4 adds no stage, no job and no workflow. Its work lands in `check.yml`
> and `deploy.yml` as they are.**
>
> Three things are worth a reader's attention anyway. The pipeline is in
> considerably better shape than the team practice describes — **the lockfile,
> CVE and Kotlin-toolchain gaps `team.md` records as open are closed**, which I
> verified by opening the files. The one precondition assertion it names is
> still missing, and it is the one that matters most to this unit: **nothing
> checks that the integration suite actually ran**, and D4's six tables are
> tested almost entirely there. And `deploy.yml` advertises a migration control
> it does not have.

## Sources

- [upstream] `construction/teaching-and-recording/nfr-design/reliability-design.md`
  § 9 — the migration, forward-only and rehearsed; § 3, the queue's tests
- [upstream] `construction/teaching-and-recording/nfr-design/security-design.md`
  §§ 1.3, 6.3 — the two obligations a new table carries, and the built
  verifiers for each; § 2, the probe matrix the suite gains
- [upstream] `construction/teaching-and-recording/nfr-design/observability-design.md`
  §§ 3.2, 4.1 — the counters and the freshness test shape
- [upstream] `construction/teaching-and-recording/nfr-design/scalability-design.md`
  § 2.6 — why a sequential concurrency test establishes nothing
- [upstream] `construction/teaching-and-recording/nfr-design/performance-design.md`
  § 2 — statement count, verified in the suite rather than monitored
- [upstream] `construction/teaching-and-recording/nfr-design/logical-components.md`
  §§ 5, 6.3 — what must not erode, and the gaps handed forward
- [upstream] `construction/teaching-and-recording/nfr-requirements/tech-stack-decisions.md`
  — NFR17.4–NFR17.8, test tooling and the screen-check obligation
- [upstream] `construction/teaching-and-recording/functional-design/functional-spec.md`
  §§ on the attendance and marks paths a smoke step would drive
- [upstream] `inception/domain-design/components.md` — the component
  catalogue, to which D4 adds no deployable
- [prior] D3's `collecting-fees/infrastructure-design/cicd-pipeline.md` — the
  smoke gap and the staging gap this unit inherits
- [code] `.github/workflows/check.yml`, `.github/workflows/deploy.yml`,
  `Makefile`, `tests/conftest.py`, `android/build.gradle.kts`,
  `requirements.txt`, `android/gradle.lockfile`,
  `gradle/verification-metadata.xml`, `.security-exceptions.md`,
  `.github/dependabot.yml`, `infra/modules/app/user_data.sh.tftpl`,
  read 2026-10-24

---

## 1. Where D4's work lands

**No new stage, no new job, no new workflow.**

| Stage | Trigger | D4's change |
|---|---|---|
| `check.yml` → `backend` | Every push | **More tests, same command** |
| `check.yml` → `android-unit` | Every push | D4's seven screens and their mapping functions |
| `deploy.yml` → `plan` | Manual dispatch | none |
| `deploy.yml` → `infrastructure` | Manual dispatch | **A `user_data` diff — the cron entry** [spec § 3.1] |
| `deploy.yml` → `release` | Manual dispatch | none; the image is built the same way |
| Migration | **Boot only** — § 3 | **Six new tables through the existing step** |
| Rollout | ASG instance refresh | none |
| Post-deploy | `curl /health` over SSM | **Should extend — § 5.2** |

### What `make check` runs for D4

`make check` is `lint typecheck test android android-quality`, the same
entrypoint locally and in CI — the property this project treats as the most
important in a solo build, and it is intact.

| Gate | D4's addition |
|---|---|
| `ruff format --check` / `ruff check` | D4's modules; the banned-api rule on raw `decimal` already covers them, stated over paths |
| `mypy app` | D4's modules, including its new authorization code, which lands inside the already-strict `app.authz.*` island — § 2.3 |
| Money coverage, 100% branch | **D4 touches no money code**; the floor must not move |
| Backend floor, 80% line | D4's services, routes and the generation job |
| Import gates | D4 adds none of its own; `logical-components.md` § 5 is enforced by what exists |
| Schema-diff gate | **D4's endpoints and declared error responses change `openapi.json`** |
| **Governance tests, both directions** | **Fail until all six tables carry a disposition** — § 2.1 |
| **Reachability tests** | **Fail until all six tables are granted** — § 2.1 |
| Android: spotless, detekt, lint, coverage ratchet | D4's screens, against a ratchet that is now armed |

---

## 2. The gates D4 will trip, and why that is the system working

### 2.1 Two obligations per new table, one of them silent

`security-design.md` § 6.3 states the pair and it is the single most useful
thing to carry into Code Generation:

| Obligation | Verifier | Fails where | Failure mode |
|---|---|---|---|
| A `TableGovernance` entry | `tests/db/test_governance.py`, both directions | `make check` | **Loud** |
| An explicit `GRANT` to `APP_ROLE` | `test_the_restricted_role_can_read_every_live_table` | `make check` | **Loud now, silent historically** |

**Both are built. D4 specifies no new test for either**, which is the point of
recording them: the natural instinct at six-new-tables is to write a
reachability test, and it would duplicate `tests/db/test_governance.py:171`
and `:191`.

**The second row's parenthetical is the part worth knowing.** An ungranted
table is invisible to the restricted role in `information_schema`, so before
those assertions existed a missing grant **narrowed every other governance gate
without failing any of them** — `0002`'s docstring records exactly that
happening. The tests convert a silent narrowing into a loud failure, which is
why the right move is to add D4's six names to the migration's `NEW_TABLES`
tuple and let the existing gates do their work.

### 2.2 The integration suite is where D4 is actually tested, and nothing asserts it ran

**This is the inherited gap that matters most to this unit.**

`tests/conftest.py:32-48` skips the integration suite at module level when no
Docker daemon is reachable. The skip itself is reasonable and deliberately
loud in `make check`'s sibling targets. **What is missing is the precondition
assertion `team.md` assigns**: CI asserting Docker was present and the
integration suite actually ran. I searched `.github/workflows/check.yml` for
such a step and found none — the `backend` job runs `make check` with no
assertion that the database half executed.

**Why D4 escalates it.** Almost everything this unit guarantees is tested
against a real PostgreSQL:

| D4 guarantee | Tested where |
|---|---|
| Six governance rows, both directions | Integration — reads the live schema |
| Six grants to the restricted role | Integration — reads as the restricted role |
| `UNIQUE (submitted_by_account_id, client_mutation_id)` [NFR19.33] | Integration — the constraint must fire |
| `UNIQUE (session_id, resulting_version)` [BR3.4] | Integration |
| The conditional-update concurrency guarantee [NFR6.44–NFR6.47] | Integration, **and concurrent** — § 2.4 |
| `ON CONFLICT DO NOTHING` generation idempotency [NFR6.51] | Integration |
| The lens probe matrix [NFR14.48–NFR14.49] | Integration |

**A runner without Docker would report a green `make check` having run none of
them.** That is not hypothetical for this unit: it would pass D4 with its
constraints unexercised, its grants unverified and its privacy probes unrun,
signalling only a pytest skip line in a log nobody reads.

**Cost to close: one step.** Assert `docker info` succeeds before `make check`,
or assert a non-zero integration test count after it. **Assigned by `team.md`
to "before D1" and not delivered; D4 is where its absence would do the most
damage.** This document does not add the step — it is not D4's to add
unilaterally — but it records that D4's test obligations rest on it.

**Verifier for the assertion itself: none exists today.**

### 2.3 `app.authz` IS a strict island, and D4's new code inherits it

**Corrected 2026-10-25 after review.** An earlier draft of this section said
the island was unconfigured and named it an open item for the human. That was
wrong, and it was wrong in this project's most-warned-against way: it asserted
the state of built code from a stale secondary source rather than from the
file. `pyproject.toml:222-226` sets `strict = true` and
`disallow_any_explicit = true` on `app.authz.*`, added **2026-10-22** — two
days before this stage's own stated evidence date.

The source of the error is worth naming, because it will mislead the next
stage too: **`team.md`'s Code Style section still carries the drift note**
("`app.authz` is a declared strict island and was never configured ... Assigned
to: before D1"), and that note reaches every stage through the rule bundle. It
describes work that was then done. It is a learnings-gate matter, listed in
§ 6 with the other two stale-practice items.

What this means for D4 is the opposite of an open item: **D4's new
authorization code lands inside an island that is already strict**, so
`disallow_untyped_calls`, `no_implicit_reexport` and `warn_return_any` apply to
it from its first commit. That matters here because D4 is lens-heavy — six
readers across four routes at one boundary [security § 2.2], plus the
authorization-before-version-check ordering that prevents a roster reaching a
stranger in a 409 body [security § 5.4].

**Nothing to do, and no pipeline change.** `mypy app` already enforces it.

### 2.4 The concurrency tests must be concurrent

`scalability-design.md` § 2.6 is explicit and the project rule behind it is
already affirmed: **a sequential test establishes nothing** about a guarantee
that exists because application-level guards fail under concurrency.

D4 has **three** separate concurrency guarantees, not one:

| Guarantee | Shape of the test |
|---|---|
| The attendance version conditional update [NFR6.44, NFR6.46] | Overlapping submissions against one session; assert exactly one applies |
| Replay under concurrency [NFR6.50] | The same `client_mutation_id` twice, overlapping; assert one row, one increment, **`created_at` unmoved** |
| Generation idempotency [NFR6.51, NFR6.52] | Overlapping runs **and** a re-run on a later day |

**The `created_at` assertion is the load-bearing one** in the middle row
[reliability § 5]: a test that merely counts rows passes against an
implementation that overwrites the original in place — right count, right
version, original timestamp destroyed.

**These run in the integration suite**, which returns § 2.2 to the foreground:
all three are among the tests a Docker-less runner silently skips.

---

## 3. The migration path, and an input that does nothing

### 3.1 Where migration actually happens

**It happens at boot and only at boot.** `user_data.sh.tftpl:394-412` runs
`alembic upgrade head` as a distinct logged step that exits non-zero and serves
nothing on failure. Since the rollout replaces the instance, every deploy
migrates before it serves.

**For D4 this means no pipeline change for six tables** [NFR19.46], which is
the second-most useful thing this stage can tell Code Generation after the
cron entry.

### 3.2 Finding: `skip_migrations` is wired to nothing

> **Resolved 2026-10-25, during this stage's review.** The input was removed
> from `deploy.yml`, verified as a single occurrence — its own declaration,
> with no `if:` and no expression anywhere else in the file — so removing it
> changed no behaviour. A comment at `:39` records what it was and why it went.
> **The misleading toggle is gone; the two real gaps below are not closed**:
> there is still no pipeline-side Alembic step and no preview of what is about
> to be applied. Removing a control that did nothing does not supply one that
> does something, and D4's six tables are still migrated only at instance boot.
> The finding as written below is the state the documents were drafted against
> and is kept for the record.

Carried from `infrastructure-specification.md` § 4.2 because this is the
document a dispatcher reads.

I searched all of `.github/workflows/deploy.yml` for `alembic` and `migrat`:
the only matches are comments at `:21` and `:414` and the input's own
description at `:40`. **There is no Alembic step in any job, and
`skip_migrations` is referenced nowhere after its declaration.**

| What a dispatcher sees | What happens |
|---|---|
| A toggle reading "Skip Alembic (the instance still migrates at boot)" | **Nothing. Either way.** The boot migration runs regardless |
| `team.md`'s "*verified … `deploy.yml` runs Alembic as a separate logged step*" | The step is in `user_data.sh.tftpl` |

**The outcome is safe and the record is wrong**, and for D4 the wrongness is
pointed: six tables is this unit's largest irreversible act, and the control a
dispatcher would reach for to stage it separately does not exist.

**Verifier: none.** A workflow input's description is prose and nothing asserts
it against the workflow's steps — the project's own rule that a stated scope is
a claim [project.md], applied to a workflow input.

---

## 4. What the pipeline already has that the practice says it does not

**Recorded because a stale "absent" is as misleading as a stale number**, and
because `team.md` assigns four controls to "before D1" that are now built. I
checked each by opening the file rather than trusting either source.

| Control | `team.md` says | Verified 2026-10-24 |
|---|---|---|
| Python lockfile | absent | **`requirements.txt`, hash-pinned**, with `make lock` and a CI currency check at `check.yml:115-132` |
| CI installs from the lockfile | absent | **Built** — `check.yml:107`, and the step is no longer mislabelled |
| Gradle locking and checksums | absent | **`android/gradle.lockfile` and `gradle/verification-metadata.xml`** |
| `pip-audit` per push, annotating | absent | **Built**, `continue-on-error`, `check.yml:142-149` |
| Dependabot | absent | **`.github/dependabot.yml`** |
| `.security-exceptions.md` | absent | **Present** |
| ktlint via spotless, detekt | absent | **Both plugins applied**, `android/build.gradle.kts:6-7` |
| `lint.xml` | absent | **`android/lint.xml`** |
| Kotlin coverage ratchet | absent | **`:android:verifyCoverageRatchet` in `make check`** |

**The two-speed CVE model is built as designed**: annotating and non-blocking
per push, blocking at the release gate, with the reasoning preserved in the
workflow comment. **That makes the release checklist's third line checkable for
the first time** — `team.md` notes it "has never been checkable, because
nothing produces dependency findings", and now something does.

**What remains genuinely open** from that list: the **Docker precondition
assertion** (§ 2.2), **Schemathesis** (unassigned by choice), and the
**screenshot harness** (§ 5.3). I am not proposing to close any of them in D4;
naming them accurately is the point, and two of the three are repository-wide
rather than unit-scoped.

**The `app.authz` strict island was on this list in an earlier draft and is
not open** — it was built on 2026-10-22 and § 2.3 records why the draft said
otherwise.

---

## 5. Deploy

| Facet | Mechanism | D4's change |
|---|---|---|
| Trigger | **Explicit `workflow_dispatch`**, never on merge | none |
| Inputs | Environment and ref. `skip_migrations` was removed 2026-10-25 [§ 3.2] | none |
| Concurrency | Per environment, **never cancelled mid-run** | none |
| Image | SHA tag, immutable repository, `latest` never deployed | none |
| Terraform | Applied on every deploy; a plan job prints what is about to change | **The cron entry appears here** |
| Migration | Boot only, fails closed | **Six tables through it** |
| Rollout | ASG instance refresh, re-running `user_data` | **Which is what installs the cron entry** |
| Post-deploy | `curl /health` over SSM | **Should extend — § 5.2** |
| Rollback | Redeploy the previous SHA tag | **Partial for D4 — § 5.1** |
| Auth | GitHub OIDC, no long-lived keys | none |

### 5.1 What a rollback restores, and what it does not

| Unit | What a tag rollback restores |
|---|---|
| D1 | The previous image against additive columns the old image never selects |
| D2 | Everything — no schema moved |
| D3 | The previous image. **Not the charges** |
| **D4** | The previous image. **Not the attendance, and not the marks** |

**The migration is additive** — six new tables, nothing altered — so the
previous application version runs against the new schema and a tag rollback is
a valid *code* rollback.

**What it does not undo is recorded teaching.** Attendance rows and marks are
records of things that happened in a classroom. Rolling back the image leaves
them, correctly: a mark a teacher entered is a fact about a child's work, and
the design already provides the remedy — **corrections supersede rather than
delete** [reliability § 4.2], and submissions are never deleted [NFR24.19].

**D4 differs from D3 in who is affected rather than in degree.** A wrongly
generated charge is a number a teacher can correct. A wrongly recorded absence
is a statement about a child that a guardian may already have seen.

### 5.2 The smoke gap, and what D4 makes newly smokeable

**What exists is `curl /health` over SSM** (`deploy.yml:415-454`), which tests
the container and **deliberately bypasses the path every real user takes.**
D3's § 4.2a records what that cost: three units deployed behind an origin
returning 502 to every CloudFront request, and nothing in the pipeline noticed
because nothing in the pipeline looks. **That origin certificate is now issued
by certbot in `user_data` and the premise that caused it is corrected** — but
the smoke set that would have caught it still does not exist.

| Smoke step the practice names | Buildable before D4? | Now |
|---|---|---|
| Health + migration revision | Yes | Partly built, over SSM rather than through the CDN |
| OTP issue and verify | Yes, since B3 | Still not in the deploy |
| Authenticated lens resolution | Yes, since B3 | Still not in the deploy |
| One read of a fee cycle | Yes, since D3 | Still not in the deploy |
| **One read of a session** | **No** | **Yes** — D4 generates them |

**This design does not add the smoke set**, because four of its five lines are
not D4's and how far to extend it is the human's call. It records that **a
single line through the CDN rather than over SSM is worth more than four lines
over SSM**, which is the lesson the 502 taught rather than a new opinion.

### 5.3 Seven screens and no screenshot harness

[NFR17.8] D4 ships **seven Compose screens**, more than any prior unit, and
there is still **no Paparazzi, no Roborazzi and no screenshot infrastructure of
any kind** — I checked `android/build.gradle.kts` for a screenshot plugin and
found the six listed in § 4, none of them a screenshot tool.

`logical-components.md` § 6.3 names the substitute: **a written per-screen
check at the longest Bangla string.** Its own sentence is the honest one and it
belongs here too: **this is not a verifier of the layout.** Nothing automated
discharges the Bangla layout obligation for these seven screens, and the
per-screen check is a person looking at a screen.

**Both options remain the human's**, as `team.md` records. What this document
adds is the count: three units of screens have now shipped under the same
sentence, and D4 makes it seven more.

### 5.4 Deploy timing

Deploys carrying D4 are scheduled **outside Bangladesh classroom hours**. The
reason is sharper for this unit than any before it: the recreate-style rollout
drops in-flight requests, and a dropped attendance write during a live class is
the specific failure a teacher will not forgive [D-9, TC-8]. **The offline
queue softens this** — a write refused during a restart queues and syncs rather
than being lost [reliability § 1.3] — which is the one place the queue helps
deployment, and it is not a reason to stop scheduling carefully.

**Also outside the generation window**, now two windows rather than one once
D4's cron entry lands [spec § 3.2].

**Verifier: the person dispatching the deploy. Nothing automated prevents a
deploy landing in a class hour or a generation window.**

---

## 6. Secrets in CI/CD

| Secret | Path | D4 |
|---|---|---|
| OTP HMAC key, JWT keys, SMS credentials, FCM credentials | GitHub secret → `runtime.env` → SSM `SecureString` | unchanged |
| AWS access | **OIDC**, no long-lived keys | unchanged |

**D4 introduces no secret of any kind.** It adds no third-party integration,
and the FCM path it uses is D3's, already provisioned. The runtime file is
written under `umask 077` and removed after upload.

**The device queue holds no secret either** — enrollment ids, booleans, a
version number and two UUIDs [security § 7.1] — so no key material reaches the
build, and the existing DEX scan and manifest allowlist are unaffected.

---

## 7. What D4 does not add

| Not added | Why |
|---|---|
| A new workflow, job or stage | The work lands in `check.yml` and `deploy.yml` as they are |
| A deployment strategy change | Recreate-style at one instance; blue/green needs a second host and an ALB |
| A feature flag system | Nothing in D4 needs dark-launching; generation is idempotent and the endpoints are additive |
| A separate migration pipeline | The boot step exists and fails closed [§ 3.1] |
| A benchmark or performance job | **PU-3.6 carries no V1 obligation**; statement count is verified in the suite [performance § 2] |
| New import-boundary checks | `logical-components.md` § 5 is enforced by gates that exist |
| An artifact store change | ECR, SHA-tagged, immutable |

---

## Assumptions & Open Questions

- **Assumed**: the session-generation job ships inside the same image as the
  API, so the release stage is unchanged and the cron entry invokes one
  artifact, as the fee entry does.
- **Assumed**: D4's endpoints and declared error responses change the committed
  `openapi.json`, so the schema-diff gate shows them as a reviewable diff.
- **Assumed**: the Android coverage ratchet absorbs D4's seven screens as D3's
  did; if it drops, the diagnosis is a glob catching a non-composable — narrow
  the glob, never lower the floor [project.md].
- **Open, and the human's**: the Docker precondition assertion [§ 2.2]. It is
  `team.md`'s own assignment, undelivered, and D4 is the unit whose guarantees
  rest most heavily on the suite it protects.
- **Open, and the human's**: whether to wire, remove or replace
  `skip_migrations` [§ 3.2].
- **Open, and the human's**: how far to extend the post-deploy smoke set now
  that a session read is buildable, and whether to move even one line from SSM
  to the CDN path [§ 5.2].
- **Open, and the human's**: the Bangla layout verifier for seven screens
  [§ 5.3] — a screenshot harness, or a written per-screen check that **nothing
  automated discharges**.
- **Not open, corrected after review**: the `app.authz` strict island was
  listed here as the human's call and is in fact built [§ 2.3]. What is open
  is the `team.md` note still describing it as missing, which is one of the
  three stale-practice items for the learnings gate.
