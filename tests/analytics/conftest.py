"""Fixtures for D5, shaped so a correct-looking implementation fails.

**Two of these exist to defeat a specific wrong implementation**, and
each says which:

* :func:`add_batch` lets a test grow **batches per teacher** rather than
  seats per batch. D3's query-count test grows seats inside one batch,
  which passes against a per-batch loop -- and a per-batch loop is
  exactly what D5's cross-batch read invites [BR1.6].
* :func:`seat_with_ledger` writes entries through the built
  ``append_entry``, so a fixture cannot produce a row shape the
  application never writes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from app.authz.lenses import TeacherLens
from app.db.models import Batch, BatchSubject, Exam
from app.fees.ledger_writer import append_entry
from app.money import Money
from tests.batches.conftest import TeacherFixture, _account, enroll, make_teacher


def add_batch(session: Session, owner_id: uuid.UUID, name: str) -> uuid.UUID:
    """Add one more batch to an existing owner.

    ``make_teacher`` creates a teacher **and one batch**, so it cannot
    express "the same teacher with five batches" -- which is the axis
    D5's statement-count property has to grow along [BR1.6].

    :param session: An arranging session
    :param owner_id: The owner the batch hangs from
    :param name: The batch's name
    :return: The new batch's id
    """
    batch = Batch(
        owner_id=owner_id,
        name=name,
        default_fee=Money("1000.00"),
        fee_due_day=10,
        marksheet_visible=True,
        active=True,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(batch)
    session.commit()
    return batch.id


def seat_with_ledger(
    owner_session: Session,
    restricted_session: Session,
    *,
    batch_id: uuid.UUID,
    display_name: str,
    entries: list[tuple[str, str, str]],
    inactive_from: dt.date | None = None,
    student_decision: str = "accepted",
) -> uuid.UUID:
    """Create one seat and append the entries it carries.

    ``entries`` is a list of ``(kind, period, amount)`` triples, written
    through the built ``append_entry`` so no fixture can produce a row
    the application would never write.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session the entries are written on
    :param batch_id: The batch the seat belongs to
    :param display_name: The teacher-typed name
    :param entries: ``(kind, period, amount)`` triples
    :param inactive_from: When the seat went inactive, or None
    :param student_decision: The student link's decision
    :return: The new enrollment's id
    """
    seat = enroll(
        owner_session,
        batch_id=batch_id,
        display_name=display_name,
        student_account_id=_account(owner_session),
        student_decision=student_decision,
    )
    if inactive_from is not None:
        _set_inactive(owner_session, seat, inactive_from)

    for kind, period, amount in entries:
        append_entry(
            restricted_session,
            enrollment_id=seat,
            period=period,
            kind=kind,
            amount=Money(amount),
        )
    restricted_session.commit()
    return seat


def _set_inactive(session: Session, seat: uuid.UUID, when: dt.date) -> None:
    """Mark a seat inactive from a date.

    :param session: An arranging session
    :param seat: The enrollment
    :param when: The date the seat stops being active
    :return: None
    """
    from app.db.models import Enrollment

    record = session.get(Enrollment, seat)
    assert record is not None
    record.inactive_from = when
    session.commit()


def add_exam(
    session: Session,
    *,
    batch_id: uuid.UUID,
    title: str,
    date: dt.date,
    subject_name: str = "Physics",
    created_at: dt.datetime | None = None,
) -> uuid.UUID:
    """Create one exam with its subject, on a batch.

    :param session: An arranging session
    :param batch_id: The batch the exam sits on
    :param title: The teacher's name for it
    :param date: When it is sat
    :param subject_name: The subject assessed
    :param created_at: The creation stamp, for the BR3.3 tiebreaker
    :return: The exam's id
    """
    subject = BatchSubject(batch_id=batch_id, name=subject_name)
    session.add(subject)
    session.commit()

    exam = Exam(
        batch_id=batch_id,
        batch_subject_id=subject.id,
        title=title,
        date=date,
        total_marks=100,
        created_at=created_at or dt.datetime.now(tz=dt.UTC),
    )
    session.add(exam)
    session.commit()
    return exam.id


def lens_for(teacher: TeacherFixture) -> TeacherLens:
    """Build the teacher lens for a fixture.

    :param teacher: The teacher
    :return: Their lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


@pytest.fixture
def teacher(owner_session: Session) -> TeacherFixture:
    """One teacher with one batch.

    :param owner_session: A session able to arrange fixture data
    :return: The teacher
    """
    return make_teacher(owner_session, name="Physics")


@pytest.fixture
def other_teacher(owner_session: Session) -> TeacherFixture:
    """Build a second, unrelated teacher with a lens of their own.

    A VALID lens deliberately: an unauthenticated caller is refused one
    step earlier and proves nothing about a scoping boundary.

    :param owner_session: A session able to arrange fixture data
    :return: The second teacher
    """
    return make_teacher(owner_session, name="Chemistry")


@pytest.fixture
def client(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build a client whose app uses the RESTRICTED test engine.

    Restricted and not owner: a suite driven through an application
    connected as the table owner passes identically whether the row
    policy is correct, broken or absent [pg-rls].

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
def signed_in_teacher(owner_session: Session) -> TeacherFixture:
    """Build a teacher who will reach the routes over HTTP.

    :param owner_session: A session able to arrange fixture data
    :return: The teacher
    """
    return make_teacher(owner_session, name="Physics")


@pytest.fixture
def teacher_token(owner_session: Session, signed_in_teacher: TeacherFixture) -> str:
    """Issue an access token for the signed-in teacher.

    :param owner_session: The session the token family is written through
    :param signed_in_teacher: Whose token to issue
    :return: The bearer token
    """
    pair = issue_pair(
        owner_session,
        account_id=signed_in_teacher.account_id,
        correlation_id=uuid.uuid4(),
    )
    return pair.access_token


@pytest.fixture
def batch_factory(owner_session: Session) -> Callable[[uuid.UUID, str], uuid.UUID]:
    """Return a factory adding batches to an existing owner.

    :param owner_session: A session able to arrange fixture data
    :return: A callable taking ``(owner_id, name)``
    """

    def make(owner_id: uuid.UUID, name: str) -> uuid.UUID:
        return add_batch(owner_session, owner_id, name)

    return make
