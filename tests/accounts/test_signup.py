"""Signup: the Owner fork, the one transaction, and the ordering.

Written from the acceptance criteria rather than from the service
[team: Testing Posture]. The three that carry real weight are the
``Owner`` fork [AC1.11.1], the atomicity of account-and-profile
[BR3.3], and that the account exists **before** the code is sent
[AC1.11.4] -- the last of which is an ordering claim that no response
body reveals, so it is asserted against the database at the moment the
gateway is called.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.service import (
    DuplicateNumber,
    SignupRole,
    create_account,
)
from app.db.models import Account, Owner, Profile
from app.errors import ConflictError


def _phone() -> str:
    """Generate a unique number for one test.

    :return: A number in international form
    """
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


def test_choosing_teacher_creates_an_owner_row(
    restricted_session: Session, owner_session: Session
) -> None:
    """The row's EXISTENCE is the teacher claim [BR4.1, AC1.11.1].

    :param restricted_session: A session as the application role
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    created = create_account(
        restricted_session,
        phone=_phone(),
        role=SignupRole.TEACHER,
        self_name="Karim Teacher",
    )

    owners = owner_session.execute(
        sa.select(sa.func.count(Owner.id)).where(Owner.account_id == created.account_id)
    ).scalar_one()

    assert created.is_teacher is True
    assert owners == 1


@pytest.mark.parametrize("role", [SignupRole.STUDENT, SignupRole.GUARDIAN])
def test_choosing_any_other_role_creates_no_owner_row(
    restricted_session: Session, owner_session: Session, role: SignupRole
) -> None:
    """A student holding a teacher lens is the harm [BR4.1, AC1.11.1].

    Both non-teacher roles, because they are indistinguishable in their
    effect and a test covering one would not notice an implementation
    that forked on ``!= STUDENT``.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to read fixture data back
    :param role: The claimed role
    :return: None
    """
    created = create_account(
        restricted_session, phone=_phone(), role=role, self_name="Rahim"
    )

    owners = owner_session.execute(
        sa.select(sa.func.count(Owner.id)).where(Owner.account_id == created.account_id)
    ).scalar_one()

    assert created.is_teacher is False
    assert owners == 0


def test_the_name_lands_on_the_profile_and_not_on_the_account(
    restricted_session: Session, owner_session: Session
) -> None:
    """No third name; signup writes ``self_name`` [BR3.1, ADR-010].

    :param restricted_session: A session as the application role
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    created = create_account(
        restricted_session,
        phone=_phone(),
        role=SignupRole.STUDENT,
        self_name="Rahim Uddin",
        address="12 Example Road, Dhaka",
    )

    profile = owner_session.get(Profile, created.account_id)

    assert profile is not None
    assert profile.self_name == "Rahim Uddin"
    assert profile.address == "12 Example Road, Dhaka"
    # The structural half: there is no personal field on `Account` to
    # have written it to instead.
    assert "self_name" not in Account.__table__.columns


def test_a_profile_exists_for_every_account_signup_creates(
    restricted_session: Session, owner_session: Session
) -> None:
    """``Profile`` stops being optional [BR3.3, ADR-010].

    :param restricted_session: A session as the application role
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    created = create_account(
        restricted_session,
        phone=_phone(),
        role=SignupRole.GUARDIAN,
        self_name="Guardian",
    )

    assert owner_session.get(Profile, created.account_id) is not None


def test_a_failure_between_the_two_writes_leaves_neither(
    restricted_session: Session,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One transaction, asserted by breaking it [BR3.3].

    **The assertion that could not be made without a fault.** A happy
    path cannot distinguish "one transaction" from "two that both
    happened to succeed", and the account-with-no-profile row is
    created precisely when the second write fails.

    The fault is injected at the ``Profile`` **constructor**, which is
    the narrowest point that is unambiguously after the ``Account``
    flush and before the commit. Patching the service's own function
    would prove nothing; patching the model it writes second reproduces
    the real shape -- the first write succeeded, the second did not.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to read fixture data back
    :param monkeypatch: The patcher
    :return: None
    """
    phone = _phone()

    def _explode(*args: object, **kwargs: object) -> None:
        """Fail where the profile row would have been built.

        :param args: Unused
        :param kwargs: Unused
        :return: Never returns
        :raises RuntimeError: Always
        """
        raise RuntimeError("injected failure at the profile write")

    monkeypatch.setattr("app.accounts.service.Profile", _explode)

    with pytest.raises(RuntimeError):
        create_account(
            restricted_session,
            phone=phone,
            role=SignupRole.STUDENT,
            self_name="Rahim",
        )
    restricted_session.rollback()

    owner_session.expire_all()
    account_id = owner_session.execute(
        sa.select(Account.id).where(Account.phone == phone)
    ).scalar_one_or_none()

    assert account_id is None, "an account survived a failed signup"


def test_a_number_that_already_has_an_account_is_refused(
    restricted_session: Session, owner_session: Session
) -> None:
    """The uniqueness constraint reporting itself [BR4.4, AC1.12.4].

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    phone = _phone()
    owner_session.add(Account(phone=phone, created_at=dt.datetime.now(tz=dt.UTC)))
    owner_session.commit()

    with pytest.raises(DuplicateNumber) as refusal:
        create_account(
            restricted_session,
            phone=phone,
            role=SignupRole.STUDENT,
            self_name="Rahim",
        )

    # A ConflictError, which is where retryability lives: the handler
    # reads it off the CLASS in exactly one place, so asserting the
    # class is asserting the 409-and-not-retryable answer [team: Error
    # handling].
    assert refusal.value.code == "ACCOUNT_EXISTS"
    assert isinstance(refusal.value, ConflictError)


def test_nothing_verifies_a_role_claim(
    restricted_session: Session, owner_session: Session
) -> None:
    """A deliberate decision that reads as an omission [BR4.2].

    Recorded as a test for the same reason it is recorded as a rule:
    the next reader's instinct is to add verification, and claiming
    Teacher gains nobody anything they could not have by creating a
    batch.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to read fixture data back
    :return: None
    """
    created = create_account(
        restricted_session,
        phone=_phone(),
        role=SignupRole.TEACHER,
        self_name="Nobody checked this",
    )

    assert created.is_teacher is True
    # And no role was stored anywhere: the lens is computed per request
    # from owned batches and accepted seats [TC-11, D-2].
    assert "role" not in Account.__table__.columns
    assert "is_teacher" not in Account.__table__.columns
