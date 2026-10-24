"""The fee system: the half the money module deliberately refuses to hold.

``app.money`` owns the arithmetic -- the fold from entries to balances,
``min(available, owed)`` for credit, the carry as an inseparable pair --
and says so in its own docstring: *"This module persists nothing. It owns
no table, no row, no identifier and no supersession."*

This package owns the other half: the tables entries live in, the
transaction that commits a pair, the calendar that ``period`` is opaque
to, and when each entry is written.

**Nothing here reimplements the arithmetic.** Where a rule looks like a
restatement -- a carry not exceeding the origin, a non-negative amount --
it is constraining the PERSISTED rows rather than the fold, because a row
inserted by a migration or a repair script never passes through the value
type.

**No calendar knowledge may move the other way** [BR2.1]. ``app.money``
treats a period as an opaque string, and the import-boundary test asserts
it imports nothing outside itself; a ``datetime`` import there would be
new.
"""
