"""``0014`` wraps every claim made before submissions in its own submission.

Staged at ``0013`` with unlinked claims in every status, because those
are the rows a deploy meets: without a submission they cannot be
decided, and their seats cannot be settled.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Engine

from app.money import Money
from tests.db.migration_support import (
    _alembic_config,
    insert_account,
    stage_at,
    upgrade_to_head,
)

SUBMITTED = dt.datetime(2026, 10, 31, 20, 30, tzinfo=dt.UTC)
DECIDED = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.UTC)


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0013``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0013") as engine:
        yield engine


def _seat(engine: Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Insert an owner, a batch, a seat and a payer account.

    :param engine: The staged engine
    :return: The batch, the seat and the payer account
    """
    owner_id, batch_id, seat_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with engine.begin() as connection:
        teacher = insert_account(connection, f"+8801{uuid.uuid4().int % 10**9:09d}")
        payer = insert_account(connection, f"+8801{uuid.uuid4().int % 10**9:09d}")
        connection.execute(
            sa.text(
                "INSERT INTO owner (id, account_id, created_at) "
                "VALUES (:id, :account, :now)"
            ),
            {"id": owner_id, "account": teacher, "now": SUBMITTED},
        )
        connection.execute(
            sa.text(
                "INSERT INTO batch (id, owner_id, name, marksheet_visible, "
                "active, created_at) VALUES (:id, :owner, 'B', false, true, :now)"
            ),
            {"id": batch_id, "owner": owner_id, "now": SUBMITTED},
        )
        connection.execute(
            sa.text(
                "INSERT INTO enrollment (id, batch_id, display_name, "
                "student_decision, guardian_decision, created_at) "
                "VALUES (:id, :batch, 'S', 'pending', 'pending', :now)"
            ),
            {"id": seat_id, "batch": batch_id, "now": SUBMITTED},
        )
    return batch_id, seat_id, payer


def _claim(
    engine: Engine,
    seat_id: uuid.UUID,
    payer: uuid.UUID,
    status: str,
    reason: str | None = None,
) -> uuid.UUID:
    """Insert one unlinked claim in the given status.

    :param engine: The staged engine
    :param seat_id: The seat
    :param payer: Who submitted it
    :param status: The claim's status
    :param reason: The rejection reason, if any
    :return: The claim id
    """
    claim_id = uuid.uuid4()
    decided = status != "pending"
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO payment_claim (id, enrollment_id, period, "
                "claimed_amount, channel, transaction_id, "
                "submitted_by_account_id, submitted_at, status, "
                "approved_amount, rejection_reason, verified_by_account_id, "
                "verified_at) VALUES (:id, :seat, '2026-10', 1200, 'Nagad', "
                ":tx, :payer, :submitted, CAST(:status AS payment_claim_status), "
                ":approved, :reason, :by, :at)"
            ),
            {
                "id": claim_id,
                "seat": seat_id,
                "tx": f"TX{claim_id.hex[:6]}",
                "payer": payer,
                "submitted": SUBMITTED,
                "status": status,
                "approved": 1200 if status.startswith("approved") else None,
                "reason": reason,
                "by": payer if decided else None,
                "at": DECIDED if decided else None,
            },
        )
    return claim_id


def _wrapped(engine: Engine) -> dict[uuid.UUID, sa.RowMapping]:
    """Read each claim's submission, keyed by claim id.

    :param engine: The upgraded engine
    :return: Claim id to its submission's columns
    """
    with engine.begin() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT c.id AS claim_id, s.* FROM payment_claim c "
                "JOIN payment_submission s ON s.id = c.payment_submission_id"
            )
        ).mappings()
        return {row["claim_id"]: row for row in rows}


def test_0014_wraps_every_unlinked_claim_with_its_status(staged: Engine) -> None:
    """Each status maps across and the claim's columns are copied.

    :param staged: The engine staged at ``0013``
    :return: None
    """
    batch_id, seat_id, payer = _seat(staged)
    claims = {
        status: _claim(staged, seat_id, payer, status, reason)
        for status, reason in (
            ("pending", None),
            ("approved_full", None),
            ("approved_partial", None),
            ("rejected", "Wrong number"),
        )
    }

    upgrade_to_head(staged)

    wrapped = _wrapped(staged)
    assert {status: wrapped[claim]["status"] for status, claim in claims.items()} == {
        "pending": "pending",
        "approved_full": "approved",
        "approved_partial": "approved",
        "rejected": "rejected",
    }
    assert len({row["id"] for row in wrapped.values()}) == 4
    pending = wrapped[claims["pending"]]
    assert pending["batch_id"] == batch_id
    assert Money(pending["total_amount"]) == Money("1200.00")
    assert pending["paid_on"] == dt.date(2026, 11, 1)
    assert pending["transaction_id"] == f"TX{claims['pending'].hex[:6]}"
    assert pending["submitted_by_account_id"] == payer
    assert pending["submitted_at"] == SUBMITTED
    assert pending["destination_snapshot"] == {"kind": "legacy", "channel": "Nagad"}
    assert pending["decided_at"] is None
    rejected = wrapped[claims["rejected"]]
    assert rejected["decision_note"] == "Wrong number"
    assert rejected["decided_by_account_id"] == payer
    assert rejected["decided_at"] == DECIDED


def test_0014_leaves_an_already_linked_claim_alone(staged: Engine) -> None:
    """A claim with a submission keeps it and gains no second one.

    :param staged: The engine staged at ``0013``
    :return: None
    """
    batch_id, seat_id, payer = _seat(staged)
    claim_id = _claim(staged, seat_id, payer, "pending")
    submission_id = uuid.uuid4()
    with staged.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO payment_submission (id, batch_id, "
                "destination_snapshot, total_amount, paid_on, submitted_at, "
                'status) VALUES (:id, :batch, \'{"kind": "cash"}\', 1200, '
                "'2026-11-01', :now, 'pending')"
            ),
            {"id": submission_id, "batch": batch_id, "now": SUBMITTED},
        )
        connection.execute(
            sa.text(
                "UPDATE payment_claim SET payment_submission_id = :s WHERE id = :c"
            ),
            {"s": submission_id, "c": claim_id},
        )

    upgrade_to_head(staged)

    with staged.begin() as connection:
        count = connection.execute(
            sa.text("SELECT count(*) FROM payment_submission")
        ).scalar_one()
    assert _wrapped(staged)[claim_id]["id"] == submission_id
    assert count == 1


def test_0014_downgrade_removes_only_what_it_made(staged: Engine) -> None:
    """Wrapped claims are unlinked and their submissions deleted.

    :param staged: The engine staged at ``0013``
    :return: None
    """
    batch_id, seat_id, payer = _seat(staged)
    claim_id = _claim(staged, seat_id, payer, "approved_full")
    upgrade_to_head(staged)
    with staged.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO payment_submission (id, batch_id, "
                "destination_snapshot, total_amount, paid_on, submitted_at, "
                'status) VALUES (:id, :batch, \'{"kind": "cash"}\', 500, '
                "'2026-11-01', :now, 'pending')"
            ),
            {"id": uuid.uuid4(), "batch": batch_id, "now": SUBMITTED},
        )

    url = staged.url.render_as_string(hide_password=False)
    command.downgrade(_alembic_config(url), "0013")

    with staged.begin() as connection:
        link = connection.execute(
            sa.text("SELECT payment_submission_id FROM payment_claim WHERE id = :c"),
            {"c": claim_id},
        ).scalar_one()
        kinds = connection.execute(
            sa.text("SELECT destination_snapshot->>'kind' FROM payment_submission")
        ).scalars()
        remaining = list(kinds)
    assert link is None
    assert remaining == ["cash"]
