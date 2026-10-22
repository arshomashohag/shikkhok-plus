# Re-scoping the pending Bolts as vertical slices

**Decided 2026-10-22, at the user's instruction, after installing the
APK on a real phone.**

## Why this document exists

The original plan types every Bolt `service` or `spec` and carries the
Android work as a trailing clause of the DoD — B3 ends with "Android:
OTP entry via SMS Retriever, the lens switcher, both language bundles
on screen one".

That shape let a Bolt be **technically done and practically unusable**.
B3 and B5 both shipped. Their endpoints work. What reached the phone
was a phone-number field, an OTP field, a batch list, and two unstyled
forms — against nine working endpoints. Nothing flagged it, because
each Bolt's stated DoD had been met.

The user's words on seeing it: *"This is totally shit. You haven't
built the necessary screens."* That is a fair reading of the
deliverable, and the cause is the Bolt boundary, not the execution.

**From here, a Bolt is one user-visible capability: API, screens and
tests together.** Its DoD names the design artboard it must match, and
it is not done until the thing can be done on a phone.

## The gap this surfaced: no account creation

No Bolt covers it. The product has no signup endpoint, and that was
never recorded as a decision — it fell out of the design:

- A **student or guardian** is created by their teacher, by phone
  number. B5 calls this "dormant-account resolution": the row exists
  before they open the app, and signing in activates it.
- A **teacher** has no path at all. Today one can only exist by
  inserting a row into the database by hand.

**The design already answers how.** `O1 · Create account` was read in
full on 2026-10-22, and it specifies considerably more than "a name
screen" — which is what an earlier draft of this document assumed
without reading it. Corrected below.

### What O1 specifies

**Four fields**: a role picker (Teacher / Student / Guardian), full
name, mobile number with a fixed `+88` prefix, and an **address**.

**Signup comes BEFORE the OTP, not after.** The submit button reads
"Send code to 01712-345678", so the order is: fill the form → create
the account → then send the code. An earlier draft had it the other
way round, which would have put the role question after verification
and contradicted the screen.

That ordering has a consequence worth stating plainly. `POST
/v1/auth/otp` stays byte-identical for known and unknown numbers
[BR2.7] — unchanged. But signup is a **different endpoint**, and state
5 of the artboard shows it saying "This number already has an
account." That is an existence oracle by construction, and it is the
design's deliberate choice: someone trying to sign up needs telling to
log in instead, and refusing to say so would make the screen unusable.
The two paths therefore have different disclosure properties on
purpose — so signup needs its own abuse controls, per-number and
per-IP, precisely because its response is informative.

**State 3 is the state most likely to be missed.** When a teacher has
already added the number, the form arrives pre-filled and the role is
**locked**:

> You've been added already
> মাহফুজুর রহমান added this number as a **student** in
> পদার্থবিজ্ঞান · Batch A. Check your details and add your address.

Teacher and Guardian are `disabled`; Student is selected. The name is
the teacher's entry, marked "Filled in by your teacher. You can
correct it." The address is still the account holder's to add.

This is B5's dormant-account path, finally given a screen. It also
means the form needs a **lookup before it renders** — something that
answers "is this number already enrolled, and as what" — which is a
second endpoint whose disclosure has to be reasoned about rather than
assumed, since it names a teacher and a batch to an unauthenticated
caller.

### Role is chosen but still never stored

`Account` has no role column, deliberately: `BR1.1` forbids one so
nothing can read a stale role. O1's picker does not contradict that,
because it decides **what gets created**, not what gets labelled:

| Picked | What is created | How the lens then computes it |
|---|---|---|
| Teacher | an `Owner` row | teacher, from owning batches |
| Student | no `Owner` | student, from their enrollments |
| Guardian | no `Owner` | guardian, from enrollments they guard |

The role therefore stays computed per request. The user's own framing
— *"if the user signs up as a teacher then he is a teacher, we don't
monitor that, it's up to the user"* — is exactly the resulting
behaviour: pick Teacher, get an `Owner` row, be a teacher. Nothing
verifies the claim and nothing is meant to.

### Settled: no role column (2026-10-22)

The question was raised directly — *"we need the role per account,
otherwise how can we set the access limitation?"* — and the answer is
that the limitation already exists and the role already is stored, as
an `owner` **row** rather than a string.

Confirmed by test rather than by argument
(`tests/batches/test_role_restricts_writes.py`,
`tests/authz/test_dual_role_cost.py`):

- a student is refused create-batch, add-enrollment, roster read and
  the teacher batch list — the last as a 403 rather than an empty
  list, because an empty list tells a non-teacher they are a teacher
  with no classes;
- one account resolves teacher, student and guardian together, in one
  statement, and each lens scopes correctly;
- teacher access appears when an `owner` row appears, with nothing
  written to the account.

**The decision: keep this model.** Two reasons recorded, so the
question does not get reopened from first principles:

1. The `owner` row is the *same fact* the teacher-scoped queries join
   on. "May this account create a batch" and "whose batches are
   these" are therefore answered by one thing that cannot disagree
   with itself. A role string is a second copy of that fact.
2. `FR1.4`'s dual-role account — a tutor whose own child is tutored
   elsewhere — carries three lenses at once. A single role column has
   to pick one and is wrong for every request about the others.

### Schema gaps this opens

Neither field O1 collects has anywhere to go:

- **`address`** — no column anywhere. New, and it is personal data, so
  it needs a disposition row in the governance manifest and a
  retention class before it is stored [RC-5, B11].
- **display name** — `Owner` has no name column, and a student's name
  today lives on the enrollment their teacher created, not on the
  account. Where a self-signed-up student's own name lives is a real
  modelling question rather than a column to add casually.

## Decided 2026-10-22: free to use, and lenses chosen at login

Two changes, recorded together because they arrived together.

### The app charges nobody

No teacher, student or guardian pays ShikhokPlus. **This removes the
platform subscription, not the fee system** — teachers still record
and collect tuition from their own students, which is the product's
core feature and all of `T4`, `T5` and `S3`.

Nothing to delete in code: "subscription" appears only in a comment
explaining why `Owner` exists as an indirection, and no billing was
ever built. One affirmed rule in `project.md` still mentions it —
*"visibility is limited to subscriber information — teacher name,
plan and payment status"* [TC-14, D-6]. That rule is a practices-gate
artifact and is **not edited here**; it needs the learnings ritual,
and the correction is narrow: an administrator sees teacher name
only, since plan and payment status no longer exist.

### Every lens at login, data per lens on demand

Sign in → the app learns which lenses the account has → the person
picks one → that lens's data is fetched → every screen offers a
switcher.

This replaces the implicit "you are a teacher" the app assumes today,
and it is what finally serves the `FR1.4` account that is a teacher
in one place and a guardian in another.

**Measured before being adopted**, at 50,000 accounts and 200,000
enrollments — 500× the 100-teacher target:

| Query | Time | Buffers | Plan |
|---|---|---|---|
| Lens resolution, as built | 0.23 ms | 17 | 3 index scans, no seq scan |
| Fetch-everything summary | **0.20 ms** | **14** | all index-ONLY scans |
| The busiest account in the set | 0.10 ms | — | index-only |

The summary is *cheaper* than the existing lens query: it reads the
same three indexes and never touches the heap.

**Why it stays flat as data grows**, which is the requirement rather
than the measurement: every lookup is `WHERE <column> = :account_id`
against a B-tree, so it is O(log n) in the table and O(1) in the
rows that belong to this account. Going from 200k to 20M enrollments
adds about two tree levels, not 100× the work. The cost tracks how
much data is *yours*, never how much exists.

What would break that is a query with no `account_id` in its
predicate. None exists, and the route-enumeration test is what keeps
it so: every endpoint must resolve a lens, and the lens *carries* the
scoping id, so such a query cannot be written without deleting the
dependency first.

### What this does NOT add

- **No cached summary table and no denormalised counts.** They cost
  more to maintain than the indexes cost to read, and they
  reintroduce the staleness `BR1.1` exists to prevent.
- **No eager per-lens data at login.** Loading every batch's roster
  up front is the one thing in this design that *would* grow with the
  data. The summary carries counts; a lens's rows arrive when it is
  chosen.

### The slice

`GET /v1/me` returns every lens the account has, with a count each:

```
{"lenses": [
   {"kind": "teacher",  "batches": 6},
   {"kind": "student",  "enrollments": 4},
   {"kind": "guardian", "children": 4}
]}
```

One statement, the same three indexes. The app renders the picker
from it, and a single-lens account skips the picker entirely rather
than being shown a list of one.

## The re-scoped sequence

Each slice below is independently installable and demonstrable on a
phone. Sizes are relative, not estimates.

### V1 — `v1-account-and-first-batch` (M, was S)

The slice that makes the app usable by someone who has never used it.
**This is the one that was missing**, and reading O1 moved it from S
to M: five states, a locked-role path and two new columns.

- **API.** `POST /v1/accounts` taking role, name, phone and address,
  creating the `Account` plus an `Owner` when the role is Teacher;
  a lookup the form can call before it renders, for the
  already-added case; migrations for `address` and a display name,
  each with its governance disposition row. Signup gets its own
  per-number and per-IP ceilings, because unlike otp-issue its
  response is deliberately informative.
- **Screens.** `O1` in all five of its states — empty, filled,
  **already-added with the role locked**, sending, and the two errors
  (number taken, address missing); `O2` log in, restyled; `O3` OTP,
  which already matches.
- **Tests.** `POST /v1/auth/otp` stays byte-identical for known and
  unknown numbers — the existing adversarial test, re-run to prove
  signup did not weaken it. Picking Teacher creates an `Owner`;
  picking Student or Guardian creates none, and the lens still refuses
  a teacher lens to an account owning no batches. The already-added
  path cannot be used to change the role a teacher set.
- **Done when.** Someone installs the APK, signs up as a teacher on a
  number nobody has entered, and reaches their own empty batch list —
  and a student whose teacher already added them sees their name
  pre-filled with the role locked.

### V2 — `v2-batch-and-roster` (M)

Everything B5's endpoints already support, with the screens the design
specifies.

- **API.** No new endpoints. `GET /v1/batches`, `POST /v1/batches`,
  `GET /v1/batches/{id}/roster`, `POST /v1/batches/{id}/enrollments`,
  `DELETE /v1/enrollments/{id}` all exist and work.
- **Screens.** `T6` batch list (done); `T7` single batch with its
  roster; `T8` add student; create-batch, replacing the bare
  `CreateForms.kt` text fields; remove-student, which has no UI at all
  today.
- **Done when.** A teacher creates a batch, adds two students by phone
  number, sees them on the roster, and removes one.

### V3 — `v3-guardian-view` (S)

The only other endpoint with no UI.

- **API.** `GET /v1/guardian/children` exists. OQ-7 (the route shape)
  was deferred to B5 "with the guardian screens in front of the
  decider" — this slice is where that finally happens.
- **Screens.** `G1` child home and switcher.
- **Done when.** A guardian with two children switches between them.

### V4 onward — unchanged in substance, re-typed in shape

B6–B11 keep their domain scope and confidence hypotheses; each gains
its screens and its artboard reference in the DoD:

| Was | Becomes | Artboards it must match |
|---|---|---|
| B6 fee-cycles-and-ledger | V4 fees | `T5` dues, `S2` batch fees |
| B7 payment-claims | V5 payments | `T4` verify, `S3` submit, `G3` history |
| B8 sessions-and-attendance | V6 attendance | `T1` today, `T2` record a class |
| B9 exams-and-marksheets | V7 marks | `T3` entry, marksheet light/dark |
| B10 teacher-insights | V8 insights | — |
| B11 privacy-and-governance | V9 governance | both deletion paths [TC-19] |

**B11 stays last and stays release-blocking.** Neither account-deletion
path exists yet, and `project.md` makes both V1 deliverables — so no
public Play track until V9 lands, whatever else is done.

## What does not change

The money boundary, the lens-per-request rule, the privacy boundary,
the test-first predicate, the coverage floors and both release gates
all hold exactly as recorded. This document reshapes **when work is
cut**, not what is required of it.

## Assumptions & Open Questions

- **Assumed:** a teacher's display name is the only thing signup needs.
  A subscription plan, an institution name and a photo are all
  plausible and none is required to reach a batch list, so they are
  left out until something needs them.
- **Settled 2026-10-22:** whether a self-signed-up account can choose
  its own role. It can, and nothing verifies the claim — "if the user
  signs up as a teacher then he is a teacher, we don't monitor that".
  O1's picker was already there; an earlier draft of this document
  raised it as an open question without having read the artboard.
- **Open:** whether the already-added lookup should name the teacher
  and the batch to an **unauthenticated** caller, as O1 state 3 shows
  ("মাহফুজুর রহমান added this number as a student in পদার্থবিজ্ঞান ·
  Batch A"). That is a real disclosure: anyone who types a number
  learns who teaches that person and in which batch. The screen needs
  something to show, but it could show less — "you have already been
  added" without naming either. Worth deciding before V1 ships rather
  than during it.
