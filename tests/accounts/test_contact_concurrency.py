"""Two connections, interleaved: the contact locks and the bounded retry.

Written from the rules (BR2.7, NFR4.2, NFR4.3, NFR4.4, NFR8.11), after the
implementation. Every interleaving holds the first transaction open on a
real connection as the restricted role and starts the second on another,
because a lock that is never contended in a test is a lock nobody has
tested. Each held transaction is bounded by the engine's lock_timeout, so
a regression shows as a failure, never as a hung suite.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.accounts.identifier import Identifier
from app.authz.lenses import TeacherLens
from app.errors import TransientError
from tests.accounts.contact_support import (
    PASSWORD,
    account,
    address,
    auth,
    code_for,
    number,
    seat_links,
)
from tests.batches.conftest import TeacherFixture, make_teacher


@pytest.fixture
def teacher(owner_session: Session) -> TeacherFixture:
    """Create a teacher with one batch.

    :param owner_session: An arranging session
    :return: The teacher
    """
    return make_teacher(owner_session, name="Physics")


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the teacher's lens.

    :param teacher: The teacher
    :return: The lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _in_thread(work: Callable[[], Any]) -> tuple[threading.Thread, list[Any]]:
    """Start work on its own thread, collecting its result or its error.

    :param work: The work
    :return: The thread and a list that receives one outcome
    """
    outcome: list[Any] = []

    def run() -> None:
        """Run the work and record what it produced.

        :return: None
        """
        try:
            outcome.append(work())
        except Exception as error:  # noqa: BLE001 -- the test asserts on it
            outcome.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def _create_student(engine: Engine, teacher: TeacherFixture, email: str) -> uuid.UUID:
    """Record a student by email and seat them, as the teacher's save does.

    :param engine: The restricted engine
    :param teacher: The teacher
    :param email: The student's address
    :return: The student id
    """
    from app.students.service import SeatRequest, create_student

    with Session(bind=engine, expire_on_commit=False) as session:
        row = create_student(
            session,
            lens=_lens(teacher),
            display_name="Mitu",
            student_email=email,
            seats=[SeatRequest(batch_id=teacher.batch_id)],
        )
        return row.seats[0].enrollment_id


# ------------------------------------------------------------------ BR2.7


def test_a_save_waits_for_a_match_of_its_contact_and_then_links(
    restricted_engine: Engine, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Match first, held open: the save waits, then sees the account.

    :param restricted_engine: The application's role
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from app.accounts.matching import match_contact

    email = address()
    holder = account(owner_session, email=email)
    matcher = Session(bind=restricted_engine)
    match_contact(matcher, account_id=holder, contact=Identifier.email(email))

    thread, outcome = _in_thread(
        lambda: _create_student(restricted_engine, teacher, email)
    )
    thread.join(timeout=1.0)
    assert thread.is_alive(), "the save must wait for the match's key"
    matcher.commit()
    matcher.close()
    thread.join(timeout=10.0)

    assert isinstance(outcome[0], uuid.UUID), outcome
    assert seat_links(owner_session, outcome[0]).student == holder


def test_a_match_waits_for_a_save_of_its_contact_and_then_links_it(
    restricted_engine: Engine, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Save first, held open at its commit: the match waits, then links it.

    The account appears between the save's target resolution (none) and
    its commit, which is exactly the window the key closes.

    :param restricted_engine: The application's role
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from app.accounts.matching import match_contact
    from app.students.service import SeatRequest, create_student

    email = address()
    saver = Session(bind=restricted_engine, expire_on_commit=False)
    release = threading.Event()
    reached = threading.Event()
    real_commit = saver.commit

    def held_commit() -> None:
        """Hold the save's commit until the match is waiting.

        :return: None
        """
        reached.set()
        release.wait(timeout=10.0)
        real_commit()

    saver.commit = held_commit  # type: ignore[method-assign]
    save, saved = _in_thread(
        lambda: create_student(
            saver,
            lens=_lens(teacher),
            display_name="Mitu",
            student_email=email,
            seats=[SeatRequest(batch_id=teacher.batch_id)],
        )
    )
    assert reached.wait(timeout=10.0)
    holder = account(owner_session, email=email)

    def match() -> None:
        """Match the address on its own connection.

        :return: None
        """
        with Session(bind=restricted_engine) as session:
            match_contact(session, account_id=holder, contact=Identifier.email(email))
            session.commit()

    matching, matched = _in_thread(match)
    matching.join(timeout=1.0)
    assert matching.is_alive(), "the match must wait for the save's key"
    release.set()
    save.join(timeout=10.0)
    matching.join(timeout=10.0)
    saver.close()

    assert matched == [None], matched
    seat_id = saved[0].seats[0].enrollment_id
    assert seat_links(owner_session, seat_id).student == holder


def test_saves_for_different_contacts_never_wait_on_each_other(
    restricted_engine: Engine, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Keys are per contact, never global [NFR8.11].

    :param restricted_engine: The application's role
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    from app.accounts.matching import match_contact

    held = Session(bind=restricted_engine)
    match_contact(
        held, account_id=account(owner_session), contact=Identifier.email(address())
    )

    thread, outcome = _in_thread(
        lambda: _create_student(restricted_engine, teacher, address())
    )
    thread.join(timeout=5.0)
    held.rollback()
    held.close()

    assert not thread.is_alive()
    assert isinstance(outcome[0], uuid.UUID), outcome


# ------------------------------------------------------- NFR4.2 LO-3 (c)


def test_a_replacement_code_changed_since_the_unlocked_read_is_refused(
    restricted_session: Session,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A newer code, or one spent meanwhile, refuses the row that was read.

    The attempt is recorded on the row that was read and on no other, and
    no other row is spent.

    :param restricted_session: The application's role
    :param owner_session: An arranging session
    :param monkeypatch: The patcher
    :return: None
    """
    from app.auth import otp
    from app.auth.hashing import OTP_HMAC_KEY_ENV

    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    holder = account(owner_session, phone=number())
    owner_session.commit()
    destination = Identifier.email(address())
    first = otp.issue(
        restricted_session,
        destination,
        "c1",
        purpose=otp.CONTACT_REPLACE_PURPOSE,
        requested_by=holder,
    )
    read = otp.find_replacement_code(restricted_session, destination, requester=holder)
    assert read == first.request_id
    newer = otp.issue(
        restricted_session,
        destination,
        "c2",
        purpose=otp.CONTACT_REPLACE_PURPOSE,
        requested_by=holder,
    )

    with pytest.raises(otp.CodeRefused):
        otp.consume_replacement_code(
            restricted_session,
            destination,
            first.code,
            "c3",
            requester=holder,
            code_id=read,
        )

    attempts = dict(
        owner_session.execute(
            sa.text(
                "SELECT o.id, count(v.id) FROM otp_request o LEFT JOIN "
                "verify_attempt v ON v.otp_request_id = o.id "
                "WHERE o.id IN (:a, :b) GROUP BY o.id"
            ),
            {"a": first.request_id, "b": newer.request_id},
        ).all()
    )
    consumed = owner_session.execute(
        sa.text(
            "SELECT count(*) FROM otp_request WHERE id IN (:a, :b) "
            "AND consumed_at IS NOT NULL"
        ),
        {"a": first.request_id, "b": newer.request_id},
    ).scalar_one()
    assert attempts == {first.request_id: 1, newer.request_id: 0}
    assert consumed == 0


# ------------------------------------------------------------------ NFR4.3


class _State:
    """A driver error carrying only a SQLSTATE, as psycopg's does."""

    def __init__(self, sqlstate: str) -> None:
        """Carry one state.

        :param sqlstate: The five-character SQLSTATE
        """
        self.sqlstate = sqlstate


def _operational(sqlstate: str) -> OperationalError:
    """Build the error SQLAlchemy raises for a state.

    :param sqlstate: The SQLSTATE
    :return: The wrapped error
    """
    return OperationalError("SELECT 1", {}, _State(sqlstate))  # type: ignore[arg-type]


def test_a_real_deadlock_is_rerun_once_and_then_succeeds(
    restricted_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """A two-connection deadlock aborts the unit; the re-run completes.

    The unit takes key A and waits for key B; the other connection holds
    B and then asks for A. The unit waited first, so PostgreSQL's deadlock
    check, which runs after ``deadlock_timeout``, picks it.

    :param restricted_engine: The application's role
    :param caplog: The log capture
    :return: None
    """
    from app.db.retry import run_with_retry

    caplog.set_level("WARNING")
    key_a, key_b = f"test:{uuid.uuid4()}:a", f"test:{uuid.uuid4()}:b"
    lock = sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))")
    other = Session(bind=restricted_engine)
    other.execute(lock, {"k": key_b})
    unit_waiting = threading.Event()
    attempts: list[int] = []

    def other_side() -> None:
        """Ask for A once the unit is waiting for B, then finish.

        :return: None
        """
        unit_waiting.wait(timeout=10.0)
        threading.Event().wait(0.2)
        try:
            other.execute(lock, {"k": key_a})
            other.commit()
        except OperationalError:
            other.rollback()
        finally:
            other.close()

    worker = threading.Thread(target=other_side)
    worker.start()
    with Session(bind=restricted_engine) as session:

        def unit() -> str:
            """Take A, then B: deadlocks on the first attempt only.

            :return: ``done``
            """
            attempts.append(1)
            session.execute(lock, {"k": key_a})
            if len(attempts) == 1:
                unit_waiting.set()
            session.execute(lock, {"k": key_b})
            session.commit()
            return "done"

        result = run_with_retry(session, unit, correlation_id="deadlock-test")
    worker.join(timeout=10.0)

    assert result == "done"
    assert len(attempts) == 2
    retries = [r for r in caplog.records if getattr(r, "event", None) == "db_retry"]
    assert [(r.outcome, r.sqlstate) for r in retries] == [("retrying", "40P01")]  # type: ignore[attr-defined]


def test_exhausted_retries_fail_as_retryable(restricted_session: Session) -> None:
    """Three attempts, then TransientError, which renders retryable: true.

    :param restricted_session: The application's role
    :return: None
    """
    from app.db.retry import run_with_retry

    attempts: list[float] = []
    waits: list[float] = []

    def unit() -> None:
        """Fail with a serialization failure every time.

        :return: None
        :raises OperationalError: Always
        """
        attempts.append(1)
        raise _operational("40001")

    with pytest.raises(TransientError):
        run_with_retry(
            restricted_session, unit, correlation_id=None, sleep=waits.append
        )

    assert len(attempts) == 3
    assert 0.010 <= waits[0] <= 0.050
    assert 0.050 <= waits[1] <= 0.150


def test_a_lock_timeout_is_not_retried(restricted_session: Session) -> None:
    """``55P03`` already waited five seconds; it is raised at once [NFR4.3].

    :param restricted_session: The application's role
    :return: None
    """
    from app.db.retry import run_with_retry

    attempts: list[int] = []

    def unit() -> None:
        """Fail with a lock timeout.

        :return: None
        :raises OperationalError: Always
        """
        attempts.append(1)
        raise _operational("55P03")

    with pytest.raises(OperationalError):
        run_with_retry(restricted_session, unit, correlation_id=None)

    assert attempts == [1]


def test_a_deadlocked_replacement_is_rerun_and_done_exactly_once(
    api_client: TestClient,
    owner_session: Session,
    outbound: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``40P01`` after the match: one replacement, one count, one notice.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :param monkeypatch: The patcher
    :return: None
    """
    import app.accounts.contact as contact

    old = address()
    holder = account(owner_session, phone=number(), email=old, password=PASSWORD)
    headers = auth(api_client, owner_session, holder)
    new = address()
    asked = api_client.post(
        "/v1/me/contact", json={"email": new, "password": PASSWORD}, headers=headers
    )
    assert asked.status_code == 200, asked.text
    code = code_for(outbound, new)
    real = contact.match_contact
    calls: list[int] = []

    def deadlock_once(*args: object, **kwargs: Any) -> None:
        """Match, then fail the first attempt with a deadlock.

        :param args: The matcher's arguments
        :param kwargs: The matcher's keyword arguments
        :return: None
        :raises OperationalError: On the first call
        """
        calls.append(1)
        real(*args, **kwargs)  # type: ignore[arg-type]
        if len(calls) == 1:
            raise _operational("40P01")

    monkeypatch.setattr(contact, "match_contact", deadlock_once)
    done = api_client.post(
        "/v1/me/contact/verify", json={"email": new, "code": code}, headers=headers
    )

    assert done.status_code == 200, done.text
    assert done.json()["email"] == new
    assert len(calls) == 2
    owner_session.expire_all()
    counted = owner_session.execute(
        sa.text(
            "SELECT count FROM rate_limit_counter WHERE scope_kind = "
            "'contact_chg_day' AND scope_value = :a"
        ),
        {"a": str(holder)},
    ).scalar_one()
    replaced = owner_session.execute(
        sa.text(
            "SELECT count(*) FROM auth_audit_log WHERE account_id = :a "
            "AND event = 'CONTACT_REPLACED'"
        ),
        {"a": holder},
    ).scalar_one()
    assert (counted, replaced) == (1, 1)
    assert [to for to, _ in outbound].count(old) == 1
