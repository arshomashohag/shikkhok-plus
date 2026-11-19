"""The owner's side of a join request: list, read one and close it.

**Written before the implementation.** Owner scoping and the contact
predicate are authorization predicates: a wrong answer shows one teacher
another teacher's requests, or hands an owner a number its guardian did not
agree to share. The ``call_us`` rule [F11] is one too, in the other
direction: a family told to call a number they cannot see.

The world is arranged through the table-owner session; every call under
test runs through the restricted application role.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import itertools
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.errors import (
    AuthorizationError,
    ConflictError,
    TaxonomyError,
    ValidationError,
)
from app.errors.handler import to_response
from app.hub.enquiries import owner, sending
from app.notifications.inbox import HUB_ENQUIRY_ANSWERED, HUB_ENQUIRY_RECEIVED
from tests.enquiries.support import EnquirableWorld, enquirable_owner, guardian

#: A morning in Dhaka; every send uses it.
NOW = dt.datetime(2026, 11, 19, 4, 0, tzinfo=dt.UTC)

#: When the owner answers.
LATER = NOW + dt.timedelta(hours=3)

#: The owner's published number, for ``call_us``.
PUBLIC_PHONE = "+8801911223344"

#: Every outcome, in the enum's order.
OUTCOMES = ("added", "not_now", "call_us")

_numbers = itertools.count(1)


def _phone() -> str:
    """Return a typed mobile number no other test account holds.

    :return: An eleven-digit Bangladeshi mobile number
    """
    return f"0171{next(_numbers) + 5_000_000:07d}"


def _send(
    session: Session,
    account: uuid.UUID,
    world: EnquirableWorld,
    *,
    share_contact: bool = True,
    batch: bool = True,
    student_name: str = "Nadia Rahman",
    now: dt.datetime = NOW,
) -> uuid.UUID:
    """Send a request as a guardian and return its id.

    :param session: The restricted session
    :param account: The guardian
    :param world: The owner asked
    :param share_contact: Whether the guardian shares their contact
    :param batch: Whether the request names the world's batch
    :param student_name: The student's name
    :param now: When it is sent
    :return: The request id
    """
    return sending.send(
        session,
        account,
        world.owner_slug,
        student_name=student_name,
        class_level="class_8",
        message="Wants Physics",
        batch_id=world.batch_id if batch else None,
        share_contact=share_contact,
        now=now,
    ).id


def _publish_phone(session: Session, world: EnquirableWorld) -> None:
    """Give the owner's listing a public contact number.

    :param session: An arranging session
    :param world: The owner
    :return: None
    """
    session.execute(
        sa.text(
            "UPDATE owner_listing SET public_contact_phone = :p WHERE owner_id = :o"
        ),
        {"p": PUBLIC_PHONE, "o": world.lens.owner_id},
    )
    session.commit()


def _listing_status(session: Session, world: EnquirableWorld, status: str) -> None:
    """Move the owner's listing to another status.

    :param session: An arranging session
    :param world: The owner
    :param status: ``published``, ``hidden`` or ``suspended``
    :return: None
    """
    session.execute(
        sa.text(
            "UPDATE owner_listing SET status = CAST(:s AS hub_listing_status) "
            "WHERE owner_id = :o"
        ),
        {"s": status, "o": world.lens.owner_id},
    )
    session.commit()


def _refusal(error: TaxonomyError) -> tuple[int, bytes]:
    """Render a refusal as the client receives it.

    :param error: The raised error
    :return: ``(status, body bytes)``
    """
    response = to_response(error)
    return response.status_code, bytes(response.body)


def _row(session: Session, enquiry_id: uuid.UUID) -> sa.Row[tuple[object, ...]]:
    """Read a request's stored state.

    :param session: An arranging session
    :param enquiry_id: The request
    :return: Its row
    """
    session.rollback()
    return session.execute(
        sa.text("SELECT status, outcome, closed_at FROM listing_enquiry WHERE id = :e"),
        {"e": enquiry_id},
    ).one()


def _items(session: Session, enquiry_id: uuid.UUID) -> list[sa.Row[tuple[object, ...]]]:
    """Read every inbox item about a request.

    :param session: An arranging session
    :param enquiry_id: The request
    :return: Rows ordered by kind then account
    """
    session.rollback()
    return list(
        session.execute(
            sa.text(
                "SELECT account_id, kind, batch_name, preview, read_at "
                "FROM notification WHERE source_id = :e ORDER BY kind, account_id"
            ),
            {"e": enquiry_id},
        )
    )


# --------------------------------------------------------- contact predicate

CONTACTS = [
    pytest.param(
        "01712345678",
        "mother@example.com",
        False,
        None,
        None,
        id="phone-and-email-not-shared",
    ),
    pytest.param(
        "01712345678",
        "mother@example.com",
        True,
        "+8801712345678",
        None,
        id="phone-and-email-shared-gives-the-phone",
    ),
    pytest.param(
        None,
        "mother@example.com",
        True,
        None,
        "mother@example.com",
        id="email-only-shared-gives-the-email",
    ),
]


@pytest.mark.parametrize(
    ("phone", "email", "share", "shown_phone", "shown_email"), CONTACTS
)
def test_contact_shared_only_with_consent(
    owner_session: Session,
    restricted_session: Session,
    phone: str | None,
    email: str | None,
    share: bool,
    shown_phone: str | None,
    shown_email: str | None,
) -> None:
    """Review Focus 1: the owner sees the contact only when it was shared.

    The phone when the account has one, else the email; neither without
    consent. Asserted on the list and on one request, and no inbox item
    of either party ever carries it.
    """
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session, phone=phone, email=email)
    sent = _send(restricted_session, caller, world, share_contact=share)

    (listed,) = owner.list_for(restricted_session, world.lens)
    one = owner.get(restricted_session, world.lens, sent)

    for seen in (listed, one):
        assert seen.id == sent
        assert (seen.guardian_phone, seen.guardian_email) == (shown_phone, shown_email)
    assert listed == one

    owner.close(restricted_session, world.lens, sent, "not_now", LATER)

    stored = owner_session.execute(
        sa.text(
            "SELECT row_to_json(n)::text AS item FROM notification n "
            "WHERE source_id = :e"
        ),
        {"e": sent},
    ).scalars()
    items = list(stored)
    assert len(items) == 2  # the manager's received item and the answer
    for item in items:
        for contact in ("1712345678", "mother@example.com"):
            assert contact not in item
    previews = owner_session.execute(
        sa.text("SELECT kind, preview FROM notification WHERE source_id = :e"),
        {"e": sent},
    ).all()
    assert {(p.kind, p.preview) for p in previews} == {
        (HUB_ENQUIRY_RECEIVED, None),
        (HUB_ENQUIRY_ANSWERED, "not_now"),
    }


def test_owner_enquiry_carries_no_account_id() -> None:
    """Never in any enquiry response: an account id of anyone."""
    names = {f.name for f in dataclasses.fields(owner.OwnerEnquiry)}
    assert names == {
        "id",
        "batch_id",
        "batch_title",
        "student_name",
        "class_level",
        "message",
        "status",
        "outcome",
        "received_at",
        "guardian_phone",
        "guardian_email",
        "outcomes_allowed",
    }


def test_contact_is_read_live(
    owner_session: Session, restricted_session: Session
) -> None:
    """The contact is never copied into the request (Call 4)."""
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session, phone="01712345678")
    sent = _send(restricted_session, caller, world)
    assert owner.get(restricted_session, world.lens, sent).guardian_phone == (
        "+8801712345678"
    )

    owner_session.execute(
        sa.text("UPDATE account SET phone = '+8801812345678' WHERE id = :a"),
        {"a": caller},
    )
    owner_session.commit()

    restricted_session.rollback()
    assert owner.get(restricted_session, world.lens, sent).guardian_phone == (
        "+8801812345678"
    )
    (listed,) = owner.list_for(restricted_session, world.lens)
    assert listed.guardian_phone == "+8801812345678"


# ------------------------------------------------------------- owner scoping


def test_other_owner_cannot_list_read_or_close(
    owner_session: Session, restricted_session: Session
) -> None:
    """Teacher B learns nothing about teacher A's request, and changes nothing.

    B's read and close of A's id answer the same status and bytes as an id
    that never existed.
    """
    first = enquirable_owner(owner_session)
    second = enquirable_owner(owner_session, centre=True)
    _publish_phone(owner_session, first)
    _publish_phone(owner_session, second)
    theirs = _send(restricted_session, guardian(owner_session, phone=_phone()), first)
    own = _send(restricted_session, guardian(owner_session, phone=_phone()), second)
    never = uuid.uuid4()

    assert [e.id for e in owner.list_for(restricted_session, second.lens)] == [own]
    assert [e.id for e in owner.list_for(restricted_session, first.lens)] == [theirs]

    def attempts(target: uuid.UUID) -> list[TaxonomyError]:
        refusals: list[TaxonomyError] = []
        with pytest.raises(AuthorizationError) as refused:
            owner.get(restricted_session, second.lens, target)
        refusals.append(refused.value)
        for outcome in OUTCOMES:
            with pytest.raises(AuthorizationError) as refused:
                owner.close(restricted_session, second.lens, target, outcome, LATER)
            refusals.append(refused.value)
        return refusals

    refusals = attempts(theirs) + attempts(never)
    assert len(refusals) == 8
    for refusal in refusals:
        assert (refusal.code, refusal.message_key) == (
            "ENQUIRY_NOT_FOUND",
            "hub.enquiry.not_found",
        )
    answers = {_refusal(r) for r in refusals}
    assert len(answers) == 1
    ((status, _),) = answers
    assert status == 404
    row = _row(owner_session, theirs)
    assert (row.status, row.outcome, row.closed_at) == ("open", None, None)
    assert [i.kind for i in _items(owner_session, theirs)] == [HUB_ENQUIRY_RECEIVED]


def test_centre_managers_share_one_inbox(
    owner_session: Session, restricted_session: Session
) -> None:
    """Both of a centre's managers see, read and may close the one request."""
    world = enquirable_owner(owner_session, centre=True)
    sent = _send(restricted_session, guardian(owner_session), world)
    lenses = [
        TeacherLens(account_id=manager, owner_id=world.lens.owner_id)
        for manager in world.manager_ids
    ]
    assert len(lenses) == 2

    for lens in lenses:
        assert [e.id for e in owner.list_for(restricted_session, lens)] == [sent]
        assert owner.get(restricted_session, lens, sent).status == "open"

    other = next(lens for lens in lenses if lens.account_id != world.lens.account_id)
    closed = owner.close(restricted_session, other, sent, "not_now", LATER)

    assert closed.status == "closed"
    for lens in lenses:
        assert owner.get(restricted_session, lens, sent).outcome == "not_now"


def test_list_for_puts_open_first_then_newest_and_returns_at_most_100(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    for minute in range(101):
        owner_session.execute(
            sa.text(
                "INSERT INTO listing_enquiry (owner_id, enquirer_account_id, "
                "student_name, class_level, share_contact, status, outcome, "
                "created_at, closed_at) VALUES (:o, :a, :n, 'class_8', false, "
                "'closed', 'not_now', :t, :t)"
            ),
            {
                "o": world.lens.owner_id,
                "a": caller,
                "n": f"Closed {minute}",
                "t": NOW + dt.timedelta(minutes=minute),
            },
        )
    owner_session.commit()
    old_open = _send(
        restricted_session,
        guardian(owner_session, phone=_phone()),
        world,
        student_name="Open early",
        now=NOW - dt.timedelta(days=30),
    )

    listed = owner.list_for(restricted_session, world.lens)

    assert len(listed) == owner.LIST_LIMIT == 100
    assert listed[0].id == old_open
    assert listed[0].status == "open"
    assert [e.student_name for e in listed[1:3]] == ["Closed 100", "Closed 99"]
    assert listed[-1].student_name == "Closed 2"
    assert listed[1].received_at == NOW + dt.timedelta(minutes=100)


def test_get_describes_the_request(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    with_batch = _send(restricted_session, caller, world, share_contact=False)
    owner.close(restricted_session, world.lens, with_batch, "not_now", LATER)
    without = _send(restricted_session, caller, world, batch=False)

    assert owner.get(restricted_session, world.lens, with_batch) == owner.OwnerEnquiry(
        id=with_batch,
        batch_id=world.batch_id,
        batch_title=world.batch_title,
        student_name="Nadia Rahman",
        class_level="class_8",
        message="Wants Physics",
        status="closed",
        outcome="not_now",
        received_at=NOW,
        guardian_phone=None,
        guardian_email=None,
        outcomes_allowed=[],
    )
    open_one = owner.get(restricted_session, world.lens, without)
    assert (open_one.batch_id, open_one.batch_title) == (None, None)
    assert open_one.outcomes_allowed == ["added", "not_now"]


# ------------------------------------------------------------------- closing


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_close_outcomes(
    owner_session: Session, restricted_session: Session, outcome: str
) -> None:
    """Each outcome closes the request, answers the guardian, settles the inbox.

    The guardian's ``hub_enquiry_answered`` carries the outcome code as its
    preview and nothing else; every manager's received item is marked read.
    """
    world = enquirable_owner(owner_session, centre=True)
    _publish_phone(owner_session, world)
    caller = guardian(owner_session)
    sent = _send(restricted_session, caller, world)

    closed = owner.close(restricted_session, world.lens, sent, outcome, LATER)

    assert (closed.id, closed.status, closed.outcome) == (sent, "closed", outcome)
    assert closed.outcomes_allowed == []
    row = _row(owner_session, sent)
    assert (row.status, row.outcome, row.closed_at) == ("closed", outcome, LATER)
    items = _items(owner_session, sent)
    answered = [i for i in items if i.kind == HUB_ENQUIRY_ANSWERED]
    received = [i for i in items if i.kind == HUB_ENQUIRY_RECEIVED]
    assert [(i.account_id, i.preview, i.batch_name) for i in answered] == [
        (caller, outcome, world.batch_title)
    ]
    assert answered[0].read_at is None
    assert [i.account_id for i in received] == world.manager_ids
    assert all(i.read_at == LATER for i in received)
    assert sending.mine(restricted_session, caller)[0].outcome == outcome


def test_answer_without_a_batch_names_the_owner(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    sent = _send(restricted_session, caller, world, batch=False)

    owner.close(restricted_session, world.lens, sent, "not_now", LATER)

    answered = [
        i for i in _items(owner_session, sent) if i.kind == HUB_ENQUIRY_ANSWERED
    ]
    assert [i.batch_name for i in answered] == ["Rahim Sir"]


def _assert_untouched(session: Session, enquiry_id: uuid.UUID) -> None:
    """Assert a refused close left the request and its inbox as they were.

    :param session: An arranging session
    :param enquiry_id: The request
    :return: None
    """
    row = _row(session, enquiry_id)
    assert (row.status, row.outcome, row.closed_at) == ("open", None, None)
    items = _items(session, enquiry_id)
    assert {i.kind for i in items} == {HUB_ENQUIRY_RECEIVED}
    assert all(i.read_at is None for i in items)


def _refuse(
    session: Session, lens: TeacherLens, enquiry_id: uuid.UUID, outcome: str
) -> ValidationError:
    """Close with an outcome that must be refused, and return the refusal.

    :param session: The restricted session
    :param lens: The owner's lens
    :param enquiry_id: The request
    :param outcome: The outcome tried
    :return: The refusal
    """
    with pytest.raises(ValidationError) as refused:
        owner.close(session, lens, enquiry_id, outcome, LATER)
    assert refused.value.code == "ENQUIRY_OUTCOME_INVALID"
    assert refused.value.message_key == "hub.enquiry.outcome_invalid"
    assert to_response(refused.value).status_code == 400
    return refused.value


def test_added_without_contact_and_call_us_without_public_phone_invalid(
    owner_session: Session, restricted_session: Session
) -> None:
    """``added`` needs a shared contact; ``call_us`` a public number."""
    world = enquirable_owner(owner_session)
    unshared = _send(
        restricted_session, guardian(owner_session), world, share_contact=False
    )
    shared = _send(restricted_session, guardian(owner_session, phone=_phone()), world)

    _refuse(restricted_session, world.lens, unshared, "added")
    _refuse(restricted_session, world.lens, shared, "call_us")
    _refuse(restricted_session, world.lens, unshared, "call_us")

    _assert_untouched(owner_session, unshared)
    _assert_untouched(owner_session, shared)
    assert owner.get(restricted_session, world.lens, unshared).outcomes_allowed == [
        "not_now"
    ]
    assert owner.get(restricted_session, world.lens, shared).outcomes_allowed == [
        "added",
        "not_now",
    ]


@pytest.mark.parametrize("status", ["hidden", "suspended"])
def test_call_us_invalid_while_listing_not_public(
    owner_session: Session, restricted_session: Session, status: str
) -> None:
    """F11: the guardian is shown the number only while the owner is public.

    A hidden or suspended listing keeps its number in the base table, but
    ``hub_public_owner`` holds no row for it, so "please call us" would
    send a family to a number they cannot see. A suspended listing still
    closes with another outcome.
    """
    world = enquirable_owner(owner_session)
    _publish_phone(owner_session, world)
    sent = _send(restricted_session, guardian(owner_session), world)
    assert "call_us" in owner.get(restricted_session, world.lens, sent).outcomes_allowed

    _listing_status(owner_session, world, status)
    restricted_session.rollback()

    assert owner.get(restricted_session, world.lens, sent).outcomes_allowed == [
        "added",
        "not_now",
    ]
    _refuse(restricted_session, world.lens, sent, "call_us")
    _assert_untouched(owner_session, sent)

    closed = owner.close(restricted_session, world.lens, sent, "not_now", LATER)
    assert closed.outcome == "not_now"


@pytest.mark.parametrize(
    ("share", "phone", "public"),
    list(itertools.product([True, False], repeat=3)),
    ids=lambda v: str(v).lower(),
)
def test_outcomes_allowed_matches_close_rules(
    owner_session: Session,
    restricted_session: Session,
    share: bool,
    phone: bool,
    public: bool,
) -> None:
    """The clients render exactly what ``close`` would accept, and decide nothing.

    For every combination of a shared contact, a stored public number and a
    public listing, an outcome is listed exactly when closing with it
    succeeds.
    """
    world = enquirable_owner(owner_session)
    if phone:
        _publish_phone(owner_session, world)
    sent = {
        outcome: _send(
            restricted_session,
            guardian(owner_session, phone=_phone()),
            world,
            share_contact=share,
        )
        for outcome in OUTCOMES
    }
    if not public:
        _listing_status(owner_session, world, "hidden")
        restricted_session.rollback()

    expected = [
        o
        for o in OUTCOMES
        if o == "not_now"
        or (o == "added" and share)
        or (o == "call_us" and phone and public)
    ]
    for outcome, enquiry_id in sent.items():
        allowed = owner.get(restricted_session, world.lens, enquiry_id).outcomes_allowed
        assert allowed == expected
        try:
            owner.close(restricted_session, world.lens, enquiry_id, outcome, LATER)
        except ValidationError as refused:
            assert refused.code == "ENQUIRY_OUTCOME_INVALID"
            accepted = False
        else:
            accepted = True
        assert accepted == (outcome in allowed), outcome


def test_second_close_is_already_closed(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    _publish_phone(owner_session, world)
    caller = guardian(owner_session)
    sent = _send(restricted_session, caller, world)
    owner.close(restricted_session, world.lens, sent, "not_now", LATER)

    for outcome in OUTCOMES:
        with pytest.raises(ConflictError) as refused:
            owner.close(
                restricted_session,
                world.lens,
                sent,
                outcome,
                LATER + dt.timedelta(hours=1),
            )
        assert (refused.value.code, refused.value.message_key) == (
            "ENQUIRY_ALREADY_CLOSED",
            "hub.enquiry.already_closed",
        )
        assert to_response(refused.value).status_code == 409

    row = _row(owner_session, sent)
    assert (row.status, row.outcome, row.closed_at) == ("closed", "not_now", LATER)
    answered = [
        i for i in _items(owner_session, sent) if i.kind == HUB_ENQUIRY_ANSWERED
    ]
    assert len(answered) == 1
