"""The platform administration surface over HTTP [TC-14, D-6].

**Written to the authorization predicate first.** Two properties carry
the weight: only an allowlisted number reaches any administration route,
and nothing an administrator reads names a student or a guardian. The
second is asserted against the raw response text, not only the parsed
fields, so a name or number leaking into any field -- a preview, a
label, a nested object added later -- fails here.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.accounts.clients import record_client
from app.authz.admin import PLATFORM_ADMIN_PHONES_ENV, platform_admin_phones
from app.errors import ValidationError
from app.help.identity import requester_ref
from tests.admin.conftest import EDGE, admin_headers
from tests.conftest import bearer
from tests.help.conftest import (
    STUDENT_SEAT_NAME,
    TEACHER_NAME,
    People,
    phone_of,
)

ROUTES = (
    ("GET", "/v1/admin/overview", None),
    ("GET", "/v1/admin/teachers", None),
    ("GET", "/v1/admin/help/requesters", None),
    ("GET", "/v1/admin/help/tickets", None),
    ("GET", "/v1/admin/help/tickets/{t}", None),
    ("POST", "/v1/admin/help/tickets/{t}/messages", {"body": "hi"}),
    ("PUT", "/v1/admin/help/tickets/{t}/status", {"status": "closed"}),
)


def _local(phone: str) -> str:
    """Spell a canonical number the way a person types it.

    :param phone: ``+8801XXXXXXXXX``
    :return: ``01XXXXXXXXX``
    """
    return "0" + phone[4:]


@pytest.fixture
def admin(
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    """Make the stranger an administrator and return their headers.

    The allowlist is written in the local spelling, so the test also
    proves it is canonicalised.

    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param monkeypatch: The patcher
    :return: The administrator's request headers
    """
    monkeypatch.setenv(
        PLATFORM_ADMIN_PHONES_ENV,
        f" {_local(phone_of(owner_session, people.stranger))} , ",
    )
    return admin_headers(owner_session, people.stranger)


def _ask(client: TestClient, session: Session, account: uuid.UUID, subject: str) -> str:
    """Open a ticket as someone and return its id.

    :param client: The HTTP client
    :param session: A session to mint the token through
    :param account: Who asks
    :param subject: Its subject
    :return: The ticket id
    """
    response = client.post(
        "/v1/me/help/tickets",
        json={"subject": subject, "body": f"About {subject}."},
        headers={**bearer(session, account), "X-Client-Platform": "web"},
    )
    assert response.status_code == 201, response.text
    session.commit()
    return str(response.json()["ticket"]["ticket_id"])


def _call(
    client: TestClient,
    method: str,
    path: str,
    body: dict | None,
    headers: dict[str, str],
) -> object:
    """Send one request.

    :param client: The HTTP client
    :param method: The method
    :param path: The path
    :param body: The JSON body, if any
    :param headers: The headers
    :return: The response
    """
    return client.request(method, path, json=body, headers=headers)


def test_an_ordinary_account_reaches_no_admin_route(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teachers included: the lens is the allowlist, not a role.

    Even holding an admin token and a confirmed factor -- the strongest
    thing a non-administrator could have -- every route answers 403.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(
        PLATFORM_ADMIN_PHONES_ENV, phone_of(owner_session, people.stranger)
    )
    ticket = _ask(api_client, owner_session, people.student, "x")
    for account in (people.teacher.account_id, people.member, people.student):
        headers = admin_headers(owner_session, account)
        for method, path, body in ROUTES:
            response = _call(api_client, method, path.format(t=ticket), body, headers)
            assert response.status_code == 403, (method, path)  # type: ignore[attr-defined]
            assert (
                response.json()["error"]["message_key"]  # type: ignore[attr-defined]
                == "authz.lens.not_available"
            )


def test_an_app_token_reaches_no_admin_route_even_for_an_admin(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the admin sign-in's token works; the app's is a 401.

    The administrator's own number, through the admin hostname, with the
    app token they would hold from signing in to the app.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(
        PLATFORM_ADMIN_PHONES_ENV, phone_of(owner_session, people.stranger)
    )
    ticket = _ask(api_client, owner_session, people.student, "x")
    headers = {**EDGE, **bearer(owner_session, people.stranger)}
    owner_session.commit()
    for method, path, body in ROUTES:
        response = _call(api_client, method, path.format(t=ticket), body, headers)
        assert response.status_code == 401, (method, path)  # type: ignore[attr-defined]


def test_an_unset_allowlist_admits_nobody(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deployment that forgets the variable has no admin surface.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.delenv(PLATFORM_ADMIN_PHONES_ENV, raising=False)
    response = api_client.get(
        "/v1/admin/overview", headers=admin_headers(owner_session, people.stranger)
    )
    assert response.status_code == 403


def test_a_malformed_allowlist_admits_nobody_and_says_why(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo locks the surface rather than opening it.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(
        PLATFORM_ADMIN_PHONES_ENV,
        f"{phone_of(owner_session, people.stranger)},not-a-number",
    )
    with pytest.raises(ValidationError):
        platform_admin_phones()
    response = api_client.get(
        "/v1/admin/overview", headers=admin_headers(owner_session, people.stranger)
    )
    assert response.status_code == 403


def test_no_token_is_401(api_client: TestClient) -> None:
    """Authentication comes before the allowlist.

    :param api_client: The HTTP client
    :return: None
    """
    assert api_client.get("/v1/admin/overview", headers=EDGE).status_code == 401


def test_the_overview_counts_everyone_and_names_nobody(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    people: People,
    admin: dict[str, str],
) -> None:
    """Every figure is an aggregate over the arranged people.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param people: The arranged accounts
    :param admin: The administrator's headers
    :return: None
    """
    now = dt.datetime.now(tz=dt.UTC)
    old = now - dt.timedelta(days=20)
    record_client(
        restricted_session, people.teacher.account_id, "android", "1.4.0", now
    )
    record_client(restricted_session, people.teacher.account_id, "web", "0.1.0", now)
    record_client(restricted_session, people.student, "android", "1.4.0", now)
    record_client(restricted_session, people.guardian, "android", "1.3.0", old)
    restricted_session.commit()
    _ask(api_client, owner_session, people.guardian, "Pay")

    response = api_client.get("/v1/admin/overview", headers=admin)

    assert response.status_code == 200
    body = response.json()
    assert body["accounts"] == 5
    assert body["teachers"] == 1
    assert body["centres"] == 1
    assert body["centre_members"] == 1
    assert body["students"] == 1
    assert body["guardians"] == 1
    assert body["batches"] == 1
    assert body["seats"] == 1
    assert body["active_7_days"] == 2
    assert body["active_30_days"] == 3
    platforms = {p["platform"]: p for p in body["platforms"]}
    assert platforms["android"] == {
        "platform": "android",
        "accounts": 3,
        "active_7_days": 2,
        "active_30_days": 3,
    }
    assert platforms["web"]["accounts"] == 1
    assert body["both_platforms"] == 1
    assert body["no_platform"] == 2
    versions = {(v["platform"], v["version"]): v["accounts"] for v in body["versions"]}
    assert versions == {
        ("android", "1.4.0"): 2,
        ("android", "1.3.0"): 1,
        ("web", "0.1.0"): 1,
    }
    assert (body["help_open"], body["help_answered"], body["help_closed"]) == (1, 0, 0)
    _assert_names_no_family(response.text, owner_session, people)


def _assert_names_no_family(text: str, session: Session, people: People) -> None:
    """Assert a response carries no student or guardian identity.

    :param text: The raw response body
    :param session: Any session
    :param people: The arranged accounts
    :return: None
    """
    assert STUDENT_SEAT_NAME not in text
    for account in (people.student, people.guardian, people.member, people.stranger):
        phone = phone_of(session, account)
        assert phone not in text
        assert phone[4:] not in text
        assert str(account) not in text


def test_teachers_and_centres_are_listed_by_name_with_their_apps(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    people: People,
    admin: dict[str, str],
) -> None:
    """A tutor by the name their students see; a centre by its own.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param people: The arranged accounts
    :param admin: The administrator's headers
    :return: None
    """
    now = dt.datetime.now(tz=dt.UTC)
    record_client(restricted_session, people.teacher.account_id, "web", None, now)
    record_client(restricted_session, people.member, "android", None, now)
    record_client(restricted_session, people.student, "android", None, now)
    restricted_session.commit()

    response = api_client.get("/v1/admin/teachers", headers=admin)

    assert response.status_code == 200
    rows = {w["kind"]: w for w in response.json()["workspaces"]}
    assert set(rows) == {"teacher", "centre"}
    assert len(response.json()["workspaces"]) == 2
    assert rows["teacher"]["name"] == TEACHER_NAME
    assert rows["teacher"]["platforms"] == ["web"]
    assert rows["teacher"]["ref"] == requester_ref(people.teacher.account_id)
    assert rows["centre"]["name"] == "Udoy Coaching"
    assert rows["centre"]["platforms"] == ["android"]
    assert rows["centre"]["ref"] is None
    _assert_names_no_family(response.text, owner_session, people)


def test_a_deleted_tutor_is_no_longer_listed(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    admin: dict[str, str],
) -> None:
    """An owner row whose account is gone is history, not a teacher.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param admin: The administrator's headers
    :return: None
    """
    owner_session.execute(
        sa.text("UPDATE owner SET account_id = NULL WHERE id = :o"),
        {"o": people.teacher.owner_id},
    )
    owner_session.commit()

    kinds = [
        w["kind"]
        for w in api_client.get("/v1/admin/teachers", headers=admin).json()[
            "workspaces"
        ]
    ]
    assert kinds == ["centre"]


def test_requesters_are_named_only_when_they_teach(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    admin: dict[str, str],
) -> None:
    """A student and a guardian are a role and a ref; teachers have names.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param admin: The administrator's headers
    :return: None
    """
    _ask(api_client, owner_session, people.student, "Marks")
    _ask(api_client, owner_session, people.guardian, "Fees")
    _ask(api_client, owner_session, people.guardian, "Fees again")
    _ask(api_client, owner_session, people.teacher.account_id, "Batches")
    _ask(api_client, owner_session, people.member, "Payroll")

    response = api_client.get("/v1/admin/help/requesters", headers=admin)

    assert response.status_code == 200
    by_ref = {r["requester"]["ref"]: r for r in response.json()["requesters"]}
    student = by_ref[requester_ref(people.student)]
    assert student["requester"] == {
        "ref": requester_ref(people.student),
        "roles": ["student"],
        "name": None,
        "centre": None,
    }
    guardian = by_ref[requester_ref(people.guardian)]
    assert guardian["requester"]["roles"] == ["guardian"]
    assert guardian["requester"]["name"] is None
    assert (guardian["tickets"], guardian["open"]) == (2, 2)
    teacher = by_ref[requester_ref(people.teacher.account_id)]["requester"]
    assert (teacher["roles"], teacher["name"]) == (["teacher"], TEACHER_NAME)
    member = by_ref[requester_ref(people.member)]["requester"]
    assert member["roles"] == ["centre_member"]
    assert (member["name"], member["centre"]) == ("Nasrin Apa", "Udoy Coaching")
    _assert_names_no_family(response.text, owner_session, people)


def test_tickets_filter_by_person_and_status(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    admin: dict[str, str],
) -> None:
    """``ref`` narrows to one person; ``status`` to one state.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param admin: The administrator's headers
    :return: None
    """
    mine = _ask(api_client, owner_session, people.guardian, "Fees")
    _ask(api_client, owner_session, people.student, "Marks")
    ref = requester_ref(people.guardian)

    one = api_client.get(
        "/v1/admin/help/tickets", params={"ref": ref.lower()}, headers=admin
    ).json()["tickets"]
    assert [t["ticket_id"] for t in one] == [mine]
    assert one[0]["platform"] == "web"
    assert one[0]["message_count"] == 1

    closed = api_client.get(
        "/v1/admin/help/tickets", params={"status": "closed"}, headers=admin
    ).json()["tickets"]
    assert closed == []

    bad = api_client.get(
        "/v1/admin/help/tickets", params={"ref": "not-hex!!!"}, headers=admin
    )
    assert bad.status_code == 422


def test_answering_and_closing_a_ticket(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    admin: dict[str, str],
) -> None:
    """A reply answers it, the requester sees it unsigned, close and reopen.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param admin: The administrator's headers
    :return: None
    """
    ticket = _ask(api_client, owner_session, people.student, "Marks")

    replied = api_client.post(
        f"/v1/admin/help/tickets/{ticket}/messages",
        json={"body": "Marks appear once published."},
        headers=admin,
    )
    assert replied.status_code == 200
    assert replied.json()["ticket"]["status"] == "answered"
    assert [m["author"] for m in replied.json()["messages"]] == ["requester", "support"]
    writer = owner_session.execute(
        sa.text(
            "SELECT author_account_id FROM help_message "
            "WHERE ticket_id = :t AND author = 'support'"
        ),
        {"t": ticket},
    ).scalar_one()
    assert writer == people.stranger

    seen = api_client.get(
        f"/v1/me/help/tickets/{ticket}", headers=bearer(owner_session, people.student)
    ).json()
    assert "author_account_id" not in str(seen)
    assert seen["messages"][1]["author"] == "support"

    closed = api_client.put(
        f"/v1/admin/help/tickets/{ticket}/status",
        json={"status": "closed"},
        headers=admin,
    )
    assert closed.json()["ticket"]["status"] == "closed"
    reopened = api_client.put(
        f"/v1/admin/help/tickets/{ticket}/status",
        json={"status": "open"},
        headers=admin,
    )
    assert reopened.json()["ticket"]["status"] == "open"
    _assert_names_no_family(replied.text, owner_session, people)


def test_an_unknown_ticket_is_404_everywhere(
    api_client: TestClient, admin: dict[str, str]
) -> None:
    """Reading, answering and closing a missing ticket all answer 404.

    :param api_client: The HTTP client
    :param admin: The administrator's headers
    :return: None
    """
    missing = uuid.uuid4()
    for method, path, body in ROUTES[4:]:
        response = api_client.request(
            method, path.format(t=missing), json=body, headers=admin
        )
        assert response.status_code == 404, (method, path)
        assert response.json()["error"]["message_key"] == "help.ticket.not_found"


def test_an_administrator_opening_a_ticket_does_not_mark_it_seen(
    api_client: TestClient,
    owner_session: Session,
    people: People,
    admin: dict[str, str],
) -> None:
    """Only the requester opening the thread clears its new-reply flag.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param people: The arranged accounts
    :param admin: The administrator's headers
    :return: None
    """
    ticket = _ask(api_client, owner_session, people.guardian, "Fees")
    api_client.post(
        f"/v1/admin/help/tickets/{ticket}/messages", json={"body": "Hi"}, headers=admin
    )
    api_client.get(f"/v1/admin/help/tickets/{ticket}", headers=admin)

    listed = api_client.get(
        "/v1/me/help/tickets", headers=bearer(owner_session, people.guardian)
    ).json()
    assert listed["new_replies"] == 1
