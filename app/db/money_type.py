"""The storage chokepoint: the only path a money value takes to a column.

``app.money.wire`` owns the wire boundary; this owns the database one.
Both exist for the same reason — **a per-field decision is one somebody
eventually forgets**, and a forgotten money type is invisible in review
because the column still stores a number.

Without this, every model independently declares its own column type and
one eventually declares ``Numeric(10, 2)`` or, worse, a ``Float``. With
it, a money column is spelled :data:`MoneyColumn` and the precision
exists in exactly one place.

**This module is the reason ``app/db/models.py`` imports no ``Decimal``.**
The import-direction gate bans raw ``decimal`` outside ``app/money``
precisely so that money arithmetic cannot leak, and a model annotating a
column as ``Decimal`` is the most natural way to breach it. Mapping to
:class:`~app.money.Money` instead keeps the annotation inside the type
system the project actually uses.

It lives under ``app/db`` rather than inside ``app/money`` deliberately:
``app.money`` imports nothing from the persistence layer, and a
``TypeDecorator`` is a SQLAlchemy object. Putting it there would make the
strict island depend on the ORM and destroy both the layering test and
the 100% branch-coverage target that depends on the module having no I/O.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Numeric
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.money import Money

__all__ = ["MONEY_PRECISION", "MONEY_SCALE", "MoneyColumn", "MoneyType"]

#: The one precision every money column carries [TC-7, D-20]. Declared
#: here so no model restates it and none can disagree.
MONEY_PRECISION = 12
MONEY_SCALE = 2


class MoneyType(TypeDecorator[Money]):
    """Map :class:`~app.money.Money` onto ``NUMERIC(12,2)``.

    Round trips through :class:`~decimal.Decimal`, never through a
    float. ``asdecimal=True`` is what keeps the driver from handing back
    a float on read — the single most consequential setting here, because
    a float round trip reintroduces exactly the representation error the
    money module exists to prevent, silently and on correct-looking code.
    """

    impl = Numeric(precision=MONEY_PRECISION, scale=MONEY_SCALE, asdecimal=True)
    cache_ok = True

    def process_bind_param(self, value: Money | None, dialect: Dialect) -> Any:
        """Convert a :class:`Money` into the value the driver stores.

        :param value: The amount to store, or None
        :param dialect: The dialect in use, unused here
        :return: The exact decimal to store, or None
        :raises TypeError: The value is not a :class:`Money`
        """
        if value is None:
            return None
        if not isinstance(value, Money):
            # A bare Decimal or int reaching a money column means the
            # value skipped the type that enforces the rounding mode and
            # the float prohibition. Refusing it here is what makes the
            # chokepoint a chokepoint rather than a convention.
            raise TypeError(
                f"a money column takes Money, not {type(value).__name__}. "
                "Construct it through app.money.Money so the rounding "
                "mode and the float prohibition apply."
            )
        return value.amount

    def process_result_value(self, value: Any, dialect: Dialect) -> Money | None:
        """Convert a stored decimal back into a :class:`Money`.

        :param value: The decimal read from the column, or None
        :param dialect: The dialect in use, unused here
        :return: The reconstructed amount, or None
        """
        if value is None:
            return None
        return Money(value)


#: The spelling every money column uses. A model writes
#: ``mapped_column(MoneyColumn)`` and states no precision of its own.
MoneyColumn = MoneyType()
