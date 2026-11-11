"""How Alembic compares the ORM metadata with a migrated database.

One definition, read by two callers: ``migrations/env.py``, so a
developer's ``alembic check`` or ``alembic revision --autogenerate``
compares exactly what CI compares, and ``tests/db/test_schema_parity.py``,
which is the CI gate [ARC-1]. Were the options spelled twice, the gate
could pass under settings an autogenerate then ignores.

**There is no ``include_object`` filter, deliberately.** At head every
table, column, index, unique constraint and foreign key the migrations
create is described in :mod:`app.db.models`, so nothing needs hiding. A
filter added later to silence a difference is an exclusion, and belongs
here with a sentence saying why the object cannot be modelled.

Alembic does not compare CHECK constraints, partial-index predicates,
foreign-key names or enum labels. The models describe all of them anyway,
and the parity test compares them through PostgreSQL's own catalogue.
What the models do not describe, and nothing here compares, is owned by
its migration alone: exclusion constraints, row-level-security policies,
triggers and their functions, grants, and extensions.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

__all__ = ["COMPARE_OPTIONS"]

#: Options passed to ``context.configure`` and ``MigrationContext.configure``.
#:
#: ``compare_type`` is Alembic's default and is stated so it cannot be
#: lost. ``compare_server_default`` is off by default and on here: some
#: columns carry a server default an insert path relies on, and a model
#: that forgot one would otherwise pass.
COMPARE_OPTIONS: Final[Mapping[str, bool]] = {
    "compare_type": True,
    "compare_server_default": True,
}
