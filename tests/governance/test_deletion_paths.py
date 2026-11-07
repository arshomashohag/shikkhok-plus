"""Both paths reach one implementation and produce the same result.

**The two paths are compared by their SURVIVING ROW SETS**, not against
two hand-written expectations [BR3.1]. Two independent expectations
drift independently, and the route that drifts is the external one --
used less, tested less, and the one Play requires.

The external route is **public and must stay public** [AC1.7.1, RC-4]:
Play requires deletion to work without reinstalling the app, so it
cannot take a session. What it takes instead is a code sent to the
number, verified with the same mechanism the app uses [BR3.2].
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api.deletion import CODE_SENT_NOTICE, DELETED_NOTICE, INVALID_NOTICE
from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from app.config import ENVIRONMENT_ENV
from app.contract.routes import LENS_EXEMPT_AUTHENTICATED, PUBLIC_ROUTES
from app.gateway.outbox import OUTBOX_FORCE_ENV
from app.governance.dispositions import DISPOSITIONS, Disposition
from tests.governance.conftest import PopulatedSeat, build_populated_seat

CORRELATION = "deletion-path-correlation"


@pytest.fixture
def client(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build a client whose app uses the restricted test engine.

    Restricted and not owner, like every other route-level suite here:
    an application connected as the table owner bypasses row-level
    security, so a probe through it proves nothing about the boundary.

    :param restricted_engine: The non-superuser engine
    :param monkeypatch: The patcher
    :return: A context manager yielding the client
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:test-signing-key-padded-to-thirty-two")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    # The staging outbox, which is how a test reads back a code the
    # null gateway did not text. Enabled here rather than per test
    # because every route-level deletion test needs the code.
    monkeypatch.setenv(ENVIRONMENT_ENV, "test")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")

    from app.main import create_app

    app = create_app()
    app.state.engine = restricted_engine
    with TestClient(app) as test_client:
        yield test_client


def _surviving_rows(session: Session) -> dict[str, int]:
    """Count every row in every table the manifest declares.

    Enumerated from ``DISPOSITIONS``, so a table added later is
    compared across the two paths without this file being edited.

    :param session: The session to read through
    :return: Table name to row count
    """
    return {
        table: int(
            session.execute(
                sa.text(f"SELECT count(*) FROM {table}")  # noqa: S608
            ).scalar_one()
        )
        for table in sorted(DISPOSITIONS)
        if table != "staging_sms_outbox"
    }


#: Tables a REFUSED request legitimately writes to, excluded when
#: asserting that nothing was destroyed.
#:
#: **Excluded rather than ignored, and the distinction matters.** A
#: failed verify MUST write a ``verify_attempt`` row and a
#: ``VERIFY_FAILED`` audit row -- that is the attempt ceiling and the
#: audit trail doing their jobs, and a test demanding byte-identical
#: table counts after a refusal would be asserting that those controls
#: do nothing. Neither table holds anything the deletion was asked to
#: remove, so excluding them narrows the assertion to exactly what it
#: is about: the person's data is still there.
_WRITTEN_BY_A_REFUSAL: Final = frozenset(
    {"auth_audit_log", "verify_attempt", "otp_request", "rate_limit_counter"}
)


def _undestroyed_rows(session: Session) -> dict[str, int]:
    """Count every table a refusal must leave exactly as it found it.

    :param session: The session to read through
    :return: Table name to row count
    """
    return {
        table: count
        for table, count in _surviving_rows(session).items()
        if table not in _WRITTEN_BY_A_REFUSAL
    }


def _current_code(session: Session, phone: str) -> str:
    """Read back the code issued for a number, from the outbox.

    :param session: The session to read through
    :param phone: The number a code was sent to
    :return: The six-digit code
    :raises AssertionError: No message was recorded for that number
    """
    message = session.execute(
        sa.text(
            "SELECT message FROM staging_sms_outbox WHERE phone = :phone "
            "ORDER BY recorded_at DESC LIMIT 1"
        ),
        {"phone": phone},
    ).scalar_one_or_none()
    assert message is not None, f"no staging message for {phone}"
    digits = [part for part in message.split() if part.isdigit()]
    assert digits, f"no code in {message!r}"
    return digits[0]


# ---------------------------------------------------------------------------
# The allowlists, asserted rather than assumed.
# ---------------------------------------------------------------------------


def test_the_public_route_count_is_unchanged_by_this_unit() -> None:
    """D6 lands handlers against entries that already existed [BR3.2].

    Both ``/account-deletion`` entries were allowlisted in D1 as
    "pre-declared D6 scope", precisely so the public-route allowlist is
    not edited in the same commit that adds a public route. D6 left the
    count at eight; the admin and app MFA sign-in routes later moved it to
    twelve [0028], with no deletion route among them.

    :return: None
    """
    assert len(PUBLIC_ROUTES) == 12
    assert ("GET", "/account-deletion") in PUBLIC_ROUTES
    assert ("POST", "/account-deletion") in PUBLIC_ROUTES


def test_the_in_app_route_is_authenticated_and_not_public() -> None:
    """``DELETE /v1/me`` is lens-exempt, never public.

    The separation is the control: with one combined allowlist, whoever
    first hits a failing route takes the cheapest green edit, and
    nothing then records that the route must stay authenticated.

    :return: None
    """
    assert ("DELETE", "/v1/me") in LENS_EXEMPT_AUTHENTICATED
    assert ("DELETE", "/v1/me") not in PUBLIC_ROUTES


# ---------------------------------------------------------------------------
# The external route.
# ---------------------------------------------------------------------------


def test_the_deletion_page_answers_unauthenticated(client: TestClient) -> None:
    """It must work with no app installed [AC1.7.1].

    :param client: The test client
    :return: None
    """
    response = client.get("/account-deletion")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_the_page_names_the_app_and_the_developer(client: TestClient) -> None:
    """Play requires a person to tell they are on the right page.

    Before typing their number into it, which is the whole point of
    naming them [AC1.7.2].

    :param client: The test client
    :return: None
    """
    body = client.get("/account-deletion").text

    assert "ShikkhokPlus" in body
    assert "com.shikkhokplus.app" in body
    assert "Nirmata" in body


def test_a_post_without_a_code_deletes_nothing(
    client: TestClient, owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """Without ownership proof the route must not delete [BR3.2].

    A route that deleted on a bare phone number would be a
    denial-of-service against every user of the product.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    before = _undestroyed_rows(owner_session)

    response = client.post(
        "/account-deletion", json={"phone": populated_seat.student_phone}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "requested"
    owner_session.expire_all()
    assert _undestroyed_rows(owner_session) == before


def test_a_post_with_a_wrong_code_deletes_nothing(
    client: TestClient, owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """A guessed code is refused and destroys nothing.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    client.post("/account-deletion", json={"phone": populated_seat.student_phone})
    before = _undestroyed_rows(owner_session)

    response = client.post(
        "/account-deletion",
        json={"phone": populated_seat.student_phone, "code": "000000"},
    )

    assert response.status_code >= 400
    owner_session.expire_all()
    assert _undestroyed_rows(owner_session) == before


def test_a_sign_in_code_cannot_delete_through_the_route(
    client: TestClient,
    owner_session: Session,
    populated_seat: PopulatedSeat,
) -> None:
    """The purpose filter, asserted through the HTTP surface.

    The unit test in ``tests/auth/test_otp_purpose.py`` asserts the
    same property against ``verify`` directly; this one asserts the
    route actually passes the deletion purpose rather than defaulting.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    client.post("/v1/auth/otp", json={"phone": populated_seat.student_phone})
    sign_in_code = _current_code(owner_session, populated_seat.student_phone)
    before = _undestroyed_rows(owner_session)

    response = client.post(
        "/account-deletion",
        json={
            "phone": populated_seat.student_phone,
            "code": sign_in_code,
        },
    )

    assert response.status_code >= 400, (
        "a SIGN-IN code deleted an account through the deletion route"
    )
    owner_session.expire_all()
    assert _undestroyed_rows(owner_session) == before


# ---------------------------------------------------------------------------
# THE PAGE'S OWN FORM. [PA-SEC-1]
#
# The page serves a plain `<form method="post">` with no script, so a
# browser posts it urlencoded. The route took only JSON, so every real
# use of the page was a 422 -- and the JSON tests above were green
# throughout, because none of them submitted what the page submits.
# ---------------------------------------------------------------------------

UNKNOWN_PHONE: Final = "+8801799000001"


def test_the_page_form_posts_where_the_route_listens(client: TestClient) -> None:
    """The form these tests imitate is the form the page serves.

    :param client: The test client
    :return: None
    """
    page = client.get("/account-deletion").text

    assert '<form method="post" action="/account-deletion">' in page
    assert 'name="phone"' in page
    assert 'name="code"' in page


def test_a_form_post_with_a_blank_code_sends_a_code_and_deletes_nothing(
    client: TestClient, owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """``code=`` is the first step, not a code to verify.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    phone = populated_seat.student_phone
    before = _undestroyed_rows(owner_session)

    response = client.post("/account-deletion", data={"phone": phone, "code": ""})

    assert response.status_code == 200, response.text
    assert "text/html" in response.headers["content-type"]
    assert CODE_SENT_NOTICE in response.text
    # The confirm step: the same form, the number already filled in.
    assert f'name="phone" type="tel" required value="{phone}"' in response.text
    owner_session.expire_all()
    assert _undestroyed_rows(owner_session) == before
    # A DELETION code was issued, so the next step has something to spend.
    assert _current_code(owner_session, phone).isdigit()


@pytest.mark.parametrize("blank", ["", "   ", None], ids=["empty", "spaces", "absent"])
def test_every_spelling_of_no_code_is_the_first_step(
    client: TestClient,
    owner_session: Session,
    populated_seat: PopulatedSeat,
    blank: str | None,
) -> None:
    """A whitespace code box, or none at all, also asks for a code.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :param blank: What the code box held
    :return: None
    """
    data = {"phone": populated_seat.student_phone}
    if blank is not None:
        data["code"] = blank

    response = client.post("/account-deletion", data=data)

    assert response.status_code == 200, response.text
    assert CODE_SENT_NOTICE in response.text


def test_the_code_sent_page_is_identical_for_known_and_unknown_numbers(
    client: TestClient, populated_seat: PopulatedSeat
) -> None:
    """Enumeration resistance survives the move to HTML [BR2.7].

    The only difference allowed is the number the caller typed, echoed
    back into the form; with it masked the two pages are byte-identical.

    :param client: The test client
    :param populated_seat: The fixture
    :return: None
    """
    known_phone = populated_seat.student_phone
    known = client.post("/account-deletion", data={"phone": known_phone, "code": ""})
    unknown = client.post(
        "/account-deletion", data={"phone": UNKNOWN_PHONE, "code": ""}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.headers["content-type"] == unknown.headers["content-type"]
    assert known.text.replace(known_phone, "N") == unknown.text.replace(
        UNKNOWN_PHONE, "N"
    )


def test_a_form_post_with_a_wrong_code_deletes_nothing_and_says_so(
    client: TestClient, owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """A wrong code re-renders the form with what went wrong.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    phone = populated_seat.student_phone
    client.post("/account-deletion", data={"phone": phone, "code": ""})
    real = _current_code(owner_session, phone)
    wrong = "000000" if real != "000000" else "111111"
    before = _undestroyed_rows(owner_session)

    response = client.post("/account-deletion", data={"phone": phone, "code": wrong})

    assert response.status_code == 400
    assert "text/html" in response.headers["content-type"]
    assert "That code isn&#x27;t right. 4 tries left." in response.text
    assert f'value="{phone}"' in response.text
    owner_session.expire_all()
    assert _undestroyed_rows(owner_session) == before


def test_a_form_post_with_an_invalid_number_is_a_page_not_json(
    client: TestClient, owner_session: Session
) -> None:
    """A malformed number is answered in the page, and nothing is issued.

    Echoed back escaped, so the page cannot be made to carry markup.

    :param client: The test client
    :param owner_session: A session able to read everything
    :return: None
    """
    response = client.post(
        "/account-deletion", data={"phone": "<b>not a number</b>", "code": ""}
    )

    assert response.status_code == 422
    assert "text/html" in response.headers["content-type"]
    assert INVALID_NOTICE in response.text
    assert "<b>not a number</b>" not in response.text
    assert "&lt;b&gt;not a number&lt;/b&gt;" in response.text
    owner_session.expire_all()
    assert (
        owner_session.execute(sa.text("SELECT count(*) FROM otp_request")).scalar_one()
        == 0
    )


def test_a_json_body_with_a_bad_field_is_still_a_422(client: TestClient) -> None:
    """The JSON contract is unchanged by the form path.

    :param client: The test client
    :return: None
    """
    response = client.post(
        "/account-deletion", json={"phone": "+8801711111111", "code": "12"}
    )

    assert response.status_code == 422
    # The error envelope now carries request-validation failures too,
    # naming the field and echoing no input [audit C-17].
    error = response.json()["error"]
    assert error["code"] == "REQUEST_INVALID"
    assert error["details"]["fields"] == "body.code"


# ---------------------------------------------------------------------------
# THE COMPARISON. [BR3.1]
#
# Not two hand-written expectations: the surviving row sets of the two
# paths, against identical fixtures, compared with each other.
# ---------------------------------------------------------------------------


def _delete_externally(
    client: TestClient, session: Session, phone: str, *, form: bool = False
) -> None:
    """Drive the external route end to end, as JSON or as the page's form.

    The form variant submits exactly what a browser does with the page:
    urlencoded, with an EMPTY code box on the first step.

    :param client: The test client
    :param session: A session able to read the outbox
    :param phone: The number to delete
    :param form: Submit as the HTML form rather than as JSON
    :return: None
    """
    if form:
        sent = client.post("/account-deletion", data={"phone": phone, "code": ""})
        assert sent.status_code == 200, sent.text
        code = _current_code(session, phone)
        response = client.post("/account-deletion", data={"phone": phone, "code": code})
        assert response.status_code == 200, response.text
        assert "text/html" in response.headers["content-type"]
        assert DELETED_NOTICE in response.text
        return
    client.post("/account-deletion", json={"phone": phone})
    code = _current_code(session, phone)
    response = client.post("/account-deletion", json={"phone": phone, "code": code})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "deleted"


def _delete_in_app(client: TestClient, session: Session, account_id: uuid.UUID) -> None:
    """Drive the in-app route.

    :param client: The test client
    :param session: A session able to issue a token pair
    :param account_id: The account deleting itself
    :return: None
    """
    pair = issue_pair(session, account_id, CORRELATION)
    session.commit()
    response = client.request(
        "DELETE",
        "/v1/me",
        headers={"Authorization": f"Bearer {pair.access_token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "deleted"


def _seat_shape(session: Session, seat: PopulatedSeat) -> dict[str, object]:
    """Describe what survives of ONE seat, independently of the other.

    A whole-table count cannot compare two seats that coexist, so this
    reads the seat's own rows: the enrollment's two links, and the
    presence of each row that hangs off it.

    :param session: The session to read through
    :param seat: The seat to describe
    :return: A comparable description of what remains
    """
    enrollment = session.execute(
        sa.text(
            "SELECT student_account_id, guardian_account_id, display_name "
            "FROM enrollment WHERE id = :id"
        ),
        {"id": seat.enrollment_id},
    ).one_or_none()

    shape: dict[str, object] = {
        "enrollment_exists": enrollment is not None,
        "student_link_cleared": (
            enrollment is not None and enrollment.student_account_id is None
        ),
        "guardian_link": (
            enrollment is not None and enrollment.guardian_account_id is not None
        ),
        "display_name": enrollment.display_name if enrollment else None,
        "account_exists": bool(
            session.execute(
                sa.text("SELECT count(*) FROM account WHERE id = :id"),
                {"id": seat.student_account_id},
            ).scalar_one()
        ),
        "profile_rows": int(
            session.execute(
                sa.text("SELECT count(*) FROM profile WHERE account_id = :id"),
                {"id": seat.student_account_id},
            ).scalar_one()
        ),
        "token_rows": int(
            session.execute(
                sa.text("SELECT count(*) FROM refresh_token WHERE account_id = :id"),
                {"id": seat.student_account_id},
            ).scalar_one()
        ),
        # **The PHONE-scoped table, and it is what makes this
        # comparison discriminate.** Everything above is reached by a
        # constraint, so a path that deleted only the account row would
        # produce an identical shape for all of it and the comparison
        # would pass against two different implementations. Nothing
        # cascades to `otp_request`: it is keyed on the number, and a
        # path that does not clear it leaves a phone number sitting
        # beside a code hash.
        "otp_rows": int(
            session.execute(
                sa.text("SELECT count(*) FROM otp_request WHERE phone = :phone"),
                {"phone": seat.student_phone},
            ).scalar_one()
        ),
    }

    for table in ("attendance", "mark", "fee_cycle", "ledger_entry"):
        shape[table] = int(
            session.execute(
                sa.text(
                    f"SELECT count(*) FROM {table} "  # noqa: S608
                    "WHERE enrollment_id = :id"
                ),
                {"id": seat.enrollment_id},
            ).scalar_one()
        )

    claim = session.execute(
        sa.text(
            "SELECT submitted_by_account_id, transaction_id "
            "FROM payment_claim WHERE enrollment_id = :id"
        ),
        {"id": seat.enrollment_id},
    ).one_or_none()
    shape["claim_exists"] = claim is not None
    shape["claim_link_cleared"] = (
        claim is not None and claim.submitted_by_account_id is None
    )
    shape["claim_transaction_id"] = claim.transaction_id if claim is not None else None
    return shape


def _seed_otp_row(session: Session, phone: str) -> None:
    """Put one ``otp_request`` row on a number.

    :param session: An arranging session
    :param phone: The number to key it on
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO otp_request "
            "(id, phone, otp_hash, purpose, issued_at, expires_at) "
            "VALUES (:id, :phone, :hash, 'otp', now(), now())"
        ),
        {"id": uuid.uuid4(), "phone": phone, "hash": "y" * 64},
    )
    session.commit()


@pytest.mark.parametrize("form", [False, True], ids=["json", "html-form"])
def test_both_paths_leave_the_same_rows_behind(
    client: TestClient,
    owner_session: Session,
    populated_seat: PopulatedSeat,
    form: bool,
) -> None:
    """One deletion function, two callers, identical outcome [BR3.1].

    **Two identically shaped seats**, one deleted by each path, and the
    two surviving shapes compared WITH EACH OTHER rather than each
    against a hand-written expectation. Two independent expectations
    drift independently, and the route that drifts is the external one.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The first seat
    :return: None
    """
    second = build_populated_seat(owner_session)

    # **Both seats get a phone-scoped row before either is deleted.**
    # Without this the `otp_rows` field is zero on both sides whatever
    # either path does, and the one field that discriminates between
    # "called the deletion function" and "deleted the account row and
    # let the constraints do the rest" asserts nothing. The external
    # path would acquire one anyway by issuing its code; the in-app
    # path never would, which is exactly the asymmetry to remove.
    for seat in (populated_seat, second):
        _seed_otp_row(owner_session, seat.student_phone)
    assert _seat_shape(owner_session, populated_seat)["otp_rows"] == 1

    _delete_in_app(client, owner_session, populated_seat.student_account_id)
    owner_session.expire_all()
    in_app = _seat_shape(owner_session, populated_seat)

    # Parametrized over both encodings [PA-SEC-1]: the page's real form
    # is what Play's reviewer and a person without the app will use, and
    # it posts urlencoded -- which the route used to answer with a 422.
    _delete_externally(client, owner_session, second.student_phone, form=form)
    owner_session.expire_all()
    external = _seat_shape(owner_session, second)

    assert external == in_app, (
        "the two deletion paths left different rows behind, so they are "
        "not reaching one implementation [BR3.1]. The external route is "
        f"the one that drifts. In-app: {in_app}. External: {external}."
    )

    # Asserted on the SHARED result, so the comparison above cannot be
    # satisfied by two equally broken paths that both deleted nothing.
    assert in_app["account_exists"] is False
    assert in_app["enrollment_exists"] is True
    assert in_app["student_link_cleared"] is True
    assert in_app["attendance"] == 1
    assert in_app["mark"] == 1


def test_the_in_app_path_deletes_a_teacher_too(
    client: TestClient, owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """A teacher's in-app deletion goes through and keeps the batch.

    The same function as the external route, so the batch outcome is
    asserted on this path too rather than assumed.

    :param client: The test client
    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    pair = issue_pair(owner_session, populated_seat.teacher_account_id, CORRELATION)
    owner_session.commit()

    response = client.request(
        "DELETE",
        "/v1/me",
        headers={"Authorization": f"Bearer {pair.access_token}"},
    )

    assert response.status_code == 200, response.text
    owner_session.expire_all()
    accounts, batches = owner_session.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM account WHERE id = :id), "
            "(SELECT count(*) FROM batch WHERE id = :batch)"
        ),
        {"id": populated_seat.teacher_account_id, "batch": populated_seat.batch_id},
    ).one()
    assert (accounts, batches) == (0, 1)


def test_the_in_app_route_requires_a_token(client: TestClient) -> None:
    """Unauthenticated, it is refused rather than public.

    :param client: The test client
    :return: None
    """
    assert client.request("DELETE", "/v1/me").status_code == 401


def test_the_retained_tables_are_non_empty_before_the_comparison(
    owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """The comparison is only meaningful over a populated schema.

    A row-set comparison between two deletions of an empty database is
    trivially equal, which would make the BR3.1 assertion above pass
    against two completely different implementations.

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    counts = _surviving_rows(owner_session)
    retained = {
        table
        for table, governance in DISPOSITIONS.items()
        if governance.disposition is Disposition.RETAIN_WITH_BASIS and counts.get(table)
    }
    assert len(retained) >= 7, sorted(retained)
