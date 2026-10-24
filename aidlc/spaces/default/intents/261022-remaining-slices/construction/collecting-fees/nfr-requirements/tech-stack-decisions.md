# Tech Stack Decisions — D3 `collecting-fees`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **D3 makes one genuine technology choice, and it is the first in several
> units.** D1 and D2 selected nothing. D3 must run code on a schedule, and
> this product has no scheduler of any kind.
>
> Everything else D3 needs is already in the stack and already exercised. The
> arithmetic it is built around is the most thoroughly built part of the
> codebase.

## Sources

- [upstream] `aidlc/spaces/default/codekb/shikkhok-plus/technology-stack.md`
- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  §§ 3, 10
- [upstream] `construction/collecting-fees/functional-design/entities.md`
- [prior] `inception/contract-design/contract-summary.md` § D, § G
- [team] Deployment and Code Style practices, 2026-10-22
- [code] `Dockerfile:81`, `pyproject.toml:118-190`, `app/money/`,
  `android/coverage-floor.txt`, read 2026-10-23

---

## 1. What D3 uses

| Layer | Technology | D3's use | New? |
|---|---|---|---|
| API | FastAPI 0.143.5 | New fee and payment routes, **with declared error responses** | no |
| Schemas | Pydantic 2.14.1 | The existing annotated `Money` type, reused | no |
| Query | SQLAlchemy 2.1.5 | `ON CONFLICT DO NOTHING`, grouped fetch by `enrollment_id.in_(...)` | no |
| Database | PostgreSQL 16 | **Four new tables**, one unique constraint, `NUMERIC(12,2)` | migration |
| Money | `app/money/` | `derive()`, `carry_forward()`, `apply_credit()` — reused, not reimplemented | no |
| Scheduling | **see § 2** | The daily generation job | **yes** |
| Push | FCM | The adapter, **owned here and shared with D4** | **yes** |
| Client | Compose, Kotlin 2.0.21 | Fee, payment and verification screens | no |
| Tests | pytest, testcontainers, Hypothesis | Real PostgreSQL 16, barrier-released threads, the property test | no |

**Four new tables is this record's largest schema change**, and the only one
of the six remaining units that adds a scheduled surface.

---

## 2. The one real decision: how the daily job runs

**There is no scheduler in this product.** I searched `app/`, `infra/`,
`.github/workflows/` and the `Makefile` for cron, APScheduler, Celery or any
scheduling library and found none; the single `cron` match is unrelated
(`infra/modules/cdn/main.tf`). `Dockerfile:81` runs `uvicorn app.main:app` and
nothing else.

**What makes this choice easy is a reliability property established
elsewhere**: the job's correctness does not depend on running exactly once
[NFR6.39]. It may run twice, overlap itself, or miss three days, because the
unique constraint is the lock. So no option needs leader election, distributed
locking or exactly-once delivery — which removes the usual reason to reach for
a heavy scheduler.

| Option | Cost | Fit |
|---|---|---|
| **A host-level cron entry invoking a management command in the running container** | Zero recurring cost; one line of host configuration | Runs on the host that already exists. The command is also runnable by hand, which is what makes a missed run recoverable by a person as well as by the next run |
| In-process (APScheduler) inside the API container | Zero recurring cost; one dependency | Ties job execution to a web worker's lifecycle and runs once per worker — harmless here, but it makes "did it run?" harder to answer, which is exactly NFR25.9's question |
| A managed scheduler (EventBridge → a second compute target) | Recurring cost, new IAM, new compute | Correct at a larger scale and unjustifiable against the USD 50/month ceiling [OC-4] for a job this forgiving |

**Recommendation: the host-level cron entry invoking a management command**,
with the command written as an ordinary entry point that takes no arguments
and is safe to run at any time.

Two properties decide it rather than cost, since the first two options cost
the same:

1. **The job must be runnable by hand.** The recovery procedure for NFR25.9 —
   generation has not run for 48 hours — is for a person to run it. An
   in-process scheduler has no such handle.
2. **"Did it run?" must be answerable from outside the application.** A cron
   invocation produces an exit status and a log line in a place that is not the
   application's own logs, which is what makes the absence-of-success alert
   observable rather than circular.

**This is a recommendation, not a fait accompli**: it is the first new
operational surface in the product and the human may reasonably prefer the
in-process option for having nothing outside the container. The reliability
and observability requirements hold either way — NFR6.39, NFR25.9 and
NFR26.3 are stated against the job, not against its scheduler.

### The deploy model constrains the cron option, and the constraint is not optional

**The instance is replaced on every deploy.** `deploy.yml`'s rollout step
refreshes the ASG so the new instance re-runs `user_data`, deliberately —
"a refresh exercises the same path a replacement takes after a failure, so
the self-healing boot is tested on every deploy rather than only on the day
it matters." `infra/modules/app/main.tf:331-333` pins the group at
`min_size = max_size = desired_capacity = 1`.

So **"a host-level cron entry" means an entry installed by
`user_data.sh.tftpl`, not one added by a person over SSM.** A hand-added
entry is wiped by the next routine deploy, and because generation
self-heals, nothing looks wrong until nobody has been billed since the
deploy. That is NFR25.9's failure mode reached by a second route, and it is
the route a reasonable operator would take by default. If the cron option is
chosen, the entry is Terraform-managed infrastructure and the requirement is
not satisfied by an operator action.

**The absence of double-firing risk depends on `desired_capacity = 1`.** At
one instance neither option can fire twice. If that capacity is ever raised,
both options fire once per instance, and the only thing between that and
double-billing is the `(enrollment_id, period)` unique constraint with
`ON CONFLICT DO NOTHING`. That is the correct safety net and it is why the
guarantee is specified against the constraint rather than against the
scheduler's uniqueness [NFR19.8] — but it should be a stated property rather
than a happy accident, because a capacity change is an infrastructure edit
that would not otherwise prompt anyone to think about billing.

---

## 3. The FCM adapter — owned here, shared with D4

| Decision | Detail |
|---|---|
| **Owner** | D3, per OQ-4's answer. The adapter's Unit was latent between U6 and U7, whichever was built first; U7 is D3's ancestor, U6 maps to D4, and D3 is built first |
| **D4's relationship** | **Consumes the same adapter**, never builds a second one. The failure OQ-4 names is two adapters with two different `UNREGISTERED` behaviours |
| **Placement** | Shared infrastructure beside the SMS gateway client, **not** inside the fee feature that happens to be its first caller |
| **Behaviours** | Best-effort, post-commit, failure logged and not surfaced, `UNREGISTERED` deletes the stored token, no device or advertising identifier [NFR19.19–NFR19.23, NFR11.2] |

**The placement decision follows from the ownership, not from taste.** An
adapter living in `feature/fees` is one that D4 will copy rather than import,
which produces exactly the two-adapter outcome OQ-4 exists to prevent. The
SMS gateway client is the built precedent for where a third-party adapter
goes in this codebase.

---

## 4. `Money.format(locale)` — the one addition to the money module

The method **does not exist** in `app/money/_money.py` today. D3 is the first
unit that renders money, so it becomes blocking here.

| Decision | Detail |
|---|---|
| **Digits** | **Latin, even under a Bangla locale** [BR6.6] |
| **What `locale` governs** | Grouping and the currency mark — **not** the digit set |
| **Why** | The client already settled it: `Numerals.kt` states that numbers the app shows are Latin and text people typed is shown as typed. The server must **agree**, not decide independently |

**Had this gone the other way, the same amount would render in two digit sets
depending on which surface drew it** — the server's formatted string on one
screen and the client's formatter on another. That is the failure this
decision forecloses, and it is why the decision is recorded as agreeing with
an existing rule rather than as a fresh choice.

**The addition stays inside the strict island.** `app.money.*` is `strict = true`
with `disallow_any_explicit = true`, the module imports nothing but `decimal`
and its own value types, and `Money.format` must not change that: it takes a
locale value and returns a string, with no I/O, no session and no HTTP. That
constraint is what keeps 100% branch coverage reachable.

---

## 5. Strict islands

| Module | State |
|---|---|
| `app.money.*` | Strict, built. D3 adds `Money.format` **inside** it |
| `app.authz.*` | Strict, built (configured at `pyproject.toml`, the drift the practice file recorded is closed) |
| `app.schemas.*` | Strict, built |

| Decision | Detail |
|---|---|
| **Does D3 need a fourth island?** | **No.** Its authorization lives in `app.authz` and its money in `app.money`, both already strict. `app.fees` would hold orchestration — the I/O-shaped code the global baseline already covers |

**That is a decision, not an omission.** The practice names three islands and
D3 is the first unit since they were settled that could plausibly want a
fourth; declaring one for a module that is mostly session handling would make
the island boundary about package age rather than about what the strictness
protects.

---

## 6. Test tooling, unchanged and newly exercised

| Tool | D3's use | New? |
|---|---|---|
| testcontainers, PostgreSQL 16 | Required, not optional: `ON CONFLICT DO NOTHING`, `NUMERIC(12,2)` and the unique constraint are the behaviours under test and SQLite emulates none faithfully | no |
| Real threads from a barrier | The concurrency obligation, following `tests/auth/test_ceilings.py:283` | pattern reused |
| Hypothesis | The ledger invariant property test, already built | no |
| `pytest-cov`, `fail_under = 100` | The money module's floor, already at 100.00% | no |
| Kover | The Kotlin ratchet, currently **48.52** | no |
| SQLAlchemy event hooks | **Newly used**, for the statement-count assertions [NFR20.18] | pattern new |

**The statement-count assertion is the one new test pattern.** It is how the
N+1 requirement gets a verifier that is not a flaky latency assertion, and
like the barrier pattern before it, it is worth establishing once in a way
D5's dues query can copy.

---

## 7. What D3 adds no technology for

| Need | Why nothing is added |
|---|---|
| A payment gateway | There is none. A claim is an assertion that money moved out of band, verified by a teacher |
| A rollup or cache | ADR-002 names a materialized rollup as the mitigation **if** the fold bites; the arithmetic says it does not in V1 [NFR20.14] |
| A metrics backend | Phase 1's budget carries none, and D3's metrics are low-cardinality counts or plain queries over its own tables |
| A job queue | The push adapter is best-effort with no retry queue in V1 [NFR19.23], and the generation job needs none [NFR6.39] |

---

## Assumptions & Open Questions

- **Assumed**: the period type is a plain `YYYY-MM` string rather than a date
  or a custom type. `entities.md` fixes this — fixed width, sorting lexically
  in chronological order, and it is the opaque key the money module folds on,
  which is what keeps calendar knowledge out of `app/money`.
- **Assumed**: the four new tables need no new library for the append-only
  constraint. It is expressed as a rule plus tests plus a restricted role, not
  as a database trigger — consistent with how the rest of this codebase
  enforces structure.
- **Open, and the human's**: the scheduler choice in § 2. A recommendation is
  recorded with its reasoning rather than a decision taken, because it is the
  first operational surface added to this product and it changes what the
  person has to operate.
- **Open, and not D3's**: Schemathesis remains the outstanding conformance half
  of the API testing story, still unassigned by deliberate decision. D3 adds
  the most new routes of any remaining unit and is the first with declared
  error responses — which is exactly what it would check.
