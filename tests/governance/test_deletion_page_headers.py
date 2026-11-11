"""The deletion page cannot be framed, sniffed or leak its URL [SEC-7].

``/account-deletion`` is a state-changing form served without a
session. Without these headers a phishing page could frame the genuine
origin and talk a person into typing their code into it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.html import HTML_SECURITY_HEADERS

EXPECTED = {
    "content-security-policy": (
        "default-src 'none'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}


def test_the_helper_carries_exactly_the_expected_headers() -> None:
    """The policy is the one reviewed, not a loosened copy.

    :return: None
    """
    assert {k.lower(): v for k, v in HTML_SECURITY_HEADERS.items()} == EXPECTED


def test_the_page_as_first_served_carries_the_headers(api_client: TestClient) -> None:
    """The GET page a person reaches from the Play listing.

    :param api_client: The test client
    :return: None
    """
    response = api_client.get("/account-deletion")

    assert response.status_code == 200
    for name, value in EXPECTED.items():
        assert response.headers.get(name) == value, name


@pytest.mark.parametrize(
    "form",
    [
        {"phone": "not a number"},
        {"phone": "01712345678"},
        {"phone": "01712345678", "code": "123456"},
    ],
)
def test_every_answered_form_carries_the_headers(
    api_client: TestClient, form: dict[str, str]
) -> None:
    """Invalid, code-sent and refused pages alike.

    :param api_client: The test client
    :param form: The form fields posted
    :return: None
    """
    response = api_client.post("/account-deletion", data=form)

    assert response.headers["content-type"].startswith("text/html")
    for name, value in EXPECTED.items():
        assert response.headers.get(name) == value, name


def test_the_page_needs_nothing_the_policy_forbids(api_client: TestClient) -> None:
    """``default-src 'none'`` holds only while the page loads nothing.

    :param api_client: The test client
    :return: None
    """
    page = api_client.get("/account-deletion").text.lower()

    for forbidden in ("<script", "<style", "style=", "<link", "<img", "<iframe"):
        assert forbidden not in page, forbidden
