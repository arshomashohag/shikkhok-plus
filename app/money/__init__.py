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

from ._allocation import Allocation, Disposition, allocate_payment
from ._errors import MoneyValidationError
from ._kinds import LedgerEntryKind
from ._ledger import (
    DerivedQuantities,
    LedgerEntry,
    apply_credit,
    carry_forward,
    derive,
    relief_of,
)
from ._money import Money
from ._payroll import SalaryTotals, salary_base, salary_totals
from ._rounding import EXPONENT, MAX_INTEGER_DIGITS, ROUNDING
from ._settlement import Settlement, settle_oldest_first

__all__ = [
    "EXPONENT",
    "MAX_INTEGER_DIGITS",
    "ROUNDING",
    "Allocation",
    "DerivedQuantities",
    "Disposition",
    "LedgerEntry",
    "LedgerEntryKind",
    "Money",
    "MoneyValidationError",
    "SalaryTotals",
    "Settlement",
    # Exported at D3, which is the first caller. It was private only
    # because nothing outside this package had yet needed to decide how
    # much credit to spend; the function was always part of the
    # arithmetic surface, and a consumer reaching into ``_ledger`` for
    # it would be exactly the breach the public surface exists to make
    # visible. The amount is still COMPUTED here rather than supplied,
    # which is the property BR4.4 rests on.
    "allocate_payment",
    "apply_credit",
    "carry_forward",
    "derive",
    "relief_of",
    # Exported at P1, the payroll unit: a salary's base and its owed,
    # paid and remaining figures are computed here, never at a call site.
    "salary_base",
    "salary_totals",
    "settle_oldest_first",
]
