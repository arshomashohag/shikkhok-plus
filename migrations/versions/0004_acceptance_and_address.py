"""Per-link acceptance decisions, and the signup address.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23

**This is the one part of D1 that runs against live staging data and
cannot be re-run differently afterwards**, so the ordering below is
behaviour rather than convention [functional-spec § 5].

``student_decision`` and ``guardian_decision`` are two INDEPENDENT
per-link facts, sitting beside the two per-link erasure markers the
table already carries. A lens needs ``accepted`` AND an unset erasure
marker [BR6.2]; the two pairs answer different questions -- *did this
person refuse the seat* and *did this person erase themselves* -- and
both are read on every grant.

**The backfill is CONDITIONAL and a column default is forbidden**
[ADR-013, NFR19.2]. Two separate decisions, and each has a failure mode
the other does not:

*Conditional rather than* ``DEFAULT 'pending'``. Under the superseded
model signing in WAS acceptance: ``is_dormant`` was computed as
``student_account_id is None``, so every student already signed in holds
a working lens right now. A plain default would withdraw it --- a
migration that takes away working access on a children's-data product,
discovered when someone opens the app and finds their batches gone. The
honest consequence, recorded rather than hidden: the backfill grants
``accepted`` to people who were never asked, because under the old model
nobody was. The alternative, making every existing user re-accept, would
log them out of their own records to fix a problem they do not have.

*No column default, afterwards either.* A default lets a future insert
path skip the decision silently, and the seat's initial state is exactly
the thing every insert must state. ``add_enrollment`` states it
explicitly for that reason, and a test asserts the absence of the
default rather than trusting this paragraph.

**A native enum rather than a check-constrained string.** This is the
schema's first enum, and the two forms differ in how a fourth value is
later added: a native type needs ``ALTER TYPE ... ADD VALUE``, which is
the point --- widening the set of representable decisions should be a
visible migration rather than an edit to a constraint nobody reads. The
three values are the only representable ones either way [entities.md].

``profile.address`` is nullable because the already-added path can reach
signup with the name pre-filled and no address yet, and a single
free-text field because Bangladesh addresses do not decompose cleanly
into line, city and postcode [entities.md, FR1.17]. Adding the column
does NOT enrol it in the privacy gate: ``OWNER_PRIVATE_FIELDS`` is
matched by name and maintained by hand, so ``address`` joins it in this
same unit [BR3.4].

Reversible: the columns hold decisions nothing else derives from, so
dropping them loses only what this migration added. Unlike ``0002``,
nothing here is folded or destroyed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The enum type's name in the database. Shared by upgrade and downgrade
#: so a rename cannot drift between them.
DECISION_TYPE = "enrollment_decision"

#: The three representable decisions, in state-machine order.
DECISION_VALUES = ("pending", "accepted", "declined")


def upgrade() -> None:
    """Add both decision columns, backfill conditionally, add the address.

    The order is load-bearing: the columns arrive nullable so the
    backfill has somewhere to write, the backfill runs before
    ``SET NOT NULL`` so no existing row violates it, and no default is
    ever attached.

    :return: None
    """
    decision = sa.Enum(*DECISION_VALUES, name=DECISION_TYPE)
    decision.create(op.get_bind(), checkfirst=False)

    # Nullable for the moment, and with NO server_default: attaching one
    # here and dropping it afterwards would leave a window in which an
    # insert could skip the decision, and this migration is the only
    # place that window could exist.
    op.add_column(
        "enrollment",
        sa.Column("student_decision", decision, nullable=True),
    )
    op.add_column(
        "enrollment",
        sa.Column("guardian_decision", decision, nullable=True),
    )

    # THE CONDITIONAL BACKFILL. One statement per column, each reading
    # its OWN link -- a single statement keyed on either link alone
    # would grant the other link a lens its holder never had.
    op.execute(
        sa.text(
            "UPDATE enrollment SET student_decision = CASE "
            "WHEN student_account_id IS NOT NULL THEN 'accepted' "
            "ELSE 'pending' END::enrollment_decision"
        )
    )
    op.execute(
        sa.text(
            "UPDATE enrollment SET guardian_decision = CASE "
            "WHEN guardian_account_id IS NOT NULL THEN 'accepted' "
            "ELSE 'pending' END::enrollment_decision"
        )
    )

    op.alter_column("enrollment", "student_decision", nullable=False)
    op.alter_column("enrollment", "guardian_decision", nullable=False)

    op.add_column("profile", sa.Column("address", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop both decision columns, the enum type and the address.

    Reversible, unlike ``0002``: nothing here is folded or deleted, so
    dropping the columns loses only what this migration added. The
    decisions themselves are lost, which is why the deploy runbook takes
    a ``pg_dump`` first regardless.

    :return: None
    """
    op.drop_column("profile", "address")
    op.drop_column("enrollment", "guardian_decision")
    op.drop_column("enrollment", "student_decision")
    sa.Enum(name=DECISION_TYPE).drop(op.get_bind(), checkfirst=False)
