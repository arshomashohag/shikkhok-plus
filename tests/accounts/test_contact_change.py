"""Replacing and removing a contact: who may, and what it never undoes.

**The authorization rules were written before the implementation**
(BR5.2, BR5.3, BR5.5, BR5.7, BR5.13, NFR2.5): the outcome of each is
knowable from the request alone, and a wrong one hands an account, a
code or a child's seat to someone it was not meant for. The test-after
rules (BR5.4, BR5.6, BR5.9 to BR5.12) follow in their own section,
written from the rules rather than from the code.

Everything runs through the real routes against the restricted role.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.accounts.contact_support import (
    PASSWORD,
    account,
    address,
    auth,
    code_for,
    number,
    seat,
    seat_links,
)
from tests.batches.conftest import make_teacher

ADMINS_ENV = "SHIKKHOKPLUS_PLATFORM_ADMIN_PHONES"


def _key(response: object) -> str:
    """Read the refusal's message key.

    :param response: The response
    :return: The ``message_key``
    """
    body = response.json()  # type: ignore[attr-defined]
    key: str = body["error"]["message_key"]
    return key


def _contacts(session: Session, account_id: uuid.UUID) -> tuple[str | None, str | None]:
    """Read an account's phone and email fresh.

    :param session: An arranging session
    :param account_id: The account
    :return: ``(phone, email)``
    """
    session.expire_all()
    row = session.execute(
        sa.text("SELECT phone, email FROM account WHERE id = :a"), {"a": account_id}
    ).one()
    session.commit()
    return row[0], row[1]


def _replacement_code_row(
    session: Session, requester: uuid.UUID
) -> tuple[uuid.UUID, dt.datetime | None, int]:
    """Read the requester's latest replacement code and its attempt count.

    :param session: An arranging session
    :param requester: The account that requested it
    :return: ``(id, consumed_at, attempts)``
    """
    session.expire_all()
    row = session.execute(
        sa.text(
            "SELECT o.id, o.consumed_at, "
            "(SELECT count(*) FROM verify_attempt v WHERE v.otp_request_id = o.id) "
            "FROM otp_request o WHERE o.requested_by_account_id = :a "
            "AND o.purpose = 'contact_replace' ORDER BY o.issued_at DESC LIMIT 1"
        ),
        {"a": requester},
    ).one()
    session.commit()
    return row[0], row[1], int(row[2])


def _verify_failures(session: Session) -> int:
    """Read the per-network failed-verify count, every window summed.

    :param session: An arranging session
    :return: The count
    """
    session.expire_all()
    count = session.execute(
        sa.text(
            "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
            "WHERE scope_kind = 'vf_ip_hour'"
        )
    ).scalar_one()
    session.commit()
    return int(count)


# ------------------------------------------------------------------ BR5.2


def test_replacing_a_contact_needs_the_password(
    api_client: TestClient, owner_session: Session, outbound: list[tuple[str, str]]
) -> None:
    """No password, then a wrong one: both refused, and no code is sent.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :return: None
    """
    holder = account(owner_session, phone=number(), password=PASSWORD)
    headers = auth(api_client, owner_session, holder)
    new = number()

    missing = api_client.post("/v1/me/contact", json={"phone": new}, headers=headers)
    wrong = api_client.post(
        "/v1/me/contact", json={"phone": new, "password": "not it"}, headers=headers
    )

    assert missing.status_code == 400, missing.text
    assert _key(missing) == "account.contact.password_required"
    assert wrong.status_code == 400, wrong.text
    assert _key(wrong) == "auth.password.current_wrong"
    assert all(to != new for to, _ in outbound)


def test_an_account_without_a_password_must_set_one_before_a_change(
    api_client: TestClient, owner_session: Session
) -> None:
    """Replace and remove both refuse until a password exists.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    holder = account(owner_session, phone=number(), email=address())
    headers = auth(api_client, owner_session, holder)

    replaced = api_client.post(
        "/v1/me/contact",
        json={"email": address(), "password": "anything"},
        headers=headers,
    )
    removed = api_client.post(
        "/v1/me/contact/remove",
        json={"kind": "email", "password": "anything"},
        headers=headers,
    )

    assert replaced.status_code == 400, replaced.text
    assert _key(replaced) == "account.contact.password_required"
    assert removed.status_code == 400, removed.text
    assert _key(removed) == "account.contact.password_required"


def test_removing_a_contact_needs_the_right_password(
    api_client: TestClient, owner_session: Session
) -> None:
    """A wrong password removes nothing.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    phone, email = number(), address()
    holder = account(owner_session, phone=phone, email=email, password=PASSWORD)
    headers = auth(api_client, owner_session, holder)

    refused = api_client.post(
        "/v1/me/contact/remove",
        json={"kind": "email", "password": "not it"},
        headers=headers,
    )

    assert refused.status_code == 400, refused.text
    assert _key(refused) == "auth.password.current_wrong"
    assert _contacts(owner_session, holder) == (phone, email)


# ------------------------------------------------------------------ BR5.5


def test_the_last_contact_cannot_be_removed(
    api_client: TestClient, owner_session: Session
) -> None:
    """An account always keeps one way in.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :return: None
    """
    phone = number()
    holder = account(owner_session, phone=phone, password=PASSWORD)
    headers = auth(api_client, owner_session, holder)

    refused = api_client.post(
        "/v1/me/contact/remove",
        json={"kind": "phone", "password": PASSWORD},
        headers=headers,
    )

    assert refused.status_code == 409, refused.text
    assert _key(refused) == "account.contact.last_one"
    assert _contacts(owner_session, holder) == (phone, None)


# ------------------------------------------------------------------ BR5.7


def test_removing_or_replacing_a_contact_unlinks_nothing(
    api_client: TestClient, owner_session: Session, outbound: list[tuple[str, str]]
) -> None:
    """The seat the phone linked stays linked and accepted after both changes.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :return: None
    """
    phone, email = number(), address()
    holder = account(owner_session, phone=phone, email=email, password=PASSWORD)
    teacher = make_teacher(owner_session, name="Physics")
    linked = seat(
        owner_session,
        teacher.batch_id,
        student_phone=phone,
        student_account_id=holder,
        student_decision="accepted",
        guardian_email=email,
        guardian_account_id=holder,
    )
    headers = auth(api_client, owner_session, holder)

    removed = api_client.post(
        "/v1/me/contact/remove",
        json={"kind": "phone", "password": PASSWORD},
        headers=headers,
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["phone"] is None

    replacement = address()
    asked = api_client.post(
        "/v1/me/contact",
        json={"email": replacement, "password": PASSWORD},
        headers=headers,
    )
    assert asked.status_code == 200, asked.text
    proved = api_client.post(
        "/v1/me/contact/verify",
        json={"email": replacement, "code": code_for(outbound, replacement)},
        headers=headers,
    )
    assert proved.status_code == 200, proved.text
    assert proved.json()["email"] == replacement

    links = seat_links(owner_session, linked)
    assert (links.student, links.student_decision) == (holder, "accepted")
    assert (links.guardian, links.guardian_decision) == (holder, "pending")
    assert _contacts(owner_session, holder) == (None, replacement)


# ------------------------------------------------------- BR5.3 and NFR2.5


def test_a_replacement_code_is_completed_only_by_the_account_that_asked(
    api_client: TestClient, owner_session: Session, outbound: list[tuple[str, str]]
) -> None:
    """Two accounts, one destination: neither shadows, spends nor attempts
    the other's code.

    A asks first and B second, so B's code is the LATEST for the address.
    A must still complete with A's code; B's row must be untouched by it;
    B presenting A's code is a failure recorded on B's row only, counted
    against the network; and B's own code then finds the address taken.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :return: None
    """
    target = address()
    first = account(owner_session, phone=number(), email=address(), password=PASSWORD)
    second = account(owner_session, phone=number(), email=address(), password=PASSWORD)
    first_headers = auth(api_client, owner_session, first)
    second_headers = auth(api_client, owner_session, second)

    asked = api_client.post(
        "/v1/me/contact",
        json={"email": target, "password": PASSWORD},
        headers=first_headers,
    )
    assert asked.status_code == 200, asked.text
    first_code = code_for(outbound, target)
    asked = api_client.post(
        "/v1/me/contact",
        json={"email": target, "password": PASSWORD},
        headers=second_headers,
    )
    assert asked.status_code == 200, asked.text
    second_code = code_for(outbound, target)
    second_row, _, _ = _replacement_code_row(owner_session, second)

    done = api_client.post(
        "/v1/me/contact/verify",
        json={"email": target, "code": first_code},
        headers=first_headers,
    )
    assert done.status_code == 200, done.text
    assert _contacts(owner_session, first)[1] == target
    assert _replacement_code_row(owner_session, second) == (second_row, None, 0)

    failures = _verify_failures(owner_session)
    stolen = api_client.post(
        "/v1/me/contact/verify",
        json={"email": target, "code": first_code},
        headers=second_headers,
    )
    assert stolen.status_code == 400, stolen.text
    first_row, first_consumed, first_attempts = _replacement_code_row(
        owner_session, first
    )
    assert first_consumed is not None
    assert first_attempts == 1  # its own successful attempt, nothing from B
    assert _replacement_code_row(owner_session, second)[2] == 1
    assert _verify_failures(owner_session) == failures + 1

    taken = api_client.post(
        "/v1/me/contact/verify",
        json={"email": target, "code": second_code},
        headers=second_headers,
    )
    assert taken.status_code == 409, taken.text
    assert _key(taken) == "account.contact.taken"
    assert first_row != second_row


# ----------------------------------------------------------------- BR5.13


def test_an_allowlisted_admin_contact_cannot_be_removed_or_replaced(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Freeing it would make whoever verifies it next an administrator.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param monkeypatch: The patcher
    :return: None
    """
    phone, email = number(), address()
    holder = account(owner_session, phone=phone, email=email, password=PASSWORD)
    headers = auth(api_client, owner_session, holder)
    monkeypatch.setenv(ADMINS_ENV, phone)

    removed = api_client.post(
        "/v1/me/contact/remove",
        json={"kind": "phone", "password": PASSWORD},
        headers=headers,
    )
    replaced = api_client.post(
        "/v1/me/contact",
        json={"phone": number(), "password": PASSWORD},
        headers=headers,
    )

    assert removed.status_code == 409, removed.text
    assert _key(removed) == "account.contact.admin_locked"
    assert replaced.status_code == 409, replaced.text
    assert _key(replaced) == "account.contact.admin_locked"
    assert _contacts(owner_session, holder) == (phone, email)


def test_an_admin_contact_listed_after_the_request_is_refused_at_verify(
    api_client: TestClient,
    owner_session: Session,
    outbound: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The allowlist is read again at verify; the code stays unspent.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :param monkeypatch: The patcher
    :return: None
    """
    phone, email = number(), address()
    holder = account(owner_session, phone=phone, email=email, password=PASSWORD)
    headers = auth(api_client, owner_session, holder)
    new = number()
    asked = api_client.post(
        "/v1/me/contact", json={"phone": new, "password": PASSWORD}, headers=headers
    )
    assert asked.status_code == 200, asked.text

    monkeypatch.setenv(ADMINS_ENV, phone)
    refused = api_client.post(
        "/v1/me/contact/verify",
        json={"phone": new, "code": code_for(outbound, new)},
        headers=headers,
    )

    assert refused.status_code == 409, refused.text
    assert _key(refused) == "account.contact.admin_locked"
    assert _contacts(owner_session, holder) == (phone, email)
    _, consumed, _ = _replacement_code_row(owner_session, holder)
    assert consumed is None


# --------------------------------------------------------------------------
# Test-after: written from BR5.4, BR5.6, BR5.9 to BR5.12 and NFR3.4, NFR3.5.
# --------------------------------------------------------------------------


def _set_changes(session: Session, account_id: uuid.UUID, count: int) -> None:
    """Set today's completed-change count for an account.

    :param session: An arranging session
    :param account_id: The account
    :param count: The count to hold
    :return: None
    """
    today = dt.datetime.now(tz=dt.UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter (id, scope_kind, scope_value, "
            "window_start, count) VALUES (gen_random_uuid(), 'contact_chg_day', "
            ":a, :w, :c) ON CONFLICT (scope_kind, scope_value, window_start) "
            "DO UPDATE SET count = :c"
        ),
        {"a": str(account_id), "w": today, "c": count},
    )
    session.commit()


def _changes(session: Session, account_id: uuid.UUID) -> int:
    """Read today's completed-change count for an account.

    :param session: An arranging session
    :param account_id: The account
    :return: The count
    """
    session.expire_all()
    count = session.execute(
        sa.text(
            "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
            "WHERE scope_kind = 'contact_chg_day' AND scope_value = :a"
        ),
        {"a": str(account_id)},
    ).scalar_one()
    session.commit()
    return int(count)


def _audit(session: Session, account_id: uuid.UUID) -> list[str]:
    """Read the account's audit events, oldest first.

    :param session: An arranging session
    :param account_id: The account
    :return: The event names
    """
    session.expire_all()
    rows = session.execute(
        sa.text(
            "SELECT event FROM auth_audit_log WHERE account_id = :a "
            "ORDER BY occurred_at"
        ),
        {"a": account_id},
    ).scalars()
    events = list(rows)
    session.commit()
    return events


def test_a_completed_removal_is_counted_audited_and_told(
    api_client: TestClient, owner_session: Session, outbound: list[tuple[str, str]]
) -> None:
    """One count, one audit row by id, one notice to the removed address.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :return: None
    """
    phone, email = number(), address()
    holder = account(owner_session, phone=phone, email=email, password=PASSWORD)
    headers = auth(api_client, owner_session, holder)

    removed = api_client.post(
        "/v1/me/contact/remove",
        json={"kind": "email", "password": PASSWORD},
        headers=headers,
    )

    assert removed.status_code == 200, removed.text
    assert removed.json()["email"] is None
    assert _changes(owner_session, holder) == 1
    assert _audit(owner_session, holder)[-1] == "CONTACT_REMOVED"
    told = [body for to, body in outbound if to == email]
    assert len(told) == 1
    assert phone not in told[0]
    assert str(holder) not in told[0]
    # The device that made the change is still signed in [BR5.10].
    assert api_client.get("/v1/me", headers=headers).status_code == 200


def test_removing_a_kind_the_account_lacks_changes_nothing(
    api_client: TestClient, owner_session: Session, outbound: list[tuple[str, str]]
) -> None:
    """Answered with the account; nothing counted, audited or sent [BR5.12].

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :return: None
    """
    phone = number()
    holder = account(owner_session, phone=phone, password=PASSWORD)
    headers = auth(api_client, owner_session, holder)

    answered = api_client.post(
        "/v1/me/contact/remove",
        json={"kind": "email", "password": PASSWORD},
        headers=headers,
    )

    assert answered.status_code == 200, answered.text
    assert answered.json()["phone"] == phone
    assert _changes(owner_session, holder) == 0
    assert "CONTACT_REMOVED" not in _audit(owner_session, holder)
    assert outbound == []


def test_the_sixth_change_of_a_day_is_refused_before_any_code(
    api_client: TestClient, owner_session: Session, outbound: list[tuple[str, str]]
) -> None:
    """Five a day; the request step only reads the count [BR5.6].

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :return: None
    """
    holder = account(owner_session, phone=number(), email=address(), password=PASSWORD)
    headers = auth(api_client, owner_session, holder)
    _set_changes(owner_session, holder, 5)
    new = address()

    asked = api_client.post(
        "/v1/me/contact", json={"email": new, "password": PASSWORD}, headers=headers
    )
    removed = api_client.post(
        "/v1/me/contact/remove",
        json={"kind": "email", "password": PASSWORD},
        headers=headers,
    )

    assert asked.status_code == 409, asked.text
    assert _key(asked) == "account.contact.change_limit"
    assert removed.status_code == 409, removed.text
    assert _key(removed) == "account.contact.change_limit"
    assert all(to != new for to, _ in outbound)
    assert _changes(owner_session, holder) == 5


def test_a_verify_at_the_limit_is_refused_and_leaves_the_code_unspent(
    api_client: TestClient, owner_session: Session, outbound: list[tuple[str, str]]
) -> None:
    """The breach rolls the change back: nothing counted, code still good.

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :return: None
    """
    email = address()
    holder = account(owner_session, phone=number(), email=email, password=PASSWORD)
    headers = auth(api_client, owner_session, holder)
    _set_changes(owner_session, holder, 4)
    new = address()
    asked = api_client.post(
        "/v1/me/contact", json={"email": new, "password": PASSWORD}, headers=headers
    )
    assert asked.status_code == 200, asked.text
    _set_changes(owner_session, holder, 5)

    refused = api_client.post(
        "/v1/me/contact/verify",
        json={"email": new, "code": code_for(outbound, new)},
        headers=headers,
    )

    assert refused.status_code == 409, refused.text
    assert _key(refused) == "account.contact.change_limit"
    assert _changes(owner_session, holder) == 5
    assert _replacement_code_row(owner_session, holder)[1] is None
    assert _contacts(owner_session, holder)[1] == email


def test_a_failure_after_the_count_rolls_back_count_code_and_change(
    api_client: TestClient,
    owner_session: Session,
    outbound: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counter, the spent code and the write commit together or not at all.

    The matcher is made to fail after the non-committing consume and
    before the commit; afterwards the count is unchanged, the code is
    unspent and still verifies, and the old address is still the
    account's [BR5.6, NFR4.5].

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :param monkeypatch: The patcher
    :return: None
    """
    import app.accounts.contact as contact

    email = address()
    holder = account(owner_session, phone=number(), email=email, password=PASSWORD)
    headers = auth(api_client, owner_session, holder)
    new = address()
    asked = api_client.post(
        "/v1/me/contact", json={"email": new, "password": PASSWORD}, headers=headers
    )
    assert asked.status_code == 200, asked.text
    code = code_for(outbound, new)

    real = contact.match_contact

    def broken(*args: object, **kwargs: object) -> None:
        """Fail where the change's write would have happened.

        :param args: Ignored
        :param kwargs: Ignored
        :return: None
        :raises RuntimeError: Always
        """
        raise RuntimeError("forced failure after the consume")

    monkeypatch.setattr(contact, "match_contact", broken)
    with pytest.raises(RuntimeError):
        api_client.post(
            "/v1/me/contact/verify",
            json={"email": new, "code": code},
            headers=headers,
        )

    assert _changes(owner_session, holder) == 0
    assert _replacement_code_row(owner_session, holder)[1] is None
    assert _contacts(owner_session, holder)[1] == email

    monkeypatch.setattr(contact, "match_contact", real)
    done = api_client.post(
        "/v1/me/contact/verify", json={"email": new, "code": code}, headers=headers
    )
    assert done.status_code == 200, done.text
    assert _changes(owner_session, holder) == 1


def test_a_notice_that_fails_never_fails_the_change(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Best-effort, after commit, logged once by channel [BR5.9, NFR4.7, NFR4.9].

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param monkeypatch: The patcher
    :param caplog: The log capture
    :return: None
    """
    from app.gateway.email import NullEmailGateway

    email = address()
    holder = account(owner_session, phone=number(), email=email, password=PASSWORD)
    headers = auth(api_client, owner_session, holder)
    seen: list[str | None] = []

    def failing(*args: object) -> object:
        """Record whether the change was already committed, then fail.

        :param args: Ignored
        :return: Never
        :raises ConnectionError: Always
        """
        owner_session.expire_all()
        seen.append(_contacts(owner_session, holder)[1])
        raise ConnectionError("gateway down")

    monkeypatch.setattr(NullEmailGateway, "send", failing)
    caplog.set_level("INFO")

    removed = api_client.post(
        "/v1/me/contact/remove",
        json={"kind": "email", "password": PASSWORD},
        headers=headers,
    )

    assert removed.status_code == 200, removed.text
    assert seen == [None]  # the address was already gone: sent after commit
    notices = [r for r in caplog.records if r.getMessage() == "contact notice"]
    assert len(notices) == 1
    assert notices[0].purpose == "contact_notice_email"  # type: ignore[attr-defined]
    assert notices[0].outcome == "failed"  # type: ignore[attr-defined]
    assert email not in caplog.text


def test_no_contact_reaches_a_log_line_or_an_audit_row(
    api_client: TestClient,
    owner_session: Session,
    outbound: list[tuple[str, str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Sentinel contacts through replace, refusal and removal [NFR3.4].

    :param api_client: The HTTP client
    :param owner_session: An arranging session
    :param outbound: The captured sends
    :param caplog: The log capture
    :return: None
    """
    caplog.set_level("DEBUG")
    phone = "+8801700000999"
    email = "sentinel-old@example.com"
    replacement = "sentinel-new@example.com"
    holder = account(owner_session, phone=phone, email=email, password=PASSWORD)
    headers = auth(api_client, owner_session, holder)

    api_client.post(
        "/v1/me/contact",
        json={"email": replacement, "password": PASSWORD},
        headers=headers,
    )
    api_client.post(
        "/v1/me/contact/verify",
        json={"email": replacement, "code": code_for(outbound, replacement)},
        headers=headers,
    )
    api_client.post(
        "/v1/me/contact/remove",
        json={"kind": "phone", "password": "wrong"},
        headers=headers,
    )
    api_client.post(
        "/v1/me/contact/remove",
        json={"kind": "phone", "password": PASSWORD},
        headers=headers,
    )

    captured = caplog.text + "".join(str(vars(record)) for record in caplog.records)
    for sentinel in (phone, email, replacement, "sentinel"):
        assert sentinel not in captured
    owner_session.expire_all()
    audit = owner_session.execute(
        sa.text("SELECT * FROM auth_audit_log WHERE account_id = :a"), {"a": holder}
    ).all()
    assert {row.event for row in audit} >= {"CONTACT_REPLACED", "CONTACT_REMOVED"}
    assert all(
        sentinel not in str(tuple(row))
        for row in audit
        for sentinel in (phone, email, replacement)
    )


def test_the_notice_templates_carry_nothing_identifying() -> None:
    """No username, contact, account id or code; the text fits a segment
    [NFR3.5].

    :return: None
    """
    from app.gateway.template import (
        GSM7_SEGMENT,
        gsm7_length,
        render_contact_notice_email,
        render_contact_notice_sms,
    )

    sms = render_contact_notice_sms()
    email = render_contact_notice_email()

    assert gsm7_length(sms) <= GSM7_SEGMENT
    for body in (sms, email.subject, email.text):
        assert "@" not in body
        assert not any(part.isdigit() and len(part) >= 4 for part in body.split())
        assert "{" not in body
    assert "ShikkhokPlus" in email.text
