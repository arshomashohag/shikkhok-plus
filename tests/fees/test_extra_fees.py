"""Exam and other fees, and what a payment is for [0020].

Written before the code, under the team's predicate: every expected
value below is knowable from the fee, the seats and the teacher's
choices alone, and a wrong answer would be a money error. The figures
are computed in each docstring rather than asserted from memory.

The separating property for the design is **isolation**: an extra fee
lives in its own ledger, so nothing about a monthly balance may move
when a fee is raised, paid, partly paid, waived or corrected -- and a
monthly payment may never settle an extra fee. Several tests below
exist only to show that.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import ExtraFee, ExtraFeeCharge, ExtraFeeEntry, LedgerEntryRow
from app.fees.balances import derive_for_enrollment
from app.local_time import bangladesh_today
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer
from tests.fees.conftest import (
    add_method,
    charge_period,
    set_decision,
    set_inactive_from,
)

OCTOBER = "2026-10"
DUE = "2026-11-15"


@dataclass(frozen=True, slots=True)
class Class3:
    """Three seats on one batch, each owing October's monthly fee.

    :ivar guardian: The guardian of Tania and Tanvir
    :ivar tania: Tania's seat
    :ivar tanvir: Tanvir's seat
    :ivar rafi: A third student's seat, with no guardian
    :ivar method: The teacher's bKash method
    """

    guardian: uuid.UUID
    tania: uuid.UUID
    tanvir: uuid.UUID
    rafi: uuid.UUID
    method: uuid.UUID


def _class(
    session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> Class3:
    """Seat three students, each charged 1000.00 for October.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: The class
    """
    guardian = account_factory()
    tania, tanvir = (
        enroll(
            session,
            batch_id=teacher.batch_id,
            display_name=name,
            guardian_account_id=guardian,
            guardian_decision="accepted",
        )
        for name in ("Tania", "Tanvir")
    )
    rafi = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Rafi",
        student_account_id=account_factory(),
        student_decision="accepted",
    )
    for seat in (tania, tanvir, rafi):
        charge_period(session, enrollment_id=seat, period=OCTOBER, amount="1000.00")
    return Class3(
        guardian=guardian,
        tania=tania,
        tanvir=tanvir,
        rafi=rafi,
        method=add_method(session, teacher.owner_id),
    )


def _raise(
    client: TestClient,
    session: Session,
    teacher: TeacherFixture,
    **body: object,
) -> object:
    """Raise a fee as the teacher; a 500.00 exam fee unless told otherwise.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The teacher
    :param body: Fields overriding the default request
    :return: The response
    """
    request: dict[str, object] = {
        "purpose": "exam",
        "label": "Half-yearly exam fee",
        "amount": "500.00",
        "due_on": DUE,
    }
    request.update(body)
    return client.post(
        f"/v1/batches/{teacher.batch_id}/extra-fees",
        json=request,
        headers=bearer(session, teacher.account_id),
    )


def _fee_id(response: object) -> uuid.UUID:
    """Read the fee id from a successful raise.

    :param response: The response
    :return: The fee id
    """
    assert response.status_code == 201, response.text  # type: ignore[attr-defined]
    return uuid.UUID(response.json()["extra_fee_id"])  # type: ignore[attr-defined]


def _seats(
    client: TestClient, session: Session, teacher: TeacherFixture, fee: uuid.UUID
) -> dict[str, dict[str, str]]:
    """Read the fee's per-student rows as the teacher, keyed by name.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The teacher
    :param fee: The fee
    :return: Display name to that student's row
    """
    response = client.get(
        f"/v1/extra-fees/{fee}", headers=bearer(session, teacher.account_id)
    )
    assert response.status_code == 200, response.text
    return {row["display_name"]: row for row in response.json()["students"]}


def _submit(
    client: TestClient,
    session: Session,
    family: Class3,
    amount: str,
    *,
    seats: list[uuid.UUID],
    payer: uuid.UUID | None = None,
    **purpose: object,
) -> object:
    """Report one payment, for whatever purpose the caller names.

    :param client: The test client
    :param session: A session to issue the token through
    :param family: The class
    :param amount: The amount sent
    :param seats: The children covered
    :param payer: Who reports it; the guardian by default
    :param purpose: ``purpose`` and ``extra_fee_id``, or nothing at all
    :return: The response
    """
    body: dict[str, object] = {
        "enrollment_ids": [str(seat) for seat in seats],
        "payment_method_id": str(family.method),
        "amount": amount,
        "paid_on": bangladesh_today().isoformat(),
        "transaction_id": f"TX{uuid.uuid4().hex[:10]}",
    }
    body.update(
        {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in purpose.items()}
    )
    return client.post(
        "/v1/payments",
        json=body,
        headers=bearer(session, payer or family.guardian),
    )


def _submission(response: object) -> uuid.UUID:
    """Read the submission id from a successful report.

    :param response: The response
    :return: The submission id
    """
    assert response.status_code == 201, response.text  # type: ignore[attr-defined]
    return uuid.UUID(response.json()["submission_id"])  # type: ignore[attr-defined]


def _approve(
    client: TestClient,
    session: Session,
    teacher: TeacherFixture,
    submission: uuid.UUID,
    received: str,
    **choices: object,
) -> object:
    """Approve a payment as the teacher.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The teacher
    :param submission: The submission
    :param received: What the teacher received
    :param choices: Disposition, purpose, correcting and the rest
    :return: The response
    """
    body: dict[str, object] = {"received_amount": received}
    body.update(
        {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in choices.items()}
    )
    return client.post(
        f"/v1/payments/{submission}/approval",
        json=body,
        headers=bearer(session, teacher.account_id),
    )


def _code(response: object) -> str:
    """Read the error code from an envelope.

    :param response: The response
    :return: The code
    """
    code: str = response.json()["error"]["code"]  # type: ignore[attr-defined]
    return code


def _monthly(session: Session, seat: uuid.UUID) -> Money:
    """Read what a seat owes on its MONTHLY ledger.

    :param session: A reading session
    :param seat: The seat
    :return: The monthly outstanding
    """
    return derive_for_enrollment(session, seat).total_outstanding


# --- raising -------------------------------------------------------------


def test_raising_charges_every_seat_with_its_own_amount(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """500 by default, Tanvir 300, Rafi waived at 0: 800 charged in all.

    Tania 500 + Tanvir 300 + Rafi 0 = 800.00 charged and owed; Rafi's
    zero charge reads ``waived``, not ``paid``, because nobody paid it.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)

    fee = _fee_id(
        _raise(
            api_client,
            owner_session,
            teacher,
            seat_amounts=[
                {"enrollment_id": str(family.tanvir), "amount": "300.00"},
                {"enrollment_id": str(family.rafi), "amount": "0.00"},
            ],
        )
    )

    rows = _seats(api_client, owner_session, teacher, fee)
    assert {name: (row["owed"], row["status"]) for name, row in rows.items()} == {
        "Tania": ("500.00", "unpaid"),
        "Tanvir": ("300.00", "unpaid"),
        "Rafi": ("0.00", "waived"),
    }
    listing = api_client.get(
        f"/v1/batches/{teacher.batch_id}/extra-fees",
        headers=bearer(owner_session, teacher.account_id),
    ).json()["fees"]
    assert [(f["label"], f["charged_total"], f["owed_total"]) for f in listing] == [
        ("Half-yearly exam fee", "800.00", "800.00")
    ]


def test_raising_touches_no_monthly_balance(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Every seat still owes exactly October's 1000.00 on its monthly ledger.

    The isolation the separate table exists for: no row reaches
    ``ledger_entry``, so no monthly reader can see the fee.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    before = restricted_session.scalar(sa.select(sa.func.count(LedgerEntryRow.id)))

    _fee_id(_raise(api_client, owner_session, teacher))

    restricted_session.expire_all()
    after = restricted_session.scalar(sa.select(sa.func.count(LedgerEntryRow.id)))
    assert after == before
    for seat in (family.tania, family.tanvir, family.rafi):
        assert _monthly(restricted_session, seat) == Money("1000.00")


def test_a_declined_or_departed_student_is_not_charged(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The monthly rule's seats: a declined student link and a leaver are skipped.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    set_decision(owner_session, enrollment_id=family.rafi, student="declined")
    set_inactive_from(
        owner_session,
        enrollment_id=family.tanvir,
        when=bangladesh_today() - dt.timedelta(days=1),
    )

    fee = _fee_id(_raise(api_client, owner_session, teacher))

    assert set(_seats(api_client, owner_session, teacher, fee)) == {"Tania"}


def test_excluded_students_get_no_charge(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Rafi left out by the teacher: two charges, 1000.00 in all.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)

    fee = _fee_id(
        _raise(
            api_client,
            owner_session,
            teacher,
            excluded_enrollment_ids=[str(family.rafi)],
        )
    )

    assert set(_seats(api_client, owner_session, teacher, fee)) == {"Tania", "Tanvir"}


def test_a_resend_of_a_raise_records_one_fee(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The same retry key twice answers with the same fee and charges once.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    _class(owner_session, teacher, account_factory)
    key = str(uuid.uuid4())

    first = _fee_id(_raise(api_client, owner_session, teacher, client_mutation_id=key))
    second = _fee_id(_raise(api_client, owner_session, teacher, client_mutation_id=key))

    assert first == second
    assert restricted_session.scalar(sa.select(sa.func.count(ExtraFee.id))) == 1
    assert restricted_session.scalar(sa.select(sa.func.count(ExtraFeeCharge.id))) == 3


def test_the_same_key_with_a_different_fee_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A retry key names one fee; reusing it for another is a 409.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    _class(owner_session, teacher, account_factory)
    key = str(uuid.uuid4())
    _fee_id(_raise(api_client, owner_session, teacher, client_mutation_id=key))

    response = _raise(
        api_client, owner_session, teacher, client_mutation_id=key, amount="600.00"
    )

    assert response.status_code == 409  # type: ignore[attr-defined]
    assert _code(response) == "MUTATION_ID_ALREADY_USED"


def test_overlapping_resends_of_a_raise_record_one_fee(
    restricted_engine: Engine,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Four overlapping raises with one key: exactly one fee, one charge per seat.

    Concurrency, not sequence: the constraint, not a lookup, must stop
    the second. Run through the service directly so the four start
    together rather than queueing behind one HTTP client.

    :param restricted_engine: The application role's engine
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    from app.authz.lenses import TeacherLens
    from app.fees.extra import FeeDraft, raise_extra_fee

    _class(owner_session, teacher, account_factory)
    key = uuid.uuid4()
    lens = TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)
    draft = FeeDraft(
        purpose="exam",
        label="Half-yearly exam fee",
        exam_id=None,
        amount=Money("500.00"),
        due_on=dt.date(2026, 11, 15),
        seat_amounts={},
        excluded=frozenset(),
        client_mutation_id=key,
    )
    gate = threading.Barrier(4)
    found: list[uuid.UUID] = []
    errors: list[BaseException] = []

    def run() -> None:
        with Session(restricted_engine) as session:
            gate.wait()
            try:
                found.append(
                    raise_extra_fee(
                        session, lens=lens, batch_id=teacher.batch_id, draft=draft
                    ).id
                )
            except BaseException as error:  # noqa: BLE001  collected, asserted below
                errors.append(error)

    workers = [threading.Thread(target=run) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert errors == []
    assert len(set(found)) == 1
    with Session(restricted_engine) as session:
        assert session.scalar(sa.select(sa.func.count(ExtraFee.id))) == 1
        assert session.scalar(sa.select(sa.func.count(ExtraFeeEntry.id))) == 3


def test_another_teachers_batch_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Raising on a batch this lens does not own is the shared 403.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    _class(owner_session, teacher, account_factory)
    stranger = make_teacher(owner_session, name="Chemistry")

    response = api_client.post(
        f"/v1/batches/{teacher.batch_id}/extra-fees",
        json={
            "purpose": "other",
            "label": "Lab materials",
            "amount": "300.00",
            "due_on": DUE,
        },
        headers=bearer(owner_session, stranger.account_id),
    )

    assert response.status_code == 403
    assert owner_session.scalar(sa.select(sa.func.count(ExtraFee.id))) == 0


def test_a_blank_name_or_negative_amount_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A fee families cannot name, or one below zero, is a 400.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    _class(owner_session, teacher, account_factory)

    blank = _raise(api_client, owner_session, teacher, label="   ")
    negative = _raise(api_client, owner_session, teacher, amount="-1.00")

    assert blank.status_code == 400  # type: ignore[attr-defined]
    assert _code(blank) == "EXTRA_FEE_LABEL_REQUIRED"
    assert negative.status_code in (400, 422)  # type: ignore[attr-defined]


# --- paying ----------------------------------------------------------------


def test_paying_an_exam_fee_settles_it_and_no_month(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1000 for Tania and Tanvir's exam fees: both paid, October untouched.

    Each child owes 500.00 on the fee; 1000.00 approved settles both, and
    each still owes 1000.00 for October.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    submission = _submission(
        _submit(
            api_client,
            owner_session,
            family,
            "1000.00",
            seats=[family.tania, family.tanvir],
            purpose="extra",
            extra_fee_id=fee,
        )
    )

    response = _approve(api_client, owner_session, teacher, submission, "1000.00")

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    rows = _seats(api_client, owner_session, teacher, fee)
    assert (rows["Tania"]["status"], rows["Tanvir"]["status"]) == ("paid", "paid")
    assert rows["Rafi"]["owed"] == "500.00"
    restricted_session.expire_all()
    for seat in (family.tania, family.tanvir):
        assert _monthly(restricted_session, seat) == Money("1000.00")


def test_the_review_shows_what_the_family_owes_on_that_fee(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Sent 500 for Tania's 500 exam fee: matches, not 500 short of October.

    Measured against the monthly balance, 500 against 1000 would read
    "short"; against the fee it chose, it matches exactly.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    submission = _submission(
        _submit(
            api_client,
            owner_session,
            family,
            "500.00",
            seats=[family.tania],
            purpose="extra",
            extra_fee_id=fee,
        )
    )

    review = api_client.get(
        f"/v1/payments/{submission}", headers=bearer(owner_session, teacher.account_id)
    ).json()

    assert (review["owed_together"], review["comparison"]) == ("500.00", "matches")
    assert review["purpose"] == "extra"
    assert review["extra_fee"]["label"] == "Half-yearly exam fee"
    assert review["requested_purpose"] == "extra"


def test_a_short_exam_fee_needs_a_choice_and_carried_stays_owed(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """300 of Tania's 500: refused without a choice; carried leaves 200 owed.

    500 - 300 = 200.00 still owed, partly paid; nothing moves into any
    month, because an exam fee is not a month.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    submission = _submission(
        _submit(
            api_client,
            owner_session,
            family,
            "300.00",
            seats=[family.tania],
            purpose="extra",
            extra_fee_id=fee,
        )
    )

    unchosen = _approve(api_client, owner_session, teacher, submission, "300.00")
    carried = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "300.00",
        shortfall_disposition="carried",
    )

    assert unchosen.status_code == 400  # type: ignore[attr-defined]
    assert _code(unchosen) == "ALLOCATION_DISPOSITION_REQUIRED"
    assert carried.status_code == 200, carried.text  # type: ignore[attr-defined]
    tania = _seats(api_client, owner_session, teacher, fee)["Tania"]
    assert (tania["paid"], tania["owed"], tania["status"]) == (
        "300.00",
        "200.00",
        "partly_paid",
    )


def test_a_short_exam_fee_waived_leaves_nothing_owed(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """300 of 500, waived: nothing owed, 300 paid, and a payment means "paid".

    The fee's status follows the monthly rule: money arrived, so the
    settled charge reads ``paid`` rather than ``waived``.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    submission = _submission(
        _submit(
            api_client,
            owner_session,
            family,
            "300.00",
            seats=[family.tania],
            purpose="extra",
            extra_fee_id=fee,
        )
    )

    response = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "300.00",
        shortfall_disposition="waived",
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    tania = _seats(api_client, owner_session, teacher, fee)["Tania"]
    assert (tania["paid"], tania["owed"], tania["status"]) == ("300.00", "0.00", "paid")


def test_approving_more_than_an_exam_fee_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """700 against a 500 fee is refused, and nothing is written.

    An extra fee holds no credit. The excess is a different payment, and
    the teacher either applies it to the monthly fee or approves 500.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    submission = _submission(
        _submit(
            api_client,
            owner_session,
            family,
            "700.00",
            seats=[family.tania],
            purpose="extra",
            extra_fee_id=fee,
        )
    )

    response = _approve(api_client, owner_session, teacher, submission, "700.00")

    assert response.status_code == 400  # type: ignore[attr-defined]
    assert _code(response) == "EXTRA_FEE_OVERPAID"
    tania = _seats(api_client, owner_session, teacher, fee)["Tania"]
    assert tania["owed"] == "500.00"
    count = owner_session.scalar(
        sa.select(sa.func.count(ExtraFeeEntry.id)).where(
            ExtraFeeEntry.payment_claim_id.is_not(None)
        )
    )
    assert count == 0


def test_the_teacher_can_apply_an_exam_payment_to_the_month(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The family chose the exam fee; the teacher applies 1000 to October.

    October paid (1000 - 1000 = 0), the exam fee still 500.00 owed, and
    the review says both what was asked for and what it was applied to.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    submission = _submission(
        _submit(
            api_client,
            owner_session,
            family,
            "1000.00",
            seats=[family.tania],
            purpose="extra",
            extra_fee_id=fee,
        )
    )

    response = _approve(
        api_client, owner_session, teacher, submission, "1000.00", purpose="monthly"
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert (body["purpose"], body["requested_purpose"]) == ("monthly", "extra")
    assert body["extra_fee"] is None
    assert body["requested_extra_fee"]["label"] == "Half-yearly exam fee"
    restricted_session.expire_all()
    assert _monthly(restricted_session, family.tania) == Money.ZERO
    assert _seats(api_client, owner_session, teacher, fee)["Tania"]["owed"] == "500.00"


def test_a_monthly_payment_can_be_applied_to_an_exam_fee(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Sent as a monthly fee, applied to the exam fee: 500 paid there, October 1000.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    submission = _submission(
        _submit(api_client, owner_session, family, "500.00", seats=[family.tania])
    )

    response = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "500.00",
        purpose="extra",
        extra_fee_id=fee,
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    assert _seats(api_client, owner_session, teacher, fee)["Tania"]["status"] == "paid"
    restricted_session.expire_all()
    assert _monthly(restricted_session, family.tania) == Money("1000.00")


def test_correcting_an_exam_approval_to_a_rejection_restores_what_was_owed(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Approved 500, then corrected to rejected: 500.00 owed again.

    Append-only: the receipt stays, compensated by a charge, so the
    fold returns to 500 owed and the trail keeps both.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    submission = _submission(
        _submit(
            api_client,
            owner_session,
            family,
            "500.00",
            seats=[family.tania],
            purpose="extra",
            extra_fee_id=fee,
        )
    )
    _approve(api_client, owner_session, teacher, submission, "500.00")

    response = api_client.post(
        f"/v1/payments/{submission}/rejection",
        json={"correcting": True, "note": "Not in my statement"},
        headers=bearer(owner_session, teacher.account_id),
    )

    assert response.status_code == 200, response.text
    tania = _seats(api_client, owner_session, teacher, fee)["Tania"]
    assert (tania["owed"], tania["paid"]) == ("500.00", "0.00")
    kinds = owner_session.scalars(
        sa.select(ExtraFeeEntry.kind).order_by(ExtraFeeEntry.created_at)
    ).all()
    assert kinds.count("receipt") == 1
    assert kinds.count("charge") == 4  # three raised, one compensating


def test_correcting_across_purposes_moves_the_money_back(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Applied to the exam fee, then corrected to October: each ledger right.

    After the correction: exam fee 500.00 owed again, October 500.00
    owed (1000 - 500).

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    submission = _submission(
        _submit(
            api_client,
            owner_session,
            family,
            "500.00",
            seats=[family.tania],
            purpose="extra",
            extra_fee_id=fee,
        )
    )
    _approve(api_client, owner_session, teacher, submission, "500.00")

    response = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "500.00",
        purpose="monthly",
        shortfall_disposition="carried",
        correcting=True,
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    assert _seats(api_client, owner_session, teacher, fee)["Tania"]["owed"] == "500.00"
    restricted_session.expire_all()
    assert _monthly(restricted_session, family.tania) == Money("500.00")


def test_an_older_app_sending_no_purpose_pays_the_month(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """No purpose field at all: recorded as monthly, exactly as before.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    submission = _submission(
        _submit(api_client, owner_session, family, "1000.00", seats=[family.tania])
    )

    _approve(api_client, owner_session, teacher, submission, "1000.00")

    restricted_session.expire_all()
    assert _monthly(restricted_session, family.tania) == Money.ZERO
    assert _seats(api_client, owner_session, teacher, fee)["Tania"]["owed"] == "500.00"


def test_paying_a_fee_a_child_was_not_charged_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Rafi was left out of the fee, so a payment for it is a 400.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(
        _raise(
            api_client,
            owner_session,
            teacher,
            excluded_enrollment_ids=[str(family.rafi)],
        )
    )
    rafi_account = owner_session.scalar(
        sa.text("SELECT student_account_id FROM enrollment WHERE id = :id"),
        {"id": family.rafi},
    )

    response = _submit(
        api_client,
        owner_session,
        family,
        "500.00",
        seats=[family.rafi],
        payer=rafi_account,
        purpose="extra",
        extra_fee_id=fee,
    )

    assert response.status_code == 400  # type: ignore[attr-defined]
    assert _code(response) == "EXTRA_FEE_NOT_CHARGED"


def test_a_purpose_naming_no_fee_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """``extra`` without a fee, and a fee from another batch, are both 400.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    other = make_teacher(owner_session, name="Chemistry")
    enroll(owner_session, batch_id=other.batch_id, display_name="Someone")
    elsewhere = _fee_id(_raise(api_client, owner_session, other))

    missing = _submit(
        api_client,
        owner_session,
        family,
        "500.00",
        seats=[family.tania],
        purpose="extra",
    )
    foreign = _submit(
        api_client,
        owner_session,
        family,
        "500.00",
        seats=[family.tania],
        purpose="extra",
        extra_fee_id=elsewhere,
    )

    assert missing.status_code == 400  # type: ignore[attr-defined]
    assert _code(missing) == "EXTRA_FEE_REQUIRED"
    assert foreign.status_code == 400  # type: ignore[attr-defined]
    assert _code(foreign) == "EXTRA_FEE_NOT_FOUND"


def test_the_teacher_records_cash_for_an_exam_fee(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """500 in hand for Rafi's exam fee: paid there, October still 1000.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))

    response = api_client.post(
        f"/v1/enrollments/{family.rafi}/payments",
        json={"amount": "500.00", "purpose": "extra", "extra_fee_id": str(fee)},
        headers=bearer(owner_session, teacher.account_id),
    )

    assert response.status_code == 201, response.text
    assert _seats(api_client, owner_session, teacher, fee)["Rafi"]["status"] == "paid"
    restricted_session.expire_all()
    assert _monthly(restricted_session, family.rafi) == Money("1000.00")


def test_recording_more_cash_than_an_exam_fee_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """600 in hand against Rafi's 500 fee is refused, recording nothing.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))

    response = api_client.post(
        f"/v1/enrollments/{family.rafi}/payments",
        json={"amount": "600.00", "purpose": "extra", "extra_fee_id": str(fee)},
        headers=bearer(owner_session, teacher.account_id),
    )

    assert response.status_code == 400, response.text
    assert _code(response) == "EXTRA_FEE_OVERPAID"
    assert _seats(api_client, owner_session, teacher, fee)["Rafi"]["owed"] == "500.00"


# --- families reading --------------------------------------------------------


def test_a_guardian_sees_their_childs_fees_and_another_family_does_not(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Tania's guardian reads her 500 exam fee; Rafi cannot read Tania's.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    _fee_id(_raise(api_client, owner_session, teacher))
    rafi_account = owner_session.scalar(
        sa.text("SELECT student_account_id FROM enrollment WHERE id = :id"),
        {"id": family.rafi},
    )

    own = api_client.get(
        f"/v1/enrollments/{family.tania}/extra-fees",
        headers=bearer(owner_session, family.guardian),
    )
    other = api_client.get(
        f"/v1/enrollments/{family.tania}/extra-fees",
        headers=bearer(owner_session, rafi_account),
    )

    assert own.status_code == 200, own.text
    assert [
        (fee["label"], fee["owed"], fee["status"], fee["due_on"])
        for fee in own.json()["fees"]
    ] == [("Half-yearly exam fee", "500.00", "unpaid", DUE)]
    assert other.status_code == 403


def test_the_owed_line_can_ask_about_one_fee(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Tania and Tanvir owe 1000 together on the fee, 2000 on the months.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _class(owner_session, teacher, account_factory)
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    query = f"enrollment_id={family.tania}&enrollment_id={family.tanvir}"

    monthly = api_client.get(
        f"/v1/payments/owed?{query}", headers=bearer(owner_session, family.guardian)
    )
    extra = api_client.get(
        f"/v1/payments/owed?{query}&extra_fee_id={fee}",
        headers=bearer(owner_session, family.guardian),
    )

    assert monthly.json()["owed_together"] == "2000.00"
    assert extra.json()["owed_together"] == "1000.00"


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE extra_fee_entry SET amount = 0",
        "DELETE FROM extra_fee_entry",
    ],
)
def test_the_application_role_cannot_rewrite_the_fee_ledger(
    api_client: TestClient,
    owner_session: Session,
    restricted_engine: Engine,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
    statement: str,
) -> None:
    """Append-only from the first row: no amount rewritten, no row deleted.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_engine: The application role's engine
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :param statement: The forbidden write
    :return: None
    """
    _class(owner_session, teacher, account_factory)
    _fee_id(_raise(api_client, owner_session, teacher))

    with (
        pytest.raises(sa.exc.ProgrammingError),
        restricted_engine.begin() as connection,
    ):
        connection.execute(sa.text(statement))
