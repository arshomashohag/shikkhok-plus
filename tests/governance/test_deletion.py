"""Deletion asserts the ABSENCE of rows, enumerated from the manifest.

**`team.md`: deletion features are the ones most reliably shipped
broken, because nobody tests the absence of data.** A hand-listed test
covers the tables its author thought of; the table added two units later
keeps a child's personal data and nothing fails. So the table list comes
from ``DISPOSITIONS`` and from ``HARD_DELETE_SCOPES``, never from a
literal here [BR1.3].

Test-first under the ordering predicate: the expected row sets come from
the manifest without the code having been written, and a wrong answer
leaves a child's data behind or destroys another person's retained
records.

**Both roles are asserted, and the student is the one that was broken.**
A guardian's link was already ``SET NULL``; a student's was ``CASCADE``
until ``0007``. A test using only a guardian passes against the defect.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.governance.deletion import (
    HARD_DELETE_SCOPES,
    Scope,
    delete_account,
    hard_delete_tables,
)
from app.governance.dispositions import DISPOSITIONS, Disposition
from tests.governance.conftest import PopulatedSeat

# ---------------------------------------------------------------------------
# THE MANIFEST COMPLETENESS GATE. [BR1.3]
#
# This is what makes every assertion below survive D7. A table added
# later with HARD_DELETE and no scoping decision fails HERE, without
# anybody editing a deletion test.
# ---------------------------------------------------------------------------


def test_every_hard_delete_table_has_a_scoping_decision() -> None:
    """A new ``HARD_DELETE`` table cannot arrive undeclared.

    The direction that keeps a child's data: a table whose rows nothing
    reaches would otherwise be skipped in silence.

    :return: None
    """
    undeclared = hard_delete_tables() - set(HARD_DELETE_SCOPES)

    assert undeclared == set(), (
        f"these tables are HARD_DELETE and no deletion scoping decision "
        f"exists for them: {sorted(undeclared)}. Deletion cannot reach a "
        "table without knowing which column identifies the person, so "
        "these rows would survive a deletion that claims to remove them."
    )


def test_no_scoping_decision_names_a_table_that_is_not_hard_delete() -> None:
    """The other direction: a stale entry describes a decision nobody made.

    **``NOT_PERSONAL`` entries are subtracted, and that is not a
    weakening of this gate.** The map's job is to record, for every
    table deletion had to consider, how it reaches the rows -- and for
    two of them the answer is "it does not, on purpose". Dropping those
    entries to satisfy a membership check would delete the written
    reason the deletion route cannot be used to reset a phone number's
    abuse ceilings, which is the most load-bearing note in the file. The
    exemption is not open-ended: it is bounded to the
    ``Scope.NOT_PERSONAL`` entries, and
    ``test_not_personal_scoping_and_not_personal_disposition_agree``
    pins each of those to a ``NOT_PERSONAL`` disposition in the other
    manifest, so a table cannot escape this check merely by being listed
    here.

    :return: None
    """
    considered_but_not_deleted = {
        table
        for table, target in HARD_DELETE_SCOPES.items()
        if target.scope is Scope.NOT_PERSONAL
    }
    phantom = (
        set(HARD_DELETE_SCOPES) - hard_delete_tables() - considered_but_not_deleted
    )

    assert phantom == set(), (
        f"these tables have a deletion scoping decision but are no longer "
        f"HARD_DELETE: {sorted(phantom)}. Deleting a row the manifest says "
        "to retain is the BR1.2 defect by another route."
    )


def test_every_scoping_decision_states_why() -> None:
    """A note short enough to be a placeholder is a decision nobody made.

    :return: None
    """
    thin = [
        table
        for table, target in HARD_DELETE_SCOPES.items()
        if len(target.note.strip()) < 30
    ]
    assert thin == []


def test_the_column_scopes_name_a_column_and_the_others_do_not() -> None:
    """A scope and its column must agree, or the delete is malformed.

    :return: None
    """
    for table, target in HARD_DELETE_SCOPES.items():
        needs_column = target.scope in (
            Scope.ACCOUNT_COLUMN,
            Scope.PHONE_COLUMN,
        )
        assert (target.column is not None) is needs_column, table


# ---------------------------------------------------------------------------
# Absence, enumerated. Asserted for BOTH roles.
# ---------------------------------------------------------------------------


def _rows_for_account(
    session: Session, account_id: uuid.UUID, phone: str
) -> dict[str, int]:
    """Count the rows each hard-delete table holds for one person.

    Enumerated from :data:`HARD_DELETE_SCOPES` rather than listed, on
    BR1.3's reasoning.

    :param session: The session to read through
    :param account_id: The account being counted
    :param phone: Its number, for the phone-scoped tables
    :return: Table name to row count
    """
    counts: dict[str, int] = {}
    for table, target in sorted(HARD_DELETE_SCOPES.items()):
        if target.column is None:
            continue
        value = account_id if target.scope is Scope.ACCOUNT_COLUMN else phone
        counts[table] = int(
            session.execute(
                sa.text(
                    f"SELECT count(*) FROM {table} "  # noqa: S608
                    f"WHERE {target.column} = :value"
                ),
                {"value": value},
            ).scalar_one()
        )
    return counts


def _retained_counts(session: Session) -> dict[str, int]:
    """Count every row in every ``RETAIN_WITH_BASIS`` table.

    A total rather than a per-account count, deliberately: the point of
    retention is that the rows survive an account's departure, and after
    the deletion there is no account to scope the count by.

    :param session: The session to read through
    :return: Table name to row count
    """
    return {
        table: int(
            session.execute(
                sa.text(f"SELECT count(*) FROM {table}")  # noqa: S608
            ).scalar_one()
        )
        for table, governance in sorted(DISPOSITIONS.items())
        if governance.disposition is Disposition.RETAIN_WITH_BASIS
    }


@pytest.mark.parametrize("role", ["student", "guardian"])
def test_deletion_removes_every_hard_delete_row_for_the_account(
    owner_session: Session, populated_seat: PopulatedSeat, role: str
) -> None:
    """Every account-scoped and phone-scoped row is gone afterwards.

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :param role: Which link holder is deleting
    :return: None
    """
    account_id = (
        populated_seat.student_account_id
        if role == "student"
        else populated_seat.guardian_account_id
    )
    phone = (
        populated_seat.student_phone
        if role == "student"
        else populated_seat.guardian_phone
    )

    before = _rows_for_account(owner_session, account_id, phone)
    assert before["profile"] == 1, (
        "the fixture created no profile, so the absence assertion below is vacuous"
    )
    assert before["refresh_token"] == 1

    delete_account(owner_session, phone)
    owner_session.expire_all()

    after = _rows_for_account(owner_session, account_id, phone)
    remaining = {table: count for table, count in after.items() if count}
    assert remaining == {}, (
        f"these tables still hold rows for the deleted account: "
        f"{remaining}. The published policy says the phone number and "
        "everything the person wrote are removed permanently."
    )


@pytest.mark.parametrize("role", ["student", "guardian"])
def test_deletion_leaves_every_retained_row_standing(
    owner_session: Session, populated_seat: PopulatedSeat, role: str
) -> None:
    """Attendance, marks, the ledger and the seat itself all survive.

    **The student case is the one that was broken.** Before ``0007``
    this deleted the enrollment row and six tables cascading from it --
    the teacher's entire record of that seat [BR1.2, AC1.6.2].

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :param role: Which link holder is deleting
    :return: None
    """
    phone = (
        populated_seat.student_phone
        if role == "student"
        else populated_seat.guardian_phone
    )

    before = _retained_counts(owner_session)
    populated = {table for table, count in before.items() if count}
    assert {
        "enrollment",
        "attendance",
        "mark",
        "ledger_entry",
        "payment_claim",
        "fee_cycle",
        "queued_submission",
    } <= populated, (
        f"the fixture populated only {sorted(populated)}, so the retention "
        "assertions below are vacuously true over empty tables"
    )

    delete_account(owner_session, phone)
    owner_session.expire_all()

    after = _retained_counts(owner_session)
    assert after == before, (
        "a RETAIN_WITH_BASIS table lost rows to an account deletion. "
        f"Before: {before}. After: {after}."
    )


def test_a_students_deletion_clears_the_link_and_keeps_the_seat(
    owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """The constraint does the clearing, not the deletion code [BR1.2].

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    delete_account(owner_session, populated_seat.student_phone)
    owner_session.expire_all()

    row = owner_session.execute(
        sa.text(
            "SELECT student_account_id, guardian_account_id, display_name "
            "FROM enrollment WHERE id = :id"
        ),
        {"id": populated_seat.enrollment_id},
    ).one()

    assert row.student_account_id is None
    assert row.guardian_account_id == populated_seat.guardian_account_id
    assert row.display_name == "Teacher-typed name", (
        "the teacher-typed name is the teacher's own record and survives "
        "the student's erasure [ADR-012]"
    )


def test_a_students_deletion_keeps_their_payment_claim(
    owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """The second contradicting reference, asserted directly.

    Before ``0007`` a student deleting their account also deleted the
    record of a payment they submitted, with its channel and transaction
    reference -- on a table the manifest marks ``RETAIN_WITH_BASIS``.

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    delete_account(owner_session, populated_seat.student_phone)
    owner_session.expire_all()

    row = owner_session.execute(
        sa.text(
            "SELECT submitted_by_account_id, transaction_id, channel "
            "FROM payment_claim WHERE enrollment_id = :id"
        ),
        {"id": populated_seat.enrollment_id},
    ).one()

    assert row.submitted_by_account_id is None
    assert row.transaction_id == "TRX123456"
    assert row.channel == "bkash"


def test_deletion_does_not_clear_a_decline(
    owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """A decline is the record of someone saying "not mine" [BR1.5].

    Resetting it on deletion re-exposes a stranger's child to the next
    person who signs up with that number, which is the exposure the
    acceptance model exists to close.

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    owner_session.execute(
        sa.text("UPDATE enrollment SET student_decision = 'declined' WHERE id = :id"),
        {"id": populated_seat.enrollment_id},
    )
    owner_session.commit()

    delete_account(owner_session, populated_seat.student_phone)
    owner_session.expire_all()

    decision = owner_session.execute(
        sa.text("SELECT student_decision FROM enrollment WHERE id = :id"),
        {"id": populated_seat.enrollment_id},
    ).scalar_one()
    assert decision == "declined"


def test_a_second_deletion_succeeds_and_changes_nothing(
    owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """A user who clicks twice sees success, not an error [BR1.4].

    On a deletion screen an error reads as "it did not work", and the
    action already succeeded.

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    first = delete_account(owner_session, populated_seat.student_phone)
    assert first.existed is True

    retained_after_first = _retained_counts(owner_session)

    second = delete_account(owner_session, populated_seat.student_phone)
    assert second.existed is False
    assert sum(second.rows_deleted.values()) == 0

    assert _retained_counts(owner_session) == retained_after_first


def test_deleting_an_unknown_number_is_a_success_that_writes_nothing(
    owner_session: Session,
) -> None:
    """No lookup-then-delete guard, which would be a race [BR1.4].

    :param owner_session: A session able to read everything
    :return: None
    """
    result = delete_account(owner_session, "+8801700000000")

    assert result.existed is False
    assert sum(result.rows_deleted.values()) == 0


def test_the_phone_scoped_tables_are_cleared(
    owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """``otp_request`` is keyed on the NUMBER and no constraint reaches it.

    It holds a phone number beside a code hash, which is precisely what
    a deletion must remove -- and because nothing cascades to it, an
    implementation that deleted only the account row would leave it
    behind while every account-scoped assertion passed.

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    owner_session.execute(
        sa.text(
            "INSERT INTO otp_request "
            "(id, phone, otp_hash, purpose, issued_at, expires_at) "
            "VALUES (:id, :phone, :hash, 'otp', now(), now())"
        ),
        {
            "id": uuid.uuid4(),
            "phone": populated_seat.student_phone,
            "hash": "x" * 64,
        },
    )
    owner_session.commit()

    delete_account(owner_session, populated_seat.student_phone)

    remaining = owner_session.execute(
        sa.text("SELECT count(*) FROM otp_request WHERE phone = :phone"),
        {"phone": populated_seat.student_phone},
    ).scalar_one()
    assert remaining == 0


def test_the_counters_are_not_cleared_by_a_deletion(
    owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """Clearing a number's ceilings on request would be the attack.

    ``rate_limit_counter`` keys two of its seven scopes on a phone
    number, and is still ``NOT_PERSONAL`` for deletion: if a deletion
    cleared them, the public deletion route would be the way to reset
    the abuse controls protecting a number. They expire on their own
    48-hour window instead.

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    owner_session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter "
            "(id, scope_kind, scope_value, window_start, count) "
            "VALUES (gen_random_uuid(), 'number_day', :value, now(), 3)"
        ),
        {"value": populated_seat.student_phone},
    )
    owner_session.commit()

    delete_account(owner_session, populated_seat.student_phone)

    surviving = owner_session.execute(
        sa.text("SELECT count FROM rate_limit_counter WHERE scope_value = :value"),
        {"value": populated_seat.student_phone},
    ).scalar_one()
    assert surviving == 3


# ---------------------------------------------------------------------------
# A TEACHER'S DELETION. [BR1.6, as amended 2026-10-28]
#
# BR1.6 refused while a teacher owned a batch, and nothing in the app
# could close or hand over a batch, so a teacher could never delete. The
# amended rule follows the O5 board: the teacher's login and profile go,
# and every batch stays with its students as read-only history.
# ---------------------------------------------------------------------------


def _batch_row(session: Session, batch_id: uuid.UUID) -> sa.Row[tuple[object, ...]]:
    """Read what a deletion changes on a batch.

    :param session: A session able to read everything
    :param batch_id: The batch
    :return: Its owner's account, active flag, teacher name and number
    """
    return session.execute(
        sa.text(
            "SELECT o.account_id, b.active, b.teacher_display_name, "
            "b.collection_number "
            "FROM batch b JOIN owner o ON o.id = b.owner_id WHERE b.id = :id"
        ),
        {"id": batch_id},
    ).one()


def test_a_teacher_owning_a_batch_can_delete(
    owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """The account goes; the batch and its owner row stay, unlinked.

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    result = delete_account(owner_session, populated_seat.teacher_phone)

    gone = owner_session.execute(
        sa.text("SELECT count(*) FROM account WHERE id = :id"),
        {"id": populated_seat.teacher_account_id},
    ).scalar_one()
    assert result.existed is True
    assert gone == 0
    assert _batch_row(owner_session, populated_seat.batch_id)[0] is None


def test_a_teachers_deletion_keeps_every_students_records(
    owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """Every retained row survives, the teacher's chain included.

    **The assertion the old refusal existed for.** Seven retained tables
    hang off ``owner -> batch``; a cascade from the account would take
    them all, so the count is taken across every retained table.

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    before = _retained_counts(owner_session)

    delete_account(owner_session, populated_seat.teacher_phone)

    assert _retained_counts(owner_session) == before


def test_a_teachers_batch_stops_and_forgets_the_teacher(
    owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """Inactive, so no new fee falls due; no name, no payment number.

    Charges already made stay owed on the records. A new one would be a
    debt nobody can collect, and a payment number left in place would
    send a student's money to an account that no longer exists.

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    owner_session.execute(
        sa.text(
            "UPDATE batch SET teacher_display_name = 'Sir', "
            "collection_number = '01700000000' WHERE id = :id"
        ),
        {"id": populated_seat.batch_id},
    )
    owner_session.commit()

    delete_account(owner_session, populated_seat.teacher_phone)

    _, active, name, number = _batch_row(owner_session, populated_seat.batch_id)
    assert (active, name, number) == (False, None, None)


def test_a_students_deletion_leaves_the_teachers_batch_alone(
    owner_session: Session, populated_seat: PopulatedSeat
) -> None:
    """Only a teacher's own deletion retires their batches.

    :param owner_session: A session able to read everything
    :param populated_seat: The fixture
    :return: None
    """
    delete_account(owner_session, populated_seat.student_phone)

    account, active, _, _ = _batch_row(owner_session, populated_seat.batch_id)
    assert (account, active) == (populated_seat.teacher_account_id, True)


def test_not_personal_scoping_and_not_personal_disposition_agree() -> None:
    """The two manifests cannot label one table two ways [NFR14.101].

    **The cross-check that was missing, and its absence shipped a false
    statement to a regulator.** ``rate_limit_counter`` and
    ``job_heartbeat`` were declared ``HARD_DELETE`` in
    ``dispositions.py`` while :data:`HARD_DELETE_SCOPES` marked them
    ``Scope.NOT_PERSONAL`` and :func:`delete_account` deliberately never
    touched them. The completeness gates above compare only MEMBERSHIP
    -- every hard-delete table has *an* entry, and no entry names a
    non-hard-delete table -- so both passed over a table carrying a
    disposition its own scoping contradicted. The generated privacy
    policy reads the disposition, and published "Counters that limit
    sign-in attempts" under *Deleted outright when you delete your
    account* for rows the code never deletes.

    The digest gate could not catch it either: a digest proves the
    document matches the manifest, and here the manifest itself was
    wrong.

    Asserted in BOTH directions, because either one alone fails open. A
    table that stops being ``NOT_PERSONAL`` in one file and not the
    other is the same defect whichever file moves first.

    :return: None
    """
    scoped_not_personal = {
        table
        for table, target in HARD_DELETE_SCOPES.items()
        if target.scope is Scope.NOT_PERSONAL
    }
    declared_not_personal = {
        table
        for table, governance in DISPOSITIONS.items()
        if governance.disposition is Disposition.NOT_PERSONAL
    }

    assert scoped_not_personal - declared_not_personal == set(), (
        f"these tables are scoped NOT_PERSONAL but carry another "
        f"disposition: {sorted(scoped_not_personal - declared_not_personal)}. "
        "Deletion never touches them, so any other disposition is a "
        "false statement on the generated privacy policy."
    )
    assert declared_not_personal - scoped_not_personal == set(), (
        f"these tables are declared NOT_PERSONAL but their deletion "
        f"scoping says otherwise: "
        f"{sorted(declared_not_personal - scoped_not_personal)}. The "
        "policy would claim nothing happens to rows the deletion code "
        "removes."
    )
