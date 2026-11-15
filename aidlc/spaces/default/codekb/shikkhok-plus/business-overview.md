# Business Overview — ShikkhokPlus

Full rescan, 2026-11-13, commit `cb20fd1`. Facts below are verified in code unless marked *inferred*.

## What the product is

ShikkhokPlus is private-tuition management for Bangladesh (`pyproject.toml` description: "Private tuition management for Bangladesh — backend"). It serves four kinds of people through one Android app (`com.shikkhokplus.app`), one installable web app (`web/`, the same `/v1` API) and a public static site (`site/`):

| Person | What they do in the product | Where it lives in code |
|---|---|---|
| Solo teacher | Keeps one list of students, seats them in batches (classes), sets fees, takes attendance, records marks, verifies payments, sends reminders, records expenses | `app/students`, `app/batches`, `app/fees`, `app/teaching`, `app/marks`, `app/expenses`, `app/analytics` |
| Coaching centre | An organisation-owned workspace: managers, member teachers, rooms, a timetable, staff records and payroll | `app/centres`, `app/staff`, `app/teaching/assignment.py`, `app/payroll` |
| Student | Accepts the seats a teacher recorded for them, sees classes, calendar, fees, results, pays | `app/accounts/decisions.py`, `app/fees/payables.py`, `app/api/me.py`, `/v1/me/*` routes |
| Guardian | Accepts seats recorded with their number, sees each child's dashboard, fees and results, pays for several children at once | `app/guardians`, `app/fees/submissions.py`, `/v1/children/*`, `/v1/guardian/*` |
| Platform administrator | Aggregate counts, teachers and centres by name, help tickets; never a student's or guardian's data [TC-14, D-6] | `app/admin`, `app/help`, `app/api/admin*.py`, `web/src/admin` |

There is no subscription billing: the app charges nobody (team.md, Way of Working, amended 2026-10-22). Money in the product is the tuition fee a family owes a teacher, recorded and verified, never moved by the app.

## Core business concepts

- **Account** — an identity keyed on a phone number, an email address, or both (`account.phone`, `account.email`, CHECK `ck_account_has_identifier`). It has **no role column**: what a person may do is a *lens* computed per request from owned batches and accepted seats (`app/authz/resolve.py`).
- **Lens** — teacher, student, guardian, invitation, membership, class-teacher, examiner, platform-admin (`app/authz/lenses.py`). Every authenticated route depends on one; a CI gate fails on a route that resolves none (`app/contract/routes.py`).
- **Student record and seat** — a teacher records a student (`student`: name, student phone, guardian phone) and seats them in batches (`enrollment`, one per batch). The seat carries both links (student and guardian account) and a per-link decision `pending | accepted | declined` [BR5.1, ADR-013].
- **Invitation / acceptance** — linking an account to a seat by number is *not* consent. The holder accepts or declines; only an accepted link grants a student or guardian lens (`app/authz/invitations.py`, `app/accounts/decisions.py`).
- **Profile** — what a person writes about themselves (self-chosen name, address). Owner-private, protected by PostgreSQL row-level security and by a schema-wide privacy gate (`app/contract/privacy.py`).
- **Fee cycle and ledger** — a monthly cycle per seat, an append-only ledger of seven entry kinds, carry-forward, partial approval and waiver; money is a decimal value type confined to `app/money` (see `architecture.md` and `component-inventory.md`).
- **Session, attendance, topic, announcement, exam, mark** — the teaching record (`app/teaching`, `app/marks`).

## Identity and sign-in as built today (the area this intent changes)

- **Sign-up is verify-first** [C-07]. `POST /v1/accounts` stores a draft (`pending_signup`) keyed on a phone or an email and sends a code; the account, profile, and (for a teacher) owner row are created only when `POST /v1/auth/verify` accepts that code (`app/accounts/service.py:complete_signup`). Every number gets the same 201, so sign-up is not an existence oracle.
- **Sign-in is by password** [0032]. `POST /v1/auth/password` takes exactly one of `phone`/`email` plus a password. A code never signs anyone in: a verified code yields a password-setup token; `POST /v1/auth/password/setup` turns it into a session. Accounts with an authenticator factor take a second step (`POST /v1/auth/mfa`).
- **Phone and email can be added later**, once each, never replaced or removed (`app/accounts/contact.py`, `POST /v1/me/contact` + `/verify`).
- **Teachers record phone numbers only.** Students, guardians (`student`, `enrollment`) and centre invitees (`owner_member.invited_phone`) are recorded by number. When an account is created on a number, or a number is added to an account, the seats and centre invitations recorded against it are linked (`link_phone_seats`). Adding an **email** links nothing.
- **There are no usernames** in the schema, the API, the clients or the migrations.
- **There are no dormant teacher-created accounts** any more. The `Account` docstring still says "Created dormant when a teacher records a number" (`app/db/models.py:452`), but no code path does that: teacher-recorded people exist only as numbers on `student`/`enrollment`/`owner_member` until they sign up. See `code-quality-assessment.md`.

## Constraints that shape every change

Recorded once here; enforcement mechanisms are in `code-quality-assessment.md`.

- Children's data: a Play Families-track app handling phone numbers, attendance and marks [RC-1..RC-3]; data encrypted at rest (`infra/modules/database/main.tf:95` `storage_encrypted = true`).
- Nothing a student or guardian writes reaches a teacher [TC-13, D-5]; administrators see no student or guardian data [TC-14, D-6].
- No device or advertising identifier is ever transmitted; the device phone number is never read [TC-3, TC-4, D-35, D-37].
- No existence oracle: OTP issue, sign-up and password sign-in answer known and unknown identifiers identically [BR2.7].
- Bangla and English strings from the first screen (1,539 strings in each Android bundle).
- Infrastructure spend under USD 50/month [OC-4].
- Solo build: one developer-reviewer, so important rules are mechanical (team.md, Way of Working).

## Delivery state (inferred from git history and docs)

The planned units D1–D6 (acceptance, roster, fees, teaching, insights, deletion) have shipped, followed by coaching centres, staff, payroll, expenses, extra fees, help centre, two-step verification (`0028`), verify-first sign-up (`0031`), email identity and passwords (`0032`), class-change notifications (`0033`) and an improvement sprint driven by the 2026-11-11 reviews (`docs/reviews/2026-11-11/`). `CHANGELOG.md` states nothing is released to the Play Store yet.
