"""One canonical form for every phone number the server stores or compares.

**Written before the function existed.** Every expected value is knowable
from the numbering plan without an implementation, and a wrong answer is
an identity and authorization error: numbers were stored exactly as
typed, so one person signing in as ``01711111111`` and later as
``+8801711111111`` held two accounts, a teacher's ``01711-234567`` never
matched the guardian's account, and the per-number SMS ceiling counted
each spelling separately.
"""

from __future__ import annotations

import pytest

from app.accounts.phone import canonical_phone
from app.errors import ValidationError

CANONICAL = "+8801711234567"


@pytest.mark.parametrize(
    "typed",
    [
        "01711234567",
        "01711-234567",
        "017 1123 4567",
        "(017) 11234567",
        "8801711234567",
        "+8801711234567",
        "+880 1711-234567",
        "008801711234567",
        "০১৭১১২৩৪৫৬৭",
        "+৮৮০১৭১১২৩৪৫৬৭",
        "  01711234567  ",
    ],
)
def test_every_spelling_of_one_number_is_the_same_number(typed: str) -> None:
    """The spellings people actually type all name one account.

    :param typed: One spelling of the number
    :return: None
    """
    assert canonical_phone(typed) == CANONICAL


@pytest.mark.parametrize("prefix", ["013", "014", "015", "016", "017", "018", "019"])
def test_every_mobile_operator_prefix_is_accepted(prefix: str) -> None:
    """Each Bangladeshi mobile prefix in use is a valid number.

    :param prefix: The operator prefix
    :return: None
    """
    assert canonical_phone(f"{prefix}11234567") == f"+880{prefix[1:]}11234567"


@pytest.mark.parametrize(
    "typed",
    [
        "",
        "   ",
        "0171123456",  # ten digits: one short
        "017112345678",  # twelve digits: one long
        "01211234567",  # 012 is not a mobile prefix
        "02-9123456",  # a Dhaka landline cannot receive an OTP
        "+15551234567",  # not Bangladeshi
        "+8801711234567x",
        "01711234567abc",
        "phone",
    ],
)
def test_anything_else_is_refused_with_a_message_key(typed: str) -> None:
    """A number that cannot receive an OTP is refused, not stored.

    The refusal is the app's own ``ValidationError``, so it reaches the
    client as an envelope with a ``message_key`` rather than FastAPI's
    bare 422 that the client cannot translate.

    :param typed: Something that is not a Bangladeshi mobile number
    :return: None
    """
    with pytest.raises(ValidationError) as caught:
        canonical_phone(typed)

    assert caught.value.message_key == "phone.invalid"


def test_canonical_input_passes_through_unchanged() -> None:
    """Canonicalising is idempotent, so applying it twice is harmless.

    :return: None
    """
    assert canonical_phone(canonical_phone("01711234567")) == CANONICAL
