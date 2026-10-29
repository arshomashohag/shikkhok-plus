"""The teacher's payment queue (T4): what waits to be checked.

**Written before the queue existed.** It is a read over money and over
other people's claims, so both halves of the test-first predicate hold:
the expected figures are knowable from the charges without any
implementation, and a wrong answer is a money error (a shortfall the
teacher acts on) or an authorization error (a claim from another
teacher's batch).

The figures are the server's decisions. A charge of 1200 against a
claim of 800 is ``short`` by ``400.00``; the app shows those words and
never subtracts.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.errors import AuthorizationError
from app.fees.claims import submit_claim
from app.fees.ledger_writer import append_entry
from app.fees.queue import shortfall_preview, verification_queue
from app.fees.verification import reject_claim, verify_claim
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher

PERIOD = "2026-10"


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build a teacher's lens.

    :param teacher: The teacher
    :return: Their lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _charge(session: Session, seat: uuid.UUID, amount: str) -> None:
    """Charge one period.

    :param session: An arranging session
    :param seat: The enrollment
    :param amount: The amount, canonical
    :return: None
    """
    append_entry(
        session, enrollment_id=seat, period=PERIOD, kind="charge", amount=Money(amount)
    )
    session.commit()


def _claim(
    session: Session,
    seat: uuid.UUID,
    account_id: uuid.UUID,
    amount: str,
    transaction_id: str | None = "TX-1",
) -> uuid.UUID:
    """Submit one claim.

    :param session: An arranging session
    :param seat: The enrollment
    :param account_id: Who submitted it
    :param amount: The claimed amount, canonical
    :param transaction_id: The quoted reference
    :return: The claim id
    """
    return submit_claim(
        session,
        enrollment_id=seat,
        submitted_by_account_id=account_id,
        claimed_amount=Money(amount),
        channel="bKash",
        transaction_id=transaction_id,
    ).id


def test_a_pending_claim_carries_the_charge_and_the_servers_comparison(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Charged 1200, claimed 800: short by 400, decided by the server.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    _charge(owner_session, seat, "1200.00")
    claim = _claim(owner_session, seat, student, "800.00")

    queue = verification_queue(restricted_session, lens=_lens(teacher))

    [item] = queue.pending
    assert item.claim_id == claim
    assert item.display_name == "Rahim"
    assert item.charged == Money("1200.00")
    assert item.claimed_amount == Money("800.00")
    assert (item.comparison, item.difference) == ("short", Money("400.00"))
    assert item.submitted_by == "student"
    assert item.transaction_id == "TX-1"
    assert item.duplicate_of is None


def test_a_claim_equal_to_the_charge_matches_and_one_above_is_over(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The other two comparisons, each with the figure that decides it.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    results: dict[str, tuple[str, Money]] = {}
    for name, claimed in (("Exact", "1200.00"), ("Over", "1500.00")):
        student = account_factory()
        seat = enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=name,
            student_account_id=student,
            student_decision="accepted",
        )
        _charge(owner_session, seat, "1200.00")
        _claim(owner_session, seat, student, claimed, transaction_id=f"TX-{name}")

    for item in verification_queue(restricted_session, lens=_lens(teacher)).pending:
        results[item.display_name] = (item.comparison, item.difference)

    assert results == {
        "Exact": ("matches", Money.ZERO),
        "Over": ("over", Money("300.00")),
    }


def test_another_teachers_claims_never_appear(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The queue is scoped to the batches this lens owns.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: A teacher with a pending claim
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    _charge(owner_session, seat, "1200.00")
    _claim(owner_session, seat, student, "1200.00")
    stranger = make_teacher(owner_session, name="Chemistry")

    queue = verification_queue(restricted_session, lens=_lens(stranger))

    assert queue.pending == []
    assert queue.decided_recently == []


def test_a_decided_claim_leaves_the_queue_for_the_recent_list(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Approved and rejected claims move to "decided today" [T4 empty].

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    claims: list[uuid.UUID] = []
    for name in ("Asha", "Bilal"):
        student = account_factory()
        seat = enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=name,
            student_account_id=student,
            student_decision="accepted",
        )
        _charge(owner_session, seat, "1200.00")
        claims.append(_claim(owner_session, seat, student, "1200.00", f"TX-{name}"))
    verify_claim(
        owner_session,
        claim_id=claims[0],
        approved_amount=Money("1200.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )
    reject_claim(
        owner_session, claim_id=claims[1], verified_by_account_id=teacher.account_id
    )

    queue = verification_queue(restricted_session, lens=_lens(teacher))

    assert queue.pending == []
    assert {item.status for item in queue.decided_recently} == {
        "approved_full",
        "rejected",
    }


def test_a_decision_older_than_a_day_is_not_recent(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Treat "approved today" as the last day, not every decision ever.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    _charge(owner_session, seat, "1200.00")
    claim = _claim(owner_session, seat, student, "1200.00")
    verify_claim(
        owner_session,
        claim_id=claim,
        approved_amount=Money("1200.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )

    later = dt.datetime.now(tz=dt.UTC) + dt.timedelta(days=2)
    queue = verification_queue(restricted_session, lens=_lens(teacher), now=later)

    assert queue.decided_recently == []


def test_a_transaction_id_used_twice_names_the_earlier_claim(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The same bKash ID on two claims flags the later one (T4 error).

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    first_student = account_factory()
    first = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Sakib",
        student_account_id=first_student,
        student_decision="accepted",
    )
    _charge(owner_session, first, "1500.00")
    earlier = _claim(owner_session, first, first_student, "1500.00", "8N7K2QX")
    verify_claim(
        owner_session,
        claim_id=earlier,
        approved_amount=Money("1500.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )
    second_student = account_factory()
    second = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=second_student,
        student_decision="accepted",
    )
    _charge(owner_session, second, "1200.00")
    _claim(owner_session, second, second_student, "1200.00", " 8n7k2qx ")

    [item] = verification_queue(restricted_session, lens=_lens(teacher)).pending

    assert item.duplicate_of is not None
    assert item.duplicate_of.display_name == "Sakib"
    assert item.duplicate_of.status == "approved_full"
    assert item.duplicate_of.amount == Money("1500.00")


def test_a_guardian_submitted_claim_says_so_with_the_number_on_record(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Name a guardian submitter with the number the teacher typed.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        guardian_phone="+8801711234567",
        student_decision="accepted",
        guardian_decision="accepted",
    )
    _charge(owner_session, seat, "1200.00")
    _claim(owner_session, seat, guardian, "1200.00")

    [item] = verification_queue(restricted_session, lens=_lens(teacher)).pending

    assert item.submitted_by == "guardian"
    assert item.submitter_phone == "+8801711234567"


def test_the_shortfall_preview_is_charged_minus_approved(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Charged 1000, claimed 1500, approving 600 leaves 400, not 900.

    The separating case from ``test_verification.py``: a preview built
    on the claim would show 900 and lead the teacher to carry the wrong
    amount forward.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    _charge(owner_session, seat, "1000.00")
    claim = _claim(owner_session, seat, student, "1500.00")
    lens = _lens(teacher)

    short = shortfall_preview(
        restricted_session, lens=lens, claim_id=claim, approved_amount=Money("600.00")
    )
    whole = shortfall_preview(
        restricted_session, lens=lens, claim_id=claim, approved_amount=Money("1000.00")
    )

    assert short == Money("400.00")
    assert whole == Money.ZERO


def test_the_preview_refuses_another_teachers_claim(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A preview is a read of the charge, and the charge is not theirs.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    _charge(owner_session, seat, "1000.00")
    claim = _claim(owner_session, seat, student, "1000.00")
    stranger = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError) as refusal:
        shortfall_preview(
            restricted_session,
            lens=_lens(stranger),
            claim_id=claim,
            approved_amount=Money("600.00"),
        )

    assert refusal.value.code == "NOT_AVAILABLE"
