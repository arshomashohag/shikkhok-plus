"""The public hub's own strings, in English and Bangla.

Public pages are rendered on the server, so their words live here rather
than in the Android or web bundles. Every key carries both locales; a
missing locale is a ``KeyError`` at the call, never a silent English
fallback on a Bangla page.
"""

from __future__ import annotations

from typing import Final, Literal

__all__ = ["LOCALES", "MESSAGES", "Locale", "t"]

#: The locales every public page is served in.
Locale = Literal["en", "bn"]

#: The same locales as a tuple, English (the ``x-default``) first.
LOCALES: Final[tuple[Locale, ...]] = ("en", "bn")

#: Each message key's text per locale.
MESSAGES: Final[dict[str, dict[Locale, str]]] = {
    # Named in place of a centre's teachers when none agreed to be named.
    "centre_faculty": {"en": "Centre faculty", "bn": "সেন্টারের শিক্ষকবৃন্দ"},
}


def t(key: str, locale: Locale) -> str:
    """Look up one message in one locale.

    :param key: The message key
    :param locale: ``en`` or ``bn``
    :return: The text
    :raises KeyError: The key, or its locale, is not in :data:`MESSAGES`
    """
    return MESSAGES[key][locale]
