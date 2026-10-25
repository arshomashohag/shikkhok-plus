"""D5 performs no write, and the absence is asserted [NFR19.57, NFR6.61].

**The design obligation is not to be careful about writes -- it is to
assert their absence** [reliability § 4]. A test comparing table state
across the unit's reads fails on a write added later by someone who has
not read that document, which is worth more than the sentence.

The comparison is over **every table in the schema**, derived rather
than enumerated: a hand-kept list silently stops covering a table a
later migration adds, and the leak shows up as a test that passes while
covering less -- this project's most-documented defect shape.
"""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.analytics.conftest import add_exam, seat_with_ledger
from tests.batches.conftest import TeacherFixture


def _snapshot(session: Session) -> dict[str, int]:
    """Count the rows in every table in the schema.

    **Derived from ``pg_tables`` rather than enumerated.** A hand-kept
    list is one migration away from measuring less than it claims.

    :param session: A session able to read the catalogue
    :return: Row count per table
    """
    tables = [
        row[0]
        for row in session.execute(
            sa.text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' "
                "AND tablename <> 'alembic_version'"
            )
        )
    ]
    counts: dict[str, int] = {}
    for table in tables:
        quoted = sa.sql.quoted_name(table, quote=True)
        counts[table] = session.execute(
            sa.select(sa.func.count()).select_from(sa.table(quoted))
        ).scalar_one()
    return counts


def test_neither_read_changes_any_table(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """Row counts are identical before and after both reads.

    The fixture carries a dues row, an earnings figure, a trend and an
    upcoming exam, so every code path this unit has actually runs --
    a read over an empty database would write nothing trivially.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session fixture data is written on
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="Owes something",
        entries=[
            ("charge", "2026-03", "500.00"),
            ("receipt", "2026-03", "500.00"),
            ("charge", "2026-04", "800.00"),
            ("receipt", "2026-04", "200.00"),
        ],
    )
    add_exam(
        owner_session,
        batch_id=signed_in_teacher.batch_id,
        title="Upcoming",
        date=dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=3),
    )
    owner_session.commit()

    headers = {"Authorization": f"Bearer {teacher_token}"}
    before = _snapshot(owner_session)

    assert client.get("/v1/me/dues", headers=headers).status_code == 200
    assert client.get("/v1/me/overview", headers=headers).status_code == 200

    owner_session.expire_all()
    after = _snapshot(owner_session)

    assert after == before, (
        "a D5 read changed table state. This unit is read-only against "
        "every table it touches [NFR19.57]; the difference is "
        f"{ {k: (before[k], after[k]) for k in before if before[k] != after[k]} }."
    )


def test_the_snapshot_helper_would_notice_a_write(
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
) -> None:
    """The positive control: the comparison is not vacuous.

    Without this, a helper that returned an empty dict -- or one whose
    table list came back empty -- would make the test above pass over
    nothing, which is this project's most-repeated failure shape.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session fixture data is written on
    :param signed_in_teacher: The teacher whose batch the seat joins
    :return: None
    """
    before = _snapshot(owner_session)
    assert before, "the snapshot found no tables at all"

    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="A write",
        entries=[("charge", "2027-01", "100.00")],
    )
    owner_session.expire_all()

    assert _snapshot(owner_session) != before
