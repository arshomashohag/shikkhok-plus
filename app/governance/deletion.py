"""One deletion, two callers, and the refusal that comes first.

**Both deletion paths reach this module** [BR3.1]. The in-app route and
the external route call :func:`delete_account`; neither reimplements it.
Two implementations drift, and the one that drifts is the external route
-- used less, tested less, and the one Play requires.

What the function does, in order, with every destructive step in one
transaction (:func:`delete_account`'s own docstring describes the
second commit point, on the branch where no account exists):

1. **Retire every batch the account owns** [BR1.6, amended 2026-10-28].
   Each stays as its students' history: marked inactive, so no new fee
   falls due, and stripped of the teacher's name and payment number, so
   nothing of the departed teacher remains and no payment goes to a
   number that no longer answers. ``0010`` set ``owner.account_id`` to
   ``SET NULL``, so the account's removal unlinks rather than destroys.
2. **Delete the rows this account owns** that the manifest marks
   ``HARD_DELETE``.
3. **Delete the account row.** Everything else follows from the database
   constraints: ``SET NULL`` on the three references ``0007`` fixed, so
   the enrollments, payment claims and queued submissions survive with
   their links cleared; ``CASCADE`` on the five whose tables are
   ``HARD_DELETE``.

**Step 3 is what makes step 2 look redundant, and it is not.** Five of
the six account-scoped hard-delete tables would cascade anyway. They are
deleted explicitly because the explicit statement is what the absence
test observes, and because a constraint is one migration away from
changing while this module would go on reading as though it had not.
The two phone-scoped tables -- ``otp_request`` and the staging outbox --
cascade from nothing at all, because they are keyed on the number rather
than on the account, and they are exactly the rows a deletion must
remove: a code and a phone number sitting together.

**The scoping map is the part that has to be exhaustive.** A disposition
says WHAT happens to a table's rows; it cannot say WHICH rows belong to
the account being deleted, and the answers in play are enumerated by
:class:`Scope` rather than counted here. That is declared in
:data:`HARD_DELETE_SCOPES` and asserted complete against ``DISPOSITIONS``
by a test, so a table added later with ``HARD_DELETE`` and no scoping
decision fails rather than being silently skipped.

The map also carries the tables deletion considered and deliberately
does NOT touch, which is why its name is wider than its contents
suggest. Those entries are ``Scope.NOT_PERSONAL``, they are pinned to a
matching ``Disposition.NOT_PERSONAL`` by a cross-check test, and the
reason each one is left alone is written in its ``note`` -- the most
load-bearing of which is that clearing a number's rate-limit counters on
request would make the public deletion route the way to reset the abuse
ceilings protecting that number.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.governance.dispositions import DISPOSITIONS, Disposition

__all__ = [
    "HARD_DELETE_SCOPES",
    "DeletionResult",
    "Scope",
    "delete_account",
    "hard_delete_tables",
]


class Scope(enum.Enum):
    """How a table's rows are identified as belonging to one person.

    The distinction is load-bearing: a table whose rows are keyed on the
    phone number is NOT reached by deleting the account row, however its
    foreign keys are configured, because it has none. No count is stated
    here, because a count in a comment is a claim nothing checks and
    this docstring read "Three answers" against four members for as long
    as ``NOT_PERSONAL`` existed.
    """

    #: Reached by an account id column, named per entry.
    ACCOUNT_COLUMN = "account_column"

    #: Reached by the phone number. Survives the account row, so it must
    #: be deleted explicitly and BEFORE the account row is gone, while
    #: the number is still known.
    PHONE_COLUMN = "phone_column"

    #: Reached by cascading from a table this module deletes directly.
    VIA_CASCADE = "via_cascade"

    #: Belongs to no person. A counter, a job's telemetry. Deleting
    #: these on a person's request would destroy operational state
    #: shared by every user.
    NOT_PERSONAL = "not_personal"


@dataclass(frozen=True, slots=True)
class _Target:
    """One hard-delete table's scoping decision.

    :ivar scope: How its rows are identified
    :ivar column: The column to match on, for the two column scopes
    :ivar note: Why, for the reader who finds this list surprising
    """

    scope: Scope
    column: str | None
    note: str


#: Every ``HARD_DELETE`` table and how deletion reaches its rows, plus
#: the ``NOT_PERSONAL`` tables deletion considered and leaves standing.
#:
#: **Asserted complete against ``DISPOSITIONS``** by
#: ``tests/governance/test_deletion.py``, in both directions: a
#: hard-delete table missing from here fails, and an entry here naming a
#: table that is neither hard-delete nor ``NOT_PERSONAL`` fails too. The
#: first direction is the one that keeps a child's data: a table added
#: two units later with no scoping decision would otherwise be skipped
#: in silence.
#:
#: The ``NOT_PERSONAL`` entries are not an escape hatch from that gate.
#: Each is pinned to a ``Disposition.NOT_PERSONAL`` in the other
#: manifest by
#: ``test_not_personal_scoping_and_not_personal_disposition_agree``, so
#: listing a table here cannot exempt it from having its deletion
#: behaviour declared -- it only moves the declaration to the value that
#: says a deletion does nothing. That cross-check is the control whose
#: absence let ``rate_limit_counter`` carry ``HARD_DELETE`` here while
#: the published policy told parents the counters were removed with
#: their account.
HARD_DELETE_SCOPES: Final[dict[str, _Target]] = {
    "account": _Target(
        scope=Scope.ACCOUNT_COLUMN,
        column="id",
        note="The row itself, deleted last so the cascades fire once.",
    ),
    "profile": _Target(
        scope=Scope.ACCOUNT_COLUMN,
        column="account_id",
        note="Self-authored and owner-private; nobody else has a claim.",
    ),
    "refresh_token": _Target(
        scope=Scope.ACCOUNT_COLUMN,
        column="account_id",
        note="Credentials. Nothing survives the account they authenticate.",
    ),
    "hidden_batch_preference": _Target(
        scope=Scope.ACCOUNT_COLUMN,
        column="account_id",
        note="The viewer's own interface preference, visible to nobody else.",
    ),
    "reminder_event": _Target(
        scope=Scope.ACCOUNT_COLUMN,
        column="sent_by_account_id",
        note=(
            "The record that a TEACHER nudged someone. Reachable only "
            "after the batch refusal passes, like `owner`."
        ),
    ),
    "notification": _Target(
        scope=Scope.ACCOUNT_COLUMN,
        column="account_id",
        note="The account's own inbox, addressed to nobody else.",
    ),
    "otp_request": _Target(
        scope=Scope.PHONE_COLUMN,
        column="phone",
        note=(
            "Keyed on the NUMBER, not the account, so no constraint "
            "reaches it. It holds a phone number beside a code hash and "
            "is precisely what a deletion must remove."
        ),
    ),
    "staging_sms_outbox": _Target(
        scope=Scope.PHONE_COLUMN,
        column="phone",
        note=(
            "Also keyed on the number, and it holds a phone number and "
            "an OTP together in plaintext. It must never hold a row in "
            "production; deleted here regardless, because 'must never' "
            "is not a reason to skip the statement."
        ),
    ),
    "verify_attempt": _Target(
        scope=Scope.VIA_CASCADE,
        column=None,
        note="Cascades from `otp_request`, which this module deletes.",
    ),
    "rate_limit_counter": _Target(
        scope=Scope.NOT_PERSONAL,
        column=None,
        note=(
            "Keyed on a scope VALUE, which for two of the seven scopes "
            "is a phone number -- and it is still not deleted. These "
            "counters are the abuse control: clearing a number's "
            "counters on request would make the deletion route the way "
            "to reset the ceilings protecting it. They expire on their "
            "own 48-hour window instead [DESIGN-7]."
        ),
    ),
    "job_heartbeat": _Target(
        scope=Scope.NOT_PERSONAL,
        column=None,
        note=(
            "One row per scheduled job. It names no person and holds no "
            "identifier; deleting it on a person's request would destroy "
            "the freshness signal for every user."
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class DeletionResult:
    """What one deletion did.

    :ivar existed: Whether an account with that number existed
    :ivar rows_deleted: Rows removed per table, for the audit trail
    """

    existed: bool
    rows_deleted: dict[str, int]


#: Retires every batch an account owns, in the deletion's transaction.
_RETIRE_OWNED_BATCHES: Final = sa.text(
    "UPDATE batch SET active = false, teacher_display_name = NULL, "
    "collection_number = NULL, collection_channel = NULL "
    "WHERE owner_id IN (SELECT id FROM owner WHERE account_id = :account_id)"
)


def delete_account(session: Session, phone: str) -> DeletionResult:
    """Delete the account registered to a number, or report it absent.

    **Idempotent by nature, not by a lookup-then-delete guard** [BR1.4].
    A second request for a number that no longer has an account reports
    success and writes nothing. Implemented as "delete, count what went"
    rather than "check, then delete", because the latter is a race
    between two requests and the DELETE is already idempotent: deleting
    zero rows is a success.

    **Every DESTRUCTIVE step happens in one transaction**, and there
    are **two commit points, not one**. The common path -- an account
    exists -- deletes the phone-scoped rows, the account-scoped rows and
    the account row itself, then commits once at the end: a partial
    deletion is the outcome neither the user nor the teacher whose
    records hang off the chain can live with, so none of it is visible
    until all of it is.

    The second commit is the early return taken when **no account is
    registered to the number**, and it is safe for a reason worth
    stating rather than inferring. By that point the function has run
    only the phone-scoped deletes, which are a complete unit of work in
    their own right: ``otp_request`` and the staging outbox hold a
    number beside a code and are keyed on the number alone, so they are
    exactly the rows a deletion of a numberless account must still
    remove, and removing them commits nothing that a later step could
    contradict. Nothing destructive follows it -- the branch returns
    immediately -- so there is no window in which half a deletion is
    durable. **A reader must not generalise from it**: moving any
    account-scoped work above that return would turn a safe early commit
    into the partial deletion this function exists to avoid.

    A teacher's batches are retired inside the same transaction, before
    the account row goes, so a failure leaves them exactly as they were.

    :param session: The session to work through
    :param phone: The number whose account is being deleted
    :return: What was deleted
    """
    account_id: uuid.UUID | None = session.execute(
        sa.text("SELECT id FROM account WHERE phone = :phone"),
        {"phone": phone},
    ).scalar_one_or_none()

    rows_deleted: dict[str, int] = {}

    # The phone-scoped tables go FIRST, while the number is still known
    # and before the account row disappears. Nothing reaches them by
    # constraint, so an ordering mistake here is a silent leak of a
    # phone number sitting beside a code.
    for table, target in sorted(HARD_DELETE_SCOPES.items()):
        if target.scope is not Scope.PHONE_COLUMN:
            continue
        rows_deleted[table] = _delete_where(session, table, target, phone=phone)

    if account_id is None:
        session.commit()
        return DeletionResult(existed=False, rows_deleted=rows_deleted)

    # A teacher's batches stay with their students [BR1.6 amended].
    # Retired before the account row goes, in the same transaction.
    session.execute(_RETIRE_OWNED_BATCHES, {"account_id": account_id})

    for table, target in sorted(HARD_DELETE_SCOPES.items()):
        if target.scope is not Scope.ACCOUNT_COLUMN or table == "account":
            continue
        rows_deleted[table] = _delete_where(
            session, table, target, account_id=account_id
        )

    # LAST, so the SET NULL and CASCADE constraints fire against a
    # schema the explicit deletes have already emptied where they must.
    # `session.connection().execute` rather than `session.execute`, and
    # the difference is typing rather than behaviour: the former is
    # annotated to return `CursorResult`, which carries `rowcount`,
    # while the latter returns the generic `Result`, which does not.
    # The counts this function returns are the deletion's own record of
    # what it removed, so reading them is not optional.
    rows_deleted["account"] = (
        session.connection()
        .execute(
            sa.text("DELETE FROM account WHERE id = :account_id"),
            {"account_id": account_id},
        )
        .rowcount
    )

    session.commit()
    return DeletionResult(existed=True, rows_deleted=rows_deleted)


def _delete_where(
    session: Session,
    table: str,
    target: _Target,
    *,
    account_id: uuid.UUID | None = None,
    phone: str | None = None,
) -> int:
    """Delete one table's rows for one person, returning the count.

    The table and column names come from :data:`HARD_DELETE_SCOPES`, a
    module constant, and never from request input -- which is what makes
    the interpolation below safe. Identifiers cannot be bound as
    parameters in PostgreSQL, so there is no alternative shape; the
    control is that the values are literals in this file.

    :param session: The session to write through
    :param table: The table to delete from
    :param target: Its scoping decision
    :param account_id: The account, for an account-scoped table
    :param phone: The number, for a phone-scoped table
    :return: How many rows were removed
    :raises ValueError: The target names no column to match on
    """
    if target.column is None:
        raise ValueError(f"{table} has no column to match on")

    value = account_id if target.scope is Scope.ACCOUNT_COLUMN else phone
    statement = sa.text(
        f"DELETE FROM {table} WHERE {target.column} = :value"  # noqa: S608
    )
    # See the note at the `account` delete: the connection-level call is
    # the one typed to carry `rowcount`.
    return session.connection().execute(statement, {"value": value}).rowcount


def hard_delete_tables() -> set[str]:
    """Every table the manifest marks ``HARD_DELETE``.

    Derived rather than listed, so the completeness assertion in the
    test suite reads the same source this module does.

    :return: The table names
    """
    return {
        table
        for table, governance in DISPOSITIONS.items()
        if governance.disposition is Disposition.HARD_DELETE
    }
