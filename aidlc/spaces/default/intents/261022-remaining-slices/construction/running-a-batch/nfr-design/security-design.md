# Security Design — D2 `running-a-batch`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> **D2 adds no control and opens no surface.** Every route requires a session
> and resolves a lens; the abuse controls are D1's and untouched. What this
> design owns is three disclosure decisions and **one obligation with no
> server-side backstop** — which is the only interesting thing in the file and
> the reason it is not a list of inherited mechanisms.

## Sources

- [upstream] `construction/running-a-batch/nfr-requirements/security-requirements.md`
  — NFR14.26–NFR14.31, NFR23.4–NFR23.6
- [upstream] `construction/running-a-batch/functional-design/rules.md` —
  BR2.1–BR2.4, BR3.1, BR3.2, BR4.1, BR4.2
- [prior] D1's `nfr-design/security-design.md` — the lens hierarchy and the
  three-layer privacy boundary this unit inherits
- [code] `app/contract/privacy.py`, `app/batches/service.py`,
  `app/api/batches.py`, read 2026-10-23

---

## 1. The obligation with no server-side backstop

**Back after a guardian switches child** [NFR14.30, BR4.2, AC9.4.2].

Every other control in this product fails safe at the server: an unlensed
route is rejected by the route-enumeration gate, a teacher-lens response
carrying a `Profile` field fails the schema-wide invariant, a seat with no
accepted link grants nothing. **This one cannot be.** A guardian holding one
`GuardianLens` over two children makes two legitimately authorized requests;
nothing on the server can tell that the second arrived because Back took them
somewhere they had left.

### The design is to make the wrong thing unbuildable

| Approach | Back behaviour | Verdict |
|---|---|---|
| Per-child route, pushed on switch | Back returns to the previous child | **Rejected** — needs explicit stack manipulation, which is what gets forgotten |
| **Selection within one screen** | There is no back entry to return to | **Chosen** |

The switcher changes which child the single screen is scoped to. No
navigation event occurs, so there is no entry on the stack and Back leaves the
guardian home entirely — which is correct.

**This is the whole mechanism**, and it is a structural choice rather than a
rule somebody remembers. The Robolectric test [NFR23.6] asserts the behaviour;
the design is what makes the test's expectation the natural outcome.

---

## 2. Disclosure design

### The retained name

| Layer | What it does | Where |
|---|---|---|
| Governance | Records that a declined seat **keeps** the teacher-typed name, with its basis | `app/governance/dispositions.py` |
| **This design** | Records that it is **never rendered** | BR2.3, NFR14.28 |

**Retention and display are different decisions and only the first is in the
manifest.** The basis text says the name is kept because it is the teacher's
own record of who they meant to add — and the commonest cause of a decline is
a mistyped number they need to correct. None of that licenses showing it.

**The mechanism is that the mapper chooses the label.** `RosterRow` carries
`displayLabel`, already resolved to the number for a declined seat and the
name otherwise. The composable receives one string and has no second value to
render by mistake.

The alternative — pass both, let the screen pick — is the layer-boundary slip
D1 made and corrected, on a field where the slip discloses a person's name.

### The two new fields

Neither is personal data: both are decision enums [NFR14.26].

**They pass the schema-wide invariant passively, and the distinction
matters** [NFR14.27]. `forbidden_fields` iterates every teacher-lens response
schema and flags any field whose **name** appears in a forbidden set —
`OWNER_PRIVATE_FIELDS` plus `FORBIDDEN_ACCOUNT_ID_FIELDS`. It is a denylist,
not an allowlist. So `student_state` and `guardian_state` are not *verified
safe*; they are simply **never on the list**, which is the same thing a field
that should have been on the list would be.

That is adequate here and it is adequate for a reason, not by luck: the two
fields carry three enum values and no identity. What the invariant actually
protects against is a `Profile` field reaching a teacher — and **D1 learned
that it only protects against the names somebody added**, which is why
`address` needed BR3.4 to enrol it.

**So the obligation D2 inherits is the general one**: a future field on this
response that *is* personal data must be added to the forbidden set, and the
invariant will not notice if nobody does. D2 adds no such field; D1 wrote the
test that derives `OWNER_PRIVATE_FIELDS` membership from `Profile`'s columns,
which is the mechanism that would catch it.

### The guardian's reach

Unchanged and restated because D2 renders it: a guardian reaches children
**through their own guardian link**, never by finding the child and then that
child's enrollments [NFR14.29, BR4.1, and NFR14.15 of the prior record, which
is where the rule was first written]. The alternative merges two teachers'
records — a guardian recorded by teacher A seeing teacher B's batch for the
same child.

A declined guardian link reaches nothing, and the reason matters:
`list_guardian_children` has **no decision predicate of its own**. It is safe
because `GuardianLens` stops being granted [D1 BR1.1] — defended by the lens,
not by itself. D2 must not add a path that reaches it without the lens.

---

## 3. Authorization rendered, not re-decided

**Removability is the server's decision** [NFR14.31, BR3.1], and the reason it
cannot be derived client-side is specific rather than dogmatic:

`remove_enrollment` refuses on **two independent conditions** — no link
accepted (`_nobody_accepted`, reading the decision columns) and no erasure
marker set (reading `student_relink_blocked_at` and
`guardian_relink_blocked_at`). **The roster row carries the first and not the
second.**

A client deriving removability from the two link states it displays would
offer removal for an erased seat. That is not a style violation; it is a wrong
answer that the UI would present as an available action.

### The two refusals

| Code | Means | Remedy | Retryable |
|---|---|---|---|
| `ENROLLMENT_CLAIMED` | Somebody accepted | Mark inactive instead | **No** |
| `ENROLLMENT_ERASED` | The account was erased | The seat cannot be reused | **No** |

Both are `ConflictError`. **Neither offers a retry**, because retrying cannot
succeed — the screen reads `retryable` from the envelope rather than inferring
from the status code, and the envelope says false for both [BR3.2].

---

## 4. What D2 inherits unchanged

| Control | Mechanism | D2's change |
|---|---|---|
| Lens as a data dependency | Route-enumeration gate on the return annotation | none |
| Teacher-lens schema invariant | Iterates the generated OpenAPI document | covers the new fields automatically |
| Row-level security on `profile` | Policy keyed on the session account | none |
| Signup and OTP ceilings | D1's cascade | none |
| The audit vocabulary | Closed `AuthEvent` enum | **no new event** |

**D2 adds no audit event**, deliberately. The authentication log records
authentication events; reading a roster is not one, and widening that
vocabulary for ordinary reads would weaken the property that makes the log
reviewable.

---

## 5. Verification design

| Obligation | Mechanism | Why not something weaker |
|---|---|---|
| The count is right [NFR23.4] | Written from the criterion before the endpoint | It is the number a teacher reads to decide whether to chase people |
| Two refusals, two outcomes [NFR23.5] | Separate assertions per code | One test asserting "it refuses" passes for both and distinguishes neither |
| Back after switch [NFR23.6] | Robolectric rendering test | **The only mechanism** — see § 1 |
| A declined row shows no name [NFR14.28] | Rendering test on `displayLabel` | A mapper test proves the label; only a rendering test proves the screen shows nothing else |
| No `Profile` field on a teacher-lens schema | Existing schema-wide invariant | Inherited |

**NFR23.6 is the one that must not become a review note.** It is the only
obligation in this unit whose violation is invisible to every server-side
control, and this project's rule is that an obligation without a named
verifier is a wish.

---

## Assumptions & Open Questions

- **Assumed**: the guardian switcher is a selection control, which is what
  makes § 1's mechanism work. If a later unit makes it a navigation route,
  NFR14.30 needs an explicit stack decision at that point.
- **Assumed**: the two new enums serialize as lowercase strings matching
  `status`, so no new deserialization failure mode appears.
- **Open, and not D2's**: Schemathesis would check that the two widened
  response shapes conform. It remains unassigned by deliberate decision.
