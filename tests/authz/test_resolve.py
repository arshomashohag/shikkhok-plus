"""Lens resolution. The two tests at the top carry the whole rule.

**A cached lens is indistinguishable from a computed one on every happy
path.** Only a mid-session ownership change tells them apart, which is
what BR1.2 and BR1.3 describe -- and why they are named rules rather than
incidental tests. A reader who does not know that will delete them as
redundant with BR1.1.

These were written before ``app/authz/resolve.py`` existed, because the
predicate holds: the correct output is knowable from the requirement, and
a wrong answer is an authorization error.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.authz.resolve import LensResolver, available_lenses
from app.db.models import Account, Enrollment, Owner


@pytest.fixture
def account(owner_session: Session) -> uuid.UUID:
    """Create one account with neither ownership nor enrollment.

    :param owner_session: A session able to arrange fixture data
    :return: The new account's id
    """
    record = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(record)
    owner_session.commit()
    return record.id


def _grant_ownership(session: Session, account_id: uuid.UUID) -> None:
    """Insert an ``Owner`` row, as the seed script would.

    :param session: An arranging session
    :param account_id: The account gaining ownership
    :return: None
    """
    session.add(Owner(account_id=account_id, created_at=dt.datetime.now(tz=dt.UTC)))
    session.commit()


def _enroll(session: Session, account_id: uuid.UUID, role: str) -> uuid.UUID:
    """Insert an ``Enrollment`` row seating the account in a role.

    **The two roles are two COLUMNS on one row, not two rows** [BR5.0].
    U3's shell seated one account per row and said which part it played;
    U4 puts both links side by side, which is what lets a guardian's
    enrollment identify the child.

    :param session: An arranging session
    :param account_id: The account being enrolled
    :param role: ``student`` or ``guardian``
    :return: The new enrollment's id
    """
    links: dict[str, uuid.UUID] = (
        {"student_account_id": account_id}
        if role == "student"
        else {"guardian_account_id": account_id}
    )
    # D1 added two per-link decision columns with no default [ADR-013],
    # so this helper states both. ACCEPTED for the link it seats,
    # because every test in this file asserts a lens is granted or
    # withdrawn by OWNERSHIP and ENROLLMENT changes -- an unaccepted
    # link would withhold the lens for a different reason and each of
    # those assertions would pass vacuously.
    decisions = {
        "student_decision": "accepted" if role == "student" else "pending",
        "guardian_decision": "accepted" if role == "guardian" else "pending",
    }
    record = Enrollment(
        batch_id=uuid.uuid4(),
        display_name="Teacher Typed Name",
        created_at=dt.datetime.now(tz=dt.UTC),
        **decisions,
        **links,
    )
    session.add(record)
    session.commit()
    return record.id


# ---------------------------------------------------------------------------
# THE TWO THAT CARRY THE RULE. [BR1.2, BR1.3]
#
# Each fails against a cached lens and passes against every other
# implementation, correct or not. That is their only job.
# ---------------------------------------------------------------------------


def test_ownership_gained_mid_session_grants_the_teacher_lens_next_request(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    resolver = LensResolver(restricted_session)

    first = resolver.resolve(_FakeRequest(), account)
    assert not any(isinstance(lens, TeacherLens) for lens in first)

    _grant_ownership(owner_session, account)

    # A NEW request. A cache keyed on the account returns the
    # pre-creation answer here, and that is the defect [BR1.2].
    second = resolver.resolve(_FakeRequest(), account)
    assert any(isinstance(lens, TeacherLens) for lens in second)


def test_losing_the_last_enrollment_removes_the_student_lens_next_request(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    enrollment_id = _enroll(owner_session, account, "student")
    resolver = LensResolver(restricted_session)

    first = resolver.resolve(_FakeRequest(), account)
    assert any(isinstance(lens, StudentLens) for lens in first)

    owner_session.execute(sa.delete(Enrollment).where(Enrollment.id == enrollment_id))
    owner_session.commit()

    # The more dangerous direction: BR1.2 withholds access someone should
    # have, this one GRANTS access someone should not [BR1.3].
    second = resolver.resolve(_FakeRequest(), account)
    assert not any(isinstance(lens, StudentLens) for lens in second)


# ---------------------------------------------------------------------------
# The lens set itself.
# ---------------------------------------------------------------------------


def test_an_account_with_neither_has_no_lens(
    restricted_session: Session, account: uuid.UUID
) -> None:
    # AC1.2.3 holds for free rather than by a check: the queries simply
    # return nothing.
    assert available_lenses(restricted_session, account) == []


def test_an_account_with_both_has_both_lenses(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    _grant_ownership(owner_session, account)
    _enroll(owner_session, account, "student")

    lenses = available_lenses(restricted_session, account)
    assert any(isinstance(lens, TeacherLens) for lens in lenses)
    assert any(isinstance(lens, StudentLens) for lens in lenses)


def test_a_guardian_only_account_gets_no_student_lens(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    _enroll(owner_session, account, "guardian")

    lenses = available_lenses(restricted_session, account)
    assert any(isinstance(lens, GuardianLens) for lens in lenses)
    assert not any(isinstance(lens, StudentLens) for lens in lenses)


def test_a_student_only_account_gets_no_guardian_lens(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    _enroll(owner_session, account, "student")

    lenses = available_lenses(restricted_session, account)
    assert any(isinstance(lens, StudentLens) for lens in lenses)
    assert not any(isinstance(lens, GuardianLens) for lens in lenses)


def test_the_lens_is_never_read_from_a_column() -> None:
    # The absence IS the mechanism. A role column here would be the exact
    # stale-role defect the rule exists to prevent, and it would look
    # entirely reasonable to whoever added it [BR1.1].
    columns = {column.name for column in Account.__table__.columns}
    assert not columns & {"role", "is_teacher", "kind", "lens", "account_type"}


class _FakeRequest:
    """A stand-in carrying only the attribute the memo lives on.

    Using the real ``Request`` would need an ASGI scope and tell us
    nothing extra: BR1.4 is about *where* the memo lives, and that is
    ``request.state`` either way.
    """

    def __init__(self) -> None:
        """Start with an empty state, as a fresh request has.

        :return: None
        """
        self.state = _State()


class _State:
    """The mutable namespace ``request.state`` provides."""
