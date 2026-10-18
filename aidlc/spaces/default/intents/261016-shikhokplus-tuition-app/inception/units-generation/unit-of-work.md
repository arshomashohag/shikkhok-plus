# Units of Work

**Stage**: units-generation (2.7)
**Phase**: Inception
**Depth**: Comprehensive

> This artifact describes **what each Unit is**. The dependency topology is in
> `unit-of-work-dependency.md`. Neither names a build order or a critical path —
> those are Delivery Planning's (2.9) economic decisions, taken with this DAG as
> input.

## Sources

- [upstream] `inception/domain-design/components.md` — 10 components, 24 entities
- [upstream] `inception/domain-design/decisions.md` — ADR-001..ADR-008
- [upstream] `inception/requirements-analysis/requirements.md`
- [upstream] `inception/user-stories/stories.md` — 45 stories
- [upstream] `ideation/scope-definition/intent-backlog.md` — PU-1..PU-8
- [team] the affirmed Walking Skeleton and Way of Working practices

---

## The decomposition shape

**Vertical by default, split in four places.** Each feature Unit (U3–U9)
carries its backend endpoints, its Android screens and its tests together. Four
Units are not feature slices because the thing they deliver is not one: a money
library below the graph, an API contract beside it, release packaging off to one
side, and the governance join at the end.

Three forces decided this against a split-by-surface alternative:

- **The affirmed Walking Skeleton is one Unit by definition.** `team.md` binds
  the skeleton to "a Compose screen that calls a real FastAPI endpoint, which
  reads a real PostgreSQL row, through real OTP-issued authentication, running
  against the real Phase 1 Lightsail host. Not a mock at any layer." A
  backend/client split puts the skeleton across two Units, and `org.md` says the
  first Unit **is** the smallest working integrated slice — singular.
- **One reviewer, per-Unit checkpoints, and the Android surface is the declared
  weak spot [OC-3].** A backend-only checkpoint can be reviewed against a test
  suite and a schema diff, never against behaviour; its paired UI Unit then
  arrives later carrying all the integration risk and none of the context. That
  is the worst place to put the hardest-to-review surface.
- **The client holds no business logic [TC-9, D-31].** A vertical Unit here is
  not two peer halves; it is a service whose last mile is a rendering surface.
  That is why `service` is the honest `kind` for U3–U9 rather than a compromise.

**The `ui` kind is deliberately unused.** It was considered and rejected: a `ui`
Unit is a frontend surface that is a deliverable in its own right, and under
[TC-9, D-31] no such surface exists here — every screen renders a decision the
server already made, so there is no Unit whose substance is the client. Typing
any of U3–U9 as `ui` would misdescribe it, and typing a Unit twice is not
available. The per-Unit UI obligations below carry what a `ui` kind would
otherwise have demanded.

## Unit catalogue

| Unit ID | `name` | Directory | Kind | Complexity | Deployment model |
|---|---|---|---|---|---|
| U1 | `money-core` | `u1-money-core` | `library` | M | In-process Python package in the backend image; Kotlin `Money` value class ships in the app. No independent deployment. |
| U2 | `api-contract` | `u2-api-contract` | `spec` | S | Not deployed. Build-time artifact and CI gates, consumed by both surfaces. |
| U3 | `identity-and-access` | `u3-identity-and-access` | `service` | XL | One FastAPI container on the Lightsail host; Android feature package in the single `:app` module. |
| U4 | `batches-and-enrollment` | `u4-batches-and-enrollment` | `service` | L | Same container, same app module. |
| U5 | `sessions-and-attendance` | `u5-sessions-and-attendance` | `service` | L | Same container, same app module. |
| U6 | `exams-and-marksheets` | `u6-exams-and-marksheets` | `service` | M | Same container, same app module. |
| U7 | `fee-cycles-and-ledger` | `u7-fee-cycles-and-ledger` | `service` | L | Same container; the generation job is a scheduled process in the same image. |
| U8 | `payment-claims-and-verification` | `u8-payment-claims-and-verification` | `service` | L | Same container, same app module. |
| U9 | `teacher-insights` | `u9-teacher-insights` | `service` | M | Same container, same app module. |
| U10 | `release-packaging` | `u10-release-packaging` | `packaging` | M | Produces the signed AAB; ships through Play internal then closed testing. |
| U11 | `privacy-and-governance` | `u11-privacy-and-governance` | `spec` | L | Manifests and purge job in the backend container; the external deletion route is a public FastAPI route; policy and forms are Play submissions. |

**Deployment model, stated once.** Every backend Unit deploys as part of **one
FastAPI container** — a modular monolith — behind one Lightsail instance, with
Alembic run as a distinct logged step before the container serves traffic. Every
Android Unit is a **feature package inside the single `:app` Gradle module**.
ADR-007 and ADR-008 keep components separate as *code* boundaries — import
rules, distinct writers, distinct APIs — and no ADR asserts independent
deployability, so one image violates nothing. The USD 50/month ceiling [OC-4]
forbids anything else: a second always-on service would consume the budget
before compute.

---

## Unit responsibilities

### U1 `money-core` — `library`, M

The `Money` value type, the single declared rounding mode, both serialization
chokepoints (the annotated Pydantic type and the SQLAlchemy `TypeDecorator`),
the import-boundary checks, 100% branch coverage and the ledger property test.

Extracted rather than buried in a fee slice because `team.md` already defines it
as having no I/O, no session and no HTTP, and says so in as many words: "the
money module is consequently buildable and fully testable before any endpoint
exists." It is the one component with a genuinely clean `library` kind and the
most reviewable isolated artifact in the project.

*Implementation notes.* The ledger identity it must satisfy is ADR-002's
verified form: `total_charged − total_forgiven − (total_receipt +
total_credit_grant) == total_outstanding − available_credit`. No money column is
ever cleared by any later deletion path.

### U2 `api-contract` — `spec`, S

The committed OpenAPI 3.1 schema and its schema-diff CI gate, the error taxonomy
and envelope (`code` / `retryable` / `message_key`), the money-as-JSON-string
contract asserted on both sides, the route-enumeration harness with its
`PUBLIC_ROUTES` allowlist, and the schema-wide assertion that no teacher-lens
response carries a profile field.

Carved out because these are **schema-level** properties, not endpoint-level
ones: a per-endpoint privacy test fails to cover the endpoint added in U9 after
everyone stopped thinking about it. `team.md` makes the committed schema a gate
— "a stale committed schema is worse than none, because the contract tests then
pass against fiction" — so it needs an owner.

### U3 `identity-and-access` — `service`, XL — **the walking skeleton**

OTP issue and verify with all seven abuse controls and their adversarial tests,
datastore-backed rate-limit counters, the global daily SMS ceiling with its
per-number and per-IP sub-ceilings and degradation path, JWT `kid` with two
valid verification keys, rotating refresh tokens with reuse detection and family
invalidation, the lens resolver with its RLS context and single entitlement
point, the owner-private profile under row-level security, the append-only auth
audit log, the SMS gateway adapter with its per-purpose budget, the first
Alembic migration applied from zero against a real Postgres, Android OTP entry
via SMS Retriever, the lens switcher, and both language bundles on screen one.

*Implementation notes.* Toolchain arrives here by `team.md`'s explicit
sequencing: Ruff with its named rule sets, mypy on the money module, pytest with
testcontainers, Gitleaks as hook and CI job, dependency lockfiles, detekt and
Kotlin coverage reporting. Deliberately not a separate toolchain Unit.

**U3's migration creates the `Owner` and `Enrollment` tables**, empty, in
addition to its own identity tables. Lens resolution reads all three, and a
query against a table that does not exist fails — empty is not the same as
absent, so the skeleton cannot run end to end without them. U3 reads these two
and never writes them; U4 owns their behaviour and extends their columns. Table
shape only, not an ownership transfer, and not a dependency on U4.

### U4 `batches-and-enrollment` — `service`, L

The `Owner` indirection carrying the subscription anchor, Batch, BatchSubject
and ScheduleSlot, add-student with dormant-account resolution and
attach-to-existing, per-enrollment guardian, fee override, multiple enrollment
across batches, `inactive_from` date semantics, edit and remove, student and
guardian batch lists, guardian child selection, the hide-batch preference, and
Room-cached rosters with staleness.

*Implementation notes.* Establishes the Room read-cache pattern every later Unit
reuses: entities mirror the API DTO one-to-one, carry only `fetched_at`, and
hold no derived field.

### U5 `sessions-and-attendance` — `service`, L

Session instances from weekly recurrence plus ad-hoc, status transitions,
reschedule and cancel, the topic log, the atomic roster write with optimistic
concurrency and the queued-write refuse-on-conflict rule, announcements, the
mid-class Compose path, next-class and topics views for student and guardian,
and attendance visible to student and guardian.

*Implementation notes.* Owns the four-state queue (queued / confirmed / failed /
conflicted) per the amended NFR5.1, and the conflict-resolution screen FR11.5
requires. The mid-class latency obligation [PU-3.6, TC-17] is discharged here by
a Macrobenchmark on a low-end device profile — `team.md` is explicit that a
Compose correctness test does not discharge a performance requirement.

### U6 `exams-and-marksheets` — `service`, M

Exam creation per batch and subject, mark entry with the four result states and
correction history, the batch-scoped marksheet, the `marksheet_visible` toggle,
exam dates, and the guardian progress-over-time view.

*Implementation notes — why this splits from U5 without reopening ADR-008.*
ADR-008 kept Sessions, Exams and Announcements as **one Teaching component**,
rejecting a three-way split because it "would duplicate the ADR-006 concurrency
rule across two of them." U5 and U6 are separate **Units**, which is a delivery
boundary rather than a component boundary — Teaching remains one component, and
its import rules are unchanged.

The duplication ADR-008 feared does not occur, and the entity table is why:
`attendance_version` and `client_mutation_id` live only on `Session` and
`Attendance`, both U5. `Mark` carries `superseded_by_id` — correction history,
which is a different mechanism with a different failure mode. So the
optimistic-concurrency rule has exactly one home (U5) and is not implemented
twice. ADR-008 itself anticipated this, noting the split is "reversible — the
entities are already distinct."

### U7 `fee-cycles-and-ledger` — `service`, L

The append-only `LedgerEntry` with its seven kinds, the thin `FeeCycle` carrying
only the `(enrollment_id, period)` constraint, generation via `ON CONFLICT DO
NOTHING`, calendar-month periods with the short-month clamp, the daily
self-healing job, credit grant and apply, two-sided carry-forward, the
server-computed fee status, and student and guardian fee views.

*Implementation notes.* Mandatory money tests [PU-5.7, TC-20, D-23] are a
deliverable condition of this Unit, not a follow-up. Also establishes the FCM
adapter, `DeviceToken` lifecycle and `ReminderEvent` log, since the fee-due
reminder is the first trigger FR10.4 requires — see the adapter-ownership note
in the dependency artifact.

### U8 `payment-claims-and-verification` — `service`, L

The identical submission form in student and guardian lenses,
batch-to-enrollment-to-open-cycle resolution, partial amounts, the
server-supplied channel list, the pending-verification list, approve /
approve-less / reject, carry-forward-or-waive on partial, over-approval becoming
credit, verifier identity and timestamp, and payment history views.

### U9 `teacher-insights` — `service`, M

Cross-batch dues driven by outstanding balance rather than active status, plus
the four analytics views: monthly earnings, earnings trend, collection rate with
its carry-forward, waiver and credit rules, and next upcoming exam.

*Implementation notes.* This Unit inherits an arithmetic definition that is
annotated **open to correction**: FR8.3's collection rate, and AC8.3.4's rule
that a credit counts in the period whose charge it settles, which postdates it.
The money module's property test should be extended to cover that rule.

### U10 `release-packaging` — `packaging`, M

AAB output, signing config, release and debug flavours, R8 rules surviving
minification, `compileSdk` and `targetSdk` 36, the 15 MB download-size
assertion, the merged-manifest permission allowlist including the absent
`AD_ID` assertion, the minified-DEX forbidden-identifier scan, the Syft SBOM,
and the low-end-device Macrobenchmark profile.

*Implementation notes.* The allowlist and DEX scan arrive here because
`team.md` sequences them to "the first Android release build," which is this
Unit by definition. The ZAP baseline pass runs at this Unit's release gate.

### U11 `privacy-and-governance` — `spec`, L

Governance's two manifests as structured data, the schema-iterating test
asserting every table appears in both, both account-deletion paths (in-app and
the externally accessible route), the idempotent chunked purge, the
privacy-policy text generated from the dispositions, the Data Safety form
content, the Play children's-data and target-audience declarations, and the
deletion-confirmation copy naming what is retained.

Typed `spec` rather than `service` because its load-bearing deliverable is the
declarative manifest pair and the text generated from it — three consumers
reading one source. The endpoints and the purge job are the manifests'
execution, not the Unit's substance. Drift between the published policy and the
implementation is the failure this Unit exists to prevent, which is why the
policy, the form and the declarations are not separately authorable.

---

## Standing per-Unit obligations

Three PU-8 capabilities are **not Units** because they are obligations on every
Unit that adds a screen. A late sweep across forty screens is exactly what the
skeleton's both-bundles-on-screen-one rule exists to prevent.

| Obligation | Applies to | Verifier |
|---|---|---|
| **Bangla and English both present** [PU-8.3, TC-15, D-43] — no hardcoded user-facing strings, layout survives the longest Bangla string | every screen-bearing Unit | Compose screenshot test at the longest Bangla string, or an explicit per-screen manual check |
| **Accessibility and back-stack** [PU-8.4, TC-18] — no colour-only status, correct back stack across lens and child switches, touch targets and content descriptions | every screen-bearing Unit | AC9.4.2 is a **privacy** case wearing navigation clothing: Back must never land in another lens's or another child's data |
| **Low-end device discipline** [PU-8.5, TC-17] | every screen-bearing Unit | the measurable gates (download size, Macrobenchmark harness) belong to U10; the mid-class latency benchmark to U5 |
| **UI layer shape** | every `service` Unit shipping screens | feature package; ViewModel state machine tests for loading, success, error and explicit retry; the response-to-UiState mapping function as the test target; money decoded from a JSON string with loud failure on a number |

Also obligations rather than Units: the mandatory money tests [PU-5.7] are a
deliverable condition of U1 and U7; the Room read-cache pattern [PU-2.14] is
established in U4 and reused; the five cross-component invariants are standing
CI gates owned by U2 (schema-wide and route-enumeration), U1 (money import
boundary) and U11 (every table in both manifests).

---

## Assumptions & Open Questions

- **U3 is XL and has not been trimmed.** `team.md` already states the skeleton
  is deliberately larger than a minimal connectivity proof and accepts the
  trade. Reducing it is a change to an affirmed practice, which belongs at the
  learnings gate, not in a decomposition.
- **U11 is terminal in the DAG and release-blocking** [D-41, RC-4, RC-5]. That
  tension is real and belongs to Delivery Planning, not here. One option it may
  want: each Unit declares its own tables' dispositions as it creates them, with
  U11 as the completing join and the schema-iterating test as the gate. Not
  encoded as an edge, because it is a sequencing strategy rather than a topology
  fact.
- **FR8.3's collection-rate definition remains open to correction**, and
  AC8.3.4's credit rule postdates it. U9 inherits it as a known-unsettled
  definition. A requirements question, not a decomposition one.
- Carried in from Domain Design: whether `PaymentClaim.transaction_id` survives
  the claimant's deletion. A product and legal judgement; U11 implements
  whichever answer lands.
