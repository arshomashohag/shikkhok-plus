"""Withdrawing a join request is total, and never switch-gated (Call 12).

**Written before the implementation** (Review Focus 4). After a withdrawal
nothing of the request remains: not the row, not the owners'
``hub_enquiry_received`` items and not the guardian's
``hub_enquiry_answered`` item. Withdrawing someone else's request, or one
that does not exist, changes nothing and is not an error.

A withdrawal and the owner's close lock the request row first, in that
order, so the two never deadlock [F7]. The owner's close is Task 4's; until
it exists the race runs against :func:`_close_shaped`, a transaction that
does what the close is specified to do. Task 4 switches the race to
``app.hub.enquiries.owner.close``.
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

from app.hub.enquiries import forget, sending
from app.notifications.inbox import (
    HUB_ENQUIRY_ANSWERED,
    HUB_ENQUIRY_RECEIVED,
    deliver,
    mark_read_for_source,
)
from tests.enquiries.support import EnquirableWorld, close, enquirable_owner, guardian

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


def _answer(
    session: Session, enquiry: sending.MyEnquiry, enquirer: uuid.UUID, outcome: str
) -> None:
    """Close a request and tell its guardian, as the owner's close will.

    :param session: An arranging session
    :param enquiry: The request
    :param enquirer: The guardian who sent it
    :param outcome: The closing outcome
    :return: None
    """
    close(session, enquiry.id, outcome, NOW)
    deliver(
        session,
        account_ids=[enquirer],
        kind=HUB_ENQUIRY_ANSWERED,
        batch_name=enquiry.batch_title or enquiry.owner_public_name or "",
        now=NOW,
        source_id=enquiry.id,
        preview=outcome,
    )
    mark_read_for_source(session, kind=HUB_ENQUIRY_RECEIVED, source_id=enquiry.id)
    session.commit()


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
    _answer(owner_session, answered, caller, "not_now")
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


def _close_shaped(session: Session, enquiry_id: uuid.UUID) -> bool:
    """Do what the owner's close does, in its order [F7; Task 4 ``close``].

    Lock the request, close it, tell its guardian and mark every manager's
    copy read. Task 4 replaces this with ``app.hub.enquiries.owner.close``.

    :param session: A restricted session, outside any transaction
    :param enquiry_id: The request
    :return: True when it closed the request, False when none was left
    """
    row = session.execute(
        sa.text(
            "SELECT enquirer_account_id FROM listing_enquiry WHERE id = :e FOR UPDATE"
        ),
        {"e": enquiry_id},
    ).one_or_none()
    if row is None:
        session.rollback()
        return False
    return _finish_close(session, enquiry_id, row.enquirer_account_id)


def _finish_close(session: Session, enquiry_id: uuid.UUID, enquirer: uuid.UUID) -> bool:
    """Close a request whose row this session already holds locked.

    :param session: The session holding the row lock
    :param enquiry_id: The request
    :param enquirer: Its guardian
    :return: True
    """
    session.execute(
        sa.text(
            "UPDATE listing_enquiry SET status = 'closed', outcome = 'not_now', "
            "closed_at = :t WHERE id = :e"
        ),
        {"t": NOW, "e": enquiry_id},
    )
    deliver(
        session,
        account_ids=[enquirer],
        kind=HUB_ENQUIRY_ANSWERED,
        batch_name="HSC Physics",
        now=NOW,
        source_id=enquiry_id,
        preview="not_now",
    )
    mark_read_for_source(
        session, kind=HUB_ENQUIRY_RECEIVED, source_id=enquiry_id, now=NOW
    )
    session.commit()
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

    *Close first*: the close holds the row; the withdrawal waits; the close
    finishes and commits; the withdrawal then removes everything, the
    answer included. *Withdraw first*: the withdrawal holds the row and is
    held up on the inbox items (by a third session); the close waits on
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

    if first == "close":
        with factory() as closer:
            enquirer = closer.execute(
                sa.text(
                    "SELECT enquirer_account_id FROM listing_enquiry "
                    "WHERE id = :e FOR UPDATE"
                ),
                {"e": sent.id},
            ).scalar_one()
            withdrawing = _in_thread(errors, withdraw)
            _wait_for_waiters(owner_session, 1)
            closed.append(_finish_close(closer, sent.id, enquirer))
        withdrawing.join(timeout=30)
    else:
        owner_session.execute(
            sa.text("SELECT id FROM notification WHERE source_id = :e FOR UPDATE"),
            {"e": sent.id},
        ).all()
        with factory() as watcher:
            withdrawing = _in_thread(errors, withdraw)
            _wait_for_waiters(watcher, 1)

            def close_it() -> None:
                with factory() as session:
                    closed.append(_close_shaped(session, sent.id))

            closing = _in_thread(errors, close_it)
            _wait_for_waiters(watcher, 2)
        owner_session.commit()
        withdrawing.join(timeout=30)
        closing.join(timeout=30)

    assert errors == []
    assert closed == [first == "close"]
    assert _traces(owner_session, sent.id) == (0, 0)
