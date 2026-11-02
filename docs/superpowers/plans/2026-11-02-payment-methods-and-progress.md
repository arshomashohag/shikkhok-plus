# Payment Methods, Pay-Any-Time, Review, Reports and Progress Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teacher-level payment methods, a pay-any-time flow covering one or several children, submission-level approve/reject with notes, money reports, and one progress dashboard for teacher, student and guardian.

**Architecture:** A new `payment_method` table hangs off `owner`; a new `payment_submission` table holds what the payer sent once, and each covered child keeps one `payment_claim` row linked to it, so the existing per-claim ledger code (receipt, carry, waive, credit, correction) does the per-child work unchanged. The multi-child split is a pure function in `app.money`. Reports and the dashboard are read-only folds over the ledger, attendance and marks, served per lens.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, pytest + testcontainers + Hypothesis; Kotlin, Jetpack Compose, kotlinx.serialization, JUnit + Turbine.

**Spec:** `docs/superpowers/specs/2026-11-02-payment-methods-and-progress-design.md`

## Global Constraints

- Money is `app.money.Money` only; no `float`/`Decimal` outside `app/money/**`; JSON money is a string; Kotlin uses the `Money` value class.
- `app/money` stays at 100% branch coverage (`fail_under = 100`).
- Every new route resolves a lens; `PUBLIC_ROUTES` in `app/contract/routes.py` does not change.
- Integration tests run as the restricted role (`restricted_session` / `api_client`), never as superuser.
- Python: Sphinx docstrings on every module/class/function (`:param`, `:return`, `:raises`), type hints everywhere, Ruff line length 88 (project override), no inline comments in new code, imports at top.
- Every new user-facing string in `android/src/main/res/values/strings.xml` and `values-bn/strings.xml`; every new error `message_key` in `message-keys.json`.
- After any API change: `make openapi` and commit `openapi.json` (the schema-diff gate fails otherwise).
- Commits are conventional-commit shaped and end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Gate: `make check` green before each commit that touches its scope (`make test` for backend-only tasks, `make android` for Android-only tasks).
- Server vocabulary, verbatim from the spec: method kinds `mobile` | `bank`; submission status `pending` | `approved` | `rejected`; mobile services `bKash`, `Nagad`, `Rocket`; built-in channel `cash` shown as **Cash in hand**; family-facing labels **Payment done** and **Rejected**.
- Average/highest are sent only when `Batch.marksheet_visible` is true for family lenses **and** ≥ 3 seats have a mark for that exam; teacher lens needs only the ≥ 3 rule.

## Review Focus

1. A guardian picks a child whose seat is `pending` or declined, or a child in another batch → 403/422, never a claim row. (Task 4, `test_submit_refuses_unaccepted_or_cross_batch_child`.)
2. The teacher edits or retires a method after a family paid to it → the payment's detail still shows the details as paid. (Task 5, `test_detail_shows_snapshot_after_method_edit`.)
3. Two children where one already has credit (owes 0) and the payment is short → allocation never gives the zero-owed child a receipt and the shortfall lands per rule. (Task 2, `test_zero_owed_child_takes_no_receipt`.)
4. A double-tap on **Send for checking** → the second submission is flagged `duplicate_of` the first, and the Android button disables while sending. (Task 4 `test_resubmitted_reference_is_flagged`; Task 10 ViewModel test `send_is_disabled_while_sending`.)
5. `paid_on` at Bangladesh midnight (UTC still yesterday) → "today" is Bangladesh's, so a payment dated today is accepted. (Task 4, `test_paid_on_today_in_bangladesh_is_accepted`.)

---

### Task 1: Schema — methods, submissions, claim links, data move

**Files:**
- Create: `migrations/versions/0013_payment_methods_and_submissions.py`
- Modify: `app/db/models.py` (add `PaymentMethod`, `PaymentSubmission`; add columns to `PaymentClaim`)
- Modify: `app/governance/` deletion manifest for the two new tables (follow the file `tests/governance/test_deletion.py` reads)
- Modify: `tests/db/test_migration_head_pin.py` (head → `0013`)
- Test: `tests/db/test_migration_0013.py`

**Interfaces:**
- Produces: `PaymentMethod(id, owner_id, kind, provider, mobile_number, account_number, account_name, branch_name, note, position, retired_at, created_at, updated_at)`; `PaymentSubmission(id, batch_id, payment_method_id, destination_snapshot: dict, total_amount: Money, paid_on: date, transaction_id, from_account, payer_note, submitted_by_account_id, submitted_at, status, decision_note, decided_by_account_id, decided_at, previous_decision)`; `PaymentClaim.payment_submission_id: UUID | None` (FK `SET NULL`); enums `payment_method_kind`, `payment_submission_status`.

- [ ] **Step 1: Write the failing migration tests** in `tests/db/test_migration_0013.py`:
  - `test_0013_moves_each_distinct_collection_number_once`: two batches of one owner with `("01712345678","bKash")` and one with `("01812987654","Nagad")` before upgrade → after upgrade exactly 2 `payment_method` rows for that owner, `kind == "mobile"`, providers `{"bKash","Nagad"}`; the batch columns still hold their values.
  - `test_0013_batch_with_no_number_makes_no_method`.
  - `test_kind_check_refuses_mobile_without_number` and `test_kind_check_refuses_bank_fields_on_mobile` (raw INSERT raises `IntegrityError`).
  - `test_submission_total_must_be_positive` (`total_amount = 0` raises).
  - `test_linked_claim_may_carry_a_zero_share` (a claim with `payment_submission_id` set and `claimed_amount = 0` inserts; one with it NULL and `claimed_amount = 0` still raises).
  - `test_0013_downgrade_drops_new_tables_and_columns`.
- [ ] **Step 2: Run** `pytest tests/db/test_migration_0013.py -v` → FAIL (revision `0013` not found).
- [ ] **Step 3: Write the migration** (`revision = "0013"`, `down_revision = "0012"`) and the models. `CHECK`s: mobile ⇒ `mobile_number IS NOT NULL AND account_number IS NULL AND account_name IS NULL AND branch_name IS NULL`; bank ⇒ `account_number`, `account_name`, `provider`, `branch_name` NOT NULL and `mobile_number IS NULL`; `total_amount > 0`; `transaction_id IS NULL OR from_account IS NULL`. Replace `ck_payment_claim_claimed_amount_positive` with `claimed_amount > 0 OR (payment_submission_id IS NOT NULL AND claimed_amount = 0)`, because a child's provisional share of a short multi-child payment can be zero. Indexes: `payment_method(owner_id)`, `payment_submission(batch_id, status)`, `payment_claim(payment_submission_id)`. Grant the app role the same privileges `0005` grants on `payment_claim`. Data move: `INSERT … SELECT DISTINCT owner_id, 'mobile', collection_channel, collection_number … WHERE collection_number IS NOT NULL`, with `COALESCE(collection_channel, 'bKash')`. Deletion dispositions: `payment_method` hard-delete with owner; `payment_submission` retain-with-basis like `payment_claim`.
- [ ] **Step 4: Run** `pytest tests/db -v` → PASS (including the head pin and the deletion manifest test).
- [ ] **Step 5: Commit** `feat(db): payment methods and payment submissions (0013)`.

---

### Task 2: Multi-child allocation in `app.money` (test-first)

**Files:**
- Create: `app/money/_allocation.py`
- Modify: `app/money/__init__.py` (export `Allocation`, `allocate_payment`)
- Test: `tests/money/test_allocation.py`, `tests/money/test_allocation_property.py`
- Modify: `tests/named_tests.toml` (one entry per named test below, with its criterion)

**Interfaces:**
- Produces:
  ```python
  Disposition = Literal["carried", "waived"]

  @dataclass(frozen=True, slots=True)
  class Allocation:
      approved: tuple[Money, ...]
      shortfall: Money
      bearer_index: int | None
      credit_index: int | None

  def allocate_payment(
      received: Money,
      owed: Sequence[Money],
      *,
      disposition: Disposition | None,
      bearer_index: int | None,
      credit_index: int | None,
  ) -> Allocation
  ```
  `approved[i]` is what child `i`'s claim is approved at. Raises `MoneyValidationError` with codes from the tests.

- [ ] **Step 1: Write the failing tests** in `tests/money/test_allocation.py` (`M = Money`):
  - `test_exact_payment_approves_each_at_what_they_owe`: `allocate_payment(M("2000"), [M("1000"), M("1000")], disposition=None, bearer_index=None, credit_index=None).approved == (M("1000"), M("1000"))`, `shortfall == Money.ZERO`.
  - `test_short_two_children_bearer_takes_the_shortfall`: received 1500, owed [1000, 1000], `"carried"`, `bearer_index=0` → `approved == (M("500"), M("1000"))`, `shortfall == M("500")`, `bearer_index == 0`.
  - `test_shortfall_bigger_than_bearer_spills_from_the_end`: received 500, owed [1000, 1000, 1000], `bearer_index=0` → `approved == (M("0"), M("500"), M("0"))`. Others are paid in list order (index 1 then 2); the bearer is paid last; what is left unpaid falls on the bearer first, then on the others from the end of the list.
  - `test_zero_owed_child_takes_no_receipt`: received 800, owed [0, 1000], `"waived"`, `bearer_index=1` → `approved == (M("0"), M("800"))`.
  - `test_over_payment_credits_the_chosen_child`: received 2500, owed [1000, 1000], `credit_index=1` → `approved == (M("1000"), M("1500"))`.
  - `test_single_child_over_payment_needs_no_choice`: received 1200, owed [1000], all None → `approved == (M("1200"),)`, `credit_index == 0`.
  - `test_single_child_short_needs_disposition_not_bearer`: received 600, owed [1000], `"carried"`, `bearer_index=None` → `approved == (M("600"),)`, `bearer_index == 0`.
  - Refusals (`pytest.raises(MoneyValidationError)` and assert `.code`): `ALLOCATION_NO_CHILDREN` (empty owed); `ALLOCATION_RECEIVED_NEGATIVE`; `ALLOCATION_DISPOSITION_REQUIRED` (short, None); `ALLOCATION_DISPOSITION_NOT_APPLICABLE` (exact, `"waived"`); `ALLOCATION_BEARER_REQUIRED` (short, 2 children, None); `ALLOCATION_CREDIT_CHILD_REQUIRED` (over, 2 children, None); `ALLOCATION_INDEX_OUT_OF_RANGE` (bearer 5).
- [ ] **Step 2: Write the property test** `test_allocation_invariants` in `tests/money/test_allocation_property.py` (Hypothesis, owed lists of 1–4 non-negative 2dp amounts ≤ 99999, received 0–3× the sum, valid choices drawn from the case). Assert: `sum(approved) == received`; `approved[i] <= owed[i]` for every `i != credit_index`; when short, `shortfall == sum(owed) - received`; otherwise `shortfall == Money.ZERO`.
- [ ] **Step 3: Run** `pytest tests/money/test_allocation.py tests/money/test_allocation_property.py -v` → FAIL (import error).
- [ ] **Step 4: Implement `allocate_payment`** in `app/money/_allocation.py`. Use only `Money` arithmetic (`+`, `-`, comparisons, `Money.sum`, `Money.ZERO`); no `Decimal`. The fill order when short:
  ```text
  order = [i for i in range(n) if i != bearer] + [bearer]
  remaining = received
  for i in order: approved[i] = min(owed[i], remaining); remaining -= approved[i]
  ```
- [ ] **Step 5: Run** `pytest tests/money -v` and `make test` → PASS, with money branch coverage 100%.
- [ ] **Step 6: Commit** `feat(money): allocate one payment across several children`.

---

### Task 3: Payment-method routes and who sees them

**Files:**
- Create: `app/fees/methods.py`, `app/api/payment_methods.py`, `app/schemas/payment_methods.py`
- Modify: `app/api/__init__.py` / `app/main.py` router list; `app/api/fees.py` and `app/api/guardian.py` (remove both `payment-destination` routes); `app/fees/views.py` (remove `payment_destination`, `PaymentDestination`); `app/fees/claims.py` (`CHANNELS` → `MOBILE_SERVICES = ("bKash", "Nagad", "Rocket")`, `CASH = "cash"`); `app/api/batches.py` + `app/schemas/batches.py` (drop `collection_number`/`collection_channel` from create/update/response)
- Rewrite: `tests/contract/test_collection_number.py` → assert the method-detail fields appear on exactly the three routes below
- Modify: `tests/fees/test_fee_privacy.py` (destination tests → method-list tests)
- Test: `tests/fees/test_payment_methods.py`

**Interfaces:**
- Produces (service, `app/fees/methods.py`):
  - `list_methods(session, *, lens: TeacherLens) -> list[PaymentMethod]` (not retired, by `position`)
  - `create_method(session, *, lens: TeacherLens, draft: MethodDraft) -> PaymentMethod`
  - `update_method(session, *, lens: TeacherLens, method_id: UUID, draft: MethodDraft) -> PaymentMethod`
  - `retire_method(session, *, lens: TeacherLens, method_id: UUID) -> None`
  - `methods_for_seat(session, *, lens: StudentLens | GuardianLens, enrollment_id: UUID) -> FamilyMethods` (`methods`, `services`, `cash_allowed: bool = True`)
  - `MethodDraft` dataclass with a `validate() -> None` method: mobile needs `provider` (1–32) and a number that `app.accounts` phone canonicalisation accepts; bank needs `account_number`, `account_name`, `provider`, `branch_name`; `note` ≤ 200.
- Routes: `GET/POST /v1/payment-methods`, `PATCH/DELETE /v1/payment-methods/{method_id}` (teacher); `GET /v1/me/enrollments/{enrollment_id}/payment-methods` (student); `GET /v1/children/{enrollment_id}/payment-methods` (guardian). Response `PaymentMethodResponse{method_id, kind, provider, mobile_number, account_number, account_name, branch_name, note}`; family response `FamilyPaymentMethodsResponse{methods, services, teacher_display_name}`.

- [ ] **Step 1: Write failing tests** in `tests/fees/test_payment_methods.py`:
  - `test_teacher_creates_lists_edits_and_retires_a_mobile_method` (API round trip; a retired method is absent from `GET`).
  - `test_bank_method_requires_all_four_fields` (422, code `METHOD_FIELDS_INCOMPLETE`).
  - `test_custom_service_name_is_accepted` (`provider="Upay"`).
  - `test_teacher_cannot_touch_another_owners_method` (PATCH → 403).
  - `test_accepted_student_sees_their_teachers_methods`; `test_pending_seat_sees_no_methods` (403); `test_guardian_of_another_child_is_refused` (403).
  - `test_family_list_carries_the_service_suggestions` (`services == ["bKash","Nagad","Rocket"]`).
- [ ] **Step 2: Rewrite** `tests/contract/test_collection_number.py` as `test_exactly_the_allowlisted_routes_carry_method_details`: the set of routes whose response schema contains any of `mobile_number`, `account_number` equals `{GET /v1/payment-methods, POST /v1/payment-methods, PATCH /v1/payment-methods/{method_id}, GET /v1/me/enrollments/{enrollment_id}/payment-methods, GET /v1/children/{enrollment_id}/payment-methods}` as an equality, plus `GET /v1/payments/{submission_id}` (Task 5 snapshot). Add the submission route now and expect it to fail until Task 5.
- [ ] **Step 3: Run** `pytest tests/fees/test_payment_methods.py tests/contract/test_collection_number.py -v` → FAIL.
- [ ] **Step 4: Implement** the service, schemas and routes. Scope every teacher query on `PaymentMethod.owner_id == lens.owner_id`. Resolve family reach through the existing `readable_enrollment` helper and require the accepted decision for that lens. Remove the batch collection fields from schemas and forms.
- [ ] **Step 5: Run** `make test` → PASS, except the one submission-route expectation, which is marked `xfail(strict=True, reason="Task 5")`. Then `make openapi`.
- [ ] **Step 6: Commit** `feat(fees): teacher payment methods replace the per-batch number`.

---

### Task 4: Submitting a payment (one or several children, or nothing owed)

**Files:**
- Create: `app/fees/submissions.py`
- Modify: `app/fees/claims.py` (`submit_claim` gains `submission_id` and resolves to Bangladesh's current period instead of raising `NoOpenCycle`; delete `NoOpenCycle`); `app/api/fees.py` (new `POST /v1/payments`; remove `POST /v1/children/{id}/claims`, `POST /v1/enrollments/{id}/claims` and the guardian equivalent); `app/schemas/fees.py` (`PaymentSubmitRequest`, `PaymentSubmittedResponse`); `message-keys.json`
- Modify: existing tests that expected `NoOpenCycle` (`tests/fees/test_claims.py`)
- Test: `tests/fees/test_submissions.py`

**Interfaces:**
- Consumes: `PaymentMethod`, `PaymentSubmission` (Task 1); `methods_for_seat` reach rule (Task 3).
- Produces:
  ```python
  def submit_payment(
      session: Session,
      *,
      lens: StudentLens | GuardianLens,
      draft: PaymentDraft,
      today: dt.date | None = None,
  ) -> PaymentSubmission
  ```
  `PaymentDraft(enrollment_ids: tuple[UUID, ...], payment_method_id: UUID | None, cash: bool, amount: Money, paid_on: date, transaction_id: str | None, from_account: str | None, note: str | None)`. Creates one submission and one `pending` claim per child. Each claim's `claimed_amount` is its provisional share, computed as `allocate_payment(amount, owed, disposition="carried" if short else None, bearer_index=n-1 if short and n > 1 else None, credit_index=n-1 if over and n > 1 else None).approved[i]`, with children in the Task 5 order. A share may be zero (Task 1's constraint allows it). The teacher's decision replaces these shares. Commits. Sends one `CLAIM_TO_VERIFY` notification per submission.
  - `owed_together(session, *, lens, enrollment_ids) -> tuple[Money, list[Money]]`: also served on `GET /v1/payments/owed?enrollment_id=…` for the form's "Owed for …" line.

- [ ] **Step 1: Write failing tests** in `tests/fees/test_submissions.py`:
  - `test_guardian_pays_for_two_children_in_one_submission`: one `payment_submission`, two claims with `payment_submission_id` set, total 2000.
  - `test_student_can_only_pay_for_their_own_seat` (sibling id → 403).
  - `test_submit_refuses_unaccepted_or_cross_batch_child` (pending seat → 403; children in two batches → 422 `PAYMENT_CHILDREN_ACROSS_BATCHES`).
  - `test_method_of_another_teacher_is_refused` (422 `PAYMENT_METHOD_NOT_OFFERED`); `test_retired_method_is_refused`.
  - `test_mobile_needs_transaction_id_bank_needs_from_account` (422 `PAYMENT_REFERENCE_MISMATCH`).
  - `test_paying_with_nothing_owed_is_accepted` (no cycles → 201; claim period equals `bangladesh_today()` as `YYYY-MM`).
  - `test_paid_on_in_the_future_is_refused` (422 `PAYMENT_DATE_IN_FUTURE`); `test_paid_on_today_in_bangladesh_is_accepted` (`today=` injected 00:30 Asia/Dhaka).
  - `test_resubmitted_reference_is_flagged` (same transaction id twice → second's queue item has `duplicate_of` set).
  - `test_one_notification_per_submission` (two children → one teacher inbox row).
- [ ] **Step 2: Run** `pytest tests/fees/test_submissions.py -v` → FAIL.
- [ ] **Step 3: Implement** `submit_payment`, the route and the schemas. `destination_snapshot` is the method's response fields at submit time, or `{"kind": "cash"}`. Each claim's `channel` is the method's `provider` (or `cash`).
- [ ] **Step 4: Run** `make test` → PASS; `make openapi`.
- [ ] **Step 5: Commit** `feat(fees): pay any time, for one or several children`.

---

### Task 5: Deciding a payment — approve with split, reject with note

**Files:**
- Create: `app/fees/decisions.py`
- Modify: `app/fees/verification.py` (expose `verify_claim_in_transaction(...)` that skips its own commit and its own race guard, for use inside a submission decision; existing `verify_claim`/`reject_claim` keep their signatures for single-claim callers); `app/fees/queue.py` and `app/fees/views.py` (queue and detail by submission); `app/api/fees.py` (`GET /v1/payments/{submission_id}`, `POST …/approval`, `POST …/rejection`; remove `/claims/{id}/verification`, `/claims/{id}/rejection`, `/claims/{id}/shortfall`); `app/schemas/fees.py`; `app/notifications/inbox.py` (family notification carries the decision note)
- Test: `tests/fees/test_decisions.py`, `tests/fees/test_decision_races.py`; update `tests/fees/test_verification_api.py`, `test_verification_queue*.py` to the submission routes

**Interfaces:**
- Consumes: `allocate_payment` (Task 2); `submit_payment` (Task 4).
- Produces:
  ```python
  def approve_submission(
      session: Session, *, lens: TeacherLens, submission_id: UUID,
      received: Money, disposition: Disposition | None,
      carried_by_enrollment_id: UUID | None,
      credit_to_enrollment_id: UUID | None,
      note: str | None, correcting: bool = False,
  ) -> PaymentSubmission

  def reject_submission(
      session: Session, *, lens: TeacherLens, submission_id: UUID,
      note: str | None, correcting: bool = False,
  ) -> PaymentSubmission
  ```
  Children are ordered by `Enrollment.display_name` then id. That same order goes to the client and to `allocate_payment`. The race guard is a conditional `UPDATE payment_submission SET status=… WHERE id=… AND status=:read`.
- Detail/queue response `PaymentReviewResponse{submission_id, batch_name, children[{enrollment_id, display_name, period, owed}], owed_together, total_amount, comparison, difference, method: snapshot, transaction_id, from_account, paid_on, submitted_at, submitted_by, submitter_phone, payer_note, status, decision_note, duplicate_of}`.

- [ ] **Step 1: Write failing tests** in `tests/fees/test_decisions.py`:
  - `test_full_approval_marks_every_child_paid` (two children owing 1000 → both cycles `paid`, submission `approved`).
  - `test_short_carry_lands_on_the_chosen_child` (1500/2000, carried, bearer Tanvir → Tania `paid`, Tanvir has `carry_forward` 500 into next period).
  - `test_short_waive_forgives_without_carry` (`forgiveness` 500, no `carry_forward`).
  - `test_over_payment_credits_the_chosen_child` (`credit_grant` 500 on the chosen child only).
  - `test_nothing_owed_payment_becomes_credit` (approve 1000 with no cycle → one `credit_grant` 1000; the next `generate_due_cycles` spends it through `credit_apply`).
  - `test_rejection_keeps_dues_and_shows_the_note` (family claim view status `rejected`, `decision_note` present, balance unchanged).
  - `test_correction_reverses_every_childs_entries` (approve, then `correcting=True` reject → ledger fold back to before).
  - `test_detail_shows_snapshot_after_method_edit` (edit the method after submit → detail `method.mobile_number` is the old number).
  - `test_other_teacher_cannot_decide` (403).
- [ ] **Step 2: Write** `tests/fees/test_decision_races.py::test_concurrent_approvals_credit_once`: two threads approve the same submission → exactly one 200 and one 409 `CONFLICT`, receipts written once.
- [ ] **Step 3: Run** the new tests → FAIL.
- [ ] **Step 4: Implement** `approve_submission`. Claim the decision on the submission, compute `allocate_payment`, then for each child call `verify_claim_in_transaction(claim, approved_amount=approved[i], shortfall_disposition=disposition if approved[i] < charged[i] else None)`. `charged[i]` is that claim's period charge, the same figure `verify_claim` measures against, so the bearer and any spill child each get the teacher's disposition and fully paid children get none. Set `decision_note`, and notify each child's family once. Then implement `reject_submission` (every child claim `rejected`, `rejection_reason = note`).
- [ ] **Step 5: Run** `make test` → PASS, including the Task 3 contract test with its `xfail` removed. `make openapi`.
- [ ] **Step 6: Commit** `feat(fees): approve or reject a payment, split across children`.

---

### Task 6: Money reports

**Files:**
- Create: `app/analytics/collections.py`
- Modify: `app/api/analytics.py` (`GET /v1/analytics/collections`); `app/fees/views.py` + `app/api/fees.py` (`period` query on `/v1/batches/{batch_id}/fees`, add `MonthTotals` and state counts; `months` query on `/v1/enrollments/{enrollment_id}/fees` adding `month_states` and per-month `history_line`); `app/schemas/analytics.py`, `app/schemas/fees.py`
- Test: `tests/analytics/test_collections.py`, extend `tests/fees/test_batch_fee_status.py`

**Interfaces:**
- Produces: `collections(session, *, lens: TeacherLens, batch_ids: Sequence[UUID] | None, months: int, today: date | None = None) -> CollectionsReport` with `months: list[MonthCollection(period, charged, collected, in_progress, charged_bar: int, collected_bar: int)]` (bars are 0–100, each figure as a percent of the largest `charged` in the report, computed in `app.money` terms server-side so the client draws without money arithmetic), `outstanding: Money`, `owing_students: int`. `collected = receipt + credit_grant` from `app.analytics.earnings.period_totals`; `charged` = sum of `charge` entries in the period.

- [ ] **Step 1: Write failing tests**: `test_collections_sum_receipts_and_credit_not_credit_apply`; `test_bars_scale_to_the_largest_charge` (charged 20000 and 22000 → bars 91 and 100); `test_collections_filter_by_batches`; `test_current_month_is_in_progress`; `test_other_teachers_batch_id_is_refused` (403); `test_batch_fees_for_a_past_period` (October counts: paid 9, checking 1, owed 2 from a seeded batch); `test_enrollment_history_has_six_month_states`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**, reusing `period_totals` and the existing status derivation in `app/fees/status.py`. `months` is clamped to 1–24.
- [ ] **Step 4: Run** `make test` → PASS; `make openapi`.
- [ ] **Step 5: Commit** `feat(analytics): collections over months, batch month and student history`.

---

### Task 7: Progress dashboard reads

**Files:**
- Create: `app/analytics/dashboard.py`, `app/schemas/dashboard.py`
- Modify: `app/api/analytics.py` (teacher route), `app/api/me.py` or `app/api/marks.py` (student), `app/api/guardian.py` (guardian)
- Test: `tests/analytics/test_dashboard.py`

**Interfaces:**
- Produces: `seat_dashboard(session, *, lens: Lens, enrollment_id: UUID, range_: Literal["6m","year","all"], today: date | None = None) -> SeatDashboard`. It returns `tiles(attendance_percent: int | None, present: int, held: int, exam_average_percent: int | None, direction: Direction | None, owed: Money)`, `attendance_by_month[(period, held, present, percent, in_progress)]`, `exams[(exam_id, title, date, subject, marks, total, percent, batch_average: int | None, batch_highest: int | None)]` and `fee_months[(period, state)]`. Percentages are integers rounded half-up, computed by `Money`-free integer arithmetic (`(present * 100 + held // 2) // held`). `held` counts sessions with `status == "held"` on or after the seat's start.
- Routes: `GET /v1/enrollments/{enrollment_id}/dashboard` (teacher), `GET /v1/me/enrollments/{enrollment_id}/dashboard` (student), `GET /v1/children/{enrollment_id}/dashboard` (guardian).

- [ ] **Step 1: Write failing tests**: `test_attendance_counts_held_not_cancelled`; `test_average_and_highest_need_three_marked_seats` (2 marked → both None; 3 marked → values); `test_family_gets_no_comparison_when_marksheet_hidden` (`marksheet_visible=False` → None for guardian and student, values for teacher); `test_highest_carries_no_name` (no field of the exam object equals another seat's display name); `test_guardian_cannot_read_a_non_child_dashboard` (403); `test_fee_months_match_enrollment_history`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**, reusing `results_for_exam` for marks and the Task 6 month states for fees.
- [ ] **Step 4: Run** `make test` → PASS; `make openapi`.
- [ ] **Step 5: Commit** `feat(analytics): one progress dashboard for teacher, student and guardian`.

---

### Task 8: Android — teacher payment methods (P1–P3)

**Files:**
- Create: `android/src/main/kotlin/com/shikkhokplus/app/core/network/PaymentMethodDto.kt`, `HttpPaymentMethodsRepository.kt`; `feature/paymentmethods/{PaymentMethodsUiState.kt, PaymentMethodsViewModel.kt, MethodEditorViewModel.kt, ui/PaymentMethodsScreen.kt, ui/MethodEditorScreen.kt}`
- Modify: `feature/profile/ui/ProfileScreen.kt` (More → "Payment methods" row); `navigation/Destination.kt`; batch create/edit screens (remove the collection number field); both `strings.xml`
- Test: `android/src/test/kotlin/.../feature/paymentmethods/*Test.kt`, `core/network/HttpPaymentMethodsRepositoryTest.kt`

**Interfaces:**
- Consumes: Task 3 routes.
- Produces: `PaymentMethodsRepository { list(); create(draft); update(id, draft); retire(id) }`.

- [ ] **Step 1: Write failing tests**: ViewModel states `loading → loaded`, `error → retry`; `save_failure_keeps_the_form_and_shows_retry`; the editable service dropdown offers the server's `services` plus "Use “X”" for typed text; the bank form disables Save until all four fields are filled; DTO decode test.
- [ ] **Step 2: Run** `./gradlew testDebugUnitTest --tests '*paymentmethods*'` → FAIL.
- [ ] **Step 3: Implement** the screens to the P1–P3 boards (an `ExposedDropdownMenuBox` with an editable `TextField`; the +88 prefix field from the design system).
- [ ] **Step 4: Run** `make android` → PASS.
- [ ] **Step 5: Commit** `feat(android): teacher payment methods in More`.

---

### Task 9: Android — pay any time (F1–F5)

**Files:**
- Modify: `feature/pay/{PayUiState.kt, PayViewModel.kt, PayMapper.kt, ui/PayScreen.kt}`, `core/network/{PayDto.kt, HttpPayRepository.kt}`, `feature/guardian/ui/PaymentsScreen.kt`, `feature/student` payments tab, both `strings.xml`
- Test: `feature/pay/PayViewModelTest.kt`, `core/network/PayDtoTest.kt`

**Interfaces:**
- Consumes: Task 3 family method routes; Task 4 `POST /v1/payments` and `GET /v1/payments/owed`.

- [ ] **Step 1: Write failing tests**: `send_money_shows_with_nothing_owed`; `guardian_sees_children_of_the_chosen_batch_only`; `student_for_field_is_fixed_to_self`; `owed_line_comes_from_server` (no client sum); `mobile_requires_trx_bank_requires_from_account`; `send_is_disabled_while_sending`; `server_refusal_shows_message_key`; `PayDtoTest` amount decodes from a string and fails on a JSON number.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** to the boards: F1 always-visible button; F2 methods plus **Cash in hand**; F3/F4 with Batch and multi-select For, date picker defaulting to Bangladesh today; F5.
- [ ] **Step 4: Run** `make android` → PASS.
- [ ] **Step 5: Commit** `feat(android): pay any time through the teacher's methods`.

---

### Task 10: Android — review a payment (R1–R4)

**Files:**
- Modify: `feature/verify/{VerifyUiState.kt, VerifyViewModel.kt, VerifyStateMapper.kt, ui/VerifyScreen.kt, ui/PartialApprovalSheet.kt}`, `core/network/{VerificationDto.kt, HttpVerificationRepository.kt}`, `feature/inbox` (payment filter chip), both `strings.xml`
- Test: `feature/verify/*Test.kt`

**Interfaces:**
- Consumes: Task 5 routes and `PaymentReviewResponse`.

- [ ] **Step 1: Write failing tests**: `exact_amount_shows_only_approve`; `short_two_children_requires_carry_or_waive_and_a_child`; `over_two_children_requires_credit_child`; `reject_sends_note`; `decided_shows_note_and_change_decision`; `conflict_reloads_and_explains`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** to R1–R4. The sheet's child picker lists `children` in server order and shows the server's "— X is marked paid" copy keys.
- [ ] **Step 4: Run** `make android` → PASS.
- [ ] **Step 5: Commit** `feat(android): review a payment with notes and a child picker`.

---

### Task 11: Android — money reports (M1–M3)

**Files:**
- Create: `feature/collections/{CollectionsUiState.kt, CollectionsViewModel.kt, ui/CollectionsScreen.kt}`
- Modify: `feature/fees/ui/BatchFeesScreen.kt` (month switcher + filter chips), `feature/fees/ui/FeeHistoryScreen.kt` (6-month strip), `core/network/{AnalyticsDto.kt, HttpAnalyticsRepository.kt, FeeDto.kt}`, More/Today entry point, both `strings.xml`
- Test: `feature/collections/CollectionsViewModelTest.kt`, extend fees tests

- [ ] **Step 1: Write failing tests**: `batch_chips_refetch_with_selected_ids`; `in_progress_month_is_marked`; `batch_month_switch_requests_period`; `filters_use_server_counts`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** to M1–M3. Bar heights come from the server's `charged_bar`/`collected_bar` integers (0–100) times the chart height in `dp`; the client never reads a money string as a number.
- [ ] **Step 4: Run** `make android` → PASS.
- [ ] **Step 5: Commit** `feat(android): collections, batch month and student payment history`.

---

### Task 12: Android — progress dashboard (D1, D2)

**Files:**
- Create: `feature/dashboard/{DashboardUiState.kt, DashboardViewModel.kt, ui/DashboardScreen.kt, ui/AttendanceBars.kt, ui/MarksLine.kt}`, `core/network/DashboardDto.kt`
- Modify: navigation for the teacher (student detail → Progress), student and guardian (Progress tab with child switcher and batch picker), both `strings.xml`
- Test: `feature/dashboard/DashboardViewModelTest.kt`, `ui/DashboardScreenTest.kt`

- [ ] **Step 1: Write failing tests**: `average_and_highest_lines_hidden_when_null`; `guardian_switching_child_refetches`; `range_chip_refetches`; `empty_exams_shows_empty_state`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** one `DashboardScreen(state, actions)` used by all three entry points, drawn to D1/D2.
- [ ] **Step 4: Run** `make check` → PASS (full gate, the last task).
- [ ] **Step 5: Commit** `feat(android): one progress dashboard for all three roles`.
