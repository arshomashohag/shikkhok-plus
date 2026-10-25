"""The job, the heartbeat and the freshness check [NFR25.9, NFR26.3].

**The zero-cycles case is the one that decides whether the alert is
usable**, and it is the common case rather than the edge. Generation is
monthly, so on most days of most months a run starts, finds nothing due
and ends. A heartbeat written only when ``cycles_created > 0`` would
leave the row stale for weeks during correct operation, fire the
48-hour alert constantly, and get it muted -- reaching the alert's own
failure mode by the opposite route.

**The no-row branch is the one a naive query swallows.**
``SELECT ... WHERE job_name = ...`` returning zero rows is falsy in most
shapes a developer would write, so "alert if staleness > 48 hours"
treats *never ran* as *fine* -- which is exactly the
scheduler-was-never-wired failure the alert exists to catch. All three
branches of § 1.2 are asserted here.

**Time is injected throughout.** The staleness arithmetic is testable
precisely because the comparison moment is a parameter.
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.models import FEE_GENERATION_JOB, JobHeartbeat
from app.fees.commands import (
    STALENESS_THRESHOLD,
    check_generation_freshness,
    run_generation,
    stamp_heartbeat,
)
from app.fees.generation import GenerationResult
from app.money import Money
from tests.batches.conftest import TeacherFixture
from tests.fees.conftest import set_decision, set_joined_on

IN_FEBRUARY = dt.date(2027, 2, 20)
AT_NOON = dt.datetime(2027, 2, 20, 12, 0, tzinfo=dt.UTC)


def _heartbeat(session: Session) -> JobHeartbeat | None:
    """Read the generation job's heartbeat row.

    :param session: The session to read through
    :return: The row, or None
    """
    return session.scalars(
        sa.select(JobHeartbeat).where(JobHeartbeat.job_name == FEE_GENERATION_JOB)
    ).one_or_none()


# ---------------------------------------------------------------------
# The command runs end to end.
# ---------------------------------------------------------------------


def test_the_command_generates_and_stamps(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    result = run_generation(restricted_session, today=IN_FEBRUARY, now=AT_NOON)

    assert result.cycles_created == 1

    row = _heartbeat(restricted_session)
    assert row is not None
    assert row.last_success_at == AT_NOON
    assert row.cycles_created == 1
    assert row.cycles_skipped == 0
    assert row.periods_failed == 0


def test_a_run_that_finds_nothing_due_still_stamps(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # THE CASE THAT MAKES THE ALERT USABLE. The seat joins in May, so a
    # February run has nothing to do -- which is correct operation, not
    # a failure, and the row must advance with an honest zero.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 5, 1))

    result = run_generation(restricted_session, today=IN_FEBRUARY, now=AT_NOON)

    assert result.cycles_created == 0

    row = _heartbeat(restricted_session)
    assert row is not None, (
        "a run that found nothing due wrote no heartbeat. Generation is "
        "monthly, so this is most days of most months: the row would go "
        "stale during correct operation and the 48-hour alert would be "
        "muted [observability-design § 1.1a]"
    )
    assert row.last_success_at == AT_NOON
    assert row.cycles_created == 0


def test_an_empty_database_still_stamps(
    restricted_session: Session,
) -> None:
    # No enrollments at all -- the state on the day the table is
    # created. "Nothing was due" and "nothing ran" are different facts
    # and the row must distinguish them from the first run onward.
    run_generation(restricted_session, today=IN_FEBRUARY, now=AT_NOON)

    row = _heartbeat(restricted_session)
    assert row is not None
    assert row.cycles_created == 0


def test_a_second_run_updates_the_row_in_place(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # One row per job name, updated in place. An append-only run log
    # would answer the same question and grow unboundedly for a value
    # only ever read as its maximum.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    run_generation(restricted_session, today=IN_FEBRUARY, now=AT_NOON)
    later = AT_NOON + dt.timedelta(days=1)
    run_generation(restricted_session, today=dt.date(2027, 2, 21), now=later)

    rows = restricted_session.execute(
        sa.text("SELECT count(*) FROM job_heartbeat")
    ).scalar_one()
    assert rows == 1

    row = _heartbeat(restricted_session)
    assert row is not None
    assert row.last_success_at == later
    # The second run conflicted rather than creating, and the counts
    # describe THAT run rather than accumulating.
    assert row.cycles_created == 0
    assert row.cycles_skipped == 1


def test_the_heartbeat_records_a_partially_failed_run(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # A run that generated some and failed others DID succeed at the
    # ones it generated, so it stamps -- carrying the failure count for
    # the person who then looks.
    from tests.fees.conftest import enroll, set_batch_fee

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

    run_generation(restricted_session, today=IN_FEBRUARY, now=AT_NOON)

    row = _heartbeat(restricted_session)
    assert row is not None
    assert row.cycles_created == 1
    assert row.periods_failed == 1
    assert row.last_success_at == AT_NOON


def test_the_run_voids_a_declined_seat(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The mirror operation runs inside the same command, so a decline
    # recorded while the job was down is reversed on the next run
    # rather than never.
    from app.fees.balances import derive_for_enrollment

    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    run_generation(restricted_session, today=IN_FEBRUARY, now=AT_NOON)

    set_decision(owner_session, enrollment_id=seat, student="declined")
    run_generation(restricted_session, today=dt.date(2027, 2, 21), now=AT_NOON)

    assert derive_for_enrollment(restricted_session, seat).total_outstanding == Money(
        "0.00"
    )


# ---------------------------------------------------------------------
# The three branches of the freshness check.
# ---------------------------------------------------------------------


def test_no_row_at_all_is_unhealthy(restricted_session: Session) -> None:
    # THE BRANCH A NAIVE QUERY SWALLOWS. Zero rows is falsy in most
    # shapes a developer would write, so "alert if stale" reports
    # healthy here -- and never-ran is the scheduler-never-wired
    # failure the alert exists for.
    verdict = check_generation_freshness(restricted_session, now=AT_NOON)

    assert verdict.healthy is False
    assert verdict.reason == "never_ran"
    assert verdict.staleness is None


def test_a_fresh_row_is_healthy(restricted_session: Session) -> None:
    stamp_heartbeat(
        restricted_session,
        result=GenerationResult(cycles_created=0, cycles_skipped=0, periods_failed=0),
        now=AT_NOON,
    )

    verdict = check_generation_freshness(
        restricted_session, now=AT_NOON + dt.timedelta(hours=1)
    )

    assert verdict.healthy is True
    assert verdict.reason == "fresh"


def test_a_stale_row_is_unhealthy(restricted_session: Session) -> None:
    stamp_heartbeat(
        restricted_session,
        result=GenerationResult(cycles_created=0, cycles_skipped=0, periods_failed=0),
        now=AT_NOON,
    )

    verdict = check_generation_freshness(
        restricted_session, now=AT_NOON + dt.timedelta(hours=49)
    )

    assert verdict.healthy is False
    assert verdict.reason == "stale"
    assert verdict.staleness is not None
    assert verdict.staleness >= STALENESS_THRESHOLD


def test_the_threshold_boundary_is_two_missed_runs(
    restricted_session: Session,
) -> None:
    # 48 hours, derived as two missed daily runs -- the shortest window
    # that does not page on a single transient failure the next run
    # would heal. One minute under is still healthy; exactly at it is
    # not, so the boundary is asserted rather than assumed.
    stamp_heartbeat(
        restricted_session,
        result=GenerationResult(cycles_created=0, cycles_skipped=0, periods_failed=0),
        now=AT_NOON,
    )

    just_under = check_generation_freshness(
        restricted_session,
        now=AT_NOON + STALENESS_THRESHOLD - dt.timedelta(minutes=1),
    )
    exactly_at = check_generation_freshness(
        restricted_session, now=AT_NOON + STALENESS_THRESHOLD
    )

    assert just_under.healthy is True
    assert exactly_at.healthy is False
    assert STALENESS_THRESHOLD == dt.timedelta(hours=48)


def test_a_run_makes_the_check_healthy_again(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The recovery path end to end: the alert fires, a person runs the
    # command by hand, and the check goes quiet.
    assert check_generation_freshness(restricted_session, now=AT_NOON).healthy is (
        False
    )

    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    run_generation(restricted_session, today=IN_FEBRUARY, now=AT_NOON)

    assert check_generation_freshness(restricted_session, now=AT_NOON).healthy is (True)


def test_the_entry_point_dispatches_to_generate(
    monkeypatch: pytest.MonkeyPatch,
    restricted_engine: Engine,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # **The entry point is the recovery procedure**, so it is tested as
    # one rather than left to the cron entry. It is reached with no
    # arguments, by requirement: a person who sees the alert must have
    # no flags to get wrong.
    from app.fees import commands

    monkeypatch.setattr(sys, "argv", ["app.fees.commands"])
    monkeypatch.setattr(commands, "build_engine", lambda: restricted_engine)
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    assert commands.main() == 0

    with Session(restricted_engine) as check:
        row = check.scalars(
            sa.select(JobHeartbeat).where(JobHeartbeat.job_name == FEE_GENERATION_JOB)
        ).one_or_none()
    assert row is not None


def test_the_entry_point_dispatches_to_the_freshness_check(
    monkeypatch: pytest.MonkeyPatch,
    restricted_engine: Engine,
) -> None:
    # Non-zero when unhealthy, so a wrapper or a human reading an exit
    # status learns the same thing the log line says.
    from app.fees import commands

    monkeypatch.setattr(sys, "argv", ["app.fees.commands", "check-freshness"])
    monkeypatch.setattr(commands, "build_engine", lambda: restricted_engine)

    assert commands.main() == 1


def test_an_unknown_verb_is_refused_rather_than_defaulted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A typo in the crontab must not silently run generation. Exit 2
    # rather than 0, so a wrapper notices.
    from app.fees import commands

    monkeypatch.setattr(sys, "argv", ["app.fees.commands", "genrate"])

    assert commands.main() == 2


def test_the_check_is_scoped_to_its_job_name(
    restricted_session: Session,
) -> None:
    # A heartbeat for a different job must not make this one look
    # healthy. D4 adds its own job and this is the row that would
    # otherwise silence the fee alert.
    stamp_heartbeat(
        restricted_session,
        result=GenerationResult(cycles_created=0, cycles_skipped=0, periods_failed=0),
        job_name="some_other_job",
        now=AT_NOON,
    )

    verdict = check_generation_freshness(restricted_session, now=AT_NOON)

    assert verdict.healthy is False
    assert verdict.reason == "never_ran"
