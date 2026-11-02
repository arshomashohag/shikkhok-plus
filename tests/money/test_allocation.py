"""
One guardian payment allocated across several children.

The figures below are the worked cases from the review design: each was
computed by hand from the fill order, not read back from the implementation.
"""

import pytest

from app.money import Disposition, Money, MoneyValidationError, allocate_payment

M = Money


def test_exact_payment_approves_each_at_what_they_owe() -> None:
    result = allocate_payment(
        M("2000"),
        [M("1000"), M("1000")],
        disposition=None,
        bearer_index=None,
        credit_index=None,
    )
    assert result.approved == (M("1000"), M("1000"))
    assert result.shortfall == Money.ZERO
    assert result.bearer_index is None
    assert result.credit_index is None


def test_short_two_children_bearer_takes_the_shortfall() -> None:
    result = allocate_payment(
        M("1500"),
        [M("1000"), M("1000")],
        disposition="carried",
        bearer_index=0,
        credit_index=None,
    )
    assert result.approved == (M("500"), M("1000"))
    assert result.shortfall == M("500")
    assert result.bearer_index == 0
    assert result.credit_index is None


def test_shortfall_bigger_than_bearer_spills_from_the_end() -> None:
    result = allocate_payment(
        M("500"),
        [M("1000"), M("1000"), M("1000")],
        disposition="carried",
        bearer_index=0,
        credit_index=None,
    )
    assert result.approved == (M("0"), M("500"), M("0"))
    assert result.shortfall == M("2500")


def test_bearer_in_the_middle_is_filled_after_both_neighbours() -> None:
    result = allocate_payment(
        M("1500"),
        [M("1000"), M("1000"), M("1000")],
        disposition="carried",
        bearer_index=1,
        credit_index=None,
    )
    assert result.approved == (M("1000"), M("0"), M("500"))
    assert result.shortfall == M("1500")
    assert result.bearer_index == 1


def test_zero_owed_child_takes_no_receipt() -> None:
    result = allocate_payment(
        M("800"),
        [M("0"), M("1000")],
        disposition="waived",
        bearer_index=1,
        credit_index=None,
    )
    assert result.approved == (M("0"), M("800"))
    assert result.shortfall == M("200")


def test_over_payment_credits_the_chosen_child() -> None:
    result = allocate_payment(
        M("2500"),
        [M("1000"), M("1000")],
        disposition=None,
        bearer_index=None,
        credit_index=1,
    )
    assert result.approved == (M("1000"), M("1500"))
    assert result.shortfall == Money.ZERO
    assert result.credit_index == 1
    assert result.bearer_index is None


def test_single_child_over_payment_needs_no_choice() -> None:
    result = allocate_payment(
        M("1200"),
        [M("1000")],
        disposition=None,
        bearer_index=None,
        credit_index=None,
    )
    assert result.approved == (M("1200"),)
    assert result.credit_index == 0
    assert result.shortfall == Money.ZERO


def test_single_child_short_needs_disposition_not_bearer() -> None:
    result = allocate_payment(
        M("600"),
        [M("1000")],
        disposition="carried",
        bearer_index=None,
        credit_index=None,
    )
    assert result.approved == (M("600"),)
    assert result.bearer_index == 0
    assert result.shortfall == M("400")


def test_single_child_accepts_an_explicit_zero_index() -> None:
    short = allocate_payment(
        M("600"),
        [M("1000")],
        disposition="waived",
        bearer_index=0,
        credit_index=None,
    )
    over = allocate_payment(
        M("1200"),
        [M("1000")],
        disposition=None,
        bearer_index=None,
        credit_index=0,
    )
    assert short.approved == (M("600"),)
    assert short.bearer_index == 0
    assert over.approved == (M("1200"),)
    assert over.credit_index == 0


def test_refuses_no_children() -> None:
    with pytest.raises(MoneyValidationError, match=r"^ALLOCATION_NO_CHILDREN"):
        allocate_payment(
            M("100"),
            [],
            disposition=None,
            bearer_index=None,
            credit_index=None,
        )


def test_refuses_negative_received() -> None:
    with pytest.raises(MoneyValidationError, match=r"^ALLOCATION_RECEIVED_NEGATIVE"):
        allocate_payment(
            M("-1"),
            [M("1000")],
            disposition="carried",
            bearer_index=None,
            credit_index=None,
        )


def test_refuses_negative_owed_entry() -> None:
    with pytest.raises(MoneyValidationError, match=r"^ALLOCATION_OWED_NEGATIVE"):
        allocate_payment(
            M("100"),
            [M("1000"), M("-0.01")],
            disposition="carried",
            bearer_index=0,
            credit_index=None,
        )


def test_refuses_short_payment_without_disposition() -> None:
    with pytest.raises(MoneyValidationError, match=r"^ALLOCATION_DISPOSITION_REQUIRED"):
        allocate_payment(
            M("600"),
            [M("1000")],
            disposition=None,
            bearer_index=None,
            credit_index=None,
        )


def test_refuses_disposition_on_exact_payment() -> None:
    with pytest.raises(
        MoneyValidationError, match=r"^ALLOCATION_DISPOSITION_NOT_APPLICABLE"
    ):
        allocate_payment(
            M("2000"),
            [M("1000"), M("1000")],
            disposition="waived",
            bearer_index=None,
            credit_index=None,
        )


def test_refuses_disposition_on_over_payment() -> None:
    with pytest.raises(
        MoneyValidationError, match=r"^ALLOCATION_DISPOSITION_NOT_APPLICABLE"
    ):
        allocate_payment(
            M("1200"),
            [M("1000")],
            disposition="carried",
            bearer_index=None,
            credit_index=None,
        )


def test_refuses_short_several_children_without_bearer() -> None:
    with pytest.raises(MoneyValidationError, match=r"^ALLOCATION_BEARER_REQUIRED"):
        allocate_payment(
            M("1500"),
            [M("1000"), M("1000")],
            disposition="carried",
            bearer_index=None,
            credit_index=None,
        )


def test_refuses_over_several_children_without_credit_child() -> None:
    with pytest.raises(
        MoneyValidationError, match=r"^ALLOCATION_CREDIT_CHILD_REQUIRED"
    ):
        allocate_payment(
            M("2500"),
            [M("1000"), M("1000")],
            disposition=None,
            bearer_index=None,
            credit_index=None,
        )


def test_refuses_bearer_index_out_of_range() -> None:
    with pytest.raises(MoneyValidationError, match=r"^ALLOCATION_INDEX_OUT_OF_RANGE"):
        allocate_payment(
            M("1500"),
            [M("1000"), M("1000")],
            disposition="carried",
            bearer_index=5,
            credit_index=None,
        )


def test_refuses_negative_credit_index() -> None:
    with pytest.raises(MoneyValidationError, match=r"^ALLOCATION_INDEX_OUT_OF_RANGE"):
        allocate_payment(
            M("2500"),
            [M("1000"), M("1000")],
            disposition=None,
            bearer_index=None,
            credit_index=-1,
        )


@pytest.mark.parametrize(
    ("received", "disposition", "bearer_index", "credit_index"),
    [
        ("2000", None, 0, None),
        ("2000", None, None, 1),
        ("1500", "carried", 0, 1),
        ("2500", None, 0, 1),
    ],
    ids=[
        "bearer-on-exact",
        "credit-on-exact",
        "credit-on-short",
        "bearer-on-over",
    ],
)
def test_refuses_an_index_that_does_not_apply(
    received: str,
    disposition: Disposition | None,
    bearer_index: int | None,
    credit_index: int | None,
) -> None:
    with pytest.raises(MoneyValidationError, match=r"^ALLOCATION_INDEX_NOT_APPLICABLE"):
        allocate_payment(
            M(received),
            [M("1000"), M("1000")],
            disposition=disposition,
            bearer_index=bearer_index,
            credit_index=credit_index,
        )
