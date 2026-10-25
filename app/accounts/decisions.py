"""Accept, decline, and change your mind. One link at a time.

**The storage is per link and the action may carry both** [BR5.2,
BR5.3]. Those two rules read as a contradiction and are not: BR5.2
governs the DATA -- a decision belongs to the link that names its
holder, and one person's choice never speaks for the other -- while
BR5.3 governs the ACTION, where one person holding both links on their
own seat decides once rather than twice. So these functions move
*every column this account holds on this seat*, which is one column in
the split case and two in the self-guardian case, and never a column
belonging to somebody else.

**The asymmetry in :func:`decline_seat` is the design** [BR5.4]. A
decline is durable against the teacher -- no teacher action clears it,
and re-adding the number does not re-prompt -- and reversible by its
holder at any time through :func:`accept_seat`. Either half alone is a
different product: without durability a teacher can re-ask until the
person gives in; without reversibility a mis-tap locks a person out of
their own records permanently.

**Nothing here resets a decision to ``pending``** [BR6.1]. The
transition out of ``declined`` is to ``accepted``, never back to the
unanswered state, so the durability above survives every write D1
makes. There is no function in this module that could.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import InvitationLens

__all__ = ["accept_seat", "decline_seat"]

#: Move every decision column this account holds on this seat.
#:
#: **Each column's CASE tests its OWN link**, so the student column
#: moves only when the student link names this account and the guardian
#: column only when the guardian link does [BR5.2]. Where both name the
#: same account both CASEs fire, which is BR5.3 falling out of the data
#: rather than being special-cased -- an explicit "are both links the
#: same person" branch would be a second place for the rule to live.
#:
#: ``enrollment_id`` comes from the LENS and the account from the lens
#: too, so there is no parameter a caller could forge and no row this
#: statement can reach that its holder does not hold.
#:
#: The erasure markers are not tested here. A link whose holder erased
#: resolves no invitation lens [BR6.2, invitations.py], so this
#: statement is never reached for one -- and adding the condition would
#: put the same rule in two places with no mechanism keeping them
#: agreed.
_SET_DECISION = sa.text(
    """
    UPDATE enrollment
    SET student_decision = CASE
            WHEN student_account_id = :account_id
            THEN CAST(:decision AS enrollment_decision)
            ELSE student_decision
        END,
        guardian_decision = CASE
            WHEN guardian_account_id = :account_id
            THEN CAST(:decision AS enrollment_decision)
            ELSE guardian_decision
        END
    WHERE id = :enrollment_id
    """
)


def _record(session: Session, *, lens: InvitationLens, decision: str) -> None:
    """Write one decision to every link this lens's holder holds.

    One implementation for both verbs, because the two differ in a
    single literal and a second copy is how the per-link scoping stops
    matching between them.

    :param session: The session to write through
    :param lens: The invitation lens naming the holder and the seat
    :param decision: ``accepted`` or ``declined``
    :return: None
    """
    session.execute(
        _SET_DECISION,
        {
            "account_id": lens.account_id,
            "enrollment_id": lens.enrollment_id,
            "decision": decision,
        },
    )
    session.commit()


def accept_seat(session: Session, *, lens: InvitationLens) -> None:
    """Accept this seat, from ``pending`` or from ``declined``.

    **Accepting from ``declined`` is the same operation, not a second
    one** [BR5.4, AC1.13.2]: the lens becomes available exactly as if
    the person had accepted first time, and the seat's full history
    from creation becomes visible, including dues accrued before the
    decision changed [BR1.5].

    Idempotent. Accepting an already-accepted link writes the value it
    already holds, which costs one statement and removes a race between
    two taps.

    :param session: The session to write through
    :param lens: The invitation lens naming the holder and the seat
    :return: None
    """
    _record(session, lens=lens, decision="accepted")


def decline_seat(session: Session, *, lens: InvitationLens) -> None:
    """Decline this seat, withdrawing only this holder's own lens.

    **A guardian's decline does not stop the student's fee** [BR5.2,
    AC1.14.1a]. The student owes the fee; a guardian's refusal to
    oversee the enrollment withdraws the guardian's lens and nothing
    else. This is the rule a single decline confirmation, written once
    and shown to both roles, got wrong by telling a guardian a debt was
    cancelled when it was not -- which is why ``O4`` carries two
    decline sheets.

    The seat leaves the person's enrollments and **stays among their
    invitations**, with an accept action [BR5.5]. Both halves matter:
    out of the enrollments because BR1.1 denies the lens, still in the
    invitations because BR5.4 needs the holder to reach it.

    :param session: The session to write through
    :param lens: The invitation lens naming the holder and the seat
    :return: None
    """
    _record(session, lens=lens, decision="declined")
