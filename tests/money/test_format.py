"""`Money.format` renders for a person, in Latin digits [BR6.6].

**The rule is a reconciliation, not a decision made here.** The client's
`core/format/Numerals.kt` already settled it: numbers the app shows are
Latin, and text people typed is shown exactly as typed. Money is the
app's own output, so it is Latin even under a Bangla locale -- otherwise
the same amount renders in two different digit sets depending on which
surface drew it.

The grouping assertions mirror `Numerals.groupByLakh` for the same
reason: a different grouping on each surface is the same class of defect
as a different digit set.

**This is presentation, not arithmetic.** Nothing in the system reads a
formatted string back; the wire form is `app.money.wire.to_wire`, which
is a different value for a different purpose.
"""

from __future__ import annotations

import pytest

from app.money import Money

#: The Bengali digit range. No formatted amount may contain one.
BENGALI_DIGITS = frozenset("০১২৩৪৫৬৭৮৯")


@pytest.mark.parametrize("locale", ["bn", "bn-BD", "en", "en-US"])
def test_no_formatted_amount_contains_a_bengali_digit(locale: str) -> None:
    rendered = Money("125400.00").format(locale)

    assert not (BENGALI_DIGITS & set(rendered)), (
        f"{rendered!r} carries a Bengali digit under locale {locale}; the "
        "client renders the same amount in Latin, so the two surfaces "
        "would disagree [BR6.6]"
    )


def test_grouping_is_by_lakh_not_by_thousand() -> None:
    # Western grouping gives 125,400, which a Bangladeshi reader parses
    # as a different magnitude.
    assert Money("125400.00").format("bn") == "৳1,25,400"


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("0.00", "৳0"),
        ("1.00", "৳1"),
        ("99.00", "৳99"),
        ("100.00", "৳100"),
        ("999.00", "৳999"),
        ("1000.00", "৳1,000"),
        ("99999.00", "৳99,999"),
        ("100000.00", "৳1,00,000"),
        ("12500000.00", "৳1,25,00,000"),
    ],
)
def test_the_group_boundaries(amount: str, expected: str) -> None:
    assert Money(amount).format("bn") == expected


def test_paisa_are_rounded_rather_than_shown() -> None:
    # 2dp is stored, not displayed, and the rounding uses this module's
    # one declared mode so a displayed total and a computed one cannot
    # disagree by a rounding convention.
    assert Money("1234.49").format("bn") == "৳1,234"
    assert Money("1234.50").format("bn") == "৳1,235"


def test_the_locale_chooses_the_mark_and_not_the_digits() -> None:
    assert Money("1500.00").format("bn") == "৳1,500"
    assert Money("1500.00").format("en") == "BDT 1,500"


def test_the_default_locale_renders() -> None:
    assert Money("1500.00").format() == "BDT 1,500"


def test_a_negative_amount_carries_its_sign_before_the_mark() -> None:
    # A negative amount cannot cross the API -- the wire pattern admits
    # no sign -- but it is representable inside the module, and a
    # formatter that dropped the sign would display a debt as a credit.
    assert Money("-250.00").format("bn") == "-৳250"
