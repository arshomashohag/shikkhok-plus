"""The badge as the public views see it: a stored column kept by the app.

``hub_public_owner`` may not read ``enrollment`` or ``attendance``, so the
badge is stored on ``owner_listing.runs_classes``. It is set from
:func:`~app.hub.listings.badge.runs_classes` when the owner saves or
publishes, and daily by ``app.hub.listings.badge_commands``. These tests
hold the stored value to the rule.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import HUB_BADGE_JOB
from app.hub.listings import owner
from app.hub.listings.badge import runs_classes
from app.hub.listings.badge_commands import refresh_all, run_refresh
from app.hub.listings.consent import HUB_CONSENT_VERSION
from app.hub.listings.owner import OwnerListingUpdate
from app.hub.public.db import as_hub_reader
from app.local_time import bangladesh_today
from tests.hub.support import add_attendance, areas, solo_lens

NOW = dt.datetime.now(tz=dt.UTC)
TODAY = bangladesh_today(NOW)


def _qualifying(session: Session) -> TeacherLens:
    """Arrange an owner who earns the badge today.

    :param session: An arranging session
    :return: The owner's lens
    """
    lens = solo_lens(session)
    add_attendance(
        session,
        lens,
        seats=5,
        accepted=5,
        last_recorded=NOW - dt.timedelta(days=2),
    )
    return lens


def _published(session: Session, owner_id: uuid.UUID, slug: str, badge: bool) -> None:
    """Insert a published listing carrying a given stored badge.

    :param session: An arranging session
    :param owner_id: The owner
    :param slug: The slug
    :param badge: The stored ``runs_classes`` value
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "runs_classes, published_at) VALUES "
            "(:o, :slug, 'published', :slug, :badge, now())"
        ),
        {"o": owner_id, "slug": slug, "badge": badge},
    )
    session.commit()


def _stored(session: Session, owner_id: uuid.UUID) -> bool:
    """Read the stored badge.

    :param session: Any session
    :param owner_id: The owner
    :return: The column's value
    """
    value: bool = session.execute(
        sa.text("SELECT runs_classes FROM owner_listing WHERE owner_id = :o"),
        {"o": owner_id},
    ).scalar_one()
    return value


def test_view_value_equals_the_badge_rule_after_refresh(
    owner_session: Session, restricted_session: Session
) -> None:
    """After a refresh the view says what the rule says, true and false.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    earns = _qualifying(owner_session)
    idle = solo_lens(owner_session)
    _published(owner_session, earns.owner_id, "earns-badge", badge=False)
    _published(owner_session, idle.owner_id, "no-badge", badge=True)

    refresh_all(restricted_session, today=TODAY)
    expected = {
        str(earns.owner_id): runs_classes(restricted_session, earns.owner_id, TODAY),
        str(idle.owner_id): runs_classes(restricted_session, idle.owner_id, TODAY),
    }
    restricted_session.commit()
    as_hub_reader(restricted_session)
    shown = {
        str(r.owner_id): r.runs_classes
        for r in restricted_session.execute(
            sa.text("SELECT owner_id, runs_classes FROM hub_public_owner")
        )
    }

    assert expected == {str(earns.owner_id): True, str(idle.owner_id): False}
    assert shown == expected


def test_refresh_command_flips_stale_values_and_stamps_heartbeat(
    owner_session: Session, restricted_session: Session
) -> None:
    """Stale published values flip both ways; other listings are untouched.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    earns = _qualifying(owner_session)
    idle = solo_lens(owner_session)
    _published(owner_session, earns.owner_id, "earns-badge", badge=False)
    _published(owner_session, idle.owner_id, "no-badge", badge=True)
    hidden = _qualifying(owner_session)
    _published(owner_session, hidden.owner_id, "hidden-one", badge=False)
    owner_session.execute(
        sa.text("UPDATE owner_listing SET status = 'hidden' WHERE owner_id = :o"),
        {"o": hidden.owner_id},
    )
    owner_session.commit()

    result = run_refresh(restricted_session, today=TODAY, now=NOW)

    assert (result.changed, result.unchanged) == (2, 0)
    assert _stored(owner_session, earns.owner_id) is True
    assert _stored(owner_session, idle.owner_id) is False
    assert _stored(owner_session, hidden.owner_id) is False
    beat = owner_session.execute(
        sa.text(
            "SELECT last_success_at, cycles_created, cycles_skipped, "
            "periods_failed FROM job_heartbeat WHERE job_name = :j"
        ),
        {"j": HUB_BADGE_JOB},
    ).one()
    assert tuple(beat) == (NOW, 2, 0, 0)

    again = run_refresh(restricted_session, today=TODAY, now=NOW)
    assert (again.changed, again.unchanged) == (0, 2)


def test_save_and_publish_set_the_stored_badge(
    owner_session: Session, restricted_session: Session
) -> None:
    """An owner's save stores the badge, and publishing recomputes it.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = _qualifying(owner_session)
    district, upazila, _ = areas(owner_session)
    owner.get_or_draft(restricted_session, lens)
    assert _stored(owner_session, lens.owner_id) is False

    owner.update(
        restricted_session,
        lens,
        OwnerListingUpdate(
            slug="rahim-sir",
            public_name="Rahim Sir",
            headline_en="Maths for classes 6 to 10",
            bio_bn="গণিত শিক্ষক",
            district_code=district,
            upazila_code=upazila,
        ),
    )
    assert _stored(owner_session, lens.owner_id) is True

    owner_session.execute(
        sa.text("UPDATE owner_listing SET runs_classes = false WHERE owner_id = :o"),
        {"o": lens.owner_id},
    )
    owner_session.commit()
    owner.publish(restricted_session, lens, HUB_CONSENT_VERSION, NOW)

    assert _stored(owner_session, lens.owner_id) is True


def test_save_clears_a_badge_the_owner_no_longer_earns(
    owner_session: Session, restricted_session: Session
) -> None:
    """A save stores false as faithfully as true.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, lens)
    owner_session.execute(
        sa.text("UPDATE owner_listing SET runs_classes = true WHERE owner_id = :o"),
        {"o": lens.owner_id},
    )
    owner_session.commit()

    owner.update(restricted_session, lens, OwnerListingUpdate(headline_en="Maths"))

    assert _stored(owner_session, lens.owner_id) is False
