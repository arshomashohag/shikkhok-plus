"""The lens type hierarchy.

A lens is a **data dependency**, not a side-effecting guard: it carries the
value the handler needs to scope its query, so a handler cannot compile a
scoped query without one. That converts authorization from a precondition
somebody can forget into a value they need [TC-11, D-2].

This Unit defines the types only. Resolving a lens -- querying owned batches
and enrollments, setting the row-level-security context -- belongs to U3.
The route-enumeration harness needs the type to exist; it does not need
anything that produces one.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Lens:
    """The base of the three-way lens hierarchy.

    :ivar account_id: The authenticated account this lens was resolved for
    """

    account_id: UUID


@dataclass(frozen=True, slots=True)
class TeacherLens(Lens):
    """A teacher's view, scoped to the batches they own.

    Carries ``owner_id`` rather than an account id because a teacher-facing
    response exposes an enrollment id and never a global account key
    [ADR-001]: the lens object handed to a handler *is* the scoping value.

    :ivar owner_id: The owner whose batches this lens reaches
    """

    owner_id: UUID


@dataclass(frozen=True, slots=True)
class StudentLens(Lens):
    """A student's own view of their enrollments."""


@dataclass(frozen=True, slots=True)
class GuardianLens(Lens):
    """A guardian's view of a child's enrollments.

    ``child_enrollment_id`` is **optional, and the None case is not a
    degenerate one** [BR5.1, BR5.2]. A guardian's first authenticated
    request has not selected a child yet -- the selection list is what
    that request renders -- so the only authoritative value at that
    point is the account id. The child arrives as a **path parameter**
    on each subsequent request, never from a client-supplied hint, which
    is what OQ-7 settles.

    Resolution fills it with the first reachable enrollment so a
    single-child guardian goes straight through, but no authorization
    decision may read it without the route having named it.

    :ivar child_enrollment_id: The enrollment this request is scoped to,
        or None before a child has been selected
    """

    child_enrollment_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InvitationLens(Lens):
    """Reach for a seat whose holder has not accepted it [BR1.3].

    **A fourth type rather than a branch inside the resolver**
    [NFR14.24], for the same reason the other three are types: the
    route-enumeration gate matches on a dependency's return annotation
    being a ``Lens`` subtype, so a conditional would be invisible to it,
    and the ``enrollment_id`` living inside the lens is what stops a
    handler widening the read to a second seat.

    **Granted on ``pending`` OR ``declined``**, which is the one place
    this hierarchy admits a refused state. BR5.4 makes a decline
    reversible by its holder and by nobody else, and a reversal needs
    the holder to still reach the seat; a grant restricted to
    ``pending`` would quietly convert a mis-tap into a permanent
    lockout from a person's own records.

    **Resolved by its own statement, never by the hot-path query**
    [ADR-011, NFR20.3]. An invitation grant is a SET -- a person may
    hold several unaccepted seats -- and ``_LENS_QUERY`` returns
    scalars, so a fourth branch there would silently return only the
    first.

    What it reaches is bounded by the response SCHEMA rather than by a
    filter [BR1.4]: batch name, subject and fee amount, all three
    teacher-authored, so the unaccepted read crosses no privacy
    boundary and there is nothing to leak.

    :ivar enrollment_id: The one seat this lens reaches
    """

    enrollment_id: UUID
