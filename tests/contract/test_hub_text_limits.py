"""Every hub editor text field is bounded exactly as its column is [I1].

A request schema looser than the database lets a value through validation
that a ``CHECK`` then refuses, and the owner reads ``error.unexpected``
instead of a field-length message. Tighter would refuse text the column
holds. So the two numbers are compared here rather than kept in step by
hand, which is how they drifted (a 200-character headline against a
140-character check).
"""

from __future__ import annotations

import re
import typing
from typing import Final

import annotated_types
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from sqlalchemy import CheckConstraint, String
from sqlalchemy.dialects.postgresql import ARRAY

from app.db.models import Base, BatchListing, OwnerListing
from app.schemas.hub import BatchListingUpdateRequest, OwnerListingUpdateRequest

#: Each editor request and the table its fields are stored in.
PAIRS: Final[tuple[tuple[type[BaseModel], type[Base]], ...]] = (
    (OwnerListingUpdateRequest, OwnerListing),
    (BatchListingUpdateRequest, BatchListing),
)

#: Fields whose request bound may differ from the column, with the reason.
EXEMPT: Final[dict[tuple[str, str], str]] = {
    ("OwnerListingUpdateRequest", "public_contact_phone"): (
        "typed with spaces, dashes or a +880 prefix and stored canonical, "
        "which is never longer than the 20-character column"
    ),
}


def _max_len(metadata: list[object]) -> int | None:
    """Read a ``max_length`` out of field or type metadata.

    :param metadata: Pydantic metadata
    :return: The bound, or None
    """
    for item in metadata:
        if isinstance(item, annotated_types.MaxLen):
            return int(item.max_length)
        if isinstance(item, FieldInfo):
            found = _max_len(item.metadata)
            if found is not None:
                return found
    return None


def _string_bound(model: type[BaseModel], name: str) -> int | None:
    """Find the request's character bound on one string field.

    :param model: The request model
    :param name: The field
    :return: The bound on the string or on each string of a list, or None
        for a field that carries no free text
    """
    field = model.model_fields[name]
    leaves = [a for a in typing.get_args(field.annotation) if a is not type(None)] or [
        field.annotation
    ]
    for leaf in leaves:
        if leaf is str:
            return _max_len(field.metadata)
        if typing.get_origin(leaf) is list:
            (item,) = typing.get_args(leaf)
            if typing.get_origin(item) is typing.Annotated:
                base, *meta = typing.get_args(item)
                if base is str:
                    return _max_len(meta)
    return None


def _column_bound(table: type[Base], name: str) -> int:
    """Find the database's character bound on one column.

    :param table: The mapped table
    :param name: The column
    :return: Its ``char_length`` CHECK bound, else its ``VARCHAR`` width
    """
    pattern = re.compile(rf"{name} IS NULL OR char_length\({name}\) <= (\d+)")
    for constraint in table.__table__.constraints:
        if isinstance(constraint, CheckConstraint):
            found = pattern.fullmatch(str(constraint.sqltext))
            if found:
                return int(found.group(1))
    column_type = table.__table__.c[name].type
    if isinstance(column_type, ARRAY):
        column_type = column_type.item_type
    assert isinstance(column_type, String) and column_type.length, (
        f"{table.__tablename__}.{name} has no length bound to compare against"
    )
    return int(column_type.length)


def test_request_text_bounds_equal_the_column_bounds() -> None:
    """Each free-text field's ``max_length`` is its column's bound."""
    compared = []
    for request, table in PAIRS:
        for name in request.model_fields:
            bound = _string_bound(request, name)
            if bound is None:
                continue
            assert name in table.__table__.c, f"{request.__name__}.{name}"
            if (request.__name__, name) in EXEMPT:
                continue
            compared.append(name)
            assert bound == _column_bound(table, name), (
                f"{request.__name__}.{name} allows {bound} characters but "
                f"{table.__tablename__}.{name} holds {_column_bound(table, name)}"
            )
    assert {
        "headline_en",
        "bio_bn",
        "street_address",
        "public_title",
        "description_en",
        "syllabus_bn",
        "subject_tags",
    } <= set(compared)


def test_every_exemption_names_a_real_field() -> None:
    """A stale exemption would quietly widen the gate."""
    names = {m.__name__: m for m, _ in PAIRS}
    for model, field in EXEMPT:
        assert field in names[model].model_fields
