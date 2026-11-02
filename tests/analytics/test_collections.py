"""Collections over months: charged, collected, and the bars drawn from them.

The expected figures follow from the ledger rows seeded in each test,
written down before the module existed. **Cash in is ``receipt`` plus
``credit_grant`` and never ``credit_apply``**, and a corrected decision
must move neither "charged" nor "collected" away from the truth.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.analytics.collections import clamp_months, collections
from app.authz.lenses import TeacherLens
from app.errors import AuthorizationError
from app.fees.claims import submit_claim
from app.fees.ledger_writer import append_entry, apply_available_credit
from app.fees.verification import reject_claim, verify_claim
from app.money import Money
from tests.analytics.conftest import add_batch, lens_for, seat_with_ledger
from tests.batches.conftest import TeacherFixture, _account

TODAY = dt.date(2026, 10, 17)


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build a teacher's lens.

    :param teacher: The teacher
    :return: Their lens
    """
    return lens_for(teacher)


def test_collections_sum_receipts_and_credit_not_credit_apply(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """October collected is 1500 and November's spent credit adds nothing.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        entries=[
            ("charge", "2026-10", "1000.00"),
            ("receipt", "2026-10", "1000.00"),
            ("credit_grant", "2026-10", "500.00"),
            ("charge", "2026-11", "500.00"),
            ("credit_apply", "2026-11", "500.00"),
        ],
    )

    report = collections(
        restricted_session,
        lens=_lens(teacher),
        batch_ids=None,
        months=2,
        today=dt.date(2026, 11, 3),
    )

    october, november = report.months
    assert (october.period, november.period) == ("2026-10", "2026-11")
    assert october.collected == Money("1500.00")
    assert october.charged == Money("1000.00")
    assert november.collected == Money.ZERO
    assert november.charged == Money("500.00")


def test_bars_scale_to_the_largest_charge(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Charged 20000 and 22000 draw bars of 91 and 100.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        entries=[
            ("charge", "2026-09", "20000.00"),
            ("receipt", "2026-09", "10000.00"),
            ("charge", "2026-10", "22000.00"),
            ("receipt", "2026-10", "22000.00"),
        ],
    )

    report = collections(
        restricted_session, lens=_lens(teacher), batch_ids=None, months=2, today=TODAY
    )

    september, october = report.months
    assert (september.charged_bar, october.charged_bar) == (91, 100)
    assert (september.collected_bar, october.collected_bar) == (45, 100)


def test_bars_are_zero_when_nothing_was_charged(
    restricted_session: Session, teacher: TeacherFixture
) -> None:
    """An empty report draws empty bars and owes nothing.

    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    report = collections(
        restricted_session, lens=_lens(teacher), batch_ids=None, months=3, today=TODAY
    )

    assert [m.period for m in report.months] == ["2026-08", "2026-09", "2026-10"]
    assert all(m.charged_bar == 0 and m.collected_bar == 0 for m in report.months)
    assert report.outstanding == Money.ZERO
    assert report.owing_students == 0


def test_collections_filter_by_batches(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Naming one batch leaves the other batch's money out.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    second = add_batch(owner_session, teacher.owner_id, "Chemistry")
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="A",
        entries=[("charge", "2026-10", "1000.00"), ("receipt", "2026-10", "400.00")],
    )
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=second,
        display_name="B",
        entries=[("charge", "2026-10", "700.00")],
    )

    both = collections(
        restricted_session, lens=_lens(teacher), batch_ids=None, months=1, today=TODAY
    )
    only_second = collections(
        restricted_session,
        lens=_lens(teacher),
        batch_ids=[second],
        months=1,
        today=TODAY,
    )

    assert both.months[0].charged == Money("1700.00")
    assert both.outstanding == Money("1300.00")
    assert both.owing_students == 2
    assert only_second.months[0].charged == Money("700.00")
    assert only_second.months[0].collected == Money.ZERO
    assert only_second.outstanding == Money("700.00")
    assert only_second.owing_students == 1


def test_current_month_is_in_progress(
    restricted_session: Session, teacher: TeacherFixture
) -> None:
    """Only the month containing today is flagged.

    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    report = collections(
        restricted_session, lens=_lens(teacher), batch_ids=None, months=3, today=TODAY
    )

    assert [m.in_progress for m in report.months] == [False, False, True]


def test_months_are_clamped_between_one_and_twenty_four() -> None:
    """Out-of-range windows are pulled into 1 to 24.

    :return: None
    """
    assert clamp_months(0) == 1
    assert clamp_months(-5) == 1
    assert clamp_months(6) == 6
    assert clamp_months(99) == 24


def test_other_teachers_batch_id_is_refused(
    restricted_session: Session,
    teacher: TeacherFixture,
    other_teacher: TeacherFixture,
) -> None:
    """A batch the lens does not own is refused, owned ones alongside or not.

    :param restricted_session: The application-role session
    :param teacher: The teacher
    :param other_teacher: Someone else
    :return: None
    """
    with pytest.raises(AuthorizationError):
        collections(
            restricted_session,
            lens=_lens(teacher),
            batch_ids=[teacher.batch_id, other_teacher.batch_id],
            months=1,
            today=TODAY,
        )
    with pytest.raises(AuthorizationError):
        collections(
            restricted_session,
            lens=_lens(teacher),
            batch_ids=[uuid.uuid4()],
            months=1,
            today=TODAY,
        )


def test_the_route_refuses_another_teachers_batch(
    client: TestClient,
    owner_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """The route answers 403 for a batch that is not the caller's.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    from tests.batches.conftest import make_teacher

    stranger = make_teacher(owner_session, name="Other")
    response = client.get(
        "/v1/analytics/collections",
        params=[("batch_id", str(stranger.batch_id))],
        headers={"Authorization": f"Bearer {teacher_token}"},
    )

    assert response.status_code == 403


def test_the_route_returns_strings_for_money_and_ints_for_bars(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """Money is a quoted string on the wire and bars are integers.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The application-role session
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    period = dt.datetime.now(tz=dt.UTC).date().strftime("%Y-%m")
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="Rahim",
        entries=[("charge", period, "900.00"), ("receipt", period, "300.00")],
    )

    response = client.get(
        "/v1/analytics/collections",
        params=[("batch_id", str(signed_in_teacher.batch_id)), ("months", "100")],
        headers={"Authorization": f"Bearer {teacher_token}"},
    )

    body = response.json()
    assert response.status_code == 200
    assert len(body["months"]) == 24
    latest = body["months"][-1]
    assert latest["charged"] == "900.00"
    assert latest["collected"] == "300.00"
    assert latest["in_progress"] is True
    assert latest["charged_bar"] == 100
    assert latest["collected_bar"] == 33
    assert body["outstanding"] == "600.00"
    assert body["owing_students"] == 1


def test_a_corrected_approval_does_not_inflate_charged_or_collected(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Approve 1000, then correct it to a rejection: collected is 0, charged 1000.

    The reversal writes a compensating ``charge``. Counted as a charge
    it would read 2000, and the superseded receipt counted as cash it
    would read 1000.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :return: None
    """
    student = _account(owner_session)
    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        entries=[("charge", "2026-10", "1000.00")],
    )
    claim = submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=student,
        claimed_amount=Money("1000.00"),
        channel="bKash",
        today=TODAY,
    )
    verify_claim(
        owner_session,
        claim_id=claim.id,
        approved_amount=Money("1000.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )
    approved = collections(
        restricted_session, lens=_lens(teacher), batch_ids=None, months=1, today=TODAY
    )

    reject_claim(
        owner_session,
        claim_id=claim.id,
        verified_by_account_id=teacher.account_id,
        correcting=True,
        reason="no such transfer",
    )
    restricted_session.expire_all()
    corrected = collections(
        restricted_session, lens=_lens(teacher), batch_ids=None, months=1, today=TODAY
    )

    assert approved.months[0].collected == Money("1000.00")
    assert approved.months[0].charged == Money("1000.00")
    assert corrected.months[0].collected == Money.ZERO
    assert corrected.months[0].charged == Money("1000.00")
    assert corrected.outstanding == Money("1000.00")


@pytest.mark.parametrize(
    ("november_fee", "owed"),
    [("1000.00", "2000.00"), ("300.00", "1300.00")],
    ids=["credit-spent", "credit-partly-spent"],
)
def test_a_corrected_over_payment_does_not_inflate_charged_or_collected(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    november_fee: str,
    owed: str,
) -> None:
    """Approve 1500 for 1000, spend the credit, then reject: nothing collected.

    Computed: October was billed 1000 and November ``november_fee``;
    after the rejection nothing came in, so both months collect zero
    and the whole of both bills is outstanding.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The application-role session
    :param teacher: The teacher
    :param november_fee: November's charge, against which credit is spent
    :param owed: What is owed after the correction
    :return: None
    """
    student = _account(owner_session)
    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        entries=[("charge", "2026-10", "1000.00")],
    )
    claim = submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=student,
        claimed_amount=Money("1500.00"),
        channel="bKash",
        today=TODAY,
    )
    verify_claim(
        owner_session,
        claim_id=claim.id,
        approved_amount=Money("1500.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2026-11",
        kind="charge",
        amount=Money(november_fee),
    )
    apply_available_credit(restricted_session, enrollment_id=seat, period="2026-11")
    restricted_session.commit()

    reject_claim(
        owner_session,
        claim_id=claim.id,
        verified_by_account_id=teacher.account_id,
        correcting=True,
        reason="no such transfer",
    )
    restricted_session.expire_all()
    report = collections(
        restricted_session,
        lens=_lens(teacher),
        batch_ids=None,
        months=2,
        today=dt.date(2026, 11, 3),
    )

    october, november = report.months
    assert (october.charged, october.collected) == (Money("1000.00"), Money.ZERO)
    assert (november.charged, november.collected) == (Money(november_fee), Money.ZERO)
    assert report.outstanding == Money(owed)


def test_the_batch_route_wraps_totals_counts_and_seats(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """The route answers an object with money as strings and a period filter.

    :param client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="Rahim",
        entries=[("charge", "2026-10", "1000.00")],
    )
    url = f"/v1/batches/{signed_in_teacher.batch_id}/fees"
    headers = {"Authorization": f"Bearer {teacher_token}"}

    response = client.get(url, params={"period": "2026-10"}, headers=headers)
    bad = client.get(url, params={"period": "2026-13"}, headers=headers)

    body = response.json()
    assert response.status_code == 200, body
    assert body["period"] == "2026-10"
    assert body["charged"] == "1000.00"
    assert body["collected"] == "0.00"
    assert body["counts"] == {"paid": 0, "checking": 0, "owed": 1}
    assert body["seats"][0]["state"] == "unpaid"
    assert body["seats"][0]["outstanding"] == "1000.00"
    assert bad.status_code == 422
