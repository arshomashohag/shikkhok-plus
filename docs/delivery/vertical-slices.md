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

### Schema gaps this opens

Neither field O1 collects has anywhere to go:

- **`address`** — no column anywhere. New, and it is personal data, so
  it needs a disposition row in the governance manifest and a
  retention class before it is stored [RC-5, B11].
- **display name** — `Owner` has no name column, and a student's name
  today lives on the enrollment their teacher created, not on the
  account. Where a self-signed-up student's own name lives is a real
  modelling question rather than a column to add casually.

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
