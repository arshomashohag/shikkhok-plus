"""The area vocabulary an owner picks a district and upazila or thana from."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.schemas.hub import AreaOption

__all__ = ["children"]


def children(session: Session, parent: str | None) -> list[AreaOption]:
    """List the divisions, or the direct children of one area.

    A district's children are its upazilas followed by its city
    corporations, each group by English name; a city corporation's are its
    metropolitan thanas.

    :param session: The session
    :param parent: The enclosing area's code, or None for the divisions
    :return: The areas; empty for an unknown parent
    """
    rows = session.execute(
        sa.text(
            "SELECT code, kind::text AS kind, name_en, name_bn FROM bd_area "
            "WHERE parent_code IS NOT DISTINCT FROM CAST(:parent AS text) "
            "ORDER BY bd_area.kind = 'city_corporation', name_en, code"
        ),
        {"parent": parent},
    )
    return [
        AreaOption.model_validate(
            {"code": r.code, "kind": r.kind, "name_en": r.name_en, "name_bn": r.name_bn}
        )
        for r in rows
    ]
