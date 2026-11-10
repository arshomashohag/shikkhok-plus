"""The pure parts of passwords and email: hashing, policy, parsing, SMTP.

No database: each of these is a function of its inputs, and each is the
kind of code that passes a happy-path test while failing the case that
matters -- a malformed hash that verifies, an address stored in two
spellings, an SMTP adapter that sends in clear.
"""

from __future__ import annotations

import re
import smtplib
from typing import Any
from unittest import mock

import pytest

from app.accounts.identifier import Channel, Identifier, canonical_email
from app.auth import passwords
from app.errors import ValidationError
from app.gateway.email import (
    EMAIL_ADAPTER_ENV,
    EmailMessage,
    NullEmailGateway,
    build_email_gateway,
    email_gateway_configured,
)
from app.gateway.email_html import (
    PLAY_URL,
    SITE_URL_ENV,
    render_email_html,
    site_url_from_env,
)
from app.gateway.ses_smtp import SesSmtpGateway
from app.gateway.sms import Outcome
from app.gateway.template import render_email_code
from app.schemas.identifier import IdentifierFields

# ------------------------------------------------------------------ hashing


def test_a_hash_verifies_its_password_and_nothing_else() -> None:
    stored = passwords.hash_password("correct horse battery")
    assert passwords.verify_password("correct horse battery", stored)
    assert not passwords.verify_password("correct horse batterY", stored)
    assert not passwords.verify_password("", stored)


def test_two_hashes_of_one_password_differ() -> None:
    # A per-hash salt: equal passwords are not visible as equal rows.
    assert passwords.hash_password("same password") != passwords.hash_password(
        "same password"
    )


@pytest.mark.parametrize(
    "stored",
    ["", "garbage", "bcrypt$1$2$3$4$5", "scrypt$x$8$5$AAAA$BBBB", "scrypt$16384$8$5"],
)
def test_a_malformed_hash_verifies_nothing(stored: str) -> None:
    assert not passwords.verify_password("anything at all", stored)


def test_a_hash_with_old_parameters_is_marked_for_rehash() -> None:
    assert not passwords.needs_rehash(passwords.hash_password("fresh password"))
    assert passwords.needs_rehash("scrypt$1024$8$1$AAAA$BBBB")


@pytest.mark.parametrize(
    ("password", "key"),
    [
        ("1234567", "auth.password.too_short"),
        ("x" * (passwords.MAX_LENGTH + 1), "auth.password.too_long"),
        ("Password", "auth.password.too_common"),
        ("  qwerty123 ", "auth.password.too_common"),
        ("zzzzzzzzzz", "auth.password.too_common"),
    ],
)
def test_the_policy_refusals(password: str, key: str) -> None:
    with pytest.raises(ValidationError) as refused:
        passwords.check_policy(password)
    assert refused.value.message_key == key


def test_length_is_counted_in_characters_not_bytes() -> None:
    # Eight Bangla characters are 24 bytes; the person typed eight.
    passwords.check_policy("আমারপাসওয়")
    with pytest.raises(ValidationError):
        passwords.check_policy("আমারপাস")


# --------------------------------------------------------------- identifiers


def test_an_address_has_one_stored_spelling() -> None:
    assert canonical_email("  Rahim@Example.COM ") == "rahim@example.com"


@pytest.mark.parametrize(
    "raw", ["", "rahim", "rahim@", "@example.com", "a b@example.com", "x@y"]
)
def test_a_malformed_address_is_refused(raw: str) -> None:
    with pytest.raises(ValidationError) as refused:
        canonical_email(raw)
    assert refused.value.message_key == "email.invalid"


def test_an_overlong_address_is_refused() -> None:
    with pytest.raises(ValidationError):
        canonical_email("a" * 250 + "@x.com")


def test_an_email_rate_key_fits_the_counter_column_and_hides_the_address() -> None:
    key = Identifier.email("someone@example.com").rate_key
    assert len(key) <= 64
    assert "someone" not in key
    # A phone number keeps its old key, so existing counters carry over.
    assert Identifier.phone("01711234567").rate_key == "+8801711234567"


def test_the_column_is_one_of_two_literals() -> None:
    assert Identifier(Channel.PHONE, "+8801711234567").column == "phone"
    assert Identifier(Channel.EMAIL, "a@b.com").column == "email"


@pytest.mark.parametrize(
    "body",
    [{}, {"phone": "01711234567", "email": "a@b.com"}],
)
def test_exactly_one_identifier(body: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        IdentifierFields.model_validate(body)


def test_the_identifier_is_tagged_with_its_channel() -> None:
    parsed = IdentifierFields.model_validate({"email": "A@B.com"})
    assert parsed.identifier == Identifier(Channel.EMAIL, "a@b.com")


# -------------------------------------------------------------------- email


def test_the_email_carries_the_code_in_both_languages() -> None:
    message = render_email_code("482913")
    assert "482913" in message.subject
    assert message.text.count("482913") == 2
    assert "কোড" in message.text and "code" in message.text


def test_the_html_part_carries_the_code_and_both_languages() -> None:
    page = render_email_code("482913").html
    assert page is not None
    assert page.count("482913") == 1
    assert "যাচাই কোড" in page and "verification code" in page
    assert "5 minutes" in page and "৫ মিনিটের" in page


def test_the_html_part_escapes_the_code() -> None:
    # Always six digits in practice; escaped at the one substitution site.
    page = render_email_html("<b>&")
    assert "<b>&" not in page and "&lt;b&gt;&amp;" in page


def test_the_html_part_fetches_nothing() -> None:
    # A remote image is a read receipt nobody agreed to; the only URLs are
    # links a person may choose to follow.
    page = render_email_html("482913", "https://site.example.com")
    assert "<img" not in page and "src=" not in page and "url(" not in page
    assert sorted(re.findall(r"https?://[^\s\"<]+", page)) == sorted(
        [PLAY_URL, "https://site.example.com/bn/", "https://site.example.com/"]
    )


def test_without_a_site_url_the_website_line_is_left_out() -> None:
    page = render_email_html("482913")
    assert re.findall(r"https?://[^\s\"<]+", page) == [PLAY_URL]
    assert "Learn more" not in page


def test_the_website_line_links_both_languages() -> None:
    page = render_email_html("482913", "https://site.example.com")
    assert 'href="https://site.example.com/bn/"' in page
    assert 'href="https://site.example.com/"' in page
    assert ">site.example.com</a>" in page


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://site.example.com", "https://site.example.com"),
        ("https://site.example.com/", "https://site.example.com"),
        ("http://localhost:8080", "http://localhost:8080"),
        ("", None),
        ("http://site.example.com", None),
        ("https://site.example.com/path", None),
        ("https://site.example.com/?q=1", None),
        ("javascript:alert(1)", None),
        ('https://a.example.com/"><script>', None),
    ],
)
def test_the_site_url_must_be_a_bare_origin(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: str | None
) -> None:
    monkeypatch.setenv(SITE_URL_ENV, raw)
    assert site_url_from_env() == expected


def test_a_bad_site_url_drops_the_link_not_the_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SITE_URL_ENV, "ftp://site.example.com")
    message = render_email_code("482913")
    assert message.html is not None and "482913" in message.html
    assert "site.example.com" not in message.html


def test_the_code_comes_before_the_promotion() -> None:
    page = render_email_html("482913")
    assert page.index("482913") < page.index("About ShikkhokPlus")
    assert page.index("ignore this email") < page.index("About ShikkhokPlus")


def test_the_null_adapter_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(EMAIL_ADAPTER_ENV, raising=False)
    assert isinstance(build_email_gateway(), NullEmailGateway)
    assert not email_gateway_configured()


def test_a_half_configured_ses_adapter_refuses_to_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(EMAIL_ADAPTER_ENV, "ses")
    monkeypatch.setenv("SHIKKHOKPLUS_SES_SMTP_HOST", "email-smtp.x.amazonaws.com")
    monkeypatch.delenv("SHIKKHOKPLUS_SES_SMTP_PASSWORD", raising=False)
    assert not email_gateway_configured()
    with pytest.raises(RuntimeError, match="not fully configured"):
        build_email_gateway()


def _gateway() -> SesSmtpGateway:
    return SesSmtpGateway(
        host="email-smtp.example.amazonaws.com",
        port=587,
        username="AKIAEXAMPLE",
        password="secret",  # noqa: S106 -- a test value
        sender="ShikkhokPlus <no-reply@mail.example.com>",
        configuration_set="shikkhokplus-test-email",
    )


def test_ses_sends_over_starttls_from_the_bare_address() -> None:
    smtp = mock.MagicMock()
    with mock.patch.object(smtplib, "SMTP") as factory:
        factory.return_value.__enter__.return_value = smtp
        result = _gateway().send(
            "rahim@example.com",
            EmailMessage(subject="code", text="123456"),
            "cid",
        )
    assert result.outcome is Outcome.SENT
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("AKIAEXAMPLE", "secret")
    kwargs: dict[str, Any] = smtp.send_message.call_args.kwargs
    # The envelope sender is what the IAM policy's ses:FromAddress matches.
    assert kwargs["from_addr"] == "no-reply@mail.example.com"
    assert kwargs["to_addrs"] == ["rahim@example.com"]
    mail = smtp.send_message.call_args.args[0]
    assert mail["X-SES-CONFIGURATION-SET"] == "shikkhokplus-test-email"


def test_ses_sends_html_as_an_alternative_to_the_text() -> None:
    smtp = mock.MagicMock()
    with mock.patch.object(smtplib, "SMTP") as factory:
        factory.return_value.__enter__.return_value = smtp
        _gateway().send("a@b.com", render_email_code("482913"), "c")
    mail = smtp.send_message.call_args.args[0]
    assert mail.get_content_type() == "multipart/alternative"
    parts = [part.get_content_type() for part in mail.iter_parts()]
    # Text first: a client shows the last alternative it can render.
    assert parts == ["text/plain", "text/html"]
    assert "482913" in mail.get_body(preferencelist=("plain",)).get_content()
    assert "482913" in mail.get_body(preferencelist=("html",)).get_content()


def test_a_text_only_message_stays_single_part() -> None:
    smtp = mock.MagicMock()
    with mock.patch.object(smtplib, "SMTP") as factory:
        factory.return_value.__enter__.return_value = smtp
        _gateway().send("a@b.com", EmailMessage(subject="s", text="t"), "c")
    assert smtp.send_message.call_args.args[0].get_content_type() == "text/plain"


def test_a_server_without_starttls_fails_rather_than_sending_in_clear() -> None:
    smtp = mock.MagicMock()
    smtp.starttls.side_effect = smtplib.SMTPNotSupportedError("no STARTTLS")
    with mock.patch.object(smtplib, "SMTP") as factory:
        factory.return_value.__enter__.return_value = smtp
        result = _gateway().send("a@b.com", EmailMessage(subject="s", text="t"), "c")
    assert result.outcome is Outcome.FAILED
    smtp.send_message.assert_not_called()


def test_a_timeout_is_unknown_not_failed() -> None:
    with mock.patch.object(smtplib, "SMTP", side_effect=TimeoutError()):
        result = _gateway().send("a@b.com", EmailMessage(subject="s", text="t"), "c")
    assert result.outcome is Outcome.UNKNOWN
