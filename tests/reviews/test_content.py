"""What a review may say, and how an author is named to an administrator.

Pure functions, no database. The contact cases are Review Focus 3's, every
one of them, in both directions: smuggled contact details are refused, and
the ordinary numbers a review of a tuition batch is full of are not.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.errors import ValidationError
from app.help.identity import requester_ref
from app.reviews.content import contains_url, refuse_contact
from app.reviews.identity import review_author_ref

#: Contact details a review must not carry: phone numbers in Bangla digits,
#: with separators and with the country code, and web addresses with and
#: without a scheme.
SMUGGLED = [
    "Call ০১৭১২৩৪৫৬৭৮ for notes",
    "Ask on 017 1234 5678",
    "Reach the tutor at +880-1712-345678",
    "See www.example.com",
    "Details at example.com.bd/x",
    "Our page fb.com/page",
    "Visit https://notes.example",
    "WWW.EXAMPLE.ORG",
    "join tuition-group.online today",
]

#: Ordinary review text, full of numbers and full stops, that must pass.
ORDINARY = [
    "Class 10, 2024 batch, GPA 4.5",
    "Tk 1500 a month",
    "4.30 pm",
    "Sir explains physics clearly. My son improved a lot.",
    "স্যার খুব যত্ন নিয়ে পড়ান।",
]


@pytest.mark.parametrize("text", SMUGGLED)
def test_contact_refusal_cases_refused(text: str) -> None:
    with pytest.raises(ValidationError) as refused:
        refuse_contact("body", text)

    assert refused.value.code == "REVIEW_CONTAINS_CONTACT"
    assert refused.value.message_key == "hub.review.contains_contact"
    assert refused.value.details == {"field": "body"}


@pytest.mark.parametrize("text", ORDINARY)
def test_contact_refusal_cases_pass(text: str) -> None:
    refuse_contact("body", text)

    assert not contains_url(text)


def test_contact_refusal_names_the_field_it_was_given() -> None:
    with pytest.raises(ValidationError) as refused:
        refuse_contact("reply", "www.example.com")

    assert refused.value.details == {"field": "reply"}


def test_no_text_is_not_contact() -> None:
    refuse_contact("body", None)


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("http://x", True),
        ("www.x", True),
        ("shop.co", True),
        ("my.link", True),
        ("example.company", False),
        ("e.g. the best", False),
        ("v2.0 notes", False),
    ],
)
def test_contains_url_is_the_published_pattern(text: str, found: bool) -> None:
    assert contains_url(text) is found


def test_author_ref_is_not_the_help_requester_ref() -> None:
    """Call 14: one person's review and help tickets cannot be joined."""
    account_id = uuid.uuid4()

    ref = review_author_ref(account_id)

    expected = hashlib.sha256(
        b"shikkhokplus/hub-review-author/v1:" + account_id.bytes
    ).hexdigest()[:10]
    assert ref == expected.upper()
    assert ref != requester_ref(account_id)
    assert review_author_ref(account_id) == ref
    assert review_author_ref(uuid.uuid4()) != ref
