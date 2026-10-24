"""
The money module: the single place money arithmetic happens.

Everything a caller may use is exported here. Every other module in this
package is private — a consumer importing ``app.money._ledger`` directly is
doing something the design did not intend, and the public surface is what
makes that visible.

This package imports nothing from the API, persistence, repository,
authorization or schema layers, enforced by a layered-import test that fails
the build. Raw :mod:`decimal` arithmetic is confined here, enforced by a
banned-import lint rule with this path re-permitted by explicit exception.
The two gates point in opposite directions and neither catches the other's
case.
"""

from ._errors import MoneyValidationError
from ._kinds import LedgerEntryKind
from ._ledger import (
    DerivedQuantities,
    LedgerEntry,
    apply_credit,
    carry_forward,
    derive,
)
from ._money import Money
from ._rounding import EXPONENT, MAX_INTEGER_DIGITS, ROUNDING

__all__ = [
    "EXPONENT",
    "MAX_INTEGER_DIGITS",
    "ROUNDING",
    "DerivedQuantities",
    "LedgerEntry",
    "LedgerEntryKind",
    "Money",
    "MoneyValidationError",
    # Exported at D3, which is the first caller. It was private only
    # because nothing outside this package had yet needed to decide how
    # much credit to spend; the function was always part of the
    # arithmetic surface, and a consumer reaching into ``_ledger`` for
    # it would be exactly the breach the public surface exists to make
    # visible. The amount is still COMPUTED here rather than supplied,
    # which is the property BR4.4 rests on.
    "apply_credit",
    "carry_forward",
    "derive",
]
