"""Inbox core: who receives an item, and who may read or mark it.

**Written before the implementation.** Recipient choice and per-item
ownership decide whose inbox a message lands in and whose it can be
changed from, so a wrong answer is an authorization error: only
ACCEPTED links receive, a guardian of two children receives for both,
and one account can neither open nor mark another's item.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.db.models import Enrollment, Notification
from app.errors import AuthorizationError
from app.notifications.inbox import (
    NOTICE,
    deliver,
    inbox,
    mark_one_read,
    mark_unread_for_source,
    owned_item,
    remove_for_source,
)
from app.notifications.recipients import (
    Recipient,
    family_recipients,
    seat_recipients,
    teacher_recipient,
)
from tests.batches.conftest import enroll, make_teacher

TODAY = dt.date(2026, 10, 20)
NOW = dt.datetime(2026, 10, 20, 9, 0, tzinfo=dt.UTC)


def test_family_recipients_are_accepted_links_only(
    owner_session: Session, account_factory: Callable[[], uuid.UUID]
) -> None:
    """A pending guardian does not receive; the accepted student does."""
    teacher = make_teacher(owner_session)
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
        guardian_account_id=account_factory(),
        guardian_decision="pending",
    )

    found = family_recipients(owner_session, batch_id=teacher.batch_id, on=TODAY)

    assert found == [Recipient(account_id=student, enrollment_id=seat, child_name=None)]


def test_guardian_of_two_children_gets_two_recipients(
    owner_session: Session, account_factory: Callable[[], uuid.UUID]
) -> None:
    """One guardian on two seats receives once per child, each named."""
    teacher = make_teacher(owner_session)
    guardian = account_factory()
    for name in ("Rahim", "Karim"):
        enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=name,
            guardian_account_id=guardian,
            guardian_decision="accepted",
        )

    found = family_recipients(owner_session, batch_id=teacher.batch_id, on=TODAY)

    assert {r.account_id for r in found} == {guardian}
    assert sorted(r.child_name or "" for r in found) == ["Karim", "Rahim"]


def test_inactive_seat_is_excluded_after_inactive_from(
    owner_session: Session, account_factory: Callable[[], uuid.UUID]
) -> None:
    """A seat left yesterday is out; one leaving today is still in."""
    teacher = make_teacher(owner_session)
    gone = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Gone",
        student_account_id=account_factory(),
        student_decision="accepted",
    )
    leaving = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Leaving",
        student_account_id=account_factory(),
        student_decision="accepted",
    )
    owner_session.get(Enrollment, gone).inactive_from = TODAY - dt.timedelta(days=1)
    owner_session.get(Enrollment, leaving).inactive_from = TODAY
    owner_session.commit()

    found = family_recipients(owner_session, batch_id=teacher.batch_id, on=TODAY)

    assert [r.enrollment_id for r in found] == [leaving]
    assert [r.enrollment_id for r in seat_recipients(owner_session, enrollment_id=gone)]


def test_one_account_never_sees_or_marks_another_accounts_item(
    owner_session: Session, account_factory: Callable[[], uuid.UUID]
) -> None:
    """A cannot open B's item, nor mark it read; a missing id looks the same."""
    a, b = account_factory(), account_factory()
    deliver(owner_session, account_ids=[b], kind=NOTICE, batch_name="B", now=NOW)
    owner_session.commit()
    b_item = inbox(owner_session, account_id=b).items[0]

    with pytest.raises(AuthorizationError):
        owned_item(owner_session, account_id=a, notification_id=b_item.notification_id)
    with pytest.raises(AuthorizationError):
        owned_item(owner_session, account_id=a, notification_id=uuid.uuid4())
    mark_one_read(owner_session, account_id=a, notification_id=b_item.notification_id)

    assert inbox(owner_session, account_id=b).unread == 1
    own = owned_item(
        owner_session, account_id=b, notification_id=b_item.notification_id
    )
    assert own.notification_id == b_item.notification_id


def test_mark_one_read_marks_only_that_item(
    owner_session: Session, account_factory: Callable[[], uuid.UUID]
) -> None:
    """Marking one item leaves the account's others unread."""
    a = account_factory()
    deliver(owner_session, account_ids=[a], kind=NOTICE, batch_name="X", now=NOW)
    deliver(owner_session, account_ids=[a], kind=NOTICE, batch_name="Y", now=NOW)
    owner_session.commit()
    first = inbox(owner_session, account_id=a).items[0]

    mark_one_read(owner_session, account_id=a, notification_id=first.notification_id)

    assert inbox(owner_session, account_id=a).unread == 1


def test_deliver_stores_source_preview_and_child_name(
    owner_session: Session, account_factory: Callable[[], uuid.UUID]
) -> None:
    """The new fields are stored per recipient and returned by the inbox."""
    a, b = account_factory(), account_factory()
    source = uuid.uuid4()
    deliver(
        owner_session,
        account_ids=[a, b],
        kind=NOTICE,
        batch_name="X",
        now=NOW,
        source_id=source,
        preview="Class moved",
        child_names={b: "Rahim"},
    )
    owner_session.commit()

    item_a = inbox(owner_session, account_id=a).items[0]
    item_b = inbox(owner_session, account_id=b).items[0]

    assert (item_a.source_id, item_a.preview, item_a.child_name) == (
        source,
        "Class moved",
        None,
    )
    assert item_b.child_name == "Rahim"


def test_mark_unread_for_source_resets_read(
    owner_session: Session, account_factory: Callable[[], uuid.UUID]
) -> None:
    """An edited source becomes unread again without changing its date."""
    a = account_factory()
    source = uuid.uuid4()
    deliver(
        owner_session,
        account_ids=[a],
        kind=NOTICE,
        batch_name="X",
        now=NOW,
        source_id=source,
    )
    owner_session.commit()
    item = inbox(owner_session, account_id=a).items[0]
    mark_one_read(owner_session, account_id=a, notification_id=item.notification_id)
    assert inbox(owner_session, account_id=a).unread == 0

    mark_unread_for_source(owner_session, kind=NOTICE, source_id=source)
    owner_session.commit()

    after = inbox(owner_session, account_id=a)
    assert after.unread == 1
    assert after.items[0].created_at == NOW


def test_remove_for_source_deletes_every_recipients_row(
    owner_session: Session, account_factory: Callable[[], uuid.UUID]
) -> None:
    """Deleting a source removes its rows for all, and only its rows."""
    a, b = account_factory(), account_factory()
    source, other = uuid.uuid4(), uuid.uuid4()
    deliver(
        owner_session,
        account_ids=[a, b],
        kind=NOTICE,
        batch_name="X",
        now=NOW,
        source_id=source,
    )
    deliver(
        owner_session,
        account_ids=[a],
        kind=NOTICE,
        batch_name="Y",
        now=NOW,
        source_id=other,
    )
    owner_session.commit()

    remove_for_source(owner_session, kind=NOTICE, source_id=source)
    owner_session.commit()

    assert inbox(owner_session, account_id=b).items == []
    assert [i.source_id for i in inbox(owner_session, account_id=a).items] == [other]
    assert owner_session.query(Notification).filter_by(source_id=source).count() == 0


def test_teacher_recipient_is_batch_owner_account(owner_session: Session) -> None:
    """The batch's owner account is the teacher recipient."""
    teacher = make_teacher(owner_session)

    assert (
        teacher_recipient(owner_session, batch_id=teacher.batch_id)
        == teacher.account_id
    )
    assert teacher_recipient(owner_session, batch_id=uuid.uuid4()) is None
