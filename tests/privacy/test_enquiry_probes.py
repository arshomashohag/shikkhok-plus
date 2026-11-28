"""Adversarial probes of the join-request routes [H5].

A join request is the guardian's own, read by the people who run the
listing it was sent to and by nobody else. So the boundaries are:

* another owner reaching it answers exactly as an id that never existed,
  for a read and for every close;
* another guardian withdrawing it changes nothing;
* no platform administrator route carries any of its columns, and the
  administrator's route count does not move.

Every probe runs through the restricted application role, behind this
package's row-security gate.
"""

from __future__ import annotations

import pathlib
import uuid
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.contract.privacy import _response_schema
from app.contract.routes import PLATFORM_ADMIN_ROUTES, _api_routes
from app.db.models import ListingEnquiry
from app.main import create_app
from tests.conftest import bearer
from tests.enquiries.support import enquirable_owner, guardian
from tests.reviews.support import account

ROOT: Final = pathlib.Path(__file__).resolve().parents[2]

#: Columns any table has, which name nothing of a request on their own.
#: ``kind`` [0049] says only whether a row is a request or an interest, and
#: other tables use the name for unrelated things, such as an owner's kind.
_GENERIC: Final = frozenset(
    {"id", "owner_id", "batch_id", "status", "created_at", "kind"}
)

#: Every column that is a request's own content or history.
ENQUIRY_COLUMNS: Final = (
    frozenset(column.name for column in ListingEnquiry.__table__.columns) - _GENERIC
)

#: What an administrator module would have to name to read a request: the
#: table, the service package, or the wire models [review M2]. The last
#: matters because a gate exempts ``OwnerEnquiryWire.guardian_email`` by
#: schema name, so an admin route reusing that model would carry the
#: guardian's address past it, and the response walk below would not see
#: ``guardian_email`` either, since it is no ``listing_enquiry`` column.
ENQUIRY_NEEDLES: Final = (
    "listing_enquiry",
    "app.hub.enquiries",
    "app.schemas.enquiries",
)

#: Where every administrator route and the moderation it serves live.
ADMIN_SOURCES: Final = (
    ROOT / "app" / "api" / "admin.py",
    ROOT / "app" / "api" / "admin_auth.py",
    ROOT / "app" / "admin",
    ROOT / "app" / "moderation",
)


def _request(client: TestClient, session: Session) -> tuple[str, uuid.UUID]:
    """Have a guardian send one request to a fresh owner.

    :param client: The test client
    :param session: An arranging session
    :return: The request's id and its owner's account
    """
    world = enquirable_owner(session)
    sent = client.post(
        f"/v1/hub/owners/{world.owner_slug}/enquiries",
        json={
            "student_name": "Nadia Rahman",
            "class_level": "class_8",
            "share_contact": True,
            "declares_adult_guardian": True,
        },
        headers=bearer(session, guardian(session)),
    )
    assert sent.status_code == 201, sent.text
    return str(sent.json()["id"]), world.lens.account_id


def _row(session: Session, enquiry_id: str) -> tuple[object, ...]:
    """Read a request's stored state.

    :param session: An arranging session
    :param enquiry_id: The request
    :return: Its status, outcome and closing time
    """
    session.rollback()
    return tuple(
        session.execute(
            sa.text(
                "SELECT status, outcome, closed_at FROM listing_enquiry WHERE id = :e"
            ),
            {"e": uuid.UUID(enquiry_id)},
        ).one()
    )


@pytest.mark.usefixtures("enquiries_on")
def test_teacher_b_reaches_a_request_of_a_only_as_a_random_id(
    client: TestClient, owner_session: Session
) -> None:
    """B's read and every close of A's request answer a never-minted id's bytes."""
    enquiry_id, owner_a = _request(client, owner_session)
    owner_b = enquirable_owner(owner_session).lens.account_id
    b_headers = bearer(owner_session, owner_b)
    random_id = str(uuid.uuid4())

    answers = {
        (response.status_code, response.content)
        for target in (enquiry_id, random_id)
        for response in [
            client.get(f"/v1/hub/enquiries/{target}", headers=b_headers),
            *(
                client.post(
                    f"/v1/hub/enquiries/{target}/close",
                    json={"outcome": outcome},
                    headers=b_headers,
                )
                for outcome in ("added", "not_now", "call_us")
            ),
        ]
    }

    assert len(answers) == 1
    ((status, body),) = answers
    assert status == 404
    assert b'"ENQUIRY_NOT_FOUND"' in body
    assert _row(owner_session, enquiry_id) == ("open", None, None)
    assert client.get("/v1/hub/enquiries", headers=b_headers).json() == []
    listed = client.get("/v1/hub/enquiries", headers=bearer(owner_session, owner_a))
    assert [row["id"] for row in listed.json()] == [enquiry_id]


@pytest.mark.usefixtures("enquiries_on")
def test_guardian_b_withdrawing_a_request_of_a_leaves_it(
    client: TestClient, owner_session: Session
) -> None:
    """Another guardian's delete is the quiet 204 of a missing id, and no more."""
    enquiry_id, owner_a = _request(client, owner_session)
    stranger = bearer(owner_session, account(owner_session))

    withdrawn = client.delete(f"/v1/me/hub/enquiries/{enquiry_id}", headers=stranger)
    missing = client.delete(f"/v1/me/hub/enquiries/{uuid.uuid4()}", headers=stranger)

    assert (withdrawn.status_code, withdrawn.content) == (
        missing.status_code,
        missing.content,
    )
    assert withdrawn.status_code == 204
    assert _row(owner_session, enquiry_id) == ("open", None, None)
    assert client.get("/v1/me/hub/enquiries", headers=stranger).json() == []
    inbox = client.get(
        "/v1/me/notifications",
        params={"kind": "hub_enquiry_received"},
        headers=bearer(owner_session, owner_a),
    )
    assert [item["source_id"] for item in inbox.json()["items"]] == [enquiry_id]


def _property_names(
    schema: dict[str, object],
    definitions: dict[str, dict[str, object]],
    seen: frozenset[str],
) -> set[str]:
    """Collect every property name reachable from a schema.

    :param schema: The schema node
    :param definitions: The document's components
    :param seen: Components already walked, the cycle guard
    :return: The names
    """
    ref = schema.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        if name in seen or name not in definitions:
            return set()
        return _property_names(definitions[name], definitions, seen | {name})
    found: set[str] = set()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for field, child in properties.items():
            found.add(str(field))
            if isinstance(child, dict):
                found |= _property_names(child, definitions, seen)
    for key in ("items", "additionalProperties"):
        child = schema.get(key)
        if isinstance(child, dict):
            found |= _property_names(child, definitions, seen)
    for key in ("allOf", "anyOf", "oneOf"):
        branches = schema.get(key)
        if isinstance(branches, list):
            for branch in branches:
                if isinstance(branch, dict):
                    found |= _property_names(branch, definitions, seen)
    return found


def test_no_admin_route_returns_an_enquiry_column() -> None:
    """The administrator sees no join request: not a field, not a query.

    Two halves, because each misses what the other sees: the response walk
    catches a field named like a column on any of the fourteen routes, and
    the source scan catches an administrator query reading the table under
    an alias the walk could not recognise.
    """
    assert len(PLATFORM_ADMIN_ROUTES) == 14
    assert {"enquirer_account_id", "student_name", "message"} <= ENQUIRY_COLUMNS

    app = create_app()
    document = app.openapi()
    definitions = document["components"]["schemas"]
    walked: set[tuple[str, str]] = set()
    leaks: list[tuple[str, str, str]] = []
    for route in _api_routes(app):
        for method in sorted(route.methods or ()):
            if (method, route.path) not in PLATFORM_ADMIN_ROUTES:
                continue
            walked.add((method, route.path))
            schema = _response_schema(document, route.path, method)
            for name in _property_names(schema, definitions, frozenset()):
                if name in ENQUIRY_COLUMNS:
                    leaks.append((method, route.path, name))
    assert walked == PLATFORM_ADMIN_ROUTES
    assert leaks == []

    readers: list[str] = []
    for source in ADMIN_SOURCES:
        files = [source] if source.is_file() else sorted(source.rglob("*.py"))
        assert files, source
        for path in files:
            text = path.read_text(encoding="utf-8")
            if any(needle in text for needle in ENQUIRY_NEEDLES):
                readers.append(str(path.relative_to(ROOT)))
    assert readers == []
