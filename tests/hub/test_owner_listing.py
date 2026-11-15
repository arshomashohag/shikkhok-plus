"""The owner's listing: drafts, consent, publishing and what never publishes."""

from __future__ import annotations

import datetime as dt
import inspect
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.phone import contains_phone
from app.db.models import OwnerListing
from app.errors import ConflictError, ValidationError
from app.hub.listings import owner
from app.hub.listings.checklist import owner_checklist, owner_publishable
from app.hub.listings.consent import HUB_CONSENT_VERSION
from app.hub.listings.owner import OwnerListingUpdate
from tests.hub.support import areas, centre_lens, solo_lens

NOW = dt.datetime(2026, 11, 14, 9, 0, tzinfo=dt.UTC)


def _complete(session: Session, lens, slug: str = "rahim-sir") -> None:
    """Fill every required field of the lens's draft.

    :param session: The application role's session
    :param lens: The owner
    :param slug: The slug to claim
    :return: None
    """
    district, upazila, _ = areas(session)
    owner.get_or_draft(session, lens)
    owner.update(
        session,
        lens,
        OwnerListingUpdate(
            slug=slug,
            public_name="Rahim Sir",
            headline_en="Maths for classes 6 to 10",
            bio_bn="গণিত শিক্ষক",
            district_code=district,
            upazila_code=upazila,
        ),
    )


def test_get_or_draft_creates_one_draft_and_is_idempotent(
    owner_session: Session, restricted_session: Session
) -> None:
    """Two calls leave exactly one draft, named from the first batch.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    owner_session.execute(
        sa.text("UPDATE batch SET teacher_display_name = '  ' WHERE owner_id = :o"),
        {"o": lens.owner_id},
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO batch (id, owner_id, name, teacher_display_name, "
            "marksheet_visible, active, created_at) VALUES "
            "(gen_random_uuid(), :o, 'B2', 'Rahim Sir', true, true, now())"
        ),
        {"o": lens.owner_id},
    )
    owner_session.commit()

    first = owner.get_or_draft(restricted_session, lens)
    second = owner.get_or_draft(restricted_session, lens)

    assert first.status == "draft"
    assert first.public_name == "Rahim Sir"
    assert first.slug is None
    assert second.owner_id == first.owner_id
    count = restricted_session.execute(
        sa.text("SELECT count(*) FROM owner_listing WHERE owner_id = :o"),
        {"o": lens.owner_id},
    ).scalar_one()
    assert count == 1


def test_centre_draft_is_prefilled_from_the_centre_name(
    owner_session: Session, restricted_session: Session
) -> None:
    """A centre's draft takes the centre's name, not a batch's.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = centre_lens(owner_session)

    assert owner.get_or_draft(restricted_session, lens).public_name == "Udoy Coaching"


def test_draft_name_prefill_never_reads_profile(
    owner_session: Session, restricted_session: Session
) -> None:
    """A private profile name never reaches a public draft.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    owner_session.execute(
        sa.text("UPDATE batch SET teacher_display_name = NULL WHERE owner_id = :o"),
        {"o": lens.owner_id},
    )
    owner_session.execute(
        sa.text("INSERT INTO profile (account_id, self_name) VALUES (:a, 'PRIVATE-X')"),
        {"a": lens.account_id},
    )
    owner_session.commit()

    listing = owner.get_or_draft(restricted_session, lens)

    assert listing.public_name == ""
    assert "PRIVATE-X" not in repr(vars(listing))


def test_publish_refuses_wrong_consent_version(
    owner_session: Session, restricted_session: Session
) -> None:
    """A stale consent text is refused before anything else.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    _complete(restricted_session, lens)

    with pytest.raises(ValidationError) as raised:
        owner.publish(restricted_session, lens, "2020-01-01", NOW)

    assert raised.value.code == "HUB_CONSENT_OUTDATED"
    assert owner.get_or_draft(restricted_session, lens).status == "draft"


def test_publish_refuses_incomplete(
    owner_session: Session, restricted_session: Session
) -> None:
    """The refusal names exactly the checklist keys still open.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, lens)
    owner.update(restricted_session, lens, OwnerListingUpdate(public_name="Rahim"))

    with pytest.raises(ValidationError) as raised:
        owner.publish(restricted_session, lens, HUB_CONSENT_VERSION, NOW)

    assert raised.value.code == "HUB_LISTING_INCOMPLETE"
    assert raised.value.details == {"missing": "slug,area,headline,bio"}


def test_publish_records_consent_version_time_and_account(
    owner_session: Session, restricted_session: Session
) -> None:
    """Publishing stamps who agreed to which text, and when.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    _complete(restricted_session, lens)

    live = owner.publish(restricted_session, lens, HUB_CONSENT_VERSION, NOW)

    assert live.status == "published"
    assert live.consent_version == HUB_CONSENT_VERSION
    assert live.consent_at == NOW
    assert live.consent_by_account_id == lens.account_id
    assert live.published_at == NOW


def test_suspended_listing_cannot_be_published_or_edited(
    owner_session: Session, restricted_session: Session
) -> None:
    """Only a moderator lifts a suspension; the owner cannot route around it.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    _complete(restricted_session, lens)
    owner_session.execute(
        sa.text(
            "UPDATE owner_listing SET status = 'suspended', suspended_at = now(), "
            "suspension_reason_code = 'fake' WHERE owner_id = :o"
        ),
        {"o": lens.owner_id},
    )
    owner_session.commit()

    for attempt in (
        lambda: owner.publish(restricted_session, lens, HUB_CONSENT_VERSION, NOW),
        lambda: owner.update(
            restricted_session, lens, OwnerListingUpdate(public_name="New")
        ),
        lambda: owner.unpublish(restricted_session, lens, NOW),
    ):
        with pytest.raises(ConflictError) as raised:
            attempt()
        assert raised.value.code == "HUB_LISTING_SUSPENDED"


def test_unpublish_sets_hidden_and_republish_is_allowed(
    owner_session: Session, restricted_session: Session
) -> None:
    """Hiding is reversible by the owner.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    _complete(restricted_session, lens)
    owner.publish(restricted_session, lens, HUB_CONSENT_VERSION, NOW)

    assert owner.unpublish(restricted_session, lens, NOW).status == "hidden"
    again = owner.publish(restricted_session, lens, HUB_CONSENT_VERSION, NOW)
    assert again.status == "published"


def test_slug_taken_by_other_owner_is_conflict(
    owner_session: Session, restricted_session: Session
) -> None:
    """A slug is one owner's; availability ignores the asker's own claim.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    first = solo_lens(owner_session)
    second = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, first)
    owner.get_or_draft(restricted_session, second)
    owner.update(restricted_session, first, OwnerListingUpdate(slug="rahim-sir"))

    assert owner.slug_available(restricted_session, "rahim-sir", first) is True
    assert owner.slug_available(restricted_session, "rahim-sir", second) is False
    with pytest.raises(ConflictError) as raised:
        owner.update(restricted_session, second, OwnerListingUpdate(slug="rahim-sir"))
    assert raised.value.code == "HUB_SLUG_TAKEN"


@pytest.mark.parametrize("slug", ["ab", "Rahim", "has space", "x" * 61, "র"])
def test_malformed_slug_is_refused_before_the_database(
    owner_session: Session, restricted_session: Session, slug: str
) -> None:
    """The slug pattern is enforced in the service.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param slug: A slug outside ``^[a-z0-9-]{3,60}$``
    :return: None
    """
    lens = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, lens)

    with pytest.raises(ValidationError) as raised:
        owner.update(restricted_session, lens, OwnerListingUpdate(slug=slug))
    assert raised.value.code == "HUB_SLUG_INVALID"
    assert owner.slug_available(restricted_session, slug, lens) is False


def test_upazila_must_belong_to_district(
    owner_session: Session, restricted_session: Session
) -> None:
    """An upazila under a different district is refused.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, lens)
    _, upazila, other = areas(restricted_session)

    with pytest.raises(ValidationError) as raised:
        owner.update(
            restricted_session,
            lens,
            OwnerListingUpdate(district_code=other, upazila_code=upazila),
        )
    assert raised.value.code == "HUB_AREA_MISMATCH"


@pytest.mark.parametrize(
    "text",
    ["Call 01711234567", "+880 1711-234567", "০১৭১১২৩৪৫৬৭ এ ফোন করুন", "8801711234567"],
)
def test_free_text_containing_a_phone_number_is_refused(
    owner_session: Session, restricted_session: Session, text: str
) -> None:
    """A number belongs in ``public_contact_phone`` and nowhere else.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param text: Free text carrying a number
    :return: None
    """
    lens = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, lens)

    with pytest.raises(ValidationError) as raised:
        owner.update(restricted_session, lens, OwnerListingUpdate(bio_en=text))
    assert raised.value.code == "HUB_TEXT_CONTAINS_CONTACT"


def test_public_contact_phone_is_stored_canonical(
    owner_session: Session, restricted_session: Session
) -> None:
    """The one place a number may go, in its one stored form.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, lens)

    listing = owner.update(
        restricted_session,
        lens,
        OwnerListingUpdate(public_contact_phone="01711-234567"),
    )

    assert listing.public_contact_phone == "+8801711234567"


def test_street_address_is_for_a_centre_only(
    owner_session: Session, restricted_session: Session
) -> None:
    """A solo tutor's street address is refused; a centre's is kept.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    solo = solo_lens(owner_session)
    centre = centre_lens(owner_session)
    owner.get_or_draft(restricted_session, solo)
    owner.get_or_draft(restricted_session, centre)

    with pytest.raises(ValidationError) as raised:
        owner.update(
            restricted_session, solo, OwnerListingUpdate(street_address="1 Rd")
        )
    assert raised.value.code == "HUB_ADDRESS_CENTRE_ONLY"
    kept = owner.update(
        restricted_session, centre, OwnerListingUpdate(street_address="1 Rd")
    )
    assert kept.street_address == "1 Rd"


def test_update_none_leaves_fields_unchanged(
    owner_session: Session, restricted_session: Session
) -> None:
    """``None`` means unchanged, so a partial update never erases.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    _complete(restricted_session, lens)

    after = owner.update(restricted_session, lens, OwnerListingUpdate(bio_en="More"))

    assert after.public_name == "Rahim Sir"
    assert after.slug == "rahim-sir"
    assert after.bio_en == "More"


def test_checklist_reports_each_key() -> None:
    """The checklist has six keys in a fixed order and gates publishing.

    :return: None
    """
    empty = OwnerListing(owner_id=uuid.uuid4(), public_name="", teaching_mode=[])
    items = owner_checklist(empty)

    assert [i.key for i in items] == [
        "public_name",
        "slug",
        "area",
        "headline",
        "bio",
        "contact_or_none",
    ]
    assert owner_publishable(items) is False
    assert owner_publishable([i for i in items if i.done]) is True


def test_never_published_owner_is_draft_everywhere(
    owner_session: Session, restricted_session: Session
) -> None:
    """Nothing but ``publish`` ever sets ``published`` (Review Focus 1).

    Every other public function is called on a fresh draft, and the status is
    re-read from the database after each.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    _complete(restricted_session, lens)
    public = {
        name
        for name, fn in inspect.getmembers(owner, inspect.isfunction)
        if fn.__module__ == owner.__name__ and not name.startswith("_")
    }
    assert public == {
        "get_or_draft",
        "publish",
        "slug_available",
        "unpublish",
        "update",
    }

    def status() -> str:
        restricted_session.expire_all()
        return str(
            restricted_session.execute(
                sa.text("SELECT status FROM owner_listing WHERE owner_id = :o"),
                {"o": lens.owner_id},
            ).scalar_one()
        )

    owner.get_or_draft(restricted_session, lens)
    assert status() == "draft"
    owner.update(restricted_session, lens, OwnerListingUpdate(bio_en="x"))
    assert status() == "draft"
    owner.slug_available(restricted_session, "rahim-sir", lens)
    assert status() == "draft"
    owner.unpublish(restricted_session, lens, NOW)
    assert status() == "draft"
    owner.publish(restricted_session, lens, HUB_CONSENT_VERSION, NOW)
    assert status() == "published"
    owner.unpublish(restricted_session, lens, NOW)
    assert status() == "hidden"
    # a hidden listing is not draft, and update never republishes it.
    owner.update(restricted_session, lens, OwnerListingUpdate(bio_en="y"))
    assert status() == "hidden"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Classes 6 to 10, batch of 25",
        "Fee 1500 per month, since 2015",
        "A+ results",
        "Batches 2013 - 2014 - 2015",
        "Fee 1500 1600 1700 1800 taka",
        "2010-2015 2016-2020",
    ],
)
def test_ordinary_numbers_are_not_mistaken_for_a_phone(text: str) -> None:
    """Years, fees and class ranges stay writable.

    :param text: Text with digits but no phone number
    :return: None
    """
    assert contains_phone(text) is False


def test_slug_cannot_carry_a_phone_number(
    owner_session: Session, restricted_session: Session
) -> None:
    """A number may not be smuggled into the web address.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, lens)

    with pytest.raises(ValidationError) as raised:
        owner.update(
            restricted_session, lens, OwnerListingUpdate(slug="rahim-01711234567")
        )
    assert raised.value.code == "HUB_TEXT_CONTAINS_CONTACT"


def test_live_listing_cannot_be_edited_into_incompleteness(
    owner_session: Session, restricted_session: Session
) -> None:
    """Blanking a required field on a live listing is refused and not saved.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    _complete(restricted_session, lens)
    owner.publish(restricted_session, lens, HUB_CONSENT_VERSION, NOW)

    with pytest.raises(ValidationError) as raised:
        owner.update(restricted_session, lens, OwnerListingUpdate(headline_en=""))
    assert raised.value.code == "HUB_LISTING_INCOMPLETE"
    assert raised.value.details == {"missing": "headline"}
    assert owner.get_or_draft(restricted_session, lens).headline_en is not None


def test_publish_scans_the_prefilled_name_for_a_phone(
    owner_session: Session, restricted_session: Session
) -> None:
    """A number in a name prefilled from a batch is caught at publish.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    _complete(restricted_session, lens)
    owner_session.execute(
        sa.text(
            "UPDATE owner_listing SET public_name = 'Rahim 01711234567' "
            "WHERE owner_id = :o"
        ),
        {"o": lens.owner_id},
    )
    owner_session.commit()

    with pytest.raises(ValidationError) as raised:
        owner.publish(restricted_session, lens, HUB_CONSENT_VERSION, NOW)
    assert raised.value.code == "HUB_TEXT_CONTAINS_CONTACT"


def test_racing_slug_claim_is_a_conflict(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rival claiming the slug after the availability check still loses cleanly.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param monkeypatch: Used to slip the rival in after the check
    :return: None
    """
    rival = solo_lens(owner_session)
    lens = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, lens)
    owner.get_or_draft(restricted_session, rival)
    real = owner.slug_available

    def check_then_lose(session: Session, slug: str, who) -> bool:
        answer = real(session, slug, who)
        owner_session.execute(
            sa.text("UPDATE owner_listing SET slug = :s WHERE owner_id = :o"),
            {"s": slug, "o": rival.owner_id},
        )
        owner_session.commit()
        return answer

    monkeypatch.setattr(owner, "slug_available", check_then_lose)

    with pytest.raises(ConflictError) as raised:
        owner.update(restricted_session, lens, OwnerListingUpdate(slug="rahim-sir"))
    assert raised.value.code == "HUB_SLUG_TAKEN"
