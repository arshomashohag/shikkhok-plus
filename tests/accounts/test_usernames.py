"""What a username is, and what a hold stores [BR1, BR7].

Two halves, ordered as the team's predicate orders them:

* **Written first** (BR1.7, BR7.1, BR7.2, BR7.4): the lowercase key that
  decides who may take a name and sign in with it, and the hold that
  decides who may take a released one back. Each answer is knowable from
  the rule before the code exists, and a wrong one is an authorization
  error.
* **Test-after, from the rule and never from the implementation**
  (BR1.1 to BR1.6, BR1.8, BR7.3): the format refusals and their fixed
  precedence, the reserved list, and the upsert.

The digests are asserted against an HMAC computed here, independently,
so a test cannot pass by agreeing with whatever the module computes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts import usernames
from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.db.models import Account
from app.errors import ValidationError

#: The key the digests are computed under in this file.
TEST_KEY = "test-only-hmac-key"

NOW = dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _hmac_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test the same HMAC key.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, TEST_KEY)


def _refusal(raw: str) -> str | None:
    """Return the one refusal key a candidate gets, or None.

    :param raw: The input
    :return: The message key, or None when the candidate is valid
    """
    refused = usernames.refusal_of(raw)
    return None if refused is None else refused.message_key


def _hmac(message: str) -> str:
    """Compute the expected digest without the module under test.

    :param message: The bytes to sign, as text
    :return: Lowercase hex HMAC-SHA256 under :data:`TEST_KEY`
    """
    return hmac.new(TEST_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()


def _account(session: Session, *, username: str | None = None) -> uuid.UUID:
    """Arrange one account, optionally holding a username.

    :param session: An arranging session
    :param username: The display form, or None
    :return: The account id
    """
    record = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=NOW,
        username=username,
        username_key=username.lower() if username else None,
    )
    session.add(record)
    session.commit()
    return record.id


# --------------------------------------------------------- BR1.7 (first)


def test_the_key_is_the_lowercase_form_and_the_text_keeps_its_casing() -> None:
    """``Rahim_01`` is stored as typed and compared as ``rahim_01`` [BR1.7].

    :return: None
    """
    candidate = usernames.judge("  Rahim_01 ")

    assert candidate.text == "Rahim_01"
    assert candidate.key == "rahim_01"
    assert usernames.key_of("RaHiM.x") == "rahim.x"


def test_two_casings_of_one_name_are_the_same_name(
    owner_session: Session, restricted_session: Session
) -> None:
    """A name taken as ``Rahim_01`` is unavailable as ``rahim_01`` [BR1.7].

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    holder = _account(owner_session, username="Rahim_01")
    other = _account(owner_session)
    key = usernames.judge("rahim_01").key

    assert usernames.holder_of(restricted_session, key) == holder
    assert usernames.claim_allowed(restricted_session, key, other, NOW) is False
    assert usernames.claim_allowed(restricted_session, key, holder, NOW) is True


def test_the_reserved_list_is_compared_by_key() -> None:
    """``Admin`` is reserved because ``admin`` is [BR1.7, BR1.8].

    :return: None
    """
    assert _refusal("Admin") == "account.username.reserved"
    assert _refusal("SUPPORT") == "account.username.reserved"


# --------------------------------------------- BR1.1 to BR1.6 (test-after)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("01712345678", "account.username.must_start_with_letter"),
        ("_rahim", "account.username.must_start_with_letter"),
        (".rahim", "account.username.must_start_with_letter"),
        ("rahim.", "account.username.bad_dot"),
        ("ra..him", "account.username.bad_dot"),
        ("রহিম", "account.username.invalid_character"),
        ("ra him", "account.username.invalid_character"),
        ("rahim@x", "account.username.invalid_character"),
        ("ra-him", "account.username.invalid_character"),
        ("ab", "account.username.too_short"),
        ("", "account.username.too_short"),
        ("   ", "account.username.too_short"),
        ("a" * 21, "account.username.too_long"),
        ("admin", "account.username.reserved"),
        ("Admin", "account.username.reserved"),
    ],
)
def test_each_refusal_names_one_rule(raw: str, expected: str) -> None:
    """The worked examples in BR1.6, one key each.

    :param raw: The input
    :param expected: Its one refusal key
    :return: None
    """
    assert _refusal(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Bad characters outrank everything, even an over-long input.
        ("a" * 25 + "@", "account.username.invalid_character"),
        # Length outranks the first letter and the dots.
        ("1.", "account.username.too_short"),
        ("1" + "a" * 25, "account.username.too_long"),
        # The first letter outranks the dots.
        ("1ab.", "account.username.must_start_with_letter"),
        # Every format rule outranks the reserved list.
        (" admin. ", "account.username.bad_dot"),
    ],
)
def test_the_precedence_is_fixed(raw: str, expected: str) -> None:
    """Several broken rules give the first in BR1.6's order [BR1.6].

    :param raw: An input breaking more than one rule
    :param expected: The refusal its precedence picks
    :return: None
    """
    assert _refusal(raw) == expected


@pytest.mark.parametrize(
    "raw", ["abc", "a" * 20, "rahim_math", "r.a.h", "Ra_1", "admin_1", "x__"]
)
def test_valid_names_are_accepted(raw: str) -> None:
    """Three and twenty are inside; ``admin_1`` is not reserved [BR1.3].

    :param raw: A valid input
    :return: None
    """
    assert usernames.refusal_of(raw) is None
    assert usernames.judge(raw).text == raw


def test_a_refusal_is_a_validation_error_that_carries_no_input() -> None:
    """The refusal never echoes what was typed [BR1.6].

    :return: None
    """
    with pytest.raises(ValidationError) as caught:
        usernames.judge("zq..sentinel")

    assert caught.value.code == "USERNAME_INVALID"
    assert caught.value.message_key == "account.username.bad_dot"
    assert caught.value.details is None
    assert "sentinel" not in str(caught.value)


# ------------------------------------------------------ BR7.1 (first)


def test_the_hold_digest_is_the_keyed_hmac_with_its_purpose_prefix() -> None:
    """A known vector, computed here [BR7.1, NFR3.2].

    :return: None
    """
    assert usernames.hold_digest("rahim_01") == _hmac("username-hold:v1:rahim_01")
    # Never the unkeyed hash, and never the text.
    assert usernames.hold_digest("rahim_01") != hashlib.sha256(b"rahim_01").hexdigest()
    assert "rahim" not in usernames.hold_digest("rahim_01")


def test_the_counter_values_are_keyed_and_purpose_separated() -> None:
    """Both ``u:`` values are known vectors, and never a hold digest [NFR3.3].

    :return: None
    """
    across = usernames.counter_value("rahim_01")
    per_net = usernames.counter_value("rahim_01", "203.0.113.0/24")

    assert across == "u:" + _hmac("username-counter:v1:rahim_01")[:62]
    assert per_net == "u:" + _hmac("username-counter:v1:rahim_01|203.0.113.0/24")[:62]
    assert len(across) == len(per_net) == 64
    assert across[2:] not in usernames.hold_digest("rahim_01")


def test_a_hold_row_stores_the_digest_and_never_the_name(
    owner_session: Session, restricted_session: Session
) -> None:
    """No column of ``username_hold`` contains the name [BR7.1, NFR3.2].

    :param owner_session: An arranging session, and the reader
    :param restricted_session: The application's role
    :return: None
    """
    releasing = _account(owner_session)
    usernames.place_hold(
        restricted_session, "zq_sentinel_77", releasing_account_id=releasing, now=NOW
    )
    usernames.place_hold(
        restricted_session, "zq_sentinel_78", releasing_account_id=None, now=NOW
    )
    restricted_session.commit()

    rows = owner_session.execute(sa.text("SELECT * FROM username_hold")).all()
    assert len(rows) == 2
    text = repr(rows).lower()
    assert "zq_sentinel" not in text
    digests = {row.key_digest for row in rows}
    assert digests == {
        _hmac("username-hold:v1:zq_sentinel_77"),
        _hmac("username-hold:v1:zq_sentinel_78"),
    }


# ------------------------------------------------------ BR7.2 (first)


def test_a_hold_lasts_thirty_days_and_ends_at_its_instant(
    owner_session: Session, restricted_session: Session
) -> None:
    """Live while now < held_until; free at it [BR7.2].

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    other = _account(owner_session)
    usernames.place_hold(
        restricted_session, "rahim_m", releasing_account_id=None, now=NOW
    )
    restricted_session.commit()
    ends = NOW + dt.timedelta(days=30)

    just_before = ends - dt.timedelta(microseconds=1)
    assert usernames.live_hold(restricted_session, "rahim_m", just_before) is not None
    assert (
        usernames.claim_allowed(restricted_session, "rahim_m", other, just_before)
        is False
    )
    assert usernames.live_hold(restricted_session, "rahim_m", ends) is None
    assert usernames.claim_allowed(restricted_session, "rahim_m", other, ends) is True


# ------------------------------------------------- BR7.3 (test-after)


def test_a_later_release_replaces_the_earlier_and_keeps_created_at(
    owner_session: Session, restricted_session: Session
) -> None:
    """One row per digest; the latest release wins [BR7.3].

    :param owner_session: An arranging session, and the reader
    :param restricted_session: The application's role
    :return: None
    """
    first = _account(owner_session)
    usernames.place_hold(
        restricted_session, "rahim_m", releasing_account_id=first, now=NOW
    )
    later = NOW + dt.timedelta(days=40)
    usernames.place_hold(
        restricted_session, "rahim_m", releasing_account_id=None, now=later
    )
    restricted_session.commit()

    owner_session.expire_all()
    row = owner_session.execute(
        sa.text(
            "SELECT held_until, releasing_account_id, created_at FROM username_hold"
        )
    ).one()
    assert row.held_until == later + dt.timedelta(days=30)
    assert row.releasing_account_id is None
    assert row.created_at == NOW


def test_clearing_a_hold_removes_its_row(
    owner_session: Session, restricted_session: Session
) -> None:
    """A successful claim deletes any row on its digest [BR6.9].

    :param owner_session: An arranging session, and the reader
    :param restricted_session: The application's role
    :return: None
    """
    usernames.place_hold(
        restricted_session, "rahim_m", releasing_account_id=None, now=NOW
    )
    usernames.clear_hold(restricted_session, "rahim_m")
    restricted_session.commit()

    count = owner_session.execute(
        sa.text("SELECT count(*) FROM username_hold")
    ).scalar_one()
    assert count == 0


# ------------------------------------------------------ BR7.4 (first)


def test_a_rename_hold_lets_only_its_account_take_the_name_back(
    owner_session: Session, restricted_session: Session
) -> None:
    """The releasing account may reclaim; nobody else may [BR7.4, BR6.9].

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    releasing = _account(owner_session)
    stranger = _account(owner_session)
    usernames.place_hold(
        restricted_session, "rahim_math", releasing_account_id=releasing, now=NOW
    )
    restricted_session.commit()

    hold = usernames.live_hold(restricted_session, "rahim_math", NOW)
    assert hold is not None
    assert hold.releasing_account_id == releasing
    assert usernames.claim_allowed(restricted_session, "rahim_math", releasing, NOW)
    assert not usernames.claim_allowed(restricted_session, "rahim_math", stranger, NOW)
    # A person not signed in is never the releasing account [BR2.2].
    assert not usernames.claim_allowed(restricted_session, "rahim_math", None, NOW)


def test_erasing_the_releasing_account_turns_its_hold_into_one_for_nobody(
    owner_session: Session, restricted_session: Session
) -> None:
    """``SET NULL`` on erasure; the hold goes on blocking everyone [BR7.4].

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    releasing = _account(owner_session)
    usernames.place_hold(
        restricted_session, "rahim_math", releasing_account_id=releasing, now=NOW
    )
    restricted_session.commit()

    owner_session.execute(
        sa.text("DELETE FROM account WHERE id = :id"), {"id": releasing}
    )
    owner_session.commit()

    hold = usernames.live_hold(restricted_session, "rahim_math", NOW)
    assert hold is not None
    assert hold.releasing_account_id is None
    assert not usernames.claim_allowed(restricted_session, "rahim_math", releasing, NOW)


# --------------------------------------------- the window (BR6.2, BR6.4)


def test_the_rename_window_is_thirty_days_exactly() -> None:
    """Closed on day 20, open on day 30; null opens at once [BR6.2].

    :return: None
    """
    changed = NOW
    assert usernames.window_open(None, NOW)
    assert not usernames.window_open(changed, NOW + dt.timedelta(days=20))
    assert usernames.window_open(changed, NOW + dt.timedelta(days=30))
    assert usernames.next_change_at(None, NOW) is None
    assert usernames.next_change_at(changed, NOW + dt.timedelta(days=20)) == (
        NOW + dt.timedelta(days=30)
    )
    assert usernames.next_change_at(changed, NOW + dt.timedelta(days=30)) is None


def test_the_reclaim_allowance_is_unused_until_spent_in_the_window() -> None:
    """Unused while null or earlier than the last rename [BR6.4, BR6.5].

    :return: None
    """
    changed = NOW
    assert usernames.reclaim_unused(changed, None)
    assert usernames.reclaim_unused(changed, NOW - dt.timedelta(days=1))
    assert not usernames.reclaim_unused(changed, NOW)
    assert not usernames.reclaim_unused(changed, NOW + dt.timedelta(days=3))


def test_next_change_at_while_closed_and_after() -> None:
    """The window's next change, through :func:`next_change_at` [BR6.2].

    :return: None
    """
    assert usernames.next_change_at(NOW, NOW + dt.timedelta(days=29)) == (
        NOW + dt.timedelta(days=30)
    )


# ------------------------------------------------- BR1.9 (test-after)


@pytest.mark.parametrize(
    ("username", "key"),
    [
        ("Rahim_x", None),  # a name with no key
        (None, "rahim_x"),  # a key with no name
        ("Rahim_x", "rahim_y"),  # a key that is not the name's
        ("1rahim", "1rahim"),  # a key without the FR1 shape
        ("rahim..x", "rahim..x"),
        ("rahim.", "rahim."),
        ("ab", "ab"),
    ],
)
def test_the_database_refuses_a_row_breaking_the_backstop(
    owner_session: Session, username: str | None, key: str | None
) -> None:
    """Both-or-neither, lowercase equality and the shape [BR1.9].

    Written as the owner, the way a writer that bypassed the module
    would: the CHECKs, not the application, refuse it.

    :param owner_session: A writing session
    :param username: The display form to write
    :param key: The key to write
    :return: None
    """
    with pytest.raises(sa.exc.IntegrityError) as caught:
        owner_session.execute(
            sa.text(
                "INSERT INTO account (id, phone, created_at, username, username_key) "
                "VALUES (gen_random_uuid(), '+8801711000990', now(), :name, :key)"
            ),
            {"name": username, "key": key},
        )
        owner_session.commit()
    owner_session.rollback()
    assert not usernames.is_username_clash(caught.value)


def test_a_duplicate_key_is_the_uniqueness_backstop(owner_session: Session) -> None:
    """``uq_account_username_key``, which is the clean refusal [BR10.2].

    :param owner_session: A writing session
    :return: None
    """
    _account(owner_session, username="Rahim_dup")

    with pytest.raises(sa.exc.IntegrityError) as caught:
        _account(owner_session, username="rahim_DUP")
    owner_session.rollback()

    assert usernames.is_username_clash(caught.value)


# ------------------------------------------- BR7.6, NFR4.7 (test-after)


def test_the_purge_removes_expired_holds_only_and_reruns_harmlessly(
    owner_session: Session, restricted_session: Session
) -> None:
    """Strictly before the run's moment goes; live stays; a rerun is a no-op.

    :param owner_session: An arranging session, and the reader
    :param restricted_session: The application's role, which purges
    :return: None
    """
    from app.governance.commands import purge_expired

    usernames.place_hold(
        restricted_session, "aged_one", releasing_account_id=None, now=NOW
    )
    usernames.place_hold(
        restricted_session,
        "fresh_one",
        releasing_account_id=None,
        now=NOW + dt.timedelta(days=10),
    )
    restricted_session.commit()
    moment = NOW + dt.timedelta(days=31)

    first = purge_expired(restricted_session, now=moment)
    second = purge_expired(restricted_session, now=moment)

    owner_session.expire_all()
    left = set(
        owner_session.execute(sa.text("SELECT key_digest FROM username_hold")).scalars()
    )
    assert left == {usernames.hold_digest("fresh_one")}
    assert first.deleted["username_hold"] == 1
    assert second.deleted["username_hold"] == 0


# ---------------------------------------------------- NFR3.7 (test-after)


def test_no_account_is_described_as_dormant() -> None:
    """Verify-first sign-up creates no dormant account [FR8.4, NFR3.7].

    :return: None
    """
    import inspect

    from app.auth import otp

    assert "dormant" not in (Account.__doc__ or "").lower()
    assert "dormant" not in inspect.getsource(otp.verify).lower()


def test_the_username_clock_is_aware_utc() -> None:
    """The one clock the routes read is now, in UTC.

    :return: None
    """
    before = dt.datetime.now(tz=dt.UTC)
    moment = usernames.utc_now()

    assert moment.tzinfo is dt.UTC
    assert before <= moment <= dt.datetime.now(tz=dt.UTC)


# ---------------------------------------------- the change unit's edges


def test_a_change_for_an_account_that_has_gone_is_a_401(
    restricted_session: Session,
) -> None:
    """Deleted between authentication and the lock [functional-spec § 7].

    :param restricted_session: The application's role
    :return: None
    """
    from app.errors import AuthorizationError

    with pytest.raises(AuthorizationError) as caught:
        usernames.apply_change(
            restricted_session,
            uuid.uuid4(),
            usernames.judge("rahim_gone"),
            password_confirmed=True,
            now=NOW,
            correlation_id="gone",
        )

    assert caught.value.status == 401


def test_a_name_that_appeared_under_the_lock_needs_the_password(
    owner_session: Session, restricted_session: Session
) -> None:
    """Two devices choosing first: the second is a rename [W7 step 2].

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    account_id = _account(owner_session, username="Chosen_first")

    with pytest.raises(usernames.UsernamePasswordRequired):
        usernames.apply_change(
            restricted_session,
            account_id,
            usernames.judge("chosen_second"),
            password_confirmed=False,
            now=NOW,
            correlation_id="second-device",
        )


def test_the_store_maps_only_the_key_constraint_to_unavailable(
    owner_session: Session,
    restricted_engine: sa.Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A duplicate key is ``unavailable``; any other refusal is not [BR10.2].

    The claim check is bypassed so the constraint is what answers. A
    candidate whose key is not its name's lowercase form -- impossible
    through :func:`usernames.judge` -- meets a different CHECK, which
    keeps its own handling.

    :param owner_session: An arranging session
    :param restricted_engine: The application's role
    :param monkeypatch: The patcher
    :return: None
    """
    _account(owner_session, username="Taken_key")
    claimer = _account(owner_session)
    monkeypatch.setattr(usernames, "claim_allowed", lambda *args, **kwargs: True)

    def change(candidate: usernames.Candidate) -> None:
        """Run one change in a fresh session.

        :param candidate: The candidate
        :return: None
        """
        with Session(bind=restricted_engine) as session:
            usernames.apply_change(
                session,
                claimer,
                candidate,
                password_confirmed=True,
                now=NOW,
                correlation_id="store",
            )

    with pytest.raises(usernames.UsernameUnavailable):
        change(usernames.judge("taken_KEY"))
    with pytest.raises(sa.exc.IntegrityError):
        change(usernames.Candidate(text="Mismatch_a", key="mismatch_b"))


def test_next_change_at_renders_as_iso_utc_with_seconds_and_z() -> None:
    """``details`` are strings, so the instant is written out [BR6.2].

    :return: None
    """
    moment = dt.datetime(2026, 12, 15, 12, 0, 5, 123456, tzinfo=dt.UTC)
    assert usernames.iso_utc(moment) == "2026-12-15T12:00:05Z"
    refused = usernames.UsernameChangeTooSoon(moment)
    assert refused.details == {"next_change_at": "2026-12-15T12:00:05Z"}
    assert refused.message_key == "account.username.change_too_soon"
    assert refused.status == 409
