"""Coaching centres: workspaces, membership offers and their grant [0022].

Written from the decisions, not from the code. Each of these is an
authorization outcome -- who reaches a centre's records and when they stop
-- so they meet the team's test-first predicate: a wrong answer here hands
a stranger a centre's families or keeps a removed manager in.

* A manager acts on the centre through the same teacher routes a solo
  tutor uses, choosing it with ``X-Workspace-Id``.
* Naming a number grants nothing: pending, declined, revoked and
  teacher-role memberships give no teacher lens.
* The header is a choice among the caller's own workspaces, never a grant.
* A centre always keeps a manager.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Account, Owner, OwnerMember
from app.governance.deletion import delete_account
from app.notifications.recipients import teacher_recipients
from tests.batches.conftest import make_teacher
from tests.conftest import bearer

ADDRESS = {
    "address_house": "House 12",
    "address_road": "Road 5",
    "address_city": "Dhaka",
    "address_postcode": "1205",
}


def _phone() -> str:
    """Generate a unique number.

    :return: A number in international form
    """
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


def _account(session: Session, phone: str | None = None) -> uuid.UUID:
    """Create an account directly.

    :param session: An arranging session
    :param phone: Its number, or None for a fresh one
    :return: The account id
    """
    account = Account(phone=phone or _phone(), created_at=dt.datetime.now(tz=dt.UTC))
    session.add(account)
    session.commit()
    return account.id


def _sign_up_coaching(client: TestClient, session: Session) -> uuid.UUID:
    """Sign up as a coaching centre and return the new account.

    :param client: The test client
    :param session: A session to read the account back through
    :return: The account id
    """
    phone = _phone()
    response = client.post(
        "/v1/accounts",
        json={
            "phone": phone,
            "role": "coaching",
            "self_name": "Rina Manager",
            "centre_name": "Udoy Coaching",
            **ADDRESS,
        },
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["account_id"])


def _me(client: TestClient, session: Session, account_id: uuid.UUID) -> dict:
    """Read GET /v1/me.

    :param client: The test client
    :param session: A session to issue the token through
    :param account_id: The account
    :return: The body
    """
    response = client.get("/v1/me", headers=bearer(session, account_id))
    assert response.status_code == 200, response.text
    body: dict = response.json()
    return body


def _headers(
    session: Session, account_id: uuid.UUID, workspace: uuid.UUID | None = None
) -> dict[str, str]:
    """Authorize, optionally naming a workspace.

    :param session: A session to issue the token through
    :param account_id: The account
    :param workspace: The workspace to act on, or None
    :return: The headers
    """
    headers = bearer(session, account_id)
    if workspace is not None:
        headers["X-Workspace-Id"] = str(workspace)
    return headers


def _create_batch(client: TestClient, headers: dict[str, str], name: str) -> object:
    """Create a batch through the teacher route.

    :param client: The test client
    :param headers: The request headers
    :param name: The batch name
    :return: The response
    """
    return client.post(
        "/v1/batches", json={"name": name, "subjects": ["Physics"]}, headers=headers
    )


def _batch_names(client: TestClient, headers: dict[str, str]) -> set[str]:
    """List the batch names the request's workspace reaches.

    :param client: The test client
    :param headers: The request headers
    :return: The names
    """
    response = client.get("/v1/batches", headers=headers)
    assert response.status_code == 200, response.text
    return {row["name"] for row in response.json()}


def _member(
    session: Session,
    *,
    centre: uuid.UUID,
    account_id: uuid.UUID | None,
    role: str = "manager",
    decision: str = "accepted",
    revoked: bool = False,
    phone: str | None = None,
) -> uuid.UUID:
    """Arrange a membership row directly.

    :param session: An arranging session
    :param centre: The centre
    :param account_id: The member's account
    :param role: The role
    :param decision: The decision
    :param revoked: Whether it has ended
    :param phone: The number invited
    :return: The membership id
    """
    now = dt.datetime.now(tz=dt.UTC)
    member = OwnerMember(
        owner_id=centre,
        account_id=account_id,
        invited_phone=phone or _phone(),
        display_name="Someone",
        role=role,
        decision=decision,
        created_at=now,
        revoked_at=now if revoked else None,
    )
    session.add(member)
    session.commit()
    return member.id


def _centre(session: Session, name: str = "Udoy Coaching") -> uuid.UUID:
    """Arrange a centre with no members.

    :param session: An arranging session
    :param name: Its name
    :return: The centre's owner id
    """
    centre = Owner(
        account_id=None,
        kind="organisation",
        name=name,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(centre)
    session.commit()
    return centre.id


# ------------------------------------------------------------------ sign-up


def test_signing_up_as_coaching_opens_a_centre_the_person_manages(
    api_client: TestClient, owner_session: Session
) -> None:
    """The centre exists, has no account, and its creator is its manager."""
    account_id = _sign_up_coaching(api_client, owner_session)

    me = _me(api_client, owner_session, account_id)
    assert [w["kind"] for w in me["workspaces"]] == ["centre"]
    assert me["workspaces"][0]["name"] == "Udoy Coaching"
    assert me["lenses"] == [{"kind": "teacher", "count": 0}]

    centre = owner_session.get(Owner, uuid.UUID(me["workspaces"][0]["owner_id"]))
    assert centre is not None
    assert centre.kind == "organisation"
    assert centre.account_id is None
    # No solo workspace was created beside it.
    assert (
        owner_session.scalar(
            sa.select(sa.func.count()).where(Owner.account_id == account_id)
        )
        == 0
    )


def test_a_coaching_sign_up_needs_a_centre_name_and_others_refuse_one(
    api_client: TestClient,
) -> None:
    """The name is required for coaching and only for coaching."""
    base = {"self_name": "X", **ADDRESS}
    missing = api_client.post(
        "/v1/accounts", json={"phone": _phone(), "role": "coaching", **base}
    )
    extra = api_client.post(
        "/v1/accounts",
        json={"phone": _phone(), "role": "teacher", "centre_name": "Y", **base},
    )
    assert missing.status_code == 422, missing.text
    assert extra.status_code == 422, extra.text


# --------------------------------------------------------------- workspaces


def test_a_manager_acts_on_the_centre_through_the_teacher_routes(
    api_client: TestClient, owner_session: Session
) -> None:
    """With no solo workspace the centre is the default; the header agrees."""
    account_id = _sign_up_coaching(api_client, owner_session)
    centre = uuid.UUID(
        _me(api_client, owner_session, account_id)["workspaces"][0]["owner_id"]
    )

    created = _create_batch(api_client, _headers(owner_session, account_id), "Class 9")
    assert created.status_code == 201, created.text  # type: ignore[attr-defined]

    owners = owner_session.scalars(
        sa.text("SELECT owner_id FROM batch WHERE name = 'Class 9'")
    ).all()
    assert owners == [centre]
    assert _batch_names(api_client, _headers(owner_session, account_id, centre)) == {
        "Class 9"
    }


def test_a_tutor_who_also_manages_a_centre_keeps_the_two_apart(
    api_client: TestClient, owner_session: Session
) -> None:
    """No header is the solo workspace, exactly as before centres existed."""
    tutor = make_teacher(owner_session, name="Solo batch")
    opened = api_client.post(
        "/v1/centres",
        json={"name": "Udoy Coaching", "manager_name": "Karim"},
        headers=bearer(owner_session, tutor.account_id),
    )
    assert opened.status_code == 201, opened.text
    centre = uuid.UUID(opened.json()["owner_id"])

    me = _me(api_client, owner_session, tutor.account_id)
    assert [w["kind"] for w in me["workspaces"]] == ["solo", "centre"]

    made = _create_batch(
        api_client, _headers(owner_session, tutor.account_id, centre), "Centre batch"
    )
    assert made.status_code == 201, made.text  # type: ignore[attr-defined]

    assert _batch_names(api_client, _headers(owner_session, tutor.account_id)) == {
        "Solo batch"
    }
    assert _batch_names(
        api_client, _headers(owner_session, tutor.account_id, centre)
    ) == {"Centre batch"}


def test_a_workspace_the_account_does_not_manage_is_refused(
    api_client: TestClient, owner_session: Session
) -> None:
    """Naming another centre, or nonsense, reads the same as naming none."""
    tutor = make_teacher(owner_session)
    stranger_centre = _centre(owner_session)

    for workspace in (str(stranger_centre), str(uuid.uuid4()), "not-a-uuid"):
        headers = bearer(owner_session, tutor.account_id)
        headers["X-Workspace-Id"] = workspace
        response = api_client.get("/v1/batches", headers=headers)
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "NO_TEACHER_LENS"


def test_only_an_accepted_live_manager_membership_grants_the_centre(
    api_client: TestClient, owner_session: Session
) -> None:
    """Pending, declined, revoked and teacher-role memberships grant nothing."""
    centre = _centre(owner_session)
    cases = [
        {"decision": "pending"},
        {"decision": "declined"},
        {"decision": "accepted", "revoked": True},
        {"decision": "accepted", "role": "teacher"},
    ]
    for case in cases:
        account_id = _account(owner_session)
        _member(owner_session, centre=centre, account_id=account_id, **case)  # type: ignore[arg-type]
        response = api_client.get(
            "/v1/batches", headers=_headers(owner_session, account_id, centre)
        )
        assert response.status_code == 403, (case, response.text)
        assert _me(api_client, owner_session, account_id)["workspaces"] == []

    manager = _account(owner_session)
    _member(owner_session, centre=centre, account_id=manager)
    response = api_client.get(
        "/v1/batches", headers=_headers(owner_session, manager, centre)
    )
    assert response.status_code == 200, response.text


# ------------------------------------------------------------------ members


def test_an_invited_manager_holds_nothing_until_they_accept(
    api_client: TestClient, owner_session: Session
) -> None:
    """Invite, list, accept, then reach; decline withdraws again."""
    manager = _sign_up_coaching(api_client, owner_session)
    invitee_phone = _phone()
    invitee = _account(owner_session, invitee_phone)

    invited = api_client.post(
        "/v1/centre/members",
        json={"phone": invitee_phone, "display_name": "Sumi", "role": "manager"},
        headers=bearer(owner_session, manager),
    )
    assert invited.status_code == 201, invited.text
    assert invited.json()["decision"] == "pending"
    member_id = invited.json()["member_id"]

    assert _me(api_client, owner_session, invitee)["workspaces"] == []
    offers = api_client.get("/v1/memberships", headers=bearer(owner_session, invitee))
    assert offers.json() == [
        {
            "member_id": member_id,
            "centre_name": "Udoy Coaching",
            "role": "manager",
            "decision": "pending",
        }
    ]

    accepted = api_client.post(
        f"/v1/memberships/{member_id}/accept", headers=bearer(owner_session, invitee)
    )
    assert accepted.status_code == 200, accepted.text
    assert [
        w["kind"] for w in _me(api_client, owner_session, invitee)["workspaces"]
    ] == ["centre"]
    assert (
        api_client.get("/v1/memberships", headers=bearer(owner_session, invitee)).json()
        == []
    )

    # An accepted offer is no longer the holder's to toggle.
    again = api_client.post(
        f"/v1/memberships/{member_id}/decline", headers=bearer(owner_session, invitee)
    )
    assert again.status_code == 403, again.text


def test_an_offer_is_reachable_only_by_the_number_it_names(
    api_client: TestClient, owner_session: Session
) -> None:
    """Another account cannot accept someone else's offer."""
    centre = _centre(owner_session)
    invitee = _account(owner_session)
    member_id = _member(
        owner_session, centre=centre, account_id=invitee, decision="pending"
    )
    stranger = _account(owner_session)
    response = api_client.post(
        f"/v1/memberships/{member_id}/accept", headers=bearer(owner_session, stranger)
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "NO_MEMBERSHIP_LENS"


def test_an_invitation_to_a_new_number_links_at_sign_up_but_stays_pending(
    api_client: TestClient, owner_session: Session
) -> None:
    """Signing up is not accepting."""
    manager = _sign_up_coaching(api_client, owner_session)
    phone = _phone()
    invited = api_client.post(
        "/v1/centre/members",
        json={"phone": phone, "display_name": "Sumi", "role": "teacher"},
        headers=bearer(owner_session, manager),
    )
    assert invited.status_code == 201, invited.text

    signed = api_client.post(
        "/v1/accounts",
        json={"phone": phone, "role": "teacher", "self_name": "Sumi", **ADDRESS},
    )
    assert signed.status_code == 201, signed.text
    account_id = uuid.UUID(signed.json()["account_id"])

    member = owner_session.get(OwnerMember, uuid.UUID(invited.json()["member_id"]))
    owner_session.refresh(member)
    assert member is not None
    assert member.account_id == account_id
    assert member.decision == "pending"
    offers = api_client.get(
        "/v1/memberships", headers=bearer(owner_session, account_id)
    )
    assert [o["role"] for o in offers.json()] == ["teacher"]


def test_a_number_cannot_hold_two_live_memberships_in_one_centre(
    api_client: TestClient, owner_session: Session
) -> None:
    """The second invitation is refused while the first stands."""
    manager = _sign_up_coaching(api_client, owner_session)
    body = {"phone": _phone(), "display_name": "Sumi", "role": "teacher"}
    first = api_client.post(
        "/v1/centre/members", json=body, headers=bearer(owner_session, manager)
    )
    second = api_client.post(
        "/v1/centre/members", json=body, headers=bearer(owner_session, manager)
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "MEMBER_ALREADY_INVITED"


def test_a_revoked_manager_loses_the_centre_on_the_next_request(
    api_client: TestClient, owner_session: Session
) -> None:
    """Revocation takes effect at once and the record stays."""
    manager = _sign_up_coaching(api_client, owner_session)
    centre = uuid.UUID(
        _me(api_client, owner_session, manager)["workspaces"][0]["owner_id"]
    )
    second = _account(owner_session)
    member_id = _member(owner_session, centre=centre, account_id=second)
    assert (
        api_client.get(
            "/v1/batches", headers=_headers(owner_session, second, centre)
        ).status_code
        == 200
    )

    revoked = api_client.post(
        f"/v1/centre/members/{member_id}/revoke", headers=bearer(owner_session, manager)
    )
    assert revoked.status_code == 204, revoked.text

    response = api_client.get(
        "/v1/batches", headers=_headers(owner_session, second, centre)
    )
    assert response.status_code == 403, response.text
    listed = api_client.get(
        "/v1/centre/members", headers=bearer(owner_session, manager)
    ).json()
    assert [(row["is_you"], row["revoked"]) for row in listed] == [
        (True, False),
        (False, True),
    ]


def test_the_last_manager_cannot_be_revoked(
    api_client: TestClient, owner_session: Session
) -> None:
    """A centre always keeps someone who can manage it."""
    manager = _sign_up_coaching(api_client, owner_session)
    listed = api_client.get(
        "/v1/centre/members", headers=bearer(owner_session, manager)
    ).json()
    own = listed[0]["member_id"]

    response = api_client.post(
        f"/v1/centre/members/{own}/revoke", headers=bearer(owner_session, manager)
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "LAST_MANAGER"


def test_a_member_of_another_centre_cannot_be_revoked_from_this_one(
    api_client: TestClient, owner_session: Session
) -> None:
    """The id is checked against the centre the request acts on."""
    manager = _sign_up_coaching(api_client, owner_session)
    other = _centre(owner_session, "Other")
    theirs = _member(owner_session, centre=other, account_id=_account(owner_session))
    response = api_client.post(
        f"/v1/centre/members/{theirs}/revoke", headers=bearer(owner_session, manager)
    )
    assert response.status_code == 403, response.text
    assert owner_session.get(OwnerMember, theirs).revoked_at is None  # type: ignore[union-attr]


def test_a_solo_workspace_has_no_members_to_manage(
    api_client: TestClient, owner_session: Session
) -> None:
    """The member routes refuse a tutor's own workspace."""
    tutor = make_teacher(owner_session)
    response = api_client.get(
        "/v1/centre/members", headers=bearer(owner_session, tutor.account_id)
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "NOT_A_CENTRE"


# --------------------------------------------------- notification, deletion


def test_a_centre_batch_notifies_every_live_manager(owner_session: Session) -> None:
    """Accepted, unrevoked managers only; never a teacher or a pending offer."""
    centre = _centre(owner_session)
    first, second = _account(owner_session), _account(owner_session)
    _member(owner_session, centre=centre, account_id=first)
    _member(owner_session, centre=centre, account_id=second)
    _member(
        owner_session,
        centre=centre,
        account_id=_account(owner_session),
        decision="pending",
    )
    _member(
        owner_session, centre=centre, account_id=_account(owner_session), role="teacher"
    )
    _member(
        owner_session, centre=centre, account_id=_account(owner_session), revoked=True
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO batch (id, owner_id, name, marksheet_visible, active, "
            "created_at) VALUES (:id, :owner, 'B', true, true, now())"
        ),
        {"id": (batch := uuid.uuid4()), "owner": centre},
    )
    owner_session.commit()

    assert teacher_recipients(owner_session, batch_id=batch) == [first, second]


def test_deleting_an_account_ends_its_memberships(
    api_client: TestClient, owner_session: Session, restricted_session: Session
) -> None:
    """The centre keeps the record; the number cannot relink to it."""
    centre = _centre(owner_session)
    phone = _phone()
    leaving = _account(owner_session, phone)
    member_id = _member(owner_session, centre=centre, account_id=leaving, phone=phone)

    delete_account(restricted_session, phone)

    member = owner_session.get(OwnerMember, member_id)
    owner_session.refresh(member)
    assert member is not None
    assert member.account_id is None
    assert member.revoked_at is not None

    signed = api_client.post(
        "/v1/accounts",
        json={"phone": phone, "role": "teacher", "self_name": "Back", **ADDRESS},
    )
    assert signed.status_code == 201, signed.text
    owner_session.refresh(member)
    assert member.account_id is None


def test_two_invitations_of_one_number_at_once_get_one_member(
    api_client: TestClient, owner_session: Session
) -> None:
    """A double tap is one 201 and one 409, never a 500 [audit C-47].

    Both requests pass the "already invited?" read before either writes;
    the partial unique index refuses the second insert, which must be
    reported as the same conflict a sequential duplicate gets.
    """
    import threading

    manager = _sign_up_coaching(api_client, owner_session)
    body = {"phone": _phone(), "display_name": "Sumi", "role": "teacher"}
    headers = [bearer(owner_session, manager) for _ in range(2)]
    barrier = threading.Barrier(2)
    outcomes: list[tuple[int, str | None]] = []
    guard = threading.Lock()

    def invite(header: dict[str, str]) -> None:
        barrier.wait(timeout=30)
        response = api_client.post("/v1/centre/members", json=body, headers=header)
        code = None if response.status_code == 201 else response.json()["error"]["code"]
        with guard:
            outcomes.append((response.status_code, code))

    threads = [threading.Thread(target=invite, args=(h,)) for h in headers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads)

    assert sorted(outcomes, key=lambda o: o[0]) == [
        (201, None),
        (409, "MEMBER_ALREADY_INVITED"),
    ]
