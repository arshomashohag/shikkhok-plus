# Security Requirements — D4 `teaching-and-recording`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **D4 is where the product's children's data actually arrives.** Until now
> the privacy boundary has protected a profile and a fee balance. This unit
> stores **attendance and marks** — a record of where a named child was on a
> given afternoon, and how they performed. That is the data the Families
> declaration, the Data Safety form and RC-1 through RC-3 were written about,
> and D4 is the first unit to hold it.
>
> Three security surfaces are new rather than inherited, and each gets its own
> section: the **anonymised marksheet**, which is a disclosure mechanism rather
> than a view (§ 4); the **marksheet toggle**, which is an authorization
> control on an existing column (§ 5); and the **replay guard**, where a
> malicious replay of another account's `client_mutation_id` must be an
> authorization failure rather than a silent success (§ 6).

> **`NFRx.y` IDs are GLOBAL across units.** D4's new IDs start above the
> high-water mark each base reached after D3, recomputed at this stage across
> both records. A bare `NFR14.41`, `NFR14.36`, `NFR10.15` or `NFR12.x` below is
> a **citation** of an earlier unit's requirement, never an ID defined here.

## Sources

- [upstream] `construction/teaching-and-recording/functional-design/functional-spec.md`
  §§ 3.3, 4.2, 4.3, 5
- [upstream] `construction/teaching-and-recording/functional-design/rules.md` —
  BR1.5, BR3.8, BR3.10, BR5.1, BR5.2, BR5.3, BR5.4, BR5.5, BR6.1–BR6.5, BR7.2
- [upstream] `construction/teaching-and-recording/functional-design/entities.md` —
  all six new tables and the three read-only existing ones
- [upstream] `inception/requirements-analysis/requirements.md` — NFR20, NFR23
- [upstream] `inception/domain-design/components.md` — the decision columns
- [prior] `261016-.../inception/requirements-analysis/requirements.md` — NFR10,
  NFR11, NFR13, NFR14, NFR15
- [prior] `261016-.../inception/contract-design/contract-summary.md` —
  **§ B.7**, § B.8
- [code] `app/governance/dispositions.py`, `app/contract/privacy.py`,
  `app/contract/routes.py`, `app/errors/_classes.py`, `app/errors/codes.py`,
  `app/authz/lenses.py` — read 2026-10-24

---

## 1. The six readers, each with an IDOR probe

BR5.2 names six new readers that must filter on the enrollment decision
columns. This project recorded on 2026-10-22 that **adding a column is not
adding a behaviour** — the queries that must start reading it have to be named
— so the requirement is stated per reader rather than once in general.

**NFR14.48** — Every one of the six readers filters on the decision column its
lens corresponds to, and each carries an adversarial probe asserting the
refusal rather than only the success.

| Reader | Lens | Required predicate | Probe asserts |
|---|---|---|---|
| Session roster | Teacher | BR1.5's four clauses | A declined seat is absent from the roster |
| Session detail | Teacher | batch owner matches `owner_id` | Teacher A cannot read teacher B's session |
| Student attendance history | Student | `student_decision = accepted` | A pending seat reads nothing |
| Guardian attendance history | Guardian | `guardian_decision = accepted` | A declined guardian reads nothing |
| Batch marksheet | Student, Guardian | the respective decision column | Each lens refused on its own column |
| Guardian progress | Guardian | `guardian_decision = accepted` | A non-child enrollment id is refused |

**Verifier: one probe per row, in the adversarial privacy suite, run as the
restricted role per NFR14.41.**

**NFR14.49** — A guardian requesting a **non-child** enrollment id receives
`NOT_AVAILABLE`, byte-identical to the response for an invented id — the same
status, the same code, the same body, and no timing difference that
distinguishes the two [BR7.2]. **Verifier: an equality assertion over the two
responses, not two independent assertions that each is a refusal.** Two
separate assertions pass while the bodies differ, which is the leak.

**NFR14.50** — Every route D4 adds resolves a lens, enforced by the built
route-enumeration test that walks `route.dependant` recursively and matches on
the dependency's **return annotation being a `Lens` subtype** [BR5.1].
**Verifier: `app/contract/routes.py`'s existing test, with no new mechanism.**
D4 adds **no** entry to `PUBLIC_ROUTES`; every route in this unit is
authenticated.

---

## 2. No profile field, and no account identifier, reaches a teacher

**NFR14.51** — No teacher-facing response schema in this unit carries a field
in the owner-private profile set or a global account identifier; a roster
exposes an **enrollment id** and never `student_account_id` [BR5.3].
**Verifier: `app/contract/privacy.py`, which iterates the generated OpenAPI
document and reads the lens from the route — already built, no new
mechanism.**

This matters more in D4 than in any prior unit for a reason worth stating
plainly: **a roster is literally a list of people**, and it is the most
natural place in the whole product to render a student's self-authored name or
photo beside the checkbox a teacher is tapping. The gate catches the schema;
nothing catches a designer deciding the roster should show photos. That
decision was already made against — the roster shows what the teacher recorded
[ADR-001] — and this requirement is the mechanical half.

---

## 3. Row-level security on D4's six tables — decided, with the reason

**NFR14.52** — D4's six tables are protected by **lens-scoped queries plus
adversarial probes**, and no row-level security policy is added for them. This
follows D3's NFR14.36 decision for the same stated reason, re-checked against
D4's schema: RLS exists on `profile` alone, because `profile` has a column
naming its reader (`account_id`), which is what an RLS policy needs to compare
against a session variable. **None of D4's six tables has such a column.**
`attendance` is keyed by `(session_id, enrollment_id)`; reaching the reader
from a row requires joining enrollment to account and branching on which of
three lenses is asking, which is the lens resolver's job and not a policy
predicate's. **Verifier: the decision is recorded here; what is verified is the
probe suite of § 1, which is what actually enforces the boundary.**

**NFR14.53** — This decision is revisited if any D4 table gains a column
identifying a reader directly. Stated so the decision has a trigger rather
than being permanent by default.

**NFR14.54** — `attendance_submission.submitted_by_account_id` is **not** such
a column. It names the *writer*, not a permitted reader, and no read is ever
scoped by it. Stated explicitly because it is the one column in D4 that looks
like a counter-example to NFR14.52 and would be mistaken for one.

---

## 4. The anonymised marksheet is a disclosure mechanism

This is the new security surface in D4, and treating it as a feature rather
than a disclosure is how it ships wrong.

**NFR14.55** — A marksheet returns the viewer's own mark named, plus **rank,
average, highest and a banded distribution**, and returns **no row
attributable to another student** [BR6.2]. **Verifier: a schema-level
assertion that the marksheet response carries no per-student collection, plus
a probe asserting a second student's mark is not derivable from the response
body.**

**NFR14.56** — No published band holds fewer than three results; a band under
three merges into its neighbour and the merge repeats until every published
band holds at least three [BR6.3]. **Verifier: the computed case in BR6.3 and
§ 4.2 of the functional spec, plus a property-style test over generated mark
lists asserting `min(published band counts) >= 3` or zero bands published.**

A band of one **is** a named mark. In a batch of 8 to 20 students who sit
together and compare marks, the name is supplied by anyone in the room within
a day. That is the whole reason the merge rule exists, and it is why the
threshold is a security requirement rather than a presentation nicety.

**NFR14.57** — No comparison of any kind is published below **five** marked
results, and none is published while any roster seat is still `not_entered`
[BR6.4]. The two conditions are independent and both must hold. **Verifier: a
test per condition, each holding the other condition satisfied — a single test
varying both at once passes while either check alone is implemented.**

**NFR14.58** — Every aggregate is scoped to **one batch** and never computed
across a teacher's batches [BR6.5]. **Verifier: a probe seeding two batches
with disjoint marks and asserting the average matches the single-batch
computation.** A cross-batch aggregate would disclose the existence and shape
of a batch the viewer is not enrolled in.

---

## 5. The toggle is an authorization control

**NFR14.59** — When `Batch.marksheet_visible` is false, **no marksheet is
returned at all** to any student or guardian lens — not an empty one, not one
with the comparison fields nulled [BR5.4]. **Verifier: a probe asserting the
response is a refusal or an absence, and specifically that it does not carry an
exam count, an exam list or an empty marks array.**

An empty marksheet still discloses that exams exist and how many. That is the
precise failure mode, and it is the one an implementation reaches by habit,
because returning an empty collection is the kinder-looking code.

**NFR14.60** — The toggle is written through **exactly one route**, under a
teacher lens scoped to the batch's owner [BR5.4]. The teacher's own view is
unaffected by its value. **Verifier: the route-enumeration test for the lens,
plus a probe asserting a non-owner teacher cannot write it.**

---

## 6. Replay, conflict, and the three mechanisms that must not be blurred

D4 is the first unit to hold **two** of the four writes § B.7 names as
carrying `client_mutation_id`. The product now has three distinct concurrency
mechanisms, each correct for its own case, and a requirement that blurs them
invites the wrong one being reached for:

| Mechanism | Protects against | Where | Key |
|---|---|---|---|
| `client_mutation_id` | **replay** — the same decision arriving twice | attendance, topic log, payment claim, payment verification | `UNIQUE (submitted_by_account_id, client_mutation_id)` |
| `attendance_version` / `topic_version` | **conflict** — a stale decision arriving late | the two queued paths only | the conditional `UPDATE` |
| insert-conflict | **duplicate generation** | fee cycles, sessions | `ON CONFLICT DO NOTHING` on a natural key |

**NFR14.61** — `client_mutation_id` is required on **exactly** the writes
§ B.7 names, two of which are D4's: `POST /v1/sessions/{id}/attendance` and
`PUT /v1/sessions/{id}/topic`. It is **not** added to any other D4 write.
**Verifier: a schema-level assertion over the generated OpenAPI document that
exactly these two D4 request bodies carry the field.** § B.7 says "stating the
four explicitly is what makes the rule reviewable", so generalising it to all
writes would contradict a deliberate decision rather than extend it.

**NFR14.62** — **A replay of another account's `client_mutation_id` is an
`AuthorizationError`, not a silent success.** The uniqueness is scoped per
account per endpoint [§ B.7], so account B presenting account A's id is not a
duplicate at all and must not be treated as one. **Verifier: a probe
submitting account A's id under account B's token and asserting a refusal —
specifically asserting it is not a `200` carrying A's stored result.**

This is the requirement that ships as a silent success if nobody writes it
down. The natural implementation looks up the id, finds a row, and returns it.

**NFR14.63** — The replay response returns the original stored result with
`200` and leaves the original's `created_at` **unchanged**, so a replay is
observably a replay [§ B.7, BR3.8]. **Verifier: assert `created_at` did not
move — not merely that no second row exists.** A second-row assertion passes
against an implementation that overwrites the original in place.

**NFR14.64** — A version conflict is refused **after** authorization, never
before [BR3.10]. If the caller's lens does not reach the session, the request
is refused with the shared `NOT_AVAILABLE` before any version is compared.
**Verifier: a probe asserting that a caller with no lens on the session
receives `NOT_AVAILABLE` and never `ATTENDANCE_VERSION_CONFLICT`, for both a
matching and a non-matching version.**

The ordering is the security property. `ATTENDANCE_VERSION_CONFLICT` carries
`current_version` and `current_state` — that is, **the roster** — so emitting
it before the authorization check would hand a stranger the class's attendance
in an error body. The descriptive code is permitted precisely because it is
unreachable without authorization, which is what keeps it clear of the oracle
rule in `app/errors/codes.py`.

---

## 7. Governance: six `TableGovernance` entries, in one change

**NFR10.18** — Each of D4's six new tables carries a **`TableGovernance` entry**
in `app/governance/dispositions.py`, written in the **same change** as the
migration that creates it [BR6.1].

One entry per table, not two: `RETENTION` is **derived** from `DISPOSITIONS`
by a dict comprehension at `dispositions.py:279-281`, so the two cannot fall
out of step and there is no second map to maintain. The entry carries three
fields — `disposition`, `retention` and `basis` — and the `basis` is the
sentence the generated privacy policy is written from, so it is prose a parent
could read rather than a code comment.

**Verifier: `tests/db/test_governance.py`, already built, which iterates live
`pg_tables` and asserts in BOTH directions.** The second direction is the one
that matters for D4 specifically: six tables arrive in one migration, and a
typo in a table name produces a **stale entry naming a table that does not
exist** rather than a missing entry — which a one-directional check would miss
entirely.

**NFR10.19** — `attendance`, `exam` and `mark` take `RETAIN_WITH_BASIS`, which
is the case that enum value was created for: rows written by the **teacher**,
which are the teacher's business record and simultaneously the child's
personal data [BR6.1, the `Disposition` docstring]. The values are
**transcribed from the prior components catalogue, not invented here**;
`attendance_submission` is the one table with no upstream row, because this
design added it, and it takes `attendance`'s disposition and retention since it
holds nothing `attendance` does not and is meaningless without it.
**Verifier: the same governance test, plus review against the prior
catalogue's rows.**

**NFR10.20** — D4 adds no hosting or database tier, and therefore does not
disturb the encryption-at-rest requirement for children's data [RC-8, D-29,
NFR10]. It is restated because D4 is the unit that first makes "children's
data" literal. **Verifier: no infrastructure change in this unit; the existing
tier's storage encryption stands.**

---

## 8. What must never be logged — the new items D4 introduces

Covered as requirements in `observability-requirements.md` § 1, where the
whole logging rule set lives. Named here because they are security properties
first: **a child's name never reaches a log line, a mark never reaches a log
line, and an attendance roster never reaches a log line.**

---

## 9. What D4 does not change

Stated so a reader does not look for a decision that was made elsewhere:

- **Authentication, tokens and OTP abuse controls** [NFR12, NFR13] — untouched.
  D4 adds no credential, no session and no token.
- **Device identifiers** [NFR11] — untouched. D4 adds no SDK. The queue's
  storage choice in `tech-stack-decisions.md` § 2 is checked against the
  forbidden-identifier set as the project ALWAYS-rule requires.
- **The restricted test role** [NFR14.41] — binds here exactly as before,
  although D4 adds no RLS policy, because the guard protects the *suite*: a
  privacy suite run as a superuser passes whether the boundary is correct,
  broken or absent.
- **The teacher/platform-administrator boundary** [TC-14, D-6] — D4 adds no
  administrator surface.

---

## 10. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| Six readers filter on decisions | One adversarial probe each [NFR14.48] | yes |
| Guardian IDOR is byte-identical | Equality over two responses [NFR14.49] | yes |
| Every route names a lens | Built route-enumeration test [NFR14.50] | yes |
| No profile field to a teacher | Built `app/contract/privacy.py` [NFR14.51] | yes |
| No band under three | Computed case + property test [NFR14.56] | yes |
| No comparison below five, or while incomplete | A test per condition [NFR14.57] | yes |
| Toggle off returns nothing at all | Probe on the absence [NFR14.59] | yes |
| Cross-account replay is refused | Probe under a second token [NFR14.62] | yes |
| Replay leaves `created_at` unmoved | Equality on the timestamp [NFR14.63] | yes |
| Authorization precedes the version check | Probe for `NOT_AVAILABLE` [NFR14.64] | yes |
| Six governance entries | Built `tests/db/test_governance.py` [NFR10.18] | yes |
| No latency assertion on the attendance path | Review [NFR2.6] | **no — review only, stated deliberately** |
| RLS decision for D4's tables | Recorded, not tested [NFR14.52] | **no — the probes are what enforce it** |

---

## Assumptions & Open Questions

- **`project.md`'s NEVER on local write queues contradicts its own cited
  source, and this document specifies the queue it appears to forbid.** The
  rule reads "NEVER accept a write without connectivity in V1; there is no
  local write queue"; NFR5, which it cites, reads **"Permitted for the
  mid-class path only"**. The functional design reconciles this at BR3.1 and
  flags the wording for amendment at a learnings gate. This document does not
  edit memory. **For the human.**
- **I searched for an existing RLS policy on any table other than `profile`**
  — migration `0001` lines 261-266, `app/authz/rls.py`, and every migration in
  `migrations/` — and found none. NFR14.52's claim that `profile` is the only
  policy is from that search, and it agrees with D3's independently-made
  NFR14.36.
- **The band width of 20 is the functional design's choice, not an upstream
  decision**, and it is visible to students. The merge rule makes the width
  largely immaterial to the disclosure property NFR14.56 states — what is
  published is whatever survives merging — so this document's requirements hold
  at any width. Flagged, not re-litigated.
- **No threat model document exists for this product.** I searched both
  records' `inception/` trees and `docs/`. The requirements above are derived
  from the stated constraints and the built gates rather than from an enumerated
  threat set, which is the same basis D1 through D3 used.
