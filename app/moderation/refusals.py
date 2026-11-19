"""The two not-found refusals moderation shares.

Kept apart from :mod:`app.moderation.reports` so that reports and photo
moderation (:mod:`app.moderation.media`), which call each other, can both
raise them without importing one another in a cycle.
"""

from __future__ import annotations

from app.errors import AuthorizationError

__all__ = ["admin_not_found", "not_found"]


def not_found() -> AuthorizationError:
    """Build the one refusal every unreportable target shares.

    :return: A 404-equivalent authorization error
    """
    return AuthorizationError(
        code="REPORT_TARGET_NOT_FOUND",
        message_key="hub.report_target_not_found",
        status=404,
    )


def admin_not_found() -> AuthorizationError:
    """Build the refusal an administrator gets for nothing to act on.

    :return: A 404-equivalent authorization error
    """
    return AuthorizationError(
        code="HUB_ADMIN_TARGET_NOT_FOUND",
        message_key="hub.admin_target_not_found",
        status=404,
    )
