"""Adversarial probes against D3's tables, as the restricted role.

**D3 adds no row-level-security policy, so the probes ARE the
mechanism** [NFR14.36, security-design § 2] -- not a supplement to one.
The built policy is on ``profile`` alone, where ``account_id`` IS the
subject so ``account_id = current_setting(...)`` is a predicate on a
column of the row. A fee cycle's authorization is a *path* instead:
an accepted student link, an accepted guardian link, or ownership of the
batch. Encoding that into a ``USING`` clause would make two
implementations of one authorization rule, the second outside
``app.authz``'s coverage measurement and its strict mypy island.

**Every session here is the restricted non-superuser role.** A superuser
or table owner bypasses row-level security entirely, so a privacy suite
run as either passes identically whether a policy is correct, broken, or
absent.

**Every pre-authorization refusal is the SHARED ``NOT_AVAILABLE``**
[security-design § 4]. A pair such as ``FEE_CYCLE_NOT_FOUND`` /
``FEE_CYCLE_NOT_YOURS`` is an existence oracle even though each code
reads as good practice alone: a prober reads the difference and
enumerates which ids are real.

The three IDOR shapes the affirmed posture names are all here, and the
third -- a student requesting a fee cycle not their own -- lands for the
first time in this unit, because fee cycles did not exist before.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.db.models import FeeCycle
from app.errors import AuthorizationError
from app.errors.codes import NOT_AVAILABLE
from app.fees import views
from app.fees.ledger_writer import append_entry
from app.fees.periods import Period
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher


def _charge(session: Session, seat: uuid.UUID, period: str, amount: str) -> None:
    """Arrange one generated cycle with its charge.

    Both rows, not just the entry: a fee history lists CYCLES and folds
    the ledger for each, so an entry with no cycle row describes money
    owed for a period that was never generated -- a state generation
    cannot produce.

    :param session: The session to write through
    :param seat: The enrollment
    :param period: The period
    :param amount: The amount, as a canonical string
    :return: None
    """
    session.add(
        FeeCycle(
            enrollment_id=seat,
            period=period,
            due_date=Period.parse(period).last_day(),
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    append_entry(
        session,
        enrollment_id=seat,
        period=period,
        kind="charge",
        amount=Money(amount),
    )
    session.commit()


# ---------------------------------------------------------------------
# NFR14.38 — teacher A against teacher B's batch.
# ---------------------------------------------------------------------


def test_a_teacher_cannot_read_another_teachers_batch_fees(
    restricted_session: Session,
    owner_session: Session,
    account_factory: object,
) -> None:
    first = make_teacher(owner_session, name="Physics")
    second = make_teacher(owner_session, name="Chemistry")
    their_seat = enroll(
        owner_session,
        batch_id=second.batch_id,
        display_name="Not mine",
        student_decision="accepted",
        guardian_decision="pending",
    )
    _charge(restricted_session, their_seat, "2027-01", "1000.00")

    with pytest.raises(AuthorizationError) as refusal:
        views.batch_fee_overview(
            restricted_session,
            lens=TeacherLens(account_id=first.account_id, owner_id=first.owner_id),
            batch_id=second.batch_id,
        )

    assert refusal.value.code == NOT_AVAILABLE


def test_an_invented_batch_id_is_refused_identically(
    restricted_session: Session,
    owner_session: Session,
) -> None:
    # THE ORACLE TEST. A real-but-not-yours id and an invented one must
    # be indistinguishable, or a prober enumerates which ids are real.
    first = make_teacher(owner_session, name="Physics")
    second = make_teacher(owner_session, name="Chemistry")

    lens = TeacherLens(account_id=first.account_id, owner_id=first.owner_id)

    with pytest.raises(AuthorizationError) as real_but_theirs:
        views.batch_fee_overview(
            restricted_session, lens=lens, batch_id=second.batch_id
        )
    with pytest.raises(AuthorizationError) as invented:
        views.batch_fee_overview(restricted_session, lens=lens, batch_id=uuid.uuid4())

    assert real_but_theirs.value.code == invented.value.code == NOT_AVAILABLE
    assert real_but_theirs.value.status == invented.value.status


def test_a_teacher_reads_their_own_batch_fees(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The positive case, so the refusals above are not passing because
    # the function refuses everybody.
    _charge(restricted_session, seat, "2027-01", "1000.00")

    rows = views.batch_fee_overview(
        restricted_session,
        lens=TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id),
        batch_id=teacher.batch_id,
    )

    assert [row.enrollment_id for row in rows] == [seat]
    assert rows[0].outstanding == Money("1000.00")


# ---------------------------------------------------------------------
# NFR14.39 — a guardian against a non-child's enrollment.
# ---------------------------------------------------------------------


def test_a_guardian_cannot_read_a_non_childs_fee_cycles(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: object,
) -> None:
    guardian = account_factory()
    mine = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="My child",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    theirs = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Another child",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    _charge(restricted_session, theirs, "2027-01", "1000.00")

    with pytest.raises(AuthorizationError) as refusal:
        views.enrollment_fee_history(
            restricted_session,
            lens=GuardianLens(account_id=guardian, child_enrollment_id=mine),
            enrollment_id=theirs,
        )

    assert refusal.value.code == NOT_AVAILABLE


def test_a_guardian_reads_their_own_childs_fee_cycles(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: object,
) -> None:
    guardian = account_factory()
    mine = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="My child",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    _charge(restricted_session, mine, "2027-01", "1000.00")

    history = views.enrollment_fee_history(
        restricted_session,
        lens=GuardianLens(account_id=guardian, child_enrollment_id=mine),
        enrollment_id=mine,
    )

    assert [row.period for row in history.cycles] == ["2027-01"]


def test_a_declined_guardian_link_cannot_read_the_fees(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: object,
) -> None:
    # The guardian's own LENS is withdrawn by a decline even though the
    # money is untouched [BR1.7]. Both halves of the asymmetry are
    # asserted: the fee stands, and the view is refused.
    guardian = account_factory()
    child = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Child",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="declined",
    )
    _charge(restricted_session, child, "2027-01", "1000.00")

    with pytest.raises(AuthorizationError):
        views.enrollment_fee_history(
            restricted_session,
            lens=GuardianLens(account_id=guardian, child_enrollment_id=child),
            enrollment_id=child,
        )


# ---------------------------------------------------------------------
# NFR14.40 — a student against a fee cycle not their own.
# ---------------------------------------------------------------------


def test_a_student_cannot_read_another_students_fee_cycle(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: object,
) -> None:
    # Named explicitly in the team practice and landing here for the
    # first time, because fee cycles did not exist before.
    me = account_factory()
    mine = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Me",
        student_account_id=me,
        student_decision="accepted",
        guardian_decision="pending",
    )
    theirs = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Someone else",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )
    _charge(restricted_session, theirs, "2027-01", "1000.00")
    _charge(restricted_session, mine, "2027-01", "1000.00")

    with pytest.raises(AuthorizationError) as refusal:
        views.enrollment_fee_history(
            restricted_session,
            lens=StudentLens(account_id=me),
            enrollment_id=theirs,
        )

    assert refusal.value.code == NOT_AVAILABLE

    # NOT VACUOUS: the same lens reads its OWN seat. Without this the
    # refusal above would pass against an implementation that refuses
    # every student everything, which is the shape a scope check
    # degrades into when its predicate is wrong.
    assert [
        row.period
        for row in views.enrollment_fee_history(
            restricted_session,
            lens=StudentLens(account_id=me),
            enrollment_id=mine,
        ).cycles
    ] == ["2027-01"]


def test_a_student_cannot_read_a_claim_that_is_not_theirs(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: object,
) -> None:
    from app.fees.claims import submit_claim

    me = account_factory()
    other_student = account_factory()
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Me",
        student_account_id=me,
        student_decision="accepted",
        guardian_decision="pending",
    )
    theirs = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Someone else",
        student_account_id=other_student,
        student_decision="accepted",
        guardian_decision="pending",
    )
    _charge(restricted_session, theirs, "2027-01", "1000.00")
    claim = submit_claim(
        restricted_session,
        enrollment_id=theirs,
        submitted_by_account_id=other_student,
        claimed_amount=Money("1000.00"),
        channel="bKash",
    )

    with pytest.raises(AuthorizationError) as refusal:
        views.claim_detail(
            restricted_session,
            lens=StudentLens(account_id=me),
            claim_id=claim.id,
        )

    assert refusal.value.code == NOT_AVAILABLE


def test_a_student_reads_their_own_claim(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: object,
) -> None:
    from app.fees.claims import submit_claim

    me = account_factory()
    mine = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Me",
        student_account_id=me,
        student_decision="accepted",
        guardian_decision="pending",
    )
    _charge(restricted_session, mine, "2027-01", "1000.00")
    claim = submit_claim(
        restricted_session,
        enrollment_id=mine,
        submitted_by_account_id=me,
        claimed_amount=Money("1000.00"),
        channel="bKash",
    )

    detail = views.claim_detail(
        restricted_session, lens=StudentLens(account_id=me), claim_id=claim.id
    )

    assert detail.claimed_amount == Money("1000.00")
    assert detail.status == "pending"


def test_a_non_owning_teacher_cannot_verify_a_claim(
    restricted_session: Session,
    owner_session: Session,
    account_factory: object,
) -> None:
    # A non-owning teacher must not learn the claim exists.
    from app.fees.claims import submit_claim

    first = make_teacher(owner_session, name="Physics")
    second = make_teacher(owner_session, name="Chemistry")
    student = account_factory()
    their_seat = enroll(
        owner_session,
        batch_id=second.batch_id,
        display_name="Theirs",
        student_account_id=student,
        student_decision="accepted",
        guardian_decision="pending",
    )
    _charge(restricted_session, their_seat, "2027-01", "1000.00")
    claim = submit_claim(
        restricted_session,
        enrollment_id=their_seat,
        submitted_by_account_id=student,
        claimed_amount=Money("1000.00"),
        channel="bKash",
    )

    with pytest.raises(AuthorizationError) as refusal:
        views.assert_claim_is_verifiable(
            restricted_session,
            lens=TeacherLens(account_id=first.account_id, owner_id=first.owner_id),
            claim_id=claim.id,
        )

    assert refusal.value.code == NOT_AVAILABLE


# ---------------------------------------------------------------------
# BR6.4, NFR14.32 — the collection number, bounded DOWNWARD.
# ---------------------------------------------------------------------


def test_the_collection_number_is_visible_to_an_enrolled_student(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: object,
) -> None:
    owner_session.execute(
        sa.text("UPDATE batch SET collection_number = :n WHERE id = :id"),
        {"n": "01711000000", "id": teacher.batch_id},
    )
    owner_session.commit()

    me = account_factory()
    mine = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Me",
        student_account_id=me,
        student_decision="accepted",
        guardian_decision="pending",
    )

    destination = views.payment_destination(
        restricted_session,
        lens=StudentLens(account_id=me),
        enrollment_id=mine,
    )

    assert destination is not None
    assert destination.collection_number == "01711000000"
    # [BR6.5] The channel set is SERVER-supplied, in the same response.
    assert destination.channels


def test_the_collection_number_is_refused_to_a_non_enrolled_student(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: object,
) -> None:
    owner_session.execute(
        sa.text("UPDATE batch SET collection_number = :n WHERE id = :id"),
        {"n": "01711000000", "id": teacher.batch_id},
    )
    owner_session.commit()

    outsider = account_factory()
    someone_elses = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Not theirs",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )

    with pytest.raises(AuthorizationError):
        views.payment_destination(
            restricted_session,
            lens=StudentLens(account_id=outsider),
            enrollment_id=someone_elses,
        )


def test_an_unset_collection_number_omits_the_destination(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: object,
) -> None:
    # [NFR14.34] ABSENT, not present-with-null. A null invites a client
    # placeholder; an absent object leaves the client nothing to render
    # and the copy tells the person to ask the teacher.
    owner_session.execute(
        sa.text("UPDATE batch SET collection_number = NULL WHERE id = :id"),
        {"id": teacher.batch_id},
    )
    owner_session.commit()

    me = account_factory()
    mine = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Me",
        student_account_id=me,
        student_decision="accepted",
        guardian_decision="pending",
    )

    assert (
        views.payment_destination(
            restricted_session,
            lens=StudentLens(account_id=me),
            enrollment_id=mine,
        )
        is None
    )


def test_no_other_fee_response_carries_the_collection_number(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # **The direction the built schema-wide invariant does not check.**
    # That gate asserts no TEACHER-facing response carries a profile
    # field; this asserts the collection number appears in no listing
    # and no overview, which is a different question about a field the
    # teacher is entitled to see.
    owner_session.execute(
        sa.text("UPDATE batch SET collection_number = :n WHERE id = :id"),
        {"n": "01711000000", "id": teacher.batch_id},
    )
    owner_session.commit()
    _charge(restricted_session, seat, "2027-01", "1000.00")

    rows = views.batch_fee_overview(
        restricted_session,
        lens=TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id),
        batch_id=teacher.batch_id,
    )
    history = views.enrollment_fee_history(
        restricted_session,
        lens=TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id),
        enrollment_id=seat,
    )

    for row in [*rows, *history.cycles]:
        assert not hasattr(row, "collection_number")

    # The WRAPPER too, not only its rows. `enrollment_fee_history`
    # gained a `total_outstanding` on 2026-10-27, and a field added to
    # the envelope would slip past a loop that only reads the entries.
    assert not hasattr(history, "collection_number")
