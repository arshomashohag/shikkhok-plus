"""BR1.4: the memo's LOCATION is the control, not its existence.

On ``request.state`` the memo is garbage-collected with the request. In a
module-level dict, an ``lru_cache``, or a Redis key it is not -- and at
the call site the three look identical. That is why the rule names the
mechanism rather than the intent, and why this file counts queries rather
than reading code.

Two assertions, and the pair is what makes it a boundary:

* Two lookups in **one** request hit the database **once**.
* Two **separate** requests hit it **twice**.

An implementation passing only the first is a cache. One passing only the
second has no memo at all and makes lens resolution the hottest query in
the system twice over.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session

from app.authz.resolve import LensResolver
from app.db.models import Account, Owner


class QueryCounter:
    """Count statements issued on one engine.

    A **count**, never a duration [NFR6.3]: a wall-clock assertion is
    flaky and gets deleted the third time CI fails on it.

    :ivar statements: Every statement seen while attached
    """

    def __init__(self) -> None:
        """Start with an empty record.

        :return: None
        """
        self.statements: list[str] = []

    def __call__(
        self,
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        """Record one statement.

        :param conn: The DBAPI connection
        :param cursor: The cursor
        :param statement: The SQL being executed
        :param parameters: Bound parameters
        :param context: The execution context
        :param executemany: Whether this is an executemany
        :return: None
        """
        self.statements.append(statement)

    @property
    def lens_queries(self) -> list[str]:
        """Return only the statements that read the lens tables.

        :return: The matching statements
        """
        return [
            statement
            for statement in self.statements
            if "owner" in statement.lower() or "enrollment" in statement.lower()
        ]


@pytest.fixture
def counter(restricted_engine: Engine) -> Iterator[QueryCounter]:
    """Attach a statement counter to the restricted engine.

    :param restricted_engine: The engine to watch
    :return: A context manager yielding the counter
    """
    recorder = QueryCounter()
    event.listen(restricted_engine, "before_cursor_execute", recorder)
    yield recorder
    event.remove(restricted_engine, "before_cursor_execute", recorder)


@pytest.fixture
def seeded_account(owner_session: Session) -> uuid.UUID:
    """Create an account that owns one batch, so a lens resolves.

    :param owner_session: A session able to arrange fixture data
    :return: The account's id
    """
    record = Account(
        phone=f"+8801{uuid.uuid4().int % 10**9:09d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(record)
    owner_session.commit()
    owner_session.add(
        Owner(account_id=record.id, created_at=dt.datetime.now(tz=dt.UTC))
    )
    owner_session.commit()
    return record.id


def test_two_lookups_in_one_request_hit_the_database_once(
    restricted_session: Session, seeded_account: uuid.UUID, counter: QueryCounter
) -> None:
    resolver = LensResolver(restricted_session)
    request = _FakeRequest()

    counter.statements.clear()
    resolver.resolve(request, seeded_account)
    resolver.resolve(request, seeded_account)

    assert len(counter.lens_queries) == 1, (
        "the second lookup in one request re-queried: the memo is missing"
    )


def test_two_separate_requests_each_hit_the_database(
    restricted_session: Session, seeded_account: uuid.UUID, counter: QueryCounter
) -> None:
    resolver = LensResolver(restricted_session)

    counter.statements.clear()
    resolver.resolve(_FakeRequest(), seeded_account)
    resolver.resolve(_FakeRequest(), seeded_account)

    assert len(counter.lens_queries) == 2, (
        "the second REQUEST reused a memo: that is a cached lens [BR1.1]"
    )


def test_resolution_issues_one_query_not_three(
    restricted_session: Session, seeded_account: uuid.UUID, counter: QueryCounter
) -> None:
    # Three EXISTS booleans in one statement [NFR6.1]. Lens resolution is
    # the hottest query in the system on a 2 GB instance, so the shape is
    # a requirement rather than an optimization.
    counter.statements.clear()
    LensResolver(restricted_session).resolve(_FakeRequest(), seeded_account)
    assert len(counter.lens_queries) == 1


def test_the_memo_lives_on_the_request_object(
    restricted_session: Session, seeded_account: uuid.UUID
) -> None:
    request = _FakeRequest()
    LensResolver(restricted_session).resolve(request, seeded_account)

    # The memo must be reachable on the request and nowhere else. On
    # request.state it dies with the request; in a module dict it does
    # not, and the difference is invisible at the call site.
    assert hasattr(request.state, "lenses")


def test_a_fresh_request_carries_no_memo(
    restricted_session: Session, seeded_account: uuid.UUID
) -> None:
    LensResolver(restricted_session).resolve(_FakeRequest(), seeded_account)
    assert not hasattr(_FakeRequest().state, "lenses")


def test_no_module_level_cache_survives_the_resolver(
    restricted_session: Session, seeded_account: uuid.UUID
) -> None:
    # A second resolver instance must not inherit anything. An lru_cache
    # or a module dict would make this pass only by accident of ordering.
    LensResolver(restricted_session).resolve(_FakeRequest(), seeded_account)

    import app.authz.resolve as module

    cached = [
        name
        for name, value in vars(module).items()
        if not name.startswith("__")
        and (hasattr(value, "cache_info") or isinstance(value, dict | set))
    ]
    assert cached == [], f"module-level cache found: {cached}"


def test_the_rls_session_variable_is_set_during_resolution(
    restricted_session: Session, seeded_account: uuid.UUID
) -> None:
    from app.authz.rls import set_account_context

    set_account_context(restricted_session, seeded_account)
    current = restricted_session.execute(
        sa.text("SELECT current_setting('app.account_id', true)")
    ).scalar_one()
    assert current == str(seeded_account)


class _FakeRequest:
    """A stand-in carrying only the attribute the memo lives on."""

    def __init__(self) -> None:
        """Start with an empty state, as a fresh request has.

        :return: None
        """
        self.state = _State()


class _State:
    """The mutable namespace ``request.state`` provides."""
