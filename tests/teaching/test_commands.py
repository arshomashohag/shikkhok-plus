"""The session job registers its OWN heartbeat [observability § 4.1].

**A shared job name would let a healthy fee run mask a session job that
has never fired**, and the masking would be total because session
generation self-heals: nothing looks wrong until a teacher opens the app
and there is no class to mark attendance against.

So the decisive assertion here is not "a heartbeat exists" but "a
heartbeat exists under the SESSION job's name, and the fee job's row is
untouched".
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.db.models import FEE_GENERATION_JOB, SESSION_GENERATION_JOB, JobHeartbeat
from app.fees.commands import check_all_jobs
from app.teaching.commands import run_session_generation
from tests.batches.conftest import TeacherFixture

IN_FEBRUARY = dt.date(2027, 2, 7)
NOW = dt.datetime(2027, 2, 7, 1, 0, tzinfo=dt.UTC)


def test_the_run_stamps_a_heartbeat_under_the_session_job_name(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    run_session_generation(restricted_session, today=IN_FEBRUARY, now=NOW)

    row = restricted_session.scalars(
        sa.select(JobHeartbeat).where(JobHeartbeat.job_name == SESSION_GENERATION_JOB)
    ).one_or_none()
    assert row is not None, (
        "the session job wrote no heartbeat, so the freshness check has "
        "nothing to read and a job that stops firing is silent"
    )
    assert row.last_success_at == NOW
    assert row.cycles_created == 9


def test_the_session_job_does_not_write_the_fee_jobs_row(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    run_session_generation(restricted_session, today=IN_FEBRUARY, now=NOW)

    fee_row = restricted_session.scalars(
        sa.select(JobHeartbeat).where(JobHeartbeat.job_name == FEE_GENERATION_JOB)
    ).one_or_none()
    assert fee_row is None, (
        "the session job stamped the FEE job's heartbeat: the two jobs "
        "would then mask each other's silence [NFR1.8]"
    )


def test_a_run_that_creates_nothing_still_stamps(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    # Unconditional on OUTCOME, conditional only on COMPLETION. Over a
    # two-month horizon almost every run creates nothing, and stamping
    # only on `created > 0` would leave the row stale during entirely
    # correct operation and fire the 48-hour alert constantly.
    run_session_generation(restricted_session, today=IN_FEBRUARY, now=NOW)
    later = NOW + dt.timedelta(days=1)

    result = run_session_generation(restricted_session, today=IN_FEBRUARY, now=later)

    assert result.sessions_created == 0
    row = restricted_session.scalars(
        sa.select(JobHeartbeat).where(JobHeartbeat.job_name == SESSION_GENERATION_JOB)
    ).one()
    assert row.last_success_at == later


def test_the_freshness_check_sees_the_session_job(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    monday_slot: uuid.UUID,
) -> None:
    # The end of the chain the infrastructure finding was about: the
    # row is written AND something reads it.
    run_session_generation(restricted_session, today=IN_FEBRUARY, now=NOW)

    verdicts = dict(check_all_jobs(restricted_session, now=NOW))
    assert SESSION_GENERATION_JOB in verdicts
    assert verdicts[SESSION_GENERATION_JOB].healthy is True
