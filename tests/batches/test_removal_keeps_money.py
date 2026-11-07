"""Removing a seat never destroys money or teaching history [audit C-02].

A pending seat is the normal state of a seat: it is charged every month
and a teacher can record cash against it before anyone accepts. Removal
used to check only acceptance and erasure, then ``session.delete`` the
row, and the ``ON DELETE CASCADE`` from ``enrollment`` took the receipts,
credits, claims, attendance and marks with it. ``0015`` revoked
``DELETE`` on ``ledger_entry`` from the application role, but a
referential action runs as the table owner, so the revoke never applied
to the cascade.

Two layers now refuse: the service, with a message the teacher can act
on, and a ``BEFORE DELETE`` trigger on ``enrollment``, so a future code
path that deletes a seat directly is refused by the database as well.

What may still go is a seat whose only rows are generated charges and
forgiveness of them: a seat typed on the wrong number and removed before
anything happened on it. Nothing a person paid, recorded or was owed as
credit is lost.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import EnrollmentNotRemovable, remove_enrollment
from app.db.models import Enrollment, LedgerEntryRow
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the lens the service requires.

    :param teacher: The teacher to build a lens for
    :return: That teacher's lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _pending_seat(owner_session: Session, teacher: TeacherFixture) -> uuid.UUID:
    """Create a seat nobody has accepted.

    :param owner_session: An arranging session
    :param teacher: The owning teacher
    :return: The seat's id
    """
    return enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Pending",
        student_decision="pending",
        guardian_decision="pending",
    )


def _ledger(
    owner_session: Session,
    enrollment_id: uuid.UUID,
    *,
    kind: str,
    created_by: uuid.UUID | None,
) -> uuid.UUID:
    """Append one ledger row for a seat.

    :param owner_session: An arranging session
    :param enrollment_id: The seat
    :param kind: The ledger kind
    :param created_by: Who caused it, or None for the generation job
    :return: The row's id
    """
    row = LedgerEntryRow(
        enrollment_id=enrollment_id,
        period="2026-10",
        kind=kind,
        amount=Money("500.00"),
        created_by_account_id=created_by,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(row)
    owner_session.commit()
    return row.id


@pytest.mark.parametrize(
    "kind", ["receipt", "credit_grant", "credit_apply", "carry_forward"]
)
def test_a_pending_seat_with_money_movement_is_refused(
    restricted_session: Session, owner_session: Session, kind: str
) -> None:
    """Cash and credit on a pending seat survive a removal attempt.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param kind: A ledger kind that records money moving
    :return: None
    """
    teacher = make_teacher(owner_session)
    seat = _pending_seat(owner_session, teacher)
    _ledger(owner_session, seat, kind="charge", created_by=None)
    entry = _ledger(owner_session, seat, kind=kind, created_by=teacher.account_id)

    with pytest.raises(EnrollmentNotRemovable) as refusal:
        remove_enrollment(restricted_session, lens=_lens(teacher), enrollment_id=seat)

    assert refusal.value.code == "ENROLLMENT_HAS_HISTORY"
    assert refusal.value.message_key == "enrollment.remove.has_history"
    restricted_session.rollback()
    assert restricted_session.get(Enrollment, seat) is not None
    assert restricted_session.get(LedgerEntryRow, entry) is not None


def test_a_seat_with_only_generated_charges_is_still_removable(
    restricted_session: Session, owner_session: Session
) -> None:
    """A mistyped seat removed before anything happened on it goes.

    Generated charges and their forgiveness are not anyone's history;
    refusing them would block the recovery path removal exists for.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    seat = _pending_seat(owner_session, teacher)
    _ledger(owner_session, seat, kind="charge", created_by=None)
    _ledger(owner_session, seat, kind="forgiveness", created_by=teacher.account_id)

    remove_enrollment(restricted_session, lens=_lens(teacher), enrollment_id=seat)

    assert restricted_session.get(Enrollment, seat) is None


def test_the_database_refuses_a_direct_delete_of_a_seat_with_cash(
    restricted_session: Session, owner_session: Session
) -> None:
    """The trigger is the backstop for a path that skips the service.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    seat = _pending_seat(owner_session, teacher)
    _ledger(owner_session, seat, kind="receipt", created_by=teacher.account_id)

    with pytest.raises(DBAPIError) as refusal:
        restricted_session.execute(sa.delete(Enrollment).where(Enrollment.id == seat))
    assert "enrollment_has_history" in str(refusal.value)
    restricted_session.rollback()

    count = owner_session.scalar(
        sa.select(sa.func.count())
        .select_from(LedgerEntryRow)
        .where(LedgerEntryRow.enrollment_id == seat)
    )
    assert count == 1


def test_the_database_allows_a_direct_delete_of_a_charge_only_seat(
    restricted_session: Session, owner_session: Session
) -> None:
    """The trigger does not block the one removal that must work.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    seat = _pending_seat(owner_session, teacher)
    _ledger(owner_session, seat, kind="charge", created_by=None)

    restricted_session.execute(sa.delete(Enrollment).where(Enrollment.id == seat))
    restricted_session.commit()

    assert owner_session.get(Enrollment, seat) is None


def test_the_service_and_the_trigger_name_the_same_kinds() -> None:
    """Two statements of one rule must not drift apart.

    :return: None
    """
    import importlib.util
    from pathlib import Path

    from app.batches.service import MONEY_MOVEMENT_KINDS

    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "0029_seat_history_and_supersession_index.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0027", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert set(migration.MONEY_MOVEMENT_KINDS) == MONEY_MOVEMENT_KINDS
