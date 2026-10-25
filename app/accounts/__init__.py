"""Signup, the already-added lookup, and the acceptance decisions.

Beside ``app.auth`` rather than inside it, because the two answer
different questions with opposite disclosure properties [BR2.3,
security-design § 2]. ``app.auth`` proves that someone holds a number
and must never reveal whether that number is known; this package
*creates* the identity behind a number, and its lookup deliberately
discloses that a seat exists. Conflating the two is how one inherits the
other's assumptions.

Both belong to the identity-and-access component [components.md].
"""
