"""Exams, marks and the anonymised marksheet.

:mod:`app.marks.marksheet` is **pure computation with no I/O, no
session and no HTTP**, which is what makes its 100% branch target
reachable -- the same property that makes it true of ``app/money/``.
Burying it in a package full of session I/O would invite a session
parameter and the target with it.
"""

from __future__ import annotations
