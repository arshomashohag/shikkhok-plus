"""The reviews switch: off unless the setting is exactly ``on``.

Reviews are off by default [H4 switch]. Every gated route depends on
:func:`app.reviews.switch.require_reviews_on`, which answers one
documented 404 so that nothing about an off feature is distinguishable
from any other refusal a client already handles.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.errors import AuthorizationError
from app.hub.public.settings import HUB_REVIEWS_ENV, reviews_enabled
from app.reviews.switch import (
    REVIEWS_OFF_RESPONSES,
    require_reviews_on,
    reviews_off,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_off_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(HUB_REVIEWS_ENV, raising=False)

    assert reviews_enabled() is False


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
    monkeypatch.setenv(HUB_REVIEWS_ENV, value)

    assert reviews_enabled() is expected


def test_read_at_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HUB_REVIEWS_ENV, "on")
    assert reviews_enabled() is True
    monkeypatch.delenv(HUB_REVIEWS_ENV)
    assert reviews_enabled() is False
    monkeypatch.setenv(HUB_REVIEWS_ENV, "on")
    assert reviews_enabled() is True


def test_the_environment_variable_is_named_as_documented() -> None:
    assert HUB_REVIEWS_ENV == "SHIKKHOKPLUS_HUB_REVIEWS"


def test_require_reviews_on_raises_documented_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(HUB_REVIEWS_ENV, raising=False)

    with pytest.raises(AuthorizationError) as raised:
        require_reviews_on()

    assert raised.value.code == "HUB_REVIEWS_OFF"
    assert raised.value.status == 404
    assert raised.value.message_key == "hub.review.off"


def test_require_reviews_on_passes_when_on(reviews_on: None) -> None:
    assert require_reviews_on() is None


def test_reviews_off_builds_the_verbatim_response() -> None:
    error = reviews_off()

    assert (error.code, error.status, error.message_key) == (
        "HUB_REVIEWS_OFF",
        404,
        "hub.review.off",
    )


def test_off_responses_document_the_404_envelope() -> None:
    entry = REVIEWS_OFF_RESPONSES[404]

    assert entry["description"] == "Reviews are switched off (HUB_REVIEWS_OFF)"
    assert entry["model"].__name__ == "ErrorEnvelope"


def test_message_key_published() -> None:
    published = json.loads((ROOT / "message-keys.json").read_text())["keys"]
    assert "hub.review.off" in published
    for bundle in ("values", "values-bn"):
        xml = (ROOT / "android/src/main/res" / bundle / "strings.xml").read_text()
        assert 'name="hub_review_off"' in xml
    kotlin = (
        ROOT
        / "android/src/main/kotlin/com/shikkhokplus/app/feature/auth/MessageKeys.kt"
    ).read_text()
    assert '"hub.review.off" to R.string.hub_review_off' in kotlin
