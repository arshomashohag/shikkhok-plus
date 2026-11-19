"""A join request's text and the guardian's contact are never logged [H5].

The Global Constraint says ``student_name``, ``message`` and the contact
are never logged at any level. It holds by construction: nothing in
``app/hub/enquiries`` logs, the engine hides bound parameters, and an
error envelope echoes no input. This makes it mechanical [team: "where a
rule is important, it is mechanical"; H5 final review M5]: a whole
send, read, close and withdraw over HTTP, then a send that fails with a
500 from a statement bound with the canaries, all captured at DEBUG on the
root logger, and no canary in any record, its arguments or its traceback.

The app runs on an engine built by :func:`app.db.session.build_engine`, the
production builder, rather than the suite's plain test engine, so the
engine settings under test are the ones that ship.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import build_engine
from app.hub.enquiries import sending
from tests.conftest import bearer
from tests.enquiries.support import enquirable_owner, guardian

#: Typed into the request; never in a log line.
STUDENT_CANARY: Final = "Zubaydacanary Qilfoyle"

#: Typed into the request; never in a log line.
MESSAGE_CANARY: Final = "Wantsxyzcanary chemistry"

#: The guardian's number as typed. The owner reads it back, shared.
PHONE_CANARY: Final = "01398765432"

#: What would betray the number in any rendering: its subscriber digits,
#: which every form of it carries (``0139...``, ``+880139...``).
PHONE_DIGITS: Final = "1398765432"

#: Every string that must appear in no record.
CANARIES: Final = (STUDENT_CANARY, MESSAGE_CANARY, PHONE_DIGITS)


@pytest.fixture
def shipped_client(api_client: TestClient, restricted_url: str) -> Iterator[TestClient]:
    """Serve the app on the production engine builder, 500s rendered.

    :param api_client: The suite's client, whose app is reused
    :param restricted_url: The restricted role's URL
    :return: A context manager yielding the client
    """
    engine = build_engine(restricted_url)
    app = api_client.app
    assert isinstance(app, FastAPI)
    previous = app.state.engine
    app.state.engine = engine
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.state.engine = previous
        engine.dispose()


def _rendered(record: logging.LogRecord) -> str:
    """Render everything a record carries, as any handler could print it.

    :param record: A captured record
    :return: The formatted line, its traceback, its raw arguments and fields
    """
    return logging.Formatter().format(record) + repr(vars(record))


@pytest.mark.usefixtures("enquiries_on")
def test_join_request_text_and_contact_are_never_logged(
    shipped_client: TestClient,
    owner_session: Session,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = enquirable_owner(owner_session)
    sender = guardian(owner_session, phone=PHONE_CANARY)
    mine = bearer(owner_session, sender)
    teacher = bearer(owner_session, world.lens.account_id)
    send = f"/v1/hub/owners/{world.owner_slug}/enquiries"
    body = {
        "student_name": STUDENT_CANARY,
        "class_level": "class_8",
        "message": MESSAGE_CANARY,
        "batch_id": str(world.batch_id),
        "share_contact": True,
        "declares_adult_guardian": True,
    }

    with caplog.at_level(logging.DEBUG):
        # The capture's precondition: DEBUG reaches the root and the handler.
        assert logging.getLogger().getEffectiveLevel() == logging.DEBUG
        assert caplog.handler.level <= logging.DEBUG
        sent = shipped_client.post(send, json=body, headers=mine)
        assert sent.status_code == 201, sent.text
        enquiry = sent.json()["id"]
        read = shipped_client.get(f"/v1/hub/enquiries/{enquiry}", headers=teacher)
        assert read.status_code == 200, read.text
        # The owner was shown the canaries, so the run carried them.
        assert read.json()["student_name"] == STUDENT_CANARY
        assert PHONE_DIGITS in read.json()["guardian_phone"]
        closed = shipped_client.post(
            f"/v1/hub/enquiries/{enquiry}/close",
            json={"outcome": "not_now"},
            headers=teacher,
        )
        assert closed.status_code == 200, closed.text
        withdrawn = shipped_client.delete(
            f"/v1/me/hub/enquiries/{enquiry}", headers=mine
        )
        assert withdrawn.status_code == 204, withdrawn.text

        # A statement bound with every canary fails after the request has
        # passed its checks: the unexpected-failure path logs the
        # exception, whose text would carry bound values if they leaked.
        monkeypatch.setattr(
            sending,
            "_CREATE",
            sa.text(
                sending._CREATE.text.replace(
                    "RETURNING id", "RETURNING id, no_such_column"
                )
            ),
        )
        failed = shipped_client.post(send, json=body, headers=mine)

    assert failed.status_code == 500, failed.text
    # And it saw the 500's traceback, so the failure path was captured.
    tracebacks = [r for r in caplog.records if r.exc_info is not None]
    assert any("no_such_column" in _rendered(r) for r in tracebacks), [
        r.getMessage() for r in caplog.records
    ]
    leaks = [
        (record.name, canary)
        for record in caplog.records
        for canary in CANARIES
        if canary in _rendered(record)
    ]
    assert leaks == []
