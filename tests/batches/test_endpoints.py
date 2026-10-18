"""The batch and enrollment routes, end to end through the real app.

**The money assertions are made at the HTTP boundary**, not at the
function boundary. A money value emitted as a JSON number is converted
to an IEEE 754 double by the client's parser, on the far side of the
wire where none of this project's controls reach -- so the only place
worth asserting it is where the bytes actually leave.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from tests.batches.conftest import TeacherFixture, enroll, make_teacher


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


def _auth(
    client: TestClient, session: Session, account_id: uuid.UUID
) -> dict[str, str]:
    """Build an Authorization header for an account.

    :param client: The test client, for its app's configuration
    :param session: The session to write the token family through
    :param account_id: The account to authenticate as
    :return: The header mapping
    """
    pair = issue_pair(session, account_id=account_id, correlation_id=uuid.uuid4())
    return {"Authorization": f"Bearer {pair.access_token}"}


@pytest.fixture
def teacher(owner_session: Session) -> TeacherFixture:
    """Create a teacher with one batch.

    :param owner_session: A session able to arrange fixture data
    :return: The teacher
    """
    return make_teacher(owner_session, name="Physics")


def test_a_roster_read_requires_a_lens(
    client: TestClient, teacher: TeacherFixture
) -> None:
    """An unauthenticated roster read is refused.

    :param client: The test client
    :param teacher: A teacher with a batch
    :return: None
    """
    response = client.get(f"/v1/batches/{teacher.batch_id}/roster")

    assert response.status_code in {401, 403}


def test_money_crosses_as_a_json_string_never_a_number(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """``default_fee`` is a quoted string in the raw response body.

    Parsing the JSON first would hide the defect this asserts: a number
    and a string both decode to something truthy, and the damage is done
    by the client's parser before any assertion runs. The **raw text**
    is what carries the proof.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param teacher: A teacher with a batch
    :return: None
    """
    response = client.get(
        "/v1/batches", headers=_auth(client, owner_session, teacher.account_id)
    )

    assert response.status_code == 200
    assert '"default_fee":"1500.00"' in response.text.replace(" ", "")
    body = response.json()
    assert isinstance(body[0]["default_fee"], str)


def test_a_money_field_sent_as_a_number_is_refused(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A lenient decoder is the actual failure mode, so inbound is pinned.

    A decoder that quietly accepted a number and converted would pass a
    happy-path test on both sides while the value was already a float.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param teacher: A teacher with a batch
    :return: None
    """
    response = client.post(
        "/v1/batches",
        headers=_auth(client, owner_session, teacher.account_id),
        content=json.dumps(
            {"name": "Chemistry", "subjects": ["Chem"], "default_fee": 1500.00}
        ),
    )

    assert response.status_code == 422


def test_the_roster_carries_a_server_computed_status(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Each row names its status; the client compares nothing [TC-9].

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param teacher: A teacher with a batch
    :return: None
    """
    from tests.batches.conftest import _account

    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Dormant seat",
        student_account_id=None,
    )
    claimed = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Active seat",
        student_account_id=_account(owner_session),
    )
    left = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Inactive seat",
        student_account_id=_account(owner_session),
    )
    from app.db.models import Enrollment

    record = owner_session.get(Enrollment, left)
    assert record is not None
    record.inactive_from = dt.date(2026, 2, 15)
    owner_session.commit()

    response = client.get(
        f"/v1/batches/{teacher.batch_id}/roster",
        headers=_auth(client, owner_session, teacher.account_id),
    )

    assert response.status_code == 200
    statuses = {row["display_name"]: row["status"] for row in response.json()}
    assert statuses["Dormant seat"] == "dormant"
    assert statuses["Active seat"] == "active"
    assert statuses["Inactive seat"] == "inactive"
    assert claimed is not None


def test_another_owners_batch_returns_404_not_403(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A 403 would confirm the batch exists [NFR14.13].

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param teacher: A teacher with a batch
    :return: None
    """
    intruder = make_teacher(owner_session, name="Biology")

    response = client.get(
        f"/v1/batches/{teacher.batch_id}/roster",
        headers=_auth(client, owner_session, intruder.account_id),
    )

    assert response.status_code == 404


def test_the_error_envelope_names_a_message_key_not_english(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A server-sent English string cannot be localized [TC-15, D-43].

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param teacher: A teacher with a batch
    :return: None
    """
    intruder = make_teacher(owner_session, name="Biology")

    response = client.get(
        f"/v1/batches/{teacher.batch_id}/roster",
        headers=_auth(client, owner_session, intruder.account_id),
    )
    body = response.json()

    assert body["error"]["code"] == "BATCH_NOT_FOUND"
    assert body["error"]["message_key"] == "batch.not_found"
    assert "message" not in body["error"]


def test_another_teacher_cannot_remove_a_seat_over_http(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The IDOR, asserted at the HTTP boundary [NFR14.14].

    **The service-level regressions are not enough on their own.** They
    call the service directly, so a handler that resolved its lens and
    then passed a forged one would pass every one of them. The static
    gate cannot see it either: that handler *references* its lens.

    Only a request through the real app exercises the whole path, which
    is why this lives here rather than beside the service tests.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param teacher: The teacher who owns the batch
    :return: None
    """
    from app.db.models import Enrollment

    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Not the attacker's student",
        student_account_id=None,
    )
    attacker = make_teacher(owner_session, name="Chemistry")

    response = client.delete(
        f"/v1/enrollments/{seat}",
        headers=_auth(client, owner_session, attacker.account_id),
    )

    assert response.status_code == 404
    # The seat SURVIVES. A 404 alone would pass against a handler that
    # deleted the row and then failed to find it.
    owner_session.expire_all()
    assert owner_session.get(Enrollment, seat) is not None


def test_another_teacher_cannot_deactivate_a_seat_over_http(
    client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """The money-adjacent half, over HTTP.

    ``inactive_from`` stops future fee cycles, so writing it on another
    teacher's seat silently stops that teacher being paid.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param teacher: The teacher who owns the batch
    :return: None
    """
    from app.db.models import Enrollment
    from tests.batches.conftest import _account

    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Not the attacker's student",
        student_account_id=_account(owner_session),
    )
    attacker = make_teacher(owner_session, name="Chemistry")

    response = client.patch(
        f"/v1/enrollments/{seat}/inactive-from",
        headers=_auth(client, owner_session, attacker.account_id),
        json={"inactive_from": "2026-02-15"},
    )

    assert response.status_code == 404
    owner_session.expire_all()
    assert owner_session.get(Enrollment, seat).inactive_from is None
