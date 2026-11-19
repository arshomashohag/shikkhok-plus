"""Who may send a join request, and to what [H5 Global Constraints].

**Written before the implementation**: a wrong answer here messages a stranger
or lets an owner's own manager pose as a family. Every target that is not
enquirable answers the one ``ENQUIRY_TARGET_NOT_FOUND`` (404), byte for byte
the answer for a slug that never existed, so a refusal never says which of
its conditions failed (Review Focus 2).

The world is arranged through the table-owner session; every call under test
runs through the restricted application role.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import Owner
from app.errors import AuthorizationError
from app.errors.handler import to_response
from app.hub.enquiries import sending, target
from app.hub.listings.shared import managing_accounts
from tests.enquiries.support import (
    CASES,
    NEVER,
    enquirable_owner,
    guardian,
)
from tests.hub.support import add_member, assign_slot

NOW = dt.datetime(2026, 11, 19, 6, 0, tzinfo=dt.UTC)


def _refusal(call: Callable[[], object]) -> tuple[int, bytes]:
    """Run a call that must refuse, and render its refusal as the wire would.

    :param call: The call
    :return: The response's status and body bytes
    """
    with pytest.raises(AuthorizationError) as refused:
        call()
    response = to_response(refused.value)
    return response.status_code, bytes(response.body)


def _send(
    session: Session, account: uuid.UUID, slug: str, batch_id: uuid.UUID | None
) -> object:
    return sending.send(
        session,
        account,
        slug,
        student_name="Nadia",
        class_level="class_8",
        message=None,
        batch_id=batch_id,
        share_contact=True,
        now=NOW,
    )


def _rows(session: Session, table: str) -> int:
    session.rollback()
    return int(
        session.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608  a fixed table name
    )


@pytest.mark.parametrize("name", list(CASES))
def test_unenquirable_targets_answer_identically(
    owner_session: Session, restricted_session: Session, name: str
) -> None:
    """Review Focus 2: every bad target reads as a slug that never existed."""
    world = enquirable_owner(owner_session)
    slug, batch_id, caller = CASES[name](owner_session, world)
    stranger = guardian(owner_session, phone="01812345678")

    never = _refusal(lambda: target.resolve(restricted_session, stranger, NEVER, None))
    restricted_session.rollback()
    resolved = _refusal(
        lambda: target.resolve(restricted_session, caller, slug, batch_id)
    )
    restricted_session.rollback()
    sent = _refusal(lambda: _send(restricted_session, caller, slug, batch_id))
    described = _refusal(
        lambda: sending.describe(restricted_session, caller, slug, batch_id)
    )
    restricted_session.rollback()

    assert never[0] == 404
    assert resolved == never
    assert sent == never
    assert described == never
    error = target.not_found()
    assert (error.code, error.message_key, error.status) == (
        "ENQUIRY_TARGET_NOT_FOUND",
        "hub.enquiry.target_not_found",
        404,
    )
    assert _rows(owner_session, "listing_enquiry") == 0
    assert _rows(owner_session, "rate_limit_counter") == 0
    assert _rows(owner_session, "notification") == 0


def _statements(session: Session, call: Callable[[], object]) -> list[str]:
    """Record the SQL a refused call executes, in order.

    :param session: The session the call runs through
    :param call: A call that must refuse
    :return: Each statement's text, without its parameters
    """
    executed: list[str] = []

    def record(*args: object) -> None:
        executed.append(str(args[2]))

    engine = session.get_bind()
    sa.event.listen(engine, "before_cursor_execute", record)
    try:
        _refusal(call)
    finally:
        sa.event.remove(engine, "before_cursor_execute", record)
    session.rollback()
    return executed


@pytest.mark.parametrize("name", list(CASES))
def test_every_refusal_runs_the_same_statements(
    owner_session: Session, restricted_session: Session, name: str
) -> None:
    """A registered slug that is not public refuses as a slug never registered.

    Not only the same bytes: the same statements, in the same order, so the
    number of round trips cannot tell them apart [H5 T7 re-review]. The
    send's hold runs and ``resolve`` runs whichever condition failed.
    """
    world = enquirable_owner(owner_session)
    slug, batch_id, caller = CASES[name](owner_session, world)
    stranger = guardian(owner_session, phone="01812345678")

    never = _statements(
        restricted_session, lambda: _send(restricted_session, stranger, NEVER, None)
    )
    refused = _statements(
        restricted_session, lambda: _send(restricted_session, caller, slug, batch_id)
    )

    assert refused == never
    # The key, the account read, the hold and `resolve`.
    assert len(never) == 4


def test_the_same_world_unbroken_is_enquirable(
    owner_session: Session, restricted_session: Session
) -> None:
    """The control for the cases above: each breaks exactly one condition."""
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)

    found = target.resolve(restricted_session, caller, world.owner_slug, world.batch_id)

    assert found == target.Target(
        owner_id=world.lens.owner_id,
        owner_slug=world.owner_slug,
        owner_public_name="Rahim Sir",
        batch_id=world.batch_id,
        batch_title=world.batch_title,
    )


def test_an_owner_request_names_no_batch(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)

    found = target.resolve(
        restricted_session, guardian(owner_session), world.owner_slug, None
    )

    assert (found.batch_id, found.batch_title) == (None, None)
    assert found.owner_id == world.lens.owner_id


def test_waitlist_batch_accepts(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session, admissions="waitlist")

    found = target.resolve(
        restricted_session, guardian(owner_session), world.owner_slug, world.batch_id
    )

    assert found.batch_id == world.batch_id


def test_centre_class_teacher_may_send(
    owner_session: Session, restricted_session: Session
) -> None:
    """A class teacher never reads the inbox, so they may ask like anyone [F8].

    They run the batch for review purposes (``runs_batch_sql``), but join
    requests go only to ``managing_accounts``, and a class teacher is not
    one of those.
    """
    world = enquirable_owner(owner_session, centre=True)
    member, teacher = add_member(owner_session, world.lens.owner_id, role="teacher")
    assign_slot(owner_session, world.batch_id, member)

    found = target.resolve(
        restricted_session, teacher, world.owner_slug, world.batch_id
    )

    assert found.owner_id == world.lens.owner_id


@pytest.mark.parametrize("centre", [False, True], ids=["solo", "centre"])
def test_resolve_refuses_exactly_the_managing_accounts(
    owner_session: Session, restricted_session: Session, centre: bool
) -> None:
    """F8: the SQL predicate and ``managing_accounts`` cannot drift apart.

    Every account with any tie to the owner is tried, plus a stranger; the
    accounts ``resolve`` refuses are exactly the ones ``managing_accounts``
    would deliver the request to.
    """
    world = enquirable_owner(owner_session, centre=centre)
    owner_id = world.lens.owner_id
    candidates = {world.lens.account_id, guardian(owner_session), *world.manager_ids}
    if centre:
        for role, decision, revoked in (
            ("teacher", "accepted", False),
            ("teacher", "pending", False),
            ("manager", "pending", False),
            ("manager", "declined", False),
            ("manager", "accepted", True),
        ):
            member, account = add_member(
                owner_session,
                owner_id,
                role=role,
                decision=decision,
                revoked=revoked,
            )
            if role == "teacher":
                assign_slot(owner_session, world.batch_id, member)
            candidates.add(account)

    refused: set[uuid.UUID] = set()
    for account in candidates:
        for batch_id in (None, world.batch_id):
            try:
                target.resolve(restricted_session, account, world.owner_slug, batch_id)
            except AuthorizationError:
                refused.add(account)
            restricted_session.rollback()

    owner = owner_session.get(Owner, owner_id)
    assert owner is not None
    managing = set(managing_accounts(owner_session, owner))
    assert managing == set(world.manager_ids)
    assert refused == managing
