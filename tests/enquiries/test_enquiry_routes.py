"""The join-request routes, end to end through the real application [H5 Task 5].

Each route runs against the restricted database role, with the lens
resolved by the real dependency and the switch read from the environment
per request. The world is arranged through the table-owner session.

Written before the routes existed: the off table (Review Focus 4), the
dependency order that makes an off switch answer ``HUB_ENQUIRIES_OFF`` and
never a target, ownership or lens refusal, the identical bad-target bytes
over HTTP (Review Focus 2), strict consent fields [F9] and the teacher-lens
refusal are authorization predicates [team: Testing Posture].
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Final

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.ceilings import HUB_ENQUIRY_ACCOUNT_DAILY, CeilingChecker
from app.hub.enquiries import forget, owner
from app.hub.public.settings import HUB_ENQUIRIES_ENV
from tests.batches.conftest import enroll
from tests.conftest import bearer
from tests.enquiries.support import (
    CASES,
    NEVER,
    EnquirableWorld,
    enquirable_owner,
    guardian,
)
from tests.hub.support import add_member, assign_slot
from tests.reviews.support import account, guardian_seat

#: The guardian's target and send paths for one owner.
TARGET: Final = "/v1/hub/owners/{slug}/enquiry-target"
SEND: Final = "/v1/hub/owners/{slug}/enquiries"

#: The guardian's own requests.
MINE: Final = "/v1/me/hub/enquiries"

#: The owner's list.
OWNER_LIST: Final = "/v1/hub/enquiries"

#: What the request form is told before sending, and nothing else.
TARGET_FIELDS: Final = {
    "owner_public_name",
    "batch_title",
    "contact_kind",
    "already_open",
}

#: A guardian's own request on the wire: no account id, no own contact.
MY_FIELDS: Final = {
    "id",
    "owner_public_name",
    "batch_title",
    "student_name",
    "class_level",
    "message",
    "share_contact",
    "status",
    "outcome",
    "sent_on",
    "owner_contact_phone",
}

#: A request as the people who run the listing read it.
OWNER_FIELDS: Final = {
    "id",
    "batch_id",
    "batch_title",
    "student_name",
    "class_level",
    "message",
    "status",
    "outcome",
    "received_at",
    "guardian_phone",
    "guardian_email",
    "outcomes_allowed",
}

#: The owner's published number, in canonical form.
PUBLIC_PHONE: Final = "+8801811111111"


def _body(**changes: object) -> dict[str, object]:
    """Build a valid send body, with changes.

    :param changes: Fields to replace; a value of ``...`` removes the field
    :return: The body
    """
    body: dict[str, object] = {
        "student_name": "Nadia Rahman",
        "class_level": "class_8",
        "message": "Wants Physics and Maths",
        "share_contact": True,
        "declares_adult_guardian": True,
    }
    for name, value in changes.items():
        if value is ...:
            body.pop(name, None)
        else:
            body[name] = value
    return body


def _error(response: httpx.Response) -> dict[str, object]:
    """Read an error envelope's body.

    :param response: The response
    :return: The ``error`` object
    """
    body = response.json()
    assert set(body) == {"error"}, body
    error = body["error"]
    assert isinstance(error, dict)
    return error


def _refused(
    response: httpx.Response, status: int, code: str, message_key: str
) -> dict[str, object]:
    """Assert a refusal's status, code and message key.

    :param response: The response
    :param status: The expected status
    :param code: The expected code
    :param message_key: The expected message key
    :return: The error object, for further checks
    """
    assert response.status_code == status, response.text
    error = _error(response)
    assert error["code"] == code
    assert error["message_key"] == message_key
    return error


def _count(session: Session, sql: str, **values: object) -> int:
    """Count rows, outside any arranging transaction.

    :param session: An arranging session
    :param sql: A ``SELECT count(*)`` statement
    :param values: Its parameters
    :return: The count
    """
    session.rollback()
    return int(session.execute(sa.text(sql), values).scalar_one())


def _send(
    client: TestClient,
    session: Session,
    world: EnquirableWorld,
    caller: uuid.UUID,
    **changes: object,
) -> httpx.Response:
    """Send a join request to the world's owner about its batch.

    :param client: The test client
    :param session: An arranging session
    :param world: The owner
    :param caller: The sending account
    :param changes: Body changes, as :func:`_body` takes them
    :return: The response
    """
    return client.post(
        SEND.format(slug=world.owner_slug),
        json=_body(batch_id=str(world.batch_id), **changes),
        headers=bearer(session, caller),
    )


def _sent(
    client: TestClient,
    session: Session,
    world: EnquirableWorld,
    caller: uuid.UUID,
    **changes: object,
) -> str:
    """Send a join request that must be stored.

    :param client: The test client
    :param session: An arranging session
    :param world: The owner
    :param caller: The sending account
    :param changes: Body changes
    :return: The new request's id
    """
    response = _send(client, session, world, caller, **changes)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _inbox(
    client: TestClient, session: Session, caller: uuid.UUID, kinds: list[str] | None
) -> dict[str, object]:
    """Read a caller's inbox, announcing kinds or none.

    :param client: The test client
    :param session: An arranging session
    :param caller: The reader
    :param kinds: The kinds announced, or None for an old client
    :return: The inbox body
    """
    params = None if kinds is None else [("kind", kind) for kind in kinds]
    response = client.get(
        "/v1/me/notifications", params=params, headers=bearer(session, caller)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


@pytest.mark.usefixtures("enquiries_off")
def test_gated_routes_answer_enquiries_off_and_withdraw_still_works(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 4: off refuses every gated route first, and only those.

    Every gated route answers the same bytes to a guardian, an owner and a
    stranger, about a real target or a missing one, and about an owned
    request or a random id: the switch runs before any target, lens or
    ownership check. The guardian still lists and withdraws, totally.
    """
    world = enquirable_owner(owner_session)
    sender = guardian(owner_session)
    stranger = account(owner_session)
    monkeypatch.setenv(HUB_ENQUIRIES_ENV, "on")
    enquiry_id = _sent(api_client, owner_session, world, sender)
    answered = api_client.post(
        f"{OWNER_LIST}/{enquiry_id}/close",
        json={"outcome": "not_now"},
        headers=bearer(owner_session, world.lens.account_id),
    )
    assert answered.status_code == 200, answered.text
    monkeypatch.delenv(HUB_ENQUIRIES_ENV)

    owned = f"{OWNER_LIST}/{enquiry_id}"
    foreign = f"{OWNER_LIST}/{uuid.uuid4()}"
    bodies: set[bytes] = set()
    for caller in (sender, world.lens.account_id, stranger):
        headers = bearer(owner_session, caller)
        calls = [
            api_client.get(TARGET.format(slug=world.owner_slug), headers=headers),
            api_client.get(TARGET.format(slug=NEVER), headers=headers),
            api_client.post(
                SEND.format(slug=world.owner_slug), json=_body(), headers=headers
            ),
            api_client.post(SEND.format(slug=NEVER), json=_body(), headers=headers),
            api_client.get(OWNER_LIST, headers=headers),
            api_client.get(owned, headers=headers),
            api_client.get(foreign, headers=headers),
            api_client.post(
                f"{owned}/close", json={"outcome": "not_now"}, headers=headers
            ),
            api_client.post(
                f"{foreign}/close", json={"outcome": "not_now"}, headers=headers
            ),
        ]
        for response in calls:
            _refused(response, 404, "HUB_ENQUIRIES_OFF", "hub.enquiry.off")
            bodies.add(response.content)
    assert len(bodies) == 1

    # The guardian's own list is not gated, so they can find it to withdraw.
    listed = api_client.get(MINE, headers=bearer(owner_session, sender))
    assert listed.status_code == 200, listed.text
    assert [(row["id"], row["outcome"]) for row in listed.json()] == [
        (enquiry_id, "not_now")
    ]

    # The switch never gates a deletion.
    withdrawn = api_client.delete(
        f"{MINE}/{enquiry_id}", headers=bearer(owner_session, sender)
    )
    assert withdrawn.status_code == 204, withdrawn.text
    assert withdrawn.content == b""
    assert _count(owner_session, "SELECT count(*) FROM listing_enquiry") == 0
    assert (
        _count(
            owner_session,
            "SELECT count(*) FROM notification WHERE source_id = :e",
            e=uuid.UUID(enquiry_id),
        )
        == 0
    )
    empty = api_client.get(MINE, headers=bearer(owner_session, sender))
    assert empty.json() == []

    # Switched back on, the owner's read of it is a plain not-found.
    monkeypatch.setenv(HUB_ENQUIRIES_ENV, "on")
    _refused(
        api_client.get(owned, headers=bearer(owner_session, world.lens.account_id)),
        404,
        "ENQUIRY_NOT_FOUND",
        "hub.enquiry.not_found",
    )


@pytest.mark.usefixtures("enquiries_on")
def test_end_to_end_send_answer_withdraw(
    api_client: TestClient, owner_session: Session
) -> None:
    """A guardian asks, the owner reads and answers, the guardian withdraws."""
    world = enquirable_owner(owner_session)
    owner_session.execute(
        sa.text(
            "UPDATE owner_listing SET public_contact_phone = :p WHERE owner_id = :o"
        ),
        {"p": PUBLIC_PHONE, "o": world.lens.owner_id},
    )
    owner_session.commit()
    sender = guardian(owner_session)
    mine = bearer(owner_session, sender)
    teacher = bearer(owner_session, world.lens.account_id)
    target = TARGET.format(slug=world.owner_slug)

    before = api_client.get(
        target, params={"batch_id": str(world.batch_id)}, headers=mine
    )
    assert before.status_code == 200, before.text
    assert before.json() == {
        "owner_public_name": "Rahim Sir",
        "batch_title": world.batch_title,
        "contact_kind": "phone",
        "already_open": False,
    }
    assert set(before.json()) == TARGET_FIELDS

    sent = _send(api_client, owner_session, world, sender, message="  After 4 pm  ")
    assert sent.status_code == 201, sent.text
    assert set(sent.json()) == MY_FIELDS
    enquiry_id = sent.json()["id"]
    assert sent.json() | {"id": None, "sent_on": None} == {
        "id": None,
        "owner_public_name": "Rahim Sir",
        "batch_title": world.batch_title,
        "student_name": "Nadia Rahman",
        "class_level": "class_8",
        "message": "After 4 pm",
        "share_contact": True,
        "status": "open",
        "outcome": None,
        "sent_on": None,
        "owner_contact_phone": None,
    }

    assert api_client.get(target, headers=mine).json()["already_open"] is True
    _refused(
        _send(api_client, owner_session, world, sender),
        409,
        "ENQUIRY_ALREADY_OPEN",
        "hub.enquiry.already_open",
    )

    listed = api_client.get(OWNER_LIST, headers=teacher)
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [enquiry_id]
    row = listed.json()[0]
    assert set(row) == OWNER_FIELDS
    assert row["guardian_phone"] == "+8801712345678"
    assert row["guardian_email"] is None
    assert row["outcomes_allowed"] == ["added", "not_now", "call_us"]
    assert row["batch_id"] == str(world.batch_id)

    one = api_client.get(f"{OWNER_LIST}/{enquiry_id}", headers=teacher)
    assert one.status_code == 200, one.text
    assert one.json() == row

    closed = api_client.post(
        f"{OWNER_LIST}/{enquiry_id}/close", json={"outcome": "call_us"}, headers=teacher
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert closed.json()["outcome"] == "call_us"
    assert closed.json()["outcomes_allowed"] == []
    _refused(
        api_client.post(
            f"{OWNER_LIST}/{enquiry_id}/close",
            json={"outcome": "not_now"},
            headers=teacher,
        ),
        409,
        "ENQUIRY_ALREADY_CLOSED",
        "hub.enquiry.already_closed",
    )

    answered = api_client.get(MINE, headers=mine)
    assert answered.status_code == 200, answered.text
    assert [
        (r["id"], r["outcome"], r["owner_contact_phone"]) for r in answered.json()
    ] == [(enquiry_id, "call_us", PUBLIC_PHONE)]

    withdrawn = api_client.delete(f"{MINE}/{enquiry_id}", headers=mine)
    assert withdrawn.status_code == 204, withdrawn.text
    assert api_client.get(MINE, headers=mine).json() == []
    _refused(
        api_client.get(f"{OWNER_LIST}/{enquiry_id}", headers=teacher),
        404,
        "ENQUIRY_NOT_FOUND",
        "hub.enquiry.not_found",
    )
    # Withdrawing again, or someone else's id, is a quiet no-op.
    again = api_client.delete(f"{MINE}/{enquiry_id}", headers=mine)
    assert again.status_code == 204, again.text


@pytest.mark.usefixtures("enquiries_on")
def test_a_guardian_without_a_phone_shares_their_email(
    api_client: TestClient, owner_session: Session
) -> None:
    """The form names email, and the owner sees it only while shared."""
    world = enquirable_owner(owner_session)
    sender = guardian(owner_session, phone=None, email="nadia@example.com")
    target = api_client.get(
        TARGET.format(slug=world.owner_slug), headers=bearer(owner_session, sender)
    )
    assert target.json()["contact_kind"] == "email"

    _sent(api_client, owner_session, world, sender)
    row = api_client.get(
        OWNER_LIST, headers=bearer(owner_session, world.lens.account_id)
    ).json()[0]
    assert (row["guardian_phone"], row["guardian_email"]) == (
        None,
        "nadia@example.com",
    )

    other = enquirable_owner(owner_session)
    _sent(api_client, owner_session, other, sender, share_contact=False)
    unshared = api_client.get(
        OWNER_LIST, headers=bearer(owner_session, other.lens.account_id)
    ).json()[0]
    assert (unshared["guardian_phone"], unshared["guardian_email"]) == (None, None)
    assert unshared["outcomes_allowed"] == ["not_now"]


@pytest.mark.usefixtures("enquiries_on")
@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"share_contact": ...}, id="share-missing"),
        pytest.param({"share_contact": 1}, id="share-1"),
        pytest.param({"share_contact": "true"}, id="share-true-string"),
        pytest.param({"share_contact": "on"}, id="share-on"),
        pytest.param({"share_contact": 1.0}, id="share-1.0"),
        pytest.param({"share_contact": None}, id="share-null"),
        pytest.param({"declares_adult_guardian": ...}, id="declare-missing"),
        pytest.param({"declares_adult_guardian": False}, id="declare-false"),
        pytest.param({"declares_adult_guardian": 1}, id="declare-1"),
        pytest.param({"declares_adult_guardian": "true"}, id="declare-true-string"),
        pytest.param({"declares_adult_guardian": "on"}, id="declare-on"),
        pytest.param({"declares_adult_guardian": 1.0}, id="declare-1.0"),
        pytest.param({"student_name": "   "}, id="name-blank"),
        pytest.param({"student_name": "x" * 81}, id="name-81"),
        pytest.param({"message": "x" * 301}, id="message-301"),
        pytest.param({"class_level": "class_99"}, id="class-unknown"),
        pytest.param({"stranger": "field"}, id="extra-field"),
    ],
)
def test_missing_share_contact_or_false_declaration_is_422(
    api_client: TestClient, owner_session: Session, changes: dict[str, object]
) -> None:
    """Consent is a real JSON boolean the client sent, never a coercion [F9]."""
    world = enquirable_owner(owner_session)
    sender = guardian(owner_session)

    _refused(
        _send(api_client, owner_session, world, sender, **changes),
        422,
        "REQUEST_INVALID",
        "error.unexpected",
    )
    assert _count(owner_session, "SELECT count(*) FROM listing_enquiry") == 0


@pytest.mark.usefixtures("enquiries_on")
def test_text_is_bounded_after_stripping(
    api_client: TestClient, owner_session: Session
) -> None:
    """A padded 80-character name and a blank message are accepted [H4 F14]."""
    world = enquirable_owner(owner_session)
    sender = guardian(owner_session)
    sent = _send(
        api_client,
        owner_session,
        world,
        sender,
        student_name=f"  {'n' * 80}  ",
        message="   ",
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["student_name"] == "n" * 80
    assert sent.json()["message"] is None


@pytest.mark.usefixtures("enquiries_on")
@pytest.mark.parametrize("name", sorted(CASES))
def test_unenquirable_targets_answer_identical_bytes_over_http(
    api_client: TestClient, owner_session: Session, name: str
) -> None:
    """Review Focus 2 on the wire: every bad target is a never-existing slug.

    Nothing runs before ``resolve`` on either route, so the target and the
    send answer each case with the status and body bytes a slug that never
    existed gets, and nothing is written.
    """
    world = enquirable_owner(owner_session)
    slug, batch_id, caller = CASES[name](owner_session, world)
    headers = bearer(owner_session, caller)
    query = {} if batch_id is None else {"batch_id": str(batch_id)}
    body = _body() if batch_id is None else _body(batch_id=str(batch_id))

    never_target = api_client.get(
        TARGET.format(slug=NEVER), params=query, headers=headers
    )
    never_send = api_client.post(SEND.format(slug=NEVER), json=body, headers=headers)
    bad_target = api_client.get(TARGET.format(slug=slug), params=query, headers=headers)
    bad_send = api_client.post(SEND.format(slug=slug), json=body, headers=headers)

    _refused(
        never_target, 404, "ENQUIRY_TARGET_NOT_FOUND", "hub.enquiry.target_not_found"
    )
    for response in (never_send, bad_target, bad_send):
        assert (response.status_code, response.content) == (
            never_target.status_code,
            never_target.content,
        )
    assert _count(owner_session, "SELECT count(*) FROM listing_enquiry") == 0
    assert (
        _count(
            owner_session,
            "SELECT count(*) FROM notification WHERE kind = 'hub_enquiry_received'",
        )
        == 0
    )


def _call_off(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Send while join requests are off.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Switches join requests off
    :return: The response
    """
    world = enquirable_owner(session)
    monkeypatch.delenv(HUB_ENQUIRIES_ENV)
    return _send(client, session, world, guardian(session))


def _call_target_not_found(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Ask for a target that never existed.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    return client.get(
        TARGET.format(slug=NEVER), headers=bearer(session, guardian(session))
    )


def _call_already_open(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Send a second request while the first is open.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    world = enquirable_owner(session)
    sender = guardian(session)
    _sent(client, session, world, sender)
    return _send(client, session, world, sender)


def _call_ceiling(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Send one request more than a day allows, each to a different owner.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    sender = guardian(session)
    for _ in range(HUB_ENQUIRY_ACCOUNT_DAILY):
        _sent(client, session, enquirable_owner(session), sender)
    return _send(client, session, enquirable_owner(session), sender)


def _call_contact(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Send a message carrying a phone number.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    world = enquirable_owner(session)
    return _send(client, session, world, guardian(session), message="Call 01712345678")


def _call_not_found(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Read a request id that was never minted.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    world = enquirable_owner(session)
    return client.get(
        f"{OWNER_LIST}/{uuid.uuid4()}", headers=bearer(session, world.lens.account_id)
    )


def _closing(
    client: TestClient, session: Session, outcome: str, *, share: bool, twice: bool
) -> httpx.Response:
    """Close a fresh request, once or twice.

    :param client: The test client
    :param session: An arranging session
    :param outcome: The outcome sent
    :param share: Whether the guardian shared their contact
    :param twice: Close it with ``not_now`` first
    :return: The last response
    """
    world = enquirable_owner(session)
    enquiry_id = _sent(client, session, world, guardian(session), share_contact=share)
    path = f"{OWNER_LIST}/{enquiry_id}/close"
    headers = bearer(session, world.lens.account_id)
    if twice:
        first = client.post(path, json={"outcome": "not_now"}, headers=headers)
        assert first.status_code == 200, first.text
    return client.post(path, json={"outcome": outcome}, headers=headers)


def _call_already_closed(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Close a request already closed.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    return _closing(client, session, "not_now", share=True, twice=True)


def _call_outcome_invalid(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Answer "added" a request whose guardian shared no contact.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    return _closing(client, session, "added", share=False, twice=False)


#: One case per row of the global constraints' error table, plus the
#: contact refusal [F10].
ERROR_CASES: Final = [
    pytest.param(_call_off, 404, "HUB_ENQUIRIES_OFF", "hub.enquiry.off", id="off"),
    pytest.param(
        _call_target_not_found,
        404,
        "ENQUIRY_TARGET_NOT_FOUND",
        "hub.enquiry.target_not_found",
        id="target-not-found",
    ),
    pytest.param(
        _call_already_open,
        409,
        "ENQUIRY_ALREADY_OPEN",
        "hub.enquiry.already_open",
        id="already-open",
    ),
    pytest.param(
        _call_ceiling, 409, "HUB_ENQUIRY_CEILING", "hub.enquiry.ceiling", id="ceiling"
    ),
    pytest.param(
        _call_not_found,
        404,
        "ENQUIRY_NOT_FOUND",
        "hub.enquiry.not_found",
        id="not-found",
    ),
    pytest.param(
        _call_already_closed,
        409,
        "ENQUIRY_ALREADY_CLOSED",
        "hub.enquiry.already_closed",
        id="already-closed",
    ),
    pytest.param(
        _call_outcome_invalid,
        400,
        "ENQUIRY_OUTCOME_INVALID",
        "hub.enquiry.outcome_invalid",
        id="outcome-invalid",
    ),
    pytest.param(
        _call_contact,
        400,
        "ENQUIRY_CONTAINS_CONTACT",
        "hub.enquiry.contains_contact",
        id="contains-contact",
    ),
]

#: The details each case carries; None where the envelope carries none.
ERROR_DETAILS: Final[dict[str, dict[str, str]]] = {
    "hub.enquiry.contains_contact": {"field": "message"},
}


@pytest.mark.usefixtures("enquiries_on")
@pytest.mark.parametrize(("call", "status", "code", "message_key"), ERROR_CASES)
def test_error_envelopes_for_new_codes(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    call: Callable[..., httpx.Response],
    status: int,
    code: str,
    message_key: str,
) -> None:
    """Each code arrives with its status, its key and its details."""
    response = call(api_client, owner_session, monkeypatch)

    error = _refused(response, status, code, message_key)
    assert error["retryable"] is False
    assert error.get("details") == ERROR_DETAILS.get(message_key)


@pytest.mark.usefixtures("enquiries_on")
def test_teacher_routes_refuse_centre_teacher_student_and_guardian_lenses(
    api_client: TestClient, owner_session: Session
) -> None:
    """Only the people who run the listing reach the owner's three routes.

    A centre's class teacher teaches the batch but never reads the inbox;
    a student and a guardian of the same batch hold their own lenses. Each
    gets the teacher lens's refusal, never a request.
    """
    world = enquirable_owner(owner_session, centre=True)
    enquiry_id = _sent(api_client, owner_session, world, guardian(owner_session))
    member_id, class_teacher = add_member(owner_session, world.lens.owner_id)
    assign_slot(owner_session, world.batch_id, member_id)
    student = account(owner_session)
    enroll(
        owner_session,
        batch_id=world.batch_id,
        display_name="Rafi",
        student_account_id=student,
        student_decision="accepted",
    )
    parent = account(owner_session)
    guardian_seat(owner_session, world.batch_id, parent, joined_on=None)
    one = f"{OWNER_LIST}/{enquiry_id}"
    no_lens = (403, "NO_TEACHER_LENS", "authz.lens.not_available")

    for caller in (class_teacher, student, parent):
        headers = bearer(owner_session, caller)
        _refused(api_client.get(OWNER_LIST, headers=headers), *no_lens)
        _refused(api_client.get(one, headers=headers), *no_lens)
        _refused(
            api_client.post(
                f"{one}/close", json={"outcome": "not_now"}, headers=headers
            ),
            *no_lens,
        )
    assert (
        _count(
            owner_session,
            "SELECT count(*) FROM listing_enquiry WHERE status = 'open'",
        )
        == 1
    )

    # Both managers share the one inbox.
    for manager in world.manager_ids:
        listed = api_client.get(OWNER_LIST, headers=bearer(owner_session, manager))
        assert listed.status_code == 200, listed.text
        assert [row["id"] for row in listed.json()] == [enquiry_id]


@pytest.mark.usefixtures("enquiries_on")
def test_inbox_renders_both_kinds_for_announcing_clients_only(
    api_client: TestClient, owner_session: Session
) -> None:
    """Both kinds reach a client that names them, and no older client.

    Neither carries anything the guardian typed: the owner's copy has no
    preview, and the guardian's answer carries only the outcome code.
    """
    world = enquirable_owner(owner_session, centre=True)
    sender = guardian(owner_session)
    enquiry_id = _sent(api_client, owner_session, world, sender)
    kinds = ["hub_enquiry_received", "hub_enquiry_answered"]

    for manager in world.manager_ids:
        assert _inbox(api_client, owner_session, manager, None) == {
            "items": [],
            "unread": 0,
        }
        announced = _inbox(api_client, owner_session, manager, kinds)
        assert announced["unread"] == 1
        items = announced["items"]
        assert isinstance(items, list)
        assert [
            (i["kind"], i["source_id"], i["batch_name"], i["preview"], i["read"])
            for i in items
        ] == [("hub_enquiry_received", enquiry_id, world.batch_title, None, False)]

    closed = api_client.post(
        f"{OWNER_LIST}/{enquiry_id}/close",
        json={"outcome": "not_now"},
        headers=bearer(owner_session, world.manager_ids[0]),
    )
    assert closed.status_code == 200, closed.text

    assert _inbox(api_client, owner_session, sender, None)["items"] == []
    answered = _inbox(api_client, owner_session, sender, kinds)
    assert answered["unread"] == 1
    items = answered["items"]
    assert isinstance(items, list)
    assert [(i["kind"], i["source_id"], i["preview"]) for i in items] == [
        ("hub_enquiry_answered", enquiry_id, "not_now")
    ]
    # Closing marked every manager's copy read.
    for manager in world.manager_ids:
        assert _inbox(api_client, owner_session, manager, kinds)["unread"] == 0


@pytest.mark.usefixtures("enquiries_on")
def test_write_routes_roll_back_on_an_unexpected_error(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-taxonomy failure mid-write leaves every row as it was."""
    world = enquirable_owner(owner_session)
    sender = guardian(owner_session)
    kept = _sent(api_client, owner_session, world, sender)
    client = TestClient(api_client.app, raise_server_exceptions=False)
    real_forget = forget.forget

    def boom(*args: object, **kwargs: object) -> None:
        msg = "after the write"
        raise RuntimeError(msg)

    def forget_then_boom(session: Session, ids: list[uuid.UUID]) -> None:
        real_forget(session, ids)
        boom()

    monkeypatch.setattr(CeilingChecker, "consume_hub_enquiry_in_transaction", boom)
    monkeypatch.setattr(owner, "mark_read_for_source", boom)
    monkeypatch.setattr(forget, "forget", forget_then_boom)

    other = enquirable_owner(owner_session)
    sent = _send(client, owner_session, other, sender)
    closed = client.post(
        f"{OWNER_LIST}/{kept}/close",
        json={"outcome": "not_now"},
        headers=bearer(owner_session, world.lens.account_id),
    )
    withdrawn = client.delete(f"{MINE}/{kept}", headers=bearer(owner_session, sender))

    assert (sent.status_code, closed.status_code, withdrawn.status_code) == (
        500,
        500,
        500,
    )
    assert (
        _count(
            owner_session,
            "SELECT count(*) FROM listing_enquiry WHERE id = :e AND status = 'open'",
            e=uuid.UUID(kept),
        )
        == 1
    )
    assert _count(owner_session, "SELECT count(*) FROM listing_enquiry") == 1
    assert (
        _count(
            owner_session,
            "SELECT count(*) FROM notification WHERE source_id = :e",
            e=uuid.UUID(kept),
        )
        == 1
    )
