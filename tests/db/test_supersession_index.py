"""The supersession probe is indexed [audit C-04].

Every ledger read that hides corrected entries runs a correlated
``NOT EXISTS (... superseded_by_id = id)`` per row. Without an index each
probe scanned the whole ledger -- every tenant's -- and a 25-seat batch's
fee month took 45 seconds at audit scale. The planner chooses a
sequential scan on the tiny tables a test builds, so this asserts the
index rather than a plan.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session


def test_the_partial_index_exists(owner_session: Session) -> None:
    """The index is present, on the right column, partial on non-NULL.

    :param owner_session: A session able to read the catalog
    :return: None
    """
    definition = owner_session.scalar(
        sa.text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'ix_ledger_entry_superseded_by_id'"
        )
    )
    assert definition is not None
    assert "(superseded_by_id)" in definition
    assert "WHERE (superseded_by_id IS NOT NULL)" in definition
