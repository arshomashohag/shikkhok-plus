"""A batch's weekly schedule can be set, and sessions follow at once.

**Written before the routes existed.** Sessions are generated nightly from
``schedule_slot`` rows, and nothing could write one: no route, no field on
batch creation. So no batch ever had a session, and attendance and topic
logging could not be reached by anyone. Ownership is the authorization
half and is test-first by the predicate; the rest is pinned here because
it is the contract the app is about to be built against.

**A changed schedule leaves existing sessions alone** [BR1.2]. These
tests assert that rule as it stands rather than a friendlier one: a
Tuesday class moved to Wednesday keeps the Tuesday sessions already
generated, and the teacher cancels those individually.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session as DbSession

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from app.db.models import Session
from tests.batches.conftest import TeacherFixture, make_teacher

MON_WED = [
    {"weekday": 0, "start_time": "16:00", "end_time": "17:30"},
    {"weekday": 2, "start_time": "16:00", "end_time": "17:30"},
]


@pytest.fixture
def client(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build a client whose app uses the restricted test engine.

    :param restricted_engine: The non-superuser engine
    :param monkeypatch: The patcher
    :return: A context manager yielding the client
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:test-signing-key-padded-to-thirty-two")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    from app.main import create_app

    app = create_app()
    app.state.engine = restricted_engine
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def owner(owner_session: DbSession) -> TeacherFixture:
    """Create the teacher who owns the batch under test.

    :param owner_session: A session able to arrange fixture data
    :return: The teacher
    """
    return make_teacher(owner_session, name="Physics")


def _bearer(session: DbSession, account_id: uuid.UUID) -> dict[str, str]:
    """Authorize as an account.

    :param session: A session to write the token family through
    :param account_id: The account
    :return: The header mapping
    """
    pair = issue_pair(session, account_id=account_id, correlation_id=uuid.uuid4())
    return {"Authorization": f"Bearer {pair.access_token}"}


def _sessions(session: DbSession, batch_id: uuid.UUID) -> list[Session]:
    """Read a batch's sessions fresh.

    :param session: An arranging session
    :param batch_id: The batch
    :return: Its sessions
    """
    session.expire_all()
    return list(
        session.scalars(sa.select(Session).where(Session.batch_id == batch_id)).all()
    )


def test_setting_a_schedule_creates_sessions_at_once(
    client: TestClient, owner_session: DbSession, owner: TeacherFixture
) -> None:
    """The teacher does not wait for tonight's job to take attendance.

    :param client: The test client
    :param owner_session: An arranging session
    :param owner: The batch's teacher
    :return: None
    """
    response = client.put(
        f"/v1/batches/{owner.batch_id}/schedule",
        json={"slots": MON_WED},
        headers=_bearer(owner_session, owner.account_id),
    )

    assert response.status_code == 200, response.text
    sessions = _sessions(owner_session, owner.batch_id)
    assert sessions, "no session was generated"
    assert {row.date.weekday() for row in sessions} == {0, 2}


def test_the_schedule_reads_back(
    client: TestClient, owner_session: DbSession, owner: TeacherFixture
) -> None:
    """What was set is what is read, in weekday order.

    :param client: The test client
    :param owner_session: An arranging session
    :param owner: The batch's teacher
    :return: None
    """
    headers = _bearer(owner_session, owner.account_id)
    client.put(
        f"/v1/batches/{owner.batch_id}/schedule",
        json={"slots": list(reversed(MON_WED))},
        headers=headers,
    )

    slots = client.get(f"/v1/batches/{owner.batch_id}/schedule", headers=headers).json()

    assert slots == MON_WED


def test_setting_a_schedule_replaces_the_old_one(
    client: TestClient, owner_session: DbSession, owner: TeacherFixture
) -> None:
    """Replacing, not appending: the read shows only the new slots.

    :param client: The test client
    :param owner_session: An arranging session
    :param owner: The batch's teacher
    :return: None
    """
    headers = _bearer(owner_session, owner.account_id)
    url = f"/v1/batches/{owner.batch_id}/schedule"
    client.put(url, json={"slots": MON_WED}, headers=headers)
    friday = [{"weekday": 4, "start_time": "09:00", "end_time": "10:00"}]

    client.put(url, json={"slots": friday}, headers=headers)

    assert client.get(url, headers=headers).json() == friday


def test_a_changed_schedule_leaves_generated_sessions_alone(
    client: TestClient, owner_session: DbSession, owner: TeacherFixture
) -> None:
    """BR1.2 as it stands: moving Monday away keeps Monday's sessions.

    :param client: The test client
    :param owner_session: An arranging session
    :param owner: The batch's teacher
    :return: None
    """
    headers = _bearer(owner_session, owner.account_id)
    url = f"/v1/batches/{owner.batch_id}/schedule"
    client.put(url, json={"slots": MON_WED[:1]}, headers=headers)
    mondays = {row.id for row in _sessions(owner_session, owner.batch_id)}

    client.put(url, json={"slots": MON_WED[1:]}, headers=headers)

    remaining = {row.id for row in _sessions(owner_session, owner.batch_id)}
    assert mondays <= remaining


def test_another_teachers_batch_is_not_found(
    client: TestClient, owner_session: DbSession, owner: TeacherFixture
) -> None:
    """A teacher cannot set or read a schedule on a batch they do not own.

    404 rather than 403, so the refusal does not confirm the batch exists.

    :param client: The test client
    :param owner_session: An arranging session
    :param owner: The batch's teacher
    :return: None
    """
    stranger = make_teacher(owner_session, name="Chemistry")
    headers = _bearer(owner_session, stranger.account_id)
    url = f"/v1/batches/{owner.batch_id}/schedule"

    written = client.put(url, json={"slots": MON_WED}, headers=headers)
    read = client.get(url, headers=headers)

    assert written.status_code == 404
    assert read.status_code == 404
    assert _sessions(owner_session, owner.batch_id) == []


@pytest.mark.parametrize(
    "slot",
    [
        {"weekday": 7, "start_time": "16:00", "end_time": "17:00"},
        {"weekday": -1, "start_time": "16:00", "end_time": "17:00"},
        {"weekday": 1, "start_time": "17:00", "end_time": "16:00"},
        {"weekday": 1, "start_time": "16:00", "end_time": "16:00"},
    ],
)
def test_an_impossible_slot_is_refused(
    client: TestClient,
    owner_session: DbSession,
    owner: TeacherFixture,
    slot: dict[str, object],
) -> None:
    """A weekday outside 0-6, or a class that ends before it starts.

    :param client: The test client
    :param owner_session: An arranging session
    :param owner: The batch's teacher
    :param slot: One impossible slot
    :return: None
    """
    response = client.put(
        f"/v1/batches/{owner.batch_id}/schedule",
        json={"slots": [slot]},
        headers=_bearer(owner_session, owner.account_id),
    )

    assert response.status_code in (400, 422)
    assert _sessions(owner_session, owner.batch_id) == []


def test_two_identical_slots_are_refused(
    client: TestClient, owner_session: DbSession, owner: TeacherFixture
) -> None:
    """The same class twice is a typing error, not two classes.

    :param client: The test client
    :param owner_session: An arranging session
    :param owner: The batch's teacher
    :return: None
    """
    response = client.put(
        f"/v1/batches/{owner.batch_id}/schedule",
        json={"slots": [MON_WED[0], MON_WED[0]]},
        headers=_bearer(owner_session, owner.account_id),
    )

    assert response.status_code == 400
    assert response.json()["error"]["message_key"] == "schedule.duplicate_slot"


def test_a_batch_can_be_created_with_its_schedule(
    client: TestClient, owner_session: DbSession, owner: TeacherFixture
) -> None:
    """T0 "Set up your first batch": name it and pick its class days.

    :param client: The test client
    :param owner_session: An arranging session
    :param owner: A teacher
    :return: None
    """
    response = client.post(
        "/v1/batches",
        json={"name": "Batch S", "subjects": ["Physics"], "schedule": MON_WED},
        headers=_bearer(owner_session, owner.account_id),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["schedule"] == MON_WED
    assert _sessions(owner_session, uuid.UUID(body["id"])), "no session was generated"


def test_the_batch_list_carries_each_schedule(
    client: TestClient, owner_session: DbSession, owner: TeacherFixture
) -> None:
    """T6's card line, "Mon Wed · 4:00 pm", needs the slots on the list.

    :param client: The test client
    :param owner_session: An arranging session
    :param owner: The batch's teacher
    :return: None
    """
    headers = _bearer(owner_session, owner.account_id)
    client.put(
        f"/v1/batches/{owner.batch_id}/schedule",
        json={"slots": MON_WED},
        headers=headers,
    )

    listed = next(
        batch
        for batch in client.get("/v1/batches", headers=headers).json()
        if batch["id"] == str(owner.batch_id)
    )

    assert listed["schedule"] == MON_WED
