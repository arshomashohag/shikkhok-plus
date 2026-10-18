"""What happens to each table's rows on deletion, and for how long.

**The privacy policy is generated from this, not written beside it.** A
privacy policy that contradicts the implementation is worse than a vague
one, and the only way to keep the two in step is to have one of them be
the source.

Two manifests, because they answer different questions:

* a **disposition** per table and actor -- what deletion does;
* a **retention class** per table -- how long a row lives even without a
  deletion request.

A test iterates the **migrated schema** and fails on any live table
missing an entry, so a table added in a later Unit cannot quietly arrive
without a decision having been made about it.

``account_deletion`` dispositions are declared here but **enforced by
U11**, which owns both deletion paths. Declaring them now rather than
with the implementation is deliberate: they are decided against the full
schema once, rather than rediscovered per table.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final

__all__ = [
    "DISPOSITIONS",
    "RETENTION",
    "Disposition",
    "RetentionClass",
    "TableGovernance",
]


class Disposition(enum.Enum):
    """What deletion does to a table's rows.

    ``RETAIN_WITH_BASIS`` exists because a student's attendance and marks
    were written by the **teacher** and are the teacher's record, while
    the same rows are the child's personal data. A guardian's erasure
    right and a teacher's legitimate business record are in direct
    tension, and pretending otherwise produces a policy nobody can
    implement.
    """

    HARD_DELETE = "hard_delete"
    ANONYMIZE_IN_PLACE = "anonymize_in_place"
    RETAIN_WITH_BASIS = "retain_with_basis"


class RetentionClass(enum.Enum):
    """How long a row lives absent any deletion request."""

    DAYS_7 = "7_days"
    HOURS_48 = "48_hours"
    MONTHS_12 = "12_months"
    UNTIL_EXPIRY_PLUS_30_DAYS = "until_expiry_plus_30_days"
    LIFE_OF_ACCOUNT = "life_of_account"


@dataclass(frozen=True, slots=True)
class TableGovernance:
    """One table's written decisions.

    :ivar disposition: What account deletion does to these rows
    :ivar retention: How long a row lives without a deletion request
    :ivar basis: Why, in one sentence, for the generated policy text
    """

    disposition: Disposition
    retention: RetentionClass
    basis: str


#: Every table this Unit creates. A later Unit adding a table without an
#: entry here fails the governance test rather than shipping undeclared.
DISPOSITIONS: Final[dict[str, TableGovernance]] = {
    "account": TableGovernance(
        disposition=Disposition.ANONYMIZE_IN_PLACE,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "The phone number is the permanent key, so the row is "
            "anonymized rather than removed: a hard delete would free the "
            "number for reuse by a different person while enrollments "
            "still reference the account."
        ),
    ),
    "profile": TableGovernance(
        disposition=Disposition.HARD_DELETE,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "Everything here is self-authored and owner-private. Nobody "
            "else has a claim on it, so it is removed outright."
        ),
    ),
    "otp_request": TableGovernance(
        disposition=Disposition.HARD_DELETE,
        retention=RetentionClass.DAYS_7,
        basis=(
            "High volume, carries a phone number, and has an obviously "
            "short lifetime. A code is useless after five minutes."
        ),
    ),
    "verify_attempt": TableGovernance(
        disposition=Disposition.HARD_DELETE,
        retention=RetentionClass.DAYS_7,
        basis="Tied to an OTP that is itself purged after seven days.",
    ),
    "refresh_token": TableGovernance(
        disposition=Disposition.HARD_DELETE,
        retention=RetentionClass.UNTIL_EXPIRY_PLUS_30_DAYS,
        basis=(
            "Reuse detection needs the rotated-out row to still exist, so "
            "the row outlives the token it represents."
        ),
    ),
    "rate_limit_counter": TableGovernance(
        disposition=Disposition.HARD_DELETE,
        retention=RetentionClass.HOURS_48,
        basis=(
            "The longest window is a day, so a 48-hour retention covers "
            "every live counter with room to spare."
        ),
    ),
    "auth_audit_log": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.MONTHS_12,
        basis=(
            "Retained to answer whether a child's data was accessed "
            "improperly, which both COPPA and GDPR-K assume can be "
            "answered. It holds no OTP, no token, no phone number and no "
            "child name, so retaining it discloses nothing about the "
            "person it concerns."
        ),
    ),
    "owner": TableGovernance(
        disposition=Disposition.HARD_DELETE,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis="U4 owns this table's behaviour; U3 declares its shape only.",
    ),
    "enrollment": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "display_name is TEACHER-authored and part of the teacher's "
            "own record. This is the direct tension between a guardian's "
            "erasure right and a teacher's business record, and U11 "
            "resolves it against the full schema."
        ),
    ),
}

#: The retention half, derived so the two can never disagree.
RETENTION: Final[dict[str, RetentionClass]] = {
    table: governance.retention for table, governance in DISPOSITIONS.items()
}
