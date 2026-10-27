"""The invitation grant: its own statement, off the hot path.

**A second statement, and that is the design rather than a compromise**
[ADR-011, NFR20.3]. ``app.authz.resolve`` answers "which role lenses
does this account have" in one statement returning three scalars,
because it runs on every authenticated request on a 2 GB instance. An
invitation grant is a **set** -- a person may hold several unaccepted
seats, and each is a separate thing they may accept or decline -- so a
fourth scalar there would silently return only the first.

Adding it here costs nothing on the hot path, because nothing on the
hot path calls it: this runs on the invitation route alone.

**``pending`` and ``declined`` both grant** [BR1.3]. The inclusion of
``declined`` is deliberate and is the mirror of BR5.4: a decline is
reversible by its holder and by nobody else, which requires the holder
to still reach the seat. A grant restricted to ``pending`` would make
the reversal unreachable and turn a mis-tap into a permanent lockout
from a person's own records.

**One row, one lens, even when one account holds both links** [BR5.3].
A person who is recorded as both the student and the guardian of their
own seat decides once and sees the seat once, so this returns one lens
per enrollment rather than one per link. The storage stays per-link
[BR5.2]; the deduplication is a property of what is LISTED, which is
precisely the distinction BR5.3 draws between the data and the action.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import InvitationLens
from app.db.models import Batch, BatchSubject, Enrollment
from app.money import Money

__all__ = ["InvitationRow", "available_invitations", "read_invitation"]

#: ONE statement over one table, returning a SET of enrollment ids.
#:
#: The ``OR`` is across the two links rather than across two queries,
#: and the row is returned once however many of its links match --
#: which is BR5.3's "the seat appears once" expressed as SQL rather
#: than as a deduplication step a later reader could drop.
#:
#: **Each link's decision is paired with its OWN account column.** The
#: plausible wrong form -- ``(student_account_id = :account_id OR
#: guardian_account_id = :account_id) AND (student_decision <>
#: 'accepted' OR guardian_decision <> 'accepted')`` -- grants a person
#: who ACCEPTED as student an invitation to the same seat because its
#: guardian link is still pending, re-listing a seat they already hold.
#:
#: The erasure markers are read for the same reason the role grants
#: read them [BR6.2]: an erased link names an account that no longer
#: exists, and offering it an invitation would invite a ghost.
_INVITATION_QUERY = sa.text(
    """
    SELECT id FROM enrollment
    WHERE (
        student_account_id = :account_id
        AND student_decision IN ('pending', 'declined')
        AND student_relink_blocked_at IS NULL
    ) OR (
        guardian_account_id = :account_id
        AND guardian_decision IN ('pending', 'declined')
        AND guardian_relink_blocked_at IS NULL
    )
    ORDER BY created_at, id
    """
)


def available_invitations(
    session: Session, account_id: uuid.UUID
) -> list[InvitationLens]:
    """Grant one invitation lens per unaccepted seat this account holds.

    Ordered oldest first, so the list does not reshuffle between reads
    as decisions are made.

    :param session: The session to query through
    :param account_id: The authenticated account
    :return: One lens per reachable seat, empty when none is unaccepted
    """
    rows = session.execute(_INVITATION_QUERY, {"account_id": account_id}).all()
    return [InvitationLens(account_id=account_id, enrollment_id=row.id) for row in rows]


@dataclass(frozen=True, slots=True)
class InvitationRow:
    """One unaccepted seat, at the width BR1.4 permits.

    Three teacher-authored facts plus the holder's own decision. The
    narrowness is the requirement rather than an optimization: a person
    who has not agreed to be in a batch is shown what they are being
    asked to join and nothing else [AC1.10.1, AC1.10.2].

    :ivar enrollment_id: The seat
    :ivar batch_name: The class being joined
    :ivar subject: The subjects taught, as the teacher named them
    :ivar fee_amount: This seat's fee, or None when it inherits the
        batch default. None is NOT zero: zero is a waiver
    :ivar decision: This holder's own decision, never the other link's
    :ivar role: Which link this account holds, ``student`` or
        ``guardian``. Present so the decline confirmation can say what
        a decline actually does for THIS holder
    """

    enrollment_id: uuid.UUID
    batch_name: str
    subject: list[str]
    fee_amount: Money | None
    decision: str
    role: str


#: Read ONE seat through its invitation lens, at BR1.4's width.
#:
#: The fee falls back to the batch default here rather than on the
#: client, because "what will this cost me" is a decision the server
#: owes the person [TC-9] -- and because ``NULL`` meaning *inherit* and
#: ``0.00`` meaning *waived* are two different answers a client
#: comparing a number would collapse into one.
#:
#: ``decision`` is resolved to THIS holder's link, so a person who is
#: their own guardian sees one answer rather than two, and a person who
#: holds one link never reads the other's state [BR5.2].
#:
#: Scoped on the enrollment AND the account together. The id comes from
#: the lens, but repeating the account predicate is what makes the
#: statement safe to read on its own: there is no row it can reach that
#: its caller does not hold.
#:
#: **Written through the ORM columns rather than as literal SQL, and
#: that is about money rather than style.** ``fee_amount`` is a
#: ``MoneyColumn``, so selecting the mapped attribute returns a
#: :class:`~app.money.Money`; the same column read through ``sa.text``
#: comes back as a bare ``Decimal``, which would then need
#: reconstructing at the call site -- a second, unguarded place where a
#: money value is built [BR5.3]. The other statements in this module
#: are literal SQL because none of them touches an amount.
def _invitation_statement(
    *, account_id: uuid.UUID, enrollment_id: uuid.UUID
) -> sa.Select[uuid.UUID, str, Money | None, str, str]:
    """Build the one-seat read, scoped to its holder.

    The fee falls back to the batch default here rather than on the
    client, because "what will this cost me" is a decision the server
    owes the person [TC-9] -- and because ``NULL`` meaning *inherit*
    and ``0.00`` meaning *waived* are two different answers a client
    comparing a number would collapse into one.

    ``decision`` resolves to THIS holder's link, so a person who is
    their own guardian sees one answer rather than two, and a person
    who holds one link never reads the other's state [BR5.2].

    :param account_id: The holder, from the lens
    :param enrollment_id: The seat, from the lens
    :return: The select statement
    """
    return (
        sa.select(
            Enrollment.id,
            Batch.name,
            sa.func.coalesce(Enrollment.fee_amount, Batch.default_fee),
            sa.case(
                (
                    Enrollment.student_account_id == account_id,
                    Enrollment.student_decision,
                ),
                else_=Enrollment.guardian_decision,
            ),
            # **Which link this account holds.** The same condition the
            # decision column already branches on, so this discloses
            # nothing the holder does not have: they are on this seat.
            #
            # It is here because the DECLINE CONFIRMATION differs by
            # role [BR5.2] -- a student's decline stops their fee, a
            # guardian's leaves the student's obligation intact -- and
            # the client had no trustworthy way to tell them apart. A
            # single sheet shown to both once told a guardian a debt
            # was cancelled when it was not.
            sa.case(
                (Enrollment.student_account_id == account_id, sa.literal("student")),
                else_=sa.literal("guardian"),
            ),
        )
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(
            Enrollment.id == enrollment_id,
            sa.or_(
                Enrollment.student_account_id == account_id,
                Enrollment.guardian_account_id == account_id,
            ),
        )
    )


def read_invitation(session: Session, *, lens: InvitationLens) -> InvitationRow:
    """Read the one seat this lens reaches, at BR1.4's width.

    The subjects come from a **second statement**, because a subject is
    a ROW and the first returns one row per seat: joining would
    multiply the seat by its subjects and make the fee appear once per
    subject, which is the shape that becomes a wrong total the first
    time somebody sums it.

    :param session: The session to query through
    :param lens: The invitation lens naming the holder and the seat
    :return: The three teacher-authored fields and this holder's state
    :raises LookupError: The seat vanished between grant and read
    """
    row = session.execute(
        _invitation_statement(
            account_id=lens.account_id, enrollment_id=lens.enrollment_id
        )
    ).one_or_none()

    if row is None:
        # Reachable only if the seat was removed between resolving the
        # lens and reading it, which a teacher may legitimately do
        # while nobody has accepted [BR7.1]. Raised rather than
        # returned as None so a caller cannot render an empty
        # invitation.
        raise LookupError(str(lens.enrollment_id))

    enrollment_id, batch_name, fee_amount, decision, role = row

    subjects = [
        name
        for (name,) in session.execute(
            sa.select(BatchSubject.name)
            .join(Enrollment, Enrollment.batch_id == BatchSubject.batch_id)
            .where(Enrollment.id == lens.enrollment_id)
            .order_by(BatchSubject.name)
        ).all()
    ]

    return InvitationRow(
        enrollment_id=enrollment_id,
        batch_name=batch_name,
        subject=subjects,
        fee_amount=fee_amount,
        decision=decision,
        role=role,
    )
