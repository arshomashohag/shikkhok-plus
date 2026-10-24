"""Which fee a cycle charges [BR2.4].

**The whole module is one rule, and the rule is about NULL rather than
falsiness.** `enrollment.fee_amount or batch.default_fee` is the
idiomatic Python line and it silently converts a teacher's deliberate
permanent waiver of 0.00 into the batch default, billing a student the
teacher excused. The built model's own docstring already says "Zero is a
real fee of zero, which is a waiver"; this module is where that sentence
becomes binding, because it lives in another unit's file.
"""

from __future__ import annotations

from app.errors import ValidationError
from app.money import Money

__all__ = ["FeeNotResolvable", "resolve_fee"]


class FeeNotResolvable(ValidationError):
    """Neither the seat nor its batch names a fee.

    A :class:`~app.errors.ValidationError` rather than a silent zero.
    Charging zero here would answer a question nobody asked: the teacher
    set no fee anywhere, which is a configuration gap and not a waiver,
    and once a 0.00 charge is on the append-only ledger the two are
    indistinguishable.
    """

    def __init__(self) -> None:
        """Initialize the refusal with its registered code."""
        super().__init__(
            code="FEE_NOT_SET",
            message_key="fees.resolution.not_set",
        )


def resolve_fee(
    *,
    enrollment_fee: Money | None,
    batch_default: Money | None,
) -> Money:
    """Return the amount this seat is charged for one period.

    :param enrollment_fee: The seat's own fee, or None to inherit.
    :param batch_default: The batch's default fee, or None.
    :return: The amount to charge, which may legitimately be zero.
    :raises FeeNotResolvable: Neither value is set.
    """
    # `is not None`, never a truthiness test. Zero is a real fee.
    if enrollment_fee is not None:
        return enrollment_fee
    if batch_default is not None:
        return batch_default
    raise FeeNotResolvable
