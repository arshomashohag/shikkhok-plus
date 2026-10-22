# Business Overview

## What this product is

ShikhokPlus is a private tuition management application for Bangladesh. The
customer is a **private tutor** — a teacher who runs one or more small
classes, called **batches**, outside a school. The product gives that teacher
a single place to hold the roster, the attendance, the marks and, above all,
the money owed to them, and it gives the students and their guardians a view
of the same facts from their own side.

The repository holds two deployable surfaces and one shared contract between
them:

- a **Python/FastAPI backend** (`app/`) over PostgreSQL 16, which owns every
  business rule;
- an **Android application in Kotlin and Jetpack Compose** (`android/`),
  which renders what the server computes and holds no business logic of its
  own;
- a **committed OpenAPI 3.1 document** (`openapi.json`) that is the contract
  between them and is checked against the generated document in CI.

The application is **free to its users**. The 2026-10-22 delivery plan
records that the platform subscription was removed: the product charges
nobody, and the fee system that remains is the teacher collecting tuition
from their own students.

## The people it serves

The system models three ways of relating to a batch, and it deliberately does
**not** model them as roles on an account.

| Who | What they do | How the system knows |
|---|---|---|
| **Teacher** | Owns batches, enrols students, records attendance and marks, sets and collects fees | The account has a row in `owner` |
| **Student** | Sees their own enrolments, what they owe, their marks | An `enrollment` row names the account as `student_account_id` |
| **Guardian** | Sees a child's enrolments, dues and progress; may pay on their behalf | An `enrollment` row names the account as `guardian_account_id` |

A single account can be all three at once — a teacher who is also a parent is
the ordinary case, not an edge case — and the system answers "what can this
person do" freshly on every request by looking at those two tables. There is
no role column anywhere, and `GET /v1/me` is the endpoint that reports which
of the three lenses an account currently has, with a count behind each, so
the app can show a picker.

## The domain, in the system's own terms

- **Account** — one person, keyed permanently by their phone number. There is
  no password: sign-in is a one-time code sent by SMS.
- **Owner** — the indirection that makes someone a teacher. A teacher-facing
  response exposes an `enrollment` id and never a global account key, so that
  teacher A cannot acquire a stable handle on a student who also studies with
  teacher B.
- **Batch** — one class a teacher runs: a name, its subjects, a weekly
  schedule, a default fee and a day of the month that fee falls due.
- **Enrollment** — one seat in a batch. The student link and the guardian
  link live on the **same row**, so the enrolment a guardian reaches *is* the
  child's enrolment. A seat may carry a `fee_amount` overriding the batch
  default; `null` means inherit, while zero means a waiver, and the
  distinction is load-bearing.
- **Profile** — what a student or guardian writes about *themselves*
  (`self_name`, `photo_ref`). It belongs to exactly one account, is visible
  only to that account, and is never visible to any teacher.
- **Money** — Bangladeshi Taka, always exact fixed-point decimal, never a
  floating-point number anywhere in the stack.

## What the built system does today

Four units of work are complete and merged, and they cover identity and the
roster:

- A person signs in by typing their phone number, receiving an SMS code and
  presenting it. Seven abuse controls sit around that path, because each SMS
  costs money and the per-SMS bill is a direct attack surface on the
  project's budget.
- An authenticated request resolves its lenses from the data, with no stored
  role and no cross-request cache.
- A teacher can create a batch, list their batches, read a roster, add a
  student (with an optional guardian), mark an enrolment inactive from a
  date, and remove a seat nobody has yet claimed.
- A guardian can list the children they are recorded against.
- Everything a student or guardian writes about themselves is fenced off
  from every teacher by table design, by PostgreSQL row-level security and
  by the shape of the response schemas.

## What the business needs next, and is not yet built

There is **no code at all** for the commercial core of the product. The
following domain concepts appear in the plan and in the governance manifest
but exist in neither the schema nor the application:

- **Account creation.** Nothing in the built system creates an account. A
  teacher can only exist by inserting a database row by hand.
- **Seat acceptance.** A teacher typing a phone number today makes that
  account a student or guardian immediately — no consent, no notification, no
  way to decline. A mistyped digit silently exposes a child's records.
- **Fee cycles, the ledger, payment claims and verification.** The money
  *type* and its boundary are built and heavily tested; nothing that charges,
  receives, carries forward, waives or credits exists.
- **Sessions, attendance, exams and marks.**
- **Cross-batch dues and earnings insights.**
- **Both account-deletion paths**, which are release-blocking for a public
  Play track.

## Language and locale

The product is Bangla-first with English alongside. Both string bundles are
present and complete on the built screens — 53 strings in each of
`values/strings.xml` and `values-bn/strings.xml` — and no user-facing string
is hard-coded in a composable. Money is rendered server-side so the client
never decides digit shape or separator placement.

## Commercial constraints that shape the code

- Infrastructure spend is capped at **USD 50/month**. The Terraform root
  module computes the monthly figure and refuses to apply above the ceiling;
  the current Phase 1 estate is recorded in it at USD 24.50/month.
- The audience includes children, so the Google Play Families policy applies.
  The application transmits **no device or advertising identifier**, requests
  **no SMS read permission**, and carries **no analytics or crash-reporting
  SDK**. Two release-build gates enforce this mechanically rather than by
  review.

## Sources

- [code] `app/`, `android/src/`, `migrations/`, `infra/`, read 2026-10-22 at
  commit `b14b1fa`
- [code] `openapi.json`, the committed contract
- [code] `app/governance/dispositions.py`, the per-table deletion and
  retention manifest
- [upstream] `aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/inception/delivery-planning/bolt-plan.md`
  — the approved plan for the six remaining deliverable units
