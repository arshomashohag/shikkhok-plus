"""The batch fee view's query count is constant in N [NFR20.16-.18].

**The property is constant-in-N, not minimal.** Asserting a literal
count pins an implementation detail, and the first time a correct change
moves it the number gets raised rather than investigated -- which is how
this check gets retired. Comparing two sizes asserts the thing that
actually matters: adding students must not add queries.

The harness is D2's, deliberately: `tests/batches/test_query_count.py`
established it for the roster, and NFR20.17 says D3 "closes what D2
deliberately left open, and must not close it with a query per seat".
Reusing the counter rather than writing a second one keeps the two
answering the same question.

**NFR20.18 is why this is a statement count and not a latency
assertion.** A latency figure on one 2 GB host is flaky and fails for
the wrong reason; a statement count is deterministic.

Both sizes sit below SQLAlchemy's 500-row chunk boundary, for the
reason D2's file records: a correct implementation can issue a second
query past it, so a test spanning that boundary would fail against
working code and the obvious "fix" would be to delete the assertion.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import FeeCycle
from app.fees import views
from app.fees.ledger_writer import append_entry
from app.money import Money
from tests.batches.conftest import TeacherFixture, _account, enroll, make_teacher


class QueryCounter:
    """Count the statements issued through one engine.

    :ivar count: How many statements were executed while active
    """

    def __init__(self) -> None:
        """Start a counter at zero."""
        self.count = 0

    def __call__(self, *args: object, **kwargs: object) -> None:
        """Record one statement.

        :param args: The event payload, unused
        :param kwargs: The event payload, unused
        :return: None
        """
        self.count += 1


@pytest.fixture
def counted(restricted_session: Session) -> Iterator[QueryCounter]:
    """Count statements issued on the session's engine.

    :param restricted_session: The session under test
    :return: A context manager yielding the counter
    """
    counter = QueryCounter()
    engine: Engine = restricted_session.get_bind()
    sa.event.listen(engine, "before_cursor_execute", counter)
    yield counter
    sa.event.remove(engine, "before_cursor_execute", counter)


def _charged_batch(
    owner_session: Session,
    restricted_session: Session,
    size: int,
) -> TeacherFixture:
    """Build a teacher whose batch holds ``size`` charged seats.

    Each seat carries a generated cycle AND a charge, because a seat
    with no ledger row exercises none of the per-seat work this test
    exists to detect.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session the charges are written on
    :param size: How many enrollments to create
    :return: The teacher
    """
    teacher = make_teacher(owner_session, name=f"Fees of {size}")
    for index in range(size):
        seat = enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=f"Student {index:03d}",
            student_account_id=_account(owner_session),
        )
        restricted_session.add(
            FeeCycle(
                enrollment_id=seat,
                period="2027-02",
                due_date=dt.date(2027, 2, 28),
                created_at=dt.datetime.now(tz=dt.UTC),
            )
        )
        append_entry(
            restricted_session,
            enrollment_id=seat,
            period="2027-02",
            kind="charge",
            amount=Money("1000.00"),
        )
    restricted_session.commit()
    return teacher


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the teacher lens for a fixture.

    :param teacher: The teacher
    :return: Their lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def test_the_batch_fee_view_query_count_does_not_grow_with_the_batch(
    restricted_session: Session,
    owner_session: Session,
    counted: QueryCounter,
) -> None:
    """The same number of queries at N=2 and N=25.

    A one-row fixture cannot see N+1 at all: one row produces one
    follow-up query, which is indistinguishable from none. Two sizes
    are the minimum that can tell the shapes apart.

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :param counted: The statement counter
    :return: None
    """
    small = _charged_batch(owner_session, restricted_session, 2)
    large = _charged_batch(owner_session, restricted_session, 25)

    counted.count = 0
    views.batch_fee_overview(
        restricted_session, lens=_lens(small), batch_id=small.batch_id
    )
    at_two = counted.count

    counted.count = 0
    views.batch_fee_overview(
        restricted_session, lens=_lens(large), batch_id=large.batch_id
    )
    at_twenty_five = counted.count

    assert at_two == at_twenty_five, (
        f"{at_two} statements for 2 seats and {at_twenty_five} for 25: the "
        "batch fee view issues a query per seat [NFR20.16, NFR20.17]. D2 "
        "left the roster's fee column open deliberately, and D3 must not "
        "close it with an N+1."
    )


def test_the_roster_fee_read_is_one_fold_per_enrollment_not_three(
    restricted_session: Session,
    owner_session: Session,
    counted: QueryCounter,
) -> None:
    """Deriving a seat's position reads its ledger once, not repeatedly.

    The shape this guards against is subtler than N+1 and was the
    actual defect: ``derive_for_enrollment`` and ``fee_status`` each
    fold the same enrollment's entries, so a naive row builder reads
    one seat's ledger twice and its cycles a third time. At N=1 that is
    three statements where one would do, and it multiplies by N.

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :param counted: The statement counter
    :return: None
    """
    teacher = _charged_batch(owner_session, restricted_session, 4)

    counted.count = 0
    views.batch_fee_overview(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
    )

    # A constant handful: the batch lookup, the seats, the ledger and
    # the cycles. The bound is deliberately generous -- the property
    # under test is the absence of per-seat growth, which the test
    # above asserts directly -- but it must exclude the three-reads-
    # per-seat shape, which at N=4 would be at least twelve.
    assert counted.count <= 8, (
        f"{counted.count} statements for a 4-seat batch. Each seat's "
        "ledger is being folded more than once; derive and the status "
        "computation must share one read [NFR20.16]."
    )
