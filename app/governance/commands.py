"""The retention purge: this product's first enforcer of a window.

``RetentionClass`` has existed since U3 and until now nothing acted on
one. The governance test asserts every table HAS a class; no code
honoured any of them. So this is NEW behaviour rather than a scheduled
version of something existing, and the two rules that matter are both
about not doing too much.

**BR4.2 -- ``LIFE_OF_ACCOUNT`` is never purged.** Eighteen of the
twenty-five tables carry that class, including every attendance row,
every mark and the whole fee ledger. The dangerous implementation is the
NATURAL one: iterate the tables, apply a default window to those without
an explicit one. That deletes the product's entire history on its first
run, and it is the reason :data:`WINDOWS` is built by SELECTING the
finite classes rather than by excluding the infinite one. The difference
is not stylistic. A selection fails CLOSED when a new retention class
arrives -- the table is simply not purged, and
``test_every_finite_retention_class_has_a_window`` fails loudly in CI. An
exclusion would fail OPEN: an unrecognised class is not
``LIFE_OF_ACCOUNT``, so it would be purged at whatever default the code
reached for.

**BR4.1 -- idempotent and chunked.** The honest failure of a retention
job is not deleting too much; it is dying halfway and being re-run. Each
chunk commits before the next begins, so an interrupted run leaves
committed work committed and uncommitted work absent, and a re-run
simply continues. The alternative -- one ``DELETE`` per table -- holds a
row lock over a year of ``otp_request`` rows on the single small
instance this product runs on, which is the outage the chunking exists to
avoid rather than a theoretical nicety.

**The heartbeat is this job's whole contribution to its own
monitoring.** ``check_all_jobs`` enumerates ``job_heartbeat`` rather than
naming jobs, so registering a row under
:data:`~app.db.models.RETENTION_PURGE_JOB` is sufficient for the
freshness alert to cover this job -- with no change to the checker, to
the host's bare ``check-freshness`` invocation, or to
``user_data.sh.tftpl``. That is the property option B was chosen for on
2026-10-25, and this is the first unit to cash it in without also having
written the checker.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import RETENTION_PURGE_JOB
from app.db.session import build_engine, session_scope
from app.fees.commands import stamp_heartbeat
from app.fees.generation import GenerationResult as HeartbeatCounts
from app.governance.dispositions import RETENTION, RetentionClass

__all__ = [
    "CHUNK_SIZE",
    "WINDOWS",
    "PurgeResult",
    "TableWindow",
    "main",
    "main_purge",
    "purge_expired",
    "purge_table",
    "run_purge",
]

log = logging.getLogger(__name__)

#: **1,000 rows, and the commit boundary is per chunk** [BR4.1]. Stated
#: as a number rather than as "bounded", because an unstated bound is
#: not a bound. The figure is a starting point rather than a
#: measurement: nothing has been run against production volumes, and it
#: is small enough to be safe on the single small instance this product
#: runs on. The property that matters is not the value but that each
#: chunk commits before the next begins, which is what makes an
#: interrupted run leave a consistent state.
CHUNK_SIZE: Final = 1_000

#: How long each finite retention class keeps a row past its age column.
#:
#: ``UNTIL_EXPIRY_PLUS_30_DAYS`` is the odd one and is correct: the
#: refresh-token row's age column is ``expires_at`` rather than
#: ``issued_at``, because reuse detection needs the rotated-out row to
#: still exist after the token it represents has expired. Measuring that
#: window from issue would delete rows whose reuse-detection purpose had
#: not yet lapsed.
_CLASS_AGE: Final[dict[RetentionClass, dt.timedelta]] = {
    RetentionClass.DAYS_7: dt.timedelta(days=7),
    RetentionClass.HOURS_48: dt.timedelta(hours=48),
    RetentionClass.MONTHS_12: dt.timedelta(days=365),
    RetentionClass.UNTIL_EXPIRY_PLUS_30_DAYS: dt.timedelta(days=30),
}

#: Which column carries each purgeable table's age.
#:
#: **Named per table rather than guessed from a convention**, because
#: the convention does not hold: the five auth tables use five different
#: column names (``issued_at``, ``attempted_at``, ``recorded_at``,
#: ``window_start``, ``occurred_at``) and a code path falling back to
#: ``created_at`` would raise on all five. A missing entry here is a
#: ``KeyError`` at import, which is the right direction for this to be
#: wrong in.
_AGE_COLUMN: Final[dict[str, str]] = {
    "otp_request": "issued_at",
    "verify_attempt": "attempted_at",
    "staging_sms_outbox": "recorded_at",
    "rate_limit_counter": "window_start",
    "auth_audit_log": "occurred_at",
    "reminder_event": "sent_at",
    "notification": "created_at",
    "refresh_token": "expires_at",
}


@dataclass(frozen=True, slots=True)
class TableWindow:
    """One table's purge rule.

    :ivar table: The table this rule purges
    :ivar age_column: The timestamp column a row's age is measured from
    :ivar keep_for: How long past that column a row is kept
    """

    table: str
    age_column: str
    keep_for: dt.timedelta

    def cutoff(self, now: dt.datetime) -> dt.datetime:
        """Compute the instant before which rows are expired.

        :param now: The moment the purge is running at
        :return: Rows whose age column is strictly older are deletable
        """
        return now - self.keep_for


def _build_windows() -> dict[str, TableWindow]:
    """Derive the purge rules from the governance manifest.

    **Built by SELECTING finite classes, never by excluding
    ``LIFE_OF_ACCOUNT``** [BR4.2]. See this module's docstring: the two
    forms differ in which direction they fail when a retention class is
    added, and only selection fails closed.

    :return: One rule per table carrying a finite retention class
    :raises KeyError: If a finite-retention table names no age column,
        which is a programming error caught at import rather than a
        row-deleting surprise at 03:00
    """
    windows: dict[str, TableWindow] = {}
    for table, retention in RETENTION.items():
        keep_for = _CLASS_AGE.get(retention)
        if keep_for is None:
            # LIFE_OF_ACCOUNT, or a class added later with no window.
            # Either way the table is not purged, which is the safe
            # outcome; the paired test fails loudly if the omission was
            # unintended.
            continue
        windows[table] = TableWindow(
            table=table,
            age_column=_AGE_COLUMN[table],
            keep_for=keep_for,
        )
    return windows


#: The purge's complete scope. Seven tables; the other eighteen are
#: ``LIFE_OF_ACCOUNT`` and are never touched at any age [BR4.2].
WINDOWS: Final[dict[str, TableWindow]] = _build_windows()


@dataclass(frozen=True, slots=True)
class PurgeResult:
    """What one purge run deleted.

    :ivar deleted: Rows removed, per table, including zero-count tables
    :ivar chunks: How many chunked deletes were issued in total
    """

    deleted: dict[str, int]
    chunks: int

    @property
    def total(self) -> int:
        """Sum the rows deleted across every table.

        :return: The total row count
        """
        return sum(self.deleted.values())


def purge_table(
    session: Session,
    window: TableWindow,
    *,
    now: dt.datetime,
    chunk_size: int = CHUNK_SIZE,
) -> tuple[int, int]:
    """Delete one table's expired rows, in committed chunks.

    **The subquery with ``LIMIT`` is what makes this chunked.**
    PostgreSQL has no ``DELETE ... LIMIT``, so the bound is expressed by
    deleting the rows a limited ``SELECT`` names.

    **There is deliberately no ``FOR UPDATE SKIP LOCKED``**, and the
    reason is a privilege rather than a preference. The first version
    carried it, for the usual reason -- so a retried run overlapping the
    first does not block on rows the other holds -- and it failed
    against the real schema with *permission denied for table
    staging_sms_outbox*: ``0003`` grants that table ``SELECT, INSERT,
    DELETE`` and PostgreSQL requires ``UPDATE`` to take a row lock,
    which is exactly the narrower grant that table was given on purpose.
    Widening the grant to satisfy a lock hint would be loosening a
    deliberate privilege boundary to suit an optimisation. The purge is
    a single scheduled job, so there is no second writer to skip past,
    and a plain ``DELETE`` locks only the rows it removes.

    **Each chunk commits.** That is the property BR4.1 asks for: an
    interrupted run leaves every completed chunk durable and no partial
    chunk, so re-running continues rather than redoing.

    :param session: The session to delete through
    :param window: The table and its age rule
    :param now: The moment the purge is running at
    :param chunk_size: Maximum rows per statement
    :return: Rows deleted, and how many statements it took
    :raises ValueError: If a non-positive chunk size is passed, which
        would otherwise loop forever deleting nothing
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")

    cutoff = window.cutoff(now)

    # Both identifiers are module-level constants read from the
    # governance manifest and `_AGE_COLUMN`, never request input. The
    # cutoff -- the only value a caller influences -- is a bind
    # parameter.
    statement = sa.text(
        f'DELETE FROM "{window.table}" '  # noqa: S608  manifest constants
        f"WHERE ctid IN ("
        f'  SELECT ctid FROM "{window.table}" '
        f'  WHERE "{window.age_column}" < :cutoff '
        f'  ORDER BY "{window.age_column}" '
        f"  LIMIT :chunk"
        f")"
    )

    deleted = 0
    chunks = 0
    while True:
        # Through `session.connection()` rather than `session.execute`,
        # because `rowcount` is what drives the loop and only
        # `CursorResult` declares it -- `Session.execute` is typed as
        # returning the narrower `Result`. Same connection, same
        # transaction, same commit boundary; the difference is entirely
        # in what the type checker can see.
        result = session.connection().execute(
            statement, {"cutoff": cutoff, "chunk": chunk_size}
        )
        session.commit()
        chunks += 1
        removed = result.rowcount or 0
        deleted += removed
        if removed < chunk_size:
            # A short chunk means the matching set is exhausted. Testing
            # `< chunk_size` rather than `== 0` saves one empty round
            # trip per table on every run, and a run that deletes
            # nothing still issues exactly one statement -- which is
            # what makes a second immediate run cheap as well as
            # idempotent.
            break

    return deleted, chunks


def purge_expired(
    session: Session,
    *,
    now: dt.datetime | None = None,
    chunk_size: int = CHUNK_SIZE,
) -> PurgeResult:
    """Purge every table carrying a finite retention window.

    **Iterates ``WINDOWS``, never the schema.** A purge that walked
    ``pg_tables`` and consulted the manifest per table would delete any
    table the manifest had not yet heard of, which is the undeclared-table
    case the governance gate exists to catch -- arriving by a route that
    destroys data rather than one that fails a test.

    Tables are purged in name order so a run's statement sequence is
    reproducible, which makes an interrupted run's partial state
    predictable rather than dependent on dict ordering.

    :param session: The session to delete through
    :param now: The moment to measure ages against; the clock by default
    :param chunk_size: Maximum rows per statement
    :return: The per-table counts and the statement count
    """
    moment = now or dt.datetime.now(tz=dt.UTC)

    deleted: dict[str, int] = {}
    chunks = 0
    for table in sorted(WINDOWS):
        rows, statements = purge_table(
            session, WINDOWS[table], now=moment, chunk_size=chunk_size
        )
        deleted[table] = rows
        chunks += statements

    return PurgeResult(deleted=deleted, chunks=chunks)


def run_purge(
    session: Session,
    *,
    now: dt.datetime | None = None,
    chunk_size: int = CHUNK_SIZE,
) -> PurgeResult:
    """Run one purge pass and stamp this job's heartbeat.

    The order is the requirement: purge, then stamp. Stamping first
    records a success before the work, which is the timer-level
    heartbeat the observability design rejects -- a scheduler firing a
    command that crashes immediately would still stamp it.

    **The heartbeat is unconditional on OUTCOME.** A run that deletes
    nothing is the normal case: the auth tables are purged daily and
    most days have little to remove, and a row stamped only when
    ``total > 0`` would go stale during entirely correct operation,
    fire the 48-hour alert, and get it muted -- reaching the alert's own
    failure mode by the opposite route.

    The heartbeat's three integer columns are the fee job's names
    reused, as D4's session job already does: the table is keyed by job
    name and carries three counts, and widening it to per-job column
    names would be a migration for a difference that does not exist.
    Here they are rows deleted, tables purged, and zero failures --
    a failing purge raises rather than counting, because a retention job
    that half-worked and reported success is the thing the heartbeat
    exists to make visible.

    :param session: The session to work through
    :param now: The moment to measure ages against; the clock by default
    :param chunk_size: Maximum rows per statement
    :return: The run's per-table counts
    """
    result = purge_expired(session, now=now, chunk_size=chunk_size)

    stamp_heartbeat(
        session,
        result=HeartbeatCounts(
            cycles_created=result.total,
            cycles_skipped=len(result.deleted),
            periods_failed=0,
        ),
        job_name=RETENTION_PURGE_JOB,
        now=now,
    )
    return result


def main_purge() -> int:
    """Entry point for ``purge-expired``.

    Takes no arguments, by requirement: this is also the by-hand
    recovery procedure, so there are no flags to get wrong at the moment
    somebody is running it because something else went wrong.

    :return: 0 on completion
    """
    with session_scope(build_engine()) as session:
        result = run_purge(session)

    # Counts only. No phone number, no OTP, no child name and no row
    # identifier reaches this line.
    log.info(
        "retention purge complete",
        extra={
            "rows_deleted": result.total,
            "tables_purged": len(result.deleted),
            "statements": result.chunks,
        },
    )
    return 0


def main() -> int:
    """Dispatch the one verb this module carries.

    **No freshness verb here**, for the same reason D4's command has
    none: the freshness check enumerates every registered job from one
    entry point, so this job registers a heartbeat row and adds no
    second checker.

    :return: The command's exit status, or 2 for an unknown verb
    """
    verb = sys.argv[1] if len(sys.argv) > 1 else "purge"
    if verb == "purge":
        return main_purge()

    log.error("unknown command", extra={"verb": verb, "known": "purge"})
    return 2


if __name__ == "__main__":  # pragma: no cover - a process entry point
    sys.exit(main())
