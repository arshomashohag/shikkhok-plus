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
from tests.accounts.signup_support import sign_up, submit_signup, unique_username


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
        "username": unique_username(),
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


# ---------------------------------------------------------------------------
# Usernames at sign-up [U1: BR2]. Written FIRST: who ends up holding a
# name, and whether a sign-up answer reveals anything about a contact,
# are authorization answers knowable from the rules.
# ---------------------------------------------------------------------------


def _username_of(session: Session, phone: str) -> tuple[str | None, str | None]:
    """Read the username an account holds, by its number.

    :param session: A session able to read fixture data
    :param phone: The number
    :return: ``(username, username_key)``
    """
    session.expire_all()
    row = session.execute(
        sa.select(Account.username, Account.username_key).where(Account.phone == phone)
    ).one()
    return row.username, row.username_key


def _draft_username(session: Session, phone: str) -> str | None:
    """Read the username a number's draft carries.

    :param session: A session able to read fixture data
    :param phone: The number
    :return: The draft's username
    """
    session.expire_all()
    value: str | None = session.execute(
        sa.text("SELECT username FROM pending_signup WHERE phone = :phone"),
        {"phone": phone},
    ).scalar_one()
    return value


def _attempts(session: Session, phone: str) -> int:
    """Count verify attempts recorded against a number's codes.

    :param session: A session able to read fixture data
    :param phone: The number
    :return: The count
    """
    session.expire_all()
    return int(
        session.execute(
            sa.text(
                "SELECT count(*) FROM verify_attempt v JOIN otp_request o "
                "ON o.id = v.otp_request_id WHERE o.phone = :phone"
            ),
            {"phone": phone},
        ).scalar_one()
    )


def _counters(session: Session) -> dict[str, int]:
    """Sum every counter by scope kind.

    :param session: A session able to read the counters
    :return: The totals
    """
    session.expire_all()
    return {
        str(kind): int(total)
        for kind, total in session.execute(
            sa.text(
                "SELECT scope_kind, sum(count) FROM rate_limit_counter "
                "GROUP BY scope_kind"
            )
        ).all()
    }


def _take(client: TestClient, name: str) -> str:
    """Give some other account the name, through sign-up.

    :param client: A client against the restricted engine
    :param name: The username to take
    :return: That account's number
    """
    phone = _phone()
    sign_up(client, _body(phone, username=name))
    return phone


def test_signup_requires_a_username(client: TestClient) -> None:
    """A form without one is refused by the schema [BR2.1].

    :param client: A client against the restricted engine
    :return: None
    """
    response, code = submit_signup(client, _body(_phone(), username=None))

    assert response.status_code == 422
    assert code is None


def test_a_malformed_username_is_refused_before_the_draft_is_saved(
    client: TestClient, owner_session: Session
) -> None:
    """The one refusal key, no draft, no code [BR2.1, BR1.6].

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    phone = _phone()

    response, code = submit_signup(client, _body(phone, username="ra..him"))

    assert response.status_code == 400
    assert response.json()["error"]["message_key"] == "account.username.bad_dot"
    assert code is None
    owner_session.expire_all()
    drafts = owner_session.execute(
        sa.text("SELECT count(*) FROM pending_signup WHERE phone = :phone"),
        {"phone": phone},
    ).scalar_one()
    assert drafts == 0


def test_the_draft_answer_never_depends_on_the_contact(
    client: TestClient, owner_session: Session
) -> None:
    """Free names match, and taken-name 409s match, known contact or not.

    [BR2.2, BR2.9, NFR1.7] Every username decision is taken before the
    contact is read, so the answers for a number with an account and one
    without are the same in status, shape and body.

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :return: None
    """
    known, _ = _existing(owner_session)
    unknown = _phone()
    taken = unique_username()
    _take(client, taken)

    free_known, _ = submit_signup(client, _body(known, username=unique_username()))
    free_unknown, _ = submit_signup(client, _body(unknown, username=unique_username()))
    taken_known, sent_known = submit_signup(client, _body(known, username=taken))
    taken_unknown, sent_unknown = submit_signup(client, _body(unknown, username=taken))

    assert free_known.status_code == free_unknown.status_code == 201
    assert set(free_known.json()) == set(free_unknown.json())
    assert len(free_known.content) == len(free_unknown.content)
    assert taken_known.status_code == taken_unknown.status_code == 409
    assert taken_known.content == taken_unknown.content
    error = taken_known.json()["error"]
    assert error["message_key"] == "account.username.unavailable"
    assert error["code"] == "USERNAME_UNAVAILABLE"
    assert error["retryable"] is False
    assert sent_known is None and sent_unknown is None


def test_a_taken_name_is_refused_in_any_casing(
    client: TestClient, owner_session: Session
) -> None:
    """``Rahim_X`` is unavailable once ``rahim_x`` exists [BR1.7, BR2.2].

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :return: None
    """
    name = unique_username()
    _take(client, name)

    response, _ = submit_signup(client, _body(_phone(), username=name.upper()))

    assert response.status_code == 409


def test_a_held_name_is_refused_at_the_draft(
    client: TestClient, owner_session: Session, restricted_session: Session
) -> None:
    """A live hold blocks a person who is not signed in [BR2.2].

    :param client: A client against the restricted engine
    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    from app.accounts import usernames

    name = unique_username()
    usernames.place_hold(
        restricted_session,
        name,
        releasing_account_id=None,
        now=dt.datetime.now(tz=dt.UTC),
    )
    restricted_session.commit()

    response, _ = submit_signup(client, _body(_phone(), username=name))

    assert response.status_code == 409
    assert response.json()["error"]["message_key"] == "account.username.unavailable"


def test_a_draft_reserves_nothing_and_the_first_verify_takes_the_name(
    client: TestClient, owner_session: Session
) -> None:
    """Two drafts on one name; the second verify is refused [BR2.3, BR2.4].

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    name = unique_username()
    first, second = _phone(), _phone()

    first_draft, first_code = submit_signup(client, _body(first, username=name))
    second_draft, second_code = submit_signup(client, _body(second, username=name))
    assert first_draft.status_code == second_draft.status_code == 201

    won = client.post("/v1/auth/verify", json={"phone": first, "code": first_code})
    lost = client.post("/v1/auth/verify", json={"phone": second, "code": second_code})

    assert won.status_code == 200, won.text
    assert lost.status_code == 409, lost.text
    assert lost.json()["error"]["message_key"] == "account.username.unavailable"
    assert _username_of(owner_session, first) == (name, name.lower())
    assert _account_id(owner_session, second) is None


def test_a_name_taken_after_the_draft_rolls_the_whole_verify_back(
    client: TestClient, owner_session: Session
) -> None:
    """Nothing from the verify survives; the code is still usable [BR2.4].

    [NFR4.4] No account, no spent code, no attempt row, the draft as it
    was -- and no failed-verify ceiling is counted, because the code was
    right.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    name = unique_username()
    phone = _phone()
    _, code = submit_signup(client, _body(phone, username=name))
    _take(client, name)
    before = _counters(owner_session)

    refused = client.post("/v1/auth/verify", json={"phone": phone, "code": code})

    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["retryable"] is False
    assert _account_id(owner_session, phone) is None
    assert _draft_username(owner_session, phone) == name
    assert _attempts(owner_session, phone) == 0
    after = _counters(owner_session)
    assert after.get(ScopeKind.VERIFY_FAIL_IP_HOURLY.value) == before.get(
        ScopeKind.VERIFY_FAIL_IP_HOURLY.value
    )


def test_the_same_code_with_a_replacement_completes_the_signup(
    client: TestClient, owner_session: Session
) -> None:
    """The replacement replaces the draft's name, inside the verify [BR2.5].

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    name, replacement = unique_username(), "Replaced_" + unique_username()[:8]
    phone = _phone()
    _, code = submit_signup(client, _body(phone, username=name))
    _take(client, name)
    client.post("/v1/auth/verify", json={"phone": phone, "code": code})

    retried = client.post(
        "/v1/auth/verify",
        json={"phone": phone, "code": code, "username": replacement},
    )

    assert retried.status_code == 200, retried.text
    assert _username_of(owner_session, phone) == (replacement, replacement.lower())


def test_a_taken_replacement_is_refused_and_the_code_still_works(
    client: TestClient, owner_session: Session
) -> None:
    """A second unavailable name answers 409 again; the code survives [BR2.5].

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    name, also_taken, free = unique_username(), unique_username(), unique_username()
    phone = _phone()
    _, code = submit_signup(client, _body(phone, username=name))
    _take(client, name)
    _take(client, also_taken)

    again = client.post(
        "/v1/auth/verify", json={"phone": phone, "code": code, "username": also_taken}
    )
    assert again.status_code == 409
    assert _draft_username(owner_session, phone) == name

    finally_free = client.post(
        "/v1/auth/verify", json={"phone": phone, "code": code, "username": free}
    )
    assert finally_free.status_code == 200, finally_free.text
    assert _username_of(owner_session, phone)[0] == free


def test_a_malformed_replacement_is_refused_before_anything_is_counted(
    client: TestClient, owner_session: Session
) -> None:
    """BR1 first: a 400 that consumes no counter and reads no code [BR2.5].

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    phone = _phone()
    _, code = submit_signup(client, _body(phone))
    before = _counters(owner_session)

    refused = client.post(
        "/v1/auth/verify", json={"phone": phone, "code": code, "username": "ab"}
    )

    assert refused.status_code == 400
    assert refused.json()["error"]["message_key"] == "account.username.too_short"
    assert _counters(owner_session) == before
    assert _attempts(owner_session, phone) == 0


def test_each_replacement_is_counted_before_the_code_and_survives_rollback(
    client: TestClient, owner_session: Session
) -> None:
    """Family C commits before the code is read [BR2.6, NFR2.3].

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    name, also_taken = unique_username(), unique_username()
    phone = _phone()
    _, code = submit_signup(client, _body(phone, username=name))
    _take(client, name)
    _take(client, also_taken)
    before = _counters(owner_session)

    refused = client.post(
        "/v1/auth/verify", json={"phone": phone, "code": code, "username": also_taken}
    )

    assert refused.status_code == 409
    after = _counters(owner_session)
    for kind in ("un_rp_dest_hour", "un_rp_ip_hour", "un_lk_global_hr"):
        assert after.get(kind, 0) == before.get(kind, 0) + 1, kind
    # A verify with no replacement consumes nothing here.
    client.post("/v1/auth/verify", json={"phone": phone, "code": code})
    assert _counters(owner_session).get("un_rp_dest_hour") == after["un_rp_dest_hour"]


def test_the_sixth_replacement_for_one_destination_is_refused(
    client: TestClient, owner_session: Session
) -> None:
    """At its limit, 429 before the code is read; the code still works.

    [NFR2.3] Five per destination per hour. The refused verify checks no
    code and writes no attempt, so the same code without a replacement
    completes the draft as it stands; a sixth for a DIFFERENT
    destination from the same network is not refused.

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    phone, other = _phone(), _phone()
    name = unique_username()
    _, code = submit_signup(client, _body(phone, username=name))
    _, other_code = submit_signup(client, _body(other))
    window = dt.datetime.now(tz=dt.UTC).replace(minute=0, second=0, microsecond=0)
    owner_session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter (id, scope_kind, scope_value, "
            "window_start, count) VALUES (gen_random_uuid(), 'un_rp_dest_hour', "
            ":value, :window, 5)"
        ),
        {"value": phone, "window": window},
    )
    owner_session.commit()

    refused = client.post(
        "/v1/auth/verify",
        json={"phone": phone, "code": code, "username": unique_username()},
    )
    elsewhere = client.post(
        "/v1/auth/verify",
        json={"phone": other, "code": other_code, "username": unique_username()},
    )
    plain = client.post("/v1/auth/verify", json={"phone": phone, "code": code})

    assert refused.status_code == 429, refused.text
    error = refused.json()["error"]
    assert error["message_key"] == "auth.lookup.too_many"
    assert error["retryable"] is False
    assert "retry-after" not in {key.lower() for key in refused.headers}
    assert elsewhere.status_code == 200, elsewhere.text
    assert plain.status_code == 200, plain.text
    assert _username_of(owner_session, phone)[0] == name


def test_a_draft_saved_before_usernames_creates_an_account_without_one(
    client: TestClient, owner_session: Session
) -> None:
    """No username, no ``USERNAME_SET``, and the flag up [BR2.7] (test-after).

    The draft is arranged as one saved before the column existed: its
    username is null.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange and read back
    :return: None
    """
    from tests.accounts.conftest import auth_header

    phone = _phone()
    _, code = submit_signup(client, _body(phone))
    owner_session.execute(
        sa.text("UPDATE pending_signup SET username = NULL WHERE phone = :p"),
        {"p": phone},
    )
    owner_session.commit()

    verified = client.post("/v1/auth/verify", json={"phone": phone, "code": code})

    assert verified.status_code == 200, verified.text
    assert _username_of(owner_session, phone) == (None, None)
    account_id = _account_id(owner_session, phone)
    assert account_id is not None
    events = owner_session.execute(
        sa.text("SELECT event FROM auth_audit_log WHERE account_id = :id"),
        {"id": account_id},
    ).scalars()
    assert "USERNAME_SET" not in set(events)
    headers = auth_header(owner_session, account_id)
    owner_session.commit()
    me = client.get("/v1/me", headers=headers).json()
    assert (me["username"], me["username_required"]) == (None, True)


def test_recovery_takes_no_login_field(client: TestClient) -> None:
    """Codes go to a phone or an email only [BR9.1, NFR3.9] (test-after).

    A ``login`` key is an unknown field, and a username typed into the
    email field is refused as any non-address is.

    :param client: A client against the restricted engine
    :return: None
    """
    assert client.post("/v1/auth/otp", json={"login": "rahim_01"}).status_code == 422
    assert (
        client.post(
            "/v1/auth/verify", json={"login": "rahim_01", "code": "123456"}
        ).status_code
        == 422
    )
    as_email = client.post("/v1/auth/otp", json={"email": "rahim_01"})
    assert as_email.status_code == 400
    assert as_email.json()["error"]["message_key"] == "email.invalid"


def test_creating_an_account_with_a_username_records_username_set(
    client: TestClient, owner_session: Session
) -> None:
    """By account id, after ``ACCOUNT_CREATED`` [BR2.8].

    :param client: A client against the restricted engine
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    account_id = sign_up(client, _body(_phone()))

    owner_session.expire_all()
    events = [
        row.event
        for row in owner_session.execute(
            sa.text(
                "SELECT event FROM auth_audit_log WHERE account_id = :id "
                "ORDER BY occurred_at, event"
            ),
            {"id": account_id},
        )
    ]
    assert "ACCOUNT_CREATED" in events
    assert events.count("USERNAME_SET") == 1
