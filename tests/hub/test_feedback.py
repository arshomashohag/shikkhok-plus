"""The teacher demand question: "Did the hub bring you a student?" [H2].

At day 60 and day 90 after an owner's FIRST publish, the daily job asks the
people who run the listing, in their inbox, and records one row per
``(owner, day)``. The answers decide whether the hub continues, so the
three properties pinned here are the ones a wrong implementation would get
quietly wrong: the day is counted in Dhaka, not UTC; a missed run heals
within a week; and overlapping runs ask once.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import HUB_FEEDBACK_JOB
from app.governance.deletion import HARD_DELETE_SCOPES, Scope, delete_account
from app.governance.dispositions import DISPOSITIONS, Disposition, RetentionClass
from app.hub.feedback import ask_due
from app.hub.feedback_commands import run_ask
from app.local_time import DHAKA
from app.notifications.inbox import HUB_FEEDBACK_QUESTION, LEGACY_KINDS
from tests.batches.conftest import make_teacher
from tests.conftest import bearer
from tests.hub.support import add_member, centre_with_manager

#: The day the job runs in these tests, in Dhaka.
TODAY = dt.date(2027, 3, 1)

#: When the job runs: 03:00 UTC, 09:00 in Dhaka.
NOW = dt.datetime(2027, 3, 1, 3, 0, tzinfo=dt.UTC)

#: How many runs contend in the concurrency test.
WORKERS = 8


def _dhaka(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    """Build a moment on a Dhaka wall clock.

    :param day: The Dhaka date
    :param hour: The Dhaka hour
    :param minute: The Dhaka minute
    :return: The aware moment
    """
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=DHAKA)


def _days_ago(days: int, hour: int = 10, minute: int = 0) -> dt.datetime:
    """Build a moment on the Dhaka date ``days`` before :data:`TODAY`.

    :param days: How many Dhaka days back
    :param hour: The Dhaka hour
    :param minute: The Dhaka minute
    :return: The aware moment
    """
    return _dhaka(TODAY - dt.timedelta(days=days), hour, minute)


def _listing(
    session: Session,
    owner_id: uuid.UUID,
    first_published_at: dt.datetime | None,
    *,
    name: str = "Rahim Sir",
) -> None:
    """Arrange an owner listing first published at a given moment.

    ``published_at`` is set to now, as a republish would leave it, so a
    job anchored on the wrong column asks on the wrong day.

    :param session: An arranging session
    :param owner_id: The owner
    :param first_published_at: When it was first published, or never
    :param name: The public name
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "published_at, first_published_at) VALUES (:o, :slug, :status, "
            ":name, CASE WHEN CAST(:first AS timestamptz) IS NULL THEN NULL "
            "ELSE now() END, :first)"
        ),
        {
            "o": owner_id,
            "slug": f"o-{owner_id.hex[:12]}",
            "status": "draft" if first_published_at is None else "published",
            "name": name,
            "first": first_published_at,
        },
    )
    session.commit()


def _asked(session: Session) -> set[tuple[uuid.UUID, int]]:
    """Read every asked ``(owner, day)``.

    :param session: Any session
    :return: The pairs
    """
    return {
        (row.owner_id, row.day)
        for row in session.execute(sa.text("SELECT owner_id, day FROM hub_feedback"))
    }


def _questions(session: Session) -> list[tuple[uuid.UUID, uuid.UUID, str]]:
    """Read every question delivered, as ``(account, source, preview)``.

    :param session: Any session
    :return: The deliveries, sorted
    """
    return sorted(
        (row.account_id, row.source_id, row.preview)
        for row in session.execute(
            sa.text(
                "SELECT account_id, source_id, preview FROM notification "
                "WHERE kind = :k"
            ),
            {"k": HUB_FEEDBACK_QUESTION},
        )
    )


def _phone(session: Session, account_id: uuid.UUID) -> str:
    """Read an account's number.

    :param session: A session
    :param account_id: The account
    :return: Its phone number
    """
    return str(
        session.execute(
            sa.text("SELECT phone FROM account WHERE id = :a"), {"a": account_id}
        ).scalar_one()
    )


def test_asks_at_day_60_and_90_dhaka_date(
    owner_session: Session, restricted_session: Session
) -> None:
    """Day 60 and day 90 are Dhaka dates; a UTC date is a day off at night.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    # 00:30 in Dhaka on day 60 is still the previous UTC day (day 61).
    sixty = make_teacher(owner_session)
    _listing(owner_session, sixty.owner_id, _days_ago(60, hour=0, minute=30))
    # 05:59 in Dhaka on day 59 is the UTC date of day 60: not asked yet.
    fifty_nine = make_teacher(owner_session)
    _listing(owner_session, fifty_nine.owner_id, _days_ago(59, hour=5, minute=59))
    ninety = make_teacher(owner_session)
    _listing(owner_session, ninety.owner_id, _days_ago(90))
    seventy = make_teacher(owner_session)
    _listing(owner_session, seventy.owner_id, _days_ago(70))
    never = make_teacher(owner_session)
    _listing(owner_session, never.owner_id, None)

    asked = ask_due(restricted_session, TODAY, now=NOW)

    assert asked == 2
    assert _asked(owner_session) == {(sixty.owner_id, 60), (ninety.owner_id, 90)}
    asked_on = owner_session.execute(
        sa.text("SELECT DISTINCT asked_on FROM hub_feedback")
    ).scalar_one()
    assert asked_on == TODAY
    assert _questions(owner_session) == sorted(
        [
            (sixty.account_id, sixty.owner_id, "60"),
            (ninety.account_id, ninety.owner_id, "90"),
        ]
    )
    assert HUB_FEEDBACK_QUESTION == "hub_feedback_question"
    assert HUB_FEEDBACK_QUESTION not in LEGACY_KINDS


def test_self_heals_missed_run_within_7_days(
    owner_session: Session, restricted_session: Session
) -> None:
    """A run missed for up to seven days still asks; the eighth day does not.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    late_sixty = make_teacher(owner_session)
    _listing(owner_session, late_sixty.owner_id, _days_ago(67, hour=23, minute=59))
    too_late = make_teacher(owner_session)
    _listing(owner_session, too_late.owner_id, _days_ago(68))
    late_ninety = make_teacher(owner_session)
    _listing(owner_session, late_ninety.owner_id, _days_ago(97, hour=0))

    result = run_ask(restricted_session, today=TODAY, now=NOW)

    assert result.asked == 2
    assert _asked(owner_session) == {
        (late_sixty.owner_id, 60),
        (late_ninety.owner_id, 90),
    }
    # The next day's run asks nothing twice, and still heartbeats.
    again = run_ask(restricted_session, today=TODAY + dt.timedelta(days=1), now=NOW)
    assert again.asked == 0
    assert len(_questions(owner_session)) == 2
    stamped = owner_session.execute(
        sa.text("SELECT count(*) FROM job_heartbeat WHERE job_name = :j"),
        {"j": HUB_FEEDBACK_JOB},
    ).scalar_one()
    assert stamped == 1


def test_idempotent_concurrent_runs(
    restricted_engine: Engine, owner_session: Session
) -> None:
    """Overlapping runs ask each ``(owner, day)`` once, and notify once.

    Real threads released together against real PostgreSQL, as the fee
    generator's race test does: a sequential pair passes against a job with
    no atomicity at all.

    :param restricted_engine: The application role's engine
    :param owner_session: An arranging session
    :return: None
    """
    solo = make_teacher(owner_session)
    _listing(owner_session, solo.owner_id, _days_ago(60))
    other = make_teacher(owner_session)
    _listing(owner_session, other.owner_id, _days_ago(92))
    centre = centre_with_manager(owner_session)
    _, second_manager = add_member(owner_session, centre.owner_id, role="manager")
    _listing(owner_session, centre.owner_id, _days_ago(61), name="Udoy Coaching")

    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(WORKERS)
    failures: list[BaseException] = []
    lock = threading.Lock()

    def run() -> None:
        session = factory()
        try:
            barrier.wait(timeout=30)
            ask_due(session, TODAY, now=NOW)
        except BaseException as error:  # noqa: BLE001  recorded, then asserted
            with lock:
                failures.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=run) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert failures == [], f"{len(failures)} racing runs raised: {failures[:1]!r}"
    rows = owner_session.execute(
        sa.text("SELECT owner_id, day, count(*) FROM hub_feedback GROUP BY 1, 2")
    ).all()
    assert sorted((r[0], r[1], r[2]) for r in rows) == sorted(
        [(solo.owner_id, 60, 1), (other.owner_id, 90, 1), (centre.owner_id, 60, 1)]
    )
    # THE OUTCOME: one question per account per question, not eight.
    assert _questions(owner_session) == sorted(
        [
            (solo.account_id, solo.owner_id, "60"),
            (other.account_id, other.owner_id, "90"),
            (centre.manager_account_id, centre.owner_id, "60"),
            (second_manager, centre.owner_id, "60"),
        ]
    )


def test_answer_overwrites_and_refuses_unasked_day(
    api_client: TestClient, owner_session: Session, restricted_session: Session
) -> None:
    """The latest answer stands; a day never asked is refused with 409.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    teacher = make_teacher(owner_session)
    _listing(owner_session, teacher.owner_id, _days_ago(60))
    bystander = make_teacher(owner_session)
    _listing(owner_session, bystander.owner_id, _days_ago(60))
    ask_due(restricted_session, TODAY, now=NOW)
    headers = bearer(owner_session, teacher.account_id)

    first = api_client.post(
        "/v1/hub/feedback", json={"day": 60, "answer": "yes"}, headers=headers
    )
    second = api_client.post(
        "/v1/hub/feedback", json={"day": 60, "answer": "not_sure"}, headers=headers
    )
    unasked = api_client.post(
        "/v1/hub/feedback", json={"day": 90, "answer": "yes"}, headers=headers
    )
    wrong_day = api_client.post(
        "/v1/hub/feedback", json={"day": 30, "answer": "yes"}, headers=headers
    )
    wrong_answer = api_client.post(
        "/v1/hub/feedback", json={"day": 60, "answer": "maybe"}, headers=headers
    )

    assert (first.status_code, second.status_code) == (204, 204)
    assert unasked.status_code == 409
    assert unasked.json()["error"]["code"] == "HUB_FEEDBACK_NOT_ASKED"
    assert unasked.json()["error"]["message_key"] == "hub.feedback_not_asked"
    assert (wrong_day.status_code, wrong_answer.status_code) == (422, 422)
    rows = {
        row.owner_id: (row.answer, row.answered_by_account_id, row.answered_at)
        for row in owner_session.execute(
            sa.text(
                "SELECT owner_id, answer, answered_by_account_id, answered_at "
                "FROM hub_feedback"
            )
        )
    }
    answer, by, at = rows[teacher.owner_id]
    assert (answer, by) == ("not_sure", teacher.account_id)
    assert at is not None
    # Nobody else's question moved.
    assert rows[bystander.owner_id] == (None, None, None)
    assert _asked(owner_session) == {
        (teacher.owner_id, 60),
        (bystander.owner_id, 60),
    }


def test_centre_managers_receive_question(
    api_client: TestClient, owner_session: Session, restricted_session: Session
) -> None:
    """A centre's accepted, unrevoked managers are asked; nobody else is.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    centre = centre_with_manager(owner_session)
    _, pending = add_member(
        owner_session, centre.owner_id, role="manager", decision="pending"
    )
    _, revoked = add_member(
        owner_session, centre.owner_id, role="manager", revoked=True
    )
    _, teacher = add_member(owner_session, centre.owner_id, role="teacher")
    _listing(owner_session, centre.owner_id, _days_ago(90), name="Udoy Coaching")

    ask_due(restricted_session, TODAY, now=NOW)

    asked = {account for account, _, _ in _questions(owner_session)}
    assert asked == {centre.manager_account_id}
    assert not asked & {pending, revoked, teacher}
    name = owner_session.execute(
        sa.text("SELECT batch_name FROM notification WHERE kind = :k"),
        {"k": HUB_FEEDBACK_QUESTION},
    ).scalar_one()
    assert name == "Udoy Coaching"

    # The manager answers for the centre by naming it as the workspace.
    answered = api_client.post(
        "/v1/hub/feedback",
        json={"day": 90, "answer": "not_yet"},
        headers={
            **bearer(owner_session, centre.manager_account_id),
            "X-Workspace-Id": str(centre.owner_id),
        },
    )
    assert answered.status_code == 204
    stored = owner_session.execute(
        sa.text("SELECT answer, answered_by_account_id FROM hub_feedback")
    ).one()
    assert (stored.answer, stored.answered_by_account_id) == (
        "not_yet",
        centre.manager_account_id,
    )


def test_deletion_disposition(
    owner_session: Session, restricted_session: Session
) -> None:
    """A solo owner's answers go with them; a centre's outlive a manager.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    governance = DISPOSITIONS["hub_feedback"]
    assert governance.disposition is Disposition.HARD_DELETE
    assert governance.retention is RetentionClass.LIFE_OF_ACCOUNT
    target = HARD_DELETE_SCOPES["hub_feedback"]
    assert (target.scope, target.column) == (Scope.SOLO_OWNER, "owner_id")

    solo = make_teacher(owner_session)
    _listing(owner_session, solo.owner_id, _days_ago(60))
    centre = centre_with_manager(owner_session)
    _listing(owner_session, centre.owner_id, _days_ago(60), name="Udoy Coaching")
    ask_due(restricted_session, TODAY, now=NOW)
    owner_session.execute(
        sa.text(
            "UPDATE hub_feedback SET answer = 'yes', answered_at = now(), "
            "answered_by_account_id = :a WHERE owner_id = :o"
        ),
        {"a": centre.manager_account_id, "o": centre.owner_id},
    )
    owner_session.commit()

    delete_account(owner_session, _phone(owner_session, solo.account_id))
    delete_account(owner_session, _phone(owner_session, centre.manager_account_id))
    owner_session.expire_all()

    remaining = owner_session.execute(
        sa.text("SELECT owner_id, answer, answered_by_account_id FROM hub_feedback")
    ).all()
    assert [(r[0], r[1], r[2]) for r in remaining] == [(centre.owner_id, "yes", None)]
