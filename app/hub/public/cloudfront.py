"""The boto3 invalidation client, and the best-effort drain after a request commits.

Kept apart from :mod:`app.hub.public.invalidation` so the takedown services,
which only enqueue, never import the AWS SDK.

**The site distribution comes from** ``SHIKKHOKPLUS_SITE_DISTRIBUTION_ID``.
Unset -- locally, in tests, and on a host with no public site --
:func:`client_from_environment` returns None and every drain logs and leaves
the rows unsent; the retention purge clears them after seven days.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from collections.abc import Callable
from typing import Any, Final

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from sqlalchemy.orm import Session

from app.hub.public import invalidation
from app.hub.public.invalidation import InvalidationClient

__all__ = [
    "DISTRIBUTION_ID_ENV",
    "CloudFrontInvalidationClient",
    "client_from_environment",
    "drain_after_commit",
]

log = logging.getLogger(__name__)

#: The public site's CloudFront distribution id.
DISTRIBUTION_ID_ENV: Final[str] = "SHIKKHOKPLUS_SITE_DISTRIBUTION_ID"

#: Short timeouts and one retry: a drain that cannot reach CloudFront
#: leaves its rows for the next one rather than holding a worker thread.
_CONFIG: Final = Config(
    connect_timeout=3,
    read_timeout=10,
    retries={"max_attempts": 2, "mode": "standard"},
)


class CloudFrontInvalidationClient:
    """Send invalidation batches to one distribution through boto3."""

    def __init__(self, distribution_id: str, client: Any | None = None) -> None:
        """Bind the client to a distribution.

        :param distribution_id: The site distribution's id
        :param client: A boto3 CloudFront client; built when omitted
        """
        self._distribution_id = distribution_id
        # CloudFront is a global service, signed in us-east-1.
        self._client = client or boto3.client(
            "cloudfront", region_name="us-east-1", config=_CONFIG
        )

    def create_invalidation(self, paths: list[str], caller_reference: str) -> str:
        """Ask CloudFront to evict paths.

        :param paths: The paths
        :param caller_reference: The batch's idempotency key
        :return: The invalidation's id
        """
        response = self._client.create_invalidation(
            DistributionId=self._distribution_id,
            InvalidationBatch={
                "Paths": {"Quantity": len(paths), "Items": list(paths)},
                "CallerReference": caller_reference,
            },
        )
        return str(response["Invalidation"]["Id"])


def client_from_environment() -> InvalidationClient | None:
    """Build the client for the configured distribution, if one is.

    Read at each call, so a restarted process sees the current value.

    :return: The client, or None when no distribution is configured
    """
    distribution = os.environ.get(DISTRIBUTION_ID_ENV, "").strip()
    if not distribution:
        return None
    return CloudFrontInvalidationClient(distribution)


def drain_after_commit(session_factory: Callable[[], Session]) -> None:
    """Drain the outbox once a takedown request has committed, best-effort.

    Runs after the response is sent, in a session of its own. **Never
    raises**: whatever fails here leaves the rows for the ten-minute cron,
    and the takedown itself has already committed.

    :param session_factory: Builds a session on the application's engine
    :return: None
    """
    try:
        client = client_from_environment()
        if client is None:
            log.info("no site distribution configured; invalidations left unsent")
            return
        session = session_factory()
        try:
            invalidation.drain(session, client, dt.datetime.now(tz=dt.UTC))
        finally:
            session.close()
    except Exception as error:  # noqa: BLE001  best-effort by rule: cron is the backstop
        log.warning(
            "cdn invalidation drain after commit failed",
            extra={"error": type(error).__name__},
        )
