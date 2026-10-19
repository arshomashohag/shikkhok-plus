"""Step 20 (RED): the roster's query count is constant in N.

**The property is constant-in-N, not minimal.** Asserting a literal
count pins an implementation detail, and the first time a correct change
moves it the number gets raised rather than investigated -- which is how
this check gets retired. Comparing two sizes asserts the thing that
actually matters: adding students must not add queries.

**Both sizes sit below SQLAlchemy's 500-row ``selectinload`` chunk
boundary**, which is the trap in this test rather than a detail. A
correct implementation using ``selectinload`` issues a second query once
a collection exceeds 500 rows, so a test comparing N=2 against N=600
would fail against working code and the obvious "fix" would be to delete
the assertion. 2 and 25 are both under it, verified against the
installed version.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import list_roster
from tests.batches.conftest import TeacherFixture, _account, enroll, make_teacher


class QueryCounter:
    """Count the statements issued through one engine.

    :ivar count: How many statements were executed while active
    """

    def __init__(self) -> None:
        """Start a counter at zero.

        :return: None
        """
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


def _roster_of_size(owner_session: Session, size: int) -> TeacherFixture:
    """Build a teacher whose batch holds ``size`` seats.

    :param owner_session: A session able to arrange fixture data
    :param size: How many enrollments to create
    :return: The teacher
    """
    teacher = make_teacher(owner_session, name=f"Batch of {size}")
    for index in range(size):
        enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=f"Student {index:03d}",
            student_account_id=_account(owner_session),
        )
    return teacher


def test_the_roster_query_count_does_not_grow_with_the_roster(
    restricted_session: Session, owner_session: Session, counted: QueryCounter
) -> None:
    """The same number of queries at N=2 and N=25.

    A one-row fixture cannot see N+1 at all: one row produces one
    follow-up query, which is indistinguishable from none. Two sizes are
    the minimum that can tell the shapes apart.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param counted: The statement counter
    :return: None
    """
    small = _roster_of_size(owner_session, 2)
    large = _roster_of_size(owner_session, 25)

    counted.count = 0
    list_roster(
        restricted_session,
        lens=TeacherLens(account_id=small.account_id, owner_id=small.owner_id),
        batch_id=small.batch_id,
    )
    small_queries = counted.count

    counted.count = 0
    list_roster(
        restricted_session,
        lens=TeacherLens(account_id=large.account_id, owner_id=large.owner_id),
        batch_id=large.batch_id,
    )
    large_queries = counted.count

    assert small_queries == large_queries, (
        f"{small_queries} queries for 2 seats and {large_queries} for 25: "
        "the count grows with the roster, which is the N+1 shape"
    )


def test_the_fixture_sizes_are_below_sqlalchemys_chunk_boundary() -> None:
    """The sizes are deliberate, and this pins why.

    SQLAlchemy chunks ``selectinload`` at 500 rows, so a correct
    implementation issues an extra query past that. A fixture above the
    boundary would fail this suite against working code, and the
    cheapest fix would be deleting the assertion rather than resizing
    the fixture.

    The constant is read defensively: it is private and has been renamed
    between versions, so a missing symbol skips rather than failing. The
    point of this test is to document the reasoning behind 2 and 25, not
    to police SQLAlchemy's internals.

    :return: None
    """
    from sqlalchemy.orm import strategies

    loader = getattr(strategies, "_SelectInLoader", None) or getattr(
        strategies, "SelectInLoader", None
    )
    if loader is None:  # pragma: no cover - version-dependent
        pytest.skip("SQLAlchemy's selectin loader is not where it was")

    chunk_size = loader._chunksize
    assert 2 < chunk_size
    assert 25 < chunk_size
