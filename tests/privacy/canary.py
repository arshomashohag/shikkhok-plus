"""The canary probe harness: seed unique private strings, hunt for them.

Every value a public page must never show is seeded with a unique
``uuid4().hex``-derived string. The probe renders each cacheable public
page and asserts none of them appears in any body. Substring matching on
unique random values has no false positives, and it catches a leak
whatever field name or template carried it.

:func:`rendered_public_bodies` and :func:`canary_leaks` are the ONE
collection and assertion path: the real probe and the planted-leak fixture
both call them, so the fixture proves the real check fires [the same
reasoning as ``unlensed_routes`` taking the application as an argument].
"""

from __future__ import annotations

import datetime as dt
import re
import secrets
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Account, Batch, Enrollment, Owner, Profile, Student
from tests.batches.conftest import make_teacher
from tests.hub.support import add_member, assign_slot, centre_with_manager

__all__ = [
    "LOCALES",
    "CanaryWorld",
    "canary_leaks",
    "rendered_public_bodies",
    "seed_canaries",
    "walk_cacheable_routes",
]

#: The locales every public route is walked in.
LOCALES: tuple[str, ...] = ("en", "bn")

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


@dataclass(frozen=True)
class CanaryWorld:
    """The seeded private values, and the owner that holds them.

    :ivar strings: Every private string a public body must not contain
    :ivar owner_id: The solo owner the strings were seeded under
    :ivar owner_slug: The owner's published listing's slug
    :ivar batch_slug: The batch's published listing's slug
    :ivar centre_slug: The published centre's listing slug
    :ivar centre_batch_slug: The centre's published batch listing slug
    :ivar account_phone: The solo owner's account phone, a canary
    :ivar public_phone: The number the solo owner chose to publish, which
        is NOT a canary and differs from ``account_phone``
    :ivar batch_name: The solo batch's private ``batch.name``
    :ivar draft_name: The never-published draft's public name
    :ivar draft_slug: The never-published draft's slug
    :ivar member_name: The unconsented centre member's display name
    :ivar member_phone: The unconsented centre member's invited phone
    :ivar other_owner_strings: Every private string seeded under the draft
        and the centre, which no other owner's preview may show
    :ivar consented_name: The consented centre member's name, which a
        public page SHOULD show
    :ivar approved_alt_en: The solo owner's approved photo's English alt
        text, which the English owner page SHOULD show
    :ivar approved_alt_bn: Its Bangla alt text, for the Bangla owner page
    :ivar unapproved_photo_strings: The alt texts and ids of the solo
        owner's pending, held and rejected photos; all are canaries
    :ivar pending_photo_strings: The pending photo's share of them, which
        the owner's own preview SHOULD show, marked as awaiting review
    """

    strings: frozenset[str]
    owner_id: uuid.UUID
    owner_slug: str
    batch_slug: str
    centre_slug: str
    centre_batch_slug: str
    account_phone: str
    public_phone: str
    batch_name: str
    draft_name: str
    draft_slug: str
    member_name: str
    member_phone: str
    other_owner_strings: frozenset[str]
    consented_name: str
    approved_alt_en: str
    approved_alt_bn: str
    unapproved_photo_strings: frozenset[str]
    pending_photo_strings: frozenset[str]


def _canary(label: str) -> str:
    """Build one unique, recognisable private string.

    :param label: A short label naming the field it is seeded into
    :return: The unique string
    """
    return f"canary-{label}-{uuid.uuid4().hex}"


def _digits(width: int) -> str:
    """Build a run of random digits, every position random.

    :param width: How many digit positions the target format allows
    :return: Exactly ``width`` digits from the system CSPRNG
    """
    return f"{secrets.randbelow(10**width):0{width}d}"


#: The centre member who agreed to be named: a page SHOULD show this.
CONSENTED_NAME = "Consented Canary Sir"

#: The approved photo's alt texts: the owner page SHOULD show these.
APPROVED_ALT_EN = "Canary approved classroom photo"
APPROVED_ALT_BN = "ক্যানারি অনুমোদিত শ্রেণিকক্ষের ছবি"


@dataclass(frozen=True)
class _Draft:
    """The seeded never-published owner.

    :ivar name: Its public name
    :ivar slug: Its slug
    :ivar strings: Every private string seeded under it
    """

    name: str
    slug: str
    strings: frozenset[str]


@dataclass(frozen=True)
class _Centre:
    """The seeded published centre.

    :ivar slug: The centre listing's slug
    :ivar batch_slug: Its batch listing's slug
    :ivar member_name: The unconsented member's display name
    :ivar member_phone: The unconsented member's invited phone
    :ivar strings: Every private string seeded under it
    """

    slug: str
    batch_slug: str
    member_name: str
    member_phone: str
    strings: frozenset[str]


@dataclass(frozen=True)
class _Photos:
    """The solo owner's seeded photos.

    :ivar unapproved: Every unapproved photo's alt texts and id
    :ivar pending: The pending photo's alt texts and id
    """

    unapproved: frozenset[str]
    pending: frozenset[str]


def _photo(
    session: Session,
    owner_id: uuid.UUID,
    *,
    status: str,
    alt_en: str,
    alt_bn: str,
    batch_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one photo with its variants and dimensions recorded.

    :param session: An arranging session
    :param owner_id: The owner
    :param status: Its status; only ``approved`` gets a public key
    :param alt_en: Its English alt text
    :param alt_bn: Its Bangla alt text
    :param batch_id: Its batch, or None for the owner's own gallery
    :return: The media id
    """
    media_id = uuid.uuid4()
    session.execute(
        sa.text(
            "INSERT INTO listing_media (id, owner_id, batch_id, status, "
            "content_type, byte_size, public_key, width, height, widths, "
            "alt_en, alt_bn) VALUES (:id, :o, :b, CAST(:st AS media_status), "
            "'image/jpeg', 2048, :key, 1200, 800, '{320,960}', :en, :bn)"
        ),
        {
            "id": media_id,
            "o": owner_id,
            "b": batch_id,
            "st": status,
            "key": uuid.uuid4().hex if status == "approved" else None,
            "en": alt_en,
            "bn": alt_bn,
        },
    )
    return media_id


def _seed_photos(session: Session, owner_id: uuid.UUID, batch_id: uuid.UUID) -> _Photos:
    """Seed one approved photo and three that must never be public.

    The approved photo's alt texts are public. A pending and a held photo
    sit in the owner's own gallery and a rejected one in the batch's, each
    with canary alt texts: only the status keeps them off the owner page
    and the batch page, which the view must therefore be checking.

    :param session: An arranging session
    :param owner_id: The solo owner
    :param batch_id: The solo owner's published batch
    :return: The canaries the unapproved photos carry
    """
    _photo(
        session,
        owner_id,
        status="approved",
        alt_en=APPROVED_ALT_EN,
        alt_bn=APPROVED_ALT_BN,
    )
    strings: dict[str, frozenset[str]] = {}
    for status, batch in (
        ("pending_review", None),
        ("held", None),
        ("rejected", batch_id),
    ):
        alt_en, alt_bn = _canary(f"{status}-alt-en"), _canary(f"{status}-alt-bn")
        media_id = _photo(
            session,
            owner_id,
            status=status,
            alt_en=alt_en,
            alt_bn=alt_bn,
            batch_id=batch,
        )
        strings[status] = frozenset({alt_en, alt_bn, str(media_id), media_id.hex})
    session.commit()
    return _Photos(
        unapproved=frozenset().union(*strings.values()),
        pending=strings["pending_review"],
    )


def _seed_draft(session: Session, now: dt.datetime) -> _Draft:
    """Seed an owner that never published, with a public name and a slug.

    Its batch listing IS published, so only the owner's draft status keeps
    the batch off the hub: the trap an owner unpublish also springs.

    :param session: An arranging session
    :param now: The seeding time
    :return: The draft's identifying strings
    """
    batch_name = _canary("draft-batch-name")
    teacher = make_teacher(session, name=batch_name)
    name, slug, batch_slug = (
        _canary("draft-public-name"),
        _canary("draft-slug").lower(),
        _canary("draft-batch-slug").lower(),
    )
    account_phone = session.execute(
        sa.text("SELECT phone FROM account WHERE id = :a"),
        {"a": teacher.account_id},
    ).scalar_one()
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name) "
            "VALUES (:o, :slug, 'draft', :name)"
        ),
        {"o": teacher.owner_id, "slug": slug, "name": name},
    )
    session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, slug, status, "
            "public_title, class_levels, subject_tags, show_fee, "
            "show_schedule, published_at) VALUES (:b, :o, :slug, 'published', "
            "'Draft batch title', ARRAY['class_9']::varchar[], "
            "ARRAY['maths']::varchar[], true, true, :now)"
        ),
        {"b": teacher.batch_id, "o": teacher.owner_id, "slug": batch_slug, "now": now},
    )
    session.commit()
    return _Draft(
        name=name,
        slug=slug,
        strings=frozenset({name, slug, batch_slug, batch_name, account_phone}),
    )


def _seed_centre(session: Session, now: dt.datetime) -> _Centre:
    """Seed a published centre, a published batch and two members.

    The consented member is named on the batch page. The unconsented one
    teaches a slot of the same published batch, so only the consent rule
    keeps their name and phone off the page.

    :param session: An arranging session
    :param now: The seeding time
    :return: The centre's identifying strings
    """
    centre_name = _canary("centre-owner-name")
    centre = centre_with_manager(session, name=centre_name)
    batch_name = _canary("centre-batch-name")
    manager_name = _canary("manager-name")
    member_name = _canary("member-name")
    member_phone = "+8801" + _digits(9)
    member_account_phone = "+8801" + _digits(9)
    consented_account_phone = "+8801" + _digits(9)
    slug, batch_slug = "canary-centre", "canary-centre-batch"

    accounts = []
    for account_phone in (member_account_phone, consented_account_phone):
        account = Account(phone=account_phone, created_at=now, activated_at=now)
        session.add(account)
        session.flush()
        accounts.append(account.id)
    session.commit()
    unconsented, _ = add_member(
        session, centre.owner_id, name=member_name, account_id=accounts[0]
    )
    consented, _ = add_member(
        session,
        centre.owner_id,
        name=CONSENTED_NAME,
        consented=True,
        account_id=accounts[1],
    )
    session.execute(
        sa.text("UPDATE owner_member SET invited_phone = :p WHERE id = :m"),
        {"p": member_phone, "m": unconsented},
    )
    session.execute(
        sa.text(
            "UPDATE owner_member SET display_name = :n "
            "WHERE owner_id = :o AND role = 'manager'"
        ),
        {"n": manager_name, "o": centre.owner_id},
    )
    session.execute(
        sa.text("UPDATE batch SET name = :n WHERE id = :b"),
        {"n": batch_name, "b": centre.batch_id},
    )
    session.commit()
    assign_slot(session, centre.batch_id, unconsented)
    assign_slot(session, centre.batch_id, consented)
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "headline_en, published_at) VALUES (:o, :slug, 'published', "
            "'Canary Centre', 'Canary centre headline', :now)"
        ),
        {"o": centre.owner_id, "slug": slug, "now": now},
    )
    session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, slug, status, "
            "public_title, class_levels, subject_tags, show_fee, "
            "show_schedule, published_at) VALUES (:b, :o, :slug, 'published', "
            "'Centre public title', ARRAY['class_9']::varchar[], "
            "ARRAY['maths']::varchar[], true, true, :now)"
        ),
        {"b": centre.batch_id, "o": centre.owner_id, "slug": batch_slug, "now": now},
    )
    session.commit()
    return _Centre(
        slug=slug,
        batch_slug=batch_slug,
        member_name=member_name,
        member_phone=member_phone,
        strings=frozenset(
            {
                centre_name,
                batch_name,
                manager_name,
                member_name,
                member_phone,
                member_account_phone,
                consented_account_phone,
            }
        ),
    )


def seed_canaries(session: Session) -> CanaryWorld:
    """Seed one solo owner whose every private field holds a unique string.

    The session must be able to write ``profile`` past its row policy, so
    callers pass the owner session, as the privacy conftest arranges data.

    :param session: An arranging session
    :return: The seeded world
    """
    now = dt.datetime.now(tz=dt.UTC)
    phone = "+8801" + _digits(9)
    guardian_phone = "+8801" + _digits(9)
    self_name = _canary("self-name")
    collection_number = "01" + _digits(9)
    enrollment_name = _canary("enrollment-name")
    student_name = _canary("student-name")
    batch_name = _canary("batch-name")

    account = Account(phone=phone, created_at=now, activated_at=now)
    session.add(account)
    session.flush()
    session.add(Profile(account_id=account.id, self_name=self_name))
    owner = Owner(account_id=account.id, created_at=now)
    session.add(owner)
    session.flush()
    batch = Batch(
        owner_id=owner.id,
        name=batch_name,
        collection_number=collection_number,
        marksheet_visible=True,
        active=True,
        created_at=now,
    )
    session.add(batch)
    session.flush()
    student = Student(
        owner_id=owner.id,
        display_name=student_name,
        guardian_phone=guardian_phone,
        created_at=now,
    )
    session.add(student)
    session.flush()
    enrollment = Enrollment(
        batch_id=batch.id,
        student_id=student.id,
        display_name=enrollment_name,
        guardian_phone=guardian_phone,
        student_decision="pending",
        guardian_decision="pending",
        created_at=now,
    )
    session.add(enrollment)
    session.flush()
    # Published, so every cacheable page has something of this owner's to
    # render: the owner page, the batch page, a search hit, the sitemap.
    owner_slug, batch_slug = "canary-owner", "canary-batch"
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "headline_en, published_at) VALUES (:o, :slug, 'published', "
            "'Canary Tutor', 'Canary headline', :now)"
        ),
        {"o": owner.id, "slug": owner_slug, "now": now},
    )
    session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, slug, status, "
            "public_title, class_levels, subject_tags, show_fee, "
            "show_schedule, published_at) VALUES (:b, :o, :slug, 'published', "
            "'Canary public title', ARRAY['class_9']::varchar[], "
            "ARRAY['maths']::varchar[], true, true, :now)"
        ),
        {"b": batch.id, "o": owner.id, "slug": batch_slug, "now": now},
    )
    # The owner publishes a contact number that is not their account phone.
    public_phone = "+8801" + _digits(9)
    while public_phone == phone:
        public_phone = "+8801" + _digits(9)
    session.execute(
        sa.text(
            "UPDATE owner_listing SET public_contact_phone = :p WHERE owner_id = :o"
        ),
        {"p": public_phone, "o": owner.id},
    )
    session.commit()

    photos = _seed_photos(session, owner.id, batch.id)
    draft = _seed_draft(session, now)
    centre = _seed_centre(session, now)

    return CanaryWorld(
        strings=frozenset(
            {
                self_name,
                phone,
                collection_number,
                enrollment_name,
                guardian_phone,
                student_name,
                batch_name,
                str(enrollment.id),
                enrollment.id.hex,
                *photos.unapproved,
                *draft.strings,
                *centre.strings,
            }
        ),
        owner_id=owner.id,
        owner_slug=owner_slug,
        batch_slug=batch_slug,
        centre_slug=centre.slug,
        centre_batch_slug=centre.batch_slug,
        account_phone=phone,
        public_phone=public_phone,
        batch_name=batch_name,
        draft_name=draft.name,
        draft_slug=draft.slug,
        member_name=centre.member_name,
        member_phone=centre.member_phone,
        other_owner_strings=frozenset({*draft.strings, *centre.strings}),
        consented_name=CONSENTED_NAME,
        approved_alt_en=APPROVED_ALT_EN,
        approved_alt_bn=APPROVED_ALT_BN,
        unapproved_photo_strings=photos.unapproved,
        pending_photo_strings=photos.pending,
    )


def _resolve(path: str, world: CanaryWorld) -> list[str]:
    """Expand a route template into every concrete path to probe.

    ``{locale}`` expands to each of :data:`LOCALES`, and ``{owner_slug}``
    and ``{batch_slug}`` to both the solo pair and the centre pair. Any
    other placeholder raises, so a public route added without a resolver
    cannot be silently skipped: the probe fails loudly until someone
    teaches it the placeholder.

    :param path: A route template such as ``/hub/{locale}``
    :param world: The seeded world, for resolvers that need its slugs
    :return: The concrete paths
    :raises NotImplementedError: For a placeholder with no resolver
    """
    pairs = (
        (world.owner_slug, world.batch_slug),
        (world.centre_slug, world.centre_batch_slug),
    )
    paths = [path]
    for name in dict.fromkeys(_PLACEHOLDER.findall(path)):
        if name == "locale":
            paths = [p.replace("{locale}", loc) for p in paths for loc in LOCALES]
        elif name not in {"owner_slug", "batch_slug"}:
            msg = f"no canary resolver for placeholder {{{name}}} in {path!r}"
            raise NotImplementedError(msg)
    if "{owner_slug}" in path or "{batch_slug}" in path:
        # The two slugs travel as one pair, so a path naming either yields
        # one path per pair, whichever of them it names.
        paths = [
            p.replace("{owner_slug}", owner).replace("{batch_slug}", batch)
            for p in paths
            for owner, batch in pairs
        ]
    return paths


def rendered_public_bodies(client: TestClient, paths: Iterable[str]) -> dict[str, str]:
    """Fetch each path anonymously and collect its response body.

    :param client: A client carrying no credentials
    :param paths: Concrete paths to fetch
    :return: The body text keyed by path
    """
    bodies: dict[str, str] = {}
    for path in paths:
        response = client.get(path)
        if response.status_code != 200:
            msg = f"public path {path!r} returned {response.status_code}, not 200"
            raise AssertionError(msg)
        bodies[path] = response.text
    return bodies


def _forms(canary: str) -> set[str]:
    """Expand a canary into every form a page might render it in.

    A numeric canary (a phone or collection number) is also matched as its
    digits alone, its national ``0``-prefixed form without the ``880``
    country code, and with the ``+`` percent-encoded. Everything is
    lower-cased, so ids and names match whatever case a page renders.

    :param canary: A seeded private string
    :return: The lower-cased forms to look for
    """
    forms = {canary.lower()}
    if re.fullmatch(r"\+?\d+", canary):
        digits = canary.lstrip("+")
        forms |= {digits, f"%2b{digits}"}
        if digits.startswith("880"):
            forms.add("0" + digits[3:])
    return forms


def canary_leaks(bodies: dict[str, str], world: CanaryWorld) -> list[tuple[str, str]]:
    """Find every canary string present in any body, in any rendered form.

    Each body is checked as-is and again with spaces and hyphens removed,
    so ``017-1234 5678`` is not a way past the probe.

    :param bodies: Body text keyed by path
    :param world: The seeded world
    :return: ``(path, canary)`` pairs, sorted, empty when nothing leaked
    """
    found: list[tuple[str, str]] = []
    for path, body in bodies.items():
        lowered = body.lower()
        squeezed = re.sub(r"[ \-]", "", lowered)
        found.extend(
            (path, canary)
            for canary in world.strings
            if any(f in lowered or f in squeezed for f in _forms(canary))
        )
    return sorted(found)


def walk_cacheable_routes(
    client: TestClient,
    world: CanaryWorld,
    routes: Iterable[tuple[str, str]],
) -> dict[str, str]:
    """Resolve and fetch every cacheable public route.

    :param client: A client carrying no credentials
    :param world: The seeded world
    :param routes: ``(method, path-template)`` pairs, GET only
    :return: The body text keyed by concrete path
    :raises NotImplementedError: For a route with an unresolvable placeholder
    """
    paths = [
        p for _method, template in sorted(routes) for p in _resolve(template, world)
    ]
    return rendered_public_bodies(client, paths)
