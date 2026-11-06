# Extra fees, expenses, staff and payroll — design

Date: 2026-11-06
Status: draft for approval (four questions open, each with a proposed default)
Builds on: `2026-11-06-coaching-centre-design.md` (workspaces, managers,
centre teachers, class assignment)

## Why

A coaching centre runs a small business, not only a set of batches:

- it hires teachers and other staff, and pays them;
- it charges more than the monthly fee — an exam fee, sometimes others;
- it spends money on exam paper, question printing and the like, and wants
  that recorded beside what it collects.

A solo tutor needs two of these too: exam and other fees, and a record of
what they spend. A solo tutor has no staff.

Success: a manager runs teachers, staff, pay, fees and spending from one
place; a family can see and pay an exam fee the same way as a monthly fee;
and anyone with a workspace can see, per month, what came in, what went
out, and what is still owed in both directions.

## Owner decisions, 2026-11-06

| # | Decision |
|---|---|
| D7 | A manager adds and manages teachers in a **teacher management console**, inviting a teacher with **name, phone, email and address**. |
| D8 | The **centre pays its teachers**; pay is managed in the app. |
| D9 | Besides the monthly fee, a workspace can charge an **exam fee or other fees**. Approving a payment records **what it is for**. |
| D10 | A centre records **other staff** (names and salary) and **other expenditure** (exam paper, question printing, …). |
| D11 | A **solo tutor** gets extra fees and the expense record, but **no staff or payroll**. |

The app only **records** money. It moves none: fees are paid out of band
and verified, and salaries and expenses are paid outside the app and
written down here. This does not change.

## What exists, and the constraint it sets

The fee system is an append-only ledger per seat (`ledger_entry`), keyed
by `(enrollment_id, period)`, folded by `app.money` through **seven closed
entry kinds** whose balance identity is checked by a property test.
Monthly obligations are `fee_cycle` rows; a payment is a `payment_claim`
settled **oldest month first** (`settle_oldest_first`), and a teacher's
hand-recorded cash is the same claim decided in one transaction
(`app/fees/received.py`).

The constraint this sets: **no eighth ledger kind.** Every design below is
checked against it, and none needs one.

## 1. Extra fees and "payment for" (D9, D11) — solo and centre

### Raising a fee

```
extra_fee        id, owner_id, batch_id, purpose ('exam' | 'other'),
                 label, exam_id NULL, amount Money, due_date,
                 created_by_account_id, cancelled_at, created_at

extra_fee_charge id, extra_fee_id, enrollment_id, amount Money,
                 created_at
                 UNIQUE (extra_fee_id, enrollment_id)

ledger_entry     + extra_fee_charge_id NULL   -- NULL = the monthly ledger, as today
```

- A manager (or solo tutor) raises a fee for a batch: purpose, label
  ("Half-yearly exam fee", "Admission", "Lab materials"), amount, due date,
  and for an exam fee optionally the exam it belongs to. It fans out to
  one `extra_fee_charge` per active, accepted seat, each with its own
  `CHARGE` ledger entry. A seat can be excluded or given a different
  amount before raising; zero is a real waiver, as for monthly fees.
- **Idempotent the same way fee cycles are:** the unique constraint plus
  `ON CONFLICT DO NOTHING`, tested with overlapping concurrent raises.
- `period` on these entries is the month the fee was raised, so monthly
  reports keep working; the fold's key becomes
  `(period, extra_fee_charge_id)`, which `app.money` already treats as
  opaque.
- Only `CHARGE`, `RECEIPT`, `FORGIVENESS`, `CREDIT_GRANT` and
  `CREDIT_APPLY` ever touch an extra fee. **No carry-forward**: an exam
  fee is not a month, so a short payment either stays owed on that fee or
  is waived. That is a new shortfall disposition (`outstanding`) for extra
  fees only — money-path logic, written test-first.
- Held credit is applied to a new extra fee exactly as to a new month,
  `min(available, owed)`, through the existing `apply_credit`.
- Families see each extra fee beside their months, with its label, due
  date and status — status computed by the server, never by the client.

### "Payment for" on every payment

```
payment_claim  + purpose ('monthly' | 'extra')     -- no default
               + extra_fee_charge_id NULL           -- required when purpose = 'extra'
```

- **A family chooses what they are paying for** when they report a
  payment: the monthly fee, or one of their open extra fees. A
  submission that covers both is already split into per-seat shares; each
  share now carries its own purpose.
- **The approver can change it** before approving, and the claim keeps the
  change in `previous_decision`, visible to the family as today.
- A teacher's or manager's hand-recorded payment picks the purpose in the
  same sheet.
- Settlement stays oldest-first **within the chosen purpose**: monthly
  across unpaid months as today, an extra fee against that one fee.
- **Older app builds send no purpose.** The server treats a missing
  purpose as `monthly`, which is exactly today's behaviour, so nothing
  shipped breaks [D-26].
- The column has no database default, on the project's rule that an
  insert must state its decision.

## 2. Expenses (D10, D11) — solo and centre

```
expense_category  id, owner_id, name, kind ('salary' | 'other'),
                  archived_at
                  -- seeded per workspace: Salary, Exam paper, Printing,
                  --   Rent, Utilities, Other; renameable, archivable

expense           id, owner_id, category_id, amount Money, spent_on,
                  payee_text NULL, staff_id NULL, salary_line_id NULL,
                  note, batch_id NULL, exam_id NULL,
                  recorded_by_account_id, created_at,
                  voided_at, voided_by_account_id, void_reason
```

- Recording an expense is one short form: category, amount, date, paid to,
  note. Optionally tagged to a batch or an exam, so "what did the
  half-yearly exam cost against what its fee brought in" is answerable.
- **Append-only, like the fee ledger.** A mistake is voided with a reason
  and re-entered; nothing is edited or deleted. The void stays visible.
- Expenses are **outside the student ledger and outside `ledger_entry`**:
  money out of the workspace is not an obligation of any seat, so it gets
  its own table and leaves the seven-kind identity alone. Amounts are
  `Money`, `NUMERIC(12,2)`, strings on the wire.
- Salary payments (section 4) are written **as** expenses of a
  `salary` category, linked by `salary_line_id`, so the expense total is
  the one source of truth and salary is never counted twice.
- Who: solo tutors and managers. Centre teachers never see expenses.

## 3. Teachers and staff (D7, D10) — centre only

```
staff        id, owner_id, kind ('teacher' | 'other'),
             display_name, phone, email NULL, address (structured, NULL),
             role_label NULL   -- "Receptionist", "Office assistant"
             member_id NULL UNIQUE  -- the owner_member giving app access
             pay_basis ('monthly' | 'per_class' | 'none'), pay_rate Money NULL,
             joined_on, left_on NULL, created_at
```

- **A staff record is what the manager types; app access is separate.**
  `owner_member` (from the centre design) stays the lean, heavily tested
  authorization table. `staff` holds the HR facts. This mirrors the split
  already built for students: `student` is teacher-typed and grants
  nothing; acceptance grants.
- **Inviting a teacher** creates both in one transaction: a `staff`
  record with name, phone, email and address, and a pending `owner_member`
  for the phone. Nothing is reachable until the teacher accepts. A
  teacher's record — and their pay — exists even if they never install
  the app.
- **Other staff** are `kind = 'other'` records with no member: name,
  contact, role label, pay terms. They never get app access.
- Address reuses the existing four-part structured address. Email is new
  personal data in the app: format-checked only, used for nothing yet.
- **Only managers see staff records.** A centre teacher sees no one's
  details, including colleagues'. The OpenAPI-wide schema test is extended
  so no centre-teacher schema carries a staff phone, email or address.
- Leaving: `left_on` ends pay and, if a member is linked, revokes app
  access in the same transaction.

## 4. Payroll (D8, D10) — centre only

```
salary_line  id, owner_id, staff_id, period ('YYYY-MM'),
             basis, rate Money, classes_held INT NULL,
             base_amount Money,
             status ('draft' | 'approved'), approved_by_account_id,
             approved_at, created_at
             UNIQUE (staff_id, period)

salary_adjustment  id, salary_line_id, kind ('addition' | 'deduction'),
                   label, amount Money   -- non-negative; the kind carries the sign
```

- **Monthly**, generated per period for every active staff record with a
  pay basis, idempotent on `(staff_id, period)` like fee cycles.
- **Two pay bases:**
  - `monthly`: the rate is the salary.
  - `per_class`: the rate times the **held** classes assigned to that
    teacher in the period (`session.status = 'held'`,
    `teacher_member_id` = theirs). Cancelled and other teachers' classes
    never count. Computed with the existing `Money.apply_rate`; no new
    money operation.
- **Adjustments** are named additions or deductions (bonus, advance
  recovered, absence), each a non-negative amount with its sign carried by
  its kind — the ledger's own rule.
- **Draft, then approve.** Approval freezes the line: `classes_held` and
  the amounts are stored, so a class edited next month never silently
  changes a salary already approved.
- **Paying** records one or more expenses against the approved line
  (part-payments and advances are normal); the line shows owed, paid and
  remaining, all derived, never stored.
- Payroll arithmetic is money-path code: it lives in `app.money` or calls
  only into it, it is written test-first, and it carries named tests per
  basis and per adjustment kind.

## 5. Where it lives in the dashboard

**Centre manager** (web desktop first, where tables fit):

| Section | Holds |
|---|---|
| Today | as today, centre-wide |
| Timetable | from the centre design |
| Batches, Students | as today, centre-wide |
| **Teachers & staff** (new console) | list with status (invited, active, left); invite a teacher; add other staff; one person's page: contact and address, pay terms, app access (resend, revoke), this week's classes, classes held this month, pay history |
| **Money** | **Approvals** (with "payment for"), **Collections** (as today, now split by monthly and extra), **Fees** (raise and track exam and other fees), **Expenses**, **Payroll** (this month's lines: draft, approve, record payment), **Summary** |

The **Summary** is server-computed per month: collected (by purpose),
spent (by category), net; still owed to the workspace (dues, by purpose);
still owed by the workspace (unpaid salary). Per exam: fee collected
against expenses tagged to it.

**Solo tutor:** the same **Money** section without Payroll, and no
Teachers & staff. On Android as well as web, because solo tutors are
phone-first: raising a fee and recording an expense are short forms.
The staff console and payroll start on web only.

**Centre teacher:** none of this, unless question 2 below says otherwise.

**Families:** extra fees appear beside months on the fees screen; the pay
sheet gains the "payment for" choice.

## Privacy and compliance

- Staff phone, email and address, and salaries, are adults' personal and
  financial data. New `DISPOSITIONS` entries are required (the manifest
  completeness test forces them): staff and payroll are proposed
  retain-with-basis (financial records), with a stated retention period
  decided at Domain Design.
- Email is a new data type in the app; the Data Safety form and the
  generated privacy policy change with it.
- Nothing here gives any teacher-side role sight of anything a student or
  guardian wrote; the `profile` boundary is untouched.

## Delivery order

Extra fees and expenses do **not** depend on centres, so they can ship
first and help every solo tutor now.

| Step | Contents | Needs |
|---|---|---|
| M1 | Extra fees, "payment for", families seeing and paying them | — |
| M2 | Expenses, categories, the monthly Summary | — |
| C1–C2 | Centre foundations, centres and managers (centre design) | — |
| S1 | Teachers & staff console, invite with details, other staff | C2 |
| C3–C4 | Scheduling, centre teachers (centre design) | C2 |
| P1 | Payroll: monthly and per-class, approve, pay as expenses | S1, C3, M2 |

M1 and P1 touch money paths and are test-first throughout.

## Open questions, with proposed defaults

1. **Pay bases.** Default: fixed monthly and per held class. Paying a
   teacher a share of a batch's collected fees is common too, but it ties
   payroll to the fee ledger and is left for later unless you need it now.
2. **Does a centre teacher see their own pay?** Default: yes — a
   read-only "My pay" with their own salary lines and payments, nothing
   else. It is their data, not anyone else's. Say no if you want the
   teacher's access to stay exactly the four things already decided.
3. **Receipt photos on expenses.** Default: not now. Photos add file
   storage and new personal-data handling; a note field covers the
   receipt number.
4. **Who may choose "payment for".** Default: the family when reporting,
   and the approver may change it. The alternative — only the approver
   decides — is simpler for families but hides from them what their money
   was applied to until approval.
