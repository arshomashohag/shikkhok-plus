"""A join request is kept 90 days from sending, through the existing purge.

Call 11: a lead nobody acted on in three months is not worth keeping a
child's name for. Whether it was answered does not matter: an open request
and a closed one age out alike, measured from ``created_at``, and nothing
inside the window is touched.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.governance.commands import WINDOWS, purge_expired
from app.governance.deletion import HARD_DELETE_SCOPES, Scope
from app.governance.dispositions import (
    DISPOSITIONS,
    RETENTION,
    Disposition,
    RetentionClass,
)
from tests.batches.conftest import _account, make_teacher

#: The moment the purge runs at in these tests.
NOW = dt.datetime(2027, 3, 1, 12, 0, tzinfo=dt.UTC)


def test_enquiry_disposition_and_retention() -> None:
    """Hard-deleted with its guardian, and kept 90 days at most.

    :return: None
    """
    governance = DISPOSITIONS["listing_enquiry"]

    assert governance.disposition is Disposition.HARD_DELETE
    assert RETENTION["listing_enquiry"] is RetentionClass.DAYS_90
    assert RetentionClass.DAYS_90.value == "90_days"
    assert WINDOWS["listing_enquiry"].keep_for == dt.timedelta(days=90)
    assert WINDOWS["listing_enquiry"].age_column == "created_at"
    assert "never shown to platform administrators" in governance.basis
    assert "90 days after it was sent" in governance.basis
    assert HARD_DELETE_SCOPES["listing_enquiry"].scope is Scope.ACCOUNT_COLUMN
    assert HARD_DELETE_SCOPES["listing_enquiry"].column == "enquirer_account_id"


def _plant(
    session: Session,
    owner_id: uuid.UUID,
    *,
    days_old: int,
    closed: bool,
) -> uuid.UUID:
    """Insert one request sent ``days_old`` days before :data:`NOW`.

    :param session: An arranging session
    :param owner_id: The owner asked
    :param days_old: Its age at the purge
    :param closed: Whether the owner answered it
    :return: The request's id
    """
    sent = NOW - dt.timedelta(days=days_old)
    enquiry_id: uuid.UUID = session.execute(
        sa.text(
            "INSERT INTO listing_enquiry (owner_id, enquirer_account_id, "
            "student_name, class_level, share_contact, status, outcome, "
            "created_at, closed_at) VALUES (:o, :a, 'Rafi', 'class_9', false, "
            "CAST(:st AS hub_enquiry_status), "
            "CAST(:out AS hub_enquiry_outcome), :sent, :closed) RETURNING id"
        ),
        {
            "o": owner_id,
            "a": _account(session),
            "st": "closed" if closed else "open",
            "out": "not_now" if closed else None,
            "sent": sent,
            "closed": sent + dt.timedelta(hours=1) if closed else None,
        },
    ).scalar_one()
    return enquiry_id


@pytest.mark.parametrize("closed", [False, True], ids=["open", "closed"])
def test_enquiries_purged_after_90_days(owner_session: Session, closed: bool) -> None:
    """The 91-day request goes and the 89-day one stays, answered or not.

    :param owner_session: An arranging and purging session
    :param closed: Whether the planted requests were answered
    :return: None
    """
    owner_id = make_teacher(owner_session).owner_id
    young = _plant(owner_session, owner_id, days_old=89, closed=closed)
    old = _plant(owner_session, owner_id, days_old=91, closed=closed)
    owner_session.commit()

    result = purge_expired(owner_session, now=NOW)

    left = set(
        owner_session.execute(sa.text("SELECT id FROM listing_enquiry")).scalars()
    )
    assert left == {young}
    assert old not in left
    assert result.deleted["listing_enquiry"] == 1
