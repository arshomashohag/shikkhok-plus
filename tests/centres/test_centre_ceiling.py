"""Opening a centre is bounded per account [L-06].

``POST /v1/centres`` had no limit, so one authenticated account could
open centres in a loop. Opening one is a deliberate, rare act, and the
allowance refuses a loop with the contentless 409 every ceiling answers.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.ceilings import CENTRES_PER_ACCOUNT_DAILY
from tests.batches.conftest import make_teacher
from tests.conftest import bearer


def test_an_account_may_open_only_so_many_centres_a_day(
    api_client: TestClient, owner_session: Session
) -> None:
    """The allowance is per account, and another account is unaffected.

    :param api_client: A client against the restricted engine
    :param owner_session: A session to arrange accounts through
    :return: None
    """
    busy = make_teacher(owner_session, name="Busy")
    other = make_teacher(owner_session, name="Other")
    body = {"name": "Udoy Coaching", "manager_name": "Karim"}

    for _ in range(CENTRES_PER_ACCOUNT_DAILY):
        opened = api_client.post(
            "/v1/centres", json=body, headers=bearer(owner_session, busy.account_id)
        )
        assert opened.status_code == 201, opened.text

    refused = api_client.post(
        "/v1/centres", json=body, headers=bearer(owner_session, busy.account_id)
    )
    elsewhere = api_client.post(
        "/v1/centres", json=body, headers=bearer(owner_session, other.account_id)
    )

    assert refused.status_code == 409
    error = refused.json()["error"]
    assert error["code"] == "TEMPORARILY_UNAVAILABLE"
    assert error["message_key"] == "centre.temporarily_unavailable"
    assert error["retryable"] is False
    assert elsewhere.status_code == 201, elsewhere.text
