"""``0013`` adds payment methods, payment submissions and claim links.

Staged at ``0012`` with batches already carrying a collection number,
because the data move is what a deploy meets.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from tests.db.migration_support import (
    _alembic_config,
    insert_account,
    stage_at,
    upgrade_to_head,
)

NOW = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.UTC)


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0012``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0012") as engine:
        yield engine


def _insert_owner(engine: Engine) -> uuid.UUID:
    """Insert an account and an owner.

    :param engine: The staged engine
    :return: The owner's id
    """
    owner_id = uuid.uuid4()
    with engine.begin() as connection:
        account_id = insert_account(connection, f"+8801{uuid.uuid4().int % 10**9:09d}")
        connection.execute(
            sa.text(
                "INSERT INTO owner (id, account_id, created_at) "
                "VALUES (:id, :account, :now)"
            ),
            {"id": owner_id, "account": account_id, "now": NOW},
        )
    return owner_id


def _insert_batch(
    engine: Engine, owner_id: uuid.UUID, number: str | None, channel: str | None
) -> uuid.UUID:
    """Insert a batch with a collection number and channel.

    :param engine: The staged engine
    :param owner_id: The owning owner
    :param number: The collection number or ``None``
    :param channel: The collection channel or ``None``
    :return: The batch's id
    """
    batch_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO batch (id, owner_id, name, collection_number, "
                "collection_channel, marksheet_visible, active, created_at) "
                "VALUES (:id, :owner, 'B', :number, :channel, false, true, :now)"
            ),
            {
                "id": batch_id,
                "owner": owner_id,
                "number": number,
                "channel": channel,
                "now": NOW,
            },
        )
    return batch_id


def _methods(engine: Engine, owner_id: uuid.UUID) -> list[sa.Row]:
    """Read an owner's payment methods.

    :param engine: The upgraded engine
    :param owner_id: The owner
    :return: Rows of ``kind``, ``provider``, ``mobile_number``
    """
    with engine.begin() as connection:
        return list(
            connection.execute(
                sa.text(
                    "SELECT kind, provider, mobile_number FROM payment_method "
                    "WHERE owner_id = :owner"
                ),
                {"owner": owner_id},
            )
        )


def test_0013_moves_each_distinct_collection_number_once(staged: Engine) -> None:
    """Two batches sharing a number make one method; another number makes another.

    :param staged: The engine staged at ``0012``
    :return: None
    """
    owner_id = _insert_owner(staged)
    _insert_batch(staged, owner_id, "01712345678", "bKash")
    _insert_batch(staged, owner_id, "01712345678", "bKash")
    _insert_batch(staged, owner_id, "01812987654", "Nagad")

    upgrade_to_head(staged)

    rows = _methods(staged, owner_id)
    assert len(rows) == 2
    assert {row.kind for row in rows} == {"mobile"}
    assert {row.provider for row in rows} == {"bKash", "Nagad"}
    with staged.begin() as connection:
        kept = connection.execute(
            sa.text("SELECT count(*) FROM batch WHERE collection_number IS NOT NULL")
        ).scalar_one()
    assert kept == 3


def test_0013_batch_with_no_number_makes_no_method(staged: Engine) -> None:
    """A batch without a collection number leaves no method behind.

    :param staged: The engine staged at ``0012``
    :return: None
    """
    owner_id = _insert_owner(staged)
    _insert_batch(staged, owner_id, None, None)

    upgrade_to_head(staged)

    assert _methods(staged, owner_id) == []


def test_0013_number_without_channel_defaults_to_bkash(staged: Engine) -> None:
    """A number with no recorded channel is moved as bKash.

    :param staged: The engine staged at ``0012``
    :return: None
    """
    owner_id = _insert_owner(staged)
    _insert_batch(staged, owner_id, "01712345678", None)

    upgrade_to_head(staged)

    assert [row.provider for row in _methods(staged, owner_id)] == ["bKash"]


@pytest.fixture
def head(staged: Engine) -> Engine:
    """Yield the staged engine upgraded to head.

    :param staged: The engine staged at ``0012``
    :return: The upgraded engine
    """
    upgrade_to_head(staged)
    return staged


def _insert_method(engine: Engine, owner_id: uuid.UUID, **columns: object) -> None:
    """Raw INSERT of a payment method with the given columns.

    :param engine: The upgraded engine
    :param owner_id: The owner
    :param columns: Column values to set
    :return: None
    """
    values = {
        "id": uuid.uuid4(),
        "owner_id": owner_id,
        "position": 0,
        "created_at": NOW,
        "updated_at": NOW,
        **columns,
    }
    names = ", ".join(values)
    params = ", ".join(f":{key}" for key in values)
    with engine.begin() as connection:
        connection.execute(
            sa.text(f"INSERT INTO payment_method ({names}) VALUES ({params})"),  # noqa: S608
            values,
        )


def test_kind_check_refuses_mobile_without_number(head: Engine) -> None:
    """A mobile method must carry a mobile number.

    :param head: The upgraded engine
    :return: None
    """
    owner_id = _insert_owner(head)

    with pytest.raises(IntegrityError):
        _insert_method(head, owner_id, kind="mobile", provider="bKash")


def test_kind_check_refuses_bank_fields_on_mobile(head: Engine) -> None:
    """A mobile method may not carry bank fields.

    :param head: The upgraded engine
    :return: None
    """
    owner_id = _insert_owner(head)

    with pytest.raises(IntegrityError):
        _insert_method(
            head,
            owner_id,
            kind="mobile",
            provider="bKash",
            mobile_number="01712345678",
            account_number="123",
        )


def test_kind_check_refuses_bank_without_branch(head: Engine) -> None:
    """A bank method needs account number, name, provider and branch.

    :param head: The upgraded engine
    :return: None
    """
    owner_id = _insert_owner(head)

    with pytest.raises(IntegrityError):
        _insert_method(
            head,
            owner_id,
            kind="bank",
            provider="Sonali",
            account_number="123",
            account_name="Teacher",
        )


def _seed_submission(
    engine: Engine, total: str, transaction_id: str | None, from_account: str | None
) -> uuid.UUID:
    """Insert a batch and a submission with the given values.

    :param engine: The upgraded engine
    :param total: The total amount
    :param transaction_id: The transaction id or ``None``
    :param from_account: The paying account or ``None``
    :return: The batch id
    """
    owner_id = _insert_owner(engine)
    batch_id = _insert_batch(engine, owner_id, None, None)
    with engine.begin() as connection:
        account_id = insert_account(connection, "+8801911111111")
        connection.execute(
            sa.text(
                "INSERT INTO payment_submission (id, batch_id, destination_snapshot, "
                "total_amount, paid_on, transaction_id, from_account, "
                "submitted_by_account_id, submitted_at, status) VALUES "
                "(:id, :batch, '{}', :total, :paid_on, :tx, :frm, :by, :now, "
                "'pending')"
            ),
            {
                "id": uuid.uuid4(),
                "batch": batch_id,
                "total": total,
                "paid_on": dt.date(2026, 11, 1),
                "tx": transaction_id,
                "frm": from_account,
                "by": account_id,
                "now": NOW,
            },
        )
    return batch_id


def test_submission_total_must_be_positive(head: Engine) -> None:
    """A submission of zero is refused.

    :param head: The upgraded engine
    :return: None
    """
    with pytest.raises(IntegrityError):
        _seed_submission(head, "0.00", "TX1", None)


def test_submission_refuses_both_reference_kinds(head: Engine) -> None:
    """A submission carries a transaction id or a paying account, not both.

    :param head: The upgraded engine
    :return: None
    """
    with pytest.raises(IntegrityError):
        _seed_submission(head, "100.00", "TX1", "01712345678")


def test_submission_accepts_a_valid_row(head: Engine) -> None:
    """The positive control for the refusals above.

    :param head: The upgraded engine
    :return: None
    """
    _seed_submission(head, "100.00", "TX1", None)


def _insert_claim(
    engine: Engine, enrollment_id: uuid.UUID, amount: str, submission_id: object
) -> None:
    """Insert a claim row with an optional submission link.

    :param engine: The upgraded engine
    :param enrollment_id: The seat
    :param amount: The claimed amount
    :param submission_id: The linked submission or ``None``
    :return: None
    """
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO payment_claim (id, enrollment_id, period, "
                "claimed_amount, channel, submitted_at, status, "
                "payment_submission_id) VALUES (:id, :enr, '2026-11', :amt, "
                "'bKash', :now, 'pending', :sub)"
            ),
            {
                "id": uuid.uuid4(),
                "enr": enrollment_id,
                "amt": amount,
                "now": NOW,
                "sub": submission_id,
            },
        )


def test_linked_claim_may_carry_a_zero_share(head: Engine) -> None:
    """Only a claim linked to a submission may claim zero.

    :param head: The upgraded engine
    :return: None
    """
    owner_id = _insert_owner(head)
    batch_id = _insert_batch(head, owner_id, None, None)
    submission_id = uuid.uuid4()
    with head.begin() as connection:
        account_id = insert_account(connection, "+8801922222222")
        enrollment_id = uuid.uuid4()
        connection.execute(
            sa.text(
                "INSERT INTO enrollment (id, batch_id, display_name, "
                "student_decision, guardian_decision, created_at) "
                "VALUES (:id, :batch, 'S', 'pending', 'pending', :now)"
            ),
            {"id": enrollment_id, "batch": batch_id, "now": NOW},
        )
        connection.execute(
            sa.text(
                "INSERT INTO payment_submission (id, batch_id, "
                "destination_snapshot, total_amount, paid_on, "
                "submitted_by_account_id, submitted_at, status) VALUES "
                "(:id, :batch, '{}', 50, :paid_on, :by, :now, 'pending')"
            ),
            {
                "id": submission_id,
                "batch": batch_id,
                "paid_on": dt.date(2026, 11, 1),
                "by": account_id,
                "now": NOW,
            },
        )

    _insert_claim(head, enrollment_id, "0.00", submission_id)

    with pytest.raises(IntegrityError):
        _insert_claim(head, enrollment_id, "0.00", None)


def test_0013_downgrade_drops_new_tables_and_columns(staged: Engine) -> None:
    """Downgrading removes what the upgrade added and restores the check.

    :param staged: The engine staged at ``0012``
    :return: None
    """
    upgrade_to_head(staged)
    url = staged.url.render_as_string(hide_password=False)
    command.downgrade(_alembic_config(url), "0012")

    with staged.begin() as connection:
        tables = set(
            connection.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            ).scalars()
        )
        columns = set(
            connection.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'payment_claim'"
                )
            ).scalars()
        )
        types = set(
            connection.execute(
                sa.text(
                    "SELECT typname FROM pg_type WHERE typname IN "
                    "('payment_method_kind', 'payment_submission_status')"
                )
            ).scalars()
        )
    assert not tables & {"payment_method", "payment_submission"}
    assert "payment_submission_id" not in columns
    assert types == set()
