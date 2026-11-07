"""The queue reads only what it shows, and still finds every repeat [C-13].

The queue used to load every submission a teacher ever received and
filter in Python. It now asks the database for waiting ones and the last
day's decisions, looks up repeated references with a targeted query, and
prefetches each review's figures for all reviews at once. Each of those
is a place a narrower read could silently drop something the old one
found, so each is pinned here:

* a repeat of a payment decided **long ago**, outside the recent window,
  is still flagged, and the flag names the EARLIEST such payment;
* a reference typed with different case, ASCII spaces, a control
  whitespace or a non-ASCII character matches exactly as
  ``_reference`` normalises it -- no more, no less;
* the single-payment review (R2) names the same earlier payment;
* the count and the preview agree with the full queue;
* a statement over more ids than PostgreSQL's 65,535 bind parameters
  still runs, because ids travel as one array.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import StudentLens, TeacherLens
from app.db.models import PaymentSubmission
from app.fees.decisions import approve_submission
from app.fees.queue import (
    covered_children,
    payment_review,
    pending_count,
    pending_preview,
    verification_queue,
)
from app.money import Money
from tests.batches.conftest import TeacherFixture
from tests.fees.test_verification_queue import _lens, _pay, _student_seat


def _approve(
    session: Session, teacher: TeacherFixture, submission_id: uuid.UUID
) -> None:
    """Approve a payment in full.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param submission_id: The payment
    :return: None
    """
    approve_submission(
        session,
        lens=_lens(teacher),
        submission_id=submission_id,
        received=Money("1200.00"),
        disposition=None,
        carried_by_enrollment_id=None,
        credit_to_enrollment_id=None,
        note=None,
    )


def _age(session: Session, submission_id: uuid.UUID, days: int) -> None:
    """Move a payment's report and decision into the past.

    :param session: An arranging session
    :param submission_id: The payment
    :param days: How many days back
    :return: None
    """
    back = dt.timedelta(days=days)
    session.execute(
        sa.update(PaymentSubmission)
        .where(PaymentSubmission.id == submission_id)
        .values(
            submitted_at=PaymentSubmission.submitted_at - back,
            decided_at=PaymentSubmission.decided_at - back,
        )
    )
    session.commit()


def test_a_repeat_of_a_long_decided_payment_names_the_earliest(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Two old approvals quote the reference; the waiting one names the first.

    Both earlier payments were decided weeks ago, so neither is in the
    queue's own read: the duplicate lookup must reach them on its own.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    payers = []
    for name, days in (("Asha", 40), ("Bilal", 20)):
        student = account_factory()
        seat = _student_seat(owner_session, teacher, name, student)
        paid = _pay(
            owner_session,
            teacher,
            StudentLens(account_id=student),
            [seat],
            "1200.00",
            "BK 77 ab",
        )
        _approve(owner_session, teacher, paid.id)
        _age(owner_session, paid.id, days)
        payers.append(paid.id)
    student = account_factory()
    seat = _student_seat(owner_session, teacher, "Chaya", student)
    waiting = _pay(
        owner_session,
        teacher,
        StudentLens(account_id=student),
        [seat],
        "1200.00",
        "bk77AB",
    )

    queue = verification_queue(restricted_session, lens=_lens(teacher))

    [item] = queue.pending
    assert queue.decided_recently == []
    assert item.duplicate_of is not None
    assert item.duplicate_of.submission_id == payers[0]
    assert item.duplicate_of.display_name == "Asha"
    single = payment_review(
        restricted_session, lens=_lens(teacher), submission_id=waiting.id
    )
    assert single.duplicate_of == item.duplicate_of
    # The earliest repeats nothing; the second names the first.
    second = payment_review(
        restricted_session, lens=_lens(teacher), submission_id=payers[1]
    )
    assert second.duplicate_of is not None
    assert second.duplicate_of.submission_id == payers[0]
    first = payment_review(
        restricted_session, lens=_lens(teacher), submission_id=payers[0]
    )
    assert first.duplicate_of is None


def test_references_match_exactly_as_they_are_normalised(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Control whitespace and non-ASCII references match by Python's rules.

    A tab inside ``tx 9ß`` is dropped and ``ß`` upper-cases to ``SS``,
    so it normalises to ``TX9SS`` -- which the database's own ``upper``
    would not produce; ``"TX9S"`` is a near miss that must not match.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    quoted = {}
    for name, reference in (
        ("Dipu", "tx\t9ß"),
        ("Esha", "TX9S"),
        ("Faruk", "TX9SS"),
        ("Gias", "TX 9 S"),
    ):
        student = account_factory()
        seat = _student_seat(owner_session, teacher, name, student)
        quoted[name] = _pay(
            owner_session,
            teacher,
            StudentLens(account_id=student),
            [seat],
            "1200.00",
            reference,
        ).id

    found = {
        item.submission_id: item.duplicate_of
        for item in verification_queue(restricted_session, lens=_lens(teacher)).pending
    }

    assert found[quoted["Dipu"]] is None
    assert found[quoted["Esha"]] is None
    faruk = found[quoted["Faruk"]]
    assert faruk is not None
    assert faruk.submission_id == quoted["Dipu"]
    gias = found[quoted["Gias"]]
    assert gias is not None
    assert gias.submission_id == quoted["Esha"]


def test_the_count_and_the_preview_agree_with_the_queue(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The badge's count is the queue's length; the preview is its head.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    for index, name in enumerate(("Hena", "Imran", "Jui", "Kamal")):
        student = account_factory()
        seat = _student_seat(owner_session, teacher, name, student)
        paid = _pay(
            owner_session,
            teacher,
            StudentLens(account_id=student),
            [seat],
            "1200.00",
            f"TX-{index}",
        )
        if name == "Imran":
            _approve(owner_session, teacher, paid.id)

    lens: TeacherLens = _lens(teacher)
    queue = verification_queue(restricted_session, lens=lens)

    assert len(queue.pending) == 3
    assert pending_count(restricted_session, lens=lens) == 3
    assert pending_preview(restricted_session, lens=lens, limit=2) == queue.pending[:2]
    assert pending_preview(restricted_session, lens=lens, limit=10) == queue.pending


def test_ids_beyond_the_bind_parameter_ceiling_still_read(
    restricted_session: Session,
) -> None:
    """Seventy thousand submission ids are one array, not 70,000 binds.

    An ``IN`` list of this size is refused by PostgreSQL's wire protocol
    (65,535 parameters at most), which is how a centre's queue would
    have failed permanently once its history grew past it.

    :param restricted_session: The application-role session
    :return: None
    """
    ids = [uuid.uuid4() for _ in range(70_000)]

    assert covered_children(restricted_session, ids) == {}
