"""The restricted role's name and the RLS session key.

These two values are shared by the migration that creates them, the
request middleware that sets the session variable, and the meta-test that
asserts both are in force. They live here rather than in the migration so
no caller has to import a revision module by filename.
"""

from __future__ import annotations

from typing import Final

__all__ = ["APP_ROLE", "HUB_READER_ROLE", "SESSION_ACCOUNT_KEY"]

#: The role the application and the test suite connect as. Deliberately
#: NOT the owner of the tables and NOT a superuser: PostgreSQL documents
#: that both bypass row-level security entirely, so a privacy suite run as
#: either passes identically whether the policy is correct, broken, or
#: absent.
APP_ROLE: Final = "shikkhok_app"

#: The ``NOLOGIN`` role the public hub reads as. The application role is a
#: member and becomes it with ``SET LOCAL ROLE`` for one transaction. It
#: holds no table grants until a later revision names each one, so anything
#: not granted fails closed.
HUB_READER_ROLE: Final = "shikkhok_hub_reader"

#: The session variable the ``profile`` policy reads. Set inside the
#: request transaction, so it cannot leak between pooled connections.
SESSION_ACCOUNT_KEY: Final = "app.account_id"
