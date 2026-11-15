# Functional Design Questions — U4 web-identity

Unit `web-identity` (U4, kind `ui`). These are the six corners the
requirements, the contracts, the two built backends and the built Android
counterpart (U3) leave open for the web client. Everything else is settled
by FR1–FR11, C1, C2 and U3's design, and is written into `functional-spec.md`
directly, with each place the web deliberately differs from U3 named there.

The person instructed: "don't wait for my approval. Go with your
recommendations." Every answer below is the recommended option, A.

## Q1. How the live username availability check behaves while typing

FR3.1 asks for a live check; FR3.2 puts it behind tight ceilings (Family A,
30 per /64 per hour, sized by U1 on the assumption that clients wait at
least 500 ms after typing); FR11.3 forbids a client hint that refuses what
the server accepts. The web has `fetch` with `AbortController`, and its
`send()` (`web/src/api/client.ts`) rethrows only a reason-less `AbortError`.

A. U3's rule, on the web's primitives. No client copy of the FR1 rules. The
   trimmed text is sent to the lookup 500 ms after the last edit, only when
   non-empty. At most one lookup is in flight; a newer one aborts the older
   through its `AbortController`. An answer is applied only if it is for the
   text still in the field (latest wins). Answers are remembered per text for
   the life of the mounted form. Each lookup is bounded at 3 s. A 429 stops
   all further lookups from that form. A refused, failed or timed-out lookup
   reads "could not check" and never blocks submission. The checker decides
   "superseded", "timed out" and "failed" from its own flags, never from the
   error's type.
B. Mirror the FR1 rules on the client to skip lookups for names that are
   certainly invalid.
C. Check only on blur.
D. Check only on submit; no live check.
E. Let superseded lookups finish instead of aborting them, and drop their
   answers.
X. Other (please specify)

[Answer]: A

## Q2. Where the choose-username gate sits, how it cannot be bypassed, and when it lifts

FR5.2: shown after sign-in, before anything else, not dismissible except by
choosing a name or signing out. On the web, `App.tsx` already returns
`LensPicker` before mounting `<Routes>` when the session is `choosing`. Unlike
Android, a failed `GET /v1/me` already shows a blocking error card with Retry
(`session.state === 'failed'`), not the app. U3's review round found that a
gate which lifts on its own write, rather than on a read, can be left on a
dead screen.

A. A new session state `username-required` carrying the account read. The
   session provider produces it whenever a successful read says
   `username_required: true`. `App` returns the full-page gate for that state
   before the lens picker and before any route is mounted. Typed URLs,
   browser Back and Forward, and deep links therefore cannot reach a screen
   while the gate shows. The gate lifts only when a later `GET /v1/me` says
   the flag is false. After a 200 from `PUT /v1/me/username` the gate
   re-reads; it never lifts on the write's answer alone. A failed read keeps
   the existing blocking error card, so the web fails closed and needs no
   periodic re-check. While the gate shows, the tab re-reads when it becomes
   visible again, so a name chosen in another tab lifts the gate here.
B. A route `/choose-username` with a redirect from every other route while
   the flag is true.
C. A modal dialog over the home screen.
D. A dismissible banner like the set-password prompt.
E. As A, but lift the gate at once on the 200, as U3 does.
X. Other (please specify)

[Answer]: A

## Q3. How Settings presents the contacts, and the rule about the last one

FR8.2 and FR8.4: replace or remove after the password, refused for the last
contact. FR11.3: the client does not decide whether a contact may be removed.
On the web the sign-in rows live in Settings → Account (`AccountEntries.tsx`),
which today shows "Add phone number" or "Add email" only when one is missing.

A. U3's layout, placed where the web keeps these rows. Settings → Account
   gains a Username row and one "Phone and email" row. These replace the two
   Add rows. "Phone and email" opens a Contacts screen listing both kinds. A
   present contact shows Replace and Remove. An absent one shows Add, which
   is the existing add flow. Remove is offered for every present contact, the
   last one included; the server's `account.contact.last_one` explains a
   refusal. Replace and Remove ask for the current password. An account the
   server says has no password sees a note linking to set one, and its
   actions stay enabled, so the server's refusal decides.
B. Separate Settings rows per contact, each with its own screen.
C. As A, but hide Remove when only one contact remains.
D. As A, but disable Replace and Remove when `has_password` is false.
E. Put the rows in More instead of Settings, as Android does.
X. Other (please specify)

[Answer]: A

## Q4. The web has no edit-student form at all

FR6.1: a teacher may enter a student email and a guardian email when they
"record or edit" a student. Android's U3 added both fields to an existing
`EditStudentDialog`. The web defines `updateStudent`
(`web/src/features/teacher/people/api.ts:36`) but no screen calls it. A web
teacher cannot correct any recorded contact today. Without an edit form, a
mistyped email can be fixed only by removing the student, which removes the
student's record. Meanwhile the wrong address can link a seat, as a pending
invitation, to whoever verifies it (FR6.5).

A. Add an "Edit" sheet on the student detail screen
   (`features/teacher/people/StudentDetail.tsx`) with the fields U3's dialog
   has: name, student phone, guardian phone, student email, guardian email.
   It uses U3's patch semantics: an unchanged field is omitted; a changed
   value is sent; an emptied email sends `null` to clear it. An emptied phone
   also sends `null` to clear it, which the schema documents. *Amended after
   review R-04*: the first draft treated an emptied phone as unchanged, as
   Android does, but the web has no existing behaviour to keep. The refusals
   `student.email.taken`, `student.number_accepted` and
   `student.number_erased` are shown in the sheet.
B. Add the email fields to the create form only, and record editing as a gap
   for a later unit.
C. An edit sheet with the two email fields only.
D. Allow inline editing in the students list.
X. Other (please specify)

[Answer]: A

## Q5. Whether sign-up calls the already-added lookup for an email

U2 built `GET /v1/accounts/already-added?email=` (FR6.7). The web's
`SignUp.tsx` asks only for a phone, and its header comment says so ("An email
address is never looked up; the route answers for numbers only"). That
comment has been false since U2 merged. U3 answered the same question with
"include it".

A. Include it, as U3 did: when the email field is left holding an address
   the shared email check accepts, the same lookup runs with `email`, with the
   phone lookup's exact behaviour: once per value, the role locked on a seat,
   nothing named, and never blocking submission. The stale comment is
   corrected.
B. Leave it out; record it as a gap.
C. Run it on submit only.
X. Other (please specify)

[Answer]: A

## Q6. The batch quick-add cannot record an email

The web's batch roster "Add student" (`features/teacher/students/AddStudent.tsx`)
posts `EnrollmentCreateRequest`, which carries no email field in
`openapi.json`. C2 added emails to `StudentCreateRequest` and
`StudentUpdateRequest` only. The quick-add also makes the student phone
mandatory on the client ("the student's phone is required (they sign in with
it)"). The server's request schema does not require it.

A. Leave the quick-add's request shape unchanged, because the contract offers
   nothing to send. Change nothing else about the quick-add's required
   fields. Add one link on the quick-add, "Record by email instead". It opens
   the existing People → New student form with this batch preselected
   (`?batch=`, already supported), which can record emails (FR6.1). Record
   the contract gap for U2, which owns C2.
B. Relax the quick-add's client-side phone requirement as well.
C. Add email fields to the quick-add and send them anyway.
D. Change nothing on the quick-add.
X. Other (please specify)

[Answer]: A

## Assumptions & Open Questions

- [assumption] The person's instruction ("don't wait for my approval. Go with
  your recommendations.") applies to every question here, so each answer is
  the recommended option A, with its reasoning carried into
  `functional-spec.md`.
- Open questions: None.

## Sources

- Unit: `inception/units-generation/unit-of-work.md` § U4 and § U3.
- Requirements: `inception/requirements-analysis/requirements.md` FR3, FR5.2,
  FR6.1, FR6.5, FR6.7, FR8.2, FR8.4, FR11.1–FR11.3.
- Contracts: `inception/contract-design/contract-summary.md` C1 and C2;
  `openapi.json` (`EnrollmentCreateRequest`, `StudentUpdateRequest`,
  `MemberResponse`).
- U3 reference: `construction/android-identity/functional-design/functional-design-questions.md`
  Q1–Q5; `code-generation/code-summary.md` (review round 1).
- Code read: `web/src/App.tsx`, `web/src/session/session.tsx`,
  `web/src/api/client.ts`, `web/src/features/auth/SignUp.tsx`,
  `web/src/features/account/security/AccountEntries.tsx`,
  `web/src/features/teacher/people/api.ts`,
  `web/src/features/teacher/students/AddStudent.tsx`.
