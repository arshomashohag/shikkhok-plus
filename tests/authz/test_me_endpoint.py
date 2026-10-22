"""`GET /v1/me` — every lens the account has, in one statement.

**The screen this serves.** Signing in no longer assumes "you are a
teacher": the app asks what this account can be, shows a picker when
there is a choice, and fetches a lens's data only once it is chosen.

**The cost property is the requirement, not a nice-to-have.** These
tests assert it directly, because the plausible implementation —
resolving lenses, then counting each one's rows in its own query — is
invisible in any correctness test and makes the account with the most
lenses the most expensive. That account is a teacher who is also a
parent, which is the one this endpoint exists for.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from app.money import Money
from tests.batches.conftest import _account, enroll, make_teacher
from tests.batches.test_query_count import QueryCounter


@pytest.fixture
def client(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build a client whose app uses the restricted test engine.

    :param restricted_engine: The non-superuser engine
    :param monkeypatch: The patcher
    :return: A context manager yielding the client
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:test-signing-key-padded-to-thirty-two")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")

    from app.main import create_app

    app = create_app()
    app.state.engine = restricted_engine
    with TestClient(app) as test_client:
        yield test_client


def _auth(session: Session, account_id: uuid.UUID) -> dict[str, str]:
    """Build an Authorization header for an account.

    :param session: The session to write the token family through
    :param account_id: The account to authenticate as
    :return: The header mapping
    """
    pair = issue_pair(session, account_id=account_id, correlation_id=uuid.uuid4())
    return {"Authorization": f"Bearer {pair.access_token}"}


def _teacher_with(session: Session, *, batches: int) -> uuid.UUID:
    """Build an account owning a given number of batches.

    :param session: A session able to arrange fixture data
    :param batches: How many batches it should own
    :return: The account id
    """
    from app.db.models import Batch, Owner

    account_id = _account(session)
    owner = Owner(account_id=account_id, created_at=dt.datetime.now(tz=dt.UTC))
    session.add(owner)
    session.commit()
    for index in range(batches):
        session.add(
            Batch(
                owner_id=owner.id,
                name=f"Batch {index}",
                default_fee=Money("1500.00"),
                fee_due_day=10,
                marksheet_visible=True,
                active=True,
                created_at=dt.datetime.now(tz=dt.UTC),
            )
        )
    session.commit()
    return account_id


def test_an_account_with_no_lenses_gets_an_empty_list(
    client: TestClient, owner_session: Session
) -> None:
    """A signed-in account with nothing attached lists no lenses.

    Not an error: the account is real and signed in, it simply has no
    place in anyone's class yet. The app shows an explanation, not a
    failure.

    :param client: The test client
    :param owner_session: A session to mint a token through
    :return: None
    """
    account_id = _account(owner_session)

    response = client.get("/v1/me", headers=_auth(owner_session, account_id))

    assert response.status_code == 200
    assert response.json()["lenses"] == []


def test_a_teacher_sees_one_lens_with_a_batch_count(
    client: TestClient, owner_session: Session
) -> None:
    """A teacher's lens carries how many batches they own.

    The count is what lets the app skip the picker for a single-lens
    account and still label the entry usefully.

    :param client: The test client
    :param owner_session: A session to mint a token through
    :return: None
    """
    account_id = _teacher_with(owner_session, batches=3)

    body = client.get("/v1/me", headers=_auth(owner_session, account_id)).json()

    assert body["lenses"] == [{"kind": "teacher", "count": 3}]


def test_all_three_lenses_come_back_for_one_account(
    client: TestClient, owner_session: Session
) -> None:
    """Teacher, student and guardian together, each with its count.

    This is the `FR1.4` account the endpoint exists for.

    :param client: The test client
    :param owner_session: A session to mint a token through
    :return: None
    """
    account_id = _teacher_with(owner_session, batches=2)

    studies_in = make_teacher(owner_session, name="Where they study")
    enroll(
        owner_session,
        batch_id=studies_in.batch_id,
        display_name="Themselves",
        student_account_id=account_id,
    )

    childs = make_teacher(owner_session, name="Their child's class")
    enroll(
        owner_session,
        batch_id=childs.batch_id,
        display_name="Their child",
        student_account_id=_account(owner_session),
        guardian_account_id=account_id,
    )

    body = client.get("/v1/me", headers=_auth(owner_session, account_id)).json()

    by_kind = {lens["kind"]: lens["count"] for lens in body["lenses"]}
    assert by_kind == {"teacher": 2, "student": 1, "guardian": 1}


def test_the_summary_is_one_statement(
    restricted_session: Session, owner_session: Session
) -> None:
    """Every lens and every count resolve in ONE statement.

    **The cost requirement, asserted as a literal count.** The
    plausible alternative — resolve the lenses, then count each one's
    rows separately — passes every test above while costing four
    statements for the account this endpoint serves, and the
    regression would be invisible.

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from app.authz.summary import lens_summary

    account_id = _teacher_with(owner_session, batches=2)
    other = make_teacher(owner_session, name="Elsewhere")
    enroll(
        owner_session,
        batch_id=other.batch_id,
        display_name="Themselves",
        student_account_id=account_id,
    )

    counter = QueryCounter()
    engine: Engine = restricted_session.get_bind()
    sa.event.listen(engine, "before_cursor_execute", counter)
    try:
        before = counter.count
        lens_summary(restricted_session, account_id)
        issued = counter.count - before
    finally:
        sa.event.remove(engine, "before_cursor_execute", counter)

    assert issued == 1, (
        f"the summary took {issued} statements, not 1 — a per-lens "
        "count makes the multi-lens account the expensive one"
    )


def test_the_statement_count_does_not_grow_with_the_data(
    restricted_session: Session, owner_session: Session
) -> None:
    """A teacher with 12 batches costs the same statements as one with 2.

    The property the user asked for in these words: the read must not
    grow proportionally with the data. Statement count is the half
    that can be asserted deterministically; the index-only plan behind
    it is what keeps each statement flat, and that was measured
    separately at 50k accounts and 200k enrollments.

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from app.authz.summary import lens_summary

    small = _teacher_with(owner_session, batches=2)
    large = _teacher_with(owner_session, batches=12)

    counter = QueryCounter()
    engine: Engine = restricted_session.get_bind()
    sa.event.listen(engine, "before_cursor_execute", counter)
    try:
        before = counter.count
        lens_summary(restricted_session, small)
        cost_small = counter.count - before

        before = counter.count
        summary_large = lens_summary(restricted_session, large)
        cost_large = counter.count - before
    finally:
        sa.event.remove(engine, "before_cursor_execute", counter)

    assert cost_small == cost_large
    # And the count is right, so the test is not passing on an empty read.
    assert summary_large.teacher_batches == 12


def test_the_endpoint_needs_authentication(client: TestClient) -> None:
    """An unauthenticated caller is refused.

    `/v1/me` names the account's whole shape, so it is not public —
    and the route-enumeration test's PUBLIC_ROUTES allowlist must not
    gain it.

    :param client: The test client
    :return: None
    """
    assert client.get("/v1/me").status_code == 401
