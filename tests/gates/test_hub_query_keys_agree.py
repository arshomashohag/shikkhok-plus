"""The edge, the CDN and the origin read the same seven query keys.

Three lists name the public hub's query keys and must never drift apart:

* ``ALLOWED`` in ``infra/modules/site/functions/hub-query.js``, which
  refuses any other key with a 400 at the edge;
* ``hub_query_strings`` in ``infra/modules/site/main.tf``, which puts
  exactly those keys in the cache key and forwards them to the origin;
* :data:`app.hub.public.routes.QUERY_KEYS`, the keys the origin reads.

A key in the edge list but not the cache policy would be accepted and then
dropped, so every value of it shared one cache entry; a key in the origin
list but not the edge's would be refused before the origin saw it. The
count is asserted because three comments state it ("seven").
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

from app.hub.public.routes import QUERY_KEYS

ROOT: Final = pathlib.Path(__file__).resolve().parents[2]
FUNCTION: Final = ROOT / "infra" / "modules" / "site" / "functions" / "hub-query.js"
SITE_MODULE: Final = ROOT / "infra" / "modules" / "site" / "main.tf"

#: The number the comments in all three files state.
KEY_COUNT: Final = 7


def _list_literal(text: str, pattern: str) -> list[str]:
    """Read the quoted strings of one list literal.

    :param text: The source file's text
    :param pattern: A regex whose group 1 is the list's body
    :return: The strings, in order
    :raises AssertionError: The list is not there exactly once
    """
    found = re.findall(pattern, text)
    assert len(found) == 1, f"expected one match of {pattern!r}, found {len(found)}"
    return re.findall(r"""['"]([^'"]+)['"]""", found[0])


def _edge_keys() -> list[str]:
    """Read ``ALLOWED`` from the viewer-request function.

    :return: The keys
    """
    return _list_literal(FUNCTION.read_text(), r"var ALLOWED = \[([^\]]*)\];")


def _edge_lowercased() -> list[str]:
    """Read ``LOWERCASED`` from the viewer-request function.

    :return: The keys
    """
    return _list_literal(FUNCTION.read_text(), r"var LOWERCASED = \[([^\]]*)\];")


def _cdn_keys() -> list[str]:
    """Read ``hub_query_strings`` from the site module's locals.

    :return: The keys
    """
    return _list_literal(
        SITE_MODULE.read_text(), r"hub_query_strings\s*=\s*\[([^\]]*)\]"
    )


def test_edge_and_origin_query_keys_agree() -> None:
    """``ALLOWED`` == ``hub_query_strings`` == ``QUERY_KEYS``, in one order."""
    edge, cdn, origin = _edge_keys(), _cdn_keys(), list(QUERY_KEYS)

    assert edge == cdn == origin
    assert len(set(origin)) == len(origin) == KEY_COUNT
    assert "sort" in origin


def test_edge_lowercases_only_allowed_keys() -> None:
    """Every key the edge lowercases is one it allows, ``sort`` among them."""
    lowered = _edge_lowercased()

    assert set(lowered) <= set(_edge_keys())
    assert lowered == ["subject", "level", "sort"]


def test_the_reader_fires_on_a_drifted_list() -> None:
    """A list missing ``sort`` reads as different, so the gate is not vacuous."""
    drifted = 'var ALLOWED = ["q", "district", "upazila", "subject", "level", "page"];'

    keys = _list_literal(drifted, r"var ALLOWED = \[([^\]]*)\];")

    assert keys != list(QUERY_KEYS)
