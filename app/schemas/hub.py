"""Request and response bodies for the public hub's listing editor [0036].

Everything here is the owner's own view of what they chose to publish. The
public pages built in a later unit read through their own view models, so
nothing in this module is served to an anonymous reader.

``teacher_names`` is deliberately not called ``display_name``: that name is
in the forbidden set of the public audience, and a field the public pages
will one day carry must not share it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import MoneyField

__all__ = [
    "AreaOption",
    "BatchListingResponse",
    "BatchListingUpdateRequest",
    "ChecklistItemWire",
    "ConsentRequest",
    "OwnerListingResponse",
    "OwnerListingUpdateRequest",
    "PublishRequest",
    "SlugAvailability",
]

TeachingMode = Literal["in_person", "home_visit", "online"]
ListingStatus = Literal["draft", "published", "hidden", "suspended"]
BatchMode = Literal["in_person", "home_visit", "online"]
Admissions = Literal["open", "waitlist", "closed"]

#: A subject tag, as the column bounds it.
_Tag = Annotated[str, Field(max_length=40)]


class ChecklistItemWire(BaseModel):
    """One requirement of a listing and whether it is met.

    :ivar key: The requirement's stable name
    :ivar done: Whether it is met
    """

    key: str
    done: bool


class OwnerListingUpdateRequest(BaseModel):
    """Edit the owner's listing; an omitted field is left alone.

    An empty string clears a nullable text field.

    :ivar slug: The public path segment
    :ivar public_name: The name shown publicly
    :ivar headline_en: The English headline
    :ivar headline_bn: The Bangla headline
    :ivar bio_en: The English biography
    :ivar bio_bn: The Bangla biography
    :ivar qualifications: Qualifications
    :ivar teaching_mode: How the owner teaches
    :ivar district_code: The district's BBS code
    :ivar upazila_code: The upazila's BBS code; must lie in the district
    :ivar street_address: A centre's street address
    :ivar public_contact_phone: The one number shown publicly
    """

    model_config = ConfigDict(extra="forbid")

    slug: str | None = Field(default=None, max_length=60)
    public_name: str | None = Field(default=None, max_length=120)
    headline_en: str | None = Field(default=None, max_length=200)
    headline_bn: str | None = Field(default=None, max_length=200)
    bio_en: str | None = Field(default=None, max_length=5000)
    bio_bn: str | None = Field(default=None, max_length=5000)
    qualifications: str | None = Field(default=None, max_length=1000)
    teaching_mode: list[TeachingMode] | None = Field(default=None, max_length=3)
    district_code: str | None = Field(default=None, max_length=12)
    upazila_code: str | None = Field(default=None, max_length=12)
    street_address: str | None = Field(default=None, max_length=300)
    public_contact_phone: str | None = Field(default=None, max_length=40)


class OwnerListingResponse(BaseModel):
    """The owner's listing, with what publishing still needs.

    :ivar status: ``draft``, ``published``, ``hidden`` or ``suspended``
    :ivar slug: The public path segment, or None while a draft
    :ivar public_name: The name shown publicly
    :ivar headline_en: The English headline
    :ivar headline_bn: The Bangla headline
    :ivar bio_en: The English biography
    :ivar bio_bn: The Bangla biography
    :ivar qualifications: Qualifications
    :ivar teaching_mode: How the owner teaches
    :ivar district_code: The district's BBS code
    :ivar upazila_code: The upazila's BBS code
    :ivar street_address: A centre's street address
    :ivar public_contact_phone: The one number shown publicly
    :ivar consent_version: The consent text the owner last agreed to
    :ivar published_at: When it was last published
    :ivar checklist: Each requirement and whether it is met
    :ivar publishable: Whether every requirement is met
    :ivar runs_classes: Whether the owner earns the Runs classes badge
    :ivar consent_version_current: The consent text version to agree to now
    """

    status: ListingStatus
    slug: str | None
    public_name: str
    headline_en: str | None
    headline_bn: str | None
    bio_en: str | None
    bio_bn: str | None
    qualifications: str | None
    teaching_mode: list[TeachingMode]
    district_code: str | None
    upazila_code: str | None
    street_address: str | None
    public_contact_phone: str | None
    consent_version: str | None
    published_at: dt.datetime | None
    checklist: list[ChecklistItemWire]
    publishable: bool
    runs_classes: bool
    consent_version_current: str


class PublishRequest(BaseModel):
    """Agree to the listing terms and publish.

    :ivar consent_version: The version of the terms the owner was shown
    """

    model_config = ConfigDict(extra="forbid")

    consent_version: str = Field(max_length=20)


class SlugAvailability(BaseModel):
    """Whether the caller may claim a slug.

    :ivar slug: The slug asked about
    :ivar available: True when it is well formed and nobody else holds it
    """

    slug: str
    available: bool


class AreaOption(BaseModel):
    """One division, district or upazila.

    :ivar code: The BBS geocode
    :ivar kind: ``division``, ``district`` or ``upazila``
    :ivar name_en: The English name
    :ivar name_bn: The Bangla name
    """

    code: str
    kind: Literal["division", "district", "upazila"]
    name_en: str
    name_bn: str


class BatchListingUpdateRequest(BaseModel):
    """Edit one batch's listing; an omitted field is left alone.

    The first save must carry ``show_fee`` and ``show_schedule``.

    :ivar slug: The public path segment, unique per owner
    :ivar description_en: The English description
    :ivar description_bn: The Bangla description
    :ivar syllabus_en: The English syllabus
    :ivar syllabus_bn: The Bangla syllabus
    :ivar class_levels: The class levels taught
    :ivar curriculum: The curriculum; empty clears it
    :ivar subject_tags: Public subject tags
    :ivar mode: How the batch is taught; empty clears it
    :ivar admissions: ``open``, ``waitlist`` or ``closed``
    :ivar show_fee: Whether the fee is public
    :ivar show_schedule: Whether the weekly timetable is public
    """

    model_config = ConfigDict(extra="forbid")

    slug: str | None = Field(default=None, max_length=60)
    description_en: str | None = Field(default=None, max_length=5000)
    description_bn: str | None = Field(default=None, max_length=5000)
    syllabus_en: str | None = Field(default=None, max_length=10000)
    syllabus_bn: str | None = Field(default=None, max_length=10000)
    class_levels: list[Annotated[str, Field(max_length=20)]] | None = Field(
        default=None, max_length=30
    )
    curriculum: str | None = Field(default=None, max_length=30)
    subject_tags: list[_Tag] | None = Field(default=None, max_length=20)
    mode: BatchMode | Literal[""] | None = None
    admissions: Admissions | None = None
    show_fee: bool | None = None
    show_schedule: bool | None = None


class BatchListingResponse(BaseModel):
    """One of the owner's batches with its listing, if it has one yet.

    ``status`` is ``draft`` before any listing row exists.

    :ivar batch_id: The batch
    :ivar batch_name: Its name
    :ivar subjects: Its subject names
    :ivar status: ``draft``, ``published``, ``hidden`` or ``suspended``
    :ivar slug: The public path segment
    :ivar description_en: The English description
    :ivar description_bn: The Bangla description
    :ivar syllabus_en: The English syllabus
    :ivar syllabus_bn: The Bangla syllabus
    :ivar class_levels: The class levels taught
    :ivar curriculum: The curriculum
    :ivar subject_tags: Public subject tags
    :ivar mode: How the batch is taught
    :ivar admissions: ``open``, ``waitlist`` or ``closed``
    :ivar show_fee: Whether the fee is public, or None before a listing
    :ivar show_schedule: Whether the timetable is public, or None
    :ivar fee: The batch fee, only while ``show_fee`` is set
    :ivar teacher_names: The teachers the page may name
    :ivar checklist: Each requirement and whether it is met
    :ivar publishable: Whether every requirement is met
    """

    batch_id: uuid.UUID
    batch_name: str
    subjects: list[str]
    status: ListingStatus
    slug: str | None
    description_en: str | None
    description_bn: str | None
    syllabus_en: str | None
    syllabus_bn: str | None
    class_levels: list[str]
    curriculum: str | None
    subject_tags: list[str]
    mode: BatchMode | None
    admissions: Admissions | None
    show_fee: bool | None
    show_schedule: bool | None
    fee: MoneyField | None
    teacher_names: list[str]
    checklist: list[ChecklistItemWire]
    publishable: bool


class ConsentRequest(BaseModel):
    """A centre member agreeing, or no longer agreeing, to be named.

    :ivar consent: True to be named on the centre's public page
    """

    model_config = ConfigDict(extra="forbid")

    consent: bool
