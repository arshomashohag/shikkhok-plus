"""A family's interest in a listed batch [0049]: share, read, withdraw, close.

An interest decides who sees a family's phone number, so its predicates
are tested here first: who may share, into which batch, whether sharing
again is harmless, that the number is read live and reaches only the
owner's side, and that join requests never see an interest nor an interest
a join request.

The world is arranged through the table-owner session; every call under
test runs through the restricted application role.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.phone import canonical_phone
from app.auth.ceilings import HUB_INTEREST_ACCOUNT_DAILY, CeilingBreach
from app.errors import AuthorizationError, ConflictError
from app.hub.enquiries import interest, owner, sending
from app.notifications.inbox import HUB_INTEREST_RECEIVED
from tests.enquiries.support import CASES, enquirable_owner, guardian

#: A morning in Dhaka.
NOW = dt.datetime(2026, 11, 28, 4, 0, tzinfo=dt.UTC)


def _items(session: Session, kind: str, source: uuid.UUID) -> list[uuid.UUID]:
    """List who holds an inbox item of a kind about a source.

    :param session: An arranging session
    :param kind: The inbox kind
    :param source: The source id
    :return: The account ids, sorted
    """
    session.rollback()
    return sorted(
        session.scalars(
            sa.text(
                "SELECT account_id FROM notification WHERE kind = :k AND source_id = :s"
            ),
            {"k": kind, "s": source},
        )
    )


def _row(session: Session, interest_id: uuid.UUID) -> sa.Row[tuple[object, ...]]:
    """Read an interest's stored row.

    :param session: An arranging session
    :param interest_id: The interest
    :return: The row
    """
    session.rollback()
    return session.execute(
        sa.text(
            "SELECT kind::text AS kind, student_name, class_level, message, "
            "share_contact, status::text AS status, outcome::text AS outcome, "
            "batch_id FROM listing_enquiry WHERE id = :i"
        ),
        {"i": interest_id},
    ).one()


def test_sharing_stores_nothing_typed_and_tells_every_manager(
    owner_session: Session, restricted_session: Session
) -> None:
    """An interest holds no name, class or message, always shares, and is announced.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    world = enquirable_owner(owner_session, centre=True)
    family = guardian(owner_session)

    shared = interest.share(
        restricted_session, family, world.owner_slug, world.batch_id, NOW
    )

    assert (shared.batch_title, shared.status, shared.shared_on) == (
        world.batch_title,
        "open",
        dt.date(2026, 11, 28),
    )
    row = _row(owner_session, shared.id)
    assert tuple(row) == (
        "interest",
        None,
        None,
        None,
        True,
        "open",
        None,
        world.batch_id,
    )
    assert _items(owner_session, HUB_INTEREST_RECEIVED, shared.id) == world.manager_ids


def test_the_owner_sees_the_phone_live_and_no_name(
    owner_session: Session, restricted_session: Session
) -> None:
    """The owner reads the number the account holds now, and nothing else.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    world = enquirable_owner(owner_session)
    family = guardian(owner_session, phone="01712000001")
    interest.share(restricted_session, family, world.owner_slug, world.batch_id, NOW)

    [seen] = interest.list_for(restricted_session, world.lens)
    assert seen.guardian_phone == canonical_phone("01712000001")
    assert seen.batch_title == world.batch_title
    assert not hasattr(seen, "student_name")

    owner_session.execute(
        sa.text("UPDATE account SET phone = :p WHERE id = :a"),
        {"p": canonical_phone("01712000002"), "a": family},
    )
    owner_session.commit()
    restricted_session.rollback()
    [seen] = interest.list_for(restricted_session, world.lens)
    assert seen.guardian_phone == canonical_phone("01712000002")


def test_sharing_again_changes_nothing_and_counts_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    """A second share answers the first, with one row and one inbox item.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    world = enquirable_owner(owner_session)
    family = guardian(owner_session)
    first = interest.share(
        restricted_session, family, world.owner_slug, world.batch_id, NOW
    )
    again = interest.share(
        restricted_session, family, world.owner_slug, world.batch_id, NOW
    )

    assert again.id == first.id
    assert len(interest.list_for(restricted_session, world.lens)) == 1
    assert _items(owner_session, HUB_INTEREST_RECEIVED, first.id) == world.manager_ids
    spent = owner_session.execute(
        sa.text(
            "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
            "WHERE scope_kind = 'hub_interest_day' AND scope_value = :a"
        ),
        {"a": str(family)},
    ).scalar_one()
    assert spent == 1


def test_a_closed_batch_still_takes_interest_but_not_a_request(
    owner_session: Session, restricted_session: Session
) -> None:
    """Interest matters most when admissions are closed; a join request is refused.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    world = enquirable_owner(owner_session, admissions="closed")
    family = guardian(owner_session)

    shared = interest.share(
        restricted_session, family, world.owner_slug, world.batch_id, NOW
    )
    assert shared.status == "open"
    with pytest.raises(AuthorizationError) as refused:
        sending.send(
            restricted_session,
            family,
            world.owner_slug,
            student_name="Nadia",
            class_level="class_8",
            message=None,
            batch_id=world.batch_id,
            share_contact=True,
            now=NOW,
        )
    assert refused.value.code == "ENQUIRY_TARGET_NOT_FOUND"


@pytest.mark.parametrize(
    "case", sorted(set(CASES) - {"batch_closed"}), ids=lambda case: case
)
def test_every_target_a_request_may_not_reach_refuses_an_interest_alike(
    owner_session: Session, restricted_session: Session, case: str
) -> None:
    """Every refusal but a closed batch is the request's own one 404.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param case: How the target is made unreachable
    :return: None
    """
    world = enquirable_owner(owner_session)
    slug, batch_id, caller = CASES[case](owner_session, world)
    batch = batch_id if batch_id is not None else world.batch_id

    with pytest.raises(AuthorizationError) as refused:
        interest.share(restricted_session, caller, slug, batch, NOW)
    assert refused.value.code == "ENQUIRY_TARGET_NOT_FOUND"
    restricted_session.rollback()
    with pytest.raises(AuthorizationError):
        interest.describe(restricted_session, caller, slug, batch)


def test_an_account_without_a_phone_cannot_share(
    owner_session: Session, restricted_session: Session
) -> None:
    """A phone number is what an interest shares; an email-only account is told so.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    world = enquirable_owner(owner_session)
    family = guardian(owner_session, phone=None, email="family@example.test")

    target = interest.describe(
        restricted_session, family, world.owner_slug, world.batch_id
    )
    assert (target.has_phone, target.already_shared) == (False, False)
    with pytest.raises(ConflictError) as refused:
        interest.share(
            restricted_session, family, world.owner_slug, world.batch_id, NOW
        )
    assert refused.value.code == "HUB_INTEREST_NEEDS_PHONE"
    assert interest.list_for(restricted_session, world.lens) == []


def test_the_daily_allowance_counts_only_stored_interests(
    owner_session: Session, restricted_session: Session
) -> None:
    """The eleventh interest in a day is refused and rolled back with its count.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    family = guardian(owner_session)
    worlds = [
        enquirable_owner(owner_session) for _ in range(HUB_INTEREST_ACCOUNT_DAILY + 1)
    ]
    for world in worlds[:-1]:
        interest.share(
            restricted_session, family, world.owner_slug, world.batch_id, NOW
        )

    last = worlds[-1]
    with pytest.raises(CeilingBreach) as refused:
        interest.share(restricted_session, family, last.owner_slug, last.batch_id, NOW)
    assert refused.value.code == "HUB_INTEREST_CEILING"
    assert interest.list_for(restricted_session, last.lens) == []
    assert len(interest.mine(restricted_session, family)) == HUB_INTEREST_ACCOUNT_DAILY


def test_requests_and_interests_never_see_each_other(
    owner_session: Session, restricted_session: Session
) -> None:
    """Each list holds its own kind, and neither blocks the other.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    world = enquirable_owner(owner_session)
    family = guardian(owner_session)
    request = sending.send(
        restricted_session,
        family,
        world.owner_slug,
        student_name="Nadia",
        class_level="class_8",
        message=None,
        batch_id=world.batch_id,
        share_contact=True,
        now=NOW,
    )
    shared = interest.share(
        restricted_session, family, world.owner_slug, world.batch_id, NOW
    )

    assert [r.id for r in sending.mine(restricted_session, family)] == [request.id]
    assert [r.id for r in owner.list_for(restricted_session, world.lens)] == [
        request.id
    ]
    assert [i.id for i in interest.mine(restricted_session, family)] == [shared.id]
    assert [i.id for i in interest.list_for(restricted_session, world.lens)] == [
        shared.id
    ]
    with pytest.raises(AuthorizationError):
        owner.get(restricted_session, world.lens, shared.id)
    restricted_session.rollback()
    with pytest.raises(AuthorizationError):
        interest.close(restricted_session, world.lens, request.id, NOW)


def test_withdrawal_forgets_the_interest_and_its_inbox_items(
    owner_session: Session, restricted_session: Session
) -> None:
    """Taking it back deletes the row and every manager's item about it.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    world = enquirable_owner(owner_session, centre=True)
    family = guardian(owner_session)
    shared = interest.share(
        restricted_session, family, world.owner_slug, world.batch_id, NOW
    )

    sending.withdraw(restricted_session, family, shared.id)

    assert interest.mine(restricted_session, family) == []
    assert interest.list_for(restricted_session, world.lens) == []
    assert _items(owner_session, HUB_INTEREST_RECEIVED, shared.id) == []


def test_another_familys_withdrawal_changes_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    """Withdrawal is scoped by account in SQL; another id is quietly ignored.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    world = enquirable_owner(owner_session)
    family = guardian(owner_session)
    stranger = guardian(owner_session, phone="01712000009")
    shared = interest.share(
        restricted_session, family, world.owner_slug, world.batch_id, NOW
    )

    sending.withdraw(restricted_session, stranger, shared.id)

    assert [i.id for i in interest.mine(restricted_session, family)] == [shared.id]


def test_the_owner_closes_quietly_and_the_family_may_share_again(
    owner_session: Session, restricted_session: Session
) -> None:
    """Closing marks the items read, tells the family nothing, and frees the batch.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    world = enquirable_owner(owner_session)
    family = guardian(owner_session)
    shared = interest.share(
        restricted_session, family, world.owner_slug, world.batch_id, NOW
    )

    interest.close(restricted_session, world.lens, shared.id, NOW)

    assert interest.list_for(restricted_session, world.lens) == []
    [mine] = interest.mine(restricted_session, family)
    assert mine.status == "closed"
    owner_session.rollback()
    unread, family_items = owner_session.execute(
        sa.text(
            "SELECT count(*) FILTER (WHERE kind = :k AND read_at IS NULL), "
            "count(*) FILTER (WHERE account_id = :f) FROM notification"
        ),
        {"k": HUB_INTEREST_RECEIVED, "f": family},
    ).one()
    assert (unread, family_items) == (0, 0)

    with pytest.raises(AuthorizationError):
        interest.close(restricted_session, world.lens, shared.id, NOW)
    restricted_session.rollback()
    again = interest.share(
        restricted_session, family, world.owner_slug, world.batch_id, NOW
    )
    assert again.id != shared.id


def test_another_owner_cannot_read_or_close_an_interest(
    owner_session: Session, restricted_session: Session
) -> None:
    """The owner's list and close are scoped by the lens's owner.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    world, other = enquirable_owner(owner_session), enquirable_owner(owner_session)
    family = guardian(owner_session)
    shared = interest.share(
        restricted_session, family, world.owner_slug, world.batch_id, NOW
    )

    assert interest.list_for(restricted_session, other.lens) == []
    with pytest.raises(AuthorizationError) as refused:
        interest.close(restricted_session, other.lens, shared.id, NOW)
    assert refused.value.code == "ENQUIRY_NOT_FOUND"
    restricted_session.rollback()
    assert len(interest.list_for(restricted_session, world.lens)) == 1


def test_the_database_holds_an_interest_to_its_shape(owner_session: Session) -> None:
    """An interest with a name, or without its contact, is refused by CHECK.

    :param owner_session: A session as the table owner
    :return: None
    """
    world = enquirable_owner(owner_session)
    family = guardian(owner_session)
    bad: tuple[tuple[str | None, str | None, str | None, bool], ...] = (
        ("Nadia", None, None, True),
        (None, "class_8", None, True),
        (None, None, "hello", True),
        (None, None, None, False),
    )
    for name, level, message, share in bad:
        with pytest.raises(sa.exc.IntegrityError):
            owner_session.execute(
                sa.text(
                    "INSERT INTO listing_enquiry (owner_id, batch_id, "
                    "enquirer_account_id, kind, student_name, class_level, "
                    "message, share_contact) VALUES (:o, :b, :a, 'interest', "
                    ":name, :level, :message, :share)"
                ),
                {
                    "o": world.lens.owner_id,
                    "b": world.batch_id,
                    "a": family,
                    "name": name,
                    "level": level,
                    "message": message,
                    "share": share,
                },
            )
        owner_session.rollback()
    with pytest.raises(sa.exc.IntegrityError):
        owner_session.execute(
            sa.text(
                "INSERT INTO listing_enquiry (owner_id, batch_id, "
                "enquirer_account_id, kind, share_contact) "
                "VALUES (:o, :b, :a, 'join', true)"
            ),
            {"o": world.lens.owner_id, "b": world.batch_id, "a": family},
        )
    owner_session.rollback()
