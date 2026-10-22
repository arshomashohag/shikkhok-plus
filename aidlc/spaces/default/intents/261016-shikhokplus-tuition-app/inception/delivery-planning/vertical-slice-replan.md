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

No Bolt covers it. The product has no signup, and that was never
recorded as a decision — it fell out of the design:

- A **student or guardian** is created by their teacher, by phone
  number. B5 calls this "dormant-account resolution": the row exists
  before they open the app, and signing in activates it.
- A **teacher** has no path at all. Today one can only exist by
  inserting a row into the database by hand.

The design's `O1 · Create account` artboard therefore has no backend
and no Bolt behind it.

**Decided: self-signup after OTP verification.** An unknown number
that verifies becomes an account; a short name screen follows and
creates the `Owner` row that makes them a teacher.

The ordering matters and is the whole reason this is safe. `POST
/v1/auth/otp` stays byte-identical for known and unknown numbers, so
it still leaks nothing about who is registered [BR2.7]. The new/existing
branch happens **after** a successful verify, where the caller has
already proven they hold that number — so there is nobody to leak to.

`Owner` currently has no name column, so this needs a migration. And
`TokenResponse` deliberately carries no role or lens [BR1.1]; the
`is_new` flag it gains is about the ACCOUNT's existence, not about
what the account may do, and the lens stays computed per request.

## The re-scoped sequence

Each slice below is independently installable and demonstrable on a
phone. Sizes are relative, not estimates.

### V1 — `v1-account-and-first-batch` (S)

The slice that makes the app usable by a teacher who has never used
it. **This is the one that was missing.**

- **API.** `POST /v1/owners` creating the `Owner` with a name;
  migration adding `owner.display_name`; `POST /v1/auth/verify`
  returning `is_new` so the client knows to ask for a name.
- **Screens.** `O1` create-account name entry; `O2` log in (restyle);
  `O3` OTP (done, already matches); routing a verified new account to
  O1 and an existing one to its home.
- **Tests.** An unknown number's otp-issue response stays byte-identical
  to a known number's — the existing adversarial test, extended to
  cover the new branch. A verified account with no `Owner` is offered
  no teacher lens.
- **Done when.** A teacher installs the APK on a phone with a number
  nobody has entered, and reaches their own empty batch list.

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
- **Open:** whether a student or guardian who was never added by a
  teacher should be able to sign up at all. Today they cannot, and V1
  does not change that — an unknown number becomes a teacher. If a
  parent downloads the app before their tutor adds them, they get a
  teacher's empty batch list, which is wrong but not harmful. Worth
  settling before closed testing.
