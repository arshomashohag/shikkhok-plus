"""The CloudFront invalidation outbox: which paths a takedown evicts.

Public owner and batch pages are cached at the edge for up to ten minutes. A
takedown -- a suspension, an unpublish, a retired batch, a withdrawn name
consent or an ended membership, a solo owner's account deletion, a slug
change -- changes rows the pages are read from, and without an invalidation
the edge goes on serving the page until its TTL ends.

**Enqueued in the takedown's own transaction.** :func:`enqueue` adds rows to
the caller's transaction and commits nothing, so a takedown that rolls back
leaves no row and one that commits cannot lose its row [Review Focus 2].

**Sent by the host, never by the container** [R8, OPS-4]. No process in the
application container calls CloudFront: the container's only AWS client is
the photo bucket's, in ``app/hub/media/storage.py``, under a role with no
CloudFront permission. A host cron runs
``app.hub.public.commands claim`` inside the running container, sends what it
prints with the host's own AWS CLI, and reports back with ``ack`` or ``fail``.

**No caller writes a path by hand.** CloudFront accepts ``*`` only as a
path's last character, so the paths come from :func:`owner_paths`,
:func:`batch_paths` and :func:`media_paths`, and :func:`enqueue` refuses
anything else. Every enqueue also carries :data:`SITEMAP_PATH`, which lists
what the takedown removed. A path holds only public slugs and public photo
keys.

The outbox is written through a lightweight table construct rather than the
ORM model: this package may not import ``app.db.models``.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.hub.public.messages import LOCALES

__all__ = [
    "MAX_PATH",
    "OUTBOX",
    "SITEMAP_PATH",
    "batch_paths",
    "enqueue",
    "media_paths",
    "owner_paths",
]

#: The sitemap, which every takedown changes.
SITEMAP_PATH: Final[str] = "/hub/sitemap.xml"

#: A photo's public key: 32 lower-case hex digits [0043].
_PUBLIC_KEY: Final = re.compile(r"[0-9a-f]{32}")

#: The sanitiser's variant widths. Restated rather than imported, because
#: the storage module imports boto3, which this package may never reach;
#: ``tests/hub/media/test_library.py`` asserts the two are equal.
_VARIANT_WIDTHS: Final[tuple[int, ...]] = (320, 960, 1600)

#: The ``path`` column's width.
MAX_PATH: Final[int] = 300

#: The outbox table, for this package's own reads and writes.
OUTBOX: Final = sa.table(
    "cdn_invalidation",
    sa.column("id"),
    sa.column("path"),
    sa.column("requested_at"),
    sa.column("sent_at"),
    sa.column("aws_id"),
    sa.column("attempts"),
)


def owner_paths(slug: str) -> list[str]:
    """Build the paths that evict an owner's page and every batch page under it.

    :param slug: The owner's slug
    :return: One prefix path per locale, each ending in ``*``
    """
    return [f"/hub/{locale}/t/{slug}*" for locale in LOCALES]


def batch_paths(owner_slug: str, batch_slug: str) -> list[str]:
    """Build the paths that evict one batch's page.

    :param owner_slug: The owner's slug
    :param batch_slug: The batch's slug
    :return: One exact path per locale
    """
    return [f"/hub/{locale}/t/{owner_slug}/{batch_slug}" for locale in LOCALES]


def media_paths(public_key: str) -> list[str]:
    """Build the paths that evict one photo's variants at ``/m/``.

    The three variant paths exactly, no wildcard: CloudFront allows only
    15 wildcard invalidations in progress, and an account deletion with
    many photos would queue one each. A variant the sanitiser did not
    write (a small photo is never upscaled) costs one path of nothing.

    :param public_key: The photo's public key, as it was while approved
    :return: ``/m/{key}/{w}.webp`` for each variant width
    :raises ValueError: The key is not 32 lower-case hex digits
    """
    if not _PUBLIC_KEY.fullmatch(public_key):
        raise ValueError("a photo key is 32 lower-case hex digits")
    return [f"/m/{public_key}/{width}.webp" for width in _VARIANT_WIDTHS]


def _require_valid(path: str) -> None:
    """Refuse a path CloudFront would reject or the column cannot hold.

    :param path: The path
    :raises ValueError: It is relative, too long, or has an inner wildcard
    """
    if not path.startswith("/"):
        raise ValueError(f"an invalidation path must be absolute: {path!r}")
    if "*" in path[:-1]:
        raise ValueError(
            f"an invalidation path may carry a wildcard only at its end: {path!r}"
        )
    if len(path) > MAX_PATH:
        raise ValueError(f"an invalidation path exceeds {MAX_PATH} characters")


def enqueue(session: Session, paths: Sequence[str], now: dt.datetime) -> None:
    """Add paths, and the sitemap, to the caller's transaction.

    Commits nothing: the rows commit or roll back with the takedown.

    :param session: The takedown's session, inside its transaction
    :param paths: The paths to evict, from :func:`owner_paths` or
        :func:`batch_paths`
    :param now: The moment of the takedown
    :return: None
    :raises ValueError: A path CloudFront would reject
    """
    wanted = list(dict.fromkeys([*paths, SITEMAP_PATH]))
    for path in wanted:
        _require_valid(path)
    session.execute(
        sa.insert(OUTBOX),
        [{"path": path, "requested_at": now} for path in wanted],
    )
