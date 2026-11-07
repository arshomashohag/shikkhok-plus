"""Recording, voiding and listing expenses [0021].

**Scoped by the teacher lens's owner**, in every query: one owner's
spending is never loaded for another, so it cannot leak through a
forgotten filter.

**Append-only.** Recording inserts; voiding stamps who, when and why on
the row and changes nothing else. The table's grants enforce the same.

**A resend is a replay**: the record path inserts ``ON CONFLICT DO
NOTHING`` against ``UNIQUE (recorded_by_account_id, client_mutation_id)``
and reads the winner back, so two simultaneous resends record once.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import EXPENSE_CATEGORY_VALUES, Batch, Expense, ExtraFee
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.errors.codes import NOT_AVAILABLE
from app.fees.periods import Period
from app.local_time import bangladesh_today
from app.money import Money

__all__ = [
    "REPLAY_CONSTRAINT",
    "ExpenseDraft",
    "ExpenseMonth",
    "expenses_in_month",
    "month_of",
    "record_expense",
    "void_expense",
]

#: The constraint a record inserts against, created by ``0021``.
REPLAY_CONSTRAINT = "uq_expense_account_mutation"


@dataclass(frozen=True, slots=True)
class ExpenseDraft:
    """What the owner typed.

    :ivar category: One of the closed category keys
    :ivar what: What it was
    :ivar amount: What was spent
    :ivar spent_on: The day the money went
    :ivar payee: Who it was paid to, if said
    :ivar note: A receipt number or note, if any
    :ivar batch_id: The batch it was for, if any
    :ivar extra_fee_id: The exam or other fee it was for, if any
    :ivar client_mutation_id: The app's retry key, if sent
    :ivar salary_line_id: The salary line this pays [0026], if any; set
        only by the payroll module, never from the expense form
    """

    category: str
    what: str
    amount: Money
    spent_on: dt.date
    payee: str | None = None
    note: str | None = None
    batch_id: uuid.UUID | None = None
    extra_fee_id: uuid.UUID | None = None
    client_mutation_id: uuid.UUID | None = None
    salary_line_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ExpenseMonth:
    """One month's expenses, with the server's totals.

    :ivar month: The month, ``YYYY-MM``
    :ivar expenses: Every expense in it, voided ones included, newest first
    :ivar total: What was spent, voided expenses left out
    :ivar by_category: Category to its total, voided left out, largest first
    """

    month: str
    expenses: list[Expense]
    total: Money
    by_category: list[tuple[str, Money]]


def _refuse() -> AuthorizationError:
    """Build the shared refusal: an absent expense and another owner's alike.

    :return: The refusal
    """
    return AuthorizationError(code=NOT_AVAILABLE, message_key="fees.not_available")


def _blank_to_none(value: str | None) -> str | None:
    """Treat a blank field as absent.

    :param value: The text as typed
    :return: The trimmed text, or None
    """
    trimmed = (value or "").strip()
    return trimmed or None


def month_of(key: str | None, *, today: dt.date | None = None) -> Period:
    """Read a ``YYYY-MM`` month, defaulting to this month in Bangladesh.

    :param key: The month asked for, or None
    :param today: Bangladesh's date; the real clock by default
    :return: The month
    :raises ValidationError: The key is not a real month
    """
    if key is None:
        return Period.containing(today or bangladesh_today())
    try:
        return Period.parse(key)
    except ValueError:
        raise ValidationError(
            code="MONTH_INVALID", message_key="money.month_invalid"
        ) from None


def _check(
    session: Session, draft: ExpenseDraft, *, lens: TeacherLens, today: dt.date
) -> str:
    """Refuse an expense that could not have happened, and trim its detail.

    :param session: The session to read through
    :param draft: The form
    :param lens: The teacher lens
    :param today: Bangladesh's date
    :return: The description, trimmed
    :raises ValidationError: An unknown category, a blank description, a
        non-positive amount, a future date, or a batch or fee not this
        owner's
    """
    if draft.category not in EXPENSE_CATEGORY_VALUES:
        raise ValidationError(
            code="EXPENSE_CATEGORY_UNKNOWN", message_key="expenses.category_unknown"
        )
    what = draft.what.strip()
    if not what:
        raise ValidationError(
            code="EXPENSE_WHAT_REQUIRED", message_key="expenses.what_required"
        )
    if not draft.amount.is_positive():
        raise ValidationError(
            code="EXPENSE_AMOUNT_NOT_POSITIVE",
            message_key="expenses.amount_not_positive",
        )
    if draft.spent_on > today:
        raise ValidationError(
            code="EXPENSE_DATE_IN_FUTURE", message_key="expenses.date_in_future"
        )
    if draft.batch_id is not None:
        owned = session.scalars(
            sa.select(Batch.id).where(
                Batch.id == draft.batch_id, Batch.owner_id == lens.owner_id
            )
        ).one_or_none()
        if owned is None:
            raise ValidationError(
                code="EXPENSE_BATCH_NOT_FOUND", message_key="expenses.batch_not_found"
            )
    if draft.extra_fee_id is not None:
        owned = session.scalars(
            sa.select(ExtraFee.id)
            .join(Batch, Batch.id == ExtraFee.batch_id)
            .where(ExtraFee.id == draft.extra_fee_id, Batch.owner_id == lens.owner_id)
        ).one_or_none()
        if owned is None:
            raise ValidationError(
                code="EXPENSE_FEE_NOT_FOUND", message_key="expenses.fee_not_found"
            )
    return what


def _prior(
    session: Session, *, account_id: uuid.UUID, key: uuid.UUID | None
) -> Expense | None:
    """Find this ACCOUNT's expense under a retry key.

    :param session: The session to read through
    :param account_id: The recording account
    :param key: The retry key
    :return: The expense, or None (always, without a key)
    """
    if key is None:
        return None
    return session.scalars(
        sa.select(Expense).where(
            Expense.recorded_by_account_id == account_id,
            Expense.client_mutation_id == key,
        )
    ).one_or_none()


def _replayed(prior: Expense, draft: ExpenseDraft) -> Expense:
    """Answer a resend with the expense it repeats, writing nothing.

    :param prior: The expense recorded under the same key
    :param draft: The resend
    :return: The expense, unchanged
    :raises ConflictError: The resend describes a different expense
    """
    same = (
        prior.category == draft.category
        and prior.what == draft.what.strip()
        and prior.amount == draft.amount
        and prior.spent_on == draft.spent_on
        and prior.payee == _blank_to_none(draft.payee)
        and prior.batch_id == draft.batch_id
        and prior.extra_fee_id == draft.extra_fee_id
    )
    if not same:
        raise ConflictError(
            code="MUTATION_ID_ALREADY_USED",
            message_key="expenses.mutation_id_already_used",
        )
    return prior


def record_expense(
    session: Session,
    *,
    lens: TeacherLens,
    draft: ExpenseDraft,
    today: dt.date | None = None,
) -> Expense:
    """Record one expense. Commits.

    :param session: The session to write through
    :param lens: The teacher lens
    :param draft: The form
    :param today: Bangladesh's date; the real clock by default
    :return: The expense, new or replayed
    :raises ValidationError: The expense could not have happened as typed
    :raises ConflictError: The retry key already names a different expense
    """
    prior = _prior(session, account_id=lens.account_id, key=draft.client_mutation_id)
    if prior is not None:
        return _replayed(prior, draft)
    what = _check(session, draft, lens=lens, today=today or bangladesh_today())
    inserted: uuid.UUID | None = session.execute(
        pg_insert(Expense)
        .values(
            id=uuid.uuid4(),
            owner_id=lens.owner_id,
            category=draft.category,
            what=what,
            amount=draft.amount,
            spent_on=draft.spent_on,
            payee=_blank_to_none(draft.payee),
            note=_blank_to_none(draft.note),
            batch_id=draft.batch_id,
            extra_fee_id=draft.extra_fee_id,
            recorded_by_account_id=lens.account_id,
            client_mutation_id=draft.client_mutation_id,
            created_at=dt.datetime.now(tz=dt.UTC),
            salary_line_id=draft.salary_line_id,
        )
        .on_conflict_do_nothing(constraint=REPLAY_CONSTRAINT)
        .returning(Expense.id)
    ).scalar_one_or_none()
    if inserted is None:
        # No rollback: the conflicting insert waited for the winner, and
        # under READ COMMITTED the next statement already sees its row.
        # A rollback here ended the CALLER's transaction too -- releasing
        # the salary line ``pay`` holds locked and discarding anything it
        # had written [audit C-16].
        winner = _prior(
            session, account_id=lens.account_id, key=draft.client_mutation_id
        )
        if winner is None:
            raise ConflictError(
                code="MUTATION_ID_ALREADY_USED",
                message_key="expenses.mutation_id_already_used",
            )
        return _replayed(winner, draft)
    session.commit()
    return session.get_one(Expense, inserted)


def void_expense(
    session: Session, *, lens: TeacherLens, expense_id: uuid.UUID, reason: str | None
) -> Expense:
    """Void one of this owner's expenses, keeping it on the record. Commits.

    A conditional ``UPDATE ... WHERE voided_at IS NULL`` decides, so two
    voids at once leave one reason and refuse the other.

    :param session: The session to write through
    :param lens: The teacher lens
    :param expense_id: The expense
    :param reason: Why, shown beside it
    :return: The voided expense
    :raises AuthorizationError: It is absent or another owner's
    :raises ConflictError: It was already voided
    """
    found = session.scalars(
        sa.select(Expense.id).where(
            Expense.id == expense_id, Expense.owner_id == lens.owner_id
        )
    ).one_or_none()
    if found is None:
        raise _refuse()
    moved = session.execute(
        sa.update(Expense)
        .where(Expense.id == expense_id, Expense.voided_at.is_(None))
        .values(
            voided_at=dt.datetime.now(tz=dt.UTC),
            voided_by_account_id=lens.account_id,
            void_reason=_blank_to_none(reason),
        )
        .execution_options(synchronize_session=False)
    )
    if moved.rowcount != 1:  # type: ignore[attr-defined]
        session.rollback()
        raise ConflictError(
            code="EXPENSE_ALREADY_VOIDED", message_key="expenses.already_voided"
        )
    session.commit()
    return session.get_one(Expense, expense_id, populate_existing=True)


def expenses_in_month(
    session: Session, *, lens: TeacherLens, month: Period
) -> ExpenseMonth:
    """Every expense this owner recorded for one month, with the totals.

    :param session: The session to read through
    :param lens: The teacher lens
    :param month: The month
    :return: The month's expenses and totals
    """
    rows = list(
        session.scalars(
            sa.select(Expense)
            .where(
                Expense.owner_id == lens.owner_id,
                Expense.spent_on >= month.first_day(),
                Expense.spent_on <= month.last_day(),
            )
            .order_by(Expense.spent_on.desc(), Expense.created_at.desc(), Expense.id)
        )
    )
    standing = [row for row in rows if row.voided_at is None]
    totals: dict[str, list[Money]] = {}
    for row in standing:
        totals.setdefault(row.category, []).append(row.amount)
    by_category = sorted(
        ((category, Money.sum(amounts)) for category, amounts in totals.items()),
        key=lambda pair: (pair[1], pair[0]),
        reverse=True,
    )
    return ExpenseMonth(
        month=str(month),
        expenses=rows,
        total=Money.sum([row.amount for row in standing]),
        by_category=by_category,
    )
