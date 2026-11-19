"""Withdrawing a join request is total, and never switch-gated (Call 12).

**Written before the implementation** (Review Focus 4). After a withdrawal
nothing of the request remains: not the row, not the owners'
``hub_enquiry_received`` items and not the guardian's
``hub_enquiry_answered`` item. Withdrawing someone else's request, or one
that does not exist, changes nothing and is not an error.

A withdrawal and the owner's close (:func:`app.hub.enquiries.owner.close`)
each lock the request row before touching an inbox item, so the two never
deadlock [F7].
"""

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.authz.lenses import TeacherLens
from app.errors import AuthorizationError
from app.hub.enquiries import forget, owner, sending
from app.notifications.inbox import HUB_ENQUIRY_ANSWERED, HUB_ENQUIRY_RECEIVED
from tests.enquiries.support import EnquirableWorld, enquirable_owner, guardian

NOW = dt.datetime(2026, 11, 19, 4, 0, tzinfo=dt.UTC)


def _send(
    session: Session, account: uuid.UUID, world: EnquirableWorld
) -> sending.MyEnquiry:
    return sending.send(
        session,
        account,
        world.owner_slug,
        student_name="Nadia Rahman",
        class_level="class_8",
        message="Wants Physics",
        batch_id=world.batch_id,
        share_contact=True,
        now=NOW,
    )


def _traces(session: Session, enquiry_id: uuid.UUID) -> tuple[int, int]:
    """Count what remains of a request: its row and its inbox items.

    :param session: An arranging session
    :param enquiry_id: The request
    :return: ``(rows, notifications)``
    """
    session.rollback()
    rows = session.execute(
        sa.text("SELECT count(*) FROM listing_enquiry WHERE id = :e"),
        {"e": enquiry_id},
    ).scalar_one()
    items = session.execute(
        sa.text("SELECT count(*) FROM notification WHERE source_id = :e"),
        {"e": enquiry_id},
    ).scalar_one()
    return int(rows), int(items)


@pytest.mark.usefixtures("enquiries_off")
def test_withdraw_is_total(owner_session: Session, restricted_session: Session) -> None:
    """Review Focus 4: an answered request, withdrawn with the switch off."""
    world = enquirable_owner(owner_session, centre=True)
    caller = guardian(owner_session)
    other = guardian(owner_session, phone="01812345678")
    answered = _send(restricted_session, caller, world)
    untouched = _send(restricted_session, other, world)
    owner.close(restricted_session, world.lens, answered.id, "not_now", NOW)
    kinds = owner_session.execute(
        sa.text(
            "SELECT account_id, kind FROM notification WHERE source_id = :e "
            "ORDER BY kind, account_id"
        ),
        {"e": answered.id},
    ).all()
    assert [(k.account_id, k.kind) for k in kinds] == [
        (caller, HUB_ENQUIRY_ANSWERED),
        *[(m, HUB_ENQUIRY_RECEIVED) for m in world.manager_ids],
    ]

    sending.withdraw(restricted_session, caller, answered.id)

    assert _traces(owner_session, answered.id) == (0, 0)
    assert _traces(owner_session, untouched.id) == (1, len(world.manager_ids))
    assert sending.mine(restricted_session, caller) == []


def test_withdraw_an_open_request_lets_the_guardian_ask_again(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    first = _send(restricted_session, caller, world)

    sending.withdraw(restricted_session, caller, first.id)
    again = _send(restricted_session, caller, world)

    assert _traces(owner_session, first.id) == (0, 0)
    assert _traces(owner_session, again.id) == (1, 1)


def test_withdraw_foreign_or_missing_id_changes_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session, centre=True)
    owner_of_it = guardian(owner_session)
    stranger = guardian(owner_session, phone="01812345678")
    theirs = _send(restricted_session, owner_of_it, world)

    sending.withdraw(restricted_session, stranger, theirs.id)
    sending.withdraw(restricted_session, stranger, uuid.uuid4())
    sending.withdraw(restricted_session, owner_of_it, uuid.uuid4())
    sending.withdraw(restricted_session, world.manager_ids[0], theirs.id)

    assert _traces(owner_session, theirs.id) == (1, len(world.manager_ids))
    assert [e.id for e in sending.mine(restricted_session, owner_of_it)] == [theirs.id]


def test_forget_commits_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    sent = _send(restricted_session, caller, world)

    forget.forget(restricted_session, [])
    forget.forget(restricted_session, [sent.id])
    assert (
        restricted_session.execute(
            sa.text("SELECT count(*) FROM listing_enquiry WHERE id = :e"),
            {"e": sent.id},
        ).scalar_one()
        == 0
    )
    restricted_session.rollback()

    assert _traces(owner_session, sent.id) == (1, 1)


def _close(session: Session, lens: TeacherLens, enquiry_id: uuid.UUID) -> bool:
    """Close a request as its owner, saying whether one was left to close.

    :param session: A restricted session, outside any transaction
    :param lens: The owner's lens
    :param enquiry_id: The request
    :return: True when it closed the request, False when none was left
    """
    try:
        owner.close(session, lens, enquiry_id, "not_now", NOW)
    except AuthorizationError as missing:
        assert missing.code == "ENQUIRY_NOT_FOUND"
        return False
    return True


def _wait_for_waiters(session: Session, count: int) -> None:
    """Block until ``count`` backends wait on a lock, or fail.

    ``pg_locks`` rather than ``pg_stat_activity``, which hides other roles'
    wait events.

    :param session: Any session
    :param count: How many lock waiters to wait for
    :return: None
    :raises AssertionError: Fewer waited within ten seconds
    """
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        waiting = session.execute(
            sa.text("SELECT count(DISTINCT pid) FROM pg_locks WHERE NOT granted")
        ).scalar_one()
        session.rollback()
        if waiting >= count:
            return
        time.sleep(0.05)
    raise AssertionError(f"fewer than {count} transactions waited on a lock")


def _in_thread(
    errors: list[BaseException], work: Callable[[], None]
) -> threading.Thread:
    """Start a thread that records any exception instead of losing it.

    :param errors: Where an exception goes
    :param work: A zero-argument callable
    :return: The started thread
    """

    def run() -> None:
        try:
            work()
        except BaseException as error:  # noqa: BLE001 -- asserted by the test
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


@pytest.mark.parametrize("first", ["close", "withdraw"])
def test_close_and_withdraw_race_without_deadlock(
    owner_session: Session,
    restricted_session: Session,
    restricted_engine: Engine,
    first: str,
) -> None:
    """F7: whichever takes the request row first, neither deadlocks.

    Both lock the request row before touching an inbox item. Were the
    withdrawal to delete the inbox items first, a close holding the row
    would then wait on those items while the withdrawal waited on the row:
    a deadlock, which PostgreSQL ends by failing one of them.

    *Close first*: the close holds the row and is held up on the inbox
    items (by a third session); the withdrawal waits on the row; once
    released, the close commits and the withdrawal then removes
    everything, the answer included. *Withdraw first*: the withdrawal
    holds the row and is held up on the inbox items; the close waits on
    the row; once released, the withdrawal commits and the close finds no
    request. Either way no request and no inbox item remain.
    """
    world = enquirable_owner(owner_session, centre=True)
    caller = guardian(owner_session)
    sent = _send(restricted_session, caller, world)
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    errors: list[BaseException] = []
    closed: list[bool] = []

    def withdraw() -> None:
        with factory() as session:
            sending.withdraw(session, caller, sent.id)

    def close_it() -> None:
        with factory() as session:
            closed.append(_close(session, world.lens, sent.id))

    order = [close_it, withdraw] if first == "close" else [withdraw, close_it]
    # Hold the inbox items, so whichever goes first stops while holding
    # the request row, inside the window a deadlock would need.
    owner_session.execute(
        sa.text("SELECT id FROM notification WHERE source_id = :e FOR UPDATE"),
        {"e": sent.id},
    ).all()
    with factory() as watcher:
        threads = []
        for waiters, work in enumerate(order, start=1):
            threads.append(_in_thread(errors, work))
            _wait_for_waiters(watcher, waiters)
    owner_session.commit()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert closed == [first == "close"]
    assert _traces(owner_session, sent.id) == (0, 0)
