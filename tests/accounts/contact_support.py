"""Arrange seats, invitations and accounts that carry phones and emails.

Shared by the contact suites of U2 [0034]: the matcher, the teacher
edit, the lookup, contact changes and deletion markers. Every helper
writes through an ARRANGING session and commits, so the assertions that
follow are made through the restricted role the application uses, never
through the table owner [pg-rls].

Addresses use the reserved ``example.com`` domain and numbers the
suite's ``+88017`` range, so nothing here is a real person's contact.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.db.models import Enrollment, Owner, OwnerMember, Student

__all__ = [
    "PASSWORD",
    "SeatLinks",
    "account",
    "address",
    "centre",
    "code_for",
    "invitation",
    "member_link",
    "number",
    "seat",
    "seat_links",
    "signup_form",
]

#: The password arranged accounts carry when a test needs one.
PASSWORD = "a long enough passphrase"  # noqa: S105 -- a test value


def number() -> str:
    """Return a fresh canonical mobile number.

    :return: ``+88017`` and eight random digits
    """
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


def address() -> str:
    """Return a fresh, lowercased email address on a reserved domain.

    :return: A unique address
    """
    return f"person-{uuid.uuid4().hex[:12]}@example.com"


def signup_form(role: str = "student", **identifier: str) -> dict[str, str]:
    """Build a sign-up form for one identifier.

    :param role: The role claimed
    :param identifier: ``phone=...`` or ``email=...``
    :return: The request body
    """
    return {
        **identifier,
        "role": role,
        "self_name": "Someone",
        "address_house": "House 12",
        "address_road": "Road 5",
        "address_city": "Dhaka",
        "address_postcode": "1205",
    }


def code_for(sent: list[tuple[str, str]], destination: str) -> str:
    """Read the latest code sent to one destination.

    :param sent: The captured ``(destination, body)`` sends
    :param destination: The number or address
    :return: The six-digit code
    """
    body = next(text for to, text in reversed(sent) if to == destination)
    return next(part for part in body.split() if part.isdigit() and len(part) == 6)


def account(
    session: Session,
    *,
    phone: str | None = None,
    email: str | None = None,
    password: str | None = None,
) -> uuid.UUID:
    """Arrange an account holding the given contacts.

    :param session: An arranging session
    :param phone: Its number, or None
    :param email: Its address, or None
    :param password: Its password, or None for none
    :return: The account id
    """
    if phone is None and email is None:
        phone = number()
    account_id = uuid.uuid4()
    now = dt.datetime.now(tz=dt.UTC)
    session.execute(
        sa.text(
            "INSERT INTO account (id, phone, email, password_hash, "
            "password_changed_at, created_at, activated_at) "
            "VALUES (:id, :p, :e, :h, :c, :now, :now)"
        ),
        {
            "id": account_id,
            "p": phone,
            "e": email,
            "h": hash_password(password) if password else None,
            "c": now if password else None,
            "now": now,
        },
    )
    session.commit()
    return account_id


def seat(
    session: Session,
    batch_id: uuid.UUID,
    **fields: Any,
) -> uuid.UUID:
    """Arrange one seat, and the student it belongs to, with contacts.

    The student row carries the same four contacts as the seat, as the
    service keeps them [BR1.5]. Decisions default to ``pending``: naming
    somebody is not their agreement.

    :param session: An arranging session
    :param batch_id: The batch
    :param fields: Any ``Enrollment`` column to set, e.g.
        ``student_email=...`` or ``guardian_relink_blocked_at=...``
    :return: The seat id
    """
    owner_id = session.execute(
        sa.text("SELECT owner_id FROM batch WHERE id = :b"), {"b": batch_id}
    ).scalar_one()
    now = dt.datetime.now(tz=dt.UTC)
    # The teacher's student who already has this number or address is the
    # same student, seated in one more batch [D2]; a second record would
    # break the per-teacher uniqueness the schema enforces [BR1.2].
    clauses = [
        getattr(Student, column) == fields[column]
        for column in ("student_phone", "student_email")
        if fields.get(column) is not None
    ]
    student = (
        session.execute(
            sa.select(Student).where(Student.owner_id == owner_id, sa.or_(*clauses))
        ).scalar_one_or_none()
        if clauses
        else None
    )
    if student is None:
        student = Student(
            owner_id=owner_id,
            display_name=fields.get("display_name", "Rahim"),
            student_phone=fields.get("student_phone"),
            guardian_phone=fields.get("guardian_phone"),
            student_email=fields.get("student_email"),
            guardian_email=fields.get("guardian_email"),
            created_at=now,
        )
        session.add(student)
        session.flush()
    values: dict[str, Any] = {
        "display_name": "Rahim",
        "student_decision": "pending",
        "guardian_decision": "pending",
        **fields,
    }
    record = Enrollment(
        batch_id=batch_id, student_id=student.id, created_at=now, **values
    )
    session.add(record)
    session.commit()
    return record.id


@dataclass(frozen=True, slots=True)
class SeatLinks:
    """One seat's two links and their decisions, read fresh.

    :ivar student: The student link's account
    :ivar guardian: The guardian link's account
    :ivar student_decision: The student link's decision
    :ivar guardian_decision: The guardian link's decision
    """

    student: uuid.UUID | None
    guardian: uuid.UUID | None
    student_decision: str
    guardian_decision: str


def seat_links(session: Session, seat_id: uuid.UUID) -> SeatLinks:
    """Read one seat's links fresh from the database.

    :param session: Any session
    :param seat_id: The seat
    :return: Its links and decisions
    """
    session.expire_all()
    row = session.execute(
        sa.text(
            "SELECT student_account_id, guardian_account_id, student_decision, "
            "guardian_decision FROM enrollment WHERE id = :e"
        ),
        {"e": seat_id},
    ).one()
    session.commit()
    return SeatLinks(*row)


def centre(session: Session) -> uuid.UUID:
    """Arrange a coaching centre with no members.

    :param session: An arranging session
    :return: The centre's owner id
    """
    owner = Owner(
        account_id=None,
        kind="organisation",
        name="Centre",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(owner)
    session.commit()
    return owner.id


def invitation(
    session: Session,
    centre_id: uuid.UUID,
    *,
    phone: str | None = None,
    email: str | None = None,
    account_id: uuid.UUID | None = None,
    revoked: bool = False,
) -> uuid.UUID:
    """Arrange one teacher invitation to a centre.

    :param session: An arranging session
    :param centre_id: The centre
    :param phone: The invited number, or None
    :param email: The invited address, or None
    :param account_id: The linked account, or None
    :param revoked: Whether the invitation is already ended
    :return: The membership id
    """
    now = dt.datetime.now(tz=dt.UTC)
    member = OwnerMember(
        owner_id=centre_id,
        account_id=account_id,
        invited_phone=phone,
        invited_email=email,
        display_name="Teacher",
        role="teacher",
        decision="pending",
        created_at=now,
        revoked_at=now if revoked else None,
    )
    session.add(member)
    session.commit()
    return member.id


def member_link(session: Session, member_id: uuid.UUID) -> tuple[uuid.UUID | None, str]:
    """Read one invitation's link and decision fresh.

    :param session: Any session
    :param member_id: The membership
    :return: Its account and its decision
    """
    session.expire_all()
    row = session.execute(
        sa.text("SELECT account_id, decision FROM owner_member WHERE id = :m"),
        {"m": member_id},
    ).one()
    session.commit()
    return row[0], row[1]


def auth(client: TestClient, session: Session, account_id: uuid.UUID) -> dict[str, str]:
    """Authorize as an account (kept here so suites import one module).

    :param client: Unused; keeps call sites symmetric with the routes
    :param session: A session to write the token family through
    :param account_id: The account
    :return: The header mapping
    """
    del client
    from tests.conftest import bearer

    headers = bearer(session, account_id)
    session.commit()
    return headers
