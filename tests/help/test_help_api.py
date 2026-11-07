"""The requester's help centre over HTTP.

**Written to the authorization predicate first.** Every route is
lens-exempt and scoped by the caller's account id in SQL, so the
property under test is that another account's ticket is refused in
exactly the shape of a missing one, on every route that takes an id.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.governance.deletion import delete_account
from app.help.tickets import MAX_TICKETS_PER_DAY, support_reply
from tests.conftest import bearer
from tests.help.conftest import People, phone_of

ASK = {"subject": "Cannot add a student", "body": "The Add button does nothing."}


def _ask(
    client: TestClient, session: Session, account: uuid.UUID, **headers: str
) -> dict:
    """Open one ticket and return its detail.

    :param client: The HTTP client
    :param session: A session to mint the token through
    :param account: Who asks
    :param headers: Extra request headers
    :return: The response body
    """
    response = client.post(
        "/v1/me/help/tickets",
        json=ASK,
        headers={**bearer(session, account), **headers},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_asking_opens_a_ticket_with_the_first_message(
    api_client: TestClient, owner_session: Session, people: People
) -> None:
    """The ticket starts open, with the question as its first message.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    body = _ask(
        api_client, owner_session, people.student, **{"X-Client-Platform": "android"}
    )

    assert body["ticket"]["status"] == "open"
    assert body["ticket"]["subject"] == ASK["subject"]
    assert body["ticket"]["has_new_reply"] is False
    assert [(m["author"], m["body"]) for m in body["messages"]] == [
        ("requester", ASK["body"])
    ]
    platform = owner_session.execute(
        sa.text("SELECT platform FROM help_ticket WHERE id = :t"),
        {"t": body["ticket"]["ticket_id"]},
    ).scalar_one()
    assert platform == "android"


def test_a_person_with_no_lens_can_still_ask(
    api_client: TestClient, owner_session: Session, people: People
) -> None:
    """Signed up, never enrolled, owns nothing -- and still gets help.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    body = _ask(api_client, owner_session, people.stranger)

    assert body["ticket"]["status"] == "open"


def test_blank_and_oversized_text_is_refused(
    api_client: TestClient, owner_session: Session, people: People
) -> None:
    """Whitespace is trimmed before the length check.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    headers = bearer(owner_session, people.teacher.account_id)
    for payload in (
        {"subject": "   ", "body": "x"},
        {"subject": "x", "body": "\n\t "},
        {"subject": "x" * 121, "body": "x"},
        {"subject": "x", "body": "x" * 4001},
    ):
        response = api_client.post("/v1/me/help/tickets", json=payload, headers=headers)
        assert response.status_code == 422, payload


def test_text_is_stored_trimmed(
    api_client: TestClient, owner_session: Session, people: People
) -> None:
    """Leading and trailing whitespace does not reach the database.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    response = api_client.post(
        "/v1/me/help/tickets",
        json={"subject": "  Fees  ", "body": "  How do I waive a fee?  "},
        headers=bearer(owner_session, people.teacher.account_id),
    )

    assert response.json()["ticket"]["subject"] == "Fees"
    assert response.json()["messages"][0]["body"] == "How do I waive a fee?"


def test_the_list_holds_only_the_callers_own_tickets(
    api_client: TestClient, owner_session: Session, people: People
) -> None:
    """Two people's tickets never mix.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    mine = _ask(api_client, owner_session, people.guardian)
    _ask(api_client, owner_session, people.student)

    listed = api_client.get(
        "/v1/me/help/tickets", headers=bearer(owner_session, people.guardian)
    ).json()

    assert [t["ticket_id"] for t in listed["tickets"]] == [mine["ticket"]["ticket_id"]]
    assert listed["new_replies"] == 0


def test_another_persons_ticket_is_indistinguishable_from_a_missing_one(
    api_client: TestClient, owner_session: Session, people: People
) -> None:
    """Same status, same body, on both routes that take an id.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    theirs = _ask(api_client, owner_session, people.student)["ticket"]["ticket_id"]
    missing = str(uuid.uuid4())
    headers = bearer(owner_session, people.guardian)

    for path in ("/v1/me/help/tickets/{}",):
        a = api_client.get(path.format(theirs), headers=headers)
        b = api_client.get(path.format(missing), headers=headers)
        assert a.status_code == b.status_code == 404
        assert a.json() == b.json()
        assert a.json()["error"]["message_key"] == "help.ticket.not_found"

    reply = {"body": "hello"}
    a = api_client.post(
        f"/v1/me/help/tickets/{theirs}/messages", json=reply, headers=headers
    )
    b = api_client.post(
        f"/v1/me/help/tickets/{missing}/messages", json=reply, headers=headers
    )
    assert a.status_code == b.status_code == 404
    assert a.json() == b.json()

    count = owner_session.execute(
        sa.text("SELECT count(*) FROM help_message WHERE ticket_id = :t"),
        {"t": theirs},
    ).scalar_one()
    assert count == 1


def test_a_support_reply_shows_as_new_until_opened(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    people: People,
) -> None:
    """``has_new_reply`` and ``new_replies`` clear when the thread is read.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param people: The arranged accounts
    :return: None
    """
    ticket = _ask(api_client, owner_session, people.student)["ticket"]["ticket_id"]
    support_reply(
        restricted_session, people.member, uuid.UUID(ticket), "Tap the + button."
    )
    restricted_session.commit()
    headers = bearer(owner_session, people.student)

    listed = api_client.get("/v1/me/help/tickets", headers=headers).json()
    assert listed["new_replies"] == 1
    assert listed["tickets"][0]["status"] == "answered"
    assert listed["tickets"][0]["has_new_reply"] is True
    assert listed["tickets"][0]["preview"] == "Tap the + button."

    opened = api_client.get(f"/v1/me/help/tickets/{ticket}", headers=headers).json()
    assert [m["author"] for m in opened["messages"]] == ["requester", "support"]
    assert opened["ticket"]["has_new_reply"] is False

    again = api_client.get("/v1/me/help/tickets", headers=headers).json()
    assert again["new_replies"] == 0


def test_replying_to_a_closed_ticket_reopens_it(
    api_client: TestClient, owner_session: Session, people: People
) -> None:
    """A person is never told they cannot ask about something any more.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    ticket = _ask(api_client, owner_session, people.teacher.account_id)["ticket"]
    owner_session.execute(
        sa.text(
            "UPDATE help_ticket SET status = 'closed', closed_at = now() WHERE id = :t"
        ),
        {"t": ticket["ticket_id"]},
    )
    owner_session.commit()

    response = api_client.post(
        f"/v1/me/help/tickets/{ticket['ticket_id']}/messages",
        json={"body": "It happened again."},
        headers=bearer(owner_session, people.teacher.account_id),
    )

    assert response.status_code == 200
    assert response.json()["ticket"]["status"] == "open"
    assert len(response.json()["messages"]) == 2
    closed_at = owner_session.execute(
        sa.text("SELECT closed_at FROM help_ticket WHERE id = :t"),
        {"t": ticket["ticket_id"]},
    ).scalar_one()
    assert closed_at is None


def test_new_tickets_are_bounded_per_day(
    api_client: TestClient, owner_session: Session, people: People
) -> None:
    """The sixth ticket in a day is refused; replies are not.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :return: None
    """
    for _ in range(MAX_TICKETS_PER_DAY):
        first = _ask(api_client, owner_session, people.guardian)

    refused = api_client.post(
        "/v1/me/help/tickets",
        json=ASK,
        headers=bearer(owner_session, people.guardian),
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["message_key"] == "help.ticket.too_many"
    assert refused.json()["error"]["retryable"] is False

    reply = api_client.post(
        f"/v1/me/help/tickets/{first['ticket']['ticket_id']}/messages",
        json={"body": "One more thing."},
        headers=bearer(owner_session, people.guardian),
    )
    assert reply.status_code == 200


def test_unauthenticated_requests_are_refused(api_client: TestClient) -> None:
    """Every route needs a token.

    :param api_client: The HTTP client
    :return: None
    """
    ticket = uuid.uuid4()
    assert api_client.get("/v1/me/help/tickets").status_code == 401
    assert api_client.post("/v1/me/help/tickets", json=ASK).status_code == 401
    assert api_client.get(f"/v1/me/help/tickets/{ticket}").status_code == 401
    assert (
        api_client.post(
            f"/v1/me/help/tickets/{ticket}/messages", json={"body": "x"}
        ).status_code
        == 401
    )


def test_deleting_the_account_deletes_its_tickets(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    people: People,
) -> None:
    """The help centre goes with the account, support's replies included.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param people: The arranged accounts
    :return: None
    """
    ticket = _ask(api_client, owner_session, people.stranger)["ticket"]["ticket_id"]
    support_reply(restricted_session, people.member, uuid.UUID(ticket), "Hello.")
    restricted_session.commit()

    phone = phone_of(owner_session, people.stranger)
    # ``bearer`` wrote a refresh token through the arranging session; its
    # open transaction holds a key lock on the account row, so release it
    # before the deletion takes that row.
    owner_session.commit()
    result = delete_account(restricted_session, phone)
    restricted_session.commit()

    assert result.rows_deleted.get("help_ticket") == 1
    left = owner_session.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM help_ticket), "
            "(SELECT count(*) FROM help_message)"
        )
    ).one()
    assert tuple(left) == (0, 0)
