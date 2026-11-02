"""
One payment allocated across the children it covers.

A guardian may send one payment for several children. The teacher records
what was received; this module decides what each child's claim is approved
at. It is a pure function of its arguments: it knows nothing of claims,
enrollments or submissions, only of amounts in the order the caller lists
them.

Three cases, decided by comparing what was received with what the children
owe together:

- **Exact.** Each child is approved at what they owe. No choice applies.
- **Short.** A disposition (carry or waive) is required, and for more than
  one child so is the child who bears the shortfall. The other children are
  paid in full in list order, and the bearer gets what is left. A shortfall
  bigger than the bearer's own figure falls on the remaining children from
  the end of the list.
- **Over.** Every child is paid in full, and the excess goes to the credit
  child, who for more than one child must be chosen.

A choice supplied for a case it does not apply to is refused rather than
ignored, so a caller bug is loud. Each refusal's message begins with its
code, which the caller maps to the error envelope.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ._errors import MoneyValidationError
from ._money import Money

Disposition = Literal["carried", "waived"]


@dataclass(frozen=True, slots=True)
class Allocation:
    """
    What one payment approves for each child it covers.

    :ivar approved: Each child's approved amount, in the caller's order.
    :ivar shortfall: What was owed together and not received; zero unless
        the payment was short.
    :ivar bearer_index: The child who carries or is forgiven the shortfall,
        or ``None`` unless the payment was short.
    :ivar credit_index: The child who receives the excess as credit, or
        ``None`` unless the payment was over.
    """

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
) -> Allocation:
    """
    Allocate one received payment across the children it covers.

    :param received: The amount the teacher recorded as received.
    :param owed: Each child's owed figure, in the order the server lists them.
    :param disposition: Carry or waive the shortfall; required when short and
        refused otherwise.
    :param bearer_index: The child who bears the shortfall; required when short
        for more than one child and refused otherwise.
    :param credit_index: The child who receives the excess; required when over
        for more than one child and refused otherwise.
    :return: Each child's approved amount and the choices that applied.
    :raises MoneyValidationError: If there are no children, an amount is
        negative, an index is out of range, a required choice is missing, or
        a choice is supplied where it does not apply.
    """
    _check_inputs(received, owed, bearer_index, credit_index)
    total = Money.sum(owed)
    if received < total:
        return _allocate_short(
            received, owed, total, disposition, bearer_index, credit_index
        )
    _refuse_disposition(disposition)
    _refuse_index(bearer_index, "bearer")
    if received == total:
        _refuse_index(credit_index, "credit")
        return Allocation(
            approved=tuple(owed),
            shortfall=Money.ZERO,
            bearer_index=None,
            credit_index=None,
        )
    return _allocate_over(received, owed, total, credit_index)


def _check_inputs(
    received: Money,
    owed: Sequence[Money],
    bearer_index: int | None,
    credit_index: int | None,
) -> None:
    """
    Refuse inputs that are wrong whatever the case.

    :param received: The amount received.
    :param owed: Each child's owed figure.
    :param bearer_index: The chosen bearer, if any.
    :param credit_index: The chosen credit child, if any.
    :raises MoneyValidationError: If there are no children, an amount is
        negative, or an index does not name a listed child.
    """
    if not owed:
        raise MoneyValidationError(
            "ALLOCATION_NO_CHILDREN: a payment must cover at least one child."
        )
    if received.is_negative():
        raise MoneyValidationError(
            f"ALLOCATION_RECEIVED_NEGATIVE: received {received} is negative."
        )
    if any(amount.is_negative() for amount in owed):
        raise MoneyValidationError(
            "ALLOCATION_OWED_NEGATIVE: a child's owed figure is negative."
        )
    for index in (bearer_index, credit_index):
        if index is not None and not 0 <= index < len(owed):
            raise MoneyValidationError(
                f"ALLOCATION_INDEX_OUT_OF_RANGE: {index} names no child of "
                f"the {len(owed)} this payment covers."
            )


def _refuse_disposition(disposition: Disposition | None) -> None:
    """
    Refuse a disposition on a payment that is not short.

    :param disposition: The supplied disposition.
    :raises MoneyValidationError: If one was supplied.
    """
    if disposition is not None:
        raise MoneyValidationError(
            "ALLOCATION_DISPOSITION_NOT_APPLICABLE: only a short payment "
            "carries or waives a shortfall."
        )


def _refuse_index(index: int | None, role: str) -> None:
    """
    Refuse a chosen child for a case that has no such choice.

    :param index: The supplied index.
    :param role: Which choice it was, for the message.
    :raises MoneyValidationError: If one was supplied.
    """
    if index is not None:
        raise MoneyValidationError(
            f"ALLOCATION_INDEX_NOT_APPLICABLE: a {role} child does not apply "
            "to this payment."
        )


def _choose_child(index: int | None, count: int, code: str, what: str) -> int:
    """
    Resolve the chosen child, which one child gets automatically.

    :param index: The supplied index, already range-checked.
    :param count: How many children the payment covers.
    :param code: The refusal code when a choice is missing.
    :param what: What the choice is for, for the message.
    :return: The chosen child's index.
    :raises MoneyValidationError: If several children and no choice.
    """
    if index is not None:
        return index
    if count == 1:
        return 0
    raise MoneyValidationError(
        f"{code}: a payment for several children needs the child who {what}."
    )


def _allocate_short(
    received: Money,
    owed: Sequence[Money],
    total: Money,
    disposition: Disposition | None,
    bearer_index: int | None,
    credit_index: int | None,
) -> Allocation:
    """
    Pay the others in list order, then the bearer, with what was received.

    What is left unpaid falls on the bearer first and then on the others
    from the end of the list, because the others are filled from the front.

    :param received: The amount received, less than the total.
    :param owed: Each child's owed figure.
    :param total: What the children owe together.
    :param disposition: The supplied disposition.
    :param bearer_index: The supplied bearer.
    :param credit_index: The supplied credit child, which must be absent.
    :return: The short allocation.
    :raises MoneyValidationError: If the disposition or the bearer is missing,
        or a credit child was supplied.
    """
    if disposition is None:
        raise MoneyValidationError(
            "ALLOCATION_DISPOSITION_REQUIRED: a short payment must be carried "
            "or waived."
        )
    _refuse_index(credit_index, "credit")
    bearer = _choose_child(
        bearer_index, len(owed), "ALLOCATION_BEARER_REQUIRED", "carries it"
    )
    order = [index for index in range(len(owed)) if index != bearer] + [bearer]
    approved = [Money.ZERO] * len(owed)
    remaining = received
    for index in order:
        share = min(owed[index], remaining)
        approved[index] = share
        remaining = remaining - share
    return Allocation(
        approved=tuple(approved),
        shortfall=total - received,
        bearer_index=bearer,
        credit_index=None,
    )


def _allocate_over(
    received: Money,
    owed: Sequence[Money],
    total: Money,
    credit_index: int | None,
) -> Allocation:
    """
    Pay every child in full and give the excess to the credit child.

    :param received: The amount received, more than the total.
    :param owed: Each child's owed figure.
    :param total: What the children owe together.
    :param credit_index: The supplied credit child.
    :return: The over allocation.
    :raises MoneyValidationError: If several children and no credit child.
    """
    credit = _choose_child(
        credit_index,
        len(owed),
        "ALLOCATION_CREDIT_CHILD_REQUIRED",
        "receives the excess",
    )
    approved = list(owed)
    approved[credit] = approved[credit] + (received - total)
    return Allocation(
        approved=tuple(approved),
        shortfall=Money.ZERO,
        bearer_index=None,
        credit_index=credit,
    )
