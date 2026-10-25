"""A read's figures describe ONE instant, not two [NFR6.62].

The dues read is two statements and a fold. **Between statement 1 and
statement 2 a receipt can commit**, and what happens then is a design
decision rather than an accident [scalability § 1]:

* two autocommitted selects give seats from before the write and ledger
  rows from after -- a seat whose balance reflects a payment its oldest
  unpaid period does not;
* **one transaction, one snapshot** gives both statements the same
  instant, so the figures agree with each other whichever instant won.

**This asserts internal consistency, never which snapshot won.** Both
are correct: the design claim is that one of them won rather than both
halves of neither.

The property is already provided by the built request-scoped session, so
this test asserts a property the code has rather than one D5 adds. It is
specified anyway because the property is **easy to lose for a
good-sounding reason** -- splitting the ledger read into its own session
"to release the connection sooner" would break it silently, and nothing
else would notice.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.analytics.dues import dues_rows
from app.analytics.seats import ledger_for_seats, owned_seats
from app.fees.ledger_writer import append_entry
from app.money import Money
from tests.analytics.conftest import lens_for, seat_with_ledger
from tests.batches.conftest import TeacherFixture


def test_a_mid_read_commit_leaves_the_figures_internally_consistent(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """A receipt committing between the two statements changes neither
    half independently.

    The write lands from a **second session** after the seat set has
    been read and before the ledger has been. Under one snapshot both
    statements see the same instant, so the outstanding balance and the
    oldest unpaid period agree with each other -- which is the only
    claim made.

    :param owner_session: The second session, which commits mid-read
    :param restricted_session: The session the read runs in
    :param teacher: The teacher
    :return: None
    """
    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Paying mid-read",
        entries=[
            ("charge", "2027-01", "500.00"),
            ("charge", "2027-02", "500.00"),
        ],
    )

    # Statement 1 of the read, inside the session's transaction.
    seats = owned_seats(restricted_session, lens_for(teacher))

    # A receipt commits from another connection, between the two.
    append_entry(
        owner_session,
        enrollment_id=seat,
        period="2027-01",
        kind="receipt",
        amount=Money("500.00"),
    )
    owner_session.commit()

    # Statement 2, and the fold.
    ledger = ledger_for_seats(
        restricted_session, [item.enrollment_id for item in seats]
    )
    rows = {row.enrollment_id: row for row in dues_rows(seats, ledger)}
    row = rows[seat]

    # Whichever instant won, the two figures agree: 1000 outstanding
    # from January if the write was not seen, 500 from February if it
    # was. What must NOT happen is 500 outstanding reported against an
    # oldest unpaid period of January -- halves of two snapshots.
    assert (row.outstanding, row.oldest_unpaid_period) in {
        (Money("1000.00"), "2027-01"),
        (Money("500.00"), "2027-02"),
    }, (
        f"outstanding {row.outstanding} against oldest unpaid period "
        f"{row.oldest_unpaid_period}: the two figures come from "
        "different instants, so the read is not one snapshot "
        "[NFR6.62]."
    )


def test_the_two_figures_come_from_the_same_fold(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Outstanding and the oldest period are one fold, not two reads.

    Asserted structurally: ``dues.py`` takes entries already in hand and
    has no session to read a second time with, so the two figures
    **cannot** come from different folds. This pins that the assembly
    function's signature stays that way.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    import inspect

    from app.analytics import dues

    parameters = inspect.signature(dues.dues_rows).parameters

    assert "session" not in parameters, (
        "dues.dues_rows has grown a session parameter. The per-seat loop "
        "lives in that module, so a module that cannot reach a session "
        "cannot add a query per row -- which is how the N+1 obligation "
        "is a property of the module graph rather than a rule someone "
        "must remember [NFR20.32]."
    )

    source = inspect.getsource(dues)
    assert "Session" not in source, (
        "app/analytics/dues.py imports a Session type. See above."
    )


def test_the_earnings_module_holds_no_io(
    owner_session: Session,
    restricted_session: Session,
) -> None:
    """``earnings.py`` has no session either [logical-components § 1].

    Which is what makes the double-count test runnable without a
    database, and the arithmetic testable at unit speed.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :return: None
    """
    import inspect

    from app.analytics import earnings

    source = inspect.getsource(earnings)

    assert "Session" not in source
    assert "sqlalchemy" not in source
