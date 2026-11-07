"""A seed run writes the described history, atomically, and refuses safely.

Against a real PostgreSQL as the RESTRICTED role, because what the
seeder promises is that it writes only what the application itself can
write: the same role, the same services, the same row-level security.

``now`` is pinned, so the history and every assertion about it are the
same on any day the suite runs. The read-only checks share ONE seed
run: a three-month seed takes tens of seconds, and none of them writes.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.accounts.service import PostalAddress, SignupRole, create_account
from app.local_time import DHAKA
from app.seed import scenario
from app.seed.scenario import SeedRefused, SeedReport, SeedRequest, seed
from tests.conftest import bearer

TEACHER = "+8801711000001"
NOW = dt.datetime(2026, 11, 6, 18, 0, tzinfo=DHAKA)


def _account(engine: Engine, phone: str, role: SignupRole) -> uuid.UUID:
    """Sign a number up, as the app's sign-up does.

    :param engine: The restricted engine
    :param phone: The number
    :param role: Teacher, student or guardian
    :return: The account
    """
    with Session(engine) as session:
        created = create_account(
            session,
            phone=phone,
            role=role,
            self_name="Test Person",
            address=PostalAddress("House 1", "Road 2", "Dhaka", "1216"),
            now=dt.datetime(2026, 7, 1, tzinfo=dt.UTC),
        )
    return created.account_id


def _rows(engine: Engine, sql: str, **params: object) -> list[tuple[object, ...]]:
    """Run a query as the restricted role, closing the connection after.

    Closing matters: a connection left idle in its transaction holds a
    lock the suite's TRUNCATE between tests then waits on forever.

    :param engine: The restricted engine
    :param sql: The statement
    :param params: Its parameters
    :return: Every row, as tuples
    """
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(sa.text(sql), params)]


def _count(engine: Engine, sql: str, **params: object) -> int:
    """Run a COUNT as the restricted role.

    :param engine: The restricted engine
    :param sql: The statement
    :param params: Its parameters
    :return: The count
    """
    value = _rows(engine, sql, **params)[0][0]
    assert isinstance(value, int)
    return value


def test_a_seeded_account(
    restricted_engine: Engine,
    restricted_session: Session,
    api_client: TestClient,
) -> None:
    """One seed run, every property of it, then a refused second run."""
    teacher = _account(restricted_engine, TEACHER, SignupRole.TEACHER)
    report = seed(
        restricted_engine, SeedRequest(phone="01711000001"), environment="test", now=NOW
    )

    _check_shape(report, restricted_engine)
    _check_weekly_tests_cover_the_week(restricted_engine)
    _check_a_real_term(report, restricted_engine)
    _check_fees(report, restricted_engine)
    _check_timestamps(restricted_engine)
    _check_the_api_serves_it(
        teacher, report, restricted_engine, restricted_session, api_client
    )

    with pytest.raises(SeedRefused, match="already has the seeded batches"):
        seed(restricted_engine, SeedRequest(phone=TEACHER), environment="test", now=NOW)


def _check_shape(report: SeedReport, engine: Engine) -> None:
    """Three batches of twenty, fewer than sixty people, three months.

    :param report: The run's report
    :param engine: The restricted engine
    :return: None
    """
    counts = report.counts
    assert report.history_from == dt.date(2026, 8, 1)
    assert counts["batches"] == 3
    assert counts["seats"] == 60
    assert 40 <= counts["students"] < 60
    sizes = _rows(
        engine,
        "SELECT b.name, count(e.id) FROM batch b JOIN enrollment e "
        "ON e.batch_id = b.id GROUP BY b.name",
    )
    assert sorted(n for _name, n in sizes) == [20, 20, 20]
    subjects = _rows(
        engine,
        "SELECT b.name, array_agg(s.name ORDER BY s.name) FROM batch b "
        "JOIN batch_subject s ON s.batch_id = b.id GROUP BY b.name",
    )
    assert sorted(tuple(names) for _b, names in subjects) == [  # type: ignore[arg-type]
        ("Math",),
        ("Math", "Physics"),
        ("Math", "Physics"),
    ]


def _check_weekly_tests_cover_the_week(engine: Engine) -> None:
    """Check a weekly test's topics are exactly that week's classes.

    :param engine: The restricted engine
    :return: None
    """
    exams = _rows(
        engine,
        "SELECT batch_id, batch_subject_id, date, topics FROM exam "
        "WHERE title LIKE 'Weekly Test%'",
    )
    assert len(exams) >= 12 * 5 - 5  # five a week, less a holiday or hartal
    for batch_id, subject_id, day, topics in exams:
        assert isinstance(day, dt.date)
        saturday = day - dt.timedelta(days=(day.weekday() - 5) % 7)
        taught = [
            row[0]
            for row in _rows(
                engine,
                "SELECT topic FROM session WHERE batch_id = :b "
                "AND batch_subject_id = :s AND date >= :sat AND date < :d "
                "AND status = 'held' ORDER BY date",
                b=batch_id,
                s=subject_id,
                sat=saturday,
                d=day,
            )
        ]
        assert topics == taught


def _check_a_real_term(report: SeedReport, engine: Engine) -> None:
    """Attendance, cancellations, drafts, absences and corrections.

    :param report: The run's report
    :param engine: The restricted engine
    :return: None
    """
    held = report.counts["sessions_held"]
    assert held > 150
    # Roughly the whole roster per class, absentees included.
    assert 15 * held < report.counts["attendance_rows"] <= 20 * held
    assert (
        _count(engine, "SELECT count(*) FROM session WHERE status = 'cancelled'") >= 4
    )
    # The latest week's tests are still drafts; one exam was called off.
    assert (
        _count(
            engine,
            "SELECT count(*) FROM exam WHERE published_at IS NULL "
            "AND cancelled_at IS NULL",
        )
        >= 2
    )
    assert (
        _count(engine, "SELECT count(*) FROM exam WHERE cancelled_at IS NOT NULL") == 1
    )
    assert (
        _count(
            engine,
            "SELECT count(*) FROM mark WHERE result_state = 'absent' "
            "AND superseded_by_id IS NULL",
        )
        > 0
    )
    assert (
        _count(engine, "SELECT count(*) FROM mark WHERE superseded_by_id IS NOT NULL")
        > 0
    )


def _check_fees(report: SeedReport, engine: Engine) -> None:
    """Paid on time, late, in part, ahead, together, rejected, not at all.

    :param report: The run's report
    :param engine: The restricted engine
    :return: None
    """
    counts = report.counts
    # Generated on the 1st for each of the four months a seat was in.
    assert 200 < counts["fee_cycles"] <= 240
    assert counts["seats_owing_last_month"] >= 5
    assert counts["payments_pending_review"] >= 1
    statuses = {
        row[0] for row in _rows(engine, "SELECT DISTINCT status FROM payment_claim")
    }
    assert statuses >= {"approved_full", "approved_partial", "rejected", "pending"}
    dispositions = {
        row[0]
        for row in _rows(
            engine,
            "SELECT DISTINCT shortfall_disposition FROM payment_claim "
            "WHERE shortfall_disposition IS NOT NULL",
        )
    }
    assert dispositions == {"carried", "waived"}
    # Several families paid on one day; the rest across many days.
    per_day = _rows(
        engine, "SELECT paid_on, count(*) FROM payment_submission GROUP BY paid_on"
    )
    assert max(n for _d, n in per_day) >= 3  # type: ignore[type-var]
    assert len(per_day) > 30
    # Paying ahead left credit that a later month spent.
    assert (
        _count(engine, "SELECT count(*) FROM ledger_entry WHERE kind = 'credit_apply'")
        > 0
    )
    # Two siblings paid in one submission.
    assert (
        _count(
            engine,
            "SELECT count(*) FROM (SELECT payment_submission_id FROM payment_claim "
            "GROUP BY payment_submission_id HAVING count(*) > 1) s",
        )
        > 0
    )


def _check_timestamps(engine: Engine) -> None:
    """Nothing was stamped with the real clock: the shim reached it all.

    :param engine: The restricted engine
    :return: None
    """
    start = dt.datetime(2026, 8, 1, tzinfo=DHAKA)
    for table, column in (
        ("batch", "created_at"),
        ("enrollment", "created_at"),
        ("fee_cycle", "created_at"),
        ("ledger_entry", "created_at"),
        ("payment_submission", "submitted_at"),
        ("payment_claim", "verified_at"),
        ("session", "created_at"),
        ("attendance", "recorded_at"),
        ("exam", "created_at"),
        ("mark", "recorded_at"),
        ("expense", "created_at"),
        ("announcement", "created_at"),
        ("notification", "created_at"),
        ("reminder_event", "sent_at"),
    ):
        [(low, high)] = _rows(
            engine,
            f"SELECT min({column}), max({column}) FROM {table}",  # noqa: S608  fixed names
        )
        assert isinstance(low, dt.datetime) and isinstance(high, dt.datetime), table
        assert start <= low <= high <= NOW, table
    # And spread across it, not bunched on one afternoon.
    days = _count(
        engine,
        "SELECT count(DISTINCT date(recorded_at AT TIME ZONE 'Asia/Dhaka')) "
        "FROM attendance",
    )
    assert days > 60


def _check_the_api_serves_it(
    teacher: uuid.UUID,
    report: SeedReport,
    engine: Engine,
    session: Session,
    client: TestClient,
) -> None:
    """Check the teacher's and a family's screens load: the point.

    :param teacher: The teacher's account
    :param report: The run's report
    :param engine: The restricted engine
    :param session: A session to issue tokens through
    :param client: The API client
    :return: None
    """
    headers = bearer(session, teacher)
    batch_ids = [row[0] for row in _rows(engine, "SELECT id FROM batch")]
    leaves = ("roster", "sessions", "exams", "extra-fees", "fees", "announcements")
    for path in (
        "/v1/batches",
        "/v1/claims/queue",
        "/v1/students",
        "/v1/expenses",
        "/v1/money/summary",
        "/v1/analytics/collections",
        *(f"/v1/batches/{b}/{leaf}" for b in batch_ids for leaf in leaves),
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.text)

    phone = next(
        login["phone"]
        for login in report.family_logins
        if login["role"] == "guardian" and login["seat"] == "accepted"
    )
    [(guardian,)] = _rows(engine, "SELECT id FROM account WHERE phone = :p", p=phone)
    assert isinstance(guardian, uuid.UUID)
    family = bearer(session, guardian)
    for path in ("/v1/guardian/children", "/v1/guardian/home", "/v1/me/notifications"):
        response = client.get(path, headers=family)
        assert response.status_code == 200, (path, response.text)


def test_a_failure_part_way_leaves_the_account_untouched(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All or nothing, although every service the run drives commits.

    Each service's commit releases a savepoint inside the run's one
    transaction, so a failure a week in rolls back the whole week.
    """
    _account(restricted_engine, TEACHER, SignupRole.TEACHER)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("the database went away mid-run")

    monkeypatch.setattr(scenario, "publish_exam", fail)
    with pytest.raises(RuntimeError, match="went away"):
        seed(
            restricted_engine,
            SeedRequest(phone=TEACHER, months=1),
            environment="test",
            now=NOW,
        )
    for table in (
        "batch",
        "student",
        "enrollment",
        "fee_cycle",
        "session",
        "exam",
        "payment_submission",
        "expense",
        "notification",
    ):
        assert _count(restricted_engine, f"SELECT count(*) FROM {table}") == 0, table  # noqa: S608
    # Only the teacher's own account is left; no family was signed up.
    assert _count(restricted_engine, "SELECT count(*) FROM account") == 1


def test_production_is_refused_before_connecting() -> None:
    engine = sa.create_engine("postgresql+psycopg://nobody@127.0.0.1:1/none")
    with pytest.raises(SeedRefused, match="production"):
        seed(engine, SeedRequest(phone=TEACHER), environment="production", now=NOW)


@pytest.mark.parametrize(
    ("phone", "message"),
    [
        ("12345", "not a Bangladeshi mobile"),
        ("+8801799999999", "no account has that number"),
    ],
)
def test_an_unusable_number_is_refused(
    restricted_engine: Engine, phone: str, message: str
) -> None:
    with pytest.raises(SeedRefused, match=message):
        seed(restricted_engine, SeedRequest(phone=phone), environment="test", now=NOW)


def test_a_family_account_is_not_a_teacher_to_seed(restricted_engine: Engine) -> None:
    _account(restricted_engine, TEACHER, SignupRole.GUARDIAN)
    with pytest.raises(SeedRefused, match="no teacher workspace"):
        seed(restricted_engine, SeedRequest(phone=TEACHER), environment="test", now=NOW)


def test_months_out_of_range_are_refused(restricted_engine: Engine) -> None:
    with pytest.raises(SeedRefused, match="months"):
        seed(
            restricted_engine,
            SeedRequest(phone=TEACHER, months=0),
            environment="test",
            now=NOW,
        )
