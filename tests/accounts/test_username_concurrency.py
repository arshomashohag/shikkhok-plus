"""Two connections, interleaved: one owner per name, and the lock order [U1: BR10].

Written FIRST: which of two racing accounts ends up holding a name, and
whether a released name can slip through between the account check and
the hold check, are authorization answers. Every interleaving holds one
transaction open on a real connection as the restricted role and starts
the other on another, because a lock that is never contended in a test
is a lock nobody has tested. Each wait is bounded by the engine's
``lock_timeout``, so a regression fails rather than hangs.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid
from collections.abc import Callable
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session

from app.accounts import usernames
from app.accounts.service import SignupRole, create_account_rows
from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.db import advisory
from tests.accounts.signup_support import named_account, unique_username

NOW = dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _hmac_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the hold digests a key.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")


def _in_thread(work: Callable[[], Any]) -> tuple[threading.Thread, list[Any]]:
    """Start work on its own thread, collecting its result or its error.

    :param work: The work
    :return: The thread and a list that receives one outcome
    """
    outcome: list[Any] = []

    def run() -> None:
        """Run the work and record what it produced.

        :return: None
        """
        try:
            outcome.append(work())
        except Exception as error:  # noqa: BLE001 -- the test asserts on it
            outcome.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def _change(
    engine: Engine,
    account_id: uuid.UUID,
    name: str,
    *,
    now: dt.datetime = NOW,
    confirmed: bool = True,
) -> usernames.ChangeResult:
    """Run one username change in its own session, as the route's unit does.

    :param engine: The restricted engine
    :param account_id: The account
    :param name: The candidate
    :param now: The moment
    :param confirmed: Whether the password was confirmed
    :return: The change's answer
    """
    with Session(bind=engine, expire_on_commit=False) as session:
        return usernames.apply_change(
            session,
            account_id,
            usernames.judge(name),
            password_confirmed=confirmed,
            now=now,
            correlation_id="race",
        )


def _held(session: Session) -> tuple[threading.Event, threading.Event]:
    """Make a session's next commit wait until released.

    :param session: The session to hold
    :return: ``(reached, release)``: set when the commit is reached, and
        set by the test to let it proceed
    """
    reached, release = threading.Event(), threading.Event()
    commit = session.commit

    def held_commit() -> None:
        """Signal, wait, then commit.

        :return: None
        """
        reached.set()
        assert release.wait(timeout=10.0)
        commit()

    session.commit = held_commit  # type: ignore[method-assign]
    return reached, release


def _key_of(session: Session, account_id: uuid.UUID) -> str | None:
    """Read an account's username key.

    :param session: A reading session
    :param account_id: The account
    :return: The key
    """
    session.expire_all()
    value: str | None = session.execute(
        sa.text("SELECT username_key FROM account WHERE id = :id"), {"id": account_id}
    ).scalar_one()
    return value


# ------------------------------------------------------------------ BR10.1


def test_the_username_namespace_is_last_in_the_one_order() -> None:
    """``student``, ``account``, ``contact``, then ``username`` [BR10.1].

    :return: None
    """
    assert advisory._NAMESPACE_ORDER == ("student", "account", "contact", "username")
    assert advisory.username_key("rahim_01") == "username:rahim_01"


def test_one_call_takes_username_keys_after_every_other_key(
    restricted_session: Session, restricted_engine: Engine
) -> None:
    """Whatever order they are passed in, the username keys go last.

    :param restricted_session: The application's role
    :param restricted_engine: Its engine, whose statements are captured
    :return: None
    """
    taken: list[str] = []

    def capture(
        conn: object,
        cursor: object,
        statement: str,
        params: Any,
        context: object,
        executemany: bool,
    ) -> None:
        """Record each advisory key taken.

        :param conn: Unused
        :param cursor: Unused
        :param statement: The SQL text
        :param params: Its parameters
        :param context: Unused
        :param executemany: Unused
        :return: None
        """
        if "pg_advisory_xact_lock" in statement and isinstance(params, dict):
            taken.append(str(params["key"]))

    event.listen(restricted_engine, "before_cursor_execute", capture)
    try:
        advisory.lock_keys(
            restricted_session,
            [
                advisory.username_key("b_name"),
                advisory.contact_key("phone", "+8801711000001"),
                advisory.username_key("a_name"),
                advisory.account_key(uuid.UUID(int=7)),
            ],
        )
    finally:
        event.remove(restricted_engine, "before_cursor_execute", capture)

    namespaces = [key.split(":", 1)[0] for key in taken]
    assert namespaces == ["account", "contact", "username", "username"]


# ------------------------------------------------------ BR10.2, NFR4.6


def test_eight_accounts_claiming_one_name_at_once_get_one_owner(
    restricted_engine: Engine, owner_session: Session
) -> None:
    """Exactly one holds it; seven are refused cleanly, none with a 5xx.

    [BR10.1, BR10.2, NFR4.6] Overlapping first choices, released together.

    :param restricted_engine: The application's role
    :param owner_session: An arranging session, and the reader
    :return: None
    """
    name = unique_username()
    accounts = [named_account(owner_session)[0] for _ in range(8)]
    start = threading.Barrier(len(accounts))

    def claim(account_id: uuid.UUID) -> Callable[[], Any]:
        """Build one racing claim.

        :param account_id: The claiming account
        :return: The work
        """

        def work() -> Any:
            """Wait for the others, then claim.

            :return: The change's answer
            """
            start.wait(timeout=10.0)
            return _change(restricted_engine, account_id, name)

        return work

    runs = [_in_thread(claim(account_id)) for account_id in accounts]
    for thread, _ in runs:
        thread.join(timeout=30.0)
    outcomes = [outcome[0] for _, outcome in runs]

    winners = [o for o in outcomes if isinstance(o, usernames.ChangeResult)]
    losers = [o for o in outcomes if isinstance(o, usernames.UsernameUnavailable)]
    assert len(winners) == 1
    assert len(losers) == 7
    owner_session.expire_all()
    holders = owner_session.execute(
        sa.text("SELECT count(*) FROM account WHERE username_key = :k"),
        {"k": name.lower()},
    ).scalar_one()
    assert holders == 1


def test_a_writer_that_skipped_the_key_meets_the_constraint_as_unavailable(
    restricted_engine: Engine, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unique constraint maps to the clean refusal [BR10.2].

    The advisory key and the claim check are bypassed, so the only thing
    left between two owners is ``uq_account_username_key``.

    :param restricted_engine: The application's role
    :param owner_session: An arranging session
    :param monkeypatch: The patcher
    :return: None
    """
    name = unique_username()
    named_account(owner_session, name)
    other, _ = named_account(owner_session)
    monkeypatch.setattr(usernames, "claim_allowed", lambda *args, **kwargs: True)
    monkeypatch.setattr(usernames, "lock_keys", lambda *args, **kwargs: None)

    with pytest.raises(usernames.UsernameUnavailable):
        _change(restricted_engine, other, name)
    assert _key_of(owner_session, other) is None


# ------------------------------------------- a rename racing a sign-up


def test_a_sign_up_holding_the_new_name_refuses_the_rename_that_waited(
    restricted_engine: Engine, owner_session: Session
) -> None:
    """Sign-up completion first, held open; the rename waits, then loses.

    :param restricted_engine: The application's role
    :param owner_session: An arranging session, and the reader
    :return: None
    """
    new = unique_username()
    renamer, _ = named_account(owner_session, unique_username())
    signing_up = Session(bind=restricted_engine, expire_on_commit=False)
    create_account_rows(
        signing_up,
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        role=SignupRole.STUDENT,
        self_name="Racer",
        username=new,
        now=NOW,
    )

    thread, outcome = _in_thread(lambda: _change(restricted_engine, renamer, new))
    thread.join(timeout=1.0)
    assert thread.is_alive(), "the rename must wait for the sign-up's username key"
    signing_up.commit()
    signing_up.close()
    thread.join(timeout=10.0)

    assert isinstance(outcome[0], usernames.UsernameUnavailable)
    assert _key_of(owner_session, renamer) != new.lower()


def test_a_sign_up_for_the_old_name_waits_for_the_rename_and_finds_it_held(
    restricted_engine: Engine, owner_session: Session
) -> None:
    """Rename first, held open; the sign-up waits on the OLD key, then loses.

    [functional-spec § 7, "A rename releasing a name"] Without the key,
    the sign-up's two reads could straddle the commit and see the name
    neither taken nor held.

    :param restricted_engine: The application's role
    :param owner_session: An arranging session, and the reader
    :return: None
    """
    from app.errors import ConflictError

    old = unique_username()
    renamer, _ = named_account(owner_session, old)
    renaming = Session(bind=restricted_engine, expire_on_commit=False)
    reached, release = _held(renaming)
    rename, renamed = _in_thread(
        lambda: usernames.apply_change(
            renaming,
            renamer,
            usernames.judge(unique_username()),
            password_confirmed=True,
            now=NOW,
            correlation_id="race",
        )
    )
    assert reached.wait(timeout=10.0)

    def sign_up() -> Any:
        """Complete a sign-up asking for the old name.

        :return: The created account
        """
        with Session(bind=restricted_engine, expire_on_commit=False) as session:
            created = create_account_rows(
                session,
                phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
                role=SignupRole.STUDENT,
                self_name="Racer",
                username=old,
                now=NOW,
            )
            session.commit()
            return created

    signing, signed = _in_thread(sign_up)
    signing.join(timeout=1.0)
    assert signing.is_alive(), "the sign-up must wait for the rename's old key"
    release.set()
    rename.join(timeout=10.0)
    signing.join(timeout=10.0)
    renaming.close()

    assert isinstance(renamed[0], usernames.ChangeResult)
    assert isinstance(signed[0], ConflictError)
    assert signed[0].message_key == "account.username.unavailable"


# ------------------------------------------------- NFR4.2, two devices


@pytest.mark.parametrize(
    ("second_name", "expected"), [("a3", "too_soon"), ("a1", "reclaim")]
)
def test_two_devices_renaming_at_once_read_the_locked_row(
    restricted_engine: Engine,
    owner_session: Session,
    second_name: str,
    expected: str,
) -> None:
    """Device 2 waits on the account key and judges the row device 1 left.

    [NFR4.2, R-06] Device 1 renames ``a1`` to ``a2``, held open. Device 2
    renames to ``a3`` -- refused ``change_too_soon``, the window having
    closed under it -- or back to ``a1``, an exempt reclaim whose hold is
    placed on ``a2``, the key from the LOCKED re-read, never on the stale
    ``a1``. Neither run deadlocks.

    :param restricted_engine: The application's role
    :param owner_session: An arranging session, and the reader
    :param second_name: Which name device 2 asks for, as a suffix
    :param expected: What device 2 must get
    :return: None
    """
    stem = f"d{uuid.uuid4().hex[:8]}_"
    account_id, _ = named_account(owner_session, stem + "a1")
    device_one = Session(bind=restricted_engine, expire_on_commit=False)
    reached, release = _held(device_one)
    first, first_outcome = _in_thread(
        lambda: usernames.apply_change(
            device_one,
            account_id,
            usernames.judge(stem + "a2"),
            password_confirmed=True,
            now=NOW,
            correlation_id="device-1",
        )
    )
    assert reached.wait(timeout=10.0)

    second, second_outcome = _in_thread(
        lambda: _change(restricted_engine, account_id, stem + second_name)
    )
    second.join(timeout=1.0)
    assert second.is_alive(), "device 2 must wait for the account key"
    release.set()
    first.join(timeout=10.0)
    second.join(timeout=10.0)
    device_one.close()

    assert isinstance(first_outcome[0], usernames.ChangeResult)
    result = second_outcome[0]
    owner_session.expire_all()
    holds = dict(
        owner_session.execute(
            sa.text("SELECT key_digest, releasing_account_id FROM username_hold")
        ).all()
    )
    if expected == "too_soon":
        assert isinstance(result, usernames.UsernameChangeTooSoon)
        assert _key_of(owner_session, account_id) == stem + "a2"
    else:
        assert isinstance(result, usernames.ChangeResult)
        assert _key_of(owner_session, account_id) == stem + "a1"
        assert holds == {usernames.hold_digest(stem + "a2"): account_id}
