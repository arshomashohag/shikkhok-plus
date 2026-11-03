"""
The allocation invariants over randomized payments.

Amounts are drawn as whole paisa and built from their canonical string, so
the generator never holds a raw decimal. The case (short, exact, over) is
derived from the drawn figures, and only the choices valid for that case are
drawn, so every example exercises a successful allocation.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.money import Disposition, Money, allocate_payment

MAX_PAISA = 99_999_00


def _from_paisa(paisa: int) -> Money:
    """
    Build an amount from a whole number of paisa.

    :param paisa: The amount in paisa.
    :return: The amount.
    """
    return Money(f"{paisa // 100}.{paisa % 100:02d}")


def _child_choice(count: int) -> st.SearchStrategy[int | None]:
    """
    Draw a valid chosen child for a case that needs one.

    :param count: How many children the payment covers.
    :return: For one child, none or zero; otherwise any index.
    """
    if count == 1:
        return st.sampled_from([None, 0])
    return st.integers(min_value=0, max_value=count - 1)


@st.composite
def payments(
    draw: st.DrawFn,
) -> tuple[Money, list[Money], Disposition | None, int | None, int | None]:
    """
    Draw one valid payment and the choices its case requires.

    :param draw: Hypothesis draw function.
    :return: Received, owed, disposition, bearer index and credit index.
    """
    owed_paisa = draw(
        st.lists(st.integers(min_value=0, max_value=MAX_PAISA), min_size=1, max_size=4)
    )
    total_paisa = sum(owed_paisa)
    received_paisa = draw(st.integers(min_value=0, max_value=3 * total_paisa))
    count = len(owed_paisa)
    disposition: Disposition | None = None
    bearer: int | None = None
    credit: int | None = None
    if received_paisa < total_paisa:
        disposition = draw(st.sampled_from(["carried", "waived"]))
        bearer = draw(_child_choice(count))
    elif received_paisa > total_paisa:
        credit = draw(_child_choice(count))
    owed = [_from_paisa(p) for p in owed_paisa]
    return _from_paisa(received_paisa), owed, disposition, bearer, credit


@settings(max_examples=2000, deadline=None)
@given(payments())
def test_allocation_invariants(
    case: tuple[Money, list[Money], Disposition | None, int | None, int | None],
) -> None:
    received, owed, disposition, bearer, credit = case
    result = allocate_payment(
        received,
        owed,
        disposition=disposition,
        bearer_index=bearer,
        credit_index=credit,
    )
    total = Money.sum(owed)

    assert len(result.approved) == len(owed)
    assert Money.sum(result.approved) == received
    assert all(not amount.is_negative() for amount in result.approved)
    for index, (approved, due) in enumerate(zip(result.approved, owed, strict=True)):
        if index != result.credit_index:
            assert approved <= due
    if received < total:
        assert result.shortfall == total - received
        assert result.shortfall + received == total
    else:
        assert result.shortfall == Money.ZERO
