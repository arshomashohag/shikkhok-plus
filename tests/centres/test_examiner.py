"""An exam's named examiner, and the examiner's reach [C4, decided 2026-11-06].

Written before the code. "A manager creates the exam and names the
examiner; the examiner enters and publishes its marks." Each test is an
authorization outcome, so the team's test-first predicate holds:

* The manager names the examiner at creation, or later; one live member
  of the centre only, and never at a solo tutor's.
* With none named, the batch's one weekly teacher is the default.
* The examiner reads the results (names and marks only), enters marks
  and publishes, through routes no other lens reaches.
* A member who is not, or is no longer, the examiner is told
  EXAM_REASSIGNED; a stranger reads the same as a missing exam.
* Removing the teacher clears them as examiner of unpublished exams.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import BatchSubject, Exam, OwnerMember
from app.local_time import bangladesh_today
from tests.batches.conftest import enroll, make_teacher
from tests.centres.test_class_teacher import _account, _teacher
from tests.conftest import bearer
from tests.scheduling.test_scheduling import Centre, _slot


class Setup:
    """A centre with a batch, one seat, and a teacher who teaches it.

    :ivar centre: The centre
    :ivar account: The teacher's account
    :ivar member: Their membership
    :ivar batch: The batch
    :ivar subject: The batch's one subject
    :ivar seat: The one seat
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
        self.subject = session.scalars(
            sa.select(BatchSubject.id).where(BatchSubject.batch_id == self.batch)
        ).one()
        self.seat = enroll(
            session,
            batch_id=self.batch,
            display_name="Rahim",
            guardian_phone="+8801711112222",
        )
        self.centre.schedule(self.batch, _slot(self.member))

    def create(self, **body: object) -> object:
        """Create an exam as the manager.

        :param body: Fields overriding the defaults
        :return: The response
        """
        request: dict[str, object] = {
            "batch_subject_id": str(self.subject),
            "title": "Half-yearly",
            "date": bangladesh_today().isoformat(),
            "total_marks": 100,
        }
        request.update(body)
        return self.centre.client.post(
            f"/v1/batches/{self.batch}/exams",
            json=request,
            headers=self.centre.headers(),
        )

    def teacher_headers(self) -> dict[str, str]:
        """Authorize as the teacher.

        :return: The headers
        """
        return bearer(self.centre.session, self.account)


@pytest.fixture
def setup(api_client: TestClient, owner_session: Session) -> Setup:
    """Arrange a centre with one teacher.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: The arrangement
    """
    return Setup(api_client, owner_session)


def _code(response: object) -> str:
    """Read an error code.

    :param response: The response
    :return: The code
    """
    code: str = response.json()["error"]["code"]  # type: ignore[attr-defined]
    return code


def _exam_id(response: object) -> str:
    """Read an exam id from a successful creation.

    :param response: The response
    :return: The id
    """
    assert response.status_code == 201, response.text  # type: ignore[attr-defined]
    exam_id: str = response.json()["exam_id"]  # type: ignore[attr-defined]
    return exam_id


def test_the_batch_teacher_is_the_default_examiner(setup: Setup) -> None:
    """With exactly one weekly teacher, the exam names them."""
    body = setup.create().json()  # type: ignore[attr-defined]
    assert body["examiner_member_id"] == str(setup.member)
    assert body["examiner_name"] == "Sumi"


def test_the_manager_names_and_changes_the_examiner(setup: Setup) -> None:
    """Named at creation, changed later, and cleared."""
    other = _teacher(setup.centre, _account(setup.centre.session))
    exam_id = _exam_id(setup.create(examiner_member_id=str(other)))
    changed = setup.centre.client.put(
        f"/v1/exams/{exam_id}/examiner",
        json={"examiner_member_id": str(setup.member)},
        headers=setup.centre.headers(),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["examiner_member_id"] == str(setup.member)
    read = setup.centre.client.get(
        f"/v1/exams/{exam_id}", headers=setup.centre.headers()
    )
    assert read.status_code == 200, read.text
    assert (read.json()["examiner_member_id"], read.json()["examiner_name"]) == (
        str(setup.member),
        "Sumi",
    )
    cleared = setup.centre.client.put(
        f"/v1/exams/{exam_id}/examiner",
        json={"examiner_member_id": None},
        headers=setup.centre.headers(),
    )
    assert cleared.json()["examiner_member_id"] is None


def test_only_a_live_member_of_this_centre_can_examine(
    setup: Setup, api_client: TestClient, owner_session: Session
) -> None:
    """A stranger's or a revoked membership is refused."""
    elsewhere = Centre(api_client, owner_session)
    stranger = _teacher(elsewhere, _account(owner_session))
    revoked = _teacher(
        setup.centre,
        _account(owner_session),
        revoked_at=dt.datetime.now(tz=dt.UTC),
    )
    for member in (stranger, revoked):
        response = setup.create(examiner_member_id=str(member))
        assert response.status_code == 400, response.text  # type: ignore[attr-defined]
        assert _code(response) == "SCHEDULE_TEACHER_UNKNOWN"


def test_a_solo_tutor_names_no_examiner(
    api_client: TestClient, owner_session: Session
) -> None:
    """A solo exam has no examiner field set, and refuses one."""
    tutor = make_teacher(owner_session)
    subject = owner_session.scalars(
        sa.select(BatchSubject.id).where(BatchSubject.batch_id == tutor.batch_id)
    ).first()
    if subject is None:
        owner_session.add(BatchSubject(batch_id=tutor.batch_id, name="Physics"))
        owner_session.commit()
        subject = owner_session.scalars(
            sa.select(BatchSubject.id).where(BatchSubject.batch_id == tutor.batch_id)
        ).one()
    body = {
        "batch_subject_id": str(subject),
        "title": "Test",
        "date": bangladesh_today().isoformat(),
        "total_marks": 10,
    }
    plain = api_client.post(
        f"/v1/batches/{tutor.batch_id}/exams",
        json=body,
        headers=bearer(owner_session, tutor.account_id),
    )
    assert plain.status_code == 201, plain.text
    assert plain.json()["examiner_member_id"] is None
    named = api_client.post(
        f"/v1/batches/{tutor.batch_id}/exams",
        json={**body, "examiner_member_id": str(uuid.uuid4())},
        headers=bearer(owner_session, tutor.account_id),
    )
    assert named.status_code == 409, named.text
    assert _code(named) == "NOT_A_CENTRE"


def test_the_examiner_enters_and_publishes_the_marks(setup: Setup) -> None:
    """Names and marks only; the published exam reaches families."""
    exam_id = _exam_id(setup.create())
    listed = setup.centre.client.get("/v1/me/exams", headers=setup.teacher_headers())
    assert [e["exam_id"] for e in listed.json()] == [exam_id]

    results = setup.centre.client.get(
        f"/v1/me/exams/{exam_id}/results", headers=setup.teacher_headers()
    )
    assert results.status_code == 200, results.text
    assert [set(r) for r in results.json()["results"]] == [
        {"enrollment_id", "display_name", "result_state", "marks"}
    ]

    mark = setup.centre.client.post(
        f"/v1/me/exams/{exam_id}/marks",
        json={"enrollment_id": str(setup.seat), "result_state": "marked", "marks": 72},
        headers=setup.teacher_headers(),
    )
    assert mark.status_code == 204, mark.text
    published = setup.centre.client.post(
        f"/v1/me/exams/{exam_id}/publish", headers=setup.teacher_headers()
    )
    assert published.status_code == 204, published.text
    setup.centre.session.expire_all()
    exam = setup.centre.session.get(Exam, uuid.UUID(exam_id))
    assert exam is not None and exam.published_at is not None


def test_a_teacher_who_is_not_the_examiner_is_told_so(setup: Setup) -> None:
    """Another member of the centre, or a moved examiner, gets EXAM_REASSIGNED."""
    other = _teacher(setup.centre, _account(setup.centre.session))
    exam_id = _exam_id(setup.create(examiner_member_id=str(other)))
    response = setup.centre.client.post(
        f"/v1/me/exams/{exam_id}/marks",
        json={"enrollment_id": str(setup.seat), "result_state": "absent"},
        headers=setup.teacher_headers(),
    )
    assert response.status_code == 409, response.text
    assert _code(response) == "EXAM_REASSIGNED"
    assert (
        setup.centre.client.get("/v1/me/exams", headers=setup.teacher_headers()).json()
        == []
    )


def test_a_stranger_reads_the_same_as_a_missing_exam(
    setup: Setup, api_client: TestClient, owner_session: Session
) -> None:
    """A teacher at another centre is refused with the shared code."""
    exam_id = _exam_id(setup.create())
    elsewhere = Centre(api_client, owner_session)
    outsider = _account(owner_session)
    _teacher(elsewhere, outsider)
    for path in (
        f"/v1/me/exams/{exam_id}/results",
        f"/v1/me/exams/{uuid.uuid4()}/results",
    ):
        response = api_client.get(path, headers=bearer(owner_session, outsider))
        assert response.status_code == 403, (path, response.text)
        assert _code(response) == "NO_EXAM_LENS"


def test_the_examiner_reaches_no_teacher_exam_route(setup: Setup) -> None:
    """The manager's exam routes stay closed to them."""
    exam_id = _exam_id(setup.create())
    headers = setup.teacher_headers()
    headers["X-Workspace-Id"] = str(setup.centre.owner_id)
    for path in (f"/v1/exams/{exam_id}/results", f"/v1/batches/{setup.batch}/exams"):
        response = setup.centre.client.get(path, headers=headers)
        assert response.status_code == 403, (path, response.text)


def test_removing_the_teacher_clears_them_from_unpublished_exams(setup: Setup) -> None:
    """A published exam keeps its examiner as the record of who marked it."""
    open_exam = _exam_id(setup.create(title="Open"))
    done = _exam_id(setup.create(title="Done"))
    setup.centre.session.execute(
        sa.update(Exam)
        .where(Exam.id == uuid.UUID(done))
        .values(published_at=dt.datetime.now(tz=dt.UTC))
    )
    setup.centre.session.commit()
    revoked = setup.centre.client.post(
        f"/v1/centre/members/{setup.member}/revoke", headers=setup.centre.headers()
    )
    assert revoked.status_code == 204, revoked.text
    setup.centre.session.expire_all()
    examiners = {
        str(row.id): row.examiner_member_id
        for row in setup.centre.session.scalars(sa.select(Exam))
    }
    assert examiners == {open_exam: None, done: setup.member}
    member = setup.centre.session.get(OwnerMember, setup.member)
    assert member is not None and member.revoked_at is not None
