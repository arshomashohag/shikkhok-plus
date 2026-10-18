"""The declarative base and the naming convention.

The naming convention is set here rather than left to SQLAlchemy's
defaults because Alembic's autogenerate emits constraint names into the
migration, and an unnamed constraint gets a database-assigned name that
differs between the migrated schema and a metadata-created one. The
privacy suite asserts a *policy* exists on a named table, and the
governance test iterates the *migrated* schema -- both read better when a
constraint's name is a fact of the model rather than of the server.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

__all__ = ["NAMING_CONVENTION", "Base"]

#: Deterministic constraint names, so a migration and a metadata-created
#: schema agree on them.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """The declarative base every model in this project derives from."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
