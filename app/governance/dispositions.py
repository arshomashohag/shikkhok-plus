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
    "batch": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "The teacher's own record of a class they taught. It holds no "
            "child-identifying data at all -- names live on the "
            "enrollment -- so retaining it after a student's erasure "
            "discloses nothing about that student. `active = false` "
            "retires a batch without deleting its history."
        ),
    ),
    "batch_subject": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "A subject name chosen by the teacher. No personal data of "
            "any kind, and U6 attaches exams to it."
        ),
    ),
    "schedule_slot": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "A weekly recurrence the teacher set. No personal data; U5 "
            "generates session instances from it."
        ),
    ),
    "hidden_batch_preference": TableGovernance(
        disposition=Disposition.HARD_DELETE,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "Purely the viewer's own interface preference, keyed on their "
            "account and visible to nobody else -- not even the teacher. "
            "Nobody else has a claim on it, so it goes with the account."
        ),
    ),
    # -- D3's five tables -------------------------------------------
    #
    # Four of them cascade from `enrollment`, which is the table whose
    # own disposition U11 resolves against the full schema. They are
    # declared here against the same tension and deliberately do NOT
    # pre-empt it: a fee a teacher charged is the teacher's business
    # record and a child's personal data at the same time.
    "fee_cycle": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "The record that a fee was owed for a period. It carries no "
            "money column and no personal data at all -- five columns, "
            "of which only the enrollment reference reaches a person -- "
            "so retaining it after an erasure discloses nothing about "
            "that person while leaving the teacher's record of what was "
            "charged intact. The ledger it indexes is the thing with a "
            "financial-record basis."
        ),
    ),
    "ledger_entry": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "A financial record of money a teacher charged and a family "
            "paid, and the one table in this product where a deletion "
            "would destroy a shared account of a transaction rather than "
            "a person's own data. It is append-only by rule, so a "
            "correction compensates rather than overwrites. It carries "
            "no name, no phone number and no transaction reference -- "
            "only an enrollment, a period, a kind and an amount."
        ),
    ),
    "payment_claim": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "The claimant's assertion that they paid, and the teacher's "
            "decision about it -- a shared record of a dispute, which is "
            "the one thing the payment feature exists to provide. It is "
            "the only D3 table holding something the CLAIMANT authored: "
            "`transaction_id`, a handle on a real payment at a real "
            "provider. Whether that reference survives the claimant's "
            "deletion is OQ-1 and is the human's; the column is nullable "
            "either way, so D6 nulls it in place rather than migrating."
        ),
    ),
    "reminder_event": TableGovernance(
        disposition=Disposition.HARD_DELETE,
        retention=RetentionClass.MONTHS_12,
        basis=(
            "A record that the teacher nudged someone about a fee, "
            "carrying a channel and an outcome and nothing a person "
            "wrote. Nobody has a claim on it once the enrollment is "
            "gone, and unlike the ledger it evidences no transaction, so "
            "it is removed outright rather than retained."
        ),
    ),
    "job_heartbeat": TableGovernance(
        disposition=Disposition.HARD_DELETE,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "Operational telemetry about a scheduled job: when it last "
            "succeeded and three per-run counts. It names no person, "
            "holds no identifier and references no enrollment, so it "
            "falls outside the privacy boundary entirely -- the only D3 "
            "table that does. One row per job name forever, so it is "
            "bounded and small and does not grow with users or time."
        ),
    ),
    "staging_sms_outbox": TableGovernance(
        disposition=Disposition.HARD_DELETE,
        retention=RetentionClass.DAYS_7,
        basis=(
            "A staging-only record of messages the null gateway did not "
            "send, so a person can read a code and sign in on a device "
            "before real SMS credentials exist. It holds a phone number "
            "and an OTP together, which is why it is read only within a "
            "five-minute window and purged with the auth tables. "
            "**It must never hold a row in production**: the writer is a "
            "no-op outside a permitted environment, the route is not "
            "registered, and the startup check refuses a production "
            "process that forced it on."
        ),
    ),
}

#: The retention half, derived so the two can never disagree.
RETENTION: Final[dict[str, RetentionClass]] = {
    table: governance.retention for table, governance in DISPOSITIONS.items()
}
