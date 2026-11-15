"""``0036`` adds the listing, report and moderation tables and their guards.

Every refusal is asserted through the database, as the application role
where the grant is the point, because a rule enforced only by the code
that calls it is the thing these tables exist not to rely on.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from tests.batches.conftest import make_teacher
from tests.db.test_append_only import _refused


def _centre(session: Session) -> uuid.UUID:
    """Create a coaching-centre owner.

    :param session: An arranging session
    :return: The owner id
    """
    owner_id = uuid.uuid4()
    session.execute(
        sa.text(
            "INSERT INTO owner (id, account_id, created_at, kind, name) "
            "VALUES (:id, NULL, now(), 'organisation', 'Udoy Coaching')"
        ),
        {"id": owner_id},
    )
    session.commit()
    return owner_id


def _listing(
    session: Session,
    owner_id: uuid.UUID,
    *,
    status: str = "draft",
    slug: str | None = None,
    street_address: str | None = None,
    public_name: str = "Rahim Sir",
) -> None:
    """Insert one owner listing.

    :param session: The session to write through
    :param owner_id: The owner
    :param status: The listing status
    :param slug: The slug, if any
    :param street_address: The street address, if any
    :param public_name: The public name
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO owner_listing "
            "(owner_id, status, slug, street_address, public_name) "
            "VALUES (:o, CAST(:st AS hub_listing_status), :slug, :street, :name)"
        ),
        {
            "o": owner_id,
            "st": status,
            "slug": slug,
            "street": street_address,
            "name": public_name,
        },
    )


def test_draft_without_slug_inserts_published_without_slug_fails(
    owner_session: Session,
) -> None:
    """A draft needs no slug; a live listing does.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    _listing(owner_session, teacher.owner_id, status="draft", slug=None)
    owner_session.commit()

    owner_session.execute(sa.text("DELETE FROM owner_listing"))
    owner_session.commit()
    with pytest.raises(sa.exc.IntegrityError, match="ck_owner_listing_slug_when_live"):
        _listing(owner_session, teacher.owner_id, status="published", slug=None)
    owner_session.rollback()


@pytest.mark.parametrize("slug", ["Rahim-Sir", "ab", "a b c", "rahim_sir", "র" * 3])
def test_slug_check_rejects_uppercase_and_short(
    owner_session: Session, slug: str
) -> None:
    """A slug is lower-case, hyphenated and at least three characters.

    :param owner_session: An arranging session
    :param slug: A malformed slug
    :return: None
    """
    teacher = make_teacher(owner_session)
    with pytest.raises(sa.exc.IntegrityError, match="ck_owner_listing_slug"):
        _listing(owner_session, teacher.owner_id, slug=slug)
    owner_session.rollback()


def test_a_slug_over_sixty_characters_is_refused(owner_session: Session) -> None:
    """The column is 60 wide and the check says 60, so 61 cannot get in.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    with pytest.raises(sa.exc.DBAPIError):
        _listing(owner_session, teacher.owner_id, slug="a" * 61)
    owner_session.rollback()


def test_a_blank_public_name_is_allowed_only_in_a_draft(
    owner_session: Session,
) -> None:
    """An empty prefill is a draft; publishing it is refused.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    _listing(owner_session, teacher.owner_id, public_name="")
    owner_session.commit()
    with pytest.raises(sa.exc.IntegrityError, match="ck_owner_listing_name_when_live"):
        owner_session.execute(
            sa.text("UPDATE owner_listing SET status = 'published', slug = 'rahim-sir'")
        )
    owner_session.rollback()


def test_slug_is_unique_across_owners(owner_session: Session) -> None:
    """Two owners cannot hold one slug.

    :param owner_session: An arranging session
    :return: None
    """
    one = make_teacher(owner_session)
    two = make_teacher(owner_session)
    _listing(owner_session, one.owner_id, slug="rahim-sir")
    owner_session.commit()
    with pytest.raises(sa.exc.IntegrityError, match="uq_owner_listing_slug"):
        _listing(owner_session, two.owner_id, slug="rahim-sir")
    owner_session.rollback()


def test_solo_owner_listing_refuses_street_address(owner_session: Session) -> None:
    """Only a centre may publish a street address; the trigger refuses.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    with pytest.raises(sa.exc.DBAPIError, match="street address"):
        _listing(owner_session, teacher.owner_id, street_address="12 Road")
    owner_session.rollback()

    _listing(owner_session, teacher.owner_id)
    owner_session.commit()
    with pytest.raises(sa.exc.DBAPIError, match="street address"):
        owner_session.execute(
            sa.text("UPDATE owner_listing SET street_address = '9 Lane'")
        )
    owner_session.rollback()

    centre = _centre(owner_session)
    _listing(owner_session, centre, street_address="12 Road")
    owner_session.commit()


def _batch_listing(
    session: Session, batch_id: uuid.UUID, owner_id: uuid.UUID, **extra: object
) -> None:
    """Insert one batch listing, both flags stated.

    :param session: The session to write through
    :param batch_id: The batch
    :param owner_id: The owner the row claims
    :param extra: Column overrides, such as ``slug``, ``status`` or ``title``
    :return: None
    """
    values: dict[str, object] = {
        "b": batch_id,
        "o": owner_id,
        "fee": False,
        "sched": False,
        "slug": None,
        "status": "draft",
        "title": "HSC Physics",
    } | extra
    session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, show_fee, "
            "show_schedule, slug, status, public_title) VALUES (:b, :o, :fee, "
            ":sched, :slug, CAST(:status AS hub_listing_status), :title)"
        ),
        values,
    )


def test_batch_listing_owner_must_match_batch_owner(owner_session: Session) -> None:
    """A listing cannot claim an owner other than its batch's.

    :param owner_session: An arranging session
    :return: None
    """
    one = make_teacher(owner_session)
    two = make_teacher(owner_session)
    _batch_listing(owner_session, one.batch_id, one.owner_id)
    owner_session.commit()
    owner_session.execute(sa.text("DELETE FROM batch_listing"))
    owner_session.commit()
    with pytest.raises(sa.exc.DBAPIError, match="does not match"):
        _batch_listing(owner_session, one.batch_id, two.owner_id)
    owner_session.rollback()


def test_batch_slug_is_unique_per_owner_only(owner_session: Session) -> None:
    """One owner cannot repeat a batch slug; another owner may reuse it.

    :param owner_session: An arranging session
    :return: None
    """
    one = make_teacher(owner_session)
    two = make_teacher(owner_session)
    other = make_teacher(owner_session)
    # A second batch for the first owner.
    second = uuid.uuid4()
    owner_session.execute(
        sa.text(
            "INSERT INTO batch (id, owner_id, name, default_fee, fee_due_day, "
            "marksheet_visible, active, created_at) SELECT :id, owner_id, 'B2', "
            "default_fee, fee_due_day, marksheet_visible, active, now() "
            "FROM batch WHERE id = :b"
        ),
        {"id": second, "b": one.batch_id},
    )
    owner_session.commit()
    _batch_listing(owner_session, one.batch_id, one.owner_id, slug="hsc-physics")
    _batch_listing(owner_session, other.batch_id, other.owner_id, slug="hsc-physics")
    owner_session.commit()
    with pytest.raises(sa.exc.IntegrityError, match="uq_batch_listing_owner_slug"):
        _batch_listing(owner_session, second, one.owner_id, slug="hsc-physics")
    owner_session.rollback()
    assert two.owner_id != one.owner_id


def test_live_batch_listing_needs_a_slug(owner_session: Session) -> None:
    """The slug rule holds for batch listings as it does for owners.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    with pytest.raises(sa.exc.IntegrityError, match="ck_batch_listing_slug_when_live"):
        _batch_listing(
            owner_session, teacher.batch_id, teacher.owner_id, status="published"
        )
    owner_session.rollback()


def test_live_batch_listing_needs_a_public_title(owner_session: Session) -> None:
    """A live batch listing carries a public title of 3 to 120 characters.

    A draft may hold none, so a batch never published needs nothing typed.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    _batch_listing(owner_session, teacher.batch_id, teacher.owner_id)
    owner_session.commit()
    for title in (None, "   ", "ab", "  ab  "):
        with pytest.raises(
            sa.exc.IntegrityError, match="ck_batch_listing_public_title_when_live"
        ):
            owner_session.execute(
                sa.text(
                    "UPDATE batch_listing SET status = 'published', "
                    "slug = 'hsc-physics', public_title = :t WHERE batch_id = :b"
                ),
                {"t": title, "b": teacher.batch_id},
            )
        owner_session.rollback()
    with pytest.raises(sa.exc.DataError):
        owner_session.execute(
            sa.text("UPDATE batch_listing SET public_title = :t WHERE batch_id = :b"),
            {"t": "x" * 121, "b": teacher.batch_id},
        )
    owner_session.rollback()
    owner_session.execute(
        sa.text(
            "UPDATE batch_listing SET status = 'published', slug = 'hsc-physics', "
            "public_title = 'HSC Physics' WHERE batch_id = :b"
        ),
        {"b": teacher.batch_id},
    )
    owner_session.commit()


def test_report_targets_name_the_listing_kind(owner_session: Session) -> None:
    """An owner listing and a batch listing are distinct report targets.

    :param owner_session: An arranging session
    :return: None
    """
    labels = owner_session.execute(
        sa.text(
            "SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder) FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'hub_report_target'"
        )
    ).scalar_one()
    assert labels == ["owner_listing", "batch_listing", "media", "review", "reply"]


def test_show_fee_has_no_default(owner_session: Session) -> None:
    """Omitting ``show_fee`` is an error, never a quiet disclosure choice.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    with pytest.raises(sa.exc.IntegrityError) as refusal:
        owner_session.execute(
            sa.text(
                "INSERT INTO batch_listing (batch_id, owner_id, show_schedule) "
                "VALUES (:b, :o, false)"
            ),
            {"b": teacher.batch_id, "o": teacher.owner_id},
        )
    owner_session.rollback()
    assert "show_fee" in str(refusal.value.orig)
    assert type(refusal.value.orig).__name__ == "NotNullViolation"


def test_class_levels_and_curriculum_are_closed_vocabularies(
    owner_session: Session,
) -> None:
    """Unknown levels and curricula are refused.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    with pytest.raises(sa.exc.IntegrityError, match="ck_batch_listing_class_levels"):
        owner_session.execute(
            sa.text(
                "INSERT INTO batch_listing (batch_id, owner_id, show_fee, "
                "show_schedule, class_levels) VALUES (:b, :o, false, false, "
                "ARRAY['class_13'])"
            ),
            {"b": teacher.batch_id, "o": teacher.owner_id},
        )
    owner_session.rollback()
    with pytest.raises(sa.exc.IntegrityError, match="ck_batch_listing_curriculum"):
        owner_session.execute(
            sa.text(
                "INSERT INTO batch_listing (batch_id, owner_id, show_fee, "
                "show_schedule, curriculum) VALUES (:b, :o, false, false, 'ib')"
            ),
            {"b": teacher.batch_id, "o": teacher.owner_id},
        )
    owner_session.rollback()


def test_free_text_lengths_are_checked(owner_session: Session) -> None:
    """An over-long bio is refused by the database.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    _listing(owner_session, teacher.owner_id)
    owner_session.commit()
    with pytest.raises(sa.exc.IntegrityError, match="ck_owner_listing_bio_en"):
        owner_session.execute(
            sa.text("UPDATE owner_listing SET bio_en = :t"), {"t": "x" * 4001}
        )
    owner_session.rollback()


def test_report_is_unique_per_reporter_and_target(owner_session: Session) -> None:
    """One reporter cannot file the same target twice.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    params = {"t": uuid.uuid4(), "a": teacher.account_id}
    insert = sa.text(
        "INSERT INTO hub_report (id, target_kind, target_id, reporter_account_id, "
        "reason) VALUES (gen_random_uuid(), 'owner_listing', :t, :a, 'abusive')"
    )
    owner_session.execute(insert, params)
    owner_session.commit()
    with pytest.raises(sa.exc.IntegrityError, match="uq_hub_report_target_reporter"):
        owner_session.execute(insert, params)
    owner_session.rollback()


def test_moderation_event_is_append_only(
    owner_session: Session, restricted_session: Session
) -> None:
    """The application role may add and read moderation events, not change them.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    event_id = uuid.uuid4()
    restricted_session.execute(
        sa.text(
            "INSERT INTO hub_moderation_event (id, event, target_kind, target_id, "
            "correlation_id) VALUES (:id, 'report_filed', 'owner_listing', :t, 'c1')"
        ),
        {"id": event_id, "t": uuid.uuid4()},
    )
    restricted_session.commit()
    assert (
        restricted_session.execute(
            sa.text("SELECT count(*) FROM hub_moderation_event")
        ).scalar_one()
        == 1
    )

    assert "permission denied" in _refused(
        restricted_session,
        "UPDATE hub_moderation_event SET decision_code = 'x' WHERE id = :id",
        {"id": event_id},
    )
    assert "retention window" in _refused(
        restricted_session,
        "DELETE FROM hub_moderation_event WHERE id = :id",
        {"id": event_id},
    )
    old = uuid.uuid4()
    owner_session.execute(
        sa.text(
            "INSERT INTO hub_moderation_event (id, event, target_kind, target_id, "
            "correlation_id, at) VALUES (:id, 'report_filed', 'owner_listing', "
            ":t, 'c2', :at)"
        ),
        {
            "id": old,
            "t": uuid.uuid4(),
            "at": dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=400),
        },
    )
    owner_session.commit()
    restricted_session.execute(
        sa.text("DELETE FROM hub_moderation_event WHERE id = :id"), {"id": old}
    )
    restricted_session.commit()


def test_the_hub_reader_has_no_grant_on_the_new_tables(
    owner_session: Session,
) -> None:
    """Nothing is public until H2's views grant it.

    :param owner_session: An arranging session
    :return: None
    """
    for table in (
        "owner_listing",
        "batch_listing",
        "hub_report",
        "hub_moderation_event",
    ):
        assert not owner_session.execute(
            sa.text("SELECT has_table_privilege('shikkhok_hub_reader', :t, 'SELECT')"),
            {"t": table},
        ).scalar_one(), table
