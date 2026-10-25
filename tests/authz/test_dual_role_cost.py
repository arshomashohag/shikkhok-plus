"""One phone number that is both a teacher and a guardian.

**The case `FR1.4` names, measured rather than reasoned about.** A tutor
whose own child is tutored by someone else is one account with two
lenses, and the question worth answering is whether resolving both
costs more than resolving one.

It does not. The resolver issues ONE statement whose three subqueries
each hit an index, so an account with every lens costs exactly what an
account with none costs. These tests assert that equality, because the
tempting "optimization" -- resolving lenses lazily, one query per lens
as it is needed -- would make the dual-role account the expensive one
and would do so invisibly.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.authz.resolve import available_lenses
from app.money import Money
from tests.batches.conftest import _account, enroll, make_teacher
from tests.batches.test_query_count import QueryCounter


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


def _make_everything_account(session: Session) -> uuid.UUID:
    """Build one account that is teacher, student and guardian at once.

    :param session: A session able to arrange fixture data
    :return: The account id carrying all three lenses
    """
    from app.db.models import Batch, Owner

    account_id = _account(session)

    # Teacher: owns a batch of their own.
    owner = Owner(account_id=account_id, created_at=dt.datetime.now(tz=dt.UTC))
    session.add(owner)
    session.commit()
    session.add(
        Batch(
            owner_id=owner.id,
            name="What they teach",
            default_fee=Money("1500.00"),
            fee_due_day=10,
            marksheet_visible=True,
            active=True,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    session.commit()

    # Student: enrolled in somebody else's batch.
    other = make_teacher(session, name="Where they study")
    enroll(
        session,
        batch_id=other.batch_id,
        display_name="Themselves",
        student_account_id=account_id,
    )

    # Guardian: named as the guardian of a child in a third batch.
    third = make_teacher(session, name="Where their child studies")
    enroll(
        session,
        batch_id=third.batch_id,
        display_name="Their child",
        student_account_id=_account(session),
        guardian_account_id=account_id,
    )

    return account_id


def test_all_three_lenses_resolve_for_one_account(
    restricted_session: Session, owner_session: Session
) -> None:
    """One account carries teacher, student and guardian together.

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account_id = _make_everything_account(owner_session)

    lenses = available_lenses(restricted_session, account_id)

    kinds = {type(lens) for lens in lenses}
    assert kinds == {TeacherLens, StudentLens, GuardianLens}


def test_every_lens_resolves_in_one_statement(
    restricted_session: Session, owner_session: Session, counted: QueryCounter
) -> None:
    """Resolution is ONE statement, whatever lenses the account has.

    **The count is asserted literally, and that is deliberate here.**
    The project's other query-count test argues against literal counts
    and asserts constant-in-N instead, which is right for a roster: the
    number there is an implementation detail and the growth is the
    requirement.

    This is the opposite case. "One statement" IS the requirement
    [NFR6.1] -- the resolver's own comment records that three round
    trips per request is exactly what makes caching a lens look
    necessary, and a cached lens is what `BR1.1` forbids. So the
    number is the property.

    An earlier version of this test compared the cost of a
    three-lens account against a no-lens account and asserted
    equality. It passed against a deliberately injected per-lens
    resolver issuing three queries -- because three equals three. The
    equality was true and worthless; verified by injection, not
    noticed by reading.

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :param counted: The statement counter
    :return: None
    """
    everything = _make_everything_account(owner_session)
    nothing = _account(owner_session)

    for label, account_id in (("all three", everything), ("none", nothing)):
        before = counted.count
        available_lenses(restricted_session, account_id)
        issued = counted.count - before
        assert issued == 1, (
            f"resolving {label} took {issued} statements, not 1 -- "
            "a per-lens resolver makes the dual-role account the "
            "expensive one and makes caching the lens look necessary"
        )


def test_the_teacher_lens_scopes_to_their_own_batch_only(
    restricted_session: Session, owner_session: Session
) -> None:
    """A dual-role account's teacher lens sees only what it owns.

    The failure this guards against is the one that matters for this
    account shape: three batches are related to it, and only one is
    its own. A teacher-facing read must not widen to the batch where
    they are a student, nor to their child's.

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from app.batches.service import list_batches

    account_id = _make_everything_account(owner_session)
    teacher = next(
        lens
        for lens in available_lenses(restricted_session, account_id)
        if isinstance(lens, TeacherLens)
    )

    names = [
        summary.batch.name for summary in list_batches(restricted_session, lens=teacher)
    ]

    assert names == ["What they teach"]


def test_the_guardian_lens_reaches_the_child_not_the_guardian(
    restricted_session: Session, owner_session: Session
) -> None:
    """The guardian lens carries the child's enrollment, not their own.

    This is the correction `BR5.0` records: resolving a guardian by
    their own account id identifies the guardian but cannot say WHICH
    child, because nothing linked the two rows except a shared batch.
    With both links on one row, the enrollment the guardian reaches IS
    the child's.

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account_id = _make_everything_account(owner_session)

    guardian = next(
        lens
        for lens in available_lenses(restricted_session, account_id)
        if isinstance(lens, GuardianLens)
    )

    # The enrollment reached is the CHILD's seat, so its own student
    # account is somebody else -- never the guardian themselves.
    from app.db.models import Enrollment

    seat = restricted_session.get(Enrollment, guardian.child_enrollment_id)
    assert seat is not None
    assert seat.guardian_account_id == account_id
    assert seat.student_account_id != account_id
    assert seat.display_name == "Their child"
