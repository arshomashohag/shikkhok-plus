"""Creating an account, and the lookup that pre-fills its form.

Two operations with deliberately opposite disclosure properties, which
is why they sit here together rather than beside the OTP path [BR2.3]:

* :func:`create_account` must not become a second way to ask whether a
  number is known. It refuses a duplicate, which *is* a disclosure --
  but the person making it has demonstrated intent to own the number,
  and the refusal is the uniqueness constraint reporting itself
  [BR4.4].
* :func:`already_added` discloses that a seat exists **by design**.
  That is its whole purpose, and it is why BR2.2 is a separate rule
  applying only to the OTP endpoint. What is bounded here is the WIDTH
  of the disclosure -- never the teacher, never the batch -- not its
  existence.

**Signing up is not accepting** [BR5.1]. Creating an account on a
number that already has seats links the account to them and leaves
every decision column exactly as it was. That is the single most
important behaviour in this Unit and it is an *absence*: nothing in a
diff shows it, which is why :mod:`tests.accounts.test_lookup` asserts
it directly.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.rls import set_account_context
from app.db.models import Account, Owner, Profile
from app.errors import ConflictError

__all__ = [
    "AccountCreated",
    "AlreadyAdded",
    "DuplicateNumber",
    "SignupRole",
    "already_added",
    "create_account",
]


class SignupRole(enum.Enum):
    """What a person says they are when they sign up.

    A **claim**, not a stored role [BR4.2]. Nothing verifies it, and
    nothing persists it: choosing ``TEACHER`` creates an ``Owner`` row
    and the three values have no other consequence. There is no role
    column on ``Account`` and this enum never reaches one -- the lens
    is computed per request from owned batches and accepted seats.

    ``STUDENT`` and ``GUARDIAN`` are therefore indistinguishable in
    their effect, and both are kept because the form asks and the
    already-added path locks the answer to the seat's [BR4.5].
    """

    TEACHER = "teacher"
    STUDENT = "student"
    GUARDIAN = "guardian"


class DuplicateNumber(ConflictError):
    """This number already has an account; the person should log in.

    A :class:`~app.errors.ConflictError` rather than a validation
    failure: the request is well-formed and the state forbids it, so
    the caller is directed elsewhere rather than invited to retry
    [BR4.4, security-design § 4].
    """

    def __init__(self) -> None:
        """Refuse the signup and point at the login path."""
        super().__init__(
            code="ACCOUNT_EXISTS",
            message_key="signup.number.already_registered",
        )


@dataclass(frozen=True, slots=True)
class AccountCreated:
    """The identity signup just created.

    :ivar account_id: The new account
    :ivar is_teacher: Whether an ``Owner`` row was created with it
    """

    account_id: uuid.UUID
    is_teacher: bool


@dataclass(frozen=True, slots=True)
class AlreadyAdded:
    """What the lookup may say about a number, and no more [BR2.3].

    **Three fields, and the absences are the requirement.** No teacher
    name, no teacher id, no batch name, no batch subject, no fee, no
    enrollment id. With any of those the lookup becomes an oracle for
    who teaches whom, readable by anyone who can type a phone number.

    :ivar exists: Whether a teacher has recorded this number
    :ivar display_name: The teacher-typed name, to pre-fill as
        correctable, or None when no seat exists
    :ivar role: The role the seat carries, to lock, or None when no
        seat exists
    """

    exists: bool
    display_name: str | None
    role: SignupRole | None


#: The seat behind a number, newest-teacher-entry last so a person added
#: twice pre-fills from the FIRST name a teacher gave them rather than
#: from whichever row the planner happened to return.
#:
#: Both links are searched, and the role is derived from WHICH link
#: matched: a number recorded as a guardian contact locks the form to
#: Guardian [BR4.5]. The student link is preferred when one row carries
#: both, because a person who is their own guardian is a student first.
#:
#: **Returns the display name and the matched link only.** The batch is
#: not joined at all -- not filtered out afterwards, not selected and
#: discarded -- so there is no column here that a later edit could
#: accidentally surface [BR2.3].
_LOOKUP_QUERY = sa.text(
    """
    SELECT
        e.display_name AS display_name,
        (a.id = e.student_account_id) AS is_student
    FROM enrollment e
    JOIN account a ON a.phone = :phone
    WHERE a.id IN (e.student_account_id, e.guardian_account_id)
    ORDER BY (a.id = e.student_account_id) DESC, e.created_at, e.id
    LIMIT 1
    """
)

#: The seats a number has when its account did not exist until now.
#:
#: A teacher records a number BEFORE anyone signs up on it, so at that
#: moment no account exists to link and the enrollment carries the
#: typed number on ``guardian_phone`` alone -- or, for a student seat,
#: nothing linkable at all. This statement finds the guardian case.
#:
#: **It sets the link and NOT the decision** [BR5.1]. That is the
#: absence this whole Unit turns on: linking is not agreeing.
_LINK_GUARDIAN_SEATS = sa.text(
    """
    UPDATE enrollment
    SET guardian_account_id = :account_id
    WHERE guardian_phone = :phone
      AND guardian_account_id IS NULL
      AND guardian_relink_blocked_at IS NULL
    """
)


def already_added(session: Session, phone: str) -> AlreadyAdded:
    """Report whether a teacher recorded this number, and nothing more.

    Called before the signup form renders, so the form can pre-fill the
    teacher-typed name as correctable and lock the role [BR4.5].

    :param session: The session to query through
    :param phone: The number typed into the form
    :return: Existence, the name to pre-fill and the role to lock
    """
    row = session.execute(_LOOKUP_QUERY, {"phone": phone}).one_or_none()

    if row is None:
        return AlreadyAdded(exists=False, display_name=None, role=None)

    return AlreadyAdded(
        exists=True,
        display_name=row.display_name,
        role=SignupRole.STUDENT if row.is_student else SignupRole.GUARDIAN,
    )


def create_account(
    session: Session,
    *,
    phone: str,
    role: SignupRole,
    self_name: str,
    address: str | None = None,
    now: dt.datetime | None = None,
) -> AccountCreated:
    """Create an account, its profile, and an ``Owner`` only for Teacher.

    **One transaction** [BR3.3]. ``Profile`` stops being optional the
    moment signup creates one, so an account with no profile row would
    violate the assumption every later reader makes -- and a failure
    between the two writes is exactly how that row gets created. The
    whole body is one ``commit``, and nothing is flushed to the caller
    before it.

    **The self-authored name lands on ``Profile.self_name`` and no
    ``Enrollment.display_name`` is touched** [BR3.1, ADR-010]. There is
    no third name: a teacher keeps seeing what that teacher typed, and
    "which name does a teacher see" stays answered by which table a
    query reads.

    **Existing seats are linked and their decisions left alone**
    [BR5.1]. This is the Unit's central absence.

    **Binds the row-level-security context to the account it just
    created**, because signup is the one write path with no
    authenticated account to bind: see the comment at that line for why
    that is the policy working rather than an exemption from it.

    :param session: The session to write through
    :param phone: The number this identity is keyed on
    :param role: The claimed role; nothing verifies it [BR4.2]
    :param self_name: The name the person chose for themselves
    :param address: The address, or None on the already-added path
    :param now: The moment of creation, or None for the clock
    :return: The new account and whether it owns batches
    :raises DuplicateNumber: The number already has an account
    """
    moment = now or dt.datetime.now(tz=dt.UTC)

    # Asked before inserting, so the refusal is a clean ConflictError
    # rather than a driver IntegrityError the caller has to classify.
    # The unique constraint remains the real guarantee: two concurrent
    # signups on one number both pass this check and the second fails
    # at COMMIT, which is why the handler maps that too.
    existing = session.execute(
        sa.select(Account.id).where(Account.phone == phone)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateNumber()

    account = Account(phone=phone, created_at=moment)
    session.add(account)
    session.flush()

    # THE ROW-LEVEL-SECURITY CONTEXT, SET HERE AND NOWHERE ELSE IN THIS
    # UNIT, and it is the one piece of this function that is not
    # obvious.
    #
    # The `profile` policy's WITH CHECK requires the inserted
    # `account_id` to equal the transaction's bound account, and the
    # request middleware binds the AUTHENTICATED account. Signup has
    # none: the account being written is created by this very
    # transaction, a moment ago, and nobody has verified a code for it
    # yet. So the insert is refused by the policy, which is the policy
    # behaving correctly rather than a fault in it.
    #
    # Binding the context to the account just created is what the
    # policy means -- a person may write their OWN profile -- rather
    # than an exemption from it. The alternative, writing this row as
    # the table owner or adding a policy branch for an unbound
    # session, would weaken the one mechanism standing between a
    # teacher and a child's home address [BR3.2, TC-13], and it would
    # weaken it for every future writer rather than for this one.
    #
    # Transaction-local, so it is discarded at the commit below and
    # cannot leak to the next request to borrow this pooled connection.
    set_account_context(session, account.id)

    session.add(Profile(account_id=account.id, self_name=self_name, address=address))

    is_teacher = role is SignupRole.TEACHER
    if is_teacher:
        # The row's EXISTENCE is the teacher claim [BR4.1]. No role is
        # recorded on the account, here or anywhere.
        session.add(Owner(account_id=account.id, created_at=moment))

    _link_existing_seats(session, account_id=account.id, phone=phone)

    session.commit()
    return AccountCreated(account_id=account.id, is_teacher=is_teacher)


def _link_existing_seats(
    session: Session, *, account_id: uuid.UUID, phone: str
) -> None:
    """Attach the new account to seats a teacher already created.

    **Sets the links and never a decision** [BR5.1]. A seat that was
    ``pending`` is still ``pending`` after this runs, and that is the
    point: signing up is not accepting, so the person is offered an
    invitation rather than a lens.

    The student link is attached through ``Enrollment.guardian_phone``
    only for the guardian case; a student seat carries no typed number
    column of its own, so a teacher creating one for an unregistered
    number records the guardian contact and the student link attaches
    when the roster's number is corrected. That is D2's screen and this
    Unit changes nothing about it.

    :param session: The session to write through
    :param account_id: The account just created
    :param phone: The number it is keyed on
    :return: None
    """
    session.execute(_LINK_GUARDIAN_SEATS, {"account_id": account_id, "phone": phone})
