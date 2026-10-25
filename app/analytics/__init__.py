"""Derived figures: what a teacher is owed, and what they received.

**D5 creates no table, adds no column and ships no migration.** Every
figure in this package derives from rows D3 and D4 already wrote, which
makes its risk profile unlike every unit before it: there is no
constraint to violate and no race to lose. **The risk is arithmetic over
existing rows, and arithmetic that is wrong still balances.**

Two rules carry it, and each has a named test that cannot pass against
its own defect:

* **Cash in is ``receipt + credit_grant`` and never ``credit_apply``**
  [BR2.1]. Counting the apply double-counts the credit -- once when it
  arrived and again when it was spent -- and every ledger row still
  balances while it does so.
* **Dues membership is driven by outstanding balance and never by active
  status** [BR1.2]. Reusing D4's roster predicate silently drops exactly
  the people most worth chasing.

**Which modules may touch a session is this package's one structural
control** [logical-components § 1]:

=============== ========= ================================================
Module          Session   What it does
=============== ========= ================================================
``seats.py``    **yes**   The one owned-seat join, and the one ledger read
``upcoming.py`` **yes**   One exam select with ``LIMIT 1``
``earnings.py`` **no**    Pure fold: entries in, period totals out
``dues.py``     **no**    Pure assembly: seats and entries in, rows out
=============== ========= ================================================

``dues.py`` taking no session is load-bearing rather than stylistic. It
is where the per-seat loop lives, so it is the one place a query could
be added per row -- **a module that cannot reach a session cannot make
that mistake** [NFR20.32]. The N+1 obligation becomes a property of the
module graph rather than a rule someone has to remember.
"""
