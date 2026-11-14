"""No contact and no code reaches a log line, an audit row or an error body.

[U2: NFR3.4; review R-03]. Distinctive sentinel contacts are driven through
every U2 surface -- a teacher's save and its refusal, a centre invitation
and its refusal, the already-added lookup by phone and by email, a contact
replacement with its code, a removal, and the account's deletion -- with
logging captured at DEBUG. Afterwards no sentinel, and no code sent, may
appear in any captured record (message or ``extra``), in any audit row, or
in any error envelope the requests received.

Written from the requirement, after the implementation.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import OwnerMember
from tests.accounts.contact_support import PASSWORD, account, auth, centre, code_for
from tests.batches.conftest import make_teacher

STUDENT_EMAIL = "sentinel-student@example.com"
GUARDIAN_EMAIL = "sentinel-guardian@example.com"
INVITED_EMAIL = "sentinel-invited@example.com"
OWN_EMAIL = "sentinel-own@example.com"
NEW_EMAIL = "sentinel-new@example.com"
STUDENT_PHONE = "+8801711999001"
OWN_PHONE = "+8801711999002"


def test_no_sentinel_reaches_a_log_an_audit_row_or_an_error_body(
    api_client: TestClient,
    owner_session: Session,
    outbound: list[tuple[str, str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every U2 surface, one run, nothing leaks.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :param caplog: The log capture
    :return: None
    """
    caplog.set_level("DEBUG")
    errors: list[str] = []

    def call(method: str, url: str, **kwargs: object) -> object:
        """Make a request, keeping every error body it returns.

        :param method: The HTTP method
        :param url: The path
        :param kwargs: The request arguments
        :return: The response
        """
        response = api_client.request(method, url, **kwargs)  # type: ignore[arg-type]
        if response.status_code >= 400:
            errors.append(response.text)
        return response

    teacher = make_teacher(owner_session, name="Physics")
    teacher_headers = auth(api_client, owner_session, teacher.account_id)
    student = {
        "display_name": "Mitu",
        "student_phone": STUDENT_PHONE,
        "student_email": STUDENT_EMAIL,
        "guardian_email": GUARDIAN_EMAIL,
        "enrollments": [{"batch_id": str(teacher.batch_id)}],
    }
    call("POST", "/v1/students", json=student, headers=teacher_headers)
    call(
        "POST",
        "/v1/students",
        json={"display_name": "Twin", "student_email": STUDENT_EMAIL},
        headers=teacher_headers,
    )
    call(
        "POST",
        "/v1/students",
        json={"display_name": "Bad", "student_email": "sentinel-broken"},
        headers=teacher_headers,
    )

    hub = centre(owner_session)
    manager = account(owner_session)
    owner_session.add(
        OwnerMember(
            owner_id=hub,
            account_id=manager,
            invited_phone=None,
            invited_email="manager@example.com",
            display_name="Manager",
            role="manager",
            decision="accepted",
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    owner_session.commit()
    centre_headers = {
        **auth(api_client, owner_session, manager),
        "X-Workspace-Id": str(hub),
    }
    invite = {"display_name": "Nadia", "role": "teacher", "email": INVITED_EMAIL}
    call("POST", "/v1/centre/members", json=invite, headers=centre_headers)
    call("POST", "/v1/centre/members", json=invite, headers=centre_headers)

    call("GET", "/v1/accounts/already-added", params={"email": STUDENT_EMAIL})
    call("GET", "/v1/accounts/already-added", params={"phone": STUDENT_PHONE})

    holder = account(owner_session, phone=OWN_PHONE, email=OWN_EMAIL, password=PASSWORD)
    holder_headers = auth(api_client, owner_session, holder)
    call(
        "POST",
        "/v1/me/contact",
        json={"email": NEW_EMAIL, "password": PASSWORD},
        headers=holder_headers,
    )
    code = code_for(outbound, NEW_EMAIL)
    call(
        "POST",
        "/v1/me/contact/verify",
        json={"email": NEW_EMAIL, "code": "000000"},
        headers=holder_headers,
    )
    call(
        "POST",
        "/v1/me/contact/verify",
        json={"email": NEW_EMAIL, "code": code},
        headers=holder_headers,
    )
    call(
        "POST",
        "/v1/me/contact/remove",
        json={"kind": "phone", "password": PASSWORD},
        headers=holder_headers,
    )
    call("DELETE", "/v1/me", headers=auth(api_client, owner_session, holder))

    sentinels = (
        STUDENT_EMAIL,
        GUARDIAN_EMAIL,
        INVITED_EMAIL,
        OWN_EMAIL,
        NEW_EMAIL,
        STUDENT_PHONE,
        OWN_PHONE,
        "sentinel",
        code,
    )
    # The test client's own `httpx` logger prints each request URL, query
    # string included; it is the harness, not the server. The server runs
    # with `--no-access-log` (Dockerfile, [C-35]), so no request URL is
    # logged in deployment.
    server_records = [r for r in caplog.records if not r.name.startswith("httpx")]
    logged = "".join(r.getMessage() + str(vars(r)) for r in server_records)
    owner_session.expire_all()
    audit = " ".join(
        str(tuple(row))
        for row in owner_session.execute(sa.text("SELECT * FROM auth_audit_log")).all()
    )
    assert errors, "the refusals above must have produced error bodies"
    for sentinel in sentinels:
        assert sentinel not in logged, sentinel
        assert sentinel not in audit, sentinel
        assert all(sentinel not in body for body in errors), sentinel
    assert uuid.UUID(str(holder))  # the account id may appear; contacts may not
