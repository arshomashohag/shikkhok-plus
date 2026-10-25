"""Generation: one charge per seat per period, and a conflict is success.

**Written before `app/fees/generation.py` existed.** A wrong charge is a
money error and every expected value is knowable from BR1.1 and BR2.4
without having written the code, so the predicate holds.

**Against real PostgreSQL, never SQLite.** The unique constraint,
``ON CONFLICT DO NOTHING`` and ``NUMERIC(12,2)`` are the behaviours under
test and SQLite emulates none of them faithfully.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import FeeCycle, LedgerEntryRow
from app.fees.generation import generate_due_cycles
from app.money import Money
from tests.batches.conftest import TeacherFixture
from tests.fees.conftest import set_batch_fee, set_joined_on

#: A day inside the period under test, used as the injected "today" so
#: the run considers 2027-02 and nothing after it.
IN_FEBRUARY = dt.date(2027, 2, 20)


def _cycles(session: Session, enrollment_id: uuid.UUID) -> list[FeeCycle]:
    """Read every cycle for a seat, oldest first.

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: The cycle rows
    """
    return list(
        session.scalars(
            sa.select(FeeCycle)
            .where(FeeCycle.enrollment_id == enrollment_id)
            .order_by(FeeCycle.period)
        )
    )


def _entries(session: Session, enrollment_id: uuid.UUID) -> list[LedgerEntryRow]:
    """Read every ledger entry for a seat, oldest first.

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: The entry rows
    """
    return list(
        session.scalars(
            sa.select(LedgerEntryRow)
            .where(LedgerEntryRow.enrollment_id == enrollment_id)
            .order_by(LedgerEntryRow.period, LedgerEntryRow.created_at)
        )
    )


def test_one_charge_is_appended_at_the_resolved_fee(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    cycles = _cycles(restricted_session, seat)
    entries = _entries(restricted_session, seat)

    assert [cycle.period for cycle in cycles] == ["2027-02"]
    assert [(entry.kind, entry.amount) for entry in entries] == [
        ("charge", Money("1500.00"))
    ]


def test_the_seats_own_fee_overrides_the_batch_default(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: object,
) -> None:
    from tests.fees.conftest import enroll

    seat_id = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Karim",
        fee_amount=Money("750.00"),
        student_decision="accepted",
        guardian_decision="pending",
    )
    set_joined_on(owner_session, enrollment_id=seat_id, when=dt.date(2027, 2, 1))

    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    entries = _entries(restricted_session, seat_id)
    assert [entry.amount for entry in entries] == [Money("750.00")]


def test_a_zero_seat_fee_charges_zero_not_the_batch_default(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
) -> None:
    # [BR2.4] The falsiness defect, exercised end to end rather than
    # only in the pure resolver: a deliberate permanent waiver must not
    # become the batch's 1500.00.
    from tests.fees.conftest import enroll

    seat_id = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Waived",
        fee_amount=Money("0.00"),
        student_decision="accepted",
        guardian_decision="pending",
    )
    set_joined_on(owner_session, enrollment_id=seat_id, when=dt.date(2027, 2, 1))

    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    entries = _entries(restricted_session, seat_id)
    assert [entry.amount for entry in entries] == [Money("0.00")]


def test_the_cycle_carries_the_clamped_due_date(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Anchor 31 in a 28-day month. The stored anchor must NOT be
    # rewritten [BR2.2]: a degrading clamp would give every later month
    # the 28th for ever.
    set_batch_fee(
        owner_session,
        batch_id=teacher.batch_id,
        default_fee=Money("1500.00"),
        fee_due_day=31,
    )
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    cycles = _cycles(restricted_session, seat)
    assert [cycle.due_date for cycle in cycles] == [dt.date(2027, 2, 28)]

    stored_anchor = owner_session.execute(
        sa.text("SELECT fee_due_day FROM batch WHERE id = :id"),
        {"id": teacher.batch_id},
    ).scalar_one()
    assert stored_anchor == 31, (
        "the clamp rewrote the stored anchor; one short month would then "
        "move every future due date for this batch for ever [BR2.2]"
    )


def test_a_second_run_for_the_same_period_appends_nothing(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # [BR1.3] The conflict is the SUCCESS path. The second run must not
    # raise and must not append a second charge.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    generate_due_cycles(restricted_session, today=IN_FEBRUARY)
    first = _entries(restricted_session, seat)

    generate_due_cycles(restricted_session, today=IN_FEBRUARY)
    second = _entries(restricted_session, seat)

    assert len(first) == 1
    assert [entry.id for entry in second] == [entry.id for entry in first]
    assert len(_cycles(restricted_session, seat)) == 1


def test_the_conflicting_run_reports_the_skip_rather_than_failing(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    first = generate_due_cycles(restricted_session, today=IN_FEBRUARY)
    second = generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    assert first.cycles_created == 1
    assert first.cycles_skipped == 0
    assert second.cycles_created == 0
    assert second.cycles_skipped == 1
    assert second.periods_failed == 0


def test_generation_charges_every_period_since_joining(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The range is inclusive at both ends, which is what lets a missed
    # day heal rather than leave a permanent hole [BR1.4].
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2026, 12, 5))

    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    cycles = _cycles(restricted_session, seat)
    assert [cycle.period for cycle in cycles] == ["2026-12", "2027-01", "2027-02"]
    assert len(_entries(restricted_session, seat)) == 3


def test_a_future_period_is_not_generated(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 5, 1))

    result = generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    assert _cycles(restricted_session, seat) == []
    assert result.cycles_created == 0


def test_a_seat_on_an_inactive_batch_does_not_generate(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    owner_session.execute(
        sa.text("UPDATE batch SET active = false WHERE id = :id"),
        {"id": teacher.batch_id},
    )
    owner_session.commit()

    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    assert _cycles(restricted_session, seat) == []


def test_a_batch_with_no_fee_anywhere_is_counted_as_failed_not_charged(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # [BR2.4] Neither the seat nor the batch names a fee. Charging zero
    # would be indistinguishable from a waiver on an append-only
    # ledger, so the enrollment-period is skipped and counted --
    # **and the run continues**, which is the per-enrollment commit
    # boundary doing its job [NFR19.8].
    set_batch_fee(owner_session, batch_id=teacher.batch_id, default_fee=None)
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    result = generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    assert _cycles(restricted_session, seat) == []
    assert result.periods_failed >= 1


def test_one_unresolvable_seat_does_not_abort_the_run(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # [NFR19.8] One bad row must not cost every other seat its cycle.
    # The broken seat sets no fee and its batch has none; the healthy
    # one carries its own.
    from tests.fees.conftest import enroll

    set_batch_fee(owner_session, batch_id=teacher.batch_id, default_fee=None)
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    healthy = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Healthy",
        fee_amount=Money("900.00"),
        student_decision="accepted",
        guardian_decision="pending",
    )
    set_joined_on(owner_session, enrollment_id=healthy, when=dt.date(2027, 2, 1))

    result = generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    assert [entry.amount for entry in _entries(restricted_session, healthy)] == [
        Money("900.00")
    ]
    assert _cycles(restricted_session, seat) == []
    assert result.cycles_created == 1
    assert result.periods_failed == 1
