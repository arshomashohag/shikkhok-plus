"""The platform at a glance: aggregate counts, no individual records.

Every number here is a ``count(*)`` or a ``count(DISTINCT ...)``. None of
the statements selects a name, a phone number, an id or a row a teacher
wrote, so the administrator boundary holds by construction: there is
nothing individual in the result to leak [TC-14, D-6].

Each count is a single indexed or small-table scan; at the hundred-
teacher target the whole overview is a few milliseconds, and it is read
by one person on demand rather than on a schedule.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.clients import PLATFORMS, Platform

__all__ = [
    "AppVersion",
    "Overview",
    "PlatformUsage",
    "overview",
]


@dataclass(frozen=True, slots=True)
class PlatformUsage:
    """How many accounts use one app.

    :ivar platform: ``android`` or ``web``
    :ivar accounts: Accounts ever seen on it
    :ivar active_7_days: Seen on it in the last seven days
    :ivar active_30_days: Seen on it in the last thirty days
    """

    platform: Platform
    accounts: int
    active_7_days: int
    active_30_days: int


@dataclass(frozen=True, slots=True)
class AppVersion:
    """How many accounts reported one app version recently.

    :ivar platform: ``android`` or ``web``
    :ivar version: The version string
    :ivar accounts: Accounts seen on it in the last thirty days
    """

    platform: Platform
    version: str
    accounts: int


@dataclass(frozen=True, slots=True)
class Overview:
    """The platform at a glance.

    :ivar generated_at: When these figures were read
    :ivar accounts: Accounts that have signed in at least once
    :ivar new_7_days: Of those, first signed in during the last 7 days
    :ivar new_30_days: Of those, first signed in during the last 30 days
    :ivar active_7_days: Seen on any app in the last 7 days
    :ivar active_30_days: Seen on any app in the last 30 days
    :ivar teachers: Accounts that own a solo-tutor workspace
    :ivar centres: Coaching centres
    :ivar centre_members: Accounts holding a live centre membership
    :ivar students: Accounts holding an accepted student seat
    :ivar guardians: Accounts holding an accepted guardian seat
    :ivar batches: Active batches
    :ivar seats: Accepted student seats in active batches
    :ivar platforms: Usage per app
    :ivar both_platforms: Accounts seen on both apps
    :ivar no_platform: Signed-in accounts no app has reported yet
    :ivar versions: App versions seen in the last 30 days
    :ivar help_open: Tickets waiting on support
    :ivar help_answered: Tickets waiting on the requester
    :ivar help_closed: Closed tickets
    """

    generated_at: dt.datetime
    accounts: int
    new_7_days: int
    new_30_days: int
    active_7_days: int
    active_30_days: int
    teachers: int
    centres: int
    centre_members: int
    students: int
    guardians: int
    batches: int
    seats: int
    platforms: tuple[PlatformUsage, ...]
    both_platforms: int
    no_platform: int
    versions: tuple[AppVersion, ...]
    help_open: int
    help_answered: int
    help_closed: int


_COUNTS: Final = sa.text(
    "SELECT "
    "(SELECT count(*) FROM account WHERE activated_at IS NOT NULL) AS accounts, "
    "(SELECT count(*) FROM account WHERE activated_at > :d7) AS new_7, "
    "(SELECT count(*) FROM account WHERE activated_at > :d30) AS new_30, "
    "(SELECT count(DISTINCT account_id) FROM account_client "
    "  WHERE last_seen_at > :d7) AS active_7, "
    "(SELECT count(DISTINCT account_id) FROM account_client "
    "  WHERE last_seen_at > :d30) AS active_30, "
    "(SELECT count(DISTINCT account_id) FROM owner "
    "  WHERE kind = 'teacher' AND account_id IS NOT NULL) AS teachers, "
    "(SELECT count(*) FROM owner WHERE kind = 'organisation') AS centres, "
    "(SELECT count(DISTINCT account_id) FROM owner_member "
    "  WHERE decision = 'accepted' AND revoked_at IS NULL "
    "  AND account_id IS NOT NULL) AS centre_members, "
    "(SELECT count(DISTINCT student_account_id) FROM enrollment "
    "  WHERE student_decision = 'accepted') AS students, "
    "(SELECT count(DISTINCT guardian_account_id) FROM enrollment "
    "  WHERE guardian_decision = 'accepted') AS guardians, "
    "(SELECT count(*) FROM batch WHERE active) AS batches, "
    "(SELECT count(*) FROM enrollment e JOIN batch b ON b.id = e.batch_id "
    "  WHERE b.active AND e.student_decision = 'accepted') AS seats, "
    "(SELECT count(*) FROM (SELECT account_id FROM account_client "
    "  GROUP BY account_id HAVING count(DISTINCT platform) > 1) both_) "
    "  AS both_platforms, "
    "(SELECT count(*) FROM account a WHERE a.activated_at IS NOT NULL "
    "  AND NOT EXISTS (SELECT 1 FROM account_client c "
    "  WHERE c.account_id = a.id)) AS no_platform, "
    "(SELECT count(*) FROM help_ticket WHERE status = 'open') AS help_open, "
    "(SELECT count(*) FROM help_ticket WHERE status = 'answered') "
    "  AS help_answered, "
    "(SELECT count(*) FROM help_ticket WHERE status = 'closed') AS help_closed"
)

_PLATFORMS: Final = sa.text(
    "SELECT platform, count(*) AS accounts, "
    "count(*) FILTER (WHERE last_seen_at > :d7) AS active_7, "
    "count(*) FILTER (WHERE last_seen_at > :d30) AS active_30 "
    "FROM account_client GROUP BY platform"
)

_VERSIONS: Final = sa.text(
    "SELECT platform, app_version, count(*) AS accounts FROM account_client "
    "WHERE last_seen_at > :d30 AND app_version IS NOT NULL "
    "GROUP BY platform, app_version "
    "ORDER BY platform, count(*) DESC, app_version LIMIT 50"
)


def overview(session: Session, now: dt.datetime | None = None) -> Overview:
    """Read the platform's aggregate figures.

    :param session: The session to read through
    :param now: The moment the windows end at, or None for the clock
    :return: The figures
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    windows = {
        "d7": moment - dt.timedelta(days=7),
        "d30": moment - dt.timedelta(days=30),
    }
    counts = session.execute(_COUNTS, windows).one()
    usage = {r.platform: r for r in session.execute(_PLATFORMS, windows)}
    platforms = tuple(
        PlatformUsage(
            platform=platform,
            accounts=usage[platform].accounts if platform in usage else 0,
            active_7_days=usage[platform].active_7 if platform in usage else 0,
            active_30_days=usage[platform].active_30 if platform in usage else 0,
        )
        for platform in PLATFORMS
    )
    versions = tuple(
        AppVersion(platform=r.platform, version=r.app_version, accounts=r.accounts)
        for r in session.execute(_VERSIONS, windows)
    )
    return Overview(
        generated_at=moment,
        accounts=counts.accounts,
        new_7_days=counts.new_7,
        new_30_days=counts.new_30,
        active_7_days=counts.active_7,
        active_30_days=counts.active_30,
        teachers=counts.teachers,
        centres=counts.centres,
        centre_members=counts.centre_members,
        students=counts.students,
        guardians=counts.guardians,
        batches=counts.batches,
        seats=counts.seats,
        platforms=platforms,
        both_platforms=counts.both_platforms,
        no_platform=counts.no_platform,
        versions=versions,
        help_open=counts.help_open,
        help_answered=counts.help_answered,
        help_closed=counts.help_closed,
    )
