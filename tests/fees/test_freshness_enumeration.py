"""The freshness check reads EVERY registered job [infra § 3.3, option B].

**The finding this closes is that the mechanism was parameterised at the
function level and hardcoded at the entry point.** ``stamp_heartbeat``
and ``check_generation_freshness`` both take ``job_name``;
``main_check_freshness`` called with no argument and logged
``FEE_GENERATION_JOB`` regardless. So a session job writing a heartbeat
under a new name would have had its row written and **nothing would read
it** -- the freshness service keeps checking the fee job, keeps
returning healthy, and a session job that never fires produces no signal
at all.

**The decisive test is the one with two jobs in disagreement.** A check
that reads the first row it finds passes every single-job test, and
passes a two-job test where both are stale, and passes one where both
are fresh. Only "fee fresh, session stale" distinguishes an enumerating
checker from one that stops at the first row [§ 4.6].

**The empty-registry case is this suite's addition.** The design
specifies enumeration and does not state what zero rows means. A loop
whose body never runs returns healthy by default, which reintroduces the
never-wired-scheduler failure through the new enumeration path -- so
zero registered jobs is UNHEALTHY, because a system with no registered
job is a system whose jobs are not registered.
"""

from __future__ import annotations

import datetime as dt
import logging

import pytest
from sqlalchemy.orm import Session

from app.db.models import FEE_GENERATION_JOB, SESSION_GENERATION_JOB, JobHeartbeat
from app.fees.commands import (
    STALENESS_THRESHOLD,
    check_all_jobs,
    check_generation_freshness,
    report_unhealthy_jobs,
)

NOW = dt.datetime(2027, 3, 1, 12, 0, tzinfo=dt.UTC)

#: Comfortably inside the 48-hour window.
FRESH = NOW - dt.timedelta(hours=2)

#: Comfortably outside it.
STALE = NOW - dt.timedelta(hours=72)


def _stamp(session: Session, *, job_name: str, when: dt.datetime) -> None:
    """Write one heartbeat row directly.

    Written as a plain insert rather than through ``stamp_heartbeat``
    because these tests are about what the CHECK reads, and routing the
    arrangement through the writer would couple them to its upsert.

    :param session: An arranging session
    :param job_name: The job this row describes
    :param when: Its last success
    :return: None
    """
    session.add(
        JobHeartbeat(
            job_name=job_name,
            last_success_at=when,
            cycles_created=0,
            cycles_skipped=0,
            periods_failed=0,
        )
    )
    session.commit()


# ---------------------------------------------------------------------
# The three branches under a NON-DEFAULT job name.
#
# A test using the default name passes against a checker that can only
# ever see the default name, which is the defect the whole option-B
# change exists to remove [§ 4.6].
# ---------------------------------------------------------------------


def test_a_session_job_with_no_row_is_never_ran(restricted_session: Session) -> None:
    verdict = check_generation_freshness(
        restricted_session, job_name=SESSION_GENERATION_JOB, now=NOW
    )
    assert verdict.healthy is False
    assert verdict.reason == "never_ran"


def test_a_stale_session_job_is_stale(
    owner_session: Session, restricted_session: Session
) -> None:
    _stamp(owner_session, job_name=SESSION_GENERATION_JOB, when=STALE)

    verdict = check_generation_freshness(
        restricted_session, job_name=SESSION_GENERATION_JOB, now=NOW
    )
    assert verdict.healthy is False
    assert verdict.reason == "stale"
    assert verdict.staleness is not None
    assert verdict.staleness >= STALENESS_THRESHOLD


def test_a_fresh_session_job_is_fresh(
    owner_session: Session, restricted_session: Session
) -> None:
    _stamp(owner_session, job_name=SESSION_GENERATION_JOB, when=FRESH)

    verdict = check_generation_freshness(
        restricted_session, job_name=SESSION_GENERATION_JOB, now=NOW
    )
    assert verdict.healthy is True
    assert verdict.reason == "fresh"


# ---------------------------------------------------------------------
# The enumeration itself.
# ---------------------------------------------------------------------


def test_an_empty_registry_is_unhealthy(restricted_session: Session) -> None:
    # The loop body never runs. A naive implementation returns healthy,
    # which is the never-wired-scheduler failure arriving by the new
    # enumeration route.
    verdicts = check_all_jobs(restricted_session, now=NOW)

    assert verdicts == [], "no rows means no per-job verdicts"


def test_every_registered_job_gets_its_own_verdict(
    owner_session: Session, restricted_session: Session
) -> None:
    _stamp(owner_session, job_name=FEE_GENERATION_JOB, when=FRESH)
    _stamp(owner_session, job_name=SESSION_GENERATION_JOB, when=FRESH)

    verdicts = check_all_jobs(restricted_session, now=NOW)

    assert {name for name, _ in verdicts} == {
        FEE_GENERATION_JOB,
        SESSION_GENERATION_JOB,
    }, (
        "the check must enumerate the registry, not read one name. "
        f"Got {[name for name, _ in verdicts]}."
    )


def test_a_stale_second_job_is_found_while_the_first_is_fresh(
    owner_session: Session, restricted_session: Session
) -> None:
    # THE decisive case [§ 4.6]. A checker that reads the first row it
    # finds, or that only ever checks the fee job, passes every other
    # test in this module and fails this one.
    _stamp(owner_session, job_name=FEE_GENERATION_JOB, when=FRESH)
    _stamp(owner_session, job_name=SESSION_GENERATION_JOB, when=STALE)

    verdicts = dict(check_all_jobs(restricted_session, now=NOW))

    assert verdicts[FEE_GENERATION_JOB].healthy is True
    assert verdicts[SESSION_GENERATION_JOB].healthy is False, (
        "the session job is 72 hours stale and was reported healthy: "
        "the check is not enumerating the registry"
    )
    assert verdicts[SESSION_GENERATION_JOB].reason == "stale"


# ---------------------------------------------------------------------
# The entry point and its alert.
# ---------------------------------------------------------------------


def test_the_entry_point_names_the_stale_job_in_the_alert(
    owner_session: Session,
    restricted_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The hardcoded `job_name: FEE_GENERATION_JOB` in the alert was the
    # second half of the finding: a stale session job that named the
    # fee job would send whoever read the alert to the wrong place.
    _stamp(owner_session, job_name=FEE_GENERATION_JOB, when=FRESH)
    _stamp(owner_session, job_name=SESSION_GENERATION_JOB, when=STALE)

    with caplog.at_level(logging.CRITICAL):
        unhealthy = report_unhealthy_jobs(restricted_session, now=NOW)

    assert unhealthy == 1
    names = [getattr(record, "job_name", None) for record in caplog.records]
    assert SESSION_GENERATION_JOB in names, (
        f"the alert named {names}, not the job that is actually stale"
    )
    assert FEE_GENERATION_JOB not in names, (
        "the fee job is fresh and must not be alerted on"
    )


def test_all_jobs_fresh_reports_nothing_unhealthy(
    owner_session: Session,
    restricted_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _stamp(owner_session, job_name=FEE_GENERATION_JOB, when=FRESH)
    _stamp(owner_session, job_name=SESSION_GENERATION_JOB, when=FRESH)

    with caplog.at_level(logging.CRITICAL):
        unhealthy = report_unhealthy_jobs(restricted_session, now=NOW)

    assert unhealthy == 0
    assert caplog.records == []


def test_an_empty_registry_reports_unhealthy_at_the_entry_point(
    restricted_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The whole point of the empty case: a system with no registered
    # job is a system whose jobs are not registered, and the entry
    # point must say so rather than returning a healthy zero.
    with caplog.at_level(logging.CRITICAL):
        unhealthy = report_unhealthy_jobs(restricted_session, now=NOW)

    assert unhealthy == 1, (
        "zero registered jobs was reported healthy, which reintroduces "
        "the never-wired-scheduler failure through the enumeration path"
    )
    assert caplog.records != []
