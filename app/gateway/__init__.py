"""The SMS gateway boundary.

The only boundary in this system where a failure costs money and a retry
may double-charge and double-message. That is why the adapter attempts
exactly once, records an ambiguous outcome as ``UNKNOWN`` rather than
``FAILED``, and why the null adapter -- not the real one -- is the default
[BR5.3, BR5.4].
"""
