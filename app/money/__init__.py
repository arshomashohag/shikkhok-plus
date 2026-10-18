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
from ._ledger import DerivedQuantities, LedgerEntry, carry_forward, derive
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
    "carry_forward",
    "derive",
]
