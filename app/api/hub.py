"""The public hub's listing editor routes [0036].

**Every route here resolves a lens** -- a :class:`TeacherLens` for the
owner's own listing and batch pages, and a :class:`CentreMemberLens` for a
member's consent to be named -- so the route-enumeration gate needs no
allowlist entry. The owner id always comes from the lens, never from the
request, so no route can name another owner's listing.

Nothing here is public: these are the owner's own views of what they chose
to publish, and the pages an anonymous reader sees are built separately.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import centre_member_lens, get_session, teacher_lens
from app.auth.ceilings import CeilingChecker
from app.authz.lenses import CentreMemberLens, TeacherLens
from app.db.models import OwnerListing
from app.hub.areas import list_areas
from app.hub.listings import batches, owner
from app.hub.listings.badge import runs_classes
from app.hub.listings.batches import BatchListingUpdate, BatchListingView
from app.hub.listings.checklist import (
    ChecklistItem,
    owner_checklist,
    owner_publishable,
)
from app.hub.listings.consent import HUB_CONSENT_VERSION
from app.hub.listings.member_consent import set_public_name_consent
from app.hub.listings.names import teacher_names
from app.hub.listings.owner import OwnerListingUpdate
from app.local_time import bangladesh_today
from app.money.wire import to_wire
from app.schemas.errors import ErrorEnvelope
from app.schemas.hub import (
    AreaOption,
    BatchListingResponse,
    BatchListingUpdateRequest,
    ChecklistItemWire,
    ConsentRequest,
    OwnerListingResponse,
    OwnerListingUpdateRequest,
    PublishRequest,
    SlugAvailability,
)
from app.schemas.money import Money as WireMoney

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["hub"])

_AUTH_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {"model": ErrorEnvelope, "description": "No credential, or an expired one."},
    403: {
        "model": ErrorEnvelope,
        "description": "No lens reaches this; absence reads the same.",
    },
}

_WRITE_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    **_AUTH_ERRORS,
    400: {
        "model": ErrorEnvelope,
        "description": "The request is wrong. Fix and resubmit; never retry as-is.",
    },
    404: {"model": ErrorEnvelope, "description": "No such batch of yours."},
    409: {
        "model": ErrorEnvelope,
        "description": "Valid request; current state forbids it. Refetch and decide.",
    },
}


def _checklist(items: list[ChecklistItem]) -> list[ChecklistItemWire]:
    """Render a checklist.

    :param items: The items
    :return: The wire form
    """
    return [ChecklistItemWire(key=i.key, done=i.done) for i in items]


def _owner_response(
    session: Session, lens: TeacherLens, listing: OwnerListing
) -> OwnerListingResponse:
    """Render the owner's listing with its checklist and badge.

    :param session: The session
    :param lens: The owner's lens
    :param listing: The listing
    :return: The response
    """
    items = owner_checklist(listing)
    return OwnerListingResponse.model_validate(
        {
            "status": listing.status,
            "slug": listing.slug,
            "public_name": listing.public_name,
            "headline_en": listing.headline_en,
            "headline_bn": listing.headline_bn,
            "bio_en": listing.bio_en,
            "bio_bn": listing.bio_bn,
            "qualifications": listing.qualifications,
            "teaching_mode": list(listing.teaching_mode),
            "district_code": listing.district_code,
            "upazila_code": listing.upazila_code,
            "street_address": listing.street_address,
            "public_contact_phone": listing.public_contact_phone,
            "consent_version": listing.consent_version,
            "published_at": listing.published_at,
            "checklist": _checklist(items),
            "publishable": owner_publishable(items),
            "runs_classes": runs_classes(session, lens.owner_id, bangladesh_today()),
            "consent_version_current": HUB_CONSENT_VERSION,
        }
    )


def _batch_response(
    session: Session, lens: TeacherLens, views: list[BatchListingView]
) -> list[BatchListingResponse]:
    """Render batch views, naming their teachers in one query.

    :param session: The session
    :param lens: The owner's lens
    :param views: The views
    :return: One response per view, in order
    """
    names = teacher_names(session, lens.owner_id, [v.batch_id for v in views])
    out = []
    for view in views:
        listing = view.listing
        fee = (
            WireMoney(to_wire(view.default_fee))
            if listing is not None and listing.show_fee and view.default_fee is not None
            else None
        )
        fields: dict[str, object] = {
            "status": "none",
            "slug": None,
            "description_en": None,
            "description_bn": None,
            "syllabus_en": None,
            "syllabus_bn": None,
            "class_levels": [],
            "curriculum": None,
            "subject_tags": [],
            "mode": None,
            "admissions": None,
            "show_fee": None,
            "show_schedule": None,
        }
        if listing is not None:
            for name in fields:
                value = getattr(listing, name)
                fields[name] = list(value) if isinstance(value, list) else value
        out.append(
            BatchListingResponse.model_validate(
                {
                    **fields,
                    "batch_id": view.batch_id,
                    "batch_name": view.batch_name,
                    "subjects": view.subjects,
                    "fee": fee,
                    "teacher_names": names[view.batch_id],
                    "checklist": _checklist(view.checklist),
                    "publishable": owner_publishable(view.checklist),
                }
            )
        )
    return out


def _one_batch(
    session: Session, lens: TeacherLens, batch_id: uuid.UUID
) -> BatchListingResponse:
    """Render one batch's listing as it now stands.

    :param session: The session
    :param lens: The owner's lens
    :param batch_id: The batch
    :return: The response
    """
    return _batch_response(session, lens, [batches.view_one(session, lens, batch_id)])[
        0
    ]


@router.get("/hub/listing", response_model=OwnerListingResponse, responses=_AUTH_ERRORS)
def get_listing(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> OwnerListingResponse:
    """Read the owner's listing, drafting one on the first call.

    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: The listing and what it still needs
    """
    return _owner_response(session, lens, owner.get_or_draft(session, lens))


@router.put(
    "/hub/listing", response_model=OwnerListingResponse, responses=_WRITE_ERRORS
)
def put_listing(
    body: OwnerListingUpdateRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> OwnerListingResponse:
    """Edit the owner's listing.

    **Bounded per owner and day**: each call consumes one of the day's
    listing edits, so a loop rewriting the page is refused with a 409.

    :param body: The edits; an omitted field is left alone
    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: The listing after the edit
    :raises CeilingBreach: The owner has used today's edits
    """
    CeilingChecker(session).check_and_consume_hub_listing(lens.owner_id)
    listing = owner.update(session, lens, OwnerListingUpdate(**body.model_dump()))
    return _owner_response(session, lens, listing)


@router.post(
    "/hub/listing/publish",
    response_model=OwnerListingResponse,
    responses=_WRITE_ERRORS,
)
def publish_listing(
    body: PublishRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> OwnerListingResponse:
    """Agree to the listing terms and make the listing public.

    :param body: The version of the terms the owner was shown
    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: The published listing
    """
    listing = owner.publish(
        session, lens, body.consent_version, dt.datetime.now(tz=dt.UTC)
    )
    return _owner_response(session, lens, listing)


@router.post(
    "/hub/listing/unpublish",
    response_model=OwnerListingResponse,
    responses=_WRITE_ERRORS,
)
def unpublish_listing(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> OwnerListingResponse:
    """Hide the owner's listing; the data is kept.

    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: The listing
    """
    listing = owner.unpublish(session, lens, dt.datetime.now(tz=dt.UTC))
    return _owner_response(session, lens, listing)


@router.get(
    "/hub/slugs/{slug}", response_model=SlugAvailability, responses=_AUTH_ERRORS
)
def slug_availability(
    slug: str,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> SlugAvailability:
    """Say whether the caller may claim a slug.

    :param slug: The wanted slug
    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: Whether it is free and well formed
    """
    return SlugAvailability(
        slug=slug, available=owner.slug_available(session, slug, lens)
    )


@router.get("/hub/areas", response_model=list[AreaOption], responses=_AUTH_ERRORS)
def hub_areas(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
    parent: Annotated[str | None, Query(max_length=12)] = None,
) -> list[AreaOption]:
    """List the divisions, or the areas directly inside one.

    :param lens: The owner's lens
    :param session: The request-scoped session
    :param parent: The enclosing area's code; omit for the divisions
    :return: The areas; empty for an unknown parent
    """
    del lens
    return [
        AreaOption.model_validate(
            {"code": a.code, "kind": a.kind, "name_en": a.name_en, "name_bn": a.name_bn}
        )
        for a in list_areas(session, parent)
    ]


@router.get(
    "/hub/batch-listings",
    response_model=list[BatchListingResponse],
    responses=_AUTH_ERRORS,
)
def list_batch_listings(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> list[BatchListingResponse]:
    """List the owner's active batches with their listing state.

    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: One entry per active batch, oldest first
    """
    return _batch_response(session, lens, batches.list_for_owner(session, lens))


@router.put(
    "/batches/{batch_id}/listing",
    response_model=BatchListingResponse,
    responses=_WRITE_ERRORS,
)
def put_batch_listing(
    batch_id: uuid.UUID,
    body: BatchListingUpdateRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> BatchListingResponse:
    """Create or edit one batch's listing.

    Shares the owner's daily allowance of listing edits.

    :param batch_id: The batch
    :param body: The edits; an omitted field is left alone
    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: The batch with its listing
    :raises CeilingBreach: The owner has used today's edits
    """
    CeilingChecker(session).check_and_consume_hub_listing(lens.owner_id)
    batches.upsert(session, lens, batch_id, BatchListingUpdate(**body.model_dump()))
    return _one_batch(session, lens, batch_id)


@router.post(
    "/batches/{batch_id}/listing/publish",
    response_model=BatchListingResponse,
    responses=_WRITE_ERRORS,
)
def publish_batch_listing(
    batch_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> BatchListingResponse:
    """Make one batch's listing public, under an owner who already is.

    :param batch_id: The batch
    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: The batch with its listing
    """
    batches.publish(session, lens, batch_id, dt.datetime.now(tz=dt.UTC))
    return _one_batch(session, lens, batch_id)


@router.post(
    "/batches/{batch_id}/listing/unpublish",
    response_model=BatchListingResponse,
    responses=_WRITE_ERRORS,
)
def unpublish_batch_listing(
    batch_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> BatchListingResponse:
    """Hide one batch's listing; the data is kept.

    :param batch_id: The batch
    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: The batch with its listing
    """
    batches.unpublish(session, lens, batch_id, dt.datetime.now(tz=dt.UTC))
    return _one_batch(session, lens, batch_id)


@router.put(
    "/centres/{centre_id}/members/me/public-name-consent",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_AUTH_ERRORS,
)
def put_public_name_consent(
    body: ConsentRequest,
    lens: Annotated[CentreMemberLens, Depends(centre_member_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Agree, or stop agreeing, to be named on the centre's public page.

    :param body: ``consent`` true to be named, false to withdraw
    :param lens: The caller's lens on their own membership
    :param session: The request-scoped session
    :return: An empty 204
    """
    set_public_name_consent(session, lens, body.consent, dt.datetime.now(tz=dt.UTC))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
