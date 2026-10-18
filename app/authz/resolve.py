"""Compute the lens, per request, from the data at that moment.

**No role column, no cross-request cache.** The lens is derived from
``Owner`` and ``Enrollment`` on every request [BR1.1], which is the single
most-mandated rule in the project and the one under the most pressure:
lens resolution runs on every request, making it the hottest query in the
system on a 2 GB instance, so the argument for caching it will arrive with
plausible numbers attached.

Two mechanisms answer that pressure without weakening the rule:

* **One query, three ``EXISTS`` booleans** [NFR6.1]. Three round trips
  would be the thing that makes caching look necessary.
* **A memo on the request object** [BR1.4]. Request-scoped is a property
  of *where the value lives*: on ``request.state`` it is garbage-collected
  with the request; in a module dict or an ``lru_cache`` it is not, and at
  the call site the two look identical.

There is deliberately no module-level dict and no ``lru_cache`` anywhere
in this file, and a test asserts their absence rather than trusting the
reading.
"""

from __future__ import annotations

import uuid
from typing import Protocol

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, Lens, StudentLens, TeacherLens

__all__ = ["LensResolver", "available_lenses"]

#: The attribute the per-request memo lives under on ``request.state``.
MEMO_ATTRIBUTE = "lenses"

#: ONE statement, carrying both the three booleans and the two scoping
#: ids [NFR6.1]. Written as literal SQL rather than as ORM checks because
#: the shape is the requirement, not an optimization.
#:
#: The ids come back as scalar subqueries rather than as follow-up
#: selects. An earlier version fetched them separately and was caught by
#: the query-count assertion: three round trips per request is exactly
#: what makes caching the lens look necessary, and the rule has to survive
#: that argument.
#:
#: ``EXISTS`` is kept for the student row even though no id is needed,
#: because a student lens carries only the account id.
#:
#: **The guardian branch reads ``guardian_account_id``, and that is the
#: correction U4 brings** [BR5.0]. U3 resolved a guardian by looking for
#: an enrollment whose ``account_id`` was the caller's and whose ``role``
#: was ``guardian`` -- which identifies the guardian but cannot answer
#: *which child*, since nothing linked that row to the student's except
#: a shared batch. The reshape puts both links on one row, so the
#: enrollment the guardian reaches IS the child's enrollment.
_LENS_QUERY = sa.text(
    """
    SELECT
        (
            SELECT id FROM owner
            WHERE account_id = :account_id
            ORDER BY created_at, id LIMIT 1
        ) AS owner_id,
        EXISTS (
            SELECT 1 FROM enrollment
            WHERE student_account_id = :account_id
        ) AS is_student,
        (
            SELECT id FROM enrollment
            WHERE guardian_account_id = :account_id
            ORDER BY created_at, id LIMIT 1
        ) AS guardian_enrollment_id
    """
)


class _HasState(Protocol):
    """The one attribute of a request this resolver touches."""

    state: object


def available_lenses(session: Session, account_id: uuid.UUID) -> list[Lens]:
    """Query the lenses this account has **at this moment**.

    Unmemoized by design: this is the function that must hit the database,
    and :class:`LensResolver` is the only thing that should ever skip it.

    :param session: The session to query through
    :param account_id: The authenticated account
    :return: Every lens the account's data supports, possibly empty
    """
    row = session.execute(_LENS_QUERY, {"account_id": account_id}).one()
    lenses: list[Lens] = []

    if row.owner_id is not None:
        # The owner id is the scoping value a teacher-facing query needs,
        # which is what makes the lens a data dependency rather than a
        # guard someone can forget to add.
        lenses.append(TeacherLens(account_id=account_id, owner_id=row.owner_id))

    if row.is_student:
        lenses.append(StudentLens(account_id=account_id))

    if row.guardian_enrollment_id is not None:
        lenses.append(
            GuardianLens(
                account_id=account_id,
                child_enrollment_id=row.guardian_enrollment_id,
            )
        )

    return lenses


class LensResolver:
    """Resolve a request's lenses, memoizing within that one request.

    :ivar session: The session lens queries are issued through
    """

    def __init__(self, session: Session) -> None:
        """Bind the resolver to a session.

        No state beyond the session. An instance attribute holding
        resolved lenses would outlive the request whenever the resolver
        does, which is the cross-request cache BR1.1 forbids.

        :param session: The session to query through
        """
        self.session = session

    def resolve(self, request: _HasState, account_id: uuid.UUID) -> list[Lens]:
        """Return this request's lenses, querying at most once.

        :param request: The request whose ``state`` carries the memo
        :param account_id: The authenticated account
        :return: Every lens the account's data supports
        """
        memo = getattr(request.state, MEMO_ATTRIBUTE, None)
        if memo is not None:
            return list(memo)

        lenses = available_lenses(self.session, account_id)
        setattr(request.state, MEMO_ATTRIBUTE, lenses)
        return list(lenses)
