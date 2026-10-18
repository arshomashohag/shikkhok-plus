"""Adversarial probes against the built boundary.

**Not "does a teacher see the right name" but "can a teacher reach the
wrong one".** The confirmatory question is answered by a correct query
over a broken policy; only the adversarial one distinguishes them.

Three routes to the same data, because an implementation can block one
and leave another open: a direct query, a join, and an ORM traversal. The
join is the one a real teacher-facing query would most plausibly contain
[BR3.1].

Every test here runs after the meta-test, and the package conftest
refuses to let a probe report a pass when the boundary is not actually in
force.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.rls import clear_account_context, set_account_context
from app.db.models import Account, Enrollment, Profile

TEACHER_TYPED_NAME = "Rahim (class 8)"
SELF_CHOSEN_NAME = "Md. Rahim Uddin"


@pytest.fixture
def student(owner_session: Session) -> uuid.UUID:
    """Create a student with both a profile and an enrollment.

    The two names are deliberately different, so a test cannot pass by
    reading the wrong table and finding the right string.

    :param owner_session: A session able to arrange fixture data
    :return: The student's account id
    """
    account = Account(
        phone=f"+8801{uuid.uuid4().int % 10**9:09d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(account)
    owner_session.commit()

    owner_session.add(
        Profile(account_id=account.id, self_name=SELF_CHOSEN_NAME, photo_ref=None)
    )
    owner_session.add(
        Enrollment(
            batch_id=uuid.uuid4(),
            student_account_id=account.id,
            display_name=TEACHER_TYPED_NAME,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    owner_session.commit()
    return account.id


@pytest.fixture
def teacher(owner_session: Session) -> uuid.UUID:
    """Create a teacher account, which owns no profile of the student's.

    :param owner_session: A session able to arrange fixture data
    :return: The teacher's account id
    """
    account = Account(
        phone=f"+8801{uuid.uuid4().int % 10**9:09d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(account)
    owner_session.commit()
    return account.id


# ---------------------------------------------------------------------------
# CAN A TEACHER REACH THE PROFILE? Three routes, all must return nothing.
# ---------------------------------------------------------------------------


def test_a_direct_query_returns_zero_rows(
    restricted_session: Session, student: uuid.UUID, teacher: uuid.UUID
) -> None:
    set_account_context(restricted_session, teacher)
    rows = restricted_session.execute(
        sa.text("SELECT self_name FROM profile WHERE account_id = :id"),
        {"id": student},
    ).all()
    assert rows == []


def test_a_join_returns_zero_profile_rows(
    restricted_session: Session, student: uuid.UUID, teacher: uuid.UUID
) -> None:
    # THE PLAUSIBLE SHAPE. A teacher-facing roster query that reaches
    # Profile does so through a join, not a direct select.
    set_account_context(restricted_session, teacher)
    rows = restricted_session.execute(
        sa.text(
            "SELECT p.self_name FROM enrollment e "
            "JOIN profile p ON p.account_id = e.student_account_id "
            "WHERE e.student_account_id = :id"
        ),
        {"id": student},
    ).all()
    assert rows == []


def test_an_orm_traversal_returns_zero_rows(
    restricted_session: Session, student: uuid.UUID, teacher: uuid.UUID
) -> None:
    set_account_context(restricted_session, teacher)
    found = (
        restricted_session.query(Profile).filter(Profile.account_id == student).all()
    )
    assert found == []


def test_an_unscoped_select_star_returns_nothing(
    restricted_session: Session, student: uuid.UUID, teacher: uuid.UUID
) -> None:
    # The query someone runs while debugging, which is exactly when a
    # leak would be copied somewhere it should not go.
    set_account_context(restricted_session, teacher)
    rows = restricted_session.execute(sa.text("SELECT * FROM profile")).all()
    assert rows == []


def test_a_session_with_no_account_context_sees_nothing(
    restricted_session: Session, student: uuid.UUID
) -> None:
    # Failing CLOSED matters: an unset context must deny rather than
    # admit everything, or a missing middleware call opens the table.
    clear_account_context(restricted_session)
    rows = restricted_session.execute(sa.text("SELECT * FROM profile")).all()
    assert rows == []


# ---------------------------------------------------------------------------
# What the owner CAN see, so the policy is not simply denying everything.
# ---------------------------------------------------------------------------


def test_an_owner_reads_their_own_profile(
    restricted_session: Session, student: uuid.UUID
) -> None:
    # Without this the suite above would pass against a policy that
    # denies unconditionally, which is not the requirement.
    set_account_context(restricted_session, student)
    name = restricted_session.execute(
        sa.text("SELECT self_name FROM profile WHERE account_id = :id"),
        {"id": student},
    ).scalar_one()
    assert name == SELF_CHOSEN_NAME


def test_a_teacher_reads_the_teacher_typed_name_successfully(
    restricted_session: Session, student: uuid.UUID, teacher: uuid.UUID
) -> None:
    # The boundary is a TABLE SPLIT, not a blanket denial: the teacher's
    # own roster read must still work [BR3.1].
    set_account_context(restricted_session, teacher)
    name = restricted_session.execute(
        sa.text("SELECT display_name FROM enrollment WHERE student_account_id = :id"),
        {"id": student},
    ).scalar_one()
    assert name == TEACHER_TYPED_NAME


# ---------------------------------------------------------------------------
# The split itself. [BR3.1]
# ---------------------------------------------------------------------------


def test_the_two_names_live_in_different_tables() -> None:
    # "Which name does a teacher see" is answered by WHICH TABLE THE
    # QUERY READS, rather than by a filter someone remembers to apply.
    assert "self_name" in Profile.__table__.columns
    assert "self_name" not in Enrollment.__table__.columns
    assert "display_name" in Enrollment.__table__.columns
    assert "display_name" not in Profile.__table__.columns


def test_the_profile_table_carries_no_teacher_typed_field() -> None:
    assert set(Profile.__table__.columns.keys()) == {
        "account_id",
        "self_name",
        "photo_ref",
    }


def test_row_level_security_is_not_enabled_on_enrollment(
    restricted_session: Session,
) -> None:
    # Stated as a test because enabling RLS here would be a plausible
    # "more security" change that silently breaks the teacher's
    # legitimate roster read. The boundary is the table SPLIT; RLS
    # protects only the owner-private side [BR3.1, BR3.2].
    enabled = restricted_session.execute(
        sa.text("SELECT relrowsecurity FROM pg_class WHERE relname = 'enrollment'")
    ).scalar_one()
    assert enabled is False
