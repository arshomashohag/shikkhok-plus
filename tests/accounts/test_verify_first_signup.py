"""Verify-first signup: no account, and no answer, until the code is typed.

Signup used to create the account, profile, owner and centre on
``POST /v1/accounts`` and answer an existing number with a 409 (audit
C-07). That made the route an oracle for which phone numbers have
accounts -- the thing the sign-in path was built never to be -- and let
anyone squat a stranger's number with a name, an address and a role the
real owner then inherited, together with every seat a teacher had
recorded against the number.

Every test here is an authorization answer and was written before the
implementation: who gets an account, with whose details, and what an
unauthenticated caller can learn. The clients' flow -- submit the form,
then type the code at ``POST /v1/auth/verify`` -- is unchanged, and the
last tests assert that it still works end to end.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.ceilings import ScopeKind
from app.db.models import Account, Owner, Profile
from tests.accounts.signup_support import sign_up, submit_signup


def _phone() -> str:
    """Generate a unique number for one test.

    :return: A number in international form
    """
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


def _body(phone: str, **changes: Any) -> dict[str, Any]:
    """Build a complete signup body.

    :param phone: The number to sign up
    :param changes: Fields to override
    :return: The body
    """
    return {
        "phone": phone,
        "role": "teacher",
        "self_name": "Karim Teacher",
        "address_house": "House 12",
        "address_road": "Road 5",
        "address_city": "Dhaka",
        "address_postcode": "1205",
        **changes,
    }


def _account_id(session: Session, phone: str) -> uuid.UUID | None:
    """Return the account for a number, if one exists.

    :param session: A session able to read fixture data
    :param phone: The number
    :return: The account id, or None
    """
    session.expire_all()
    found: uuid.UUID | None = session.execute(
        sa.select(Account.id).where(Account.phone == phone)
    ).scalar_one_or_none()
    return found


def _existing(session: Session) -> tuple[str, uuid.UUID]:
    """Create an account on a fresh number, the way a fixture would.

    :param session: An arranging session
    :return: The number and its account id
    """
    phone = _phone()
    record = Account(phone=phone, created_at=dt.datetime.now(tz=dt.UTC))
    session.add(record)
    session.commit()
    return phone, record.id


def test_submitting_the_form_creates_no_account(
    client: TestClient, owner_session: Session
) -> None:
    """Nothing exists until the number is proved [C-07].

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    phone = _phone()

    response, code = submit_signup(client, _body(phone))

    assert response.status_code == 201, response.text
    assert code is not None
    assert _account_id(owner_session, phone) is None


def test_an_existing_number_gets_the_same_answer_as_a_new_one(
    client: TestClient, owner_session: Session
) -> None:
    """No 409, no difference in status or shape: not an oracle [C-07].

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :return: None
    """
    existing, _ = _existing(owner_session)
    fresh = _phone()

    known, _ = submit_signup(client, _body(existing))
    unknown, _ = submit_signup(client, _body(fresh))

    assert known.status_code == unknown.status_code == 201
    assert set(known.json()) == set(unknown.json()) == {"account_id", "code_sent_to"}
    assert len(known.content) == len(unknown.content)
    assert known.headers.get("content-length") == unknown.headers.get("content-length")


def test_the_reported_id_is_fresh_on_every_request(
    client: TestClient, owner_session: Session
) -> None:
    """A stable id for one kind of number would be the oracle again.

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :return: None
    """
    existing, account_id = _existing(owner_session)
    fresh = _phone()

    ids = {
        submit_signup(client, _body(phone))[0].json()["account_id"]
        for phone in (existing, existing, fresh, fresh)
    }

    assert len(ids) == 4
    assert str(account_id) not in ids


def test_verifying_the_code_creates_the_account_from_the_form(
    client: TestClient, owner_session: Session
) -> None:
    """The account, its profile and its owner row appear at verify.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    phone = _phone()

    account_id = sign_up(client, _body(phone, self_name="Rina Akter"))

    assert _account_id(owner_session, phone) == account_id
    profile = owner_session.get(Profile, account_id)
    assert profile is not None
    assert profile.self_name == "Rina Akter"
    assert profile.address_postcode == "1205"
    owners = owner_session.execute(
        sa.select(sa.func.count(Owner.id)).where(Owner.account_id == account_id)
    ).scalar_one()
    assert owners == 1
    events = owner_session.execute(
        sa.text("SELECT event FROM auth_audit_log WHERE account_id = :id"),
        {"id": account_id},
    ).scalars()
    assert "ACCOUNT_CREATED" in set(events)
    drafts = owner_session.execute(
        sa.text("SELECT count(*) FROM pending_signup WHERE phone = :phone"),
        {"phone": phone},
    ).scalar_one()
    assert drafts == 0


def test_a_wrong_code_creates_nothing(
    client: TestClient, owner_session: Session
) -> None:
    """Typing anything but the code sent leaves no account.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    phone = _phone()
    response, code = submit_signup(client, _body(phone))
    wrong = "000000" if code != "000000" else "111111"

    refused = client.post("/v1/auth/verify", json={"phone": phone, "code": wrong})

    assert response.status_code == 201
    assert refused.status_code == 400
    assert _account_id(owner_session, phone) is None


def test_an_existing_number_signs_in_and_keeps_its_own_profile(
    client: TestClient, owner_session: Session
) -> None:
    """A stranger's form never overwrites the owner's account [C-07].

    The code goes to the owner's phone; typing it signs the owner in to
    the account they already had, with nothing from the form applied,
    and the form is discarded.

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :return: None
    """
    phone, account_id = _existing(owner_session)

    response, code = submit_signup(client, _body(phone, self_name="Squatter"))
    verified = client.post("/v1/auth/verify", json={"phone": phone, "code": code})

    assert response.status_code == 201
    assert verified.status_code == 200
    assert owner_session.get(Profile, account_id) is None
    owner_session.expire_all()
    owners = owner_session.execute(
        sa.select(sa.func.count(Owner.id)).where(Owner.account_id == account_id)
    ).scalar_one()
    assert owners == 0
    drafts = owner_session.execute(
        sa.text("SELECT count(*) FROM pending_signup WHERE phone = :phone"),
        {"phone": phone},
    ).scalar_one()
    assert drafts == 0


def test_a_later_form_replaces_an_earlier_one(
    client: TestClient, owner_session: Session
) -> None:
    """A squatter's draft is not what the owner ends up with [C-07].

    The squatter submits first; the owner submits their own form, gets a
    code, and the account is created from the owner's form. The
    squatter's code -- also sent to the owner's phone -- no longer
    verifies, because the later code shadows it.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    phone = _phone()
    _, squatter_code = submit_signup(client, _body(phone, self_name="Squatter"))

    account_id = sign_up(client, _body(phone, self_name="Real Owner"))

    profile = owner_session.get(Profile, account_id)
    assert profile is not None
    assert profile.self_name == "Real Owner"
    assert squatter_code is not None


def test_the_code_sent_again_completes_the_signup(
    client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sending the code again after signup still creates the account.

    Both clients send the person to the code screen after signup, and
    its resend calls ``POST /v1/auth/otp``, which texts only numbers it
    can verify. A number with a draft is one of them.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :param monkeypatch: The patcher
    :return: None
    """
    phone = _phone()
    submit_signup(client, _body(phone))
    monkeypatch.setattr("app.auth.otp.generate_code", lambda: "135790")

    resent = client.post("/v1/auth/otp", json={"phone": phone})
    verified = client.post("/v1/auth/verify", json={"phone": phone, "code": "135790"})

    assert resent.status_code == 200
    assert verified.status_code == 200, verified.text
    assert _account_id(owner_session, phone) is not None


def test_a_failure_creating_the_account_leaves_the_code_unspent(
    client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Creating the account and spending the code are one transaction.

    The old route committed the account and then issued the code in a
    second transaction, so a failure between them left an account with
    no way in. Now the account is created inside the verify, and a
    failure there leaves neither the account nor a spent code.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :param monkeypatch: The patcher
    :return: None
    """
    phone = _phone()
    _, code = submit_signup(client, _body(phone))

    def _explode(*args: object, **kwargs: object) -> None:
        """Fail where the profile row would have been built.

        :param args: Unused
        :param kwargs: Unused
        :return: Never returns
        :raises RuntimeError: Always
        """
        raise RuntimeError("injected failure at the profile write")

    with monkeypatch.context() as patch:
        patch.setattr("app.accounts.service.Profile", _explode)
        with pytest.raises(RuntimeError):
            client.post("/v1/auth/verify", json={"phone": phone, "code": code})

    assert _account_id(owner_session, phone) is None
    retried = client.post("/v1/auth/verify", json={"phone": phone, "code": code})
    assert retried.status_code == 200, retried.text
    assert _account_id(owner_session, phone) is not None


def test_signup_spends_its_own_budget_for_any_number(
    client: TestClient, owner_session: Session
) -> None:
    """Signup never spends sign-in's budget, new number or not [C-05].

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :return: None
    """
    existing, _ = _existing(owner_session)
    submit_signup(client, _body(existing))
    submit_signup(client, _body(_phone()))

    owner_session.expire_all()
    spent = dict(
        owner_session.execute(
            sa.text(
                "SELECT scope_kind, sum(count) FROM rate_limit_counter "
                "WHERE scope_value = 'global' GROUP BY scope_kind"
            )
        ).all()
    )
    assert spent == {ScopeKind.SIGNUP_GLOBAL_DAILY.value: 2}


def test_a_coaching_signup_opens_its_centre_only_at_verify(
    client: TestClient, owner_session: Session
) -> None:
    """The centre is created with the account, not with the form.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    phone = _phone()
    body = _body(phone, role="coaching", centre_name="Udoy Coaching")

    response, code = submit_signup(client, body)
    owner_session.expire_all()
    before = owner_session.execute(
        sa.text("SELECT count(*) FROM owner WHERE name = 'Udoy Coaching'")
    ).scalar_one()
    client.post("/v1/auth/verify", json={"phone": phone, "code": code})
    owner_session.expire_all()
    after = owner_session.execute(
        sa.text("SELECT count(*) FROM owner WHERE name = 'Udoy Coaching'")
    ).scalar_one()

    assert response.status_code == 201
    assert before == 0
    assert after == 1
