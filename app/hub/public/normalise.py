"""Turn what a reader typed into the search box into safe search terms.

A Bangla query arrives in many spellings of the same thing: composed or
decomposed, with a zero-width joiner a keyboard inserted, with Bangla
digits, mixed with Latin. Each term this module returns is made only of
letters, combining marks and digits, so it can be handed to
``to_tsquery`` as a prefix without any character the query syntax reads
as an operator -- which is what keeps a stray ``&``, ``'`` or ``:`` from
becoming a database error and a 500 [Review Focus 3].

The stored side is normalised the same way: both listing search vectors
pass their text through ``hub_search_norm`` (``0040``), which strips the
same zero-width characters, applies NFC and maps Bangla digits, in this
order. Change one and the other must follow;
``tests/db/test_migration_0040.py`` compares them.
"""

from __future__ import annotations

import unicodedata
from typing import Final

__all__ = ["MAX_TERMS", "MAX_TERM_LENGTH", "query_terms"]

#: At most this many terms are searched; the rest are dropped.
MAX_TERMS: Final[int] = 8

#: A term longer than this is cut to this many characters.
MAX_TERM_LENGTH: Final[int] = 40

#: Zero-width space, non-joiner, joiner, and the byte-order mark.
_ZERO_WIDTH: Final[dict[int, None]] = dict.fromkeys((0x200B, 0x200C, 0x200D, 0xFEFF))

#: Bangla digits (U+09E6 to U+09EF) to Latin 0-9.
_BANGLA_DIGITS: Final[dict[int, str]] = {0x09E6 + n: str(n) for n in range(10)}


def _word_char(char: str) -> bool:
    """Report whether a character may stand inside a search term.

    Letters, combining marks (a Bangla vowel sign is one) and digits.
    Everything else separates terms.

    :param char: One character
    :return: True when it belongs to a word
    """
    return unicodedata.category(char)[0] in {"L", "M", "N"}


def query_terms(q: str) -> list[str]:
    """Split a search query into normalised terms.

    Strips zero-width characters, NFC-normalises, maps Bangla digits to
    Latin, lowercases, treats anything but a letter, mark or digit as a
    separator, drops empty terms, and keeps at most :data:`MAX_TERMS`
    terms of at most :data:`MAX_TERM_LENGTH` characters each.

    :param q: The query as typed
    :return: The terms, in the order typed
    """
    # Zero-width characters go first: a joiner between a base and its mark
    # would otherwise keep NFC from composing them.
    text = unicodedata.normalize("NFC", q.translate(_ZERO_WIDTH))
    text = text.translate(_BANGLA_DIGITS).lower()
    spaced = "".join(char if _word_char(char) else " " for char in text)
    return [term[:MAX_TERM_LENGTH] for term in spaced.split()][:MAX_TERMS]
