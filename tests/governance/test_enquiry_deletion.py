"""Join requests go totally with either party (Call 12; Review Focus 4).

**A guardian's deletion forgets every request they sent**, and **a solo
owner's deletion forgets every request they received**: the row, the owners'
``hub_enquiry_received`` items and the guardian's ``hub_enquiry_answered``
item, whoever they were addressed to. The ``owner`` row is retained, so its
``ON DELETE CASCADE`` never fires; the solo owner's requests are collected
explicitly, in the transaction that deletes the listing.

**A coaching centre's requests outlive a manager**: they belong to the
centre, and its other managers still answer them.

The deletion runs as the application role, and the switch never gates it.
Two accounts deleted at once, each holding a request of the other's, lock
the requests in one statement in id order, so neither waits on the other in
a cycle and neither needs the deadlock retry.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.authz.lenses import TeacherLens
from app.errors import AuthorizationError
from app.governance.deletion import delete_account
from app.hub.enquiries import owner, sending
from app.notifications.inbox import HUB_ENQUIRY_ANSWERED, HUB_ENQUIRY_RECEIVED
from tests.enquiries.support import EnquirableWorld, enquirable_owner, guardian

NOW = dt.datetime(2026, 11, 19, 4, 0, tzinfo=dt.UTC)


def _send(
    session: Session, account: uuid.UUID, world: EnquirableWorld
) -> sending.MyEnquiry:
    """Send a request about the world's batch, sharing contact.

    :param session: A restricted session
    :param account: The sender
    :param world: The owner asked
    :return: The request as its sender sees it
    """
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


def _phone(session: Session, account_id: uuid.UUID) -> str:
    """Read an account's number.

    :param session: An arranging session
    :param account_id: The account
    :return: Its phone number
    """
    return str(
        session.execute(
            sa.text("SELECT phone FROM account WHERE id = :a"), {"a": account_id}
        ).scalar_one()
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


def _listings(session: Session, owner_id: uuid.UUID) -> int:
    """Count an owner's listings.

    :param session: An arranging session
    :param owner_id: The owner
    :return: 0 or 1
    """
    session.rollback()
    return int(
        session.execute(
            sa.text("SELECT count(*) FROM owner_listing WHERE owner_id = :o"),
            {"o": owner_id},
        ).scalar_one()
    )


def test_guardian_deletion_removes_their_enquiries_and_owner_inbox_items(
    owner_session: Session, restricted_session: Session
) -> None:
    centre = enquirable_owner(owner_session, centre=True)
    solo = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    other = guardian(owner_session, phone="01812345678")
    answered = _send(restricted_session, caller, centre)
    owner.close(restricted_session, centre.lens, answered.id, "not_now", NOW)
    pending = _send(restricted_session, caller, solo)
    kept = _send(restricted_session, other, centre)

    result = delete_account(restricted_session, _phone(owner_session, caller))

    assert result.rows_deleted["listing_enquiry"] == 2
    assert _traces(owner_session, answered.id) == (0, 0)
    assert _traces(owner_session, pending.id) == (0, 0)
    # Another guardian's request, and the managers' items about it, stay.
    assert _traces(owner_session, kept.id) == (1, len(centre.manager_ids))
    assert [e.id for e in owner.list_for(restricted_session, centre.lens)] == [kept.id]
    assert owner.list_for(restricted_session, solo.lens) == []


def test_solo_owner_deletion_removes_received_enquiries_and_guardian_inbox_items(
    owner_session: Session, restricted_session: Session
) -> None:
    solo = enquirable_owner(owner_session)
    elsewhere = enquirable_owner(owner_session)
    first = guardian(owner_session)
    second = guardian(owner_session, phone="01812345678")
    answered = _send(restricted_session, first, solo)
    owner.close(restricted_session, solo.lens, answered.id, "not_now", NOW)
    pending = _send(restricted_session, second, solo)
    # The solo owner also asked another owner, as a guardian would.
    asked = _send(restricted_session, solo.lens.account_id, elsewhere)
    kept = _send(restricted_session, first, elsewhere)

    result = delete_account(
        restricted_session, _phone(owner_session, solo.lens.account_id)
    )

    assert result.rows_deleted["listing_enquiry"] == 3
    assert result.rows_deleted["owner_listing"] == 1
    for gone in (answered, pending, asked):
        assert _traces(owner_session, gone.id) == (0, 0)
    assert _traces(owner_session, kept.id) == (1, 1)
    assert _listings(owner_session, solo.lens.owner_id) == 0
    # The guardians see nothing of the deleted owner, not even a request
    # with no owner name left on it.
    assert [e.id for e in sending.mine(restricted_session, first)] == [kept.id]
    assert sending.mine(restricted_session, second) == []
    assert [e.id for e in owner.list_for(restricted_session, elsewhere.lens)] == [
        kept.id
    ]


def test_centre_enquiries_survive_manager_deletion(
    owner_session: Session, restricted_session: Session
) -> None:
    centre = enquirable_owner(owner_session, centre=True)
    caller = guardian(owner_session)
    sent = _send(restricted_session, caller, centre)
    leaving = centre.lens.account_id
    (staying,) = [m for m in centre.manager_ids if m != leaving]

    result = delete_account(restricted_session, _phone(owner_session, leaving))

    assert result.rows_deleted["listing_enquiry"] == 0
    # The leaving manager's own item went with their inbox; the other's stays.
    assert _traces(owner_session, sent.id) == (1, 1)
    remaining = owner_session.execute(
        sa.text("SELECT account_id FROM notification WHERE source_id = :e"),
        {"e": sent.id},
    ).scalar_one()
    assert remaining == staying
    lens = TeacherLens(account_id=staying, owner_id=centre.lens.owner_id)
    assert [e.id for e in owner.list_for(restricted_session, lens)] == [sent.id]
    assert [e.id for e in sending.mine(restricted_session, caller)] == [sent.id]


@pytest.mark.usefixtures("enquiries_off")
@pytest.mark.parametrize("who", ["guardian", "solo_owner"])
def test_deletion_works_with_switch_off(
    owner_session: Session, restricted_session: Session, who: str
) -> None:
    """The switch never gates a deletion (Global Constraints)."""
    solo = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    sent = _send(restricted_session, caller, solo)
    owner.close(restricted_session, solo.lens, sent.id, "not_now", NOW)
    leaving = caller if who == "guardian" else solo.lens.account_id

    result = delete_account(restricted_session, _phone(owner_session, leaving))

    assert result.rows_deleted["listing_enquiry"] == 1
    assert _traces(owner_session, sent.id) == (0, 0)


@pytest.mark.parametrize("who", ["guardian", "solo_owner"])
def test_external_deletion_path_also_forgets(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    outbound: list[tuple[str, str]],
    who: str,
) -> None:
    """The ``/account-deletion`` route reaches the same deletion [BR3.1]."""
    solo = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    sent = _send(restricted_session, caller, solo)
    owner.close(restricted_session, solo.lens, sent.id, "not_now", NOW)
    phone = _phone(owner_session, caller if who == "guardian" else solo.lens.account_id)
    owner_session.rollback()

    asked = api_client.post("/account-deletion", json={"phone": phone})
    assert asked.status_code == 200, asked.text
    body = next(text for to, text in reversed(outbound) if to == phone)
    code = next(part for part in body.split() if part.isdigit() and len(part) == 6)
    deleted = api_client.post("/account-deletion", json={"phone": phone, "code": code})

    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["status"] == "deleted"
    assert _traces(owner_session, sent.id) == (0, 0)


#: Whether a backend waits on a row of one table: it holds or awaits that
#: row's tuple lock while some lock of its own is not granted.
_WAITING_ON_ROW = sa.text(
    """
    SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid = :pid AND NOT granted)
       AND EXISTS (SELECT 1 FROM pg_locks
                   WHERE pid = :pid AND locktype = 'tuple'
                     AND relation = CAST(:relation AS regclass))
    """
)

#: Whether a backend waits on an advisory key.
_WAITING_ON_KEY = sa.text(
    "SELECT EXISTS (SELECT 1 FROM pg_locks "
    "WHERE pid = :pid AND locktype = 'advisory' AND NOT granted)"
)

#: Where a racer is expected to stop: a table name, or :data:`ADVISORY`.
ADVISORY = "advisory"


@dataclass(frozen=True, slots=True)
class _Racer:
    """One transaction in a race.

    :ivar work: Runs the transaction on a fresh restricted session
    :ivar waits_on: The table whose row it should wait on, or
        :data:`ADVISORY` for an account key
    """

    work: Callable[[Session], None]
    waits_on: str


def _wait_for_waiter(
    session: Session,
    pids: dict[int, int],
    index: int,
    thread: threading.Thread,
    waits_on: str,
) -> bool:
    """Block until one racer waits where expected, or has finished.

    Filtered to that racer's own backend and to the table (or advisory key)
    it should wait on, so no other lock waiter in the database can release
    the next racer early. ``pg_locks`` rather than ``pg_stat_activity``,
    which hides other roles' wait events.

    :param session: A watching session
    :param pids: Each racer's backend pid, by index, once it has one
    :param index: The racer
    :param thread: Its thread
    :param waits_on: A table name, or :data:`ADVISORY`
    :return: True when it waited there; False when it finished, or never
        waited there within ten seconds
    """
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and thread.is_alive():
        pid = pids.get(index)
        if pid is not None:
            if waits_on == ADVISORY:
                waiting = session.execute(_WAITING_ON_KEY, {"pid": pid})
            else:
                waiting = session.execute(
                    _WAITING_ON_ROW, {"pid": pid, "relation": waits_on}
                )
            found = bool(waiting.scalar_one())
            session.rollback()
            if found:
                return True
        time.sleep(0.05)
    return False


def _race(
    owner_session: Session,
    engine: Engine,
    hold: tuple[str, dict[str, object]],
    racers: list[_Racer],
) -> tuple[list[BaseException], list[bool]]:
    """Run racers in order against a row lock a third session holds.

    The owner session locks ``hold``; each racer starts only once the one
    before it waits where expected; then the hold is released and every
    racer runs to its end. Each racer records its backend pid in its own
    transaction first, so the watcher can tell which backend is which.

    :param owner_session: Holds the lock
    :param engine: The restricted engine the racers use
    :param hold: The locking statement and its parameters
    :param racers: The racers, in start order
    :return: The racers' exceptions, and whether each waited as expected
    """
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    errors: list[BaseException] = []
    pids: dict[int, int] = {}
    waited: list[bool] = []
    threads: list[threading.Thread] = []

    def runner(index: int, racer: _Racer) -> Callable[[], None]:
        def work() -> None:
            with factory() as session:
                pids[index] = int(
                    session.execute(sa.text("SELECT pg_backend_pid()")).scalar_one()
                )
                racer.work(session)

        return work

    owner_session.execute(sa.text(hold[0]), hold[1]).all()
    try:
        with factory() as watcher:
            for index, racer in enumerate(racers):
                threads.append(_in_thread(errors, runner(index, racer)))
                waited.append(
                    _wait_for_waiter(watcher, pids, index, threads[-1], racer.waits_on)
                )
    finally:
        owner_session.commit()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()
    return errors, waited


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


def _nothing_left(session: Session) -> tuple[int, int]:
    """Count every request and every join-request inbox item left.

    :param session: An arranging session
    :return: ``(rows, notifications)``
    """
    session.rollback()
    rows = session.execute(sa.text("SELECT count(*) FROM listing_enquiry"))
    count = int(rows.scalar_one())
    items = session.execute(
        sa.text("SELECT count(*) FROM notification WHERE kind = ANY(:k)"),
        {"k": [HUB_ENQUIRY_RECEIVED, HUB_ENQUIRY_ANSWERED]},
    )
    return count, int(items.scalar_one())


def _refusal(error: BaseException) -> tuple[str, str, int]:
    """Read what a refusal would put on the wire.

    :param error: The racer's exception
    :return: ``(code, message_key, status)``
    """
    assert isinstance(error, AuthorizationError), repr(error)
    return error.code, error.message_key, error.status


def test_mutual_deletion_cannot_deadlock(
    owner_session: Session,
    restricted_session: Session,
    restricted_engine: Engine,
) -> None:
    """H4 T10-a: two solo owners, each holding the other's request, leave at once.

    Each deletion collects both requests: the one it sent and the one it
    received. Were the two kinds locked by separate statements, each
    deletion would lock its own sent request first and then wait on the
    other's: a cycle, which PostgreSQL ends by failing one side with
    ``40P01``. A third session holds the lower-id request, and the deletion
    that SENT it starts first, so it waits holding nothing; the other then
    starts. Sent-first locking would have the second take its own request
    and wait on the held one, and on release the two would wait on each
    other. Locked in one statement in id order, both queue on the same
    first row: one finishes, and the other then finds nothing left to lock.
    ``delete_account`` is called directly, outside the routes' retry, so a
    deadlock would surface here as an error.
    """
    a = enquirable_owner(owner_session)
    b = enquirable_owner(owner_session)
    a_asked_b = _send(restricted_session, a.lens.account_id, b)
    b_asked_a = _send(restricted_session, b.lens.account_id, a)
    owner.close(restricted_session, a.lens, b_asked_a.id, "not_now", NOW)
    # The sender of the held, lower-id request is deleted first.
    first, second = (a, b) if a_asked_b.id < b_asked_a.id else (b, a)
    phones = [_phone(owner_session, w.lens.account_id) for w in (first, second)]
    owner_session.rollback()

    def delete(phone: str) -> _Racer:
        return _Racer(lambda s: delete_account(s, phone).existed, "listing_enquiry")

    errors, waited = _race(
        owner_session,
        restricted_engine,
        (
            "SELECT id FROM listing_enquiry WHERE id = :e FOR UPDATE",
            {"e": min(a_asked_b.id, b_asked_a.id)},
        ),
        [delete(phone) for phone in phones],
    )

    assert errors == []
    assert waited == [True, True]
    for gone in (a_asked_b, b_asked_a):
        assert _traces(owner_session, gone.id) == (0, 0)
    assert (
        owner_session.execute(
            sa.text("SELECT count(*) FROM account WHERE id = ANY(:ids)"),
            {"ids": [a.lens.account_id, b.lens.account_id]},
        ).scalar_one()
        == 0
    )


@pytest.mark.parametrize("first", ["send", "deletion"])
def test_send_racing_solo_owner_deletion_leaves_nothing(
    owner_session: Session,
    restricted_session: Session,
    restricted_engine: Engine,
    first: str,
) -> None:
    """A request sent while its solo owner is deleted never outlives them.

    The ``owner`` row is retained, so a send's foreign key never notices the
    deletion; ``owner_listing`` is the row that goes. The send holds it
    ``FOR SHARE`` from before it decides until it commits, and the deletion
    locks it ``FOR UPDATE`` before collecting the owner's requests.

    *Send first*: the send holds the listing and is held up on its batch
    listing (by a third session); the deletion waits on the listing; once
    released, the send commits and the deletion then collects and forgets
    the new request. *Deletion first*: the deletion holds the listing and
    is held up on another request; the send waits on the listing; once
    released, the deletion commits and the send finds the listing gone and
    answers exactly what any unknown target answers.
    """
    solo = enquirable_owner(owner_session)
    sender = guardian(owner_session)
    phone = _phone(owner_session, solo.lens.account_id)
    sent: list[sending.MyEnquiry] = []
    send = _Racer(lambda s: sent.append(_send(s, sender, solo)), "owner_listing")
    delete = _Racer(lambda s: delete_account(s, phone).existed, "owner_listing")
    if first == "send":
        hold = (
            "SELECT 1 FROM batch_listing WHERE batch_id = :k FOR UPDATE",
            {"k": solo.batch_id},
        )
        racers = [_Racer(send.work, "batch_listing"), delete]
    else:
        other = guardian(owner_session, phone="01812345678")
        held = _send(restricted_session, other, solo)
        hold = (
            "SELECT 1 FROM listing_enquiry WHERE id = :k FOR UPDATE",
            {"k": held.id},
        )
        racers = [_Racer(delete.work, "listing_enquiry"), send]

    errors, waited = _race(owner_session, restricted_engine, hold, racers)

    if first == "send":
        assert errors == []
        assert len(sent) == 1
    else:
        assert [_refusal(e) for e in errors] == [
            ("ENQUIRY_TARGET_NOT_FOUND", "hub.enquiry.target_not_found", 404)
        ]
        assert sent == []
    assert _nothing_left(owner_session) == (0, 0)
    assert _listings(owner_session, solo.lens.owner_id) == 0
    assert waited == [True, True]


@pytest.mark.parametrize("first", ["send", "deletion"])
def test_send_racing_the_senders_own_deletion_leaves_nothing(
    owner_session: Session,
    restricted_session: Session,
    restricted_engine: Engine,
    first: str,
) -> None:
    """A guardian's send from a second device never outlives their deletion.

    The send takes the account's advisory key, the deletion's first lock,
    before it decides, so the two serialise. *Send first*: the send holds
    the key and is held up on its batch listing; the deletion waits on the
    key; once released, the send commits and the deletion then forgets the
    request and the owner's item about it. *Deletion first*: the deletion
    holds the key and is held up on an earlier request; the send waits on
    the key; once released, the deletion commits and the send finds no
    account, answering the 401 a deleted account's token gets anyway.
    """
    solo = enquirable_owner(owner_session)
    sender = guardian(owner_session)
    phone = _phone(owner_session, sender)
    sent: list[sending.MyEnquiry] = []
    send = _Racer(lambda s: sent.append(_send(s, sender, solo)), ADVISORY)
    delete = _Racer(lambda s: delete_account(s, phone).existed, ADVISORY)
    if first == "send":
        hold = (
            "SELECT 1 FROM batch_listing WHERE batch_id = :k FOR UPDATE",
            {"k": solo.batch_id},
        )
        racers = [_Racer(send.work, "batch_listing"), delete]
    else:
        earlier = _send(restricted_session, sender, enquirable_owner(owner_session))
        hold = (
            "SELECT 1 FROM listing_enquiry WHERE id = :k FOR UPDATE",
            {"k": earlier.id},
        )
        racers = [_Racer(delete.work, "listing_enquiry"), send]

    errors, waited = _race(owner_session, restricted_engine, hold, racers)

    if first == "send":
        assert errors == []
        assert len(sent) == 1
    else:
        assert [_refusal(e) for e in errors] == [
            ("NOT_AUTHENTICATED", "auth.token.not_valid", 401)
        ]
        assert sent == []
    assert _nothing_left(owner_session) == (0, 0)
    owner_session.rollback()
    assert (
        owner_session.execute(
            sa.text("SELECT count(*) FROM account WHERE id = :a"), {"a": sender}
        ).scalar_one()
        == 0
    )
    assert waited == [True, True]
