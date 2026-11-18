"""Turning a stored photo into the ``<img>`` a hub page renders.

One builder for the public pages and the owner's preview, so the two cannot
describe the same photo differently; only where each variant is fetched
from differs, which the caller supplies as ``url``:

- a public page names ``/m/{public_key}/{w}.webp`` (:func:`public_path`),
  relative, because the page and the photo are both on the site's host and
  the page CSP's ``img-src 'self'`` covers it;
- the preview, shown on the app host, names the same path on the site's
  origin for an approved photo and a five-minute signed GET of the staged
  variant for one awaiting review.

**Widths.** The sanitiser writes each target width in
:data:`app.hub.media.storage.VARIANT_WIDTHS` at ``min(target, source)``
pixels, never upscaled, skipping a target whose pixels equal the previous
one's, and records the targets it wrote as ``widths``. A variant's file is
named for its target; the ``srcset`` describes it by its real pixel width,
so a 500-pixel source's ``960.webp`` is ``500w``, never a claimed ``960w``.

**Dimensions.** ``width`` and ``height`` are the ``src`` variant's own
pixels, computed as the sanitiser computes them (``round(height * w /
width)``, at least 1), so a page reserves the photo's box before it loads.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from typing import Final

from app.hub.public.messages import Locale
from app.hub.public.views import HubImage

__all__ = ["SRC_WIDTH", "hub_image", "image_alt", "public_path"]

#: The variant ``src`` names when it was written: wide enough for the
#: gallery at twice its density, a fraction of the 1600's bytes.
SRC_WIDTH: Final[int] = 960


def public_path(public_key: str, width: int) -> str:
    """Name one approved variant as the site serves it.

    :param public_key: The photo's public key
    :param width: The variant's target width
    :return: ``/m/{public_key}/{width}.webp``
    """
    return f"/m/{public_key}/{width}.webp"


def image_alt(alt_en: str | None, alt_bn: str | None, locale: Locale) -> str:
    """Pick the alt text in the page's locale, else the other locale's.

    :param alt_en: The English alt text
    :param alt_bn: The Bangla alt text
    :param locale: The page's locale
    :return: The text; empty only when neither locale has any
    """
    first, second = (alt_en, alt_bn) if locale == "en" else (alt_bn, alt_en)
    return first or second or ""


def hub_image(
    *,
    media_id: uuid.UUID,
    widths: Sequence[int],
    width: int,
    height: int,
    alt: str,
    url: Callable[[int], str],
    awaiting_review: bool = False,
) -> HubImage:
    """Describe one stored photo as a page's ``<img>``.

    :param media_id: The photo
    :param widths: The variant target widths written
    :param width: The decoded source's width in pixels
    :param height: The decoded source's height in pixels
    :param alt: The alt text, already in the page's locale
    :param url: Where one variant, named by its target width, is fetched
    :param awaiting_review: Whether the preview marks it as not yet approved
    :return: The image
    :raises ValueError: No variant was written, or the source has no size
    """
    targets = sorted(set(widths))
    if not targets or width < 1 or height < 1:
        msg = f"photo {media_id} has no variant or no size to render"
        raise ValueError(msg)
    src = SRC_WIDTH if SRC_WIDTH in targets else targets[-1]
    src_width = min(src, width)
    return HubImage(
        media_id=media_id,
        src=url(src),
        srcset=", ".join(f"{url(target)} {min(target, width)}w" for target in targets),
        width=src_width,
        height=max(1, round(height * src_width / width)),
        alt=alt,
        awaiting_review=awaiting_review,
    )
