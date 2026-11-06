"""The shared money-name vocabulary, and what it deliberately exempts.

**Two gates match on these names, and before this module they each kept
their own copy.** ``app.contract.money_schema`` checks the generated
OpenAPI document; ``tests/db/test_governance.py`` checks the migrated
database. Two independent lists meant an entry added to one protected
only that surface, and nothing made the drift visible.

That duplication is why one false positive produced two build failures
with no single place to resolve it: ``batch.fee_due_day`` matches both
``fee`` and ``due`` while holding an integer day-of-month [AC2.1.2].

**Name matching is a deliberate weakening**, used only where nothing
stronger exists. The ``$ref`` predicate is the control for response
schemas and the ``Money`` type decorator is the control for columns; a
bare ``{"type": "integer"}`` or a raw ``NUMERIC`` carries nothing else
to distinguish a fee from a page count. The residual gap is real and
recorded in BR3.3: a genuine money column named ``tuition``,
``stipend`` or ``discount`` matches no token and is missed by both.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "MONEY_NAME_TOKENS",
    "NON_MONEY_COLUMNS",
    "NON_MONEY_FIELDS",
    "is_money_name",
]

#: Name fragments that mark a column or property as money-carrying.
#: Narrow and money-specific by design. **Never remove a token to make a
#: build pass**: dropping ``fee`` or ``due`` would turn the build green
#: while silently retiring the check on every genuine fee column in U7
#: and U8 -- the gate would still be reported as passing and would be
#: covering less, which is how a control is retired rather than fixed.
MONEY_NAME_TOKENS: Final[tuple[str, ...]] = (
    "amount",
    "balance",
    "fee",
    "due",
    "paid",
    "price",
    "total",
    "outstanding",
    "credit",
    "charge",
)

#: Database columns that match a money token and carry something else.
#: Keyed ``(table, column)`` so an exemption can never widen beyond the
#: one column it was reasoned about, and each entry states why.
NON_MONEY_COLUMNS: Final[dict[tuple[str, str], str]] = {
    ("batch", "fee_due_day"): (
        "An INTEGER 1-31 day-of-month, not an amount [AC2.1.2]. Values "
        "29-31 are legal and clamp to the month's last day at generation "
        "time, which is U7's arithmetic -- the column must admit them or "
        "the clamp never runs. Matches both 'fee' and 'due'."
    ),
    ("fee_cycle", "due_date"): (
        "A DATE, not an amount [BR2.2]. It is the computed due date "
        "after the short-month clamp, stored rather than recomputed so a "
        "later change to the batch's anchor day does not retroactively "
        "move a due date a student has already been shown. Matches both "
        "'fee' (from the table name's column prefix) and 'due'. The "
        "table it sits on carries NO money column of any kind, which is "
        "itself asserted by a test over the column set, so there is no "
        "money value on fee_cycle for this exemption to hide."
    ),
    ("payment_submission", "paid_on"): (
        "A DATE, not an amount: the day the family says the money moved. "
        "Matches the 'paid' token. The submission's amount is "
        "`total_amount`, a NUMERIC(12,2), and is checked by this same "
        "gate."
    ),
    ("exam", "total_marks"): (
        "An INTEGER COUNT of marks, not an amount [entities.md]. It is "
        "the denominator a score is out of, constrained >= 1 because a "
        "total of zero makes every percentage undefined. Matches the "
        "'total' token. The table it sits on carries no money column of "
        "any kind -- a title, a date, two foreign keys and this count -- "
        "so there is no money value on exam for this exemption to hide, "
        "and `mark.marks` does not match any token at all."
    ),
    ("extra_fee", "due_on"): (
        "A DATE, not an amount: the day an exam or other fee falls due "
        "[0020]. Matches 'fee' and 'due'. The fee's money column, `amount`,"
        " is a NUMERIC(12,2) checked by this same gate."
    ),
    ("extra_fee_charge", "extra_fee_id"): (
        "A UUID foreign key naming the fee a student's charge sits under, "
        "not an amount [0020]. The table carries no money column of any "
        "kind -- like fee_cycle, every figure is folded from "
        "extra_fee_entry -- so there is nothing on it for this exemption to"
        " hide."
    ),
    ("extra_fee_entry", "extra_fee_charge_id"): (
        "A UUID foreign key naming the student's charge an entry moves, not"
        " an amount [0020]. The entry's money column, `amount`, is a "
        "NUMERIC(12,2) checked by this same gate."
    ),
    ("payment_claim", "extra_fee_charge_id"): (
        "A UUID foreign key naming the student's charge a claim settles, "
        "not an amount [0020]. The claim's amounts, `claimed_amount` and "
        "`approved_amount`, are checked by this same gate."
    ),
    ("payment_submission", "extra_fee_id"): (
        "A UUID foreign key naming the extra fee a payment is applied to, "
        "not an amount [0020]. The submission's amount is `total_amount`, "
        "checked by this same gate."
    ),
    ("payment_submission", "requested_extra_fee_id"): (
        "A UUID foreign key naming the extra fee the family chose, kept as "
        "they chose it [0020]. Not an amount; the submission's amount is "
        "`total_amount`."
    ),
    ("expense", "extra_fee_id"): (
        "A UUID foreign key naming the exam or other fee an expense was "
        "spent for, not an amount [0021]. The expense's money column, "
        "`amount`, is a NUMERIC(12,2) checked by this same gate."
    ),
}

#: Response-schema properties that match a money token and carry
#: something else. Keyed ``(schema, field)`` for the same reason.
NON_MONEY_FIELDS: Final[dict[tuple[str, str], str]] = {
    ("BatchResponse", "fee_due_day"): (
        "The same day-of-month column crossing the wire. Named "
        "separately from NON_MONEY_COLUMNS because the two gates check "
        "different surfaces and a column is not always a field."
    ),
    ("BatchCreateRequest", "fee_due_day"): (
        "The same value inbound. A request schema reaches the gate too."
    ),
    ("BatchUpdateRequest", "fee_due_day"): (
        "The same value on the edit path [AC2.3.1]."
    ),
    ("HistoryLineResponse", "paid_on"): (
        "A DATE, not an amount: the day the claimant says the money "
        "moved. The line's money property, `amount`, references Money."
    ),
    ("MonthCollectionResponse", "charged_bar"): (
        "A whole percent from 0 to 100 for drawing a bar, not an amount. "
        "The server computes it with Money.percent_of so the client does "
        "no money arithmetic; the month's money properties reference Money."
    ),
    ("MonthCountsResponse", "paid"): (
        "A COUNT of seats under the Paid filter, not an amount."
    ),
    ("PaymentSubmitRequest", "paid_on"): (
        "A DATE, not an amount: the day the payer says the money moved. "
        "The request's money property, `amount`, references Money."
    ),
    ("ReceivedPaymentRequest", "paid_on"): (
        "A DATE, not an amount: the day the teacher received the money. "
        "The request's money property, `amount`, references Money."
    ),
    ("PaymentSubmittedResponse", "paid_on"): (
        "The same date echoed back. The response's money property, "
        "`total_amount`, references Money."
    ),
    ("PaymentReviewResponse", "paid_on"): (
        "A DATE, not an amount: the day the family says the money moved, "
        "as the teacher reviews it. The review's money properties -- "
        "`total_amount`, `owed_together`, `difference` -- reference Money."
    ),
    ("PaymentApprovalRequest", "credit_to_enrollment_id"): (
        "A UUID naming the child who receives an excess as credit, not an "
        "amount. Matches the 'credit' token. The request's money property, "
        "`received_amount`, references Money."
    ),
    ("CurrentFeeResponse", "paid_on"): (
        "A DATE, not an amount: the day the period's last approved "
        'payment was decided ("Paid 8 Oct"). The schema\'s money '
        "properties reference Money."
    ),
    ("PaymentLineResponse", "due_date"): (
        "A DATE, not an amount: when a month on G3's payment history "
        "was due. The line's money property, `amount`, references Money."
    ),
    ("PayableResponse", "due_date"): (
        "A DATE, not an amount: when the month offered for payment was "
        "due. Its money property, `amount_due`, references Money."
    ),
    ("FeeCycleResponse", "due_date"): (
        "A DATE crossing the wire, not an amount [BR2.2]. It is the "
        "computed due date after the short-month clamp. The schema it "
        "sits on carries two genuine money properties -- `charged` and "
        "`outstanding` -- and BOTH reference the shared Money "
        "component, so this exemption narrows the gate by exactly one "
        "field that was never money. Matches both 'fee' and 'due'."
    ),
    # D4's exam denominator, crossing the wire. An INTEGER COUNT of
    # marks, constrained >= 1 at the schema and by a database CHECK --
    # not an amount, and never a money type [entities.md]. Matches the
    # 'total' token. Named per (schema, field) like every other entry,
    # so an exemption can never widen beyond the one property it was
    # reasoned about, and none of these schemas carries a money
    # property for it to hide.
    ("ExamResponse", "total_marks"): (
        "An INTEGER COUNT of marks on the exam read, not an amount. "
        "It is the denominator a score is out of."
    ),
    ("DashboardExamResponse", "total"): (
        "An INTEGER COUNT of marks the exam is out of on the progress "
        "dashboard, not an amount."
    ),
    ("FamilyExamResponse", "total_marks"): (
        "The same count on a family's exam list and detail, not money."
    ),
    ("ExamBlock", "total_marks"): (
        "The same count on an inbox item's exam detail, not money."
    ),
    ("ExamCreateRequest", "total_marks"): (
        "The same count inbound, on creation. A request schema reaches the gate too."
    ),
    ("ExamUpdateRequest", "total_marks"): (
        "The same count inbound, on edit, which no longer reuses the creation body."
    ),
    ("ChildResultResponse", "total_marks"): (
        "The exam's mark count on G1's latest results, not money."
    ),
    ("ProgressSummaryResponse", "total_marks"): (
        "The last test's mark count on G2's summary line, not money."
    ),
    ("LastResultResponse", "total_marks"): (
        "The exam's mark count on S1's \"Last test 44/50\", not money."
    ),
    ("UpcomingExamResponse", "total_marks"): (
        'The coming exam\'s mark count ("out of 100"), not money.'
    ),
    ("ProgressEntryResponse", "total_marks"): (
        "The same count on the guardian progress series, carried so a "
        "client can render '60 out of 80' without a second lookup."
    ),
    ("ExamListItemResponse", "total_marks"): (
        "The same count on the teacher's exam list, which extends the "
        "exam read with its marking progress."
    ),
    ("PublishedMarksheetResponse", "total_marks"): (
        "The same count as the marksheet's heading, so the screen can "
        "say what the viewer's mark is out of."
    ),
    ("SuppressedMarksheetResponse", "total_marks"): (
        "The same heading count on the suppressed marksheet."
    ),
    ("OutstandingResponse", "overdue_students"): (
        "A COUNT of students with anything overdue on Today (T1), not an "
        "amount. The amount beside it, `overdue`, is the money field."
    ),
    ("RosterFeeRowResponse", "days_overdue"): (
        "A COUNT of days since the oldest unpaid period fell due, for "
        "T7's fee chip. The amounts beside it are money fields."
    ),
    ("CurrentFeeResponse", "due_date"): (
        "The same computed date on the student's batch list (S1), for "
        "their latest period. Its sibling `outstanding` is real money "
        "and references the shared Money component, so it is still "
        "checked."
    ),
    ("RosterFeeRowResponse", "due_date"): (
        "The same computed date on the teacher's roster view. Named "
        "separately because the gate matches (schema, field) pairs, so "
        "an exemption can never widen beyond the one property it was "
        "reasoned about -- and this schema's `outstanding` is real "
        "money and still checked."
    ),
    # D5's dues row. A PERIOD KEY, matching the 'paid' token inside the
    # word 'unpaid' -- which is the vocabulary's weakest match and the
    # clearest illustration of why the token list is a weakening used
    # only where nothing stronger exists.
    ("DuesRowResponse", "oldest_unpaid_period"): (
        "A `YYYY-MM` PERIOD KEY, not an amount [BR1.1]. It names which "
        "period a debt starts in and is pattern-constrained as a month "
        "string. It matches the 'paid' token inside 'unpaid', which is "
        "a substring collision rather than a money signal. The schema "
        "it sits on carries one genuine money property -- "
        "`outstanding` -- which references the shared Money component "
        "and is still checked, so this exemption narrows the gate by "
        "exactly one field that was never money."
    ),
    ("ExtraFeeDetailResponse", "due_on"): (
        "A DATE, not an amount: the day the extra fee falls due [0020]. "
        "Matches 'fee' and 'due'; every money property of this schema "
        "references Money."
    ),
    ("ExtraFeeDetailResponse", "extra_fee_id"): (
        "A UUID naming an extra fee, not an amount [0020]. Matches the "
        "'fee' token; every money property of this schema references Money."
    ),
    ("ExtraFeeDetailResponse", "paid_count"): (
        "A COUNT of students whose charge reads paid, not an amount [0020]."
        " The schema's money properties reference Money."
    ),
    ("ExtraFeeRaiseRequest", "due_on"): (
        "A DATE, not an amount: the day the extra fee falls due [0020]. "
        "Matches 'fee' and 'due'; every money property of this schema "
        "references Money."
    ),
    ("ExtraFeeRefResponse", "due_on"): (
        "A DATE, not an amount: the day the extra fee falls due [0020]. "
        "Matches 'fee' and 'due'; every money property of this schema "
        "references Money."
    ),
    ("ExtraFeeRefResponse", "extra_fee_id"): (
        "A UUID naming an extra fee, not an amount [0020]. Matches the "
        "'fee' token; every money property of this schema references Money."
    ),
    ("ExtraFeeSummaryResponse", "due_on"): (
        "A DATE, not an amount: the day the extra fee falls due [0020]. "
        "Matches 'fee' and 'due'; every money property of this schema "
        "references Money."
    ),
    ("ExtraFeeSummaryResponse", "extra_fee_id"): (
        "A UUID naming an extra fee, not an amount [0020]. Matches the "
        "'fee' token; every money property of this schema references Money."
    ),
    ("ExtraFeeSummaryResponse", "paid_count"): (
        "A COUNT of students whose charge reads paid, not an amount [0020]."
        " The schema's money properties reference Money."
    ),
    ("PaymentApprovalRequest", "extra_fee_id"): (
        "A UUID naming an extra fee, not an amount [0020]. Matches the "
        "'fee' token; every money property of this schema references Money."
    ),
    ("PaymentSubmitRequest", "extra_fee_id"): (
        "A UUID naming an extra fee, not an amount [0020]. Matches the "
        "'fee' token; every money property of this schema references Money."
    ),
    ("ReceivedPaymentRequest", "extra_fee_id"): (
        "A UUID naming an extra fee, not an amount [0020]. Matches the "
        "'fee' token; every money property of this schema references Money."
    ),
    ("SeatExtraFeeResponse", "due_on"): (
        "A DATE, not an amount: the day the extra fee falls due [0020]. "
        "Matches 'fee' and 'due'; every money property of this schema "
        "references Money."
    ),
    ("SeatExtraFeeResponse", "extra_fee_id"): (
        "A UUID naming an extra fee, not an amount [0020]. Matches the "
        "'fee' token; every money property of this schema references Money."
    ),
    ("ExpenseRequest", "extra_fee_id"): (
        "A UUID naming an extra fee, not an amount [0021]. Matches the "
        "'fee' token; every money property of this schema references Money."
    ),
    ("ExpenseResponse", "extra_fee_id"): (
        "A UUID naming an extra fee, not an amount [0021]. Matches the "
        "'fee' token; every money property of this schema references Money."
    ),
    ("MoneyFeeLineResponse", "extra_fee_id"): (
        "A UUID naming an extra fee, not an amount [0021]. Matches the "
        "'fee' token; every money property of this schema references Money."
    ),
}


def is_money_name(name: str) -> bool:
    """Report whether a name matches any money token.

    :param name: The column or property name to test
    :return: True if the name implies a money value
    """
    lowered = name.lower()
    return any(token in lowered for token in MONEY_NAME_TOKENS)
