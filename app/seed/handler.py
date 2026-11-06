"""The seeder's one entry point: an event in, a report out.

Shared by the Lambda runtime and the command line, so both validate an
event the same way. The event is::

    {"phone": "+8801711111111", "months": 3, "seed": 20261106}

``months`` and ``seed`` are optional. The phone is accepted in any form
the app accepts and is never logged [NFR24.6].
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import Engine

from app.seed.scenario import SeedRefused, SeedRequest, seed

__all__ = ["handle", "request_of"]


def request_of(event: Mapping[str, object]) -> SeedRequest:
    """Read and type-check an event.

    :param event: The decoded event
    :return: The request it describes
    :raises SeedRefused: A field is missing or the wrong type
    """
    if not isinstance(event, Mapping):
        raise SeedRefused('the event must be a JSON object like {"phone": "..."}')
    unknown = set(event) - {"phone", "months", "seed"}
    if unknown:
        raise SeedRefused(f"unknown event fields: {', '.join(sorted(unknown))}")
    phone = event.get("phone")
    if not isinstance(phone, str) or not phone.strip():
        raise SeedRefused('the event needs "phone": the teacher\'s number')
    defaults = SeedRequest(phone=phone)
    months = event.get("months", defaults.months)
    random_seed = event.get("seed", defaults.seed)
    # bool is an int subclass; true is not a month count.
    if not isinstance(months, int) or isinstance(months, bool):
        raise SeedRefused('"months" must be a whole number')
    if not isinstance(random_seed, int) or isinstance(random_seed, bool):
        raise SeedRefused('"seed" must be a whole number')
    return SeedRequest(phone=phone, months=months, seed=random_seed)


def handle(engine: Engine, event: Mapping[str, object]) -> dict[str, object]:
    """Seed the account the event names.

    :param engine: The engine to write through
    :param event: The decoded event
    :return: The report, JSON-safe
    :raises SeedRefused: The event or the run was refused
    """
    return seed(engine, request_of(event)).as_dict()
