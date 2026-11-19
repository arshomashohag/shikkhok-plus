"""The join-requests switch: off unless the setting is exactly ``on``.

Join requests are off by default [H5 switch]. Every gated route depends on
:func:`app.hub.enquiries.switch.require_enquiries_on`, which answers one
documented 404 so that nothing about an off feature is distinguishable
from any other refusal a client already handles. The switch never gates a
deletion, and it is independent of the reviews switch.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.errors import AuthorizationError
from app.hub.enquiries.switch import (
    ENQUIRIES_OFF_DESCRIPTION,
    ENQUIRIES_OFF_RESPONSES,
    enquiries_off,
    enquiries_off_responses,
    require_enquiries_on,
)
from app.hub.public.settings import (
    HUB_ENQUIRIES_ENV,
    enquiries_enabled,
    reviews_enabled,
)
from app.reviews.switch import require_reviews_on

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_off_when_unset(enquiries_off: None) -> None:
    assert enquiries_enabled() is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("on", True),
        ("ON", False),
        ("On", False),
        ("true", False),
        ("1", False),
        (" on", False),
        ("on ", False),
        ("yes", False),
        ("", False),
    ],
)
def test_on_only_for_exact_value(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    monkeypatch.setenv(HUB_ENQUIRIES_ENV, value)

    assert enquiries_enabled() is expected


def test_read_at_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HUB_ENQUIRIES_ENV, "on")
    assert enquiries_enabled() is True
    monkeypatch.delenv(HUB_ENQUIRIES_ENV)
    assert enquiries_enabled() is False
    monkeypatch.setenv(HUB_ENQUIRIES_ENV, "on")
    assert enquiries_enabled() is True


def test_the_environment_variable_is_named_as_documented() -> None:
    assert HUB_ENQUIRIES_ENV == "SHIKKHOKPLUS_HUB_ENQUIRIES"


def test_require_enquiries_on_raises_documented_error(enquiries_off: None) -> None:
    with pytest.raises(AuthorizationError) as raised:
        require_enquiries_on()

    assert raised.value.code == "HUB_ENQUIRIES_OFF"
    assert raised.value.status == 404
    assert raised.value.message_key == "hub.enquiry.off"


def test_require_enquiries_on_passes_when_on(enquiries_on: None) -> None:
    assert require_enquiries_on() is None


def test_enquiries_off_builds_the_verbatim_response() -> None:
    error = enquiries_off()

    assert (error.code, error.status, error.message_key) == (
        "HUB_ENQUIRIES_OFF",
        404,
        "hub.enquiry.off",
    )


def test_off_responses_document_the_404_envelope() -> None:
    entry = ENQUIRIES_OFF_RESPONSES[404]

    assert entry["description"] == (
        "HUB_ENQUIRIES_OFF: join requests are switched off."
    )
    assert entry["description"] == ENQUIRIES_OFF_DESCRIPTION
    assert entry["model"].__name__ == "ErrorEnvelope"


def test_off_responses_name_the_switch_before_another_404() -> None:
    entry = enquiries_off_responses(
        "ENQUIRY_TARGET_NOT_FOUND: no such teacher or class takes requests."
    )[404]

    assert entry["description"].startswith(ENQUIRIES_OFF_DESCRIPTION)
    assert entry["description"] == (
        "HUB_ENQUIRIES_OFF: join requests are switched off. "
        "ENQUIRY_TARGET_NOT_FOUND: no such teacher or class takes requests."
    )
    assert entry["model"].__name__ == "ErrorEnvelope"


def test_switches_are_independent_reviews_on_enquiries_off(
    reviews_on: None, enquiries_off: None
) -> None:
    assert reviews_enabled() is True
    assert enquiries_enabled() is False
    assert require_reviews_on() is None
    with pytest.raises(AuthorizationError) as raised:
        require_enquiries_on()
    assert raised.value.code == "HUB_ENQUIRIES_OFF"


def test_switches_are_independent_enquiries_on_reviews_off(
    reviews_off: None, enquiries_on: None
) -> None:
    assert enquiries_enabled() is True
    assert reviews_enabled() is False
    assert require_enquiries_on() is None
    with pytest.raises(AuthorizationError) as raised:
        require_reviews_on()
    assert raised.value.code == "HUB_REVIEWS_OFF"


def test_message_key_published() -> None:
    published = json.loads((ROOT / "message-keys.json").read_text())["keys"]
    assert "hub.enquiry.off" in published
    for bundle in ("values", "values-bn"):
        xml = (ROOT / "android/src/main/res" / bundle / "strings.xml").read_text()
        assert 'name="hub_enquiry_off"' in xml
    kotlin = (
        ROOT
        / "android/src/main/kotlin/com/shikkhokplus/app/feature/auth/MessageKeys.kt"
    ).read_text()
    assert '"hub.enquiry.off" to R.string.hub_enquiry_off' in kotlin
    for language in ("en", "bn"):
        generated = json.loads(
            (ROOT / f"web/src/i18n/generated/strings.{language}.json").read_text()
        )
        assert "hub_enquiry_off" in generated
    keys = json.loads((ROOT / "web/src/i18n/generated/message-keys.json").read_text())
    assert keys["hub.enquiry.off"] == "hub_enquiry_off"
