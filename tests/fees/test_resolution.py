"""Which fee is charged: the seat's, or the batch's [BR2.4].

**Written before `app/fees/resolution.py` existed.** The predicate holds
squarely: the answer is knowable from the rule, and a wrong answer bills
a student the teacher excused.

**The case that matters is zero.** `enrollment.fee_amount or
batch.default_fee` is the idiomatic Python line and it is wrong: a
deliberate permanent waiver of 0.00 is falsy, so the batch default
silently replaces it. The test is `IS NOT NULL`. The built model's own
docstring already says "Zero is a real fee of zero, which is a waiver" --
this suite is what makes that sentence binding on D3's code, since it
lives in another unit's file.

Pure arithmetic over two optional amounts, so no database fixture: the
rule is about NULL versus falsiness and needs no row to exercise.
"""

from __future__ import annotations

import pytest

from app.fees.resolution import FeeNotResolvable, resolve_fee
from app.money import Money


def test_the_seats_own_fee_wins_when_it_is_set() -> None:
    resolved = resolve_fee(
        enrollment_fee=Money("750.00"), batch_default=Money("1000.00")
    )

    assert resolved == Money("750.00")


def test_the_batch_default_applies_when_the_seat_sets_none() -> None:
    resolved = resolve_fee(enrollment_fee=None, batch_default=Money("1000.00"))

    assert resolved == Money("1000.00")


def test_zero_is_a_real_fee_and_not_a_missing_one() -> None:
    # THE SEPARATING CASE [BR2.4]. A falsiness test passes every other
    # case in this file and fails this one, converting a teacher's
    # deliberate permanent waiver into the batch default -- which bills
    # a student the teacher excused.
    resolved = resolve_fee(enrollment_fee=Money("0.00"), batch_default=Money("1000.00"))

    assert resolved == Money("0.00")
    assert resolved.is_zero()


def test_a_zero_batch_default_is_also_real() -> None:
    resolved = resolve_fee(enrollment_fee=None, batch_default=Money("0.00"))

    assert resolved == Money("0.00")


def test_both_null_refuses_rather_than_charging_zero() -> None:
    # Charging zero here would be a silent answer to a question nobody
    # asked: the teacher set no fee anywhere, which is a configuration
    # gap rather than a waiver. The two are indistinguishable once a
    # 0.00 charge is on the ledger.
    with pytest.raises(FeeNotResolvable):
        resolve_fee(enrollment_fee=None, batch_default=None)
