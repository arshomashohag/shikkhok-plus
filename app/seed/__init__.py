"""Test data for performance testing on a non-production host.

**Every row is written by the application's own services**, under a
simulated clock, so the history it produces is the history the app
would have produced: fee cycles generated on the 1st, charges and
receipts folded through the real ledger writer, rosters through the
versioned submission path, marks through the supersession chain. A
seeder that inserted rows directly would be a second, untested write
path into tables whose invariants live in code -- the reason B5
deleted the skeleton's raw-SQL seed script.

Refuses to run against production, for :mod:`app.db.seed_staging`'s
reason: a script that creates accounts is a script that creates
accounts.
"""
