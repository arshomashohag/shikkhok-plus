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
    """

    strings: frozenset[str]
    owner_id: uuid.UUID
    owner_slug: str
    batch_slug: str


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
    session.commit()

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
            }
        ),
        owner_id=owner.id,
        owner_slug=owner_slug,
        batch_slug=batch_slug,
    )


def _resolve(path: str, world: CanaryWorld) -> list[str]:
    """Expand a route template into every concrete path to probe.

    ``{locale}`` expands to each of :data:`LOCALES`, and ``{owner_slug}``
    and ``{batch_slug}`` to the seeded world's published listings. Any
    other placeholder raises, so a public route added without a resolver
    cannot be silently skipped: the probe fails loudly until someone
    teaches it the placeholder.

    :param path: A route template such as ``/hub/{locale}``
    :param world: The seeded world, for resolvers that need its slugs
    :return: The concrete paths
    :raises NotImplementedError: For a placeholder with no resolver
    """
    slugs = {"owner_slug": world.owner_slug, "batch_slug": world.batch_slug}
    paths = [path]
    for name in dict.fromkeys(_PLACEHOLDER.findall(path)):
        if name == "locale":
            paths = [p.replace("{locale}", loc) for p in paths for loc in LOCALES]
        elif name in slugs:
            paths = [p.replace(f"{{{name}}}", slugs[name]) for p in paths]
        else:
            msg = f"no canary resolver for placeholder {{{name}}} in {path!r}"
            raise NotImplementedError(msg)
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
