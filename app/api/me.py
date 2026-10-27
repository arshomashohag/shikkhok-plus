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
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import authenticated_account, get_session
from app.authz.rls import set_account_context
from app.authz.summary import LensSummary, lens_summary
from app.db.models import Profile

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
    :ivar self_name: The name this person chose for themselves, or
        None before they have set one
    :ivar address: Their address, or None. **Owner-private** [BR3.4]:
        it sits in `OWNER_PRIVATE_FIELDS` and reaches no teacher-lens
        response, which the schema-wide privacy gate asserts. It is
        returned HERE because this is the owner reading their own row
    """

    lenses: list[LensEntry] = Field(default_factory=list)
    self_name: str | None = None
    address: str | None = None


class ProfileUpdateRequest(BaseModel):
    """What a person may change about themselves.

    **Name and address only.** A profile write cannot touch the phone
    number, which is the login and changes only through the OTP path,
    and it cannot touch a lens: a role is computed per request from
    owned batches and enrollments and has no stored field to set
    [TC-11, D-2].

    Both are optional and omitting one leaves it unchanged, so the app
    can save a single edited field without resending the other.

    :ivar self_name: The new name, or None to leave it alone
    :ivar address: The new address, or None to leave it alone
    """

    model_config = ConfigDict(extra="forbid")

    self_name: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)


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
    :return: The available lenses, and this person's own profile
    """
    # The READ needs the context too. Without it the policy hides the
    # row and this returns nulls for a profile that exists — a silent
    # wrong answer rather than a refusal, which is the worse failure
    # of the two.
    set_account_context(session, account_id)

    profile = session.get(Profile, account_id)
    return MeResponse(
        lenses=_entries(lens_summary(session, account_id)),
        self_name=profile.self_name if profile else None,
        address=profile.address if profile else None,
    )


@router.patch("/me", response_model=MeResponse)
def update_me(
    body: ProfileUpdateRequest,
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> MeResponse:
    """Change this person's own name or address.

    **The row is created if it does not exist.** An account may reach
    here before anything wrote a profile for it — a person who signed
    up without one, or whose teacher recorded only a number — and a
    write that failed because there was nothing to update would be a
    confusing refusal for a form that is simply being filled in.

    **Row-level security is what bounds this, not the handler.** The
    app connects as the restricted role and the policy on `profile`
    admits only the owner's row, so a write for another account fails
    at the database rather than relying on this function remembering
    to check [TC-13, D-7].

    :param body: The fields to change; an omitted one is left alone
    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: The updated profile, with the lenses unchanged
    """
    # **Bind the row-level-security context to this account**, which
    # is what the policy means — a person may write their OWN profile
    # — rather than an exemption from it. Without it the insert is
    # refused by the database, which is the policy working: the
    # alternative, writing as the table owner or adding a branch for
    # an unbound session, would weaken the one mechanism standing
    # between a teacher and a child's home address [BR3.2, TC-13].
    #
    # Transaction-local, so the commit below discards it and it cannot
    # leak to the next request to borrow this pooled connection.
    set_account_context(session, account_id)

    profile = session.get(Profile, account_id)
    if profile is None:
        profile = Profile(account_id=account_id)
        session.add(profile)

    # An omitted field is left alone rather than cleared, so saving one
    # edited field does not erase the other.
    if body.self_name is not None:
        profile.self_name = body.self_name
    if body.address is not None:
        profile.address = body.address

    session.commit()

    return MeResponse(
        lenses=_entries(lens_summary(session, account_id)),
        self_name=profile.self_name,
        address=profile.address,
    )
