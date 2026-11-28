"""Batch listings: what publishing needs and what retiring a batch does."""

from __future__ import annotations

import datetime as dt
import inspect
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import BatchChanges, BatchNotFound, update_batch
from app.db.models import Batch, BatchListing, BatchSubject
from app.errors import ConflictError, ValidationError
from app.hub.listings import batches, owner
from app.hub.listings.batches import BatchListingUpdate
from app.hub.listings.checklist import batch_checklist
from app.hub.listings.owner import OwnerListingUpdate
from tests.batches.conftest import TeacherFixture, make_teacher
from tests.hub.support import areas

NOW = dt.datetime(2026, 11, 14, 9, 0, tzinfo=dt.UTC)


def _teacher(session: Session) -> tuple[TeacherLens, uuid.UUID]:
    """Arrange a teacher with one subject on their batch.

    :param session: An arranging session
    :return: The lens and the batch id
    """
    teacher: TeacherFixture = make_teacher(session)
    session.add(BatchSubject(batch_id=teacher.batch_id, name="Maths"))
    session.commit()
    lens = TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)
    return lens, teacher.batch_id


def _publish_owner(session: Session, lens: TeacherLens) -> None:
    """Publish the owner's own listing.

    :param session: The application role's session
    :param lens: The owner
    :return: None
    """
    district, upazila, _ = areas(session)
    owner.get_or_draft(session, lens)
    owner.update(
        session,
        lens,
        OwnerListingUpdate(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            public_name="Rahim Sir",
            headline_en="Maths",
            bio_en="Teacher",
            district_code=district,
            upazila_code=upazila,
        ),
    )
    owner.publish(session, lens, "2026-11-14", NOW)


def _full(slug: str = "class-9-maths") -> BatchListingUpdate:
    """Build a complete set of edits.

    :param slug: The slug
    :return: The edits
    """
    return BatchListingUpdate(
        slug=slug,
        public_title="Class 9 Maths",
        description_en="Weekly maths",
        class_levels=["class_9"],
        mode="in_person",
        show_fee=True,
        show_schedule=False,
    )


def test_publish_requires_owner_listing_published(
    owner_session: Session, restricted_session: Session
) -> None:
    """A batch cannot go live under an owner who is not public.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    batches.upsert(restricted_session, lens, batch_id, _full())
    with pytest.raises(ConflictError) as raised:
        batches.publish(restricted_session, lens, batch_id, NOW)
    assert raised.value.code == "HUB_OWNER_NOT_PUBLISHED"


def test_publish_requires_description_class_level_subject_and_both_flags(
    owner_session: Session, restricted_session: Session
) -> None:
    """Each missing requirement is reported by key; flags are NOT NULL.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    teacher = make_teacher(owner_session)  # no subject on purpose
    lens = TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)
    _publish_owner(restricted_session, lens)
    batches.upsert(
        restricted_session,
        lens,
        teacher.batch_id,
        BatchListingUpdate(slug="no-extras", show_fee=True, show_schedule=True),
    )
    with pytest.raises(ValidationError) as raised:
        batches.publish(restricted_session, lens, teacher.batch_id, NOW)
    assert raised.value.code == "HUB_LISTING_INCOMPLETE"
    assert raised.value.details["missing"] == (
        "public_title,description,class_levels,subjects,mode"
    )

    owner_session.add(BatchSubject(batch_id=teacher.batch_id, name="Maths"))
    owner_session.commit()
    batches.upsert(
        restricted_session,
        lens,
        teacher.batch_id,
        BatchListingUpdate(
            public_title="নবম শ্রেণির গণিত",
            description_bn="গণিত",
            class_levels=["class_9"],
            mode="online",
        ),
    )
    published = batches.publish(restricted_session, lens, teacher.batch_id, NOW)
    assert published.status == "published"
    assert published.published_at == NOW

    items = {i.key: i.done for i in batch_checklist(published, subject_count=1)}
    assert items == {
        "public_title": True,
        "slug": True,
        "description": True,
        "class_levels": True,
        "subjects": True,
        "mode": True,
    }


def test_upsert_without_show_fee_is_validation_error(
    owner_session: Session, restricted_session: Session
) -> None:
    """Creating a row without stating both flags is refused.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    for update in (
        BatchListingUpdate(show_schedule=True),
        BatchListingUpdate(show_fee=True),
    ):
        with pytest.raises(ValidationError) as raised:
            batches.upsert(restricted_session, lens, batch_id, update)
        assert raised.value.code == "HUB_BATCH_FLAGS_REQUIRED"
    assert restricted_session.get(BatchListing, batch_id) is None


def test_other_owners_batch_is_not_available(
    owner_session: Session, restricted_session: Session
) -> None:
    """Another owner's batch reads exactly as a missing one.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, _ = _teacher(owner_session)
    _, theirs = _teacher(owner_session)
    for call in (
        lambda: batches.upsert(restricted_session, lens, theirs, _full()),
        lambda: batches.publish(restricted_session, lens, theirs, NOW),
        lambda: batches.unpublish(restricted_session, lens, theirs, NOW),
    ):
        with pytest.raises(BatchNotFound) as raised:
            call()
        assert raised.value.code == "BATCH_NOT_FOUND"
    assert owner_session.get(BatchListing, theirs) is None


def test_inactive_batch_cannot_be_published(
    owner_session: Session, restricted_session: Session
) -> None:
    """A retired batch is refused with its own code.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    _publish_owner(restricted_session, lens)
    batches.upsert(restricted_session, lens, batch_id, _full())
    update_batch(
        restricted_session,
        lens=lens,
        batch_id=batch_id,
        changes=BatchChanges(active=False),
    )
    with pytest.raises(ConflictError) as raised:
        batches.publish(restricted_session, lens, batch_id, NOW)
    assert raised.value.code == "HUB_BATCH_INACTIVE"


def test_deactivating_batch_hides_listing_and_reactivation_does_not_republish(
    owner_session: Session, restricted_session: Session
) -> None:
    """Retiring hides a live listing; bringing the batch back never revives it.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    _publish_owner(restricted_session, lens)
    batches.upsert(restricted_session, lens, batch_id, _full())
    batches.publish(restricted_session, lens, batch_id, NOW)

    update_batch(
        restricted_session,
        lens=lens,
        batch_id=batch_id,
        changes=BatchChanges(active=False),
    )
    owner_session.expire_all()
    assert owner_session.get(BatchListing, batch_id).status == "hidden"

    update_batch(
        restricted_session,
        lens=lens,
        batch_id=batch_id,
        changes=BatchChanges(active=True),
    )
    owner_session.expire_all()
    assert owner_session.get(BatchListing, batch_id).status == "hidden"
    assert owner_session.get(Batch, batch_id).active is True


def test_hide_leaves_other_statuses_alone(
    owner_session: Session, restricted_session: Session
) -> None:
    """Only a published listing is hidden; draft and suspended are untouched.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    batches.upsert(restricted_session, lens, batch_id, _full())
    batches.hide_for_inactive_batch(restricted_session, batch_id)
    restricted_session.commit()
    assert restricted_session.get(BatchListing, batch_id).status == "draft"
    owner_session.execute(
        sa.text("UPDATE batch_listing SET status = 'suspended' WHERE batch_id = :b"),
        {"b": batch_id},
    )
    owner_session.commit()
    batches.hide_for_inactive_batch(restricted_session, batch_id)
    restricted_session.commit()
    restricted_session.expire_all()
    assert restricted_session.get(BatchListing, batch_id).status == "suspended"


def test_suspended_listing_refuses_edit_publish_unpublish(
    owner_session: Session, restricted_session: Session
) -> None:
    """A moderator's suspension holds against the owner.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    _publish_owner(restricted_session, lens)
    batches.upsert(restricted_session, lens, batch_id, _full())
    owner_session.execute(
        sa.text("UPDATE batch_listing SET status = 'suspended' WHERE batch_id = :b"),
        {"b": batch_id},
    )
    owner_session.commit()
    for call in (
        lambda: batches.upsert(restricted_session, lens, batch_id, _full()),
        lambda: batches.publish(restricted_session, lens, batch_id, NOW),
        lambda: batches.unpublish(restricted_session, lens, batch_id, NOW),
    ):
        with pytest.raises(ConflictError) as raised:
            call()
        assert raised.value.code == "HUB_LISTING_SUSPENDED"


def test_slug_is_validated_scanned_and_unique_per_owner(
    owner_session: Session, restricted_session: Session
) -> None:
    """Shape, phone scan and per-owner uniqueness, but not across owners.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, first = _teacher(owner_session)
    other = make_teacher(owner_session)
    lens2 = TeacherLens(account_id=other.account_id, owner_id=other.owner_id)
    second = Batch(
        owner_id=lens.owner_id,
        name="Second",
        default_fee=owner_session.get(Batch, first).default_fee,
        fee_due_day=10,
        marksheet_visible=True,
        active=True,
        created_at=NOW,
    )
    owner_session.add(second)
    owner_session.commit()

    batches.upsert(restricted_session, lens, first, _full("shared-slug"))
    with pytest.raises(ValidationError) as raised:
        batches.upsert(restricted_session, lens, first, BatchListingUpdate(slug="A_"))
    assert raised.value.code == "HUB_SLUG_INVALID"
    with pytest.raises(ValidationError) as raised:
        batches.upsert(
            restricted_session,
            lens,
            first,
            BatchListingUpdate(description_en="call 01712345678"),
        )
    assert raised.value.code == "HUB_TEXT_CONTAINS_CONTACT"
    with pytest.raises(ConflictError) as taken:
        batches.upsert(restricted_session, lens, second.id, _full("shared-slug"))
    assert taken.value.code == "HUB_SLUG_TAKEN"
    # Another owner may use the same slug.
    batches.upsert(restricted_session, lens2, other.batch_id, _full("shared-slug"))


def test_editing_a_live_listing_cannot_leave_it_incomplete(
    owner_session: Session, restricted_session: Session
) -> None:
    """Clearing the last class level of a published listing is refused.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    _publish_owner(restricted_session, lens)
    batches.upsert(restricted_session, lens, batch_id, _full())
    batches.publish(restricted_session, lens, batch_id, NOW)
    with pytest.raises(ValidationError) as raised:
        batches.upsert(
            restricted_session, lens, batch_id, BatchListingUpdate(class_levels=[])
        )
    assert raised.value.code == "HUB_LISTING_INCOMPLETE"
    assert raised.value.details["missing"] == "class_levels"
    restricted_session.expire_all()
    assert restricted_session.get(BatchListing, batch_id).class_levels == ["class_9"]


def test_unpublish_hides_and_list_for_owner_covers_active_batches(
    owner_session: Session, restricted_session: Session
) -> None:
    """Unpublish hides; the owner's view lists active batches with checklists.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    _publish_owner(restricted_session, lens)
    views = batches.list_for_owner(restricted_session, lens)
    assert [v.batch_id for v in views] == [batch_id]
    assert views[0].listing is None
    assert views[0].subjects == ["Maths"]
    assert {i.key for i in views[0].checklist if i.done} == {"subjects"}

    batches.upsert(restricted_session, lens, batch_id, _full())
    batches.publish(restricted_session, lens, batch_id, NOW)
    assert batches.unpublish(restricted_session, lens, batch_id, NOW).status == "hidden"
    views = batches.list_for_owner(restricted_session, lens)
    assert views[0].listing is not None
    assert views[0].listing.status == "hidden"

    update_batch(
        restricted_session,
        lens=lens,
        batch_id=batch_id,
        changes=BatchChanges(active=False),
    )
    assert batches.list_for_owner(restricted_session, lens) == []


def test_update_batch_calls_the_hide_in_its_own_transaction() -> None:
    """The hide runs before ``update_batch``'s commit, not after it.

    :return: None
    """
    from app.batches import service

    source = inspect.getsource(service.update_batch)
    assert source.index("hide_for_inactive_batch") < source.index("session.commit()")


def test_unpublish_without_a_listing_is_not_found(
    owner_session: Session, restricted_session: Session
) -> None:
    """A batch never listed reads as missing, like another owner's.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    with pytest.raises(BatchNotFound) as raised:
        batches.unpublish(restricted_session, lens, batch_id, NOW)
    assert raised.value.code == "BATCH_NOT_FOUND"
    assert raised.value.message_key == "batch.not_found"


def test_publish_rereads_active_after_a_concurrent_retirement(
    owner_session: Session, restricted_session: Session
) -> None:
    """A batch retired after this session loaded it is still refused.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    _publish_owner(restricted_session, lens)
    batches.upsert(restricted_session, lens, batch_id, _full())
    assert restricted_session.get(Batch, batch_id).active is True
    owner_session.execute(
        sa.text("UPDATE batch SET active = false WHERE id = :b"), {"b": batch_id}
    )
    owner_session.commit()
    with pytest.raises(ConflictError) as raised:
        batches.publish(restricted_session, lens, batch_id, NOW)
    assert raised.value.code == "HUB_BATCH_INACTIVE"


def test_subject_tags_are_scanned_for_phone_numbers(
    owner_session: Session, restricted_session: Session
) -> None:
    """A phone number hidden in a public tag is refused.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    with pytest.raises(ValidationError) as raised:
        batches.upsert(
            restricted_session,
            lens,
            batch_id,
            BatchListingUpdate(
                subject_tags=["maths", "01712345678"],
                show_fee=True,
                show_schedule=True,
            ),
        )
    assert raised.value.code == "HUB_TEXT_CONTAINS_CONTACT"
    assert raised.value.details["field"] == "subject_tags"


@pytest.mark.parametrize("title", [None, "", "  ", "ab"])
def test_public_title_is_required_and_at_least_three_characters(
    owner_session: Session, restricted_session: Session, title: str | None
) -> None:
    """A batch goes public under its own title, never under ``batch.name``.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param title: A missing, blank or too-short title
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    _publish_owner(restricted_session, lens)
    edits = _full()
    batches.upsert(
        restricted_session,
        lens,
        batch_id,
        BatchListingUpdate(**{**_as_dict(edits), "public_title": title}),
    )
    with pytest.raises(ValidationError) as raised:
        batches.publish(restricted_session, lens, batch_id, NOW)
    assert raised.value.details["missing"] == "public_title"


def test_public_title_is_scanned_for_phone_numbers(
    owner_session: Session, restricted_session: Session
) -> None:
    """A title carrying a number is refused like any other public text.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    with pytest.raises(ValidationError) as raised:
        batches.upsert(
            restricted_session,
            lens,
            batch_id,
            BatchListingUpdate(
                public_title="Call 01711234567", show_fee=True, show_schedule=True
            ),
        )
    assert raised.value.code == "HUB_TEXT_CONTAINS_CONTACT"
    assert raised.value.details["field"] == "public_title"


def _as_dict(edits: BatchListingUpdate) -> dict[str, object]:
    """Copy an update's fields into a dict.

    :param edits: The update
    :return: Its fields by name
    """
    return {f: getattr(edits, f) for f in BatchListingUpdate.__dataclass_fields__}


# ---------------------------------------------------------------------------
# Seat counts [0048]: the owner's own two numbers, shown only by choice.


def test_seats_are_stored_shown_and_stamped_only_when_a_count_changes(
    owner_session: Session, restricted_session: Session
) -> None:
    """Both counts are kept as typed; a change stamps when, a toggle does not.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    listing = batches.upsert(restricted_session, lens, batch_id, _full())
    assert (listing.show_seats, listing.seat_capacity, listing.seats_free) == (
        False,
        None,
        None,
    )
    assert listing.seats_updated_at is None

    listing = batches.upsert(
        restricted_session,
        lens,
        batch_id,
        BatchListingUpdate(show_seats=True, seat_capacity=18, seats_free=4),
    )
    assert (listing.show_seats, listing.seat_capacity, listing.seats_free) == (
        True,
        18,
        4,
    )
    first = listing.seats_updated_at
    assert first is not None

    # Hiding the seats keeps the numbers and does not restamp them.
    listing = batches.upsert(
        restricted_session, lens, batch_id, BatchListingUpdate(show_seats=False)
    )
    assert (listing.show_seats, listing.seat_capacity, listing.seats_free) == (
        False,
        18,
        4,
    )
    assert listing.seats_updated_at == first

    # A changed count restamps; the capacity is kept when only free changes.
    listing = batches.upsert(
        restricted_session,
        lens,
        batch_id,
        BatchListingUpdate(show_seats=True, seats_free=3),
    )
    assert (listing.seat_capacity, listing.seats_free) == (18, 3)
    assert listing.seats_updated_at is not None
    assert listing.seats_updated_at > first


@pytest.mark.parametrize(
    "edits",
    [
        BatchListingUpdate(seat_capacity=0, seats_free=0),
        BatchListingUpdate(seat_capacity=501, seats_free=1),
        BatchListingUpdate(seat_capacity=10, seats_free=11),
        BatchListingUpdate(seats_free=2),
        BatchListingUpdate(show_seats=True, seat_capacity=10),
        BatchListingUpdate(show_seats=True),
    ],
    ids=[
        "capacity-zero",
        "capacity-over-500",
        "free-over-capacity",
        "free-without-capacity",
        "shown-without-free",
        "shown-without-either",
    ],
)
def test_seat_counts_that_cannot_hold_are_refused_and_change_nothing(
    owner_session: Session, restricted_session: Session, edits: BatchListingUpdate
) -> None:
    """Out-of-range or inconsistent counts are one error, and nothing is saved.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param edits: The edit that must be refused
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    batches.upsert(restricted_session, lens, batch_id, _full())

    with pytest.raises(ValidationError) as raised:
        batches.upsert(restricted_session, lens, batch_id, edits)
    assert raised.value.code == "HUB_BATCH_SEATS_INVALID"
    assert raised.value.message_key == "hub.batch_seats_invalid"

    restricted_session.rollback()
    stored = owner_session.execute(
        sa.select(
            BatchListing.show_seats,
            BatchListing.seat_capacity,
            BatchListing.seats_free,
            BatchListing.seats_updated_at,
        ).where(BatchListing.batch_id == batch_id)
    ).one()
    assert tuple(stored) == (False, None, None, None)


def test_the_boundaries_are_accepted(
    owner_session: Session, restricted_session: Session
) -> None:
    """One seat, 500 seats, none free and all free are each a valid statement.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    batches.upsert(restricted_session, lens, batch_id, _full())
    for capacity, free in ((1, 0), (1, 1), (500, 0), (500, 500)):
        listing = batches.upsert(
            restricted_session,
            lens,
            batch_id,
            BatchListingUpdate(
                show_seats=True, seat_capacity=capacity, seats_free=free
            ),
        )
        assert (listing.seat_capacity, listing.seats_free) == (capacity, free)


def test_the_database_refuses_inconsistent_seats_on_its_own(
    owner_session: Session,
) -> None:
    """The CHECKs hold the service's rules for a write that skips it.

    :param owner_session: A session as the table owner
    :return: None
    """
    lens, batch_id = _teacher(owner_session)
    batches.upsert(owner_session, lens, batch_id, _full())
    bad = (
        "seat_capacity = 0, seats_updated_at = now()",
        "seat_capacity = 10, seats_free = 11, seats_updated_at = now()",
        "seats_free = 1",
        "show_seats = true",
        "seat_capacity = 10, seats_free = 2",
    )
    for assignment in bad:
        with pytest.raises(sa.exc.IntegrityError):
            owner_session.execute(
                sa.text(
                    f"UPDATE batch_listing SET {assignment} "  # noqa: S608 -- fixed test literals
                    "WHERE batch_id = :b"
                ),
                {"b": batch_id},
            )
        owner_session.rollback()
