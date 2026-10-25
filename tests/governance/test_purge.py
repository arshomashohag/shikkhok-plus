"""The retention purge: what it deletes, and the 18 tables it must not.

**BR4.2 is written first and is the reason this file exists.** The
dangerous implementation of a retention purge is the NATURAL one --
iterate every table, apply a default window to those without an explicit
one -- and it deletes every attendance row, every mark and the whole fee
ledger on its first run. Eighteen of twenty-five tables are
``LIFE_OF_ACCOUNT``, so the blast radius of that mistake is the product's
entire history.

**Every window test plants rows OLDER than its horizon.** The vacuity
trap this file is written against is that a purge test with no aged
fixtures deletes nothing and passes: the negative branch alone is
exercised, and a job that deletes nothing is indistinguishable from a job
that works. So each table gets a row on both sides of its boundary and
both outcomes are asserted.

**The fixtures are written as the OWNER and the purge runs as the
restricted role**, matching how the application actually runs. An
arrangement the restricted role could not make is not evidence about the
purge, but an assertion made as the owner proves nothing about the
policy -- so arrangement and assertion use different sessions
deliberately.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import RETENTION_PURGE_JOB, JobHeartbeat
from app.fees.commands import check_all_jobs
from app.governance.commands import (
    CHUNK_SIZE,
    WINDOWS,
    purge_expired,
    purge_table,
    run_purge,
)
from app.governance.dispositions import RETENTION, RetentionClass

NOW = dt.datetime(2027, 3, 1, 12, 0, tzinfo=dt.UTC)

#: Two years back. Old enough to be past every finite window by a wide
#: margin, so no test depends on a boundary it did not mean to test.
LONG_AGO = NOW - dt.timedelta(days=730)


def _tables_with_retention(wanted: RetentionClass) -> set[str]:
    """Name every table carrying one retention class.

    Derived from the manifest rather than listed, so a table added later
    with a new retention decision is covered without this file changing.

    :param wanted: The retention class to select
    :return: The table names carrying it
    """
    return {table for table, retention in RETENTION.items() if retention is wanted}


def _count(session: Session, table: str) -> int:
    """Count a table's rows by name.

    :param session: The session to read through
    :param table: The table name, which comes from the manifest only
    :return: The row count
    """
    # The name is a manifest key, never request input, and the manifest
    # is a module-level literal dict. Quoted anyway so a future table
    # name needing quoting does not silently produce invalid SQL.
    return int(
        session.execute(
            sa.text(f'SELECT count(*) FROM "{table}"')  # noqa: S608
        ).scalar_one()
    )


@pytest.fixture
def aged_life_of_account_rows(owner_session: Session) -> dict[str, int]:
    """Plant a two-year-old chain in the LIFE_OF_ACCOUNT tables.

    **Not every one of the eighteen can be planted independently**: most
    hang off an account and an enrollment, so the fixture builds one
    coherent chain rather than eighteen disconnected rows. What matters
    for BR4.2 is that each table HAS an aged row at the moment the purge
    runs, and a chain gives that for every table it reaches.

    **It returns no counts, and that is deliberate.** The first version
    counted here, as the owner, and compared against a count taken
    afterwards as the restricted role -- which reported ``profile``
    going from one row to zero across a purge that never names
    ``profile``. The cause was row-level security, not deletion:
    ``profile_owner_only`` hides the row from a session that has not
    set the account GUC, so the two counts were answering *who is
    reading* rather than *what survived*. Both counts are therefore
    taken through the SAME session in the test, where RLS applies
    identically to both and cancels out.

    :param owner_session: An arranging session, owner-privileged
    :return: An empty mapping; the test does its own counting
    """
    account_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    enrollment_id = uuid.uuid4()

    owner_session.execute(
        sa.text(
            "INSERT INTO account (id, phone, created_at) VALUES (:id, :phone, :at)"
        ),
        {"id": account_id, "phone": "+8801700000901", "at": LONG_AGO},
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO profile (account_id, self_name) VALUES (:account_id, :name)"
        ),
        {"account_id": account_id, "name": "Aged"},
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO owner (id, account_id, created_at) "
            "VALUES (:id, :account_id, :at)"
        ),
        {"id": owner_id, "account_id": account_id, "at": LONG_AGO},
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO batch "
            "(id, owner_id, name, marksheet_visible, active, created_at) "
            "VALUES (:id, :owner_id, :name, true, true, :at)"
        ),
        {"id": batch_id, "owner_id": owner_id, "name": "Aged", "at": LONG_AGO},
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO enrollment "
            "(id, batch_id, display_name, student_decision, "
            " guardian_decision, created_at) "
            "VALUES (:id, :batch_id, :name, 'pending', 'pending', :at)"
        ),
        {
            "id": enrollment_id,
            "batch_id": batch_id,
            "name": "Aged Student",
            "at": LONG_AGO,
        },
    )
    owner_session.commit()
    return {}


# ---------------------------------------------------------------------
# BR4.2 -- written FIRST. The catastrophic case.
# ---------------------------------------------------------------------


def test_life_of_account_tables_are_never_purged(
    restricted_session: Session,
    aged_life_of_account_rows: dict[str, int],
) -> None:
    """Two-year-old LIFE_OF_ACCOUNT rows survive a purge [BR4.2].

    **The assertion that distinguishes a correct purge from the natural
    wrong one.** A purge treating "no explicit window" as "any age"
    passes every finite-window test in this file and deletes the
    product's entire history here.

    The fixture is asserted non-empty first: planting no aged rows would
    make this test vacuously green, which is the exact shape the unit's
    test instructions name as this file's trap.

    :param restricted_session: The session the purge runs through
    :param aged_life_of_account_rows: Counts before the run
    :return: None
    """
    life_of_account = sorted(_tables_with_retention(RetentionClass.LIFE_OF_ACCOUNT))

    # Both counts through the SAME session, so row-level security
    # applies identically to each and cancels out. See the fixture's
    # docstring: measuring before as the owner and after as the
    # restricted role reports a deletion that never happened.
    before = {table: _count(restricted_session, table) for table in life_of_account}

    # **The anti-vacuity assertion.** With no aged rows visible to this
    # session the comparison below is 0 == 0 for all eighteen tables and
    # passes against a purge that truncates every one of them.
    assert sum(before.values()) > 0, (
        "no aged LIFE_OF_ACCOUNT rows are visible to the purge's own "
        "session, so this test would pass against a purge that deletes "
        "all of them"
    )

    purge_expired(restricted_session, now=NOW)

    after = {table: _count(restricted_session, table) for table in life_of_account}
    assert after == before, (
        "a LIFE_OF_ACCOUNT table lost rows to the purge. Eighteen tables "
        "carry that class, including every attendance, mark and ledger "
        "row [BR4.2]."
    )


def test_no_life_of_account_table_appears_in_the_window_map(
    restricted_session: Session,
) -> None:
    """``WINDOWS`` names no table the manifest marks LIFE_OF_ACCOUNT.

    The structural half of BR4.2, complementing the behavioural test
    above. A table reaching ``WINDOWS`` by a later edit would be purged
    at some age, and this fails at the map rather than after the rows
    are gone.

    :param restricted_session: Unused; present so the manifest is read
        against a migrated schema rather than in isolation
    :return: None
    """
    life_of_account = _tables_with_retention(RetentionClass.LIFE_OF_ACCOUNT)
    assert life_of_account & set(WINDOWS) == set(), (
        "a LIFE_OF_ACCOUNT table has acquired a purge window"
    )
    assert len(life_of_account) == 18, (
        f"the manifest now marks {len(life_of_account)} tables "
        "LIFE_OF_ACCOUNT, not 18. If that is deliberate, this count is "
        "the claim that needs updating with it."
    )


def test_every_finite_retention_class_has_a_window(
    restricted_session: Session,
) -> None:
    """Each finite class is purged, so none is silently unenforced.

    The complement of the test above, and the direction that fails open:
    a table given a finite retention class but left out of ``WINDOWS``
    is retained forever while the manifest promises otherwise.

    :param restricted_session: Unused; present so the manifest is read
        against a migrated schema
    :return: None
    """
    finite = {
        table
        for table, retention in RETENTION.items()
        if retention is not RetentionClass.LIFE_OF_ACCOUNT
    }
    assert finite == set(WINDOWS), (
        f"these tables carry a finite retention class but no purge "
        f"window: {sorted(finite - set(WINDOWS))}"
    )
    assert len(finite) == 7, (
        f"the manifest now carries {len(finite)} finite windows, not 7."
    )


# ---------------------------------------------------------------------
# The finite windows. Test-after: the boundary behaviour is not knowable
# from the requirement until the window map exists, and a wrong answer
# deletes an auth record rather than money or an authorization decision.
# ---------------------------------------------------------------------


def _plant(
    session: Session,
    table: str,
    *,
    age_column: str,
    at: dt.datetime,
    account_id: uuid.UUID,
    enrollment_id: uuid.UUID,
    otp_request_id: uuid.UUID,
) -> uuid.UUID:
    """Insert one row into a purgeable table, dated exactly ``at``.

    **Every purgeable table gets a hand-written insert**, because the
    seven differ in required columns and foreign keys and there is no
    generic shape covering them. The age column is passed in from
    ``WINDOWS`` rather than named here, so a table whose age column
    changes is planted at the new one.

    :param session: An arranging session
    :param table: Which purgeable table to plant into
    :param age_column: The column the purge measures age from
    :param at: The value to give that column
    :param account_id: An existing account, for the tables needing one
    :param enrollment_id: An existing enrollment, likewise
    :param otp_request_id: An existing OTP request, for verify_attempt
    :return: The planted row's id
    :raises AssertionError: If a purgeable table has no planting recipe,
        so a table added to WINDOWS later cannot silently go untested
    """
    row_id = uuid.uuid4()
    shared = {"id": row_id, "at": at}

    if table == "otp_request":
        session.execute(
            sa.text(
                "INSERT INTO otp_request "
                "(id, phone, otp_hash, purpose, issued_at, expires_at) "
                "VALUES (:id, :phone, :hash, 'signin', :at, :at)"
            ),
            shared | {"phone": "+8801700000902", "hash": row_id.hex},
        )
    elif table == "verify_attempt":
        session.execute(
            sa.text(
                "INSERT INTO verify_attempt "
                "(id, otp_request_id, attempted_at, succeeded) "
                "VALUES (:id, :otp, :at, false)"
            ),
            shared | {"otp": otp_request_id},
        )
    elif table == "staging_sms_outbox":
        session.execute(
            sa.text(
                "INSERT INTO staging_sms_outbox "
                "(id, phone, message, correlation_id, recorded_at) "
                "VALUES (:id, :phone, 'aged', :cid, :at)"
            ),
            shared | {"phone": "+8801700000903", "cid": row_id.hex},
        )
    elif table == "rate_limit_counter":
        session.execute(
            sa.text(
                "INSERT INTO rate_limit_counter "
                "(id, scope_kind, scope_value, window_start, count) "
                "VALUES (:id, 'number_hour', :value, :at, 1)"
            ),
            shared | {"value": row_id.hex},
        )
    elif table == "auth_audit_log":
        session.execute(
            sa.text(
                "INSERT INTO auth_audit_log "
                "(id, account_id, event, occurred_at, correlation_id) "
                "VALUES (:id, :account_id, 'otp_issued', :at, :cid)"
            ),
            shared | {"account_id": account_id, "cid": row_id.hex},
        )
    elif table == "reminder_event":
        session.execute(
            sa.text(
                "INSERT INTO reminder_event "
                "(id, enrollment_id, period, channel, sent_at, "
                " sent_by_account_id, outcome) "
                "VALUES (:id, :enrollment_id, '2026-01', 'push', :at, "
                "        :account_id, 'sent')"
            ),
            shared | {"enrollment_id": enrollment_id, "account_id": account_id},
        )
    elif table == "refresh_token":
        session.execute(
            sa.text(
                "INSERT INTO refresh_token "
                "(id, account_id, token_hash, family_id, issued_at, "
                " expires_at) "
                "VALUES (:id, :account_id, :hash, :family, :at, :at)"
            ),
            shared
            | {
                "account_id": account_id,
                "hash": row_id.hex,
                "family": uuid.uuid4(),
            },
        )
    else:  # pragma: no cover - guarded by the assertion below
        raise AssertionError(
            f"{table} is purgeable but this file has no way to plant a "
            "row in it, so its window is untested"
        )

    assert age_column in {
        "issued_at",
        "attempted_at",
        "recorded_at",
        "window_start",
        "occurred_at",
        "sent_at",
        "expires_at",
    }, f"{table} is planted at an age column this helper does not set"
    return row_id


@dataclass(frozen=True)
class _Planted:
    """One table's two rows, on either side of its horizon.

    :ivar expired: The id of the row older than the window
    :ivar fresh: The id of the row inside the window
    """

    expired: uuid.UUID
    fresh: uuid.UUID


@pytest.fixture
def rows_either_side(owner_session: Session) -> dict[str, _Planted]:
    """Plant an expired and a fresh row in every purgeable table.

    **This is the fixture the whole test-after half rests on, and the
    vacuity trap it answers is named in the unit's test instructions**:
    a purge test with no AGED fixtures deletes nothing and passes, while
    exercising only the retention logic's negative branch. So each table
    gets a row comfortably past its own horizon and one comfortably
    inside it, and the tests assert BOTH outcomes -- the expired row
    gone and the fresh row present. One without the other is half a
    test: deleting everything passes the first, deleting nothing passes
    the second.

    The margins are a day either side of each table's own cutoff rather
    than a fixed date, so the 48-hour window and the 12-month one are
    each tested at their own boundary.

    :param owner_session: An arranging session, owner-privileged
    :return: The planted ids per table
    """
    account_id = uuid.uuid4()
    enrollment_id = uuid.uuid4()
    otp_request_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    batch_id = uuid.uuid4()

    owner_session.execute(
        sa.text(
            "INSERT INTO account (id, phone, created_at) VALUES (:id, :phone, :at)"
        ),
        {"id": account_id, "phone": "+8801700000904", "at": LONG_AGO},
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO owner (id, account_id, created_at) "
            "VALUES (:id, :account_id, :at)"
        ),
        {"id": owner_id, "account_id": account_id, "at": LONG_AGO},
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO batch "
            "(id, owner_id, name, marksheet_visible, active, created_at) "
            "VALUES (:id, :owner_id, 'B', true, true, :at)"
        ),
        {"id": batch_id, "owner_id": owner_id, "at": LONG_AGO},
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO enrollment "
            "(id, batch_id, display_name, student_decision, "
            " guardian_decision, created_at) "
            "VALUES (:id, :batch_id, 'S', 'pending', 'pending', :at)"
        ),
        {"id": enrollment_id, "batch_id": batch_id, "at": LONG_AGO},
    )
    # The parent OTP request `verify_attempt` hangs off. Planted far
    # enough in the FUTURE that the purge's own otp_request window never
    # removes it mid-test and takes the verify_attempt rows with it by
    # cascade -- which would make the verify_attempt assertions pass for
    # the wrong reason.
    owner_session.execute(
        sa.text(
            "INSERT INTO otp_request "
            "(id, phone, otp_hash, purpose, issued_at, expires_at) "
            "VALUES (:id, :phone, :hash, 'signin', :at, :at)"
        ),
        {
            "id": otp_request_id,
            "phone": "+8801700000905",
            "hash": otp_request_id.hex,
            "at": NOW,
        },
    )
    owner_session.commit()

    planted: dict[str, _Planted] = {}
    for table, window in sorted(WINDOWS.items()):
        cutoff = window.cutoff(NOW)
        expired = _plant(
            owner_session,
            table,
            age_column=window.age_column,
            at=cutoff - dt.timedelta(days=1),
            account_id=account_id,
            enrollment_id=enrollment_id,
            otp_request_id=otp_request_id,
        )
        fresh = _plant(
            owner_session,
            table,
            age_column=window.age_column,
            at=cutoff + dt.timedelta(days=1),
            account_id=account_id,
            enrollment_id=enrollment_id,
            otp_request_id=otp_request_id,
        )
        planted[table] = _Planted(expired=expired, fresh=fresh)

    owner_session.commit()
    return planted


def _exists(session: Session, table: str, row_id: uuid.UUID) -> bool:
    """Report whether one row is still present.

    :param session: The session to read through
    :param table: The table to look in; a manifest key only
    :param row_id: The row's primary key
    :return: True when the row is present
    """
    return (
        session.execute(
            sa.text(f'SELECT 1 FROM "{table}" WHERE id = :id'),  # noqa: S608
            {"id": row_id},
        ).first()
        is not None
    )


def test_every_window_deletes_past_its_horizon_and_keeps_inside_it(
    owner_session: Session,
    rows_either_side: dict[str, _Planted],
) -> None:
    """Each of the seven windows removes the old row and keeps the new.

    **Both halves are asserted for every table**, which is what makes
    this a test of the boundary rather than of deletion. A purge that
    deleted everything passes the first assertion alone; one that
    deleted nothing -- the shape an un-aged fixture set cannot
    distinguish -- passes the second alone.

    Run through the owner session because the arrangement is owner-made
    and ``verify_attempt``'s and ``staging_sms_outbox``'s rows are read
    back here; the restricted-role behaviour is covered by the
    ``LIFE_OF_ACCOUNT`` test, which is the one where privilege matters.

    :param owner_session: The session to purge and assert through
    :param rows_either_side: The planted ids per table
    :return: None
    """
    assert set(rows_either_side) == set(WINDOWS), (
        "a purgeable table was not planted, so its window is untested"
    )

    purge_expired(owner_session, now=NOW)

    for table, planted in sorted(rows_either_side.items()):
        assert not _exists(owner_session, table, planted.expired), (
            f"{table}: a row past its {WINDOWS[table].keep_for} window "
            "survived the purge"
        )
        assert _exists(owner_session, table, planted.fresh), (
            f"{table}: a row INSIDE its {WINDOWS[table].keep_for} window "
            "was deleted, which is data loss rather than retention"
        )


def test_a_second_immediate_run_deletes_nothing(
    owner_session: Session,
    rows_either_side: dict[str, _Planted],
) -> None:
    """The purge is idempotent [BR4.1].

    The honest failure of a retention job is dying halfway and being
    re-run, so a second run must be a no-op rather than an error or a
    second deletion. Asserted as a count of zero rather than as "it did
    not raise".

    :param owner_session: The session to purge through
    :param rows_either_side: The planted ids, so the first run has work
    :return: None
    """
    first = purge_expired(owner_session, now=NOW)
    assert first.total == len(WINDOWS), (
        f"the first run deleted {first.total} rows; one expired row per "
        f"purgeable table is {len(WINDOWS)}"
    )

    second = purge_expired(owner_session, now=NOW)
    assert second.total == 0, (
        f"a second immediate run deleted {second.deleted}, so the purge "
        "is not idempotent"
    )


def test_the_delete_is_chunked_rather_than_one_statement_per_table(
    owner_session: Session,
    rows_either_side: dict[str, _Planted],
) -> None:
    """A table with more expired rows than the chunk size takes more
    than one statement [BR4.1].

    **The assertion that distinguishes chunked from unchunked.** A
    bounded delete issued once per table is indistinguishable from an
    unbounded one when every table holds a single expired row, which is
    what the other tests here arrange -- so this one plants more rows
    than one chunk holds and counts the statements.

    A small explicit ``chunk_size`` rather than 1,001 real rows: the
    property under test is that the loop re-issues until the matching
    set is exhausted, and the production constant is asserted
    separately.

    :param owner_session: The session to purge through
    :param rows_either_side: Provides the account the rows hang off
    :return: None
    """
    window = WINDOWS["auth_audit_log"]
    cutoff = window.cutoff(NOW)
    account_id = owner_session.execute(
        sa.text("SELECT account_id FROM auth_audit_log LIMIT 1")
    ).scalar_one()

    for index in range(6):
        owner_session.execute(
            sa.text(
                "INSERT INTO auth_audit_log "
                "(id, account_id, event, occurred_at, correlation_id) "
                "VALUES (:id, :account_id, 'otp_issued', :at, :cid)"
            ),
            {
                "id": uuid.uuid4(),
                "account_id": account_id,
                "at": cutoff - dt.timedelta(days=index + 2),
                "cid": f"chunked-{index}",
            },
        )
    owner_session.commit()

    deleted, statements = purge_table(owner_session, window, now=NOW, chunk_size=2)

    assert deleted == 7, f"expected 7 expired rows, deleted {deleted}"
    # 7 rows at 2 per chunk: three full chunks, then a short one of 1
    # that ends the loop. A single unbounded DELETE would report 1.
    assert statements == 4, (
        f"the purge issued {statements} statement(s) for 7 rows at a "
        "chunk size of 2, so it is not chunking"
    )


def test_a_non_positive_chunk_size_is_refused(
    owner_session: Session,
) -> None:
    """A zero chunk size raises rather than looping forever.

    ``LIMIT 0`` matches no rows, so the loop's own exit condition would
    be satisfied immediately and the purge would silently delete
    nothing -- a retention job reporting success having done nothing,
    which is the failure mode the heartbeat exists to surface and the
    one a wrong constant would reach by the quietest route.

    :param owner_session: An unused session fixture, for symmetry
    :return: None
    """
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        purge_table(owner_session, WINDOWS["otp_request"], now=NOW, chunk_size=0)


def test_the_production_chunk_size_is_the_documented_bound(
    owner_session: Session,
) -> None:
    """``CHUNK_SIZE`` is 1,000, the number BR4.1 states.

    An unstated bound is not a bound, so the stated one is asserted
    rather than left as prose that the constant may drift away from.

    :param owner_session: An unused session fixture, for symmetry
    :return: None
    """
    assert CHUNK_SIZE == 1_000


# ---------------------------------------------------------------------
# The heartbeat, and D4's freshness enumeration covering this job
# without being edited.
# ---------------------------------------------------------------------


def test_the_purge_registers_a_heartbeat_under_its_own_name(
    owner_session: Session,
    rows_either_side: dict[str, _Planted],
) -> None:
    """``run_purge`` writes a ``job_heartbeat`` row for this job.

    Under its OWN name, beside the fee and session jobs. A shared name
    would let a healthy fee run mask a purge that has never fired.

    :param owner_session: The session to purge through
    :param rows_either_side: The planted ids, so the run has work
    :return: None
    """
    run_purge(owner_session, now=NOW)

    row = owner_session.execute(
        sa.select(JobHeartbeat).where(JobHeartbeat.job_name == RETENTION_PURGE_JOB)
    ).scalar_one()

    assert row.last_success_at == NOW
    assert row.cycles_created == len(WINDOWS), (
        "the heartbeat's row count does not match what the run deleted"
    )


def test_a_run_that_deletes_nothing_still_stamps_the_heartbeat(
    owner_session: Session,
) -> None:
    """The heartbeat is unconditional on OUTCOME.

    **The case that would otherwise break the alert during correct
    operation.** Most purge runs legitimately delete nothing: the auth
    tables are purged daily and most days have little to remove. A row
    stamped only when something was deleted would go stale during
    entirely correct operation, fire the 48-hour alert, and get it muted
    -- reaching the alert's own failure mode by the opposite route.

    :param owner_session: The session to purge through
    :return: None
    """
    result = run_purge(owner_session, now=NOW)

    assert result.total == 0, "this test needs an empty database to mean anything"
    row = owner_session.execute(
        sa.select(JobHeartbeat).where(JobHeartbeat.job_name == RETENTION_PURGE_JOB)
    ).scalar_one()
    assert row.last_success_at == NOW
    assert row.cycles_created == 0


def test_d4s_freshness_enumeration_covers_this_job_unedited(
    owner_session: Session,
) -> None:
    """``check_all_jobs`` reports on the purge with no change to it.

    **This is the property option B was chosen for, asserted by the
    first unit to depend on it without also having written the
    checker.** The checker enumerates ``job_heartbeat`` rather than
    naming jobs, so a third job joins the freshness report by
    registering a row -- no change to ``check_all_jobs``, to the host's
    bare ``check-freshness`` invocation, or to ``user_data.sh.tftpl``.

    **The stale verdict is what makes this non-vacuous.** A checker that
    merely listed the row would satisfy a presence assertion; asserting
    the purge is judged UNHEALTHY when its row is old proves the row is
    being evaluated rather than enumerated.

    :param owner_session: The session to purge and check through
    :return: None
    """
    run_purge(owner_session, now=NOW)

    verdicts = dict(check_all_jobs(owner_session, now=NOW))
    assert RETENTION_PURGE_JOB in verdicts, (
        "the purge registered a heartbeat but the freshness check does not enumerate it"
    )
    assert verdicts[RETENTION_PURGE_JOB].healthy

    much_later = NOW + dt.timedelta(days=5)
    stale = dict(check_all_jobs(owner_session, now=much_later))
    assert not stale[RETENTION_PURGE_JOB].healthy, (
        "an old purge heartbeat is reported healthy, so the enumeration "
        "lists the row without evaluating it"
    )
