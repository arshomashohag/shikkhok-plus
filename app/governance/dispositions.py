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

    ``NOT_PERSONAL`` exists because the other three values all answer
    "what does this person's deletion do to their rows?", and for a
    counter or a job's heartbeat the honest answer is that the question
    does not apply: the rows are not about a person, so a deletion does
    nothing to them. **Forcing such a table into one of the other three
    published a false statement.** ``rate_limit_counter`` was declared
    ``HARD_DELETE`` while ``delete_account`` deliberately never touched
    it -- clearing it on request would make the public deletion route
    the way to reset the abuse ceilings protecting a phone number -- and
    the generated policy duly told parents and a regulator that the
    counters were removed with the account. ``RETAIN_WITH_BASIS`` would
    have been just as wrong in the other direction: it is the heading
    for rows that are somebody's personal data and are kept anyway, and
    filing a job heartbeat under it claims this product retains personal
    data it does not hold.
    """

    HARD_DELETE = "hard_delete"
    ANONYMIZE_IN_PLACE = "anonymize_in_place"
    RETAIN_WITH_BASIS = "retain_with_basis"
    NOT_PERSONAL = "not_personal"


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
        disposition=Disposition.HARD_DELETE,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        # **Both fields changed together, and that is the point**
        # [BR1.1, NFR14.101]. This entry read ANONYMIZE_IN_PLACE with a
        # basis ARGUING for anonymization -- "a hard delete would free
        # the number for reuse by a different person while enrollments
        # still reference the account" -- and the human chose the
        # published policy's promise over it on 2026-10-25.
        #
        # The generated privacy policy READS THIS FIELD. Correcting the
        # disposition and leaving the old basis would publish, as the
        # stated reasoning for a hard delete, an argument against doing
        # one: a document mechanically consistent with the code and
        # substantively wrong, which is WORSE than the three-way
        # disagreement it replaces, because that one was at least
        # visible to anyone who read two files.
        #
        # The old basis named a REAL hazard and it is closed rather than
        # dismissed -- by the constraint, not by this field. See BR1.2:
        # `0007` makes the three account references SET NULL, so a
        # deleted account leaves its enrollments standing with their
        # links cleared and a new account taking the same number
        # inherits no link to the old one. The hazard was real; the
        # remedy it proposed was not the only one.
        basis=(
            "The phone number and the account row are removed outright, "
            "which is what releases the number. Enrollments survive "
            "with their account links cleared by the database "
            "constraint rather than by the deletion code, so a new "
            "account registering the same number later inherits "
            "nothing from the deleted one."
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
        disposition=Disposition.NOT_PERSONAL,
        # **The basis states what the DISPOSITION does, not what the
        # table is** [NFR14.101]. The previous text -- "the longest
        # window is a day, so a 48-hour retention covers every live
        # counter" -- described only the retention class, and a basis
        # that never mentions deletion cannot contradict a wrong
        # deletion label. That is precisely why this entry sat at
        # HARD_DELETE against a `Scope.NOT_PERSONAL` scoping and an
        # implementation that never deleted it: unlike `account`, whose
        # basis ARGUED a position and so forced the two to be checked
        # against each other, nothing here could disagree with anything.
        retention=RetentionClass.HOURS_48,
        basis=(
            "A deletion request does nothing to these rows, and that is "
            "deliberate rather than an omission. The counters are keyed "
            "on a scope VALUE -- for two of the seven scopes a phone "
            "number -- and they are the abuse control itself, so "
            "clearing a number's counters on request would make the "
            "public deletion route the way to reset the ceilings "
            "protecting it. They are not a record about a person; they "
            "are a count of recent attempts, and they expire on their "
            "own 48-hour window, which is longer than the longest "
            "counting window with room to spare."
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
        disposition=Disposition.NOT_PERSONAL,
        # Same correction as `rate_limit_counter`, same reason: the old
        # basis described the TABLE ("names no person, holds no
        # identifier") and stopped short of saying what a deletion does,
        # so HARD_DELETE could sit above it unchallenged. The table's
        # nature is the ARGUMENT for the disposition; it is not the
        # disposition.
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "A deletion request does nothing to these rows, because "
            "they are not about a person. The table holds operational "
            "telemetry about a scheduled job -- when it last succeeded "
            "and three per-run counts -- naming no person, holding no "
            "identifier and referencing no enrollment. Removing a row "
            "on one person's request would destroy the freshness signal "
            "every user depends on while erasing nothing of theirs. One "
            "row per job name, so it is bounded and does not grow with "
            "users or time."
        ),
    ),
    # -- D4's six tables ---------------------------------------------
    #
    # **The unit where this product's children's data arrives.** Until
    # D4 the boundary protected a self-chosen name, a photo reference,
    # an address and a fee balance; these tables store a record of where
    # a named child was on a given afternoon and how they performed.
    #
    # The values are TRANSCRIBED from the prior components catalogue,
    # not invented here. `RETAIN_WITH_BASIS` is the case the enum value
    # was created for, and its own docstring names attendance and marks
    # explicitly [BR6.1].
    "session": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "The teacher's record that a class was held on a date, at a "
            "time, covering a topic. It names no person at all -- "
            "attendance is the separate table that reaches one -- so "
            "retaining it after a student's erasure discloses nothing "
            "about that student while leaving the teacher's record of "
            "what they taught intact."
        ),
    ),
    "queued_submission": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "The record that one queued write -- a roster or a topic "
            "log -- was accepted, carrying a version number, a replay "
            "key and who submitted it. It takes attendance's "
            "disposition and retention because it holds nothing "
            "attendance does not and is meaningless without it: every "
            "row it describes cascades from the same session. The "
            "account it names is the TEACHER who submitted, never the "
            "child."
        ),
    ),
    "attendance": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "Whether a child attended a class, written by the TEACHER. "
            "This is the direct tension RETAIN_WITH_BASIS exists for: "
            "the same row is the teacher's own record of who was in "
            "their classroom and the child's personal data. It carries "
            "no name -- only an enrollment reference -- and D6 resolves "
            "the tension against the full schema rather than this unit "
            "pre-empting it."
        ),
    ),
    "exam": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "An assessment the teacher set: a title, a date, a subject "
            "and a total. It holds no result and reaches no person, so "
            "it is the teacher's record of their own curriculum and "
            "retaining it discloses nothing about any child."
        ),
    ),
    "mark": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "What a child scored, written by the TEACHER and the second "
            "case RETAIN_WITH_BASIS was created for. Append-only with a "
            "supersession chain, so a correction is visible rather than "
            "destructive -- which is what makes a disputed mark "
            "answerable at all. It carries no name, only an enrollment "
            "and an exam, and D6 resolves the erasure tension against "
            "the full schema."
        ),
    ),
    "announcement": TableGovernance(
        disposition=Disposition.RETAIN_WITH_BASIS,
        retention=RetentionClass.LIFE_OF_ACCOUNT,
        basis=(
            "A note the teacher posted to a whole batch, which stays "
            "with that batch's history. It is addressed to no one "
            "person and holds nothing a student or guardian wrote. "
            "Soft-deleted rather than removed, so a note withdrawn from "
            "view still records that it was posted, and it NEVER "
            "expires on the passage of time."
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
