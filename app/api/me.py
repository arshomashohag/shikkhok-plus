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
from typing import Annotated, Final

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.accounts import usernames
from app.accounts.passwords import confirm_password
from app.api.auth import coarse_prefix_of, correlation_of, ip_prefix_of
from app.api.deps import authenticated_account, get_session
from app.auth.ceilings import CeilingChecker
from app.authz.rls import set_account_context
from app.authz.summary import LensSummary, lens_summary
from app.centres.service import workspaces_of
from app.db.models import Account, Profile
from app.db.retry import run_with_retry
from app.schemas.address import CityField, HouseField, PostcodeField, RoadField
from app.schemas.centres import WorkspaceResponse
from app.schemas.errors import ErrorEnvelope
from app.schemas.usernames import (
    UsernameAvailabilityRequest,
    UsernameAvailabilityResponse,
    UsernameChangeRequest,
    UsernameChangeResponse,
)

router = APIRouter(prefix="/v1", tags=["me"])


class LensEntry(BaseModel):
    """One lens the account can choose.

    :ivar kind: Which lens: teacher, class_teacher, student or guardian
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
        returned HERE because this is the owner reading their own row.
        The free-text form, kept for an address typed before 2026-11-05
    :ivar address_house: House or flat, or None. Owner-private, as above
    :ivar address_road: Road or area, or None
    :ivar address_city: City or district, or None
    :ivar address_postcode: Four digits, or None
    :ivar phone: The number this account signs in with. The owner's own
        login, read by the owner on a lens-exempt route; the profile
        shows it read-only, and in-app deletion asks the person to type
        it back as confirmation, which needs the app to know it
    :ivar email: The address this account signs in with, or None [0032].
        The owner's own, like ``phone``
    :ivar has_password: Whether a password is set; an account without
        one is asked to set one [0032]
    :ivar workspaces: Every workspace the teacher lens may act on, solo
        first [0022]. A client sends the chosen one's ``owner_id`` as
        ``X-Workspace-Id``; with one entry, or none, there is nothing to
        choose
    :ivar username: The account's username as stored, or None [U1: FR5.1].
        Owner-only: an ``OWN_ACCOUNT_FIELDS`` pair, served on these
        lens-exempt routes and nowhere else [BR8.1]
    :ivar username_required: True exactly while the account has no
        username [BR5.1]. Computed here on every response, never stored;
        the clients show the choose-username screen on it, and the server
        refuses nothing else for it [BR5.2]
    """

    lenses: list[LensEntry] = Field(default_factory=list)
    workspaces: list[WorkspaceResponse] = Field(default_factory=list)
    self_name: str | None = None
    address: str | None = None
    address_house: str | None = None
    address_road: str | None = None
    address_city: str | None = None
    address_postcode: str | None = None
    phone: str | None = None
    email: str | None = None
    has_password: bool = False
    username: str | None = None
    username_required: bool = True


class ProfileUpdateRequest(BaseModel):
    """What a person may change about themselves.

    **Name and address only.** A profile write cannot touch the phone
    number, which is the login and changes only through the OTP path,
    and it cannot touch a lens: a role is computed per request from
    owned batches and enrollments and has no stored field to set
    [TC-11, D-2].

    Both are optional and omitting one leaves it unchanged, so the app
    can save a single edited field without resending the other.

    Each address part, when sent, must be filled in: an address is
    required (decided 2026-11-05), so a part can be corrected but not
    blanked.

    :ivar self_name: The new name, or None to leave it alone
    :ivar address: The free-text address, for an app older than the four
        parts, or None to leave it alone
    :ivar address_house: The new house or flat, or None to leave it alone
    :ivar address_road: The new road or area, or None to leave it alone
    :ivar address_city: The new city or district, or None to leave it alone
    :ivar address_postcode: The new postcode, or None to leave it alone
    """

    model_config = ConfigDict(extra="forbid")

    self_name: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    address_house: HouseField | None = None
    address_road: RoadField | None = None
    address_city: CityField | None = None
    address_postcode: PostcodeField | None = None


def _entries(summary: LensSummary) -> list[LensEntry]:
    """Render a summary as the ordered list the picker shows.

    Teacher first, then centre teacher, then student, then guardian — a
    fixed order, so the picker does not reshuffle between sign-ins.

    :param summary: The resolved summary
    :return: One entry per available lens
    """
    entries: list[LensEntry] = []
    if summary.is_teacher:
        entries.append(LensEntry(kind="teacher", count=summary.teacher_batches))
    if summary.is_class_teacher:
        # [C4] A centre teacher's own classes; the count is the centres
        # taught at, since the classes change daily.
        entries.append(LensEntry(kind="class_teacher", count=summary.teaching_centres))
    if summary.is_student:
        entries.append(LensEntry(kind="student", count=summary.student_enrollments))
    if summary.is_guardian:
        entries.append(LensEntry(kind="guardian", count=summary.guardian_children))
    return entries


def _me(session: Session, account_id: uuid.UUID, profile: Profile | None) -> MeResponse:
    """Describe this account to its owner, the same way for read and write.

    :param session: The session to query through
    :param account_id: The authenticated account
    :param profile: Its profile row, or None before one exists
    :return: The lenses, the profile and the sign-in number
    """
    account = session.get(Account, account_id)
    return MeResponse(
        lenses=_entries(lens_summary(session, account_id)),
        self_name=profile.self_name if profile else None,
        address=profile.address if profile else None,
        address_house=profile.address_house if profile else None,
        address_road=profile.address_road if profile else None,
        address_city=profile.address_city if profile else None,
        address_postcode=profile.address_postcode if profile else None,
        phone=account.phone if account else None,
        email=account.email if account else None,
        has_password=bool(account and account.password_hash),
        # Read from the account row this request already loads, so the
        # flag can never disagree with the name beside it [BR5.1].
        username=account.username if account else None,
        username_required=account is None or account.username is None,
        workspaces=[
            WorkspaceResponse.model_validate(
                {"owner_id": row.owner_id, "kind": row.kind, "name": row.name}
            )
            for row in workspaces_of(session, account_id)
        ],
    )


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
    return _me(session, account_id, profile)


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
    if body.address_house is not None:
        profile.address_house = body.address_house
    if body.address_road is not None:
        profile.address_road = body.address_road
    if body.address_city is not None:
        profile.address_city = body.address_city
    if body.address_postcode is not None:
        profile.address_postcode = body.address_postcode

    session.commit()

    return _me(session, account_id, profile)


@router.post(
    "/me/username-availability",
    response_model=UsernameAvailabilityResponse,
    responses={
        429: {
            "model": ErrorEnvelope,
            "description": "auth.lookup.too_many: the availability ceilings",
        },
    },
)
def check_my_username_availability(
    body: UsernameAvailabilityRequest,
    request: Request,
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> UsernameAvailabilityResponse:
    """Say whether this account could take a name, as Settings asks [BR3.2].

    **Lens-exempt on ``GET /v1/me``'s reasoning** [BR3.5]: it acts on the
    authenticated account alone and reads nothing another account owns
    beyond a yes or no. It differs from the public lookup only for names
    this account itself holds -- its current key, or a live hold it
    released -- which answer ``available``, since a rename would take them
    back [NFR1.5]. Counted on the public lookup's ceilings, by network.

    :param body: The candidate
    :param request: The incoming request
    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: The status, and for ``invalid`` the rule it broke
    :raises CeilingBreach: A lookup ceiling refused this request
    """
    CeilingChecker(session).check_and_consume_username_lookup(
        ip_prefix=ip_prefix_of(request), coarse_prefix=coarse_prefix_of(request)
    )
    answer = usernames.availability(
        session, body.username, caller=account_id, now=usernames.utc_now()
    )
    return UsernameAvailabilityResponse(
        status=answer.status, message_key=answer.message_key
    )


@router.put(
    "/me/username",
    response_model=UsernameChangeResponse,
    responses={
        400: {
            "model": ErrorEnvelope,
            "description": (
                "A username rule refused it (account.username.*); "
                "account.username.password_required; auth.password.current_wrong"
            ),
        },
        409: {
            "model": ErrorEnvelope,
            "description": (
                "account.username.unavailable; account.username.change_too_soon "
                "with details.next_change_at; auth.password.too_many_attempts"
            ),
        },
        429: {
            "model": ErrorEnvelope,
            "description": "auth.lookup.too_many: too many claims this hour",
        },
    },
)
def change_my_username(
    body: UsernameChangeRequest,
    request: Request,
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> UsernameChangeResponse:
    """Choose the first username, rename, reclaim, or change only its case.

    **Lens-exempt on ``GET /v1/me``'s reasoning** [BR3.5]: it writes the
    authenticated account's own username and nothing else.

    In this order [NFR1.6, NFR4.3]: the format (400, nothing counted);
    the claim ceilings, committed, before the password, any lock or any
    read of another account or hold; then, for an account that already
    has a username, the password, whose failures commit their own count;
    then the change itself as one re-runnable unit of work, under the
    bounded retry because it sends nothing before its commit. A first
    choice needs no password and the one sent is ignored [BR5.3].

    Nobody is signed out [BR6.8]: other devices read the new name from
    ``GET /v1/me``.

    :param body: The candidate, and the password for a rename
    :param request: The incoming request
    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: The stored username and when it may next change
    :raises UsernameRefused: It breaks a username rule
    :raises CeilingBreach: The claim ceilings, or the password's
    :raises UsernamePasswordRequired: A rename without a password, or by
        an account that has none
    :raises ValidationError: ``auth.password.current_wrong``
    :raises UsernameUnavailable: The name is taken or held
    :raises UsernameChangeTooSoon: An ordinary rename inside the window
    """
    candidate = usernames.judge(body.username)
    ip_prefix = ip_prefix_of(request)
    coarse_prefix = coarse_prefix_of(request)
    CeilingChecker(session).check_and_consume_username_claim(
        account_id, ip_prefix, coarse_prefix
    )
    # Whether this is a rename is read again under the account's lock;
    # this read only decides whether to ask for the password first. A
    # first username chosen meanwhile on another device makes the locked
    # re-read a rename, which then refuses for want of one [W7 step 2].
    named: bool = (
        session.execute(_HAS_USERNAME, {"id": account_id}).scalar_one_or_none() is True
    )
    if named:
        confirm_password(
            session,
            account_id,
            body.password,
            ip_prefix=ip_prefix,
            coarse_prefix=coarse_prefix,
        )
    correlation_id = correlation_of(request)
    now = usernames.utc_now()
    result = run_with_retry(
        session,
        lambda: usernames.apply_change(
            session,
            account_id,
            candidate,
            password_confirmed=named,
            now=now,
            correlation_id=correlation_id,
        ),
        correlation_id=correlation_id,
    )
    return UsernameChangeResponse(
        username=result.username, next_change_at=result.next_change_at
    )


#: Whether the account has a username yet, read before its lock.
_HAS_USERNAME: Final = sa.text(
    "SELECT username_key IS NOT NULL FROM account WHERE id = :id"
)
