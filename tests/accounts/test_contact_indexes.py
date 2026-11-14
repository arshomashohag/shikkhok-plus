"""The email statements can use their indexes; the new rows are purged.

Written from the requirements, after the implementation.

* **NFR8.3**: every statement U2 adds that finds rows by a recorded email
  can use a partial index. With ``enable_seqscan`` off, each statement's
  plan names the intended index. This proves the index is USABLE, not
  that the query is fast; the latency figures are a manual staging
  reading, and nothing automated discharges them (performance NFR8.1,
  8.2, 8.6, 8.7).
* **NFR8.10**: the new ``contact_chg_day`` counters and ``contact_replace``
  codes are removed by the existing retention purge, which works by age
  and not by a list of scopes or purposes.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.service import _EMAIL_LOOKUP_QUERY
from app.centres.memberships import _LINK
from app.students.service import _LINK_GUARDIANS, _LINK_STUDENTS

_PARAMS = {
    "value": "plan@example.com",
    "email": "plan@example.com",
    "account_id": uuid.uuid4(),
    "o": uuid.uuid4(),
}


def _plan(session: Session, statement: sa.TextClause) -> str:
    """EXPLAIN a statement with sequential scans disabled, without running it.

    :param session: The application's role
    :param statement: The statement
    :return: The plan text
    """
    session.execute(sa.text("SET LOCAL enable_seqscan = off"))
    rows = session.execute(sa.text("EXPLAIN " + statement.text), _PARAMS).scalars()
    plan = "\n".join(rows)
    session.rollback()
    return plan


@pytest.mark.parametrize(
    ("name", "statement", "indexes"),
    [
        ("match guardian", _LINK_GUARDIANS["email"], ["ix_enrollment_guardian_email"]),
        ("match student", _LINK_STUDENTS["email"], ["ix_enrollment_student_email"]),
        (
            "match invitation",
            _LINK["email"],
            # Either partial email index on the table serves it; the planner
            # picks by cost.
            ["ix_owner_member_unlinked_email|uq_owner_member_live_email"],
        ),
        (
            "email lookup",
            _EMAIL_LOOKUP_QUERY,
            ["ix_enrollment_student_email", "ix_enrollment_guardian_email"],
        ),
        (
            "student email taken",
            sa.text(
                "SELECT id FROM student WHERE owner_id = :o AND student_email = :email"
            ),
            ["uq_student_owner_email"],
        ),
        (
            "live invitation",
            sa.text(
                "SELECT id FROM owner_member WHERE owner_id = :o "
                "AND invited_email = :email AND revoked_at IS NULL"
            ),
            ["uq_owner_member_live_email"],
        ),
    ],
)
def test_each_email_statement_can_use_its_partial_index(
    restricted_session: Session,
    name: str,
    statement: sa.TextClause,
    indexes: list[str],
) -> None:
    """The plan names the intended index [NFR8.3, NFR8.8].

    :param restricted_session: The application's role
    :param name: Which statement, for the report
    :param statement: The statement
    :param indexes: The indexes its plan must name; ``a|b`` means either
    :return: None
    """
    plan = _plan(restricted_session, statement)

    for index in indexes:
        assert any(alt in plan for alt in index.split("|")), (
            f"{name}: {index} not used\n{plan}"
        )


def test_the_purge_removes_aged_change_counters_and_replacement_codes(
    owner_session: Session, restricted_session: Session
) -> None:
    """Purged by age, whatever the scope or purpose [NFR8.10].

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    from app.governance.commands import purge_expired

    old = dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=30)
    owner_session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter (id, scope_kind, scope_value, "
            "window_start, count) VALUES (gen_random_uuid(), 'contact_chg_day', "
            ":a, :w, 3)"
        ),
        {"a": str(uuid.uuid4()), "w": old},
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO otp_request (id, email, otp_hash, purpose, issued_at, "
            "expires_at) VALUES (gen_random_uuid(), 'purged@example.com', :h, "
            "'contact_replace', :w, :w)"
        ),
        {"h": "0" * 64, "w": old},
    )
    owner_session.commit()

    purge_expired(restricted_session)
    restricted_session.commit()

    owner_session.expire_all()
    left = owner_session.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM rate_limit_counter "
            "WHERE scope_kind = 'contact_chg_day'), "
            "(SELECT count(*) FROM otp_request WHERE purpose = 'contact_replace')"
        )
    ).one()
    assert tuple(left) == (0, 0)
