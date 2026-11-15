"""The area vocabulary an owner picks a district and upazila from."""

from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

__all__ = ["AreaRow", "list_areas"]


@dataclass(frozen=True, slots=True)
class AreaRow:
    """One division, district or upazila.

    :ivar code: The BBS geocode
    :ivar kind: ``division``, ``district`` or ``upazila``
    :ivar name_en: The English name
    :ivar name_bn: The Bangla name
    """

    code: str
    kind: str
    name_en: str
    name_bn: str


def list_areas(session: Session, parent: str | None) -> list[AreaRow]:
    """List the divisions, or the direct children of one area.

    :param session: The session
    :param parent: The enclosing area's code, or None for the divisions
    :return: The areas by English name; empty for an unknown parent
    """
    rows = session.execute(
        sa.text(
            "SELECT code, kind::text AS kind, name_en, name_bn FROM bd_area "
            "WHERE parent_code IS NOT DISTINCT FROM CAST(:parent AS text) "
            "ORDER BY name_en, code"
        ),
        {"parent": parent},
    )
    return [AreaRow(r.code, r.kind, r.name_en, r.name_bn) for r in rows]
