"""
The module's single declared rounding mode and decimal precision.

Declared once, here, and imported by every operation that rounds. There are
exactly two rounding points in this module — construction and ``apply_rate``
— and both use this constant. Addition, subtraction and summation over
already-quantized values cannot introduce a third decimal place, so they do
not round and must not be written as though they might.

:raises: nothing
"""

from decimal import ROUND_HALF_UP, Decimal

#: The rounding mode for every money operation in this system. [BR3.1]
#:
#: Python's :mod:`decimal` default is ``ROUND_HALF_EVEN`` (banker's rounding),
#: which is wrong for consumer-facing BDT fee amounts: a teacher checking
#: arithmetic by hand expects a half to round up. The two modes genuinely
#: diverge — at three of the five halves sampled in the design — and across a
#: ledger the difference is a reconciliation discrepancy nobody can explain.
ROUNDING = ROUND_HALF_UP

#: Every money value carries exactly two decimal places. [BR1.3]
EXPONENT = Decimal("0.01")

#: The storage contract is twelve total digits with two decimals, leaving ten
#: for the integer part. [BR1.7]
MAX_INTEGER_DIGITS = 10

#: One above the largest representable magnitude.
MAGNITUDE_LIMIT = Decimal(10) ** MAX_INTEGER_DIGITS
