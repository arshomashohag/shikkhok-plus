"""Authentication: codes, ceilings, hashing and tokens.

Four modules, and the split follows the thing each one can get silently
wrong rather than the shape of the request:

* :mod:`app.auth.ceilings` -- counters that must live in the datastore,
  because a per-process dictionary passes every naive test and stops
  working at two workers.
* :mod:`app.auth.hashing` -- the one chokepoint an OTP passes through, so
  there is a single place to assert the stored value is not the sent one.
* :mod:`app.auth.otp` -- issue and verify, including the existence oracle
  both branches must defeat.
* :mod:`app.auth.tokens` -- rotation with reuse detection, whose failure
  mode is invisible on the happy path.
"""
