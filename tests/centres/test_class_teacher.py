"""A centre teacher's own classes, and nothing else [C4, decision D2].

Written before the code. Each is an authorization outcome -- which
classes a teacher reaches, and when they stop -- so the team's
test-first predicate holds:

* A centre teacher sees only the classes assigned to them, across every
  centre they teach at, and no other class of the same batch.
* They may read the roster (names only), take attendance and log the
  topic for those classes, and nothing more: no teacher route opens to
  them.
* A queued write composed before a manager reassigned the class is
  refused at replay with CLASS_REASSIGNED, never applied.
* A removed teacher reaches nothing.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Account, OwnerMember
from app.db.models import Session as ClassSession
from app.local_time import bangladesh_today
from tests.batches.conftest import enroll
from tests.conftest import bearer
from tests.scheduling.test_scheduling import Centre, _slot

TOMORROW = bangladesh_today() + dt.timedelta(days=1)


def _account(session: Session) -> uuid.UUID:
    """Create an account with a fresh number.

    :param session: An arranging session
    :return: The account id
    """
    account = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(account)
    session.commit()
    return account.id


def _teacher(centre: Centre, account_id: uuid.UUID, **extra: object) -> uuid.UUID:
    """Arrange an accepted teacher membership for an account.

    :param centre: The centre
    :param account_id: The teacher's account
    :param extra: Columns overriding the defaults
    :return: The membership id
    """
    values: dict[str, object] = {
        "owner_id": centre.owner_id,
        "account_id": account_id,
        "invited_phone": f"+88018{uuid.uuid4().int % 10**8:08d}",
        "display_name": "Sumi",
        "role": "teacher",
        "decision": "accepted",
        "created_at": dt.datetime.now(tz=dt.UTC),
    }
    values.update(extra)
    member = OwnerMember(**values)
    centre.session.add(member)
    centre.session.commit()
    return member.id


def _first_class(session: Session, batch_id: uuid.UUID) -> ClassSession:
    """Read a batch's first class from tomorrow on.

    :param session: A session to read through
    :param batch_id: The batch
    :return: The class
    """
    session.expire_all()
    return session.scalars(
        sa.select(ClassSession)
        .where(ClassSession.batch_id == batch_id, ClassSession.date >= TOMORROW)
        .order_by(ClassSession.date)
        .limit(1)
    ).one()


class Setup:
    """A centre, a batch with one seat, and a teacher assigned to it.

    :ivar centre: The centre
    :ivar account: The teacher's account
    :ivar member: Their membership
    :ivar batch: The batch
    :ivar seat: The one seat
    :ivar target: The first upcoming class, assigned to them
    """

    def __init__(self, client: TestClient, session: Session) -> None:
        """Arrange it.

        :param client: The test client
        :param session: An arranging session
        """
        self.centre = Centre(client, session)
        self.account = _account(session)
        self.member = _teacher(self.centre, self.account)
        self.batch = self.centre.batch("Class 9")
        self.seat = enroll(
            session,
            batch_id=self.batch,
            display_name="Rahim",
            guardian_phone="+8801711112222",
        )
        response = self.centre.schedule(self.batch, _slot(self.member))
        assert response.status_code == 200, response.text  # type: ignore[attr-defined]
        self.target = _first_class(session, self.batch)

    def headers(self) -> dict[str, str]:
        """Authorize as the teacher.

        :return: The headers
        """
        return bearer(self.centre.session, self.account)


@pytest.fixture
def setup(api_client: TestClient, owner_session: Session) -> Setup:
    """Arrange one teacher with one assigned class.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: The arrangement
    """
    return Setup(api_client, owner_session)


def _attendance(setup: Setup, present: bool = True) -> object:
    """Submit the whole roster as the teacher.

    :param setup: The arrangement
    :param present: Whether the one seat was present
    :return: The response
    """
    return setup.centre.client.post(
        f"/v1/me/classes/{setup.target.id}/attendance",
        json={
            "base_attendance_version": 0,
            "client_mutation_id": str(uuid.uuid4()),
            "seats": [{"enrollment_id": str(setup.seat), "present": present}],
        },
        headers=setup.headers(),
    )


def _code(response: object) -> str:
    """Read an error code.

    :param response: The response
    :return: The code
    """
    code: str = response.json()["error"]["code"]  # type: ignore[attr-defined]
    return code


def test_my_classes_lists_only_the_classes_assigned_to_me(setup: Setup) -> None:
    """Another teacher's class at the same centre is not listed."""
    other = _teacher(setup.centre, _account(setup.centre.session))
    second = setup.centre.batch("Class 10")
    setup.centre.schedule(second, _slot(other, start="18:00", end="19:00"))

    day = setup.target.date.isoformat()
    response = setup.centre.client.get(
        f"/v1/me/classes?from={day}&to={day}", headers=setup.headers()
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    assert [(r["session_id"], r["batch_name"], r["centre_name"]) for r in rows] == [
        (str(setup.target.id), "Class 9", "Udoy Coaching")
    ]


def test_the_roster_shows_names_and_marks_and_nothing_else(setup: Setup) -> None:
    """No phone, no guardian, no fee on the class teacher's roster."""
    response = setup.centre.client.get(
        f"/v1/me/classes/{setup.target.id}/attendance", headers=setup.headers()
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "seats",
        "attendance_version",
        "writable",
        "topic",
        "topic_version",
    }
    assert body["seats"] == [
        {"enrollment_id": str(setup.seat), "display_name": "Rahim", "present": None}
    ]


def test_the_assigned_teacher_takes_attendance_and_logs_the_topic(
    setup: Setup,
) -> None:
    """Both classroom writes work for an assigned class."""
    taken = _attendance(setup)
    assert taken.status_code == 200, taken.text  # type: ignore[attr-defined]
    topic = setup.centre.client.put(
        f"/v1/me/classes/{setup.target.id}/topic",
        json={
            "base_topic_version": 0,
            "client_mutation_id": str(uuid.uuid4()),
            "topic": "Newton's laws",
        },
        headers=setup.headers(),
    )
    assert topic.status_code == 200, topic.text
    setup.centre.session.expire_all()
    row = setup.centre.session.get(ClassSession, setup.target.id)
    assert row is not None
    assert (row.status, row.topic) == ("held", "Newton's laws")


def test_a_class_reassigned_since_is_refused_at_replay(setup: Setup) -> None:
    """The queued write arrives after a manager moved the class."""
    substitute = _teacher(setup.centre, _account(setup.centre.session))
    moved = setup.centre.client.post(
        f"/v1/sessions/{setup.target.id}/assignment",
        json={"teacher_member_id": str(substitute), "room_id": None},
        headers=setup.centre.headers(),
    )
    assert moved.status_code == 200, moved.text

    late = _attendance(setup)
    assert late.status_code == 409, late.text  # type: ignore[attr-defined]
    assert _code(late) == "CLASS_REASSIGNED"
    setup.centre.session.expire_all()
    row = setup.centre.session.get(ClassSession, setup.target.id)
    assert row is not None and row.attendance_version == 0


def test_a_class_at_a_centre_i_do_not_teach_at_is_refused(
    setup: Setup, api_client: TestClient, owner_session: Session
) -> None:
    """Another centre's class reads the same as a missing one."""
    elsewhere = Setup(api_client, owner_session)
    for method, path in (
        ("GET", f"/v1/me/classes/{elsewhere.target.id}/attendance"),
        ("POST", f"/v1/me/classes/{elsewhere.target.id}/attendance"),
    ):
        response = api_client.request(
            method,
            path,
            json={
                "base_attendance_version": 0,
                "client_mutation_id": str(uuid.uuid4()),
                "seats": [],
            },
            headers=setup.headers(),
        )
        assert response.status_code == 403, (path, response.text)
        assert _code(response) == "NO_CLASS_LENS"


def test_a_removed_teacher_reaches_nothing(setup: Setup) -> None:
    """Revocation ends access at once; the listing empties too."""
    setup.centre.session.execute(
        sa.update(OwnerMember)
        .where(OwnerMember.id == setup.member)
        .values(revoked_at=dt.datetime.now(tz=dt.UTC))
    )
    setup.centre.session.commit()
    read = setup.centre.client.get(
        f"/v1/me/classes/{setup.target.id}/attendance", headers=setup.headers()
    )
    assert read.status_code == 403, read.text
    day = setup.target.date.isoformat()
    listed = setup.centre.client.get(
        f"/v1/me/classes?from={day}&to={day}", headers=setup.headers()
    )
    assert listed.json() == []


def test_a_centre_teacher_opens_no_teacher_route(setup: Setup) -> None:
    """The manager's routes stay closed: fail-closed by type."""
    headers = setup.headers()
    headers["X-Workspace-Id"] = str(setup.centre.owner_id)
    for path in (
        "/v1/batches",
        f"/v1/sessions/{setup.target.id}",
        f"/v1/sessions/{setup.target.id}/attendance",
        "/v1/centre/timetable?from=2026-11-01&to=2026-11-02",
    ):
        response = setup.centre.client.get(path, headers=headers)
        assert response.status_code == 403, (path, response.text)


def test_the_lens_picker_offers_the_centre_teacher_their_classes(
    setup: Setup,
) -> None:
    """/v1/me reports a class-teacher lens, counting the centres taught at."""
    me = setup.centre.client.get("/v1/me", headers=setup.headers()).json()
    assert {"kind": "class_teacher", "count": 1} in me["lenses"]
    assert all(entry["kind"] != "teacher" for entry in me["lenses"])


def test_a_resent_attendance_is_recognised_as_a_replay(setup: Setup) -> None:
    """The same key twice returns the original result and writes once."""
    body = {
        "base_attendance_version": 0,
        "client_mutation_id": str(uuid.uuid4()),
        "seats": [{"enrollment_id": str(setup.seat), "present": True}],
    }
    url = f"/v1/me/classes/{setup.target.id}/attendance"
    first = setup.centre.client.post(url, json=body, headers=setup.headers())
    again = setup.centre.client.post(url, json=body, headers=setup.headers())
    assert first.status_code == again.status_code == 200, again.text
    assert again.json() == first.json()
    setup.centre.session.expire_all()
    row = setup.centre.session.get(ClassSession, setup.target.id)
    assert row is not None and row.attendance_version == 1
