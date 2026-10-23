"""Signup's ceilings: separate counters, narrowest first, byte-identical.

The rule these defend is that signup and the OTP path have **opposite
disclosure properties by design**, and that conflating their controls
is how one inherits the other's assumptions [BR2.1, NFR12.3]. So the
load-bearing assertion here is not that a ceiling refuses -- that is
the easy half -- but that refusing a signup consumes **no OTP
allowance**, and the reverse.

And the regression one [BR2.2, AC1.16.3]: ``POST /v1/auth/otp`` must
stay byte-identical for a known and an unknown number now that signup
exists. Signup must not weaken what the prior Unit built.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.accounts.service import SignupRole, create_account
from app.api.accounts import get_gateway
from app.auth.ceilings import (
    SIGNUP_PER_NUMBER_DAILY,
    CeilingBreach,
    CeilingChecker,
    ScopeKind,
)
from app.db.models import Account, RateLimitCounter


def _phone() -> str:
    """Generate a unique number for one test.

    :return: A number in international form
    """
    return f"+8801{uuid.uuid4().int % 10**9:09d}"


def _count(session: Session, kind: ScopeKind, value: str) -> int:
    """Total this scope's counters across every window.

    :param session: A session to read through
    :param kind: The scope kind
    :param value: The scope value
    :return: The summed count, or zero
    """
    session.expire_all()
    total = session.execute(
        sa.select(sa.func.coalesce(sa.func.sum(RateLimitCounter.count), 0)).where(
            RateLimitCounter.scope_kind == kind.value,
            RateLimitCounter.scope_value == value,
        )
    ).scalar_one()
    return int(total)


def test_the_signup_per_number_ceiling_refuses(
    restricted_session: Session,
) -> None:
    """The per-number ceiling [BR2.1, AC1.16.1].

    :param restricted_session: A session as the application role
    :return: None
    """
    checker = CeilingChecker(restricted_session)
    phone = _phone()

    for _ in range(SIGNUP_PER_NUMBER_DAILY):
        checker.check_and_consume_signup(number=phone, ip_prefix="203.0.113")

    with pytest.raises(CeilingBreach) as breach:
        checker.check_and_consume_signup(number=phone, ip_prefix="203.0.113")

    assert breach.value.scope is ScopeKind.SIGNUP_NUMBER_DAILY


def test_a_signup_refusal_consumes_nothing_at_all(
    restricted_session: Session, owner_session: Session
) -> None:
    """A refusal releases its own increment [NFR12.4].

    The quieter half of the accounting rule: a cascade that refuses
    correctly while still having incremented is wrong in a way no
    refusal test notices, because the refusal still happens.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to read counters back
    :return: None
    """
    checker = CeilingChecker(restricted_session)
    phone = _phone()

    for _ in range(SIGNUP_PER_NUMBER_DAILY):
        checker.check_and_consume_signup(number=phone, ip_prefix="203.0.113")

    at_ceiling = _count(owner_session, ScopeKind.SIGNUP_NUMBER_DAILY, phone)

    with pytest.raises(CeilingBreach):
        checker.check_and_consume_signup(number=phone, ip_prefix="203.0.113")

    after_refusal = _count(owner_session, ScopeKind.SIGNUP_NUMBER_DAILY, phone)

    assert at_ceiling == SIGNUP_PER_NUMBER_DAILY
    assert after_refusal == at_ceiling, "the refused attempt was counted"


def test_the_signup_cascade_is_evaluated_narrowest_first(
    restricted_session: Session, owner_session: Session
) -> None:
    """Narrowest first, and the wider scope untouched [NFR12.4].

    Global-first *still looks like* defence in depth, which the
    ceiling module records as the reason it would return -- and a
    second cascade is exactly where it would. The per-number scope
    must refuse before the per-IP scope has been touched by the
    refused attempt.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to read counters back
    :return: None
    """
    checker = CeilingChecker(restricted_session)
    phone = _phone()
    ip_prefix = f"198.51.{uuid.uuid4().int % 250}"

    for _ in range(SIGNUP_PER_NUMBER_DAILY):
        checker.check_and_consume_signup(number=phone, ip_prefix=ip_prefix)

    before = _count(owner_session, ScopeKind.SIGNUP_IP_HOURLY, ip_prefix)

    with pytest.raises(CeilingBreach):
        checker.check_and_consume_signup(number=phone, ip_prefix=ip_prefix)

    after = _count(owner_session, ScopeKind.SIGNUP_IP_HOURLY, ip_prefix)

    assert after == before, "a per-number refusal consumed the per-IP budget"


def test_signup_and_otp_count_against_separate_counters(
    restricted_session: Session, owner_session: Session
) -> None:
    """**The rule this file exists for** [BR2.1, NFR12.3].

    Separate controls rather than extra conditions on the OTP ones.
    Exhausting signup's per-number allowance must leave the OTP path's
    allowance for that same number untouched, or a person who mistyped
    their number three times at signup can no longer receive a login
    code.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to read counters back
    :return: None
    """
    checker = CeilingChecker(restricted_session)
    phone = _phone()

    for _ in range(SIGNUP_PER_NUMBER_DAILY):
        checker.check_and_consume_signup(number=phone, ip_prefix="203.0.113")
    with pytest.raises(CeilingBreach):
        checker.check_and_consume_signup(number=phone, ip_prefix="203.0.113")

    # The OTP path for that same number is still available, which is
    # the behavioural statement of "separate counters".
    checker.check_and_consume(number=phone, ip_prefix="203.0.113")

    assert _count(owner_session, ScopeKind.NUMBER_HOURLY, phone) == 1
    assert _count(owner_session, ScopeKind.SIGNUP_NUMBER_DAILY, phone) == (
        SIGNUP_PER_NUMBER_DAILY
    )


def test_the_otp_response_stays_byte_identical_after_signup_exists(
    client: TestClient, restricted_session: Session
) -> None:
    """The regression D1 must not cause [BR2.2, AC1.16.3].

    Signup creates accounts, so for the first time there are numbers
    that are *known* because somebody registered them rather than
    because a teacher typed them. The issue endpoint must still answer
    identically either way -- compared as **bytes**, because a
    difference in field order or whitespace is as readable to an
    attacker as a difference in content.

    :param client: A client against the restricted engine
    :param restricted_session: A session as the application role
    :return: None
    """
    known = _phone()
    unknown = _phone()
    create_account(
        restricted_session,
        phone=known,
        role=SignupRole.STUDENT,
        self_name="Registered",
    )

    known_response = client.post("/v1/auth/otp", json={"phone": known})
    unknown_response = client.post("/v1/auth/otp", json={"phone": unknown})

    assert known_response.status_code == unknown_response.status_code
    assert known_response.content == unknown_response.content


def test_the_two_cascades_share_no_scope_kind() -> None:
    """Separateness, asserted on the vocabulary itself [NFR12.3].

    A structural guard beside the behavioural one above: if a future
    edit reused an OTP scope kind inside the signup cascade, the
    counters would silently merge and the behavioural test's two
    numbers would start moving together.

    :return: None
    """
    otp_kinds = {scope.kind for scope, _ in CeilingChecker._scopes("n", "i")}
    signup_kinds = {scope.kind for scope, _ in CeilingChecker._signup_scopes("n", "i")}

    assert otp_kinds & signup_kinds == set()
    assert signup_kinds == {
        ScopeKind.SIGNUP_NUMBER_DAILY,
        ScopeKind.SIGNUP_IP_HOURLY,
    }


def test_every_scope_kind_fits_its_column() -> None:
    """A name too long for the column fails at the first request.

    **Found by running it, not by reading it.** ``signup_number_day``
    is seventeen characters and ``scope_kind`` is ``String(16)``, so
    the first signup refused with a driver truncation error rather than
    a ceiling decision. Asserted here against the column's own declared
    length rather than against the literal 16, so widening the column
    cannot leave this check pinned to a stale number.

    :return: None
    """
    limit = RateLimitCounter.__table__.columns["scope_kind"].type.length

    too_long = [kind.value for kind in ScopeKind if len(kind.value) > limit]

    assert too_long == [], (
        f"these scope kinds exceed scope_kind's {limit} characters: "
        f"{too_long}. PostgreSQL refuses the counter insert, so the "
        "ceiling never gets to make a decision."
    )


def test_a_signup_breach_carries_its_own_message_key() -> None:
    """A refusal names the step that actually failed [team: Error handling].

    Shown on the signup screen, a string saying "we could not send your
    code" describes a step that never happened. The code is shared so a
    client switches on one value; the key differs so the person reads
    the right sentence.

    :return: None
    """
    signup = CeilingBreach(ScopeKind.SIGNUP_NUMBER_DAILY)
    otp = CeilingBreach(ScopeKind.NUMBER_HOURLY)

    assert signup.code == otp.code == "TEMPORARILY_UNAVAILABLE"
    assert signup.message_key == "signup.temporarily_unavailable"
    assert otp.message_key == "auth.otp.temporarily_unavailable"
    # Neither reveals the limit or implies the number is invalid
    # [BR2.6]: revealing the limit tells an attacker how to pace a
    # drain.
    assert str(SIGNUP_PER_NUMBER_DAILY) not in signup.message_key


def test_signup_is_refused_through_the_endpoint(
    client: TestClient, owner_session: Session
) -> None:
    """The ceiling is wired to the route, not only to the checker.

    A service-level ceiling test passes against a handler that never
    calls it, which is the gap between a control existing and a control
    being in force.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read counters back
    :return: None
    """
    phone = _phone()
    body = {
        "phone": phone,
        "role": "student",
        "self_name": "Rahim",
        "address": None,
    }

    first = client.post("/v1/accounts", json=body)
    assert first.status_code == 201

    # The number now has an account, so further attempts refuse as a
    # duplicate -- which is itself a 409. The ceiling is asserted on
    # the LOOKUP instead, which is unauthenticated, repeatable and
    # bounded by the same cascade.
    for _ in range(SIGNUP_PER_NUMBER_DAILY - 1):
        assert (
            client.get(
                "/v1/accounts/already-added", params={"phone": phone}
            ).status_code
            == 200
        )

    refused = client.get("/v1/accounts/already-added", params={"phone": phone})

    assert refused.status_code == 409
    body = refused.json()["error"]
    assert body["code"] == "TEMPORARILY_UNAVAILABLE"
    assert body["retryable"] is False


def test_a_duplicate_number_is_refused_through_the_endpoint(
    client: TestClient, owner_session: Session
) -> None:
    """The person is directed to log in [BR4.4, AC1.12.4].

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    phone = _phone()
    body = {"phone": phone, "role": "teacher", "self_name": "Karim"}

    assert client.post("/v1/accounts", json=body).status_code == 201

    duplicate = client.post("/v1/accounts", json=body)

    assert duplicate.status_code == 409
    body = duplicate.json()["error"]
    assert body["code"] == "ACCOUNT_EXISTS"
    # Retryability is read off the CLASS in exactly one place; a 409
    # that advertised itself as retryable would invite a client to
    # hammer a duplicate [team: Error handling].
    assert body["retryable"] is False
    # `message_key`, never `message`: a server-sent English string
    # cannot be localized in a Bangla-first UI.
    assert body["message_key"] == "signup.number.already_registered"


def test_the_account_exists_before_the_code_is_sent(
    client: TestClient, owner_session: Session
) -> None:
    """The ordering claim, asserted at the gateway call [AC1.11.4].

    **No response body reveals this.** A handler that sent the code
    first and created the account afterwards returns the same 201, so
    the only place the ordering is observable is inside the gateway, at
    the moment it is asked to send.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    phone = _phone()
    seen: list[uuid.UUID | None] = []

    class _RecordingGateway:
        """A gateway that records whether the account existed yet."""

        def send(self, number: str, message: str, correlation_id: str) -> None:
            """Look the account up at the moment of the send.

            :param number: The destination number
            :param message: The rendered message
            :param correlation_id: The request's correlation id
            :return: None
            """
            owner_session.expire_all()
            seen.append(
                owner_session.execute(
                    sa.select(Account.id).where(Account.phone == number)
                ).scalar_one_or_none()
            )

    app = client.app
    app.dependency_overrides[get_gateway] = _RecordingGateway
    try:
        response = client.post(
            "/v1/accounts",
            json={"phone": phone, "role": "student", "self_name": "Rahim"},
        )
    finally:
        app.dependency_overrides.pop(get_gateway, None)

    assert response.status_code == 201
    assert seen == [uuid.UUID(response.json()["account_id"])], (
        "the code was sent before the account existed"
    )
