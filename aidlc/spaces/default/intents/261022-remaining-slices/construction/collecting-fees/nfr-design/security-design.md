# Security Design — D3 `collecting-fees`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **Three designs carry this unit.** A disclosure direction the product has
> never had and the built invariant cannot see; four tables whose
> authorization is a path rather than a column, so the protection is
> lens-scoping plus adversarial probes rather than a policy; and a set of
> refusals richer than any before them, several of which would be an
> existence oracle if given the descriptive code they invite.

## Sources

- [upstream] `construction/collecting-fees/nfr-requirements/security-requirements.md`
  — NFR14.32–NFR14.47, NFR9.34–NFR9.38, NFR10.15–NFR10.17, NFR11.2, NFR13.5,
  NFR23.7–NFR23.10
- [upstream] `construction/collecting-fees/nfr-requirements/reliability-requirements.md`
  — § 4, the error taxonomy this design's § 4 constrains the codes within
- [upstream] `construction/collecting-fees/functional-design/rules.md` — BR3.3,
  BR3.4, BR4.1, BR5.1, BR5.5, BR5.7, BR6.1, BR6.2, BR6.4, BR6.5
- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  §§ 5.1, 7, 8
- [upstream] `construction/collecting-fees/functional-design/entities.md`
- [prior] `261016-shikhokplus-tuition-app/inception/contract-design/contract-summary.md`
  § G — OQ-1
- [code] `app/contract/privacy.py:55-78,163-213`, `app/errors/codes.py`,
  `app/errors/_classes.py:108-113`, `tests/contract/test_error_contract.py:186-199`,
  `app/authz/resolve.py:80-104`, `app/authz/rls.py`,
  `migrations/versions/0001_initial_identity_schema.py:250-279`,
  `app/governance/dispositions.py`, read 2026-10-23

---

## 1. The downward direction: the collection number

BR6.4 is the first field in this product that flows **from** a teacher **to**
students and guardians. Every built privacy control points the other way.

### What the built invariant does and does not do

`forbidden_fields(app)` (`app/contract/privacy.py:163-213`) walks every
teacher-facing route's response schema and reports any field whose **name** is
in `OWNER_PRIVATE_FIELDS` or `FORBIDDEN_ACCOUNT_ID_FIELDS`. Two properties
follow, and the second is the one that matters here:

- It is **name-matched against a denylist**, which the module's own comment
  states: "adding a column does not enrol it, so an unenrolled field leaves
  the invariant passing over a field it cannot see."
- It asks **one question in one direction** — is a *teacher-facing* response
  carrying an *owner-private* field. A teacher-authored field reaching an
  over-broad *student* response is its mirror image, and nothing in
  `privacy.py` looks that way.

So the honest statement is: **the built invariant is silent on BR6.4, not
satisfied by it.** NFR14.32's mechanism is new work.

### The mechanism [NFR14.32, NFR14.33]

A schema-wide test, written in the same iterating shape as the built one so it
covers the route added three units later:

```
# For every route in the generated document:
#   if its response schema reaches a field named `collection_number`
#     assert the route is the ONE permitted payment-destination route
#   else assert it does not
assert collection_number_routes(app) == {("GET", "/v1/enrollments/{id}/payment-destination")}
```

| Property | Design |
|---|---|
| **Exactly one schema** | An equality against a one-element set, not a membership test. A membership test passes when the field spreads to a second response |
| **Never in a listing** [NFR14.33] | Falls out of the equality: a batch listing, a roster response or a fee-cycle collection carrying it fails the assertion |
| **The lens on that route** | Asserted separately: the route resolves a student or guardian lens and **no teacher lens**, read through `lens_types_of(route)` — the existing helper, which returns every lens rather than the first, because the first-match version was already found to misclassify |
| **Enrollment scoping** | The route takes the enrollment id and the handler checks the enrollment's batch is the one the number belongs to. This is a runtime check, covered by the probes in § 3, not by the schema test |

**Why an allowlist rather than adding `collection_number` to a denylist.**
A denylist entry would say "no teacher-facing response carries it" — which is
backwards, since the field is the teacher's own and a teacher may see it. The
property is *exactly one response carries it*, and only an allowlist expresses
that.

### Unset and the channel set [NFR14.34, NFR14.35]

| Requirement | Design |
|---|---|
| NFR14.34 — unset omits the step | The response models the destination as an **optional object**, absent rather than present-with-null. A null invites a client placeholder; an absent object leaves the client nothing to render and the copy tells the person to ask the teacher |
| NFR14.35 — server-supplied channels | The channel set is a field of the same response. No Kotlin enum of channels: an installed app cannot be forced to update, so a client list is a permanent decision made by whoever shipped it |

**NFR14.35 has a mechanical half worth naming**: the Kotlin side models
channels as a list of server-supplied values rendered as labels, not as a
sealed type with a branch per channel. A sealed type is the idiomatic Kotlin
choice and it is the wrong one here, because adding a channel server-side would
then require a client release.

---

## 2. Row-level security on D3's four tables

### The decision, with its reason [NFR14.36, NFR14.37]

**D3 adds no RLS policy.** Its four tables are protected by lens-scoped queries
plus the adversarial probes of § 3.

The built policy is on **`profile` alone**:
`0001_initial_identity_schema.py:261-266` runs `ENABLE` then `FORCE ROW LEVEL
SECURITY`, and `app/authz/rls.py` sets `app.account_id` **transaction-locally**
— the `true` argument to `set_config` being, in that module's words, "the whole
control", because a session-scoped set is connection-scoped and connections are
pooled.

That policy is expressible because `profile.account_id` **is** the subject:
`account_id = current_setting(...)` is a predicate on a column of the row.

D3's tables have no such column. A fee cycle's authorization is a **path**:
this account holds an accepted student link on this enrollment, or an accepted
guardian link on it, or owns the batch the enrollment sits in. That is the
three-branch join `_LENS_QUERY` already performs
(`app/authz/resolve.py:80-104`), including the `decision = 'accepted'`
predicates that D1 exists to enforce. Encoding it into a `USING` clause would
produce **two implementations of one authorization rule**, the second outside
`app.authz`'s branch-coverage measurement and outside its strict mypy island.

**NFR14.37 names the trigger to revisit**: any D3 table gaining an
account-scoped column that identifies a reader directly. At that point the
`profile` shape applies and the argument above stops holding.

### What makes the decision safe

The probes are the mechanism, not a supplement — which is why § 3 is
requirements rather than suggestions. **Two further things carry it:**

- **The lens is a data dependency.** Every endpoint resolves a lens whose
  return annotation is a `Lens` subtype, and the route-enumeration test asserts
  this for every route with `PUBLIC_ROUTES` as the explicit exception set. D3's
  new routes fall under the built gate with no new mechanism. A handler cannot
  compile a scoped query without the lens, because the lens carries the
  scoping value — `owner_id` for a teacher, `child_enrollment_id` for a
  guardian.
- **The suite still runs as the restricted role** [NFR14.41]. See § 3.3.

---

## 3. The adversarial probes

### 3.1 The three shapes [NFR14.38, NFR14.39, NFR14.40]

| Probe | Request | Expected |
|---|---|---|
| **NFR14.38** | Teacher A, holding a valid teacher lens, requests the fee view for a batch owned by teacher B | Refused, with the shared code of § 4 |
| **NFR14.39** | A guardian of child X requests the fee cycles of an enrollment belonging to child Y | Refused |
| **NFR14.40** | A student requests a fee cycle belonging to another enrollment, including another of their own batches' seats held by someone else | Refused |

Each is written in the IDOR shape: **a real id that exists and is not the
caller's**, never an invented id. An invented id tests the not-found path,
which is a different path and the easier one to pass.

**NFR14.40 is the one the team practice has been waiting for.** The probe set
was written naming three shapes; two were exercisable at D1 and the third was
not, because the table it probes is created by this unit.

### 3.2 Two probes the three shapes do not reach

Both follow from D3's specific structure and neither is covered by a generic
IDOR probe:

| Probe | Why it is separate |
|---|---|
| **A student submits a claim against another enrollment's fee cycle** | The three shapes above are reads. This is a write, and it is the path where a wrong answer creates a money record attached to someone else's seat |
| **A guardian whose link is `declined` requests the child's fee cycles** | Not an IDOR: the link exists and names the right child. The refusal comes from `decision = 'accepted'` in the granting query, and this probe asserts D3's reads inherit that predicate rather than finding the enrollment some other way |

The second is the specific trap this record has already recorded once: a
query that grants on the old evidence because nobody checked which statement
the new read path uses.

### 3.3 The role the probes run as [NFR14.41]

Unchanged and binding: the suite connects as `shikkhok_app`, the restricted
non-superuser role, with the built meta-test asserting `current_user` is not a
superuser **before** the privacy suite runs — enforced by a collection reorder
plus an autouse re-check.

**This binds even though D3 adds no RLS policy**, and the reason is worth
stating because the obvious reading is that it does not. The meta-test guards
the **suite**, not a table: a future reader who adds a policy to `ledger_entry`
inherits a suite that certifies it, and only if the suite was never allowed to
drift to a superuser connection in the meantime. D3's new tests fall under the
built guard with no new mechanism.

---

## 4. Refusal codes: which may be descriptive, and which may not

This is the design section the error taxonomy forces, and D3 is the unit most
likely to cross the line because its refusals are richer than any before them.

### The built rule

`app/errors/codes.py` registers **one** code — `NOT_AVAILABLE` — covering both
"this does not exist" and "you may not reach this". Its docstring states why:

> A pair such as `BATCH_NOT_FOUND` / `BATCH_NOT_YOURS` is an existence oracle
> even though each code reads as good practice on its own: teacher A probes ids
> and reads the difference, enumerating teacher B's batches.

The status pairing is a lookup (`auth_status_for`), not a judgement at the
raise site, so a 403 can never carry a 401-only code.

### The test, and what it does not catch

`tests/contract/test_error_contract.py:186-199` asserts the registry contains
no **oracle-shaped pair**: it scans `AUTH_403_CODES` for names containing
`NOT_FOUND`, `NOT_YOURS` or `FORBIDDEN`.

**That cannot catch a new code that is individually disclosing.** A code named
`FEE_CYCLE_NOT_YOURS` would be caught by the name scan; a code named
`CLAIM_BELONGS_TO_ANOTHER_ENROLLMENT` would not, and neither would any code
that is simply never registered in `AUTH_403_CODES` at all. The test asserts a
property of the registry; it says nothing about a code raised from a service
module.

### The test to apply

**Is this code reachable only by someone to whom the lens has already been
granted?** If yes, a descriptive code is better for the user. If it is
reachable before authorization resolves, it must be the single shared code.

**D2 did not cross this line and the reason is the distinction D3 must keep.**
`BATCH_NOT_FOUND` (`app/batches/service.py:280,394`) is raised for an
unauthorized **or** absent batch, so it covers both and discloses nothing.
`ENROLLMENT_CLAIMED` and `ENROLLMENT_ERASED` (`:439,:452`) are reachable only
after ownership is established — a caller who can already see the roster learns
nothing from being told why a removal was refused.

### D3's refusals, classified

| Refusal | Reachable before authorization? | Code | Reason |
|---|---|---|---|
| Fee cycle id absent, **or** belonging to another enrollment | **Yes** | **shared** `NOT_AVAILABLE` | Distinguishing them lets a student enumerate other students' fee cycles. One code, both cases |
| Claim id absent, **or** belonging to a different claimant | **Yes** | **shared** `NOT_AVAILABLE` | Same oracle, over claims. A claimant may read only their own |
| Batch fee view requested by a non-owning teacher | **Yes** | **shared** `NOT_AVAILABLE` | Exactly the `BATCH_NOT_FOUND` case D2 already answers; D3 reuses it rather than minting a fee-flavoured twin |
| Verification attempted by a teacher not owning the claim's batch | **Yes** | **shared** `NOT_AVAILABLE` | A non-owning teacher must not learn the claim exists |
| Guardian requesting a non-child's enrollment | **Yes** | **shared** `NOT_AVAILABLE` | Otherwise a guardian learns which enrollment ids are real |
| Claimed amount zero or negative | No — the caller's own submission | descriptive | Validation of the caller's own input; discloses nothing about anyone else [BR5.2] |
| No open cycle to receive a claim | No — on the caller's **own** enrollment | descriptive | The caller already holds the lens on that enrollment; the reason is the help [BR5.1] |
| Shortfall with no disposition chosen | No — post-authorization, teacher's own claim | descriptive | The teacher must choose, and must be told which choice is missing [BR5.4] |
| Carry exceeding the origin's balance | No — post-authorization | descriptive | A teacher acting on their own batch's ledger [BR3.2] |
| Claim already verified, re-verified | No — post-authorization | descriptive | The owning teacher already sees the claim. The code must say "already decided", because the remedy is the correction path and not a retry [BR5.7] |
| Negative ledger amount | No — internal, never caller-supplied | descriptive | A server-side invariant breach [BR3.4] |

**The two rows most likely to be got wrong are rows 1 and 2**, because each has
a tempting descriptive pair: `FEE_CYCLE_NOT_FOUND` for the absent case and
something else for the unauthorized one. Each reads as good practice alone,
and the pair is the oracle.

**Row 7 deserves its own note.** "No open cycle" is descriptive and safe only
because the claim submission route is scoped to the caller's own enrollment
before it reaches that check. If a later change let a claim name an arbitrary
enrollment id, this code becomes an oracle on whether that enrollment has an
open cycle — so the safety is a property of the route's scoping, not of the
code.

### Making it mechanical [team: Way of Working]

The table above is checkable, which is the point of writing it as a table. The
design's obligation on Code Generation:

- **Every D3 authorization refusal raises `NOT_AVAILABLE`**, and the registry
  gains no new authorization code. The existing `auth_status_for` lookup then
  carries the status, unchanged.
- **The registry test is extended** from "no oracle-shaped pair" to the
  stronger property it needs. The property is **not** a whole-set equality on
  `AUTH_403_CODES`: that set already holds two members today —
  `NOT_AVAILABLE` and `LENS_NOT_AVAILABLE` (`app/errors/codes.py:53`) — and
  the second is not an oracle, because a lens-hint mismatch discloses nothing
  about whether a resource exists. An equality assertion would fail against a
  registry that is already correct.

  The assertable property is narrower: **`AUTH_403_CODES` contains exactly one
  code that refuses a RESOURCE**, where the set is pinned as a literal
  allowlist of the non-resource members (`LENS_NOT_AVAILABLE` today) and the
  test asserts `AUTH_403_CODES - ALLOWED_NON_RESOURCE == {NOT_AVAILABLE}`.
  Adding any new 403 code then fails the test until someone classifies it,
  which is the behaviour wanted: the test catches a new code whatever it is
  called, and the classification is a deliberate act rather than a name-shape
  guess.
- D3's descriptive codes live in the **validation and conflict** vocabularies,
  never in `AUTH_403_CODES`, so the property above is not weakened by them.

**And `transaction_id` appears in no refusal code, no `details` payload and no
`message_key`.** It is claimant-authored and personal [NFR24.5]; a refusal
echoing it back would put it on a path the logging rule exists to keep it off.

---

## 5. Money as a security property

| Requirement | Design |
|---|---|
| NFR9.34 — JSON string both sides | The existing annotated Pydantic `Money` type on every D3 schema; the Kotlin value class reads **only** a string and fails loudly on a number. Asserted on both sides, as built |
| NFR9.35 — `NUMERIC(12,2)`, no float | The existing SQLAlchemy `TypeDecorator`. The two import-boundary mechanisms — Ruff banned-api on raw `decimal` outside `app/money/**`, and the pytest AST walk — already cover D3's new modules, because they are stated over paths rather than over a module list |
| NFR9.36 — non-negative amounts | **A `CHECK (amount >= 0)` on `ledger_entry`**, in addition to the value type's refusal |
| NFR9.37 — append-only | **A restricted-role grant**: `shikkhok_app` holds `SELECT, INSERT` on `ledger_entry` and `UPDATE` on `superseded_by_id` only; no `DELETE`. See below |
| NFR9.38 — a carry is a pair in one transaction | `carry_forward()` already returns the pair; the design's rule is that both entries are added to one session and committed together, never one flushed early |

**NFR9.36 and NFR9.37 are table-level because of the writer that does not go
through the value type.** On a single-host deployment with manual production
access, a repair script is a realistic writer, and the value type protects only
code that imports it.

**The append-only grant is the design decision here, and it has a cost worth
naming.** `0001_initial_identity_schema.py:240-247` currently grants `SELECT,
INSERT, UPDATE, DELETE` on **all tables in schema public** to `shikkhok_app`,
so D3's migration must narrow the grant for `ledger_entry` specifically after
creating it — a column-level `UPDATE` grant on `superseded_by_id` plus
`SELECT, INSERT`, and a revoke of `DELETE`. The cost is that the blanket grant
and a per-table exception now coexist, which a reader must notice. The
alternative — a `BEFORE UPDATE OR DELETE` trigger — is rejected on the stated
house rule that structure here is enforced by rules, tests and a restricted
role rather than by database triggers [tech-stack § Assumptions].

**The verifier** is a probe asserting that `DELETE FROM ledger_entry` and an
`UPDATE` of `amount` both raise as `shikkhok_app`, and succeed as the owner —
the second half mattering because a probe that only asserts failure passes
against a table that does not exist.

---

## 6. Verification as an authorization decision

| Requirement | Design |
|---|---|
| NFR14.42 — only the owning teacher verifies | The route resolves a `TeacherLens`, and the claim's enrollment's batch's `owner_id` must equal the lens's. The refusal is `AuthorizationError` with the **shared** code of § 4 |
| NFR14.43 — who, when, one transaction | `verified_by_account_id` and `verified_at` on the claim; the decision and every `LedgerEntry` it produces commit in **one** transaction. See `reliability-design.md` § 3 |
| NFR14.44 — a correction retains the prior decision, visible to both sides | `previous_decision` is `json` holding amount, disposition, actor and timestamp. **The student's and guardian's claim-history response carries the same correction history the teacher's does** |
| NFR14.45 — concurrent re-verification is a `ConflictError` | Not a second decision. The class is the one the built taxonomy already names for this shape; see `reliability-design.md` § 4 |

**NFR14.44's mechanism is where this could go wrong quietly.** The natural
implementation renders correction history on the teacher's screen — the teacher
made the correction — and omits it from the claimant's, because nobody asked
for it there. That is the shape a dispute cannot be settled from, and it is a
response-schema decision rather than a UI one: **the claimant's claim-detail
response carries `previous_decision` and the correcting actor**, and a test
asserts it on both responses rather than on the teacher's alone.

---

## 7. The decline asymmetry [NFR14.46, NFR14.47]

| Link declined | Money | Lens |
|---|---|---|
| **Student** | Generation stops; accrued cycles reversed by appended `forgiveness` entries [BR1.6] | Student lens withdrawn |
| **Guardian** | **Nothing changes** [BR1.7] | That guardian's lens withdrawn |

**The design obligation is a sweep, not a rule** [NFR14.47]. Every surface
rendering a decline is checked against **both** roles. D3's surfaces that
render one:

| Surface | Student-facing copy | Guardian-facing copy |
|---|---|---|
| Decline confirmation | The obligation stops from here; what is already owed stands | **Your access ends. The student's fees are unaffected** |
| Fee history after a student decline | Reversal entries visible as forgiveness | Not reachable — the lens is gone |
| Fee view after a guardian decline | Unchanged | Not reachable |

**This project has already paid for this once**: a decline confirmation reading
"the fee stops" was shown to guardians as well as students, telling a guardian a
debt was cancelled when it was not. D3 is where that sentence becomes true or
false in the ledger rather than only on a screen.

**The verifier is the role-paired string check**: each decline string resource
is asserted to have a distinct key per role, so one shared key cannot serve
both. There is **no automated check that the Bangla copy says the right thing**
— that is a per-screen manual check, and the project has no screenshot harness
[team: Testing Posture].

---

## 8. Governance [NFR10.15, NFR10.16, NFR10.17]

| Table | Obligation |
|---|---|
| `fee_cycle`, `ledger_entry`, `payment_claim`, `reminder_event` | A disposition **and** a retention class in `app/governance/dispositions.py` before the unit is complete. The schema-iterating test fails on a live table with no entry, so this is already mechanical |

**The dispositions are not chosen here**, because they are a domain and legal
judgement rather than a design one. What this design records is that
`ledger_entry` is the first table where `HARD_DELETE` and `RETAIN_WITH_BASIS`
pull hard in opposite directions: it is simultaneously a child's financial
record and a teacher's business record. OQ-1 is the open form of that same
tension for one column.

| Requirement | Design |
|---|---|
| NFR10.16 — encryption at rest | A hosting property, not a per-table one. D3 adds no tier that lacks it |
| NFR10.17 — `transaction_id` nullable | Ships nullable, which is **answer-agnostic**: if OQ-1 resolves to "remove", D6 nulls it in place rather than migrating a column that cannot hold the absence |

---

## 9. What D3 does not change [NFR11.2, NFR13.5]

| Control | State |
|---|---|
| OTP and signup ceilings | D1's, untouched |
| RLS on `profile` | Unchanged; D3 adds no policy and § 2 says why |
| `OWNER_PRIVATE_FIELDS` | Unchanged — D3 adds **no `Profile` column**. The collection number is a `Batch` column and is governed by § 1's allowlist, not by this denylist |
| The auth audit vocabulary | Unchanged; D3 adds no authentication event |
| Unauthenticated surface | **None added** [NFR13.5] |
| Secrets | None added. D3's routes authenticate through the built session; no new secret enters the repository or the image [NFR13.5] |

**NFR11.2 — the FCM adapter transmits no device or advertising identifier.**
App-instance-scoped installation ids only. The adapter is D3's to build and
D4's to consume [tech-stack § 3], so this property is established **once**, in
shared infrastructure beside the SMS gateway client — which is the placement
decision that prevents D4 from copying an adapter rather than importing it.
**The existing DEX scan and manifest allowlist cover the forbidden-identifier
set on the client**; what they do not cover is a server-side adapter storing an
identifier it was handed, so the verifier here is that the stored token column
holds an FCM registration token and nothing else, asserted at the adapter's
boundary.

---

## 10. Test posture [NFR23.7–NFR23.10]

| Requirement | Design |
|---|---|
| NFR23.7 — nearly everything is test-first | The affirmed predicate holds across almost this whole unit: the output is knowable from the rule without the code, and a wrong answer is a money or authorization error. That includes the lens-scoping of § 2 and the refusal classification of § 4 |
| NFR23.8 — money module at 100% branch | `fail_under = 100` unchanged. D3 adds persistence **around** the module and one pure formatter **inside** it |
| NFR23.9 — partial approval tested with claim ≠ charge | The named case: charge 1000, claim 1500, approved 600 → shortfall **400.00**. The wrong formula gives 900.00, and a test using claim = charge cannot tell them apart |
| NFR23.10 — a named test per state transition | Per `PaymentClaim.status` transition and per cycle-generation outcome, plus a documented boundary case per money input |

**NFR23.9's figures are the test.** Computed: `charged − approved` =
1000 − 600 = **400.00**; `claimed − approved` = 1500 − 600 = **900.00**. The
two formulas coincide at claim = charge, which is why the boundary case must
use a claim that differs.

---

## Assumptions & Open Questions

- **Assumed**: the payment-destination step is its own route rather than a
  field on the claim-submission response. The one-route allowlist of § 1 is
  simpler to assert against a dedicated route, and a dedicated route is also
  the one that can be lens-checked against the enrollment.
- **Assumed**: narrowing the `ledger_entry` grant inside D3's migration is
  acceptable alongside the blanket grant in `0001`. The alternative is
  re-issuing a narrower blanket grant, which touches every table and is a
  larger change than this unit should make.
- **Open, and the human's — OQ-1**: whether `PaymentClaim.transaction_id`
  survives the claimant's deletion. D3 ships it nullable so the answer is not
  foreclosed; the answer belongs in D6's disposition manifest and in the
  privacy-policy text generated from it.
- **Open, and the human's**: the four governance dispositions. Mechanically
  forced by the schema-iterating test, so this cannot ship unanswered —
  but `ledger_entry`'s is a genuine judgement.
