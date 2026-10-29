"""The adversarial lens test. Written to FAIL against today's code.

**This is the regression guard for the defect the whole unit exists to
prevent** [NFR23.2]. Before D1, *naming* an account on a link was the
grant, so a teacher who mistyped one digit of a guardian's number handed
a stranger a guardian lens over a child's attendance and marks. The two
granting queries read ``student_account_id`` and ``guardian_account_id``
and nothing else.

These were written before ``student_decision`` and ``guardian_decision``
existed, because the affirmed predicate holds on both halves: the correct
output is knowable from BR1.1 and BR1.2 without having written the code,
and a wrong answer is an authorization error [team: Testing Posture].

**Both queries are asserted, in one file, deliberately** [BR1.2]. The
grant lives in ``app.authz.resolve`` and the picker's counts live in
``app.authz.summary`` -- separate statements in separate modules that
read the same columns and neither reads the other. Fixing one alone is a
silent half-fix: either the lenses are right and the picker counts seats
that resolve to nothing, or the picker is right and the lenses are not.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, StudentLens
from app.authz.resolve import available_lenses
from app.authz.summary import lens_summary
from app.db.models import Account, Enrollment


@pytest.fixture
def account(owner_session: Session) -> uuid.UUID:
    """Create one account holding nothing at all.

    :param owner_session: A session able to arrange fixture data
    :return: The new account's id
    """
    record = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(record)
    owner_session.commit()
    return record.id


def _seat(
    session: Session,
    *,
    student_account_id: uuid.UUID | None = None,
    guardian_account_id: uuid.UUID | None = None,
    student_decision: str = "pending",
    guardian_decision: str = "pending",
) -> uuid.UUID:
    """Create one seat with both links and both decisions stated.

    **Every decision is stated explicitly**, never defaulted, which is
    the same obligation ADR-013 puts on the schema: the column carries
    no server default, so an arranging helper that omitted one would be
    arranging a state the application cannot produce.

    :param session: An arranging session
    :param student_account_id: The student link, or None
    :param guardian_account_id: The guardian link, or None
    :param student_decision: The student link's decision
    :param guardian_decision: The guardian link's decision
    :return: The new enrollment's id
    """
    record = Enrollment(
        batch_id=uuid.uuid4(),
        student_account_id=student_account_id,
        guardian_account_id=guardian_account_id,
        student_decision=student_decision,
        guardian_decision=guardian_decision,
        display_name="Teacher Typed Name",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


# ---------------------------------------------------------------------------
# THE ONE THAT CARRIES THE RULE. [BR1.1, BR1.2, NFR23.2]
# ---------------------------------------------------------------------------


def test_links_that_only_name_an_account_grant_no_role_lens(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    """A stranger on a mistyped number reaches nothing [BR1.1].

    The seat names this account on BOTH links and neither has accepted.
    Under the superseded model this granted a student lens AND a
    guardian lens over a child's records.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param account: The account named on the links
    :return: None
    """
    _seat(
        owner_session,
        student_account_id=account,
        guardian_account_id=account,
        student_decision="pending",
        guardian_decision="pending",
    )

    lenses = available_lenses(restricted_session, account)

    assert not any(isinstance(lens, StudentLens) for lens in lenses)
    assert not any(isinstance(lens, GuardianLens) for lens in lenses)


def test_declined_links_grant_no_role_lens(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    """A refusal withholds the lens as firmly as never answering [BR1.1].

    ``declined`` is a separate branch from ``pending`` and is tested
    separately, because the invitation grant INCLUDES ``declined``
    [BR1.3] -- so an implementation that collapsed the two states into
    "not accepted" for one query and "pending only" for the other would
    pass a single combined test.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param account: The account named on the links
    :return: None
    """
    _seat(
        owner_session,
        student_account_id=account,
        guardian_account_id=account,
        student_decision="declined",
        guardian_decision="declined",
    )

    lenses = available_lenses(restricted_session, account)

    assert not any(isinstance(lens, StudentLens) for lens in lenses)
    assert not any(isinstance(lens, GuardianLens) for lens in lenses)


def test_the_summary_counts_agree_with_the_grant(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    """The picker offers no lens the resolver would not grant [BR1.2].

    A SEPARATE statement in a separate module. This assertion is what
    makes fixing ``_LENS_QUERY`` alone visible as the half-fix it is.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param account: The account named on the links
    :return: None
    """
    _seat(
        owner_session,
        student_account_id=account,
        guardian_account_id=account,
        student_decision="pending",
        guardian_decision="declined",
    )

    summary = lens_summary(restricted_session, account)

    assert summary.student_enrollments == 0
    assert summary.guardian_children == 0
    assert summary.is_student is False
    assert summary.is_guardian is False


def test_accepting_one_link_grants_exactly_that_lens(
    restricted_session: Session, owner_session: Session, account: uuid.UUID
) -> None:
    """Acceptance is what grants, and it grants per link [BR1.1, BR5.2].

    The positive half, and it is not redundant with the three negatives:
    a predicate that refused everything would satisfy them all. The
    guardian link on the same row stays ``pending``, so this also
    asserts the grant is per column rather than per row.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :param account: The account named on the links
    :return: None
    """
    _seat(
        owner_session,
        student_account_id=account,
        guardian_account_id=account,
        student_decision="accepted",
        guardian_decision="pending",
    )

    lenses = available_lenses(restricted_session, account)
    summary = lens_summary(restricted_session, account)

    assert any(isinstance(lens, StudentLens) for lens in lenses)
    assert not any(isinstance(lens, GuardianLens) for lens in lenses)
    assert summary.student_enrollments == 1
    assert summary.guardian_children == 0
