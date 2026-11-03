# Payment methods, pay-any-time, payment review, money reports and the progress dashboard — design

Date: 2026-11-02
Status: draft for approval
Branch: `feat/payment-methods-and-progress`
Mockups: claude.ai artifact `4FxavKBTVdygsp8jzpLiYj` (boards P1–P3, F1–F5,
R1–R4, M1–M3, D1–D2), approved by the owner as drawn on 2026-11-02.

## Why

1. A teacher's payment destination lives on each batch as one number and
   one channel (`batch.collection_number`, `batch.collection_channel`). A
   teacher with three batches types the same bKash number three times,
   cannot offer a second service, and cannot offer a bank account at all.
2. A student or guardian can only pay when a fee is due
   (`submit_claim` raises `NoOpenCycle`), and the payment screen shows no
   way to pay otherwise.
3. The claim form has no date of payment, no payer note and no bank
   shape, and a guardian with two children in one batch must submit two
   claims for one transfer.
4. The teacher has no view of collections over months, per batch or per
   student, and no per-student dashboard of attendance and marks.

Success: a teacher sets their payment methods once in More; any family
member pays any time through any of them, for one or several children in
one transfer; the teacher approves or rejects with a note from the
notification; and teacher, student and guardian each see the same
progress dashboard for a seat.

## Goals

- Teacher-level payment methods: mobile banking (service picked from
  bKash, Nagad, Rocket or typed, number, optional note) and bank (account
  number, account name, bank name, branch name, optional note). Every
  batch the teacher owns uses the same list.
- Students and guardians always see **Send money**, choose a method, see
  its details, and submit: batch, the child or children it covers,
  amount, date paid, transaction ID (mobile) or from-account (bank), and
  an optional note.
- One submission may cover several children of one guardian in one
  batch. The total is not split by the payer.
- A payment when nothing is owed is accepted and becomes credit.
- The teacher gets an inbox notification per submission, opens its
  detail, and approves or rejects with an optional note. A short payment
  keeps carry-forward or waive; for several children the teacher picks
  which child carries the shortfall (or receives an over-payment's
  credit).
- Teacher reports: collected vs charged over months for one, several or
  all batches; one batch in one month; one student over months.
- One progress dashboard (attendance by month, exam marks over time with
  the batch average and highest, fee months) for the teacher, the
  student and the guardian.

## Non-goals

- Verifying a transaction against bKash, Nagad, Rocket or a bank. The
  teacher still checks by eye.
- Payment gateways, QR codes, uploaded receipt photos.
- Refunds, or moving credit between children after the decision.
- Changing how fee cycles are generated or how credit is applied at
  generation (`apply_available_credit` already spends credit first).
- Cross-teacher or cross-batch views for families.

## Anti-goals

- The client computing a split, a shortfall, a balance, a fee state or
  an average. The server sends every one of them [TC-9, D-31].
- A payer naming whom a teacher's decision charges. Only the teacher
  chooses which child carries a shortfall.
- Any student or guardian seeing another family's names, amounts or
  marks. The batch highest is shown as a number only.
- A float anywhere on the money path [TC-7, D-20].
- Editing or removing a method silently rewriting a past payment.

## Constraints

All of `aidlc/spaces/default/memory/` applies. The ones that bite here:

- Money arithmetic lives in `app.money` only, with 100% branch coverage
  and the ledger property test. The multi-child allocation is money
  arithmetic, so it lives there [D-20, PU-5.6].
- Every new route names its lens; `PUBLIC_ROUTES` does not grow.
- The payment destination today reaches exactly one response, asserted
  by `tests/contract/test_collection_number.py`. That rule moves with the
  data (see "Who sees a method").
- Test-first where the answer is knowable and a wrong one is a money or
  authorization error: the allocation, the decision, credit with nothing
  owed, every lens check below.
- Every new string in English and Bangla; ViewModel state-machine tests
  and money-model serialization tests on Android.

## The parts, as decided

### Payment methods (teacher) — P1, P2, P3

A new table `payment_method`, keyed on `owner_id` like `batch`:

| column | notes |
|---|---|
| `id` | |
| `owner_id` | FK `owner`, cascade |
| `kind` | enum `mobile` \| `bank` |
| `provider` | mobile: service name (any text, ≤32); bank: bank name |
| `mobile_number` | mobile only; canonical `01XXXXXXXXX`, as `account.phone` |
| `account_number`, `account_name`, `branch_name` | bank only |
| `note` | optional, ≤200 |
| `position` | display order |
| `retired_at` | set on remove; a retired method is hidden but kept |
| `created_at`, `updated_at` | |

`CHECK` constraints enforce the kind's required fields and forbid the
other kind's. The service list offered by the dropdown (`bKash`,
`Nagad`, `Rocket`) and the bank suggestions are server-supplied, so
adding one is data, not a release.

Routes (teacher lens, scoped to the lens's owner):

- `GET /v1/payment-methods`
- `POST /v1/payment-methods`
- `PATCH /v1/payment-methods/{method_id}`
- `DELETE /v1/payment-methods/{method_id}`: sets `retired_at`

Remove is a retire, because past claims reference the method. Editing a
method never changes a past claim: each claim stores a copy of the
details it was paid to (`destination_snapshot`, below).

**Migration of the old field.** Migration `0013` inserts one `mobile`
method per distinct `(owner_id, collection_number, collection_channel)`
across that owner's batches, then the app stops reading the batch
columns. The columns stay for one release and are dropped in a later
migration, so a rollback to the previous image still finds them. The
batch create/edit forms stop offering the field.

### Who sees a method

- The owner's teacher lens sees all of its own methods.
- A student or guardian sees the methods of the teacher who owns a batch
  they hold an **accepted** seat in, through
  `GET /v1/me/enrollments/{enrollment_id}/payment-methods` and
  `GET /v1/children/{enrollment_id}/payment-methods`. These replace the
  two `payment-destination` routes.
- No other response carries a method's number or account fields. The
  collection-number allowlist test is rewritten to assert exactly these
  three routes carry them, as an equality, so the field spreading to a
  fourth fails the build.
- No method: the list is empty and the copy says to ask the teacher.

### Paying (student, guardian) — F1 to F5

**F1** always shows **Send money**, with the owed figure and month list
the server already sends. **F2** lists the methods. **F3/F4** show the
chosen method's details and the form.

A new table `payment_submission` holds what the payer sent, once:

| column | notes |
|---|---|
| `id` | |
| `batch_id` | every child it covers is in this batch |
| `payment_method_id` | FK, `SET NULL` |
| `destination_snapshot` | JSON copy of the method's shown fields at submit time |
| `total_amount` | `NUMERIC(12,2)`, > 0 |
| `paid_on` | date; not after Bangladesh's today, not before the oldest seat's join date minus 60 days |
| `transaction_id` | mobile: required, ≤64 |
| `from_account` | bank: required, ≤120 |
| `payer_note` | optional, ≤500 |
| `submitted_by_account_id`, `submitted_at` | |
| `status` | `pending` \| `approved` \| `rejected` |
| `decision_note` | the teacher's note on approve or reject, shown to the family |
| decision columns | `decided_by_account_id`, `decided_at`, `previous_decision` (correction, as today) |

Each child covered gets one `payment_claim` row with a new
`payment_submission_id` FK. The ledger stays enrollment-level and
unchanged in shape; the existing claim, receipt, carry and credit code
keeps doing the per-child work.

`POST /v1/payments` (student or guardian lens):

```json
{ "enrollment_ids": ["…"], "payment_method_id": "…",
  "amount": "2000.00", "paid_on": "2026-11-01",
  "transaction_id": "9KD7Q2XL1M", "from_account": null,
  "note": "November fee" }
```

Refused unless:

- every `enrollment_id` is reachable by the lens and accepted: a student
  only their own seat; a guardian only their own children;
- all are in one batch, and the method belongs to that batch's owner and
  is not retired;
- exactly one of `transaction_id` / `from_account` is present, matching
  the method's kind.

The form's **For** field is a multi-select of the guardian's children in
the chosen batch. A student sees their own name, fixed. The line "Owed
for Tanvir and Tania: ৳2,000" comes from the server.

**Pay when nothing is owed.** `submit_claim` stops raising
`NoOpenCycle`. A claim with no unpaid cycle resolves to Bangladesh's
current period. On approval its receipt is capped at that period's
charge, which may be zero, and the rest becomes `credit_grant`. The next
generated cycle spends it through the existing `apply_available_credit`.

**Duplicate transaction IDs** keep today's check (`duplicate_of`),
compared per submission rather than per child row.

### Reviewing a payment (teacher) — R1 to R4

One inbox notification per submission (`_tell_the_teacher` moves to the
submission). The queue (`GET /v1/claims/queue`) returns submissions:
children, batch, total, what they owe together, method, reference, date
paid, submitted at, who sent it (student or guardian, and the number the
teacher holds), note and `duplicate_of`.

- `GET /v1/payments/{submission_id}`: detail (R2)
- `POST /v1/payments/{submission_id}/approval`:

  ```json
  { "received_amount": "1500.00",
    "shortfall_disposition": "carried",
    "carried_by_enrollment_id": "…",
    "credit_to_enrollment_id": null,
    "note": null, "correcting": false }
  ```

- `POST /v1/payments/{submission_id}/rejection`:
  `{ "note": "…", "correcting": false }`

The labels the family and the teacher see are **Payment done** (approved
in full or in part) and **Rejected**, with the teacher's note.

**The allocation** is a pure function in `app.money`. It takes the
received amount, each child's owed figure in the order the server lists
them, the disposition, and the chosen child. It returns each child's
approved amount, which child absorbs the shortfall, and which receives
credit:

1. **Received = owed together:** each child is approved at what they
   owe. No choice is asked (R2 shows only Approve).
2. **Received < owed (short):** the teacher must pick carry or waive. For
   more than one child they must also pick the child who carries it. The
   other children are paid in full in list order first; the chosen child
   gets what is left. If the shortfall is bigger than the chosen child's
   owed figure, the rest falls on the remaining children from the end of
   the list. Waive uses the same allocation and forgives instead of
   carrying.
3. **Received > owed (over):** every child is paid in full. For more
   than one child the teacher picks who gets the excess as credit. One
   child gets it automatically.
4. **One child:** exactly today's behaviour, so every existing
   verification test still holds.

Invariants, asserted by a Hypothesis property test: the approved amounts
sum to `received_amount`; no child is approved more than they owe except
the credit child; shortfall plus received equals owed together when
short.

The approval then calls the existing per-claim verification for each
child row in one transaction, with that child's approved amount and, for
the carrying child only, the disposition. The concurrency guard
(conditional update on the decision) moves to the submission row, so
two simultaneous approvals still conflict. A correction undoes every
child row's entries, then writes the new decision, as `verify_claim`
does today.

### Money reports (teacher) — M1, M2, M3

All figures are computed on the server from the ledger fold. Cash in is
`receipt + credit_grant`, never `credit_apply`, as the analytics module
already defines it.

- `GET /v1/analytics/collections?batch_id=…&batch_id=…&months=6`: per
  month, charged, collected and outstanding, plus the two summary tiles.
  No `batch_id` means all of the lens's batches. The current month is
  flagged `in_progress`.
- `GET /v1/batches/{batch_id}/fees` (exists, current period only):
  gains an optional `period=YYYY-MM`, collected/charged for that month,
  a state count per filter (paid, checking, owed), and each seat's
  state and one-line detail for that month.
- `GET /v1/enrollments/{enrollment_id}/fees` (exists): extended with the
  last N months' states for the strip and each month's claim history
  line, including the teacher's decision note.

### Progress dashboard (all three lenses) — D1, D2

One response shape, three routes:

- `GET /v1/enrollments/{enrollment_id}/dashboard` (teacher)
- `GET /v1/me/enrollments/{enrollment_id}/dashboard` (student)
- `GET /v1/children/{enrollment_id}/dashboard` (guardian)

Query: `range=6m|year|all`. Response:

- `tiles`: attendance percent with present/held counts, exam average
  percent with direction, owed now.
- `attendance_by_month`: `{period, held, present, percent, in_progress}`.
  Cancelled classes are not counted as held.
- `exams`: `{exam_id, title, date, subject, marks, total, percent,
  batch_average, batch_highest}`.
- `fee_months`: `{period, state}` using the existing five payment states.

**Average and highest.** Both are numbers, never names. They are sent
only when the batch's marksheet comparison is published to families
(`Batch.marksheet_visible`, the same rule `batch_average` follows today)
**and** at least 3 seats have a mark for that exam. Otherwise both are
`null` and the chart draws only the student's line. The teacher lens
always gets them when 3 or more are marked.

Families see only seats their lens reaches. The guardian screen's child
switcher and batch picker list only those.

### Android

New or changed screens, mapping to the boards:

- `feature/paymentmethods`: P1 list (More), P2/P3 editor
- `feature/pay`: F1 change (always Send money), F2 method list, F3/F4
  form with batch and child pickers, F5 sent
- `feature/verify`: R1 queue grouped by submission, R2 detail with note,
  R3 decided, R4 approval sheet with carry/waive and child picker
- `feature/collections`: M1, M2, M3
- `feature/dashboard`: D1/D2, one composable, fed per lens

Each ViewModel ships state-machine tests; every new money model ships
the decode-from-string / fail-on-number test.

## Order of work

1. Migration 0013: `payment_method`, `payment_submission`, new columns on
   `payment_claim`, data move of the collection numbers.
2. Allocation in `app.money`, test-first, with the property test.
3. Payment-method routes and the rewritten allowlist test.
4. Submission, then approval and rejection, test-first, including
   concurrency and correction.
5. Reports, then the dashboard reads.
6. Android: methods, pay, review, reports, dashboard, in that order.
7. OpenAPI schema regenerated and committed at each API step.

## Calls Claude made (owner to confirm while reading)

1. If a short payment's shortfall is bigger than the chosen child's fee,
   the remainder falls on the other children from the end of the list.
   This only arises with three or more children or a very short payment.
2. An over-payment for several children asks the teacher which child
   gets the credit.
3. Removing a method retires it; history keeps the details as they were
   when paid.
4. `paid_on` can't be in the future or more than 60 days before the
   seat's join date.
5. The old batch payment-number columns are kept for one release, then
   dropped.
6. Today a family can pick `cash` as the channel (`CHANNELS` in
   `app/fees/claims.py`). F2 keeps it as a built-in **Cash in hand**
   choice under the teacher's methods, with no details, amount, date and
   note only. A claim's `channel` becomes the method's provider name (or
   `cash`), so the column stays filled for history and the queue.
