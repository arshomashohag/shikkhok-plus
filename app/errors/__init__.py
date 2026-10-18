"""The error taxonomy: five closed classes and one response handler.

This package is on every error path in the system, so it performs no I/O:
no database call, no network call, no file read. A handler that can itself
fail turns a handled refusal into an unhandled 500 at exactly the moment
the system is already degraded. The prohibition is enforced by the layered
import test in ``tests/gates/test_import_gates.py``, not by convention.
"""
