"""
The money module's error surface: exactly one class.

Every refusal in this module raises :class:`MoneyValidationError` and only
that. [BR1.8]

Three of the five classes in the project's error taxonomy are structurally
unreachable here, which is why one class is the correct answer rather than a
simplification:

- A **conflict** means a well-formed operation the current *state* forbids.
  This module holds no state — no session, no repository, no stored balance;
  every operation is a pure function of its arguments — so there is no world
  that can change underneath a caller. Note in particular that applying more
  credit than is available is *unrepresentable* rather than refused: the
  applied amount is computed as ``min(available, owed)``.
- A **transient** failure means a retry may succeed. This module performs no
  I/O, so nothing in it can fail in a way a retry would fix.
- A **fatal** failure is an assertion, not a raise site. The one place this
  module could produce one — an unrecognised ledger kind — is an assertion
  under a statically-proven total mapping, not an exception.

What remains is the input being wrong, which is this module's whole failure
surface.

The API contract unit owns the envelope, the ``code`` strings, the
``retryable`` boolean, the ``message_key`` and every HTTP status. This module
states only which class it raises.

A refusal here that is *not* a validation failure is a signal that state or
I/O has entered the module, and is a reason to stop rather than to add a
class.
"""


class MoneyValidationError(ValueError):
    """
    A money operation received an input it cannot accept.

    Raised for a malformed or out-of-domain input: construction from a binary
    float, a magnitude beyond the storage contract, a negative or
    floating-point rate, an allocation into fewer than one part, a negative
    ledger entry amount, a non-canonical wire value, or an attempt to
    serialize a negative amount.

    Subclasses :class:`ValueError` so that callers unaware of this module's
    taxonomy still handle it as the input error it is.
    """
