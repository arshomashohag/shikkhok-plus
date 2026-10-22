"""What this account can be.

The first call after signing in. It answers "which lenses do I have,
and how much is behind each", so the app can show a picker, skip the
picker when there is only one, or explain itself when there are none.

**This route resolves no lens, and that is deliberate.** Every other
authenticated route depends on a lens, which both authorizes it and
carries the id its queries scope by. This one cannot: it is the route
that *reports* the lenses, so requiring one would mean an account had
to already know what it was in order to ask. It therefore depends on
``authenticated_account`` alone, and every value it returns is derived
from that account id — it reads nothing another account could own.

The route-enumeration gate is told about this explicitly rather than
left to infer it, because an endpoint with no lens is exactly the
shape that gate exists to catch.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import authenticated_account, get_session
from app.authz.summary import LensSummary, lens_summary

router = APIRouter(prefix="/v1", tags=["me"])


class LensEntry(BaseModel):
    """One lens the account can choose.

    :ivar kind: Which lens: teacher, student or guardian
    :ivar count: How much sits behind it
    """

    kind: str
    count: int


class MeResponse(BaseModel):
    """Everything this account can be.

    **No role, and no default lens.** The list says what is available;
    which one the person wants is their choice, and a server-chosen
    default would be a stored role by another name. A single-entry
    list is the app's cue to skip the picker.

    :ivar lenses: Every available lens, teacher first
    """

    lenses: list[LensEntry] = Field(default_factory=list)


def _entries(summary: LensSummary) -> list[LensEntry]:
    """Render a summary as the ordered list the picker shows.

    Teacher first, then student, then guardian — a fixed order, so the
    picker does not reshuffle between sign-ins as counts change.

    :param summary: The resolved summary
    :return: One entry per available lens
    """
    entries: list[LensEntry] = []
    if summary.is_teacher:
        entries.append(LensEntry(kind="teacher", count=summary.teacher_batches))
    if summary.is_student:
        entries.append(LensEntry(kind="student", count=summary.student_enrollments))
    if summary.is_guardian:
        entries.append(LensEntry(kind="guardian", count=summary.guardian_children))
    return entries


@router.get("/me", response_model=MeResponse)
def read_me(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> MeResponse:
    """List every lens this account has.

    :param account_id: The authenticated account
    :param session: The session to query through
    :return: The available lenses, each with its count
    """
    return MeResponse(lenses=_entries(lens_summary(session, account_id)))
