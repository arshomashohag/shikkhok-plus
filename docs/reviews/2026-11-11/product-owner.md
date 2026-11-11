# Product Owner review: new and improved features (2026-11-11)

Branch `claude/app-improvement-analysis-2ee6ym`. Analysis only. I checked every
claim of "missing" or "absent" below with a grep against `app/`, `web/src/` and
`android/src/main/`. Where a claim depends on an assumption, the claim says so.

## 1. What the product does today

ShikkhokPlus is a tuition ledger with three per-request lenses: teacher,
student and guardian. A teacher or coaching centre creates batches and adds
students by typing names and phone numbers (`app/api/students.py`,
`app/api/batches.py`). A family member who signs up with that number accepts
or declines the seat (`app/api/accounts.py:297` onward). Each night a cron job
generates monthly fee cycles idempotently
(`infra/modules/app/user_data.sh.tftpl:688`). Families report bKash, Nagad or
bank payments with a transaction id and duplicate detection
(`app/schemas/fees.py:305`). Teachers approve, part-approve or reject them, or
record cash themselves, and every outcome lands in the family's inbox
(`app/notifications/inbox.py:52-85`). The remaining modules are:

- Classes: schedule, calendar, cancel and reschedule (`app/api/teaching.py`).
- Attendance and topic log, with a two-path offline queue on Android only
  (`android/.../core/queue/QueuedWrite.kt`, NFR5).
- Exams, marks, marksheets and progress (`app/api/marks.py`).
- Cross-batch dues with bulk in-app reminders (`app/api/fees.py:862`,
  `web/src/features/teacher/Dues.tsx`).
- Extra fees, expenses and a money summary (`app/api/expenses.py:199`).
- Coaching centres: members, staff, rooms, timetable and payroll.
- Help tickets, MFA, email and phone sign-up, and both deletion paths
  (`app/api/deletion.py`).
- A read-mostly admin console (`app/api/admin.py:116-285`).

Web and Android are at near parity. The gaps are in what leaves the app.
Nothing can be exported, printed or shared (no `text/csv`,
`Content-Disposition`, `window.print`, `navigator.share`, `wa.me` or
`ACTION_SEND` anywhere). Families who never accepted their seat cannot be
reached at all, because in-app reminders skip them (`app/fees/reminders.py:202-203`).

## 2. Findings

Effort: S is under half a day, M is one to two days, L is more than two days.
In the "Hard constraints" column, "Yes" means the item respects all of them:
no client business logic, money as decimal strings, no device identifiers, no
new offline writes, Bangla and English strings, infra spend under USD 50 a
month, and children's data rules.

| ID | Title | Type | User value | Evidence | Effort | Hard constraints |
|---|---|---|---|---|---|---|
| PO-1 | Tell families when a class is cancelled or rescheduled | improve | High. A cancelled class is a common daily event, and today a family finds out only by opening the calendar | `cancel_session` at `app/teaching/sessions.py:307-330` and `reschedule_session` at `:265` commit without calling `deliver(...)`. The inbox kinds at `app/notifications/inbox.py:52-85` include no class kind | S | Yes. In-app plus best-effort FCM. Uses message keys, not English text |
| PO-2 | Share a dues reminder or seat invite from the teacher's own phone (WhatsApp or SMS share sheet) | new | High. Reaches families with no accepted account, whom in-app reminders skip. Costs no SMS gateway money | `app/fees/reminders.py:202-203` skips seats "with nobody who has accepted". No share mechanism exists in either client (grep above). The teacher already holds the typed numbers (`app/schemas/students.py:148-149`) | S–M | Yes, if the server composes the amount and periods and the client only renders them. Nothing passes through the SMS gateway (NFR12.1, OC-4) |
| PO-3 | Printable or shareable money receipt for each approved or recorded payment | new | High. Bangladeshi families expect a money receipt, and centres need one for paperwork and disputes | No receipt route or screen. `PaymentsResponse` (`app/schemas/guardian.py:148-162`) is a monthly roll-up with no per-payment reference | M | Yes, as an HTML print view. A server-rendered PDF stays out of scope for V1 (`.../261016-.../requirements-analysis/requirements.md:309`) |
| PO-4 | CSV export of dues, collections and expenses | new | Med–High. Centres reconcile in spreadsheets and with accountants. Today they copy figures by hand | Dues `app/api/analytics.py:139`, collections `:228`, expenses `app/api/expenses.py:112`. No CSV response type exists anywhere | S each | Yes. The server writes the CSV, money as fixed-point text. Leave out phone numbers, and declare the export in the privacy policy (children's data) |
| PO-5 | Web teacher toggle for marksheet visibility | improve | Med. Parity: a web-only teacher cannot turn the shared marksheet on or off | Endpoint `app/api/marks.py:534-539`. Android calls it (`android/.../core/network/HttpMarksRepository.kt:266`). Web code never calls it; `marksheet_visible` appears only in test fixtures | S | Yes |
| PO-6 | Web sign-up "already added" notice | improve | Med. A family signing up on the PWA is not told a teacher already added them, which is the hook into accepting the seat | Route `app/api/accounts.py:252`. Android uses it (`android/.../feature/auth/SignupStateMapper.kt:38`). No reference in `web/src` outside `schema.d.ts` | S | Yes. The notice must name neither the teacher nor the batch, as Android does (`SignupScreen.kt:116`) |
| PO-7 | Automatic due reminders, opt-in per batch, N days after `fee_due_day` | new | High for a tutor with 5 or more batches. Today every reminder needs a tap | The cron exists (`user_data.sh.tftpl:688`), as do `Batch.fee_due_day` (`app/db/models.py`, Batch) and the 24-hour throttle (`app/fees/reminders.py:76`) | M | Yes in-app or FCM only. Needs a product decision: the earlier rationale says "a reminder is re-sendable by a person" (`app/notifications/fcm.py` docstring) |
| PO-8 | Absence alert to the guardian, opt-in per batch | new | Med–High. Parents of school-age children value same-day absence news | No absence notification kind (`inbox.py:52-85`). The family spec lists "per-kind muting" as a non-goal (`docs/superpowers/specs/2026-10-31-...md:45`), so the switch would have to belong to the teacher and the batch | M | Yes. Attendance writes from the Android offline queue arrive late, so the alert has to fire on server commit, not on the device |
| PO-9 | Payroll pay basis "share of collected fees" | new | Med for centres that pay teachers a percentage | Deferred as D12 at `docs/superpowers/specs/2026-11-06-fees-expenses-and-staff-design.md:278` | L | Yes, but it is money-module work: test-first with 100% branch coverage |
| PO-10 | Inbox forward compatibility for new kinds | improve | Med. This is the precondition for PO-1, PO-7 and PO-8 | Both clients drop unknown kinds (`web/src/features/account/area/mappers.ts:63`, `android/.../inbox/InboxMapper.kt:25`), but the server's `unread` count still includes them. An old Android install would show a badge with no message behind it | S | Yes |
| PO-11 | Admin console can act, not just read: suspend a teacher account | new | Low–Med. Needed before open launch to handle abuse or fraud reports | `app/api/admin.py:116-285`: reads plus help-ticket writes only | M | Yes, provided admin sees subscriber info only (TC-14). Suspension must not expose child data |
| PO-12 | Account holder data download | new | Low–Med. Matches the deletion summary that already exists (`app/api/deletion.py:600`), with good faith for children's data | No export route | M | Needs care: the guardian lens only, never teacher-written private notes. Defer unless the privacy policy requires it |

Not findings: three things I checked on purpose that a reader might assume are
missing.

- **"Mark everyone present" exists on web** (`SessionScreen.tsx:467`). On
  Android a seat with no mark opens as present (`AttendanceStateMapper.kt:130`).
- **Per-seat fee override exists** (`Enrollment.fee_amount`).
- **Student search exists** (`q` at `app/api/students.py:96`).

## 3. Top 5 recommendations, ranked

The ranking favours value per developer-hour, with backend and web landing
first. **Android caveat:** this environment has no Android SDK
(`ANDROID_HOME` is unset), so Kotlin changes cannot be compiled or tested here.
Each item marks its Android part as a follow-up for a machine that has the SDK.

### R1: PO-1 and PO-10: notify families when a class is cancelled or moved (S, about 3h)

Touches backend (`app/teaching/sessions.py`, `app/notifications/inbox.py`,
recipients) and web (`account/area/mappers.ts`, `Inbox.tsx`, bn and en
strings). The Android follow-up is an `InboxKind` value and two string
resources.

- Given a scheduled future session in a batch with an accepted student and an
  accepted guardian, when the teacher cancels it, then each accepted account
  gets exactly one inbox item of kind `class_cancelled` carrying the batch
  name, the session date and `source_id = session_id`, and FCM dispatch runs
  only after commit.
- Given the same session, when the teacher reschedules it, then accepted
  accounts get one `class_rescheduled` item with the old and new dates. A
  second reschedule replaces the earlier item through `remove_for_source`;
  it does not stack a second one.
- Given a seat whose family is pending or declined, when the class is
  cancelled, then that family receives nothing (privacy matches today's
  `seat_recipients`).
- Given a session in the past or already cancelled, when the teacher cancels
  or reschedules it, then the existing error is returned and no notification
  is written.
- Given a client that does not know the new kind (PO-10), when it reads
  `/v1/me/notifications`, then the item is dropped and `unread` excludes
  kinds the client did not announce. Alternatively, a test pins the
  documented behaviour.
- Given the web inbox in Bangla, when it shows either new kind, then the
  title and line come from bn strings with no English fallback.

### R2: PO-2: share a reminder or invite from the teacher's phone (S–M, about 4h, web first)

Touches backend (new `GET /v1/enrollments/{id}/share-text`, or a field on the
dues row) and web (a share action on the Dues rows and on the student
detail). The Android follow-up is an `ACTION_SEND` intent.

- Given a seat owing money, when the teacher asks for share text, then the
  server returns `message_key` plus params: batch name, outstanding as a
  decimal string, oldest and latest unpaid periods, and the teacher's display
  name. It also returns the guardian phone in E.164 if one was typed. The
  client does no arithmetic.
- Given that response on a device that supports `navigator.share`, when the
  teacher taps Share, then the system share sheet opens with the rendered
  text in the current UI language. On other devices a `wa.me` or `sms:` link
  to the typed number is offered.
- Given a pending seat (no accepted account), when the teacher shares an
  invite, then the text carries the app or web sign-up link and names no
  amount. The server asserts this.
- Given a seat that is not this teacher's, when share text is requested, then
  the response is 404/403 under the existing lens rules, and a route-lens
  test covers the new route.
- Given any share, then the SMS gateway adapter is never called. A test
  asserts the gateway mock has zero calls.

### R3: PO-4: CSV export of cross-batch dues, then collections and expenses (S per export, about 3h for the first)

Touches backend (`Accept: text/csv`, or a `?format=csv` variant on
`/v1/me/dues`) and web (a Download button on Dues).

- Given a teacher with dues across batches, when they request the CSV, then
  they get `text/csv; charset=utf-8` with a BOM so Excel renders Bangla. The
  columns are student name, batch, outstanding, oldest unpaid period and days
  late, and the rows are exactly the JSON endpoint's rows in the same order.
- Given money values, then each is written as fixed-point text with two
  decimals (for example `1200.00`). No float appears on any code path, and
  the existing money import gate still passes.
- Given any export, then no phone number, account id or guardian-written
  field appears. A test asserts the header set.
- Given a student-lens or guardian-lens caller, when they request the
  teacher export, then it is refused under the existing lens rule.
- Given a teacher with no dues, then the file contains only the header row.

### R4: PO-3: money receipt for each settled payment (M, about 1 day)

Touches backend (`GET /v1/payments/{submission_id}/receipt` for the teacher
lens, plus a family-lens twin under `/children/{id}/` and `/me/`) and web (a
print-styled receipt page with Print and Share). The Android follow-up is a
view and share action.

- Given an approved, part-approved or teacher-recorded payment, when either
  the teacher or the family opens the receipt, then it shows:
  - a stable receipt number derived from the submission id;
  - payer label, batch, and teacher or centre name;
  - each period covered with the amount applied, plus any credit carried;
  - the approved amount as a decimal string, the method and transaction id,
    and the approval date in Bangladesh time.
- Given a pending or rejected claim, when its receipt is requested, then the
  answer is a `ConflictError`, never a receipt.
- Given a payment approved for less than claimed, then the receipt shows the
  approved figure, not the claimed one.
- Given the web receipt page, when the user prints, then a print stylesheet
  renders one A5-friendly page in the current language. No server PDF is
  generated (PDF export stays out of scope for V1).
- Given a family member of another seat, when they request this receipt,
  then they get 404.

### R5: PO-5 and PO-6: close the two web parity gaps (S, about 2–3h combined)

Touches web only. The backend routes already exist and are tested.

- Given a teacher on the web batch edit screen, when they flip "Share
  marksheet with the batch", then `PUT /v1/batches/{id}/marksheet-visibility`
  is sent. On success the toggle shows the server's returned value. On
  failure an explicit retry prompt appears and no optimistic state is kept
  (TC-8).
- Given an inactive batch, then the toggle is read-only, as the server
  decides.
- Given a family signing up on the PWA with a number a teacher already
  added, when the number is entered, then the web shows the same
  "already added" notice as Android, naming neither the teacher nor the
  batch.
- Given a number nobody added, then no notice is shown, and the response
  timing and shape do not reveal whether the number exists (Forbidden rule
  on OTP and number existence). Verify the existing route upholds this
  before wiring it.

## 4. Decisions that belong to the product owner, not the developer

- **PO-7 (automatic reminders)** reverses the spirit of "a reminder is
  re-sendable by a person". It should be an explicit, recorded decision, with
  the opt-in defaulting to off.
- **PO-8 (absence alerts)** conflicts with the family-screens non-goal of
  per-kind muting. The proposal resolves that with a teacher-owned batch
  switch, but the trade-off should be affirmed.
- **PO-4 and PO-12** move child-identifying data out of the system by the
  user's own action. The generated privacy policy and the Data Safety form
  must declare it before release (RC-4, RC-5).

## 5. Assumptions

- I assume pending (not yet accepted) seats are common enough in closed
  testing to make PO-2 high value. The seed (`app/seed/scenario.py:665-680`)
  models them, but I have no pilot data.
- I did not exercise UI flows. All findings come from reading code, not from
  running the app.
