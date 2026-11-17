"""Adversarial probes of the hub listing routes.

A listing is the owner's own page, so the boundaries are: nobody reaches
another owner's listing, and no hub response carries a phone, a collection
number or a per-person key.
"""

from __future__ import annotations

import uuid

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


def test_no_hub_schema_contains_collection_number_or_phone() -> None:
    """Every hub response schema is clean against the public forbidden set.

    ``public_contact_phone`` is the owner's opt-in field and is deliberately
    not in that set; every other contact or per-person key is.
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
    assert checked == 10
    assert leaks == []
    assert "public_contact_phone" not in PUBLIC_FORBIDDEN_FIELDS
