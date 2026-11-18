"""Review eligibility: one statement, every boundary written first [spec §6].

Who may review a batch is an authorization predicate, so each boundary here
was written and shown failing before the statement existed. The world is
arranged through the table-owner session and read through the restricted
application role, which is the only thing the statement is ever run as.

``today`` is passed in rather than read from the clock, so every boundary is
exact and no test depends on the day it runs.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.reviews.eligibility import Assessment, assess, reviewable
from tests.batches.conftest import enroll
from tests.hub.support import add_member, assign_slot
from tests.reviews.support import (
    account,
    add_review,
    attend,
    guardian_seat,
    hold_classes,
    public_batch,
    public_centre_batch,
    second_batch,
)

#: A fixed "today" in Bangladesh; every date below is measured from it.
TODAY = dt.date(2026, 11, 18)

#: Comfortably past the 30-day tenure condition.
LONG_AGO = TODAY - dt.timedelta(days=100)


def _days(n: int) -> dt.timedelta:
    """Spell a day count.

    :param n: Days
    :return: The interval
    """
    return dt.timedelta(days=n)


def _seat(
    session: Session,
    batch_id: uuid.UUID,
    guardian: uuid.UUID,
    *,
    joined_on: dt.date | None = LONG_AGO,
    attended: int = 4,
    **seat: object,
) -> uuid.UUID:
    """Seat a guardian's child and record attended classes.

    :param session: An arranging session
    :param batch_id: The batch
    :param guardian: The guardian account
    :param joined_on: The join date
    :param attended: How many held classes the child was present at
    :param seat: Further :func:`guardian_seat` keywords
    :return: The enrollment id
    """
    enrollment = guardian_seat(
        session,
        batch_id,
        guardian,
        joined_on=joined_on,
        **seat,
    )
    attend(session, hold_classes(session, batch_id, attended), enrollment)
    return enrollment


def _assess(
    session: Session,
    guardian: uuid.UUID,
    batch_id: uuid.UUID,
    today: dt.date = TODAY,
) -> Assessment:
    """Assess a member, failing loudly if they are not one.

    :param session: The restricted session
    :param guardian: The guardian account
    :param batch_id: The batch
    :param today: Bangladesh's date
    :return: The assessment
    """
    found = assess(session, guardian, batch_id, today)
    assert found is not None
    return found


# --- Condition 4: tenure ---------------------------------------------------


def test_day_29_not_yet_with_eligible_from(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    joined = TODAY - _days(29)
    _seat(owner_session, batch.batch_id, guardian, joined_on=joined)

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "not_yet"
    assert found.waiting_on == "tenure"
    assert found.eligible_from == joined + _days(30)


def test_day_30_eligible(owner_session: Session, restricted_session: Session) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(owner_session, batch.batch_id, guardian, joined_on=TODAY - _days(30))

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "eligible"
    assert found.waiting_on is None
    assert found.eligible_from is None


def test_joined_on_null_uses_created_at_in_dhaka(
    owner_session: Session, restricted_session: Session
) -> None:
    """20:00 UTC is 02:00 the next day in Dhaka.

    The seat was created on UTC day ``today - 30`` -- which would qualify --
    but on Dhaka day ``today - 29``, which does not.
    """
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    utc_day = TODAY - _days(30)
    created = dt.datetime.combine(utc_day, dt.time(20, 0), tzinfo=dt.UTC)
    _seat(owner_session, batch.batch_id, guardian, joined_on=None, created_at=created)

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "not_yet"
    assert found.waiting_on == "tenure"
    assert found.eligible_from == TODAY + _days(1)


# --- Condition 5: attendance -----------------------------------------------


def test_three_attended_not_yet_attendance(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(owner_session, batch.batch_id, guardian, attended=3)

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "not_yet"
    assert found.waiting_on == "attendance"
    assert found.eligible_from is None


def test_four_attended_eligible(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(owner_session, batch.batch_id, guardian, attended=4)

    assert _assess(restricted_session, guardian, batch.batch_id).standing == (
        "eligible"
    )


def test_absent_and_cancelled_sessions_do_not_count(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    seat = _seat(owner_session, batch.batch_id, guardian, attended=3)
    absent = hold_classes(owner_session, batch.batch_id, 2)
    attend(owner_session, absent, seat, present=False)
    cancelled = hold_classes(owner_session, batch.batch_id, 2, status="cancelled")
    attend(owner_session, cancelled, seat)

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "not_yet"
    assert found.waiting_on == "attendance"


def test_attendance_in_another_batch_does_not_count(
    owner_session: Session, restricted_session: Session
) -> None:
    """Neither a sibling's classes elsewhere nor a stray cross-batch row."""
    batch = public_batch(owner_session)
    other = second_batch(owner_session, batch.owner_id, title="SSC Chemistry")
    guardian = account(owner_session)
    seat = _seat(owner_session, batch.batch_id, guardian, attended=3)
    # The same child's seat attending a class of another batch.
    attend(owner_session, hold_classes(owner_session, other, 2), seat)
    # The guardian's seat in the other batch, fully attended.
    _seat(owner_session, other, guardian, attended=6)

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "not_yet"
    assert found.waiting_on == "attendance"


def test_tenure_and_attendance_unmet_waits_on_attendance_with_eligible_from(
    owner_session: Session, restricted_session: Session
) -> None:
    """F20: the date is given whenever tenure is unmet, not only alone."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    joined = TODAY - _days(5)
    _seat(owner_session, batch.batch_id, guardian, joined_on=joined, attended=1)

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "not_yet"
    assert found.waiting_on == "attendance"
    assert found.eligible_from == joined + _days(30)


# --- Condition 6: recency --------------------------------------------------


def test_inactive_180_days_eligible(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(
        owner_session,
        batch.batch_id,
        guardian,
        joined_on=TODAY - _days(400),
        inactive_from=TODAY - _days(180),
    )

    assert _assess(restricted_session, guardian, batch.batch_id).standing == (
        "eligible"
    )


def test_inactive_181_days_closed(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(
        owner_session,
        batch.batch_id,
        guardian,
        joined_on=TODAY - _days(400),
        inactive_from=TODAY - _days(181),
    )

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "closed"
    assert found.waiting_on is None
    assert found.eligible_from is None


# --- Conditions 1-3: membership --------------------------------------------


@pytest.mark.parametrize(
    "seat",
    [
        {"decision": "pending"},
        {"decision": "declined"},
        {"relink_blocked": True},
    ],
    ids=["pending", "declined", "blocked"],
)
def test_pending_declined_or_blocked_guardian_is_not_member(
    owner_session: Session, restricted_session: Session, seat: dict[str, object]
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(owner_session, batch.batch_id, guardian, **seat)

    assert assess(restricted_session, guardian, batch.batch_id, TODAY) is None


def test_student_link_is_not_member(
    owner_session: Session, restricted_session: Session
) -> None:
    """V1 is guardian-only: an accepted, long-standing student never qualifies."""
    batch = public_batch(owner_session)
    student = account(owner_session)
    seat = enroll(
        owner_session,
        batch_id=batch.batch_id,
        display_name="Student",
        student_account_id=student,
        student_decision="accepted",
    )
    attend(owner_session, hold_classes(owner_session, batch.batch_id, 6), seat)

    assert assess(restricted_session, student, batch.batch_id, TODAY) is None


@pytest.mark.parametrize(
    "listing",
    [
        {"batch_status": "draft"},
        {"batch_status": "hidden"},
        {"owner_status": "suspended"},
        {"owner_status": "draft"},
        {"active": False},
    ],
    ids=["batch-draft", "batch-hidden", "owner-suspended", "owner-draft", "inactive"],
)
def test_invisible_batch_is_not_member(
    owner_session: Session, restricted_session: Session, listing: dict[str, object]
) -> None:
    batch = public_batch(owner_session, **listing)
    guardian = account(owner_session)
    _seat(owner_session, batch.batch_id, guardian)

    assert assess(restricted_session, guardian, batch.batch_id, TODAY) is None


# --- Nobody who runs the batch reviews it [T3-c] ---------------------------


@pytest.mark.parametrize("runner", ["solo-owner", "centre-manager"])
def test_owner_or_manager_of_the_batch_is_not_member(
    owner_session: Session, restricted_session: Session, runner: str
) -> None:
    """A teacher seating their own child, however eligible, is no reviewer.

    The owner controls ``joined_on`` and marks the attendance, so without
    this a teacher is a "verified guardian" of their own batch on day one.
    """
    if runner == "solo-owner":
        batch = public_batch(owner_session)
    else:
        batch = public_centre_batch(owner_session)
    _seat(owner_session, batch.batch_id, batch.teacher_account_id)

    assert (
        assess(restricted_session, batch.teacher_account_id, batch.batch_id, TODAY)
        is None
    )


@pytest.mark.parametrize("assigned_by", ["weekly-slot", "one-class"])
def test_class_teacher_of_the_batch_is_not_member(
    owner_session: Session, restricted_session: Session, assigned_by: str
) -> None:
    batch = public_centre_batch(owner_session)
    member_id, teacher = add_member(owner_session, batch.owner_id)
    if assigned_by == "weekly-slot":
        assign_slot(owner_session, batch.batch_id, member_id)
    else:
        (klass,) = hold_classes(owner_session, batch.batch_id, 1)
        owner_session.execute(
            sa.text("UPDATE session SET teacher_member_id = :m WHERE id = :s"),
            {"m": member_id, "s": klass},
        )
        owner_session.commit()
    _seat(owner_session, batch.batch_id, teacher)

    assert assess(restricted_session, teacher, batch.batch_id, TODAY) is None


@pytest.mark.parametrize(
    ("member", "assigned"),
    [
        ({"role": "manager", "revoked": True}, None),
        ({"role": "manager", "decision": "declined"}, None),
        ({"role": "teacher", "revoked": True}, "slot-here"),
        ({"role": "teacher", "decision": "declined"}, "slot-here"),
        ({"role": "teacher"}, "slot-elsewhere"),
        ({"role": "teacher"}, "class-elsewhere"),
        ({"role": "teacher"}, "colleague-here"),
    ],
    ids=[
        "revoked-manager",
        "declined-manager",
        "revoked-teacher",
        "declined-teacher",
        "slot-in-another-batch",
        "class-in-another-batch",
        "colleague-assigned-here",
    ],
)
def test_former_or_unassigned_staff_may_review(
    owner_session: Session,
    restricted_session: Session,
    member: dict[str, object],
    assigned: str | None,
) -> None:
    """Only those running THIS batch now are excluded, as managing_accounts.

    A former or declined manager or teacher, a teacher of another batch of
    the centre, and a member whose colleague teaches this batch all review
    like any other guardian.
    """
    batch = public_centre_batch(owner_session)
    member_id, guardian = add_member(owner_session, batch.owner_id, **member)
    other = second_batch(owner_session, batch.owner_id, title="Class 10 Maths")
    if assigned == "slot-here":
        assign_slot(owner_session, batch.batch_id, member_id)
    elif assigned == "slot-elsewhere":
        assign_slot(owner_session, other, member_id)
    elif assigned == "class-elsewhere":
        (klass,) = hold_classes(owner_session, other, 1)
        owner_session.execute(
            sa.text("UPDATE session SET teacher_member_id = :m WHERE id = :s"),
            {"m": member_id, "s": klass},
        )
        owner_session.commit()
    elif assigned == "colleague-here":
        colleague, _ = add_member(owner_session, batch.owner_id, name="Salma Apa")
        assign_slot(owner_session, batch.batch_id, colleague)
    _seat(owner_session, batch.batch_id, guardian)

    assert _assess(restricted_session, guardian, batch.batch_id).standing == (
        "eligible"
    )


def test_staff_who_wrote_a_review_keeps_only_an_author_lens(
    owner_session: Session, restricted_session: Session
) -> None:
    """Becoming a manager leaves an earlier review deletable, never writable."""
    batch = public_centre_batch(owner_session)
    guardian = account(owner_session)
    seat = _seat(owner_session, batch.batch_id, guardian)
    review = add_review(owner_session, batch.batch_id, guardian, enrollment_id=seat)
    add_member(owner_session, batch.owner_id, role="manager", account_id=guardian)

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "author_only"
    assert found.review_id == review


# --- Several seats, and authors --------------------------------------------


def test_siblings_one_eligible_grants_with_that_enrollment(
    owner_session: Session, restricted_session: Session
) -> None:
    """Review Focus 1: an eligible seat wins over an earlier ineligible one.

    Three children of one guardian in one batch: the earliest has no
    attendance, two are eligible. The evidence is the eligible seat with the
    earliest join date, and its tenure is measured from that seat.
    """
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(
        owner_session,
        batch.batch_id,
        guardian,
        joined_on=TODAY - _days(400),
        attended=0,
    )
    evidence = _seat(
        owner_session, batch.batch_id, guardian, joined_on=TODAY - _days(250)
    )
    _seat(owner_session, batch.batch_id, guardian, joined_on=TODAY - _days(100))

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "eligible"
    assert found.enrollment_id == evidence
    assert found.tenure == "6_12m"


def test_closed_sibling_does_not_mask_a_live_one(
    owner_session: Session, restricted_session: Session
) -> None:
    """A long-gone seat must not close a batch a newer sibling is joining."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(
        owner_session,
        batch.batch_id,
        guardian,
        joined_on=TODAY - _days(500),
        inactive_from=TODAY - _days(300),
    )
    joined = TODAY - _days(10)
    newer = _seat(owner_session, batch.batch_id, guardian, joined_on=joined)

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "not_yet"
    assert found.enrollment_id == newer
    assert found.eligible_from == joined + _days(30)


def test_waiting_siblings_prefer_the_seat_waiting_only_on_tenure(
    owner_session: Session, restricted_session: Session
) -> None:
    """T3-d: a seat lacking only tenure has a real date; it is shown.

    The earliest seat has tenure but too few classes, and would answer
    "needs attendance" with no date while a sibling opens on a known day.
    """
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(
        owner_session,
        batch.batch_id,
        guardian,
        joined_on=TODAY - _days(100),
        attended=2,
    )
    # Dated too, but waiting on attendance as well: not a real day.
    _seat(
        owner_session,
        batch.batch_id,
        guardian,
        joined_on=TODAY - _days(20),
        attended=1,
    )
    joined = TODAY - _days(10)
    waiting = _seat(
        owner_session, batch.batch_id, guardian, joined_on=joined, attended=5
    )

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "not_yet"
    assert found.enrollment_id == waiting
    assert found.waiting_on == "tenure"
    assert found.eligible_from == joined + _days(30)


def test_waiting_siblings_never_hide_a_known_date(
    owner_session: Session, restricted_session: Session
) -> None:
    """T3-d: a dated seat beats an earlier undated one."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(
        owner_session,
        batch.batch_id,
        guardian,
        joined_on=TODAY - _days(100),
        attended=2,
    )
    joined = TODAY - _days(20)
    dated = _seat(owner_session, batch.batch_id, guardian, joined_on=joined, attended=1)

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.enrollment_id == dated
    assert found.waiting_on == "attendance"
    assert found.eligible_from == joined + _days(30)


@pytest.mark.parametrize(
    "lose",
    [
        "UPDATE enrollment SET guardian_decision = 'declined' WHERE batch_id = :b",
        "UPDATE batch_listing SET status = 'hidden' WHERE batch_id = :b",
    ],
    ids=["seat-declined", "listing-hidden"],
)
def test_author_keeps_lens_after_losing_membership(
    owner_session: Session, restricted_session: Session, lose: str
) -> None:
    batch = public_batch(owner_session, title="Class 8 English")
    guardian = account(owner_session)
    seat = _seat(owner_session, batch.batch_id, guardian)
    review = add_review(owner_session, batch.batch_id, guardian, enrollment_id=seat)
    owner_session.execute(sa.text(lose), {"b": batch.batch_id})
    owner_session.commit()

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "author_only"
    assert found.review_id == review
    assert found.enrollment_id is None
    assert found.tenure is None
    assert found.batch_title == "Class 8 English"


def test_member_who_wrote_a_review_carries_its_id(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session, title="HSC Biology", owner_name="Nila Apa")
    guardian = account(owner_session)
    seat = _seat(owner_session, batch.batch_id, guardian)
    review = add_review(owner_session, batch.batch_id, guardian, enrollment_id=seat)

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "eligible"
    assert found.review_id == review
    assert found.batch_id == batch.batch_id
    assert found.batch_title == "HSC Biology"
    assert found.owner_public_name == "Nila Apa"


def test_member_never_carries_another_authors_review(
    owner_session: Session, restricted_session: Session
) -> None:
    """A fellow parent's review is not this member's to edit or delete."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(owner_session, batch.batch_id, guardian)
    other = account(owner_session)
    add_review(
        owner_session,
        batch.batch_id,
        other,
        enrollment_id=_seat(owner_session, batch.batch_id, other),
    )

    found = _assess(restricted_session, guardian, batch.batch_id)

    assert found.standing == "eligible"
    assert found.review_id is None


def test_nonmember_without_review_and_missing_batch_assess_to_none(
    owner_session: Session, restricted_session: Session
) -> None:
    batch = public_batch(owner_session)
    stranger = account(owner_session)
    # Someone else's review must not lend the stranger a lens.
    other = account(owner_session)
    add_review(owner_session, batch.batch_id, other)

    assert assess(restricted_session, stranger, batch.batch_id, TODAY) is None
    assert assess(restricted_session, stranger, uuid.uuid4(), TODAY) is None


# --- Tenure buckets --------------------------------------------------------

#: A join date away from a month end, so ``+ interval '6 months'`` is exact.
JOINED = dt.date(2025, 3, 15)


@pytest.mark.parametrize(
    ("today", "bucket"),
    [
        (dt.date(2025, 9, 14), "lt_6m"),
        (dt.date(2025, 9, 15), "6_12m"),
        (dt.date(2026, 3, 14), "6_12m"),
        (dt.date(2026, 3, 15), "gt_1y"),
    ],
    ids=["6m-minus-1", "6m", "12m-minus-1", "12m"],
)
def test_tenure_buckets_at_boundaries(
    owner_session: Session,
    restricted_session: Session,
    today: dt.date,
    bucket: str,
) -> None:
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _seat(owner_session, batch.batch_id, guardian, joined_on=JOINED)

    found = _assess(restricted_session, guardian, batch.batch_id, today)

    assert found.standing == "eligible"
    assert found.tenure == bucket


# --- The reviewable list ---------------------------------------------------


def _five_batches(session: Session, guardian: uuid.UUID) -> dict[str, uuid.UUID]:
    """Arrange one batch per standing, titled so the list order is known.

    :param session: An arranging session
    :param guardian: The guardian
    :return: Review ids by title, for the two reviewed batches
    """
    eligible = public_batch(session, title="A eligible")
    _seat(session, eligible.batch_id, guardian)

    waiting = public_batch(session, title="B waiting")
    _seat(session, waiting.batch_id, guardian, attended=1)

    closed = public_batch(session, title="C closed")
    _seat(
        session,
        closed.batch_id,
        guardian,
        joined_on=TODAY - _days(500),
        inactive_from=TODAY - _days(200),
    )

    closed_reviewed = public_batch(session, title="D closed, reviewed")
    seat = _seat(
        session,
        closed_reviewed.batch_id,
        guardian,
        joined_on=TODAY - _days(500),
        inactive_from=TODAY - _days(200),
    )
    d = add_review(session, closed_reviewed.batch_id, guardian, enrollment_id=seat)

    gone = public_batch(session, title="E left, reviewed")
    e = add_review(session, gone.batch_id, guardian)

    # Not this guardian's: never listed.
    public_batch(session, title="F someone else's")
    return {"D closed, reviewed": d, "E left, reviewed": e}


def test_reviewable_lists_open_and_reviewed_omits_closed(
    owner_session: Session, restricted_session: Session
) -> None:
    guardian = account(owner_session)
    reviews = _five_batches(owner_session, guardian)

    rows = reviewable(restricted_session, guardian, TODAY, include_open=True)

    assert [(r.batch_title, r.standing) for r in rows] == [
        ("A eligible", "eligible"),
        ("B waiting", "not_yet"),
        ("D closed, reviewed", "closed"),
        ("E left, reviewed", "author_only"),
    ]
    assert [r.review_id for r in rows] == [
        None,
        None,
        reviews["D closed, reviewed"],
        reviews["E left, reviewed"],
    ]


def test_reviewable_off_lists_only_reviewed(
    owner_session: Session, restricted_session: Session
) -> None:
    guardian = account(owner_session)
    reviews = _five_batches(owner_session, guardian)

    rows = reviewable(restricted_session, guardian, TODAY, include_open=False)

    assert [(r.batch_title, r.review_id) for r in rows] == [
        ("D closed, reviewed", reviews["D closed, reviewed"]),
        ("E left, reviewed", reviews["E left, reviewed"]),
    ]
