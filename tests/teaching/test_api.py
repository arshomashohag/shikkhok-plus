"""The D4 routes, driven through the real application.

Written test-after, over an authorization layer already proven
test-first: the predicate does not hold for route plumbing, because
every authorization answer these routes give is the domain layer's and
is already asserted there.

**What this module adds that the domain tests cannot**: that the
handler wires the lens to the service at all. A route that resolves a
lens and then ignores it passes every domain test, and the built
route-enumeration gate only checks that a lens is RESOLVED -- not that
its value reaches the query.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session as DbSession

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from app.db.models import Session
from tests.batches.conftest import TeacherFixture, enroll

SESSION_DATE = dt.date(2027, 4, 12)


@pytest.fixture
def client(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build a client whose app uses the RESTRICTED test engine.

    Restricted and not owner, for the reason the privacy conftest
    states: an application connected as the table owner bypasses row
    policy entirely.

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


def _bearer(session: DbSession, account_id: uuid.UUID) -> dict[str, str]:
    """Build an Authorization header for an account.

    Through ``issue_pair``, which is the application's own path and
    writes the token family -- the shape ``tests/batches`` already
    established.

    :param session: The session to write the token family through
    :param account_id: The account to authenticate as
    :return: The header mapping
    """
    pair = issue_pair(session, account_id=account_id, correlation_id=uuid.uuid4())
    return {"Authorization": f"Bearer {pair.access_token}"}


@pytest.fixture
def api_session(owner_session: DbSession, teacher: TeacherFixture) -> uuid.UUID:
    """One session on the fixture teacher's batch.

    :param owner_session: A session able to arrange fixture data
    :param teacher: Its owner
    :return: The session id
    """
    row = Session(
        batch_id=teacher.batch_id,
        date=SESSION_DATE,
        start_time=dt.time(16, 0),
        status="scheduled",
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(row)
    owner_session.commit()
    return row.id


def test_an_unauthenticated_request_is_refused(
    client: TestClient, api_session: uuid.UUID
) -> None:
    response = client.get(f"/v1/sessions/{api_session}")

    assert response.status_code == 401


def test_the_roster_round_trips_through_the_api(
    owner_session: DbSession,
    client: TestClient,
    teacher: TeacherFixture,
    api_session: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    headers = _bearer(owner_session, teacher.account_id)

    before = client.get(f"/v1/sessions/{api_session}/attendance", headers=headers)
    assert before.status_code == 200
    # The response wraps its seats and carries the version, added
    # 2026-10-27: a 409 is only recoverable if the app can read the
    # current version and compose the next write from it.
    assert before.json() == {
        "seats": [
            {
                "enrollment_id": str(seat),
                "display_name": "Rahim",
                "present": None,
            }
        ],
        "attendance_version": 0,
    }

    applied = client.post(
        f"/v1/sessions/{api_session}/attendance",
        headers=headers,
        json={
            "base_attendance_version": 0,
            "client_mutation_id": str(uuid.uuid4()),
            "seats": [{"enrollment_id": str(seat), "present": False}],
        },
    )
    assert applied.status_code == 200
    assert applied.json()["attendance_version"] == 1

    after = client.get(f"/v1/sessions/{api_session}/attendance", headers=headers)
    assert after.json()["seats"][0]["present"] is False
    # The version moved with the write, which is what the next
    # submission must send as its base.
    assert after.json()["attendance_version"] == 1


def test_a_stale_version_returns_409_with_the_current_state(
    owner_session: DbSession,
    client: TestClient,
    teacher: TeacherFixture,
    api_session: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    headers = _bearer(owner_session, teacher.account_id)
    body = {
        "base_attendance_version": 0,
        "client_mutation_id": str(uuid.uuid4()),
        "seats": [{"enrollment_id": str(seat), "present": True}],
    }
    client.post(f"/v1/sessions/{api_session}/attendance", headers=headers, json=body)

    stale = client.post(
        f"/v1/sessions/{api_session}/attendance",
        headers=headers,
        json={**body, "client_mutation_id": str(uuid.uuid4())},
    )

    assert stale.status_code == 409
    envelope = stale.json()
    assert envelope["error"]["code"] == "ATTENDANCE_VERSION_CONFLICT"
    assert envelope["error"]["retryable"] is False
    assert envelope["error"]["details"]["current_version"] == "1"


def test_a_replay_through_the_api_returns_200_and_writes_nothing(
    owner_session: DbSession,
    client: TestClient,
    teacher: TeacherFixture,
    api_session: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    headers = _bearer(owner_session, teacher.account_id)
    body = {
        "base_attendance_version": 0,
        "client_mutation_id": str(uuid.uuid4()),
        "seats": [{"enrollment_id": str(seat), "present": True}],
    }

    first = client.post(
        f"/v1/sessions/{api_session}/attendance", headers=headers, json=body
    )
    second = client.post(
        f"/v1/sessions/{api_session}/attendance", headers=headers, json=body
    )

    assert first.status_code == 200
    assert second.status_code == 200, (
        "a replay must return 200 and the ORIGINAL stored result -- not "
        "201 and not an error [BR3.8]"
    )
    assert second.json() == first.json()


def test_another_teacher_gets_the_same_refusal_as_an_invented_id(
    owner_session: DbSession,
    client: TestClient,
    teacher: TeacherFixture,
    api_session: uuid.UUID,
) -> None:
    # The IDOR equality probe at the HTTP layer: same status, same
    # body. Two independent "is a refusal" assertions both pass while
    # the bodies differ, and the difference is the leak [§ 2.3].
    from tests.batches.conftest import make_teacher

    other = make_teacher(owner_session, name="Chemistry")
    headers = _bearer(owner_session, other.account_id)

    real = client.get(f"/v1/sessions/{api_session}", headers=headers)
    invented = client.get(f"/v1/sessions/{uuid.uuid4()}", headers=headers)

    assert real.status_code == invented.status_code
    assert real.json() == invented.json()


def test_the_topic_round_trips_with_its_own_version(
    owner_session: DbSession,
    client: TestClient,
    teacher: TeacherFixture,
    api_session: uuid.UUID,
) -> None:
    headers = _bearer(owner_session, teacher.account_id)

    written = client.put(
        f"/v1/sessions/{api_session}/topic",
        headers=headers,
        json={
            "base_topic_version": 0,
            "client_mutation_id": str(uuid.uuid4()),
            "topic": "Refraction",
        },
    )
    assert written.status_code == 200
    assert written.json()["topic_version"] == 1

    read = client.get(f"/v1/sessions/{api_session}", headers=headers)
    assert read.json()["topic"] == "Refraction"
    assert read.json()["topic_logged"] is True


@pytest.mark.parametrize(
    ("method", "suffix", "body", "version_field"),
    [
        pytest.param(
            "POST",
            "attendance",
            {"base_attendance_version": 0, "seats": []},
            "attendance_version",
            id="roster",
        ),
        pytest.param(
            "PUT",
            "topic",
            {"base_topic_version": 0, "topic": "Refraction"},
            "topic_version",
            id="topic",
        ),
    ],
)
def test_both_declared_mutation_id_paths_actually_replay(
    owner_session: DbSession,
    client: TestClient,
    teacher: TeacherFixture,
    api_session: uuid.UUID,
    method: str,
    suffix: str,
    body: dict[str, object],
    version_field: str,
) -> None:
    """A test per path, replaying a real request [§ B.7, BR2.1].

    **This is the assertion the contract test cannot make.**
    ``tests/contract/test_teaching_contract.py`` asserts that exactly
    two request bodies DECLARE ``client_mutation_id``, which is a
    wire-level property and passed while only the roster path
    implemented it: the topic handler bound the body and never
    forwarded the field. Declaration is not implementation, so each
    path is replayed here and asserted to write nothing the second
    time.

    Parametrised deliberately, rather than written once per path: a
    third body that declares the field without implementing it fails
    the contract test, and a path that implements it must appear here
    or the pair is incomplete again.

    :param owner_session: A session able to arrange fixture data
    :param client: The application client
    :param teacher: The session's owner
    :param api_session: The session being written
    :param method: The HTTP verb
    :param suffix: The path segment under the session
    :param body: The request body, without its replay key
    :param version_field: The version the response carries
    :return: None
    """
    headers = _bearer(owner_session, teacher.account_id)
    payload = {**body, "client_mutation_id": str(uuid.uuid4())}
    url = f"/v1/sessions/{api_session}/{suffix}"

    first = client.request(method, url, headers=headers, json=payload)
    second = client.request(method, url, headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200, (
        f"the {suffix} replay returned {second.status_code}: a replayed "
        "mutation id must return 200 and the ORIGINAL stored result "
        "[§ B.7]"
    )
    assert second.json() == first.json()
    assert second.json()[version_field] == 1, (
        f"{version_field} reached {second.json()[version_field]} on a "
        "replay: the resent write was applied again, which is what the "
        "device queue produces after one flaky send [NFR5]"
    )


def test_an_empty_topic_is_logged_and_blank(
    owner_session: DbSession,
    client: TestClient,
    teacher: TeacherFixture,
    api_session: uuid.UUID,
) -> None:
    # BR2.2 across the wire: an unwritten topic and one saved as blank
    # must read differently, which is the whole content of AC3.4.2.
    headers = _bearer(owner_session, teacher.account_id)

    before = client.get(f"/v1/sessions/{api_session}", headers=headers).json()
    assert before["topic"] is None
    assert before["topic_logged"] is False

    client.put(
        f"/v1/sessions/{api_session}/topic",
        headers=headers,
        json={
            "base_topic_version": 0,
            "client_mutation_id": str(uuid.uuid4()),
            "topic": "",
        },
    )

    after = client.get(f"/v1/sessions/{api_session}", headers=headers).json()
    assert after["topic"] == ""
    assert after["topic_logged"] is True


def test_announcements_round_trip_and_soft_delete(
    owner_session: DbSession,
    client: TestClient,
    teacher: TeacherFixture,
) -> None:
    headers = _bearer(owner_session, teacher.account_id)

    posted = client.post(
        f"/v1/batches/{teacher.batch_id}/announcements",
        headers=headers,
        json={"body": "Bring protractors"},
    )
    assert posted.status_code == 201
    assert posted.json()["edited"] is False
    note_id = posted.json()["announcement_id"]

    edited = client.put(
        f"/v1/announcements/{note_id}",
        headers=headers,
        json={"body": "Bring protractors and a ruler"},
    )
    assert edited.json()["edited"] is True

    removed = client.delete(f"/v1/announcements/{note_id}", headers=headers)
    assert removed.status_code == 204

    listed = client.get(
        f"/v1/batches/{teacher.batch_id}/announcements", headers=headers
    )
    assert listed.json() == []


def test_an_ad_hoc_session_is_created_through_the_api(
    owner_session: DbSession,
    client: TestClient,
    teacher: TeacherFixture,
) -> None:
    headers = _bearer(owner_session, teacher.account_id)

    created = client.post(
        f"/v1/batches/{teacher.batch_id}/sessions",
        headers=headers,
        json={"date": "2027-04-17", "start_time": "10:00:00"},
    )

    assert created.status_code == 201
    assert created.json()["origin"] == "ad_hoc"


def test_a_cancelled_session_refuses_a_roster_with_409(
    owner_session: DbSession,
    client: TestClient,
    teacher: TeacherFixture,
    api_session: uuid.UUID,
) -> None:
    headers = _bearer(owner_session, teacher.account_id)
    client.post(f"/v1/sessions/{api_session}/cancellation", headers=headers)

    refused = client.post(
        f"/v1/sessions/{api_session}/attendance",
        headers=headers,
        json={
            "base_attendance_version": 0,
            "client_mutation_id": str(uuid.uuid4()),
            "seats": [],
        },
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "SESSION_CANCELLED"


def test_a_body_with_an_unknown_field_is_refused(
    owner_session: DbSession,
    client: TestClient,
    teacher: TeacherFixture,
    api_session: uuid.UUID,
) -> None:
    # `extra="forbid"` on every schema: a client sending a field the
    # server does not know is told so rather than having it silently
    # dropped, which is how a queue_state field would arrive.
    response = client.post(
        f"/v1/sessions/{api_session}/attendance",
        headers=_bearer(owner_session, teacher.account_id),
        json={
            "base_attendance_version": 0,
            "client_mutation_id": str(uuid.uuid4()),
            "seats": [],
            "queue_state": "queued",
        },
    )

    assert response.status_code == 422
