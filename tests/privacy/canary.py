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
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

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
    """

    strings: frozenset[str]
    owner_id: uuid.UUID


def _canary(label: str) -> str:
    """Build one unique, recognisable private string.

    :param label: A short label naming the field it is seeded into
    :return: The unique string
    """
    return f"canary-{label}-{uuid.uuid4().hex}"


def _digits() -> str:
    """Build a unique eight-digit run for a phone number.

    :return: Eight digits derived from a fresh UUID
    """
    return f"{uuid.uuid4().int % 10**8:08d}"


def seed_canaries(session: Session) -> CanaryWorld:
    """Seed one solo owner whose every private field holds a unique string.

    The session must be able to write ``profile`` past its row policy, so
    callers pass the owner session, as the privacy conftest arranges data.

    :param session: An arranging session
    :return: The seeded world
    """
    now = dt.datetime.now(tz=dt.UTC)
    phone = "+88017" + _digits()
    guardian_phone = "+88018" + _digits()
    self_name = _canary("self-name")
    collection_number = "01" + _digits() + _digits()[:1]
    enrollment_name = _canary("enrollment-name")
    student_name = _canary("student-name")

    account = Account(phone=phone, created_at=now, activated_at=now)
    session.add(account)
    session.flush()
    session.add(Profile(account_id=account.id, self_name=self_name))
    owner = Owner(account_id=account.id, created_at=now)
    session.add(owner)
    session.flush()
    batch = Batch(
        owner_id=owner.id,
        name="Canary batch",
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
                str(enrollment.id),
            }
        ),
        owner_id=owner.id,
    )


def _resolve(path: str, world: CanaryWorld) -> list[str]:
    """Expand a route template into every concrete path to probe.

    ``{locale}`` expands to each of :data:`LOCALES`. Any other placeholder
    raises, so a public route added without a resolver cannot be silently
    skipped: the probe fails loudly until someone teaches it the slug.

    :param path: A route template such as ``/hub/{locale}``
    :param world: The seeded world, for resolvers that need its slugs
    :return: The concrete paths
    :raises NotImplementedError: For a placeholder with no resolver
    """
    del world  # slug resolution arrives with the hub pages
    paths = [path]
    for name in dict.fromkeys(_PLACEHOLDER.findall(path)):
        if name != "locale":
            msg = f"no canary resolver for placeholder {{{name}}} in {path!r}"
            raise NotImplementedError(msg)
        paths = [p.replace("{locale}", loc) for p in paths for loc in LOCALES]
    return paths


def rendered_public_bodies(client: TestClient, paths: Iterable[str]) -> dict[str, str]:
    """Fetch each path anonymously and collect its response body.

    :param client: A client carrying no credentials
    :param paths: Concrete paths to fetch
    :return: The body text keyed by path
    """
    return {path: client.get(path).text for path in paths}


def canary_leaks(bodies: dict[str, str], world: CanaryWorld) -> list[tuple[str, str]]:
    """Find every canary string present in any body.

    :param bodies: Body text keyed by path
    :param world: The seeded world
    :return: ``(path, canary)`` pairs, sorted, empty when nothing leaked
    """
    return sorted(
        (path, canary)
        for path, body in bodies.items()
        for canary in world.strings
        if canary in body
    )


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
