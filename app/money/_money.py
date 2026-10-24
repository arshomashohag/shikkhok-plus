"""
The Money value type.

Money is a type, not a number. This module is the only place in the system
where money arithmetic happens, and the only place that imports :mod:`decimal`
— a boundary enforced by two independent build gates rather than by review.

The type carries Bangladeshi Taka implicitly [BR1.4]: there is no second
currency in this system, so a currency attribute would be a field whose value
is always the same.

This module imports nothing from the API, persistence, repository,
authorization or schema layers, and nothing from the ledger vocabulary. It
depends on :mod:`decimal` and on its own siblings, and on nothing else. That
is what makes it buildable and fully testable before any endpoint exists.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Self

from ._errors import MoneyValidationError
from ._rounding import EXPONENT, MAGNITUDE_LIMIT, ROUNDING

#: What may be offered as an amount. Note the absence of ``float``: the
#: prohibition is a property of the type, checked at runtime by
#: :meth:`Money.__init__` and statically by this annotation.
Amountable = Decimal | int | str


@dataclass(frozen=True, slots=True, order=False)
class Money:
    """
    An exact monetary amount in Bangladeshi Taka.

    Immutable, always at exactly two decimal places, and never convertible
    back to a primitive number.

    :cvar ZERO: The zero amount, so callers write ``balance > Money.ZERO``
        rather than ``balance > 0`` — which removes the one place a bare
        ``0`` creeps into a comparison. [BR2.4]
    :ivar amount: The exact value, quantized to two decimal places.
    """

    ZERO: ClassVar[Money]

    amount: Decimal

    def __init__(self, value: Amountable) -> None:
        """
        Construct an amount, refusing anything that cannot be exact.

        :param value: A fixed-point decimal, an integer number of Taka, or a
            string parsed exactly. A binary floating-point number is refused.
        :raises MoneyValidationError: If the value is a float or a bool, is
            not parseable as an exact decimal, or exceeds the storage
            contract of ten integer digits.
        """
        if isinstance(value, bool) or isinstance(value, float):
            raise MoneyValidationError(
                "Money cannot be constructed from a "
                f"{type(value).__name__}; binary floating-point cannot "
                "represent most decimal fractions exactly. Pass a Decimal, "
                "an int, or a string."
            )
        try:
            raw = Decimal(value)
        except (InvalidOperation, ValueError, ArithmeticError) as exc:
            raise MoneyValidationError(
                f"{value!r} is not an exact decimal amount."
            ) from exc
        if not raw.is_finite():
            raise MoneyValidationError(f"{value!r} is not a finite amount.")
        quantized = raw.quantize(EXPONENT, rounding=ROUNDING)
        # Normalise negative zero. Decimal distinguishes -0.00 from 0.00, and
        # the difference leaks: `is_negative()` is False for -0.00, so it
        # passes every sign guard, but `str()` renders "-0.00" — a string the
        # wire chokepoint would emit and its own parser would then reject.
        # Zero has one representation here.
        if quantized.is_zero():
            quantized = abs(quantized)
        if abs(quantized) >= MAGNITUDE_LIMIT:
            raise MoneyValidationError(
                f"{quantized} exceeds the storage contract of ten integer "
                "digits. The value is rejected, not truncated."
            )
        object.__setattr__(self, "amount", quantized)

    # -- construction helpers ------------------------------------------

    @classmethod
    def _of(cls, raw: Decimal) -> Self:
        """
        Build from an already-exact decimal, re-applying every rule.

        :param raw: An exact decimal produced by this module.
        :return: The constructed amount.
        :raises MoneyValidationError: If the value exceeds the bound.
        """
        return cls(raw)

    # -- arithmetic ----------------------------------------------------

    def __add__(self, other: Money) -> Money:
        """
        Add two amounts.

        :param other: The amount to add. Must be a :class:`Money`.
        :return: The sum.
        :raises TypeError: If `other` is not a :class:`Money`.
        """
        if not isinstance(other, Money):
            return NotImplemented
        return Money._of(self.amount + other.amount)

    def __sub__(self, other: Money) -> Money:
        """
        Subtract one amount from another.

        The result may be negative: that is permitted inside this module and
        constrained per context by the rules that own each quantity.

        :param other: The amount to subtract. Must be a :class:`Money`.
        :return: The difference.
        :raises TypeError: If `other` is not a :class:`Money`.
        """
        if not isinstance(other, Money):
            return NotImplemented
        return Money._of(self.amount - other.amount)

    def __neg__(self) -> Money:
        """
        Negate the amount.

        :return: The negated amount.
        """
        return Money._of(-self.amount)

    def apply_rate(self, rate: Decimal) -> Money:
        """
        Multiply by a rate, rounding once with the module's declared mode.

        There is no multiplication operator. The operation is named so that
        every rounding in the system sits at a call site somebody wrote
        deliberately.

        :param rate: An exact, non-negative decimal proportion. A rate of
            zero is permitted; so is a rate above one, which is what a late
            fee or a multi-month catch-up charge is.
        :return: The rounded product.
        :raises MoneyValidationError: If the rate is a float or is negative.
        """
        if isinstance(rate, bool) or isinstance(rate, float):
            raise MoneyValidationError(
                "A rate must be an exact Decimal; a float is already wrong "
                "before it is multiplied."
            )
        if not isinstance(rate, Decimal):
            raise MoneyValidationError(
                f"A rate must be a Decimal, not {type(rate).__name__}."
            )
        if rate.is_signed() and rate != 0:
            raise MoneyValidationError(
                "A rate must not be negative; it would manufacture a "
                "negative amount. A reduction is a compensating entry."
            )
        return Money._of((self.amount * rate).quantize(EXPONENT, rounding=ROUNDING))

    def allocate(self, parts: int) -> list[Money]:
        """
        Split into `parts` amounts whose sum is exactly this amount.

        The remainder is distributed one smallest-unit at a time across the
        leading parts, so the first *remainder* parts receive one extra
        paisa. A negative amount is allocated on its magnitude and the sign
        restored to every part, which fixes an answer the exact-sum property
        alone cannot settle.

        :param parts: How many parts to produce. Must be one or more.
        :return: The parts, in order, summing exactly to this amount.
        :raises MoneyValidationError: If `parts` is less than one.
        """
        if parts < 1:
            raise MoneyValidationError(
                f"Cannot allocate into {parts} parts; the count must be one "
                "or more. An empty result would lose the amount."
            )
        # `to_integral_value()` with no explicit rounding consults the THREAD
        # decimal context, not this module's declared mode — a third rounding
        # point in a module whose premise is that it has exactly two, latent
        # on global mutable state. It is harmless today because the amount is
        # always pre-quantized to 2dp, so there is nothing to round; naming
        # the mode makes that independent of a context nobody here controls.
        total_paisa = int(self.amount.scaleb(2).to_integral_value(rounding=ROUNDING))
        sign = -1 if total_paisa < 0 else 1
        magnitude = abs(total_paisa)
        base, remainder = divmod(magnitude, parts)
        return [
            Money._of(Decimal(sign * (base + (1 if i < remainder else 0))).scaleb(-2))
            for i in range(parts)
        ]

    @classmethod
    def sum(cls, amounts: Iterable[Money]) -> Money:
        """
        Total a collection, with a zero identity for an empty one.

        Exists so that a dues total is never written as a builtin ``sum()``
        with a ``0`` start value, which would coerce or crash.

        :param amounts: The amounts to total.
        :return: Their total, or zero if there are none.
        """
        total = Decimal("0.00")
        for item in amounts:
            total += item.amount
        return cls._of(total)

    # -- predicates ----------------------------------------------------

    def is_zero(self) -> bool:
        """
        Report whether the amount is exactly zero.

        :return: True if zero.
        """
        return self.amount == 0

    def is_positive(self) -> bool:
        """
        Report whether the amount is greater than zero.

        :return: True if strictly positive.
        """
        return self.amount > 0

    def is_negative(self) -> bool:
        """
        Report whether the amount is less than zero.

        :return: True if strictly negative.
        """
        return self.amount < 0

    # -- comparison ----------------------------------------------------

    def __lt__(self, other: Money) -> bool:
        """
        Order against another amount.

        :param other: The amount to compare with.
        :return: True if this amount is smaller.
        :raises TypeError: If `other` is not a :class:`Money`.
        """
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        """
        Order against another amount.

        :param other: The amount to compare with.
        :return: True if this amount is smaller or equal.
        :raises TypeError: If `other` is not a :class:`Money`.
        """
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        """
        Order against another amount.

        :param other: The amount to compare with.
        :return: True if this amount is larger.
        :raises TypeError: If `other` is not a :class:`Money`.
        """
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        """
        Order against another amount.

        :param other: The amount to compare with.
        :return: True if this amount is larger or equal.
        :raises TypeError: If `other` is not a :class:`Money`.
        """
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount >= other.amount

    # -- representation ------------------------------------------------

    def format(self, locale: str = "en") -> str:
        """
        Render the amount for a person to read.

        **The digits are Latin 0-9 even under a Bangla locale** [BR6.6].
        That is a reconciliation rather than a fresh decision: the client
        already settled the rule in ``core/format/Numerals.kt`` --
        *numbers the app shows are Latin; text people typed is shown
        exactly as typed* -- because money, marks, dates and counts are
        the app's own output while a topic reading ``অধ্যায় ৩`` keeps its
        digits because a person wrote it. Had this gone the other way,
        the same amount would render in two different digit sets
        depending on which surface drew it.

        So `locale` governs the grouping and the currency mark, never
        the digit set. Grouping is **by lakh** under every locale this
        product has -- ``125400`` reads as ``1,25,400`` and not
        ``125,400``, which a Bangladeshi reader parses as a different
        magnitude.

        Paisa are stored and not shown, rounded with this module's one
        declared mode so a displayed total and a computed one cannot
        disagree by a rounding convention. This agrees with the client's
        ``Numerals.money``, which does the same.

        This is **presentation, not arithmetic**: it produces a string
        and nothing in the system reads one back. The wire form is
        :func:`app.money.wire.to_wire`, which is a different value for a
        different purpose.

        :param locale: The locale whose currency mark to use. ``bn``
            and ``en`` both group by lakh and both emit Latin digits;
            they differ only in the mark.
        :return: The amount as ``৳1,25,400``.
        """
        whole = self.amount.quantize(Decimal("1"), rounding=ROUNDING)
        grouped = _group_by_lakh(str(abs(whole)))
        mark = "৳" if locale.startswith("bn") else "BDT "
        sign = "-" if whole < 0 else ""
        return f"{sign}{mark}{grouped}"

    def __repr__(self) -> str:
        """
        Render for a developer, round-trippably.

        :return: A constructor expression.
        """
        return f"Money('{self.amount}')"

    def __str__(self) -> str:
        """
        Render the canonical amount string.

        This is the wire form for a non-negative amount: exactly two decimal
        places, no currency symbol, no thousands separator, Latin digits.
        Presentation for a human is a separate operation and a separate
        value.

        :return: The canonical two-decimal string.
        """
        return str(self.amount)


#: How many digits sit in the final group before lakh grouping starts.
_FINAL_GROUP = 3


def _group_by_lakh(digits: str) -> str:
    """
    Group digits the way a Bangladeshi reader parses them.

    Three from the right, then twos: ``125400`` becomes ``1,25,400``.
    Western grouping gives ``125,400``, which reads as a different
    magnitude to the person checking it.

    Mirrors ``Numerals.groupByLakh`` on the client deliberately: the two
    surfaces render the same amount, and a different grouping on each
    would be the same defect as a different digit set.

    :param digits: The unsigned digits.
    :return: The grouped digits.
    """
    if len(digits) <= _FINAL_GROUP:
        return digits
    last = digits[-_FINAL_GROUP:]
    rest = digits[:-_FINAL_GROUP]
    leading = [rest[max(index - 2, 0) : index] for index in range(len(rest), 0, -2)]
    return ",".join([*reversed(leading), last])


# Assigned after the class body because the value is an instance of the
# class it belongs to. Declared as a ClassVar above so mypy knows it exists.
Money.ZERO = Money(0)
