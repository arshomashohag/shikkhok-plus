"""An event is checked before anything connects to the database."""

from __future__ import annotations

import pytest

from app.seed.handler import request_of
from app.seed.scenario import SeedRefused, SeedRequest


def test_a_phone_alone_takes_the_defaults() -> None:
    assert request_of({"phone": "01711111111"}) == SeedRequest(phone="01711111111")


def test_months_and_seed_are_read() -> None:
    request = request_of({"phone": "01711111111", "months": 2, "seed": 7})
    assert (request.months, request.seed) == (2, 7)


@pytest.mark.parametrize(
    ("event", "message"),
    [
        ({}, "phone"),
        ({"phone": ""}, "phone"),
        ({"phone": 1711111111}, "phone"),
        ({"phone": "01711111111", "months": "3"}, "months"),
        ({"phone": "01711111111", "months": True}, "months"),
        ({"phone": "01711111111", "seed": 1.5}, "seed"),
        ({"phone": "01711111111", "monts": 3}, "unknown event fields: monts"),
        (["01711111111"], "JSON object"),
    ],
)
def test_a_malformed_event_is_refused_with_what_is_wrong(
    event: object, message: str
) -> None:
    with pytest.raises(SeedRefused, match=message):
        request_of(event)  # type: ignore[arg-type]
