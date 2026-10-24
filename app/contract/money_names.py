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
    ("FeeCycleResponse", "due_date"): (
        "A DATE crossing the wire, not an amount [BR2.2]. It is the "
        "computed due date after the short-month clamp. The schema it "
        "sits on carries two genuine money properties -- `charged` and "
        "`outstanding` -- and BOTH reference the shared Money "
        "component, so this exemption narrows the gate by exactly one "
        "field that was never money. Matches both 'fee' and 'due'."
    ),
    ("RosterFeeRowResponse", "due_date"): (
        "The same computed date on the teacher's roster view. Named "
        "separately because the gate matches (schema, field) pairs, so "
        "an exemption can never widen beyond the one property it was "
        "reasoned about -- and this schema's `outstanding` is real "
        "money and still checked."
    ),
}


def is_money_name(name: str) -> bool:
    """Report whether a name matches any money token.

    :param name: The column or property name to test
    :return: True if the name implies a money value
    """
    lowered = name.lower()
    return any(token in lowered for token in MONEY_NAME_TOKENS)
