"""Adversarial probes of the hub listing routes.

A listing is the owner's own page, so the boundaries are: nobody reaches
another owner's listing, and no hub response carries a phone, a collection
number or a per-person key -- except the guardian's ``guardian_phone`` on
the owner's three join-request routes, which the guardian chose to share
[H5 contact predicate].
"""

from __future__ import annotations

import uuid
from typing import Final

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.contract.privacy import (
    PUBLIC_FORBIDDEN_FIELDS,
    _public_field,
    _response_schema,
    _walk,
)
from app.db.models import BatchSubject
from app.main import create_app
from tests.batches.conftest import make_teacher
from tests.conftest import bearer

_BATCH_FILL = {
    "slug": "class-9-maths",
    "description_en": "Weekly maths",
    "class_levels": ["class_9"],
    "mode": "in_person",
    "show_fee": True,
    "show_schedule": False,
}


def _tutor(session: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Arrange a solo tutor with a subject on their batch.

    :param session: An arranging session
    :return: ``(account_id, owner_id, batch_id)``
    """
    teacher = make_teacher(session)
    session.add(BatchSubject(batch_id=teacher.batch_id, name="Maths"))
    session.commit()
    return teacher.account_id, teacher.owner_id, teacher.batch_id


def test_teacher_a_cannot_read_or_write_teacher_b_listing(
    api_client: TestClient, owner_session: Session
) -> None:
    """Each route answers from the caller's own lens, and B's batch is a 404."""
    a_account, a_owner, _ = _tutor(owner_session)
    b_account, b_owner, b_batch = _tutor(owner_session)
    a_headers = bearer(owner_session, a_account)
    api_client.put(
        "/v1/hub/listing",
        json={"slug": "teacher-b", "headline_en": "B's headline"},
        headers=bearer(owner_session, b_account),
    )

    own = api_client.get("/v1/hub/listing", headers=a_headers)
    assert own.status_code == 200
    assert own.json()["slug"] is None
    assert own.json()["headline_en"] is None

    # Naming B's workspace is a choice among A's own, never a grant.
    forged = {**a_headers, "X-Workspace-Id": str(b_owner)}
    assert api_client.get("/v1/hub/listing", headers=forged).status_code == 403
    assert (
        api_client.put(
            "/v1/hub/listing", json={"headline_en": "hijack"}, headers=forged
        ).status_code
        == 403
    )

    base = f"/v1/batches/{b_batch}/listing"
    assert api_client.put(base, json=_BATCH_FILL, headers=a_headers).status_code == 404
    assert api_client.post(f"{base}/publish", headers=a_headers).status_code == 404
    assert api_client.post(f"{base}/unpublish", headers=a_headers).status_code == 404

    listed = api_client.get("/v1/hub/batch-listings", headers=a_headers)
    assert str(b_batch) not in {row["batch_id"] for row in listed.json()}
    assert a_owner != b_owner


#: The one contact a hub response may carry by name under the public set,
#: as exact ``(path, schema, field)`` triples [H5]. ``guardian_phone`` on a
#: join request is the guardian's own account number, shown to the people
#: who run the listing only because the guardian ticked "share" (the
#: contact predicate). None of these routes is public: each resolves the
#: owner's teacher lens, and ``tests/contract/test_enquiry_privacy.py``
#: walks them against their own forbidden set, which holds a bare
#: ``phone``.
CONSENTED: Final = frozenset(
    {
        *(
            ("/v1/hub/enquiries" + suffix, "OwnerEnquiryWire", "guardian_phone")
            for suffix in ("", "/{enquiry_id}", "/{enquiry_id}/close")
        ),
        # The owner's interest list [0049]: a family shares the number on
        # their account by sharing an interest; that is all one is.
        ("/v1/hub/interests", "OwnerInterestWire", "guardian_phone"),
    }
)


def test_no_hub_schema_carries_a_phone_or_key_beyond_consented_contact() -> None:
    """Every hub response schema is clean against the public forbidden set.

    ``public_contact_phone`` is the owner's opt-in field and is deliberately
    not in that set; every other contact or per-person key is. The one
    exception is :data:`CONSENTED`: ``guardian_phone`` on the owner's three
    join-request routes, shown only because the guardian ticked "share".
    """
    app = create_app()
    document = app.openapi()
    definitions = document["components"]["schemas"]
    checked = 0
    leaks: list[tuple[str, str, str]] = []
    for path, item in document["paths"].items():
        if not (
            path.startswith("/v1/hub/")
            or (path.startswith("/v1/batches/") and "/listing" in path)
        ):
            continue
        for method, operation in item.items():
            if "responses" not in operation:
                continue
            # A JSON body has a schema to walk. An HTML page (the owner's
            # preview) has none: it renders a registered view model, which
            # tests/contract/test_public_privacy.py walks instead.
            if not any(
                code.startswith("2") and "application/json" in body.get("content", {})
                for code, body in operation["responses"].items()
            ):
                continue
            checked += 1
            schema = _response_schema(document, path, method.upper())
            leaks += [
                (path, str(name), field)
                for name, field in _walk(schema, definitions, set(), _public_field)
            ]
    # The ten listing responses, the five JSON-bodied media routes (the
    # sixth, DELETE, is a 204 with no body to walk), the five JSON-bodied
    # review routes [H4]: the reviewable list, the author's read and write,
    # the teacher's read and reply (both deletes are 204s), and the five
    # join-request routes under /v1/hub [H5]: the target, the send, and the
    # owner's list, read and close (the guardian's own list and withdrawal
    # are under /v1/me), and three interest routes [0049]: the target, the
    # share and the owner's list (the owner's close is a 204), and the
    # owner's page-view counts [0050].
    assert checked == 29
    assert sorted(set(leaks) - CONSENTED) == []
    # The allowance names leaks that occur, so it cannot outlive them.
    assert CONSENTED <= set(leaks)
    assert "public_contact_phone" not in PUBLIC_FORBIDDEN_FIELDS
