"""A student cannot do a teacher's job.

**This is the access limitation, tested.** The mechanism already
existed — every teacher-only route depends on `teacher_lens`, which
raises when the account owns no batches — but nothing asserted it, so
`NO_TEACHER_LENS` had no coverage at all. A mechanism with no test is
a mechanism that can be removed by a refactor without anything
noticing.

**Why there is no role column to test instead.** `BR1.1` forbids a
stored role, and these tests are what makes that safe rather than
merely principled: access is decided from the data at request time, so
the question "may this account create a batch" is answered by whether
it owns batches — which cannot go stale, cannot be edited to escalate,
and cannot disagree with reality.

A stored role would need its own test suite for the cases this one
cannot have: a role edited directly in the database, a role that says
`teacher` for an account whose batches were all deleted, a teacher who
is also a guardian elsewhere and needs both.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from app.money import Money
from tests.batches.conftest import (
    TeacherFixture,
    _account,
    enroll,
    make_teacher,
)


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


def _auth(session: Session, account_id: uuid.UUID) -> dict[str, str]:
    """Build an Authorization header for an account.

    :param session: The session to write the token family through
    :param account_id: The account to authenticate as
    :return: The header mapping
    """
    pair = issue_pair(session, account_id=account_id, correlation_id=uuid.uuid4())
    return {"Authorization": f"Bearer {pair.access_token}"}


@pytest.fixture
def teacher(owner_session: Session) -> TeacherFixture:
    """Build a teacher owning one batch.

    :param owner_session: A session able to arrange fixture data
    :return: The teacher
    """
    return make_teacher(owner_session, name="Physics")


@pytest.fixture
def student_account(owner_session: Session, teacher: TeacherFixture) -> uuid.UUID:
    """Build an account enrolled as a student and owning nothing.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The teacher whose batch they are enrolled in
    :return: The student's account id
    """
    account_id = _account(owner_session)
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="তাসনিম জাহান",
        student_account_id=account_id,
    )
    return account_id


# Every teacher-only write, refused ------------------------------------


def test_a_student_cannot_create_a_batch(
    client: TestClient, owner_session: Session, student_account: uuid.UUID
) -> None:
    """A student is refused the create-batch route.

    :param client: The test client
    :param owner_session: A session to mint a token through
    :param student_account: An account that owns no batches
    :return: None
    """
    response = client.post(
        "/v1/batches",
        headers=_auth(owner_session, student_account),
        json={"name": "My own batch", "subjects": ["Physics"]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NO_TEACHER_LENS"


def test_a_student_cannot_add_a_student_to_a_batch(
    client: TestClient,
    owner_session: Session,
    student_account: uuid.UUID,
    teacher: TeacherFixture,
) -> None:
    """A student is refused the add-enrollment route.

    Asked for the batch they are themselves enrolled in, which is the
    case most likely to pass by accident: the account IS related to
    this batch, just not as its owner.

    :param client: The test client
    :param owner_session: A session to mint a token through
    :param student_account: An account that owns no batches
    :param teacher: The teacher who owns the batch
    :return: None
    """
    response = client.post(
        f"/v1/batches/{teacher.batch_id}/enrollments",
        headers=_auth(owner_session, student_account),
        json={"display_name": "Someone else", "phone": "+8801711000002"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NO_TEACHER_LENS"


def test_a_student_cannot_read_a_roster(
    client: TestClient,
    owner_session: Session,
    student_account: uuid.UUID,
    teacher: TeacherFixture,
) -> None:
    """A student is refused the roster of their own batch.

    Read-only access does not mean read-everything: a roster names
    every other child in the class, and a classmate is not entitled to
    that list [TC-13].

    :param client: The test client
    :param owner_session: A session to mint a token through
    :param student_account: An account that owns no batches
    :param teacher: The teacher who owns the batch
    :return: None
    """
    response = client.get(
        f"/v1/batches/{teacher.batch_id}/roster",
        headers=_auth(owner_session, student_account),
    )
    assert response.status_code == 403


def test_a_student_sees_no_batches_on_the_teacher_route(
    client: TestClient, owner_session: Session, student_account: uuid.UUID
) -> None:
    """The teacher's batch list is refused, not merely empty.

    An empty list would be the wrong answer: it says "you are a teacher
    with no classes" to someone who is not a teacher, and a client
    would then offer them a create-batch button.

    :param client: The test client
    :param owner_session: A session to mint a token through
    :param student_account: An account that owns no batches
    :return: None
    """
    response = client.get("/v1/batches", headers=_auth(owner_session, student_account))
    assert response.status_code == 403


# The access decision follows the data, which a role column cannot -----


def test_teacher_access_comes_from_the_owner_row(
    client: TestClient,
    owner_session: Session,
    student_account: uuid.UUID,
) -> None:
    """An `Owner` row is what grants teacher access.

    **This is the account's role, and it IS stored** — as a row rather
    than as a string. An earlier version of this test asserted that
    owning a *batch* was the grant, and it failed: a teacher with zero
    batches still resolves a teacher lens, which is correct. A teacher
    who has not created their first class is still a teacher, and the
    empty batch list is a real screen in the design.

    What is not stored is a role *label*. The difference matters: an
    `Owner` row is the same fact the teacher-scoped queries join on, so
    "may this account create a batch" and "whose batches are these"
    are answered by one thing that cannot disagree with itself.

    :param client: The test client
    :param owner_session: A session to mint a token through
    :param student_account: An account with no owner row yet
    :return: None
    """
    headers = _auth(owner_session, student_account)

    refused = client.get("/v1/batches", headers=headers)
    assert refused.status_code == 403

    # Become a teacher. Note what is NOT written: no role string.
    owner_session.execute(
        text(
            "INSERT INTO owner (id, account_id, created_at) "
            "VALUES (:id, :account_id, now())"
        ),
        {"id": uuid.uuid4(), "account_id": student_account},
    )
    owner_session.commit()

    granted = client.get("/v1/batches", headers=headers)
    assert granted.status_code == 200
    # A teacher with no classes yet, which is a designed screen.
    assert granted.json() == []


def test_one_account_can_be_a_teacher_and_a_student_at_once(
    client: TestClient,
    owner_session: Session,
    student_account: uuid.UUID,
    teacher: TeacherFixture,
) -> None:
    """Both lenses resolve for one account in one session.

    **This is the case a single role column cannot represent.** The
    account is enrolled as a student in another teacher's batch AND
    owns batches of its own — a tutor who also has a child being
    tutored, which `FR1.4` names explicitly. A `role` column would
    have to pick one and would be wrong for every request about the
    other.

    :param client: The test client
    :param owner_session: A session to mint a token through
    :param student_account: An account already enrolled as a student
    :param teacher: The teacher whose batch they are enrolled in
    :return: None
    """
    # Built through the ORM, not raw SQL: `batch` carries NOT NULL
    # columns a hand-written INSERT omits, and an earlier version of
    # this test failed on exactly that.
    from app.db.models import Batch, Owner

    owner = Owner(account_id=student_account, created_at=dt.datetime.now(tz=dt.UTC))
    owner_session.add(owner)
    owner_session.commit()
    batch = Batch(
        owner_id=owner.id,
        name="What I teach",
        default_fee=Money("1500.00"),
        fee_due_day=10,
        marksheet_visible=True,
        active=True,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(batch)
    owner_session.commit()

    headers = _auth(owner_session, student_account)

    # The teacher lens: only their OWN batch, never the one they are
    # enrolled in as a student.
    mine = client.get("/v1/batches", headers=headers)
    assert mine.status_code == 200
    assert [row["name"] for row in mine.json()] == ["What I teach"]

    # And still refused the roster of the batch they are a student in.
    #
    # **404, and that is the designed answer rather than a weaker one.**
    # The teacher-lens query scopes by `owner_id`, so another teacher's
    # batch is not found rather than found-and-denied — which is the
    # indistinguishability B3's confidence hypothesis demands: the
    # response for someone else's batch must look exactly like the
    # response for a batch id that does not exist. An earlier version
    # of this test asserted 403 and failed; the implementation was
    # right and the assertion was wrong.
    other = client.get(f"/v1/batches/{teacher.batch_id}/roster", headers=headers)
    assert other.status_code == 404

    # Proving the indistinguishability rather than assuming it: a batch
    # id that exists for someone else and one that exists for nobody
    # return the same thing.
    nowhere = client.get(f"/v1/batches/{uuid.uuid4()}/roster", headers=headers)
    assert nowhere.status_code == other.status_code
    assert nowhere.json() == other.json()
