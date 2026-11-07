"""Seed a teacher's account with a realistic stretch of history.

**What a run produces**, for the teacher found by phone:

* three batches -- two teaching Math and Physics, one Math only -- on a
  weekly routine, each with twenty seats; a dozen students sit in two
  batches, so the distinct students number fewer than sixty;
* every class from the first of the month ``months`` back until now,
  attended, its topic logged, a few cancelled for a holiday or a
  hartal, one extra class, a couple never recorded;
* a weekly test every Thursday in each batch and subject, on the
  topics that week's classes covered, marked and published -- except
  the latest, which is still a draft -- plus one model test with its
  exam fee, and one exam cancelled;
* the monthly fee generated on the 1st by the real generation path, and
  paid the way families pay: on time, late, in part, in advance, two
  siblings in one payment, several in cash on the same class day, one
  rejected and sent again, a few still waiting for review -- and some
  who have not paid last month at all;
* families who installed the app and accepted their seats, some who
  have not yet, and one who declined; reminders, announcements,
  expenses, payment methods, and the inbox those produce.

**How.** :func:`seed` opens ONE database transaction and binds the
session to it in savepoint mode, so every service's own ``commit()``
releases a savepoint and the run is all-or-nothing: a failure part-way
leaves the account exactly as it was. Inside it, an event queue is run
in time order under :mod:`app.seed.clock`, each event calling the same
service the API calls, as the person who would have done it.

**Refusals.** Production, an unknown number, a number with no teacher
workspace, and an account already seeded -- a second run would double
the history and is refused rather than guessed at. A transaction-level
advisory lock on the owner makes two concurrent runs for one teacher
serialize, so the second sees the first's batches and refuses.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import heapq
import itertools
import logging
import os
import random
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Final

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.accounts.decisions import accept_seat, decline_seat
from app.accounts.phone import canonical_phone
from app.accounts.service import PostalAddress, SignupRole, create_account
from app.authz.lenses import GuardianLens, InvitationLens, StudentLens, TeacherLens
from app.batches.service import (
    BatchChanges,
    create_batch,
    set_inactive_from,
    update_batch,
)
from app.config import ENVIRONMENT_ENV
from app.db.models import (
    Account,
    Announcement,
    Attendance,
    Batch,
    Enrollment,
    Exam,
    Expense,
    ExtraFee,
    FeeCycle,
    LedgerEntryRow,
    Mark,
    Notification,
    Owner,
    PaymentSubmission,
    ReminderEvent,
    Student,
)
from app.db.models import Session as ClassSession
from app.errors import ValidationError
from app.expenses.service import ExpenseDraft, record_expense, void_expense
from app.fees.balances import derive_for_enrollment
from app.fees.decisions import approve_submission, reject_submission
from app.fees.extra import FeeDraft, raise_extra_fee
from app.fees.generation import generate_due_cycles
from app.fees.methods import MethodDraft, create_method, retire_method
from app.fees.purposes import owed_for_target, resolve_target
from app.fees.received import ReceivedPayment, record_received_payment
from app.fees.reminders import remind
from app.fees.submissions import PaymentDraft, submit_payment
from app.local_time import DHAKA
from app.marks.entry import record_mark
from app.marks.exams import cancel_exam, create_exam
from app.marks.views import publish_exam
from app.money import Disposition, Money
from app.notifications.inbox import mark_read
from app.seed.clock import SimulatedClock, simulated_clock
from app.seed.people import (
    ANNOUNCEMENTS,
    FAMILY_NAMES,
    FEMALE_NAMES,
    GUARDIAN_GIVEN_NAMES,
    MALE_NAMES,
    SESSION_NOTES,
    SYLLABUS,
)
from app.students.service import create_student, seat_for
from app.teaching.announcements import (
    delete_announcement,
    edit_announcement,
    post_announcement,
)
from app.teaching.generation import generate_sessions
from app.teaching.roster import session_roster
from app.teaching.schedule import Slot, set_schedule
from app.teaching.sessions import (
    cancel_session,
    create_ad_hoc_session,
    write_session_subject,
)
from app.teaching.submissions import SeatMark, submit_roster, write_topic

__all__ = [
    "PERMITTED_ENVIRONMENTS",
    "SeedRefused",
    "SeedReport",
    "SeedRequest",
    "seed",
]

log = logging.getLogger(__name__)

#: Environments this may run against. Production is absent and no
#: value adds it -- the same set :mod:`app.db.seed_staging` permits.
PERMITTED_ENVIRONMENTS: Final = frozenset({"staging", "development", "test"})

#: The longest history a run may write. A year of three batches is
#: still minutes of work; more is a typo, and the run is one transaction.
MAX_MONTHS: Final = 12

#: A weekly test's total, and the model test's.
WEEKLY_TOTAL: Final = 25
MODEL_TOTAL: Final = 50

#: Marks a test slot in a routine: the class that sits the weekly test.
TEST: Final = "TEST"

#: A payment reported this close to the end is left for the teacher to
#: review, so the review queue is not empty.
PENDING_WINDOW: Final = dt.timedelta(hours=36)

#: Bangladesh's weekday numbers as ``ScheduleSlot`` counts them.
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


class SeedRefused(RuntimeError):
    """The run was refused before anything was written."""


@dataclass(frozen=True, slots=True)
class SeedRequest:
    """What to seed.

    :ivar phone: The teacher's number, in any form the app accepts
    :ivar months: Whole months of history before the current one
    :ivar seed: The random seed; the same seed gives the same history
    """

    phone: str
    months: int = 3
    seed: int = 20261106


@dataclass(slots=True)
class SeedReport:
    """What a run wrote, counted from the database afterwards.

    :ivar owner_id: The teacher workspace seeded
    :ivar history_from: The first simulated day
    :ivar history_to: The moment the simulation stopped, which is now
    :ivar counts: Rows per kind, scoped to this owner
    :ivar family_logins: A few seeded family numbers to sign in with
    """

    owner_id: uuid.UUID
    history_from: dt.date
    history_to: dt.datetime
    counts: dict[str, int]
    family_logins: list[dict[str, str]]

    def as_dict(self) -> dict[str, object]:
        """Render the report as JSON-safe values.

        :return: The report
        """
        return {
            "owner_id": str(self.owner_id),
            "history_from": self.history_from.isoformat(),
            "history_to": self.history_to.isoformat(),
            "counts": dict(self.counts),
            "family_logins": list(self.family_logins),
        }


# ---------------------------------------------------------------------------
# The plan: batches, routines and people. Deterministic per seed.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _SlotSpec:
    """One weekly class: day, times, and what it teaches.

    :ivar weekday: 0-6, Monday first
    :ivar start: Start, Bangladesh time
    :ivar end: End, Bangladesh time
    :ivar subject: The subject taught, or :data:`TEST` for test day
    """

    weekday: int
    start: dt.time
    end: dt.time
    subject: str


@dataclass(frozen=True, slots=True)
class _BatchSpec:
    """One batch as the teacher sets it up.

    :ivar key: A short handle used inside the simulation only
    :ivar name: The batch name
    :ivar subjects: The subjects, in order
    :ivar fee: The monthly fee in taka
    :ivar due_day: The fee's day of month
    :ivar slots: The weekly routine
    """

    key: str
    name: str
    subjects: tuple[str, ...]
    fee: int
    due_day: int
    slots: tuple[_SlotSpec, ...]


def _t(text: str) -> dt.time:
    """Parse ``HH:MM``.

    :param text: The time
    :return: The time value
    """
    hours, minutes = text.split(":")
    return dt.time(int(hours), int(minutes))


#: Two Math-and-Physics batches and one Math-only, on routines that do
#: not overlap: mornings, evenings, and a late slot.
BATCHES: Final = (
    _BatchSpec(
        key="A",
        name="SSC 2027 Science - Morning",
        subjects=("Math", "Physics"),
        fee=1500,
        due_day=10,
        slots=(
            _SlotSpec(SAT, _t("07:30"), _t("09:00"), "Math"),
            _SlotSpec(SUN, _t("07:30"), _t("09:00"), "Physics"),
            _SlotSpec(TUE, _t("07:30"), _t("09:00"), "Math"),
            _SlotSpec(WED, _t("07:30"), _t("09:00"), "Physics"),
            _SlotSpec(THU, _t("07:30"), _t("08:30"), TEST),
        ),
    ),
    _BatchSpec(
        key="B",
        name="SSC 2027 Science - Evening",
        subjects=("Math", "Physics"),
        fee=1800,
        due_day=5,
        slots=(
            _SlotSpec(SAT, _t("17:00"), _t("18:30"), "Physics"),
            _SlotSpec(SUN, _t("17:00"), _t("18:30"), "Math"),
            _SlotSpec(MON, _t("17:00"), _t("18:30"), "Physics"),
            _SlotSpec(TUE, _t("17:00"), _t("18:30"), "Math"),
            _SlotSpec(THU, _t("17:00"), _t("18:00"), TEST),
        ),
    ),
    _BatchSpec(
        key="C",
        name="Math Special Care",
        subjects=("Math",),
        fee=1000,
        due_day=15,
        slots=(
            _SlotSpec(SUN, _t("19:00"), _t("20:00"), "Math"),
            _SlotSpec(TUE, _t("19:00"), _t("20:00"), "Math"),
            _SlotSpec(THU, _t("19:00"), _t("20:00"), TEST),
        ),
    ),
)

#: Which batches each of the 48 students sits in: 14 in A only, 14 in B
#: only, 8 in C only, and 6 each of A and B who also take C -- twenty
#: seats per batch, forty-eight people.
MEMBERSHIP: Final = (
    *(("A",) for _ in range(14)),
    *(("B",) for _ in range(14)),
    *(("C",) for _ in range(8)),
    *(("A", "C") for _ in range(6)),
    *(("B", "C") for _ in range(6)),
)

#: How a family pays, as weights. ``owes`` pays until last month and
#: then stops -- the dues the teacher chases.
PAYER_WEIGHTS: Final = {
    "prompt": 40,
    "late": 25,
    "owes": 22,
    "partial": 10,
    "advance": 5,
    "cash_day": 5,
}


@dataclass(slots=True)
class _Kid:
    """One student, their family, and how they behave.

    :ivar index: Position in :data:`MEMBERSHIP`
    :ivar name: The teacher-typed name
    :ivar student_phone: Their own number, or None for a younger child
    :ivar guardian_phone: The guardian's number
    :ivar guardian_name: The guardian's own name, for their profile
    :ivar batches: Batch keys, in seat order
    :ivar joins: The day they join
    :ivar leaves: The ``inactive_from`` of a leaver's first batch
    :ivar fee: A seat fee different from the batch's, in taka
    :ivar payer: One of :data:`PAYER_WEIGHTS`
    :ivar app_user: ``guardian``, ``student`` or ``None`` for cash
    :ivar pending_guardian: Signed up, never accepted
    :ivar declined_guardian: Signed up and declined
    :ivar present_rate: How often they attend
    :ivar ability: Their mean score, 0-1
    :ivar method: The payment method they use in the app
    :ivar student_id: The teacher's student record, once created
    :ivar seats: Enrollment per batch key, once created
    :ivar student_account: Their account, once they sign up
    :ivar guardian_account: Their guardian's, once they sign up
    """

    index: int
    name: str
    student_phone: str | None
    guardian_phone: str
    guardian_name: str
    batches: tuple[str, ...]
    joins: dt.date
    leaves: dt.date | None = None
    fee: int | None = None
    payer: str = "prompt"
    app_user: str | None = None
    pending_guardian: bool = False
    declined_guardian: bool = False
    present_rate: float = 0.9
    ability: float = 0.7
    method: str = "bkash"
    student_id: uuid.UUID | None = None
    seats: dict[str, uuid.UUID] = field(default_factory=dict)
    student_account: uuid.UUID | None = None
    guardian_account: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def seed(
    engine: Engine,
    request: SeedRequest,
    *,
    environment: str | None = None,
    now: dt.datetime | None = None,
) -> SeedReport:
    """Seed one teacher's account, all or nothing.

    :param engine: The engine to connect through; the restricted role
    :param request: Which account, how far back, which random seed
    :param environment: The environment name, or None to read it
    :param now: Where the history ends; the real clock by default
    :return: What was written
    :raises SeedRefused: Production, an unknown number, no teacher
        workspace, an already-seeded account, or a bad request
    """
    environment = environment or os.environ.get(ENVIRONMENT_ENV, "development")
    if environment not in PERMITTED_ENVIRONMENTS:
        raise SeedRefused(
            f"refusing to run: {ENVIRONMENT_ENV} is '{environment}'. This "
            "creates accounts and money records, which is not something a "
            "script should do to a production database."
        )
    if not 1 <= request.months <= MAX_MONTHS:
        raise SeedRefused(f"months must be between 1 and {MAX_MONTHS}")
    try:
        phone = canonical_phone(request.phone)
    except ValidationError:
        raise SeedRefused("phone is not a Bangladeshi mobile number") from None

    end = (now or dt.datetime.now(tz=dt.UTC)).astimezone(DHAKA)

    with engine.connect() as connection:
        outer = connection.begin()
        # Savepoint mode: every service's commit() releases a savepoint
        # and the run commits once, below, or not at all.
        session = Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            lens = _teacher_lens(session, phone)
            simulation = _Simulation(session, lens=lens, request=request, end=end)
            simulation.run()
            report = simulation.report()
            session.close()
            outer.commit()
        except BaseException:
            session.close()
            outer.rollback()
            raise
    log.info("seeded a teacher workspace", extra={"counts": report.counts})
    return report


def _teacher_lens(session: Session, phone: str) -> TeacherLens:
    """Find the teacher, lock their workspace, refuse a second seed.

    :param session: The run's session
    :param phone: The canonical number
    :return: The solo teacher workspace's lens
    :raises SeedRefused: No account, no teacher workspace, or seeded
    """
    account_id = session.execute(
        sa.select(Account.id).where(Account.phone == phone)
    ).scalar_one_or_none()
    if account_id is None:
        raise SeedRefused("no account has that number; sign up as a teacher first")
    owner_id = session.execute(
        sa.select(Owner.id)
        .where(Owner.account_id == account_id, Owner.kind == "teacher")
        .order_by(Owner.created_at)
        .limit(1)
    ).scalar_one_or_none()
    if owner_id is None:
        raise SeedRefused("that account has no teacher workspace to seed")

    # Two concurrent runs for one teacher queue here; the second then
    # sees the first's batches below and refuses.
    session.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"shikkhokplus-seed:{owner_id}"},
    )
    names = {spec.name for spec in BATCHES}
    seeded = session.execute(
        sa.select(sa.func.count())
        .select_from(Batch)
        .where(Batch.owner_id == owner_id, Batch.name.in_(names))
    ).scalar_one()
    if seeded:
        raise SeedRefused(
            "this account already has the seeded batches; seeding again "
            "would double its history. Use a fresh teacher account."
        )
    return TeacherLens(account_id=account_id, owner_id=owner_id)


# ---------------------------------------------------------------------------
# The simulation
# ---------------------------------------------------------------------------


def _at(day: dt.date, clock: dt.time | str) -> dt.datetime:
    """Build a Bangladesh-time moment on a day.

    :param day: The date
    :param clock: The time, or ``HH:MM``
    :return: The aware moment
    """
    value = _t(clock) if isinstance(clock, str) else clock
    return dt.datetime.combine(day, value, tzinfo=DHAKA)


def _week_of(day: dt.date) -> dt.date:
    """Return the Saturday a Bangladesh school week starts on.

    :param day: Any date
    :return: The Saturday on or before it
    """
    return day - dt.timedelta(days=(day.weekday() - SAT) % 7)


def _month_start(day: dt.date, back: int) -> dt.date:
    """Return the first of the month ``back`` months before ``day``'s.

    :param day: The reference date
    :param back: Whole months back
    :return: That month's first day
    """
    index = day.year * 12 + day.month - 1 - back
    return dt.date(index // 12, index % 12 + 1, 1)


def _taka(amount: Money) -> int:
    """Read a whole-taka amount as an integer, for planning only.

    :param amount: The money
    :return: Its taka part
    """
    return int(str(amount).split(".")[0])


def _round_down_100(value: int) -> int:
    """Round an amount down to a hundred taka, as people pay.

    :param value: Taka
    :return: The rounded amount, at least 100
    """
    return max(100, value - value % 100)


class _Simulation:
    """The event queue and the world it acts on.

    :ivar session: The run's session
    :ivar teacher: The teacher's lens
    :ivar rng: The run's only source of randomness
    :ivar start: The first simulated day
    :ivar end: The moment the simulation stops
    :ivar clock: The simulated clock the services read
    """

    def __init__(
        self,
        session: Session,
        *,
        lens: TeacherLens,
        request: SeedRequest,
        end: dt.datetime,
    ) -> None:
        """Plan the run.

        :param session: The run's session
        :param lens: The teacher's lens
        :param request: The request
        :param end: Where the history stops
        """
        self.session = session
        self.teacher = lens
        self.rng = random.Random(f"{request.seed}:{lens.owner_id}")  # noqa: S311  test data, not security
        self.end = end
        self.today = end.date()
        self.start = _month_start(self.today, request.months)
        self.clock = SimulatedClock(_at(self.start, "00:00"))
        self._queue: list[tuple[dt.datetime, int, Callable[[], None]]] = []
        self._sequence = itertools.count()

        self.batch_ids: dict[str, uuid.UUID] = {}
        self.subject_ids: dict[tuple[str, str], uuid.UUID] = {}
        self.specs = {spec.key: spec for spec in BATCHES}
        self.methods: dict[str, uuid.UUID] = {}
        self.syllabus_at: dict[tuple[str, str], int] = defaultdict(int)
        self.covered: dict[tuple[str, str, dt.date], list[str]] = defaultdict(list)
        self.test_rosters: dict[tuple[str, dt.date], dict[uuid.UUID, bool]] = {}
        self.exams: list[tuple[uuid.UUID, str, dt.date]] = []
        self.announcements: list[uuid.UUID] = []
        self.rejected_once = False
        self.unrecorded_left = 2

        self.block = (
            int(
                hashlib.sha256(f"{lens.owner_id}:{request.seed}".encode()).hexdigest(),
                16,
            )
            % 10_000
        )
        self.kids = self._plan_people()
        self.holidays = self._plan_holidays()
        self.hartal_week = _week_of(self.start + dt.timedelta(days=52))
        self.model_day = self._plan_model_day()

    # -- planning ----------------------------------------------------------

    def _phone(self, role: int, index: int) -> str:
        """Build a deterministic, owner-specific family number.

        ``013`` + a four-digit block from the owner and seed + a role
        digit + a three-digit index: eleven digits, a valid mobile.

        :param role: 1 for a student, 2 for a guardian
        :param index: The kid's index
        :return: The canonical number
        """
        return canonical_phone(f"013{self.block:04d}{role}{index:03d}")

    def _plan_people(self) -> list[_Kid]:
        """Draw the forty-eight students and how each behaves.

        :return: The students, in :data:`MEMBERSHIP` order
        """
        rng = self.rng
        kids: list[_Kid] = []
        used: set[str] = set()
        for index, batches in enumerate(MEMBERSHIP):
            given = rng.choice(MALE_NAMES if index % 2 else FEMALE_NAMES)
            surname = rng.choice(FAMILY_NAMES)
            while f"{given} {surname}" in used:
                surname = rng.choice(FAMILY_NAMES)
            used.add(f"{given} {surname}")
            kids.append(
                _Kid(
                    index=index,
                    name=f"{given} {surname}",
                    student_phone=(
                        self._phone(1, index) if rng.random() < 0.7 else None
                    ),
                    guardian_phone=self._phone(2, index),
                    guardian_name=f"{rng.choice(GUARDIAN_GIVEN_NAMES)} {surname}",
                    batches=batches,
                    joins=self.start + dt.timedelta(days=rng.choice((0, 0, 0, 1, 2))),
                    payer=rng.choices(
                        list(PAYER_WEIGHTS), weights=list(PAYER_WEIGHTS.values())
                    )[0],
                    app_user=rng.choices(
                        ["guardian", "student", None], weights=[45, 20, 35]
                    )[0],
                    present_rate=rng.choice((0.97, 0.93, 0.9, 0.85, 0.7)),
                    ability=rng.uniform(0.35, 0.95),
                    method=rng.choices(["bkash", "nagad", "bank"], [70, 22, 8])[0],
                )
            )

        # Siblings: two pairs share a guardian, a surname and a payment.
        for first, second in ((2, 3), (16, 17)):
            older, younger = kids[first], kids[second]
            younger.name = f"{younger.name.split()[0]} {older.name.split()[1]}"
            younger.guardian_phone = older.guardian_phone
            younger.guardian_name = older.guardian_name
            for kid in (older, younger):
                kid.app_user, kid.payer, kid.fee = "guardian", "prompt", 1200
                kid.student_phone = None

        # Late joiners, a leaver, a discount, a free seat, and the
        # families who signed up but have not accepted, or declined.
        days = (self.today - self.start).days
        kids[13].joins = self.start + dt.timedelta(days=min(45, days // 2))
        kids[27].joins = self.start + dt.timedelta(days=min(66, days * 2 // 3))
        kids[35].joins = self.start + dt.timedelta(days=min(40, days // 2))
        kids[12].leaves = self.start + dt.timedelta(days=max(1, days - 18))
        kids[12].payer = "owes"
        kids[5].fee = 1000
        kids[30].fee = 0
        kids[30].payer = "prompt"
        for index in (8, 22):
            kids[index].app_user, kids[index].pending_guardian = None, True
        kids[40].app_user, kids[40].declined_guardian = "student", True
        kids[40].student_phone = kids[40].student_phone or self._phone(1, 40)
        for kid in kids:
            if kid.app_user == "student" and kid.student_phone is None:
                kid.app_user = "guardian"
            if kid.payer == "cash_day":
                kid.app_user = None
        return kids

    def _plan_holidays(self) -> set[dt.date]:
        """Pick a two-day holiday, a Saturday and Sunday, mid-history.

        :return: The holiday dates
        """
        middle = self.start + dt.timedelta(days=(self.today - self.start).days * 2 // 3)
        saturday = _week_of(middle)
        return {saturday, saturday + dt.timedelta(days=1)}

    def _plan_model_day(self) -> dt.date | None:
        """Pick the model test's Friday: the last of the second month.

        :return: That Friday, or None when the history is too short
        """
        month = (
            _month_start(self.today, 1)
            if self.start < _month_start(self.today, 1)
            else None
        )
        if month is None:
            return None
        day = month - dt.timedelta(days=1)
        while day.weekday() != FRI:
            day -= dt.timedelta(days=1)
        return day if day - dt.timedelta(days=10) >= self.start else None

    # -- the queue ---------------------------------------------------------

    def at(self, moment: dt.datetime, action: Callable[[], None]) -> None:
        """Schedule an action, dropping it if it falls after the end.

        :param moment: When it happens
        :param action: What happens
        :return: None
        :raises ValueError: The moment is before the clock -- the past
            cannot be scheduled
        """
        if moment < self.clock.moment:
            raise ValueError("an event cannot be scheduled in the past")
        if moment <= self.end:
            heapq.heappush(self._queue, (moment, next(self._sequence), action))

    def run(self) -> None:
        """Run every event in time order under the simulated clock.

        :return: None
        """
        self.at(_at(self.start, "06:00"), self._set_up)
        day = self.start
        while day <= self.today:
            self.at(_at(day, "00:05"), partial(self._open_month, day))
            self.at(_at(day, "06:30"), partial(self._open_day, day))
            day += dt.timedelta(days=1)
        with simulated_clock(self.clock):
            while self._queue:
                moment, _order, action = heapq.heappop(self._queue)
                self.clock.set(moment)
                action()
            self.clock.set(self.end - dt.timedelta(hours=3))
            self._last_minute_payments()
            self.clock.set(self.end)
            self._plan_upcoming_topics()

    # -- set-up ------------------------------------------------------------

    def _set_up(self) -> None:
        """Set up the first morning: methods, batches, routines, students.

        :return: None
        """
        local = (
            "0"
            + self.session.execute(
                sa.select(Account.phone).where(Account.id == self.teacher.account_id)
            ).scalar_one()[4:]
        )
        for key, draft in (
            (
                "bkash",
                MethodDraft(
                    kind="mobile",
                    provider="bKash",
                    mobile_number=local,
                    note="Personal number. Use Send Money.",
                ),
            ),
            (
                "nagad",
                MethodDraft(kind="mobile", provider="Nagad", mobile_number=local),
            ),
            (
                "rocket",
                MethodDraft(kind="mobile", provider="Rocket", mobile_number=local),
            ),
            (
                "bank",
                MethodDraft(
                    kind="bank",
                    provider="Dutch-Bangla Bank",
                    account_number="1051100048215",
                    account_name="Fee collection account",
                    branch_name="Mirpur",
                ),
            ),
        ):
            self.methods[key] = create_method(
                self.session, lens=self.teacher, draft=draft
            ).id

        for spec in BATCHES:
            summary = create_batch(
                self.session,
                lens=self.teacher,
                name=spec.name,
                subjects=list(spec.subjects),
                default_fee=Money(spec.fee),
                fee_due_day=spec.due_day,
            )
            self.batch_ids[spec.key] = summary.batch.id
            update_batch(
                self.session,
                lens=self.teacher,
                batch_id=summary.batch.id,
                changes=BatchChanges(marksheet_visible=True),
            )
            for subject_id, name in zip(
                summary.subject_ids, summary.subjects, strict=True
            ):
                self.subject_ids[(spec.key, name)] = subject_id
            set_schedule(
                self.session,
                lens=self.teacher,
                batch_id=summary.batch.id,
                slots=[Slot(s.weekday, s.start, s.end) for s in spec.slots],
                today=self.start,
            )
            self._announce(spec.key, "welcome")
        self._plan_month_notices(self.start)

        for kid in self.kids:
            self.at(_at(kid.joins, "06:10"), partial(self._admit, kid))
            if kid.leaves is not None:
                self.at(_at(kid.leaves, "10:00"), partial(self._leave, kid))
        self.at(_at(self.start, "06:20"), self._generate_fees)
        self.at(_at(self.start + dt.timedelta(days=40), "22:00"), self._retire_rocket)

    def _admit(self, kid: _Kid) -> None:
        """Record a student and seat them, then plan their family.

        :param kid: The student
        :return: None
        """
        row = create_student(
            self.session,
            lens=self.teacher,
            display_name=kid.name,
            student_phone=kid.student_phone,
            guardian_phone=kid.guardian_phone,
        )
        kid.student_id = row.student_id
        student = self.session.get_one(Student, row.student_id)
        for key in kid.batches:
            spec = self.specs[key]
            fee = None if kid.fee is None or kid.fee == spec.fee else Money(kid.fee)
            seat = seat_for(
                self.session,
                lens=self.teacher,
                student=student,
                batch_id=self.batch_ids[key],
                fee_amount=fee,
                joined_on=kid.joins,
            )
            self.session.commit()
            kid.seats[key] = seat.id
        if kid.joins != self.start:
            self._generate_fees()
        for key in kid.batches:
            self._plan_month(kid, key, kid.joins)
        self._plan_family(kid)

    def _plan_family(self, kid: _Kid) -> None:
        """Schedule the family signing up and answering their seats.

        :param kid: The student
        :return: None
        """
        signup = kid.joins + dt.timedelta(days=self.rng.randint(1, 9))
        evening = f"{self.rng.randint(19, 22)}:{self.rng.choice(('05', '20', '40'))}"
        if kid.app_user == "student" or kid.declined_guardian:
            self.at(_at(signup, evening), lambda: self._sign_up(kid, "student"))
        if kid.app_user == "guardian" or kid.pending_guardian or kid.declined_guardian:
            later = signup + dt.timedelta(days=1)
            self.at(_at(later, evening), lambda: self._sign_up(kid, "guardian"))

    def _sign_up(self, kid: _Kid, role: str) -> None:
        """Create a family account and answer every seat it reaches.

        :param kid: The student
        :param role: ``student`` or ``guardian``
        :return: None
        :raises SeedRefused: The number is already someone's account
        """
        if role == "guardian" and kid.guardian_account is not None:
            return
        sibling = next(
            (
                other
                for other in self.kids
                if other is not kid
                and other.guardian_phone == kid.guardian_phone
                and other.guardian_account is not None
            ),
            None,
        )
        if role == "guardian" and sibling is not None:
            kid.guardian_account = sibling.guardian_account
            self._answer(kid, role)
            return
        phone = kid.student_phone if role == "student" else kid.guardian_phone
        assert phone is not None  # noqa: S101  planned with a number
        exists = self.session.execute(
            sa.select(Account.id).where(Account.phone == phone)
        ).scalar_one_or_none()
        if exists is not None:
            raise SeedRefused(
                "a seeded family number already belongs to an account; "
                "run again with a different seed"
            )
        rng = self.rng
        created = create_account(
            self.session,
            phone=phone,
            role=SignupRole.STUDENT if role == "student" else SignupRole.GUARDIAN,
            self_name=kid.name if role == "student" else kid.guardian_name,
            address=PostalAddress(
                house=f"House {rng.randint(3, 120)}, Flat {rng.choice('ABCD')}",
                road=f"Road {rng.randint(1, 18)}, Mirpur {rng.randint(1, 14)}",
                city="Dhaka",
                postcode="1216",
            ),
        )
        if role == "student":
            kid.student_account = created.account_id
        else:
            kid.guardian_account = created.account_id
        self._answer(kid, role)

    def _answer(self, kid: _Kid, role: str) -> None:
        """Accept, decline, or leave pending every seat of this link.

        :param kid: The student
        :param role: Which link answers
        :return: None
        """
        account = kid.student_account if role == "student" else kid.guardian_account
        assert account is not None  # noqa: S101  just signed up
        if role == "guardian" and kid.pending_guardian:
            return
        answer = (
            decline_seat
            if role == "guardian" and kid.declined_guardian
            else accept_seat
        )
        for seat in kid.seats.values():
            answer(
                self.session,
                lens=InvitationLens(account_id=account, enrollment_id=seat),
            )

    def _leave(self, kid: _Kid) -> None:
        """Record that a student stopped coming to their first batch.

        :param kid: The student
        :return: None
        """
        assert kid.leaves is not None  # noqa: S101  scheduled for a leaver
        set_inactive_from(
            self.session,
            lens=self.teacher,
            enrollment_id=kid.seats[kid.batches[0]],
            inactive_from=kid.leaves,
        )

    def _retire_rocket(self) -> None:
        """Retire the Rocket method; the teacher stopped taking it.

        :return: None
        """
        retire_method(self.session, lens=self.teacher, method_id=self.methods["rocket"])

    # -- months ------------------------------------------------------------

    def _open_month(self, day: dt.date) -> None:
        """On the 1st: cycles, the routine's next month, fees, costs.

        :param day: Today
        :return: None
        """
        if day.day != 1 or not self.batch_ids:
            return
        self._generate_fees()
        for batch_id in self.batch_ids.values():
            generate_sessions(self.session, today=day, batch_id=batch_id)
        for kid in self.kids:
            if kid.student_id is None:
                continue
            for key in kid.batches:
                self._plan_month(kid, key, day)
        self._plan_month_notices(day)

    def _plan_month_notices(self, day: dt.date) -> None:
        """Schedule a month's fee notices, reminders and spending.

        Called from the 1st, and from the first morning's set-up -- the
        1st's own event runs before any batch exists.

        :param day: The 1st
        :return: None
        """
        second_month = day == _month_start(self.start, -1)
        for spec in BATCHES:
            notice = day + dt.timedelta(days=spec.due_day - 4)
            withdrawn = second_month and spec.key == "C"
            self.at(
                _at(notice, "09:30"),
                partial(self._fee_notice, spec.key, spec.due_day, withdrawn=withdrawn),
            )
            self.at(
                _at(day + dt.timedelta(days=spec.due_day + 7), "20:30"),
                partial(self._remind, spec.key),
            )
        self._plan_expenses(day)
        if second_month:
            self.at(_at(day + dt.timedelta(days=20), "20:00"), self._raise_notes_fee)

    def _fee_notice(self, key: str, due_day: int, *, withdrawn: bool) -> None:
        """Post the month's fee notice; once, delete one posted by mistake.

        :param key: The batch
        :param due_day: Its due day
        :param withdrawn: Whether the teacher deletes it a few minutes later
        :return: None
        """
        note = self._announce(key, "fee_due", due_day=due_day)
        if withdrawn:
            self.at(
                self.clock.moment + dt.timedelta(minutes=7),
                lambda: delete_announcement(
                    self.session, lens=self.teacher, announcement_id=note
                ),
            )

    def _raise_notes_fee(self) -> None:
        """Charge batch C for printed lecture notes, an "other" fee.

        :return: None
        """
        day = self.clock.moment.date()
        fee = raise_extra_fee(
            self.session,
            lens=self.teacher,
            batch_id=self.batch_ids["C"],
            draft=FeeDraft(
                purpose="other",
                label="Printed lecture notes",
                exam_id=None,
                amount=Money(150),
                due_on=day + dt.timedelta(days=7),
                seat_amounts={},
                excluded=frozenset(),
                client_mutation_id=uuid.uuid4(),
            ),
            today=day,
        )
        self._plan_extra_fee_payments("C", fee.id, share_paying=0.5)

    def _generate_fees(self) -> None:
        """Run fee generation for today, as the daily job would.

        Generation is not owner-scoped: on a shared staging database it
        reaches other teachers' seats too, but only for periods already
        due, which the real daily job has generated -- so it inserts
        nothing there and every conflict is the success path.

        :return: None
        """
        generate_due_cycles(self.session, today=self.clock.moment.date())

    def _plan_month(self, kid: _Kid, key: str, day: dt.date) -> None:
        """Decide when and how this seat pays this month.

        :param kid: The student
        :param key: The batch
        :param day: The 1st, or the day they joined
        :return: None
        """
        spec = self.specs[key]
        if kid.fee == 0:
            return  # a free seat: charged nothing, so nothing to pay
        due = day.replace(day=spec.due_day)
        last_month = _month_start(self.today, 1)
        month_index = (day.year - self.start.year) * 12 + day.month - self.start.month
        behaviour = kid.payer
        if behaviour == "owes" and day >= last_month:
            return
        if kid.leaves is not None and day >= kid.leaves.replace(day=1):
            return

        rng = self.rng
        amount = "owed"
        if behaviour == "prompt":
            paid = due - dt.timedelta(days=rng.randint(0, 5))
        elif behaviour in ("late", "owes"):
            paid = due + dt.timedelta(days=rng.randint(2, 14))
        elif behaviour == "partial" and month_index in (0, 1):
            paid = due + dt.timedelta(days=rng.randint(0, 6))
            amount = "part"
        elif behaviour == "advance" and month_index == 1:
            paid = due - dt.timedelta(days=rng.randint(1, 4))
            amount = "two_months"
        elif behaviour == "cash_day":
            paid = due
        else:
            paid = due + dt.timedelta(days=rng.randint(-3, 6))
        paid = max(paid, day, kid.joins)

        if kid.app_user is not None and not kid.pending_guardian:
            moment = _at(paid, f"{rng.randint(19, 23)}:{rng.randint(0, 59):02d}")
            self.at(moment, lambda: self._pay_in_app(kid, key, amount, paid))
        else:
            self._pay_in_class(kid, key, amount, paid)

    def _class_on_or_after(self, key: str, day: dt.date) -> tuple[dt.date, dt.time]:
        """Find the batch's next class that has not ended yet.

        :param key: The batch
        :param day: The earliest day
        :return: That day and the class's end
        """
        for offset in range(15):
            candidate = day + dt.timedelta(days=offset)
            for slot in sorted(self.specs[key].slots, key=lambda s: s.end):
                if (
                    slot.weekday == candidate.weekday()
                    and candidate not in self.holidays
                    and _at(candidate, slot.end) > self.clock.moment
                ):
                    return candidate, slot.end
        return day + dt.timedelta(days=15), dt.time(21, 0)

    def _pay_in_class(self, kid: _Kid, key: str, amount: str, paid: dt.date) -> None:
        """Record cash a family hands over in class, as the teacher.

        Everyone paying cash around the due date pays at the same class,
        which is what gives several payments the same date.

        :param kid: The student
        :param key: The batch
        :param amount: ``owed``, ``part`` or ``two_months``
        :param paid: When they meant to pay
        :return: None
        """
        day, end = self._class_on_or_after(key, paid)
        moment = _at(day, end) + dt.timedelta(minutes=self.rng.randint(2, 15))

        def record() -> None:
            seat = kid.seats[key]
            owed = self._owed(key, seat)
            if not owed.is_positive():
                return
            value = self._amount(owed, kid, key, amount)
            short = value < owed
            record_received_payment(
                self.session,
                lens=self.teacher,
                enrollment_id=seat,
                payment=ReceivedPayment(
                    amount=value,
                    paid_on=day,
                    shortfall_disposition=(
                        ("waived" if kid.index % 2 else "carried") if short else None
                    ),
                    note=None,
                ),
                today=day,
            )

        self.at(moment, record)

    def _pay_in_app(self, kid: _Kid, key: str, amount: str, paid: dt.date) -> None:
        """Report a payment in the app as the family; schedule the review.

        Siblings sharing a guardian pay together, in the older child's
        event; the younger child's own event finds nothing owed.

        :param kid: The student
        :param key: The batch
        :param amount: ``owed``, ``part`` or ``two_months``
        :param paid: The day the money moved
        :return: None
        """
        payer, lens = self._family_lens(kid, key)
        if payer is None or lens is None:
            self._pay_in_class(kid, key, amount, self.clock.moment.date())
            return
        seats = [kid.seats[key]]
        if kid.app_user == "guardian":
            seats += [
                other.seats[key]
                for other in self.kids
                if other is not kid
                and other.guardian_account == kid.guardian_account
                and key in other.seats
                and not other.declined_guardian
            ]
        owed = [self._owed(key, seat) for seat in seats]
        if not any(value.is_positive() for value in owed):
            return
        seats = [s for s, value in zip(seats, owed, strict=True) if value.is_positive()]
        total = Money.sum(v for v in owed if v.is_positive())
        value = self._amount(total, kid, key, amount)
        method = kid.method if kid.method in self.methods else "bkash"
        bank = method == "bank"
        wrong = not self.rejected_once and kid.payer == "late" and not bank
        draft = PaymentDraft(
            enrollment_ids=tuple(seats),
            payment_method_id=self.methods[method],
            cash=False,
            amount=value,
            paid_on=paid,
            transaction_id=None if bank else self._transaction_id(method, wrong),
            from_account=f"DBBL A/C ending {self.rng.randint(1000, 9999)}"
            if bank
            else None,
            note=None if self.rng.random() < 0.8 else "Paid for this month.",
            client_mutation_id=uuid.uuid4(),
            purpose="monthly",
        )
        submission = submit_payment(self.session, lens=lens, draft=draft, today=paid)
        if wrong:
            self.rejected_once = True
        review = self.clock.moment + dt.timedelta(
            days=self.rng.choice((0, 1, 1, 2)), hours=self.rng.randint(0, 2)
        )
        review = max(review, self.clock.moment + dt.timedelta(minutes=20))
        if self.end - self.clock.moment < PENDING_WINDOW:
            return  # sent in the last day and a half: still awaiting review
        self.at(review, lambda: self._review(submission.id, kid, key, wrong, paid))

    def _review(
        self,
        submission_id: uuid.UUID,
        kid: _Kid,
        key: str,
        wrong: bool,
        paid: dt.date,
    ) -> None:
        """Approve a payment as the teacher, or reject a wrong reference.

        :param submission_id: The submission
        :param kid: The paying student
        :param key: The batch
        :param wrong: Whether its transaction id was mistyped
        :param paid: When the money moved, for the resubmission
        :return: None
        """
        if wrong:
            reject_submission(
                self.session,
                lens=self.teacher,
                submission_id=submission_id,
                note="Transaction ID not found in the bKash statement. Please check.",
            )
            again = self.clock.moment + dt.timedelta(hours=self.rng.randint(1, 12))
            self.at(again, lambda: self._pay_in_app(kid, key, "owed", paid))
            return
        submission = self.session.get_one(PaymentSubmission, submission_id)
        claims = (
            self.session.execute(
                sa.text(
                    "SELECT enrollment_id FROM payment_claim "
                    "WHERE payment_submission_id = :id ORDER BY enrollment_id"
                ),
                {"id": submission_id},
            )
            .scalars()
            .all()
        )
        owed = Money.sum(self._owed(key, seat) for seat in claims)
        received = submission.total_amount
        short, over = received < owed, received > owed
        first = claims[0] if len(claims) > 1 else None
        disposition: Disposition | None = None
        if short:
            disposition = "waived" if kid.index % 2 else "carried"
        approve_submission(
            self.session,
            lens=self.teacher,
            submission_id=submission_id,
            received=received,
            disposition=disposition,
            carried_by_enrollment_id=first if disposition == "carried" else None,
            credit_to_enrollment_id=first if over else None,
            note=None,
        )

    def _family_lens(
        self, kid: _Kid, key: str
    ) -> tuple[uuid.UUID | None, StudentLens | GuardianLens | None]:
        """Return the account paying for this seat in the app, if any.

        :param kid: The student
        :param key: The batch
        :return: The account and its lens, or Nones when nobody can pay
        """
        if kid.app_user == "student" and kid.student_account is not None:
            return kid.student_account, StudentLens(account_id=kid.student_account)
        if (
            kid.app_user == "guardian"
            and kid.guardian_account is not None
            and not kid.declined_guardian
        ):
            return kid.guardian_account, GuardianLens(
                account_id=kid.guardian_account, child_enrollment_id=kid.seats[key]
            )
        return None, None

    def _owed(self, key: str, seat: uuid.UUID) -> Money:
        """Read what a seat owes on its monthly fees now.

        :param key: The batch
        :param seat: The enrollment
        :return: The outstanding, never negative
        """
        target = resolve_target(
            self.session,
            purpose="monthly",
            extra_fee_id=None,
            batch_id=self.batch_ids[key],
        )
        return owed_for_target(self.session, target=target, enrollment_id=seat)

    def _amount(self, owed: Money, kid: _Kid, key: str, kind: str) -> Money:
        """Turn what is owed into what this family sends.

        :param owed: The outstanding
        :param kid: The student
        :param key: The batch
        :param kind: ``owed``, ``part`` or ``two_months``
        :return: The amount paid
        """
        if kind == "part":
            return Money(_round_down_100(_taka(owed) * 2 // 3))
        if kind == "two_months":
            fee = kid.fee if kid.fee is not None else self.specs[key].fee
            return owed + Money(fee)
        return owed

    def _transaction_id(self, method: str, wrong: bool) -> str:
        """Make a mobile-money reference in its service's shape.

        :param method: ``bkash`` or ``nagad``
        :param wrong: Whether it is mistyped
        :return: The reference
        """
        letters = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        length = 10 if method == "bkash" else 8
        reference = "".join(self.rng.choice(letters) for _ in range(length))
        return reference[:-2] if wrong else reference

    def _remind(self, key: str) -> None:
        """Remind every family in a batch that still owes.

        :param key: The batch
        :return: None
        """
        seats = (
            self.session.execute(
                sa.select(Enrollment.id).where(
                    Enrollment.batch_id == self.batch_ids[key]
                )
            )
            .scalars()
            .all()
        )
        owing = [seat for seat in seats if self._owed(key, seat).is_positive()]
        if owing:
            remind(self.session, lens=self.teacher, enrollment_ids=owing)

    def _plan_expenses(self, day: dt.date) -> None:
        """Schedule the month's spending.

        :param day: The 1st
        :return: None
        """
        rng = self.rng
        first_month = day.replace(day=1) == self.start.replace(day=1)

        def spend(on: dt.date, clock: str, draft: ExpenseDraft) -> None:
            def record() -> None:
                record_expense(self.session, lens=self.teacher, draft=draft, today=on)

            self.at(_at(on, clock), record)

        rent = ExpenseDraft(
            category="rent",
            what="Coaching room rent",
            amount=Money(8000),
            spent_on=day + dt.timedelta(days=1),
            payee="Landlord",
        )
        if first_month:
            self.at(_at(day + dt.timedelta(days=1), "11:00"), self._rent_typo)
        else:
            spend(day + dt.timedelta(days=1), "11:00", rent)
        spend(
            day + dt.timedelta(days=11),
            "18:10",
            ExpenseDraft(
                category="utilities",
                what="Electricity bill",
                amount=Money(rng.randint(850, 1450)),
                spent_on=day + dt.timedelta(days=11),
                note=f"Bill no. {rng.randint(100000, 999999)}",
            ),
        )
        spend(
            day + dt.timedelta(days=4),
            "17:40",
            ExpenseDraft(
                category="materials",
                what="Markers, duster and chalk",
                amount=Money(rng.choice((280, 350, 420))),
                spent_on=day + dt.timedelta(days=4),
                payee="Nilkhet stationery",
            ),
        )
        for offset in rng.sample(range(3, 27), 2):
            on = day + dt.timedelta(days=offset)
            spend(
                on,
                "13:00",
                ExpenseDraft(
                    category="transport",
                    what="Rickshaw and CNG to coaching",
                    amount=Money(rng.choice((120, 180, 250))),
                    spent_on=on,
                ),
            )
        cursor = day
        while cursor.month == day.month:
            if cursor.weekday() == WED:
                for key in self.batch_ids:
                    spend(
                        cursor,
                        "21:30",
                        ExpenseDraft(
                            category="exam_paper",
                            what="Weekly test question papers",
                            amount=Money(len(self.specs[key].subjects) * 20 * 4),
                            spent_on=cursor,
                            batch_id=self.batch_ids[key],
                            payee="Photocopy shop",
                        ),
                    )
            cursor += dt.timedelta(days=1)

    def _rent_typo(self) -> None:
        """Record the first rent with an extra zero, void it, re-enter it.

        :return: None
        """
        day = self.clock.moment.date()
        wrong = record_expense(
            self.session,
            lens=self.teacher,
            today=day,
            draft=ExpenseDraft(
                category="rent",
                what="Coaching room rent",
                amount=Money(80000),
                spent_on=day,
                payee="Landlord",
            ),
        )
        void_expense(
            self.session,
            lens=self.teacher,
            expense_id=wrong.id,
            reason="Typo: one zero too many",
        )
        record_expense(
            self.session,
            lens=self.teacher,
            today=day,
            draft=ExpenseDraft(
                category="rent",
                what="Coaching room rent",
                amount=Money(8000),
                spent_on=day,
                payee="Landlord",
            ),
        )

    # -- days and classes --------------------------------------------------

    def _open_day(self, day: dt.date) -> None:
        """Schedule the day's classes, tests and housekeeping.

        :param day: Today
        :return: None
        """
        for key, batch_id in self.batch_ids.items():
            rows = self.session.execute(
                sa.select(
                    ClassSession.id, ClassSession.start_time, ClassSession.end_time
                )
                .where(ClassSession.batch_id == batch_id, ClassSession.date == day)
                .order_by(ClassSession.start_time)
            ).all()
            for session_id, start, end in rows:
                slot = self._slot(key, day, start)
                if day in self.holidays:
                    self._cancel_ahead(key, session_id, day)
                    continue
                finish = (
                    end
                    or (dt.datetime.combine(day, start) + dt.timedelta(hours=1)).time()
                )
                self.at(
                    _at(day, start) - dt.timedelta(minutes=10),
                    partial(self._begin, key, session_id, slot),
                )
                self.at(
                    _at(day, finish) + dt.timedelta(minutes=3),
                    partial(self._hold, key, session_id, slot, day),
                )
            tomorrow = day + dt.timedelta(days=1)
            if (
                any(
                    s.subject == TEST and s.weekday == tomorrow.weekday()
                    for s in self.specs[key].slots
                )
                and tomorrow not in self.holidays
            ):
                self.at(_at(day, "21:00"), partial(self._set_tests, key, tomorrow))
        self._model_test_events(day)
        self._hartal_events(day)
        if day.weekday() == FRI:
            self.at(_at(day, "21:15"), self._read_inboxes)

    def _slot(self, key: str, day: dt.date, start: dt.time) -> _SlotSpec | None:
        """Find the routine slot a generated class came from.

        :param key: The batch
        :param day: Its date
        :param start: Its start
        :return: The slot, or None for an ad-hoc class
        """
        return next(
            (
                s
                for s in self.specs[key].slots
                if s.weekday == day.weekday() and s.start == start
            ),
            None,
        )

    def _cancel_ahead(self, key: str, session_id: uuid.UUID, day: dt.date) -> None:
        """Cancel a holiday class; the notice went out days before.

        :param key: The batch
        :param session_id: The class
        :param day: Its date
        :return: None
        """
        cancel_session(self.session, lens=self.teacher, session_id=session_id)
        first = min(self.holidays)
        if day == first:
            label = " and ".join(d.strftime("%d %B") for d in sorted(self.holidays))
            self._announce(key, "holiday", date=label)

    def _begin(self, key: str, session_id: uuid.UUID, slot: _SlotSpec | None) -> None:
        """Before class: the teacher picks the subject on screen.

        :param key: The batch
        :param session_id: The class
        :param slot: Its routine slot
        :return: None
        """
        if self.session.get_one(ClassSession, session_id).status == "cancelled":
            return
        subject = slot.subject if slot is not None else "Math"
        if subject == TEST:
            subject = "Math" if self.specs[key].subjects == ("Math",) else ""
        if subject:
            write_session_subject(
                self.session,
                lens=self.teacher,
                session_id=session_id,
                batch_subject_id=self.subject_ids[(key, subject)],
            )

    def _hold(
        self, key: str, session_id: uuid.UUID, slot: _SlotSpec | None, day: dt.date
    ) -> None:
        """After class: attendance, then the topic.

        :param key: The batch
        :param session_id: The class
        :param slot: Its routine slot, or None for an ad-hoc class
        :param day: Its date
        :return: None
        """
        row = self.session.get_one(ClassSession, session_id)
        if row.status == "cancelled":
            return
        recent = (self.today - day).days < 10
        if recent and self.unrecorded_left and self.rng.random() < 0.08:
            self.unrecorded_left -= 1  # the teacher forgot this one
            return
        subject = slot.subject if slot is not None else "Math"
        is_test = subject == TEST
        by_seat = {
            kid_seat: kid for kid in self.kids for kid_seat in kid.seats.values()
        }
        roster = session_roster(self.session, lens=self.teacher, session_id=session_id)
        marks = []
        for seat in roster:
            kid = by_seat.get(seat.enrollment_id)
            rate = kid.present_rate if kid is not None else 0.9
            if is_test:
                rate = min(0.99, rate + 0.03)
            marks.append(
                SeatMark(
                    enrollment_id=seat.enrollment_id, present=self.rng.random() < rate
                )
            )
        result = submit_roster(
            self.session,
            lens=self.teacher,
            session_id=session_id,
            base_version=row.attendance_version,
            client_mutation_id=uuid.uuid4(),
            seats=marks,
            composed_at=self.clock.moment,
        )
        del result
        if is_test:
            self.test_rosters[(key, day)] = {m.enrollment_id: m.present for m in marks}
            topic = "Weekly test: " + " and ".join(self.specs[key].subjects)
            notes = None
        elif slot is None:
            topic, notes = "Extra class: model test revision", None
        else:
            topic = self._next_topic(key, subject)
            self.covered[(key, subject, _week_of(day))].append(topic)
            notes = self.rng.choice(SESSION_NOTES) if self.rng.random() < 0.25 else None
        self.session.refresh(row)
        write_topic(
            self.session,
            lens=self.teacher,
            session_id=session_id,
            base_version=row.topic_version,
            client_mutation_id=uuid.uuid4(),
            topic=topic,
            notes=notes,
            notes_supplied=notes is not None,
            composed_at=self.clock.moment,
        )
        if is_test:
            self.at(
                self.clock.moment + dt.timedelta(hours=3),
                lambda: self._mark_tests(key, day),
            )

    def _next_topic(self, key: str, subject: str) -> str:
        """Take the next topic of a batch's subject, wrapping at the end.

        :param key: The batch
        :param subject: The subject
        :return: The topic
        """
        topics = SYLLABUS[subject]
        position = self.syllabus_at[(key, subject)]
        self.syllabus_at[(key, subject)] = position + 1
        return topics[position % len(topics)]

    # -- tests -------------------------------------------------------------

    def _set_tests(self, key: str, test_day: dt.date) -> None:
        """Create the weekly tests the evening before, one per subject.

        :param key: The batch
        :param test_day: The Thursday
        :return: None
        """
        week = _week_of(test_day)
        for subject in self.specs[key].subjects:
            topics = list(self.covered.get((key, subject, week), ()))
            if not topics:
                continue
            exam = create_exam(
                self.session,
                lens=self.teacher,
                batch_id=self.batch_ids[key],
                batch_subject_id=self.subject_ids[(key, subject)],
                title=f"Weekly Test - {subject} ({test_day.strftime('%d %b')})",
                date=test_day,
                total_marks=WEEKLY_TOTAL,
                topics=topics,
            )
            self.exams.append((exam.exam_id, key, test_day))

    def _mark_tests(self, key: str, test_day: dt.date) -> None:
        """Enter the day's results; publish tomorrow unless the latest.

        The latest test day is still being marked: one batch's results
        are entered but unpublished, another's only half entered.

        :param key: The batch
        :param test_day: The Thursday
        :return: None
        """
        attended = self.test_rosters.get((key, test_day), {})
        latest = (self.today - test_day).days < 7
        for exam_id, exam_key, day in self.exams:
            if exam_key != key or day != test_day:
                continue
            exam = self.session.get_one(Exam, exam_id)
            if exam.cancelled_at is not None:
                continue
            seats = list(attended.items())
            if latest and key == "B":
                seats = seats[: len(seats) // 2]
            self._enter(exam_id, seats, exam.total_marks)
            if not latest or key == "C":
                self.at(
                    _at(test_day + dt.timedelta(days=1), "10:00"),
                    partial(self._publish, exam_id),
                )

    def _enter(
        self, exam_id: uuid.UUID, seats: list[tuple[uuid.UUID, bool]], total: int
    ) -> None:
        """Enter a mark, or absent, for each seat that sat or missed it.

        :param exam_id: The exam
        :param seats: Each seat and whether it was present
        :param total: The exam's total
        :return: None
        """
        by_seat = {seat: kid for kid in self.kids for seat in kid.seats.values()}
        for seat, present in seats:
            kid = by_seat.get(seat)
            if not present or kid is None:
                record_mark(
                    self.session,
                    lens=self.teacher,
                    exam_id=exam_id,
                    enrollment_id=seat,
                    result_state="absent",
                    marks=None,
                )
                continue
            score = min(1.0, max(0.05, self.rng.gauss(kid.ability, 0.12))) * total
            record_mark(
                self.session,
                lens=self.teacher,
                exam_id=exam_id,
                enrollment_id=seat,
                result_state="marked",
                marks=round(score * 2) / 2,
            )

    def _publish(self, exam_id: uuid.UUID) -> None:
        """Publish an exam; now and then correct one mark the day after.

        :param exam_id: The exam
        :return: None
        """
        publish_exam(self.session, lens=self.teacher, exam_id=exam_id)
        if self.rng.random() < 0.12:
            self.at(
                self.clock.moment + dt.timedelta(days=1, hours=2),
                lambda: self._correct(exam_id),
            )

    def _correct(self, exam_id: uuid.UUID) -> None:
        """Correct one mark a student pointed out was mis-added.

        :param exam_id: The exam
        :return: None
        """
        live = self.session.execute(
            sa.select(Mark.enrollment_id, Mark.marks, Exam.total_marks)
            .join(Exam, Exam.id == Mark.exam_id)
            .where(
                Mark.exam_id == exam_id,
                Mark.superseded_by_id.is_(None),
                Mark.result_state == "marked",
                Mark.marks < Exam.total_marks - 1,
            )
            .limit(1)
        ).first()
        if live is not None:
            record_mark(
                self.session,
                lens=self.teacher,
                exam_id=exam_id,
                enrollment_id=live[0],
                result_state="marked",
                marks=(live[1] or 0) + 1,
            )

    def _hartal_events(self, day: dt.date) -> None:
        """One Thursday, a hartal: batch C's class and test are called off.

        :param day: Today
        :return: None
        """
        thursday = self.hartal_week + dt.timedelta(days=(THU - SAT) % 7)
        if day != thursday or day in self.holidays:
            return

        def call_off() -> None:
            for exam_id, key, exam_day in self.exams:
                if key == "C" and exam_day == day:
                    cancel_exam(
                        self.session,
                        lens=self.teacher,
                        exam_id=exam_id,
                        reason="Hartal: the test moves to next week",
                    )
            rows = (
                self.session.execute(
                    sa.select(ClassSession.id).where(
                        ClassSession.batch_id == self.batch_ids["C"],
                        ClassSession.date == day,
                    )
                )
                .scalars()
                .all()
            )
            for session_id in rows:
                cancel_session(self.session, lens=self.teacher, session_id=session_id)
            note = self._announce("C", "holiday", date=day.strftime("%d %B"))
            edit_announcement(
                self.session,
                lens=self.teacher,
                announcement_id=note,
                body=(
                    f"Hartal on {day.strftime('%d %B')}: no class and no test "
                    "today. The test moves to next week."
                ),
            )

        self.at(_at(day, "06:45"), call_off)

    def _model_test_events(self, day: dt.date) -> None:
        """Around the model test: notice, fee, extra class, test, results.

        :param day: Today
        :return: None
        """
        if self.model_day is None:
            return
        if day == self.model_day - dt.timedelta(days=8):
            self.at(_at(day, "21:00"), self._set_model_tests)
        if day == self.model_day - dt.timedelta(days=7):
            self.at(_at(day, "10:00"), self._extra_class)
        if day == self.model_day:
            self.at(_at(day, "13:00"), self._sit_model_tests)
        if day == self.model_day + dt.timedelta(days=1):
            self.at(_at(day, "16:00"), self._mark_model_tests)

    def _set_model_tests(self) -> None:
        """Create the model tests and raise their exam fee.

        :return: None
        """
        assert self.model_day is not None  # noqa: S101  scheduled only then
        for key, spec in self.specs.items():
            linked: uuid.UUID | None = None
            for subject in spec.subjects:
                covered = [
                    topic
                    for (k, s, _w), topics in self.covered.items()
                    if k == key and s == subject
                    for topic in topics
                ]
                exam = create_exam(
                    self.session,
                    lens=self.teacher,
                    batch_id=self.batch_ids[key],
                    batch_subject_id=self.subject_ids[(key, subject)],
                    title=f"Model Test - {subject}",
                    date=self.model_day,
                    total_marks=MODEL_TOTAL,
                    topics=list(dict.fromkeys(covered))[:12],
                )
                self.exams.append((exam.exam_id, f"model:{key}", self.model_day))
                linked = linked or exam.exam_id
            free = {
                kid.seats[key] for kid in self.kids if kid.fee == 0 and key in kid.seats
            }
            fee = raise_extra_fee(
                self.session,
                lens=self.teacher,
                batch_id=self.batch_ids[key],
                draft=FeeDraft(
                    purpose="exam",
                    label="Model test fee",
                    exam_id=linked,
                    amount=Money(200 if key == "C" else 300),
                    due_on=self.model_day,
                    seat_amounts={s: Money(0) for s in free},
                    excluded=frozenset(),
                    client_mutation_id=uuid.uuid4(),
                ),
            )
            self._announce(key, "model_test", date=self.model_day.strftime("%d %B"))
            self.at(
                self.clock.moment + dt.timedelta(minutes=30),
                partial(self._print_model_test, fee.id, key),
            )
            self._plan_extra_fee_payments(key, fee.id)

    def _print_model_test(self, fee_id: uuid.UUID, key: str) -> None:
        """Record the model test's printing against its fee.

        :param fee_id: The exam fee
        :param key: The batch
        :return: None
        """
        record_expense(
            self.session,
            lens=self.teacher,
            draft=ExpenseDraft(
                category="printing",
                what="Model test question papers",
                amount=Money(650),
                spent_on=self.clock.moment.date(),
                batch_id=self.batch_ids[key],
                extra_fee_id=fee_id,
                payee="Photocopy shop",
            ),
        )

    def _plan_extra_fee_payments(
        self, key: str, fee_id: uuid.UUID, *, share_paying: float = 0.75
    ) -> None:
        """Most families pay an extra fee in class within a week.

        :param key: The batch
        :param fee_id: The fee
        :param share_paying: How many pay at all; the rest still owe it
        :return: None
        """
        for kid in self.kids:
            if key not in kid.seats or kid.fee == 0 or self.rng.random() > share_paying:
                continue
            day, end = self._class_on_or_after(
                key,
                self.clock.moment.date() + dt.timedelta(days=self.rng.randint(1, 6)),
            )
            seat = kid.seats[key]

            def pay(seat: uuid.UUID = seat, day: dt.date = day) -> None:
                target = resolve_target(
                    self.session,
                    purpose="extra",
                    extra_fee_id=fee_id,
                    batch_id=self.batch_ids[key],
                )
                owed = owed_for_target(self.session, target=target, enrollment_id=seat)
                if owed.is_positive():
                    record_received_payment(
                        self.session,
                        lens=self.teacher,
                        enrollment_id=seat,
                        payment=ReceivedPayment(
                            amount=owed,
                            paid_on=day,
                            purpose="extra",
                            extra_fee_id=fee_id,
                        ),
                        today=day,
                    )

            self.at(_at(day, end) + dt.timedelta(minutes=20), pay)

    def _extra_class(self) -> None:
        """Hold an extra Friday revision class for the morning batch.

        :return: None
        """
        day = self.clock.moment.date()
        self._announce("A", "extra_class", date=day.strftime("%d %B"))
        row = create_ad_hoc_session(
            self.session,
            lens=self.teacher,
            batch_id=self.batch_ids["A"],
            date=day,
            start_time=dt.time(15, 0),
            end_time=dt.time(16, 30),
            batch_subject_id=self.subject_ids[("A", "Math")],
        )
        self.at(_at(day, "16:33"), lambda: self._hold("A", row.session_id, None, day))

    def _sit_model_tests(self) -> None:
        """Note who sat the model tests, from the day's attendance.

        :return: None
        """
        assert self.model_day is not None  # noqa: S101  scheduled only then
        for key in self.batch_ids:
            seats = (
                self.session.execute(
                    sa.select(Enrollment.id).where(
                        Enrollment.batch_id == self.batch_ids[key],
                        sa.or_(
                            Enrollment.joined_on.is_(None),
                            Enrollment.joined_on <= self.model_day,
                        ),
                        sa.or_(
                            Enrollment.inactive_from.is_(None),
                            Enrollment.inactive_from > self.model_day,
                        ),
                    )
                )
                .scalars()
                .all()
            )
            self.test_rosters[(f"model:{key}", self.model_day)] = {
                seat: self.rng.random() < 0.93 for seat in seats
            }

    def _mark_model_tests(self) -> None:
        """Enter and publish the model tests.

        :return: None
        """
        assert self.model_day is not None  # noqa: S101  scheduled only then
        for exam_id, key, day in self.exams:
            if not key.startswith("model:") or day != self.model_day:
                continue
            attended = self.test_rosters.get((key, day), {})
            self._enter(exam_id, list(attended.items()), MODEL_TOTAL)
            self.at(
                self.clock.moment + dt.timedelta(hours=18),
                partial(self._publish, exam_id),
            )
        self.at(self.clock.moment + dt.timedelta(hours=19), self._results_notice)

    def _results_notice(self) -> None:
        """Tell every batch the model test results are out.

        :return: None
        """
        for key in self.batch_ids:
            self._announce(key, "results")

    # -- notices and inboxes -------------------------------------------------

    def _announce(self, key: str, which: str, **values: object) -> uuid.UUID:
        """Post one of :data:`ANNOUNCEMENTS` to a batch.

        :param key: The batch
        :param which: The notice
        :param values: Its placeholders
        :return: The announcement
        """
        body = ANNOUNCEMENTS[which].format(batch=self.specs[key].name, **values)
        row = post_announcement(
            self.session, lens=self.teacher, batch_id=self.batch_ids[key], body=body
        )
        self.announcements.append(row.announcement_id)
        return row.announcement_id

    def _read_inboxes(self) -> None:
        """Most families open the app at the end of the week.

        :return: None
        """
        accounts = {
            account
            for kid in self.kids
            for account in (kid.student_account, kid.guardian_account)
            if account is not None
        }
        for account in sorted(accounts):
            if self.rng.random() < 0.7:
                mark_read(self.session, account_id=account, now=self.clock.moment)

    def _last_minute_payments(self) -> None:
        """Report a few payments the teacher has not reached yet.

        Deliberate rather than left to chance, so the review queue is
        never empty: whether a family happened to pay in the last day is
        otherwise up to the random seed.

        :return: None
        """
        reported = 0
        for kid in self.kids:
            if reported == 3:
                return
            for key in kid.batches:
                _payer, lens = self._family_lens(kid, key)
                if lens is None or not self._owed(key, kid.seats[key]).is_positive():
                    continue
                if self._has_pending(kid.seats[key]):
                    continue
                self._pay_in_app(kid, key, "owed", self.today)
                reported += 1
                break

    def _has_pending(self, seat: uuid.UUID) -> bool:
        """Whether a seat already has a payment waiting for review.

        :param seat: The enrollment
        :return: True when one is pending
        """
        return bool(
            self.session.execute(
                sa.text(
                    "SELECT 1 FROM payment_claim WHERE enrollment_id = :e "
                    "AND status = 'pending' LIMIT 1"
                ),
                {"e": seat},
            ).first()
        )

    def _plan_upcoming_topics(self) -> None:
        """At the end: the teacher plans the next class of each batch.

        :return: None
        """
        for key, batch_id in self.batch_ids.items():
            upcoming = (
                self.session.execute(
                    sa.select(ClassSession)
                    .where(
                        ClassSession.batch_id == batch_id,
                        ClassSession.status == "scheduled",
                        ClassSession.date > self.today,
                    )
                    .order_by(ClassSession.date, ClassSession.start_time)
                    .limit(4)
                )
                .scalars()
                .all()
            )
            for row in upcoming:
                slot = self._slot(key, row.date, row.start_time)
                if slot is None or slot.subject == TEST:
                    continue
                position = self.syllabus_at[(key, slot.subject)]
                topics = SYLLABUS[slot.subject]
                write_topic(
                    self.session,
                    lens=self.teacher,
                    session_id=row.id,
                    base_version=row.topic_version,
                    client_mutation_id=uuid.uuid4(),
                    topic=topics[position % len(topics)],
                    plan=True,
                    notes_supplied=False,
                )
                self.syllabus_at[(key, slot.subject)] = position + 1
                break

    # -- the report --------------------------------------------------------

    def report(self) -> SeedReport:
        """Count what the run wrote, from the database.

        :return: The report
        """
        owner = self.teacher.owner_id
        batches = sa.select(Batch.id).where(Batch.owner_id == owner)
        seats = sa.select(Enrollment.id).where(Enrollment.batch_id.in_(batches))
        sessions = sa.select(ClassSession.id).where(ClassSession.batch_id.in_(batches))

        def count(statement: sa.Select[int]) -> int:
            value = self.session.execute(statement).scalar_one()
            return int(value)

        def rows(model: type, *where: sa.ColumnElement[bool]) -> int:
            return count(sa.select(sa.func.count()).select_from(model).where(*where))

        counts = {
            "batches": rows(Batch, Batch.owner_id == owner),
            "seats": rows(Enrollment, Enrollment.id.in_(seats)),
            "students": len({kid.student_id for kid in self.kids if kid.student_id}),
            "family_accounts": len(
                {
                    a
                    for kid in self.kids
                    for a in (kid.student_account, kid.guardian_account)
                    if a
                }
            ),
            "sessions": rows(ClassSession, ClassSession.id.in_(sessions)),
            "sessions_held": rows(
                ClassSession,
                ClassSession.id.in_(sessions),
                ClassSession.status == "held",
            ),
            "attendance_rows": rows(Attendance, Attendance.session_id.in_(sessions)),
            "exams": rows(Exam, Exam.batch_id.in_(batches)),
            "marks": rows(Mark, Mark.enrollment_id.in_(seats)),
            "fee_cycles": rows(FeeCycle, FeeCycle.enrollment_id.in_(seats)),
            "ledger_entries": rows(
                LedgerEntryRow, LedgerEntryRow.enrollment_id.in_(seats)
            ),
            "payment_submissions": rows(
                PaymentSubmission, PaymentSubmission.batch_id.in_(batches)
            ),
            "payments_pending_review": rows(
                PaymentSubmission,
                PaymentSubmission.batch_id.in_(batches),
                PaymentSubmission.status == "pending",
            ),
            "seats_owing_last_month": self._owing_last_month(),
            "extra_fees": rows(ExtraFee, ExtraFee.batch_id.in_(batches)),
            "expenses": rows(Expense, Expense.owner_id == owner),
            "announcements": rows(Announcement, Announcement.batch_id.in_(batches)),
            "reminders": rows(ReminderEvent, ReminderEvent.enrollment_id.in_(seats)),
            "notifications": rows(Notification, Notification.enrollment_id.in_(seats)),
        }
        logins: list[dict[str, str]] = []
        for kid in self.kids:
            for role, account, phone in (
                ("guardian", kid.guardian_account, kid.guardian_phone),
                ("student", kid.student_account, kid.student_phone),
            ):
                if account is not None and phone and len(logins) < 6:
                    if any(entry["phone"] == phone for entry in logins):
                        continue
                    answered = "accepted"
                    if role == "guardian" and kid.pending_guardian:
                        answered = "not yet accepted"
                    elif role == "guardian" and kid.declined_guardian:
                        answered = "declined"
                    logins.append(
                        {"phone": phone, "role": role, "of": kid.name, "seat": answered}
                    )
        return SeedReport(
            owner_id=owner,
            history_from=self.start,
            history_to=self.end,
            counts=counts,
            family_logins=logins,
        )

    def _owing_last_month(self) -> int:
        """Count seats whose last month still shows a balance.

        :return: How many seats
        """
        period = _month_start(self.today, 1).strftime("%Y-%m")
        return sum(
            1
            for kid in self.kids
            for seat in kid.seats.values()
            if derive_for_enrollment(self.session, seat)
            .per_cycle.get(period, Money.ZERO)
            .is_positive()
        )
