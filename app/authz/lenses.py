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

    :ivar child_enrollment_id: The enrollment this request is scoped to
    """

    child_enrollment_id: UUID
