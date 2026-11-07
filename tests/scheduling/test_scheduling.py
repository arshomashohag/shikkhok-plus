"""Scheduling at a centre: rooms, assignment, overrides, swaps, clashes [0024].

Written before the code, from the centre design's section 4:

* A weekly slot carries a teacher and a room; generation copies both into
  each class.
* Changing a slot's teacher or room moves its future, not-yet-held classes
  that follow the slot, and leaves held, cancelled and overridden ones as
  they are [BR1.2, amended].
* A manager can set one class's teacher or room alone, or swap the
  teachers of two classes.
* A teacher or a room cannot be double-booked; the database refuses it,
  and the refusal names the class it clashes with.
* Only a live member of this centre can be assigned, and only this
  centre's rooms; a solo tutor's schedule takes neither.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import OwnerMember, ScheduleSlot
from app.db.models import Session as ClassSession
from app.local_time import bangladesh_today
from tests.accounts.signup_support import sign_up
from tests.batches.conftest import make_teacher
from tests.conftest import bearer

ADDRESS = {
    "address_house": "House 12",
    "address_road": "Road 5",
    "address_city": "Dhaka",
    "address_postcode": "1205",
}

#: A weekday that is in the future this week or next, so the horizon
#: always holds at least one class on it after today.
TOMORROW = bangladesh_today() + dt.timedelta(days=1)
WEEKDAY = TOMORROW.weekday()


def _phone() -> str:
    """Generate a unique number.

    :return: A number in international form
    """
    return f"+88017{uuid.uuid4().int % 10**8:08d}"


class Centre:
    """A signed-up centre, its manager, and helpers to drive it.

    :ivar client: The test client
    :ivar session: An arranging session
    :ivar manager: The manager's account
    :ivar owner_id: The centre
    """

    def __init__(self, client: TestClient, session: Session) -> None:
        """Sign a centre up.

        :param client: The test client
        :param session: An arranging session
        """
        self.client = client
        self.session = session
        # Form and code: the account is created at verify [C-07].
        self.manager = sign_up(
            client,
            {
                "phone": _phone(),
                "role": "coaching",
                "self_name": "Rina",
                "centre_name": "Udoy Coaching",
                **ADDRESS,
            },
        )
        me = client.get("/v1/me", headers=self.headers()).json()
        self.owner_id = uuid.UUID(me["workspaces"][0]["owner_id"])

    def headers(self) -> dict[str, str]:
        """Authorize as the manager.

        :return: The headers
        """
        return bearer(self.session, self.manager)

    def teacher(self, decision: str = "accepted", revoked: bool = False) -> uuid.UUID:
        """Arrange a teacher membership.

        :param decision: Its decision
        :param revoked: Whether it has ended
        :return: The membership id
        """
        now = dt.datetime.now(tz=dt.UTC)
        member = OwnerMember(
            owner_id=self.owner_id,
            account_id=None,
            invited_phone=_phone(),
            display_name=f"Teacher {uuid.uuid4().hex[:4]}",
            role="teacher",
            decision=decision,
            created_at=now,
            revoked_at=now if revoked else None,
        )
        self.session.add(member)
        self.session.commit()
        return member.id

    def room(self, name: str) -> uuid.UUID:
        """Add a room through the API.

        :param name: Its name
        :return: The room id
        """
        response = self.client.post(
            "/v1/centre/rooms", json={"name": name}, headers=self.headers()
        )
        assert response.status_code == 201, response.text
        return uuid.UUID(response.json()["room_id"])

    def batch(self, name: str) -> uuid.UUID:
        """Create a batch in the centre.

        :param name: Its name
        :return: The batch id
        """
        response = self.client.post(
            "/v1/batches",
            json={"name": name, "subjects": ["Physics"]},
            headers=self.headers(),
        )
        assert response.status_code == 201, response.text
        return uuid.UUID(response.json()["id"])

    def schedule(self, batch_id: uuid.UUID, *slots: dict[str, object]) -> object:
        """Set a batch's weekly schedule.

        :param batch_id: The batch
        :param slots: The slots
        :return: The response
        """
        return self.client.put(
            f"/v1/batches/{batch_id}/schedule",
            json={"slots": list(slots)},
            headers=self.headers(),
        )


def _slot(
    teacher: uuid.UUID | None = None,
    room: uuid.UUID | None = None,
    start: str = "16:00",
    end: str = "17:00",
    **extra: object,
) -> dict[str, object]:
    """Build one wire slot on the test weekday.

    :param teacher: The teacher membership, or None
    :param room: The room, or None
    :param start: Start time
    :param end: End time
    :param extra: Fields overriding the defaults
    :return: The slot
    """
    slot: dict[str, object] = {"weekday": WEEKDAY, "start_time": start, "end_time": end}
    if teacher is not None:
        slot["teacher_member_id"] = str(teacher)
    if room is not None:
        slot["room_id"] = str(room)
    slot.update(extra)
    return slot


def _future(session: Session, batch_id: uuid.UUID) -> list[ClassSession]:
    """Read a batch's classes from tomorrow on, soonest first.

    :param session: A session to read through
    :param batch_id: The batch
    :return: The classes
    """
    session.expire_all()
    return list(
        session.scalars(
            sa.select(ClassSession)
            .where(ClassSession.batch_id == batch_id, ClassSession.date >= TOMORROW)
            .order_by(ClassSession.date)
        )
    )


def _code(response: object) -> str:
    """Read an error code.

    :param response: The response
    :return: The code
    """
    code: str = response.json()["error"]["code"]  # type: ignore[attr-defined]
    return code


@pytest.fixture
def centre(api_client: TestClient, owner_session: Session) -> Centre:
    """Sign up a centre for one test.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: The centre
    """
    return Centre(api_client, owner_session)


# -------------------------------------------------------------------- rooms


def test_a_centre_names_its_rooms_once_each(centre: Centre) -> None:
    """Rooms are listed by name; a live name cannot be used twice."""
    centre.room("Room 1")
    centre.room("Lab")
    again = centre.client.post(
        "/v1/centre/rooms", json={"name": "room 1"}, headers=centre.headers()
    )
    assert again.status_code == 409, again.text
    assert _code(again) == "ROOM_NAME_TAKEN"
    listed = centre.client.get("/v1/centre/rooms", headers=centre.headers()).json()
    assert [r["name"] for r in listed] == ["Lab", "Room 1"]


def test_an_archived_room_is_no_longer_offered_and_its_name_frees(
    centre: Centre,
) -> None:
    """Archiving keeps the room on old classes and frees the name."""
    room = centre.room("Room 1")
    archived = centre.client.patch(
        f"/v1/centre/rooms/{room}", json={"archived": True}, headers=centre.headers()
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived"] is True
    centre.room("Room 1")


# ---------------------------------------------------------- slot assignment


def test_a_slots_teacher_and_room_reach_every_class_generated_from_it(
    centre: Centre,
) -> None:
    """Generation copies the assignment into each class."""
    teacher, room = centre.teacher(), centre.room("Room 1")
    batch = centre.batch("Class 9")
    response = centre.schedule(batch, _slot(teacher, room))
    assert response.status_code == 200, response.text
    assert response.json()[0]["teacher_member_id"] == str(teacher)

    classes = _future(centre.session, batch)
    assert classes
    assert {(c.teacher_member_id, c.room_id, c.assignment_source) for c in classes} == {
        (teacher, room, "slot")
    }


def test_resaving_a_schedule_without_assignment_keeps_it(centre: Centre) -> None:
    """A client that sends only times does not clear the teacher."""
    teacher = centre.teacher()
    batch = centre.batch("Class 9")
    centre.schedule(batch, _slot(teacher))
    resaved = centre.schedule(batch, _slot())
    assert resaved.status_code == 200, resaved.text
    assert resaved.json()[0]["teacher_member_id"] == str(teacher)

    cleared = centre.schedule(batch, _slot(teacher_member_id=None))
    assert cleared.json()[0]["teacher_member_id"] is None


def test_only_a_live_member_and_this_centres_room_can_be_assigned(
    api_client: TestClient, owner_session: Session, centre: Centre
) -> None:
    """A stranger's membership or room, or a revoked one, is refused."""
    batch = centre.batch("Class 9")
    other = Centre(api_client, owner_session)
    for slot, code in (
        (_slot(other.teacher()), "SCHEDULE_TEACHER_UNKNOWN"),
        (_slot(centre.teacher(revoked=True)), "SCHEDULE_TEACHER_UNKNOWN"),
        (_slot(centre.teacher(decision="declined")), "SCHEDULE_TEACHER_UNKNOWN"),
        (_slot(room=other.room("Theirs")), "SCHEDULE_ROOM_UNKNOWN"),
    ):
        response = centre.schedule(batch, slot)
        assert response.status_code == 400, (slot, response.text)
        assert _code(response) == code


def test_a_solo_tutor_cannot_assign_teachers_or_rooms(
    api_client: TestClient, owner_session: Session, centre: Centre
) -> None:
    """A solo schedule takes neither field; it works exactly as before."""
    tutor = make_teacher(owner_session)
    headers = bearer(owner_session, tutor.account_id)
    plain = api_client.put(
        f"/v1/batches/{tutor.batch_id}/schedule",
        json={"slots": [_slot()]},
        headers=headers,
    )
    assert plain.status_code == 200, plain.text
    assigned = api_client.put(
        f"/v1/batches/{tutor.batch_id}/schedule",
        json={"slots": [_slot(centre.teacher())]},
        headers=headers,
    )
    assert assigned.status_code == 409, assigned.text
    assert _code(assigned) == "NOT_A_CENTRE"


def test_reassigning_a_slot_moves_only_its_future_unheld_followers(
    centre: Centre,
) -> None:
    """Held and overridden classes keep the teacher they had."""
    first, second, substitute = centre.teacher(), centre.teacher(), centre.teacher()
    batch = centre.batch("Class 9")
    centre.schedule(batch, _slot(first))
    classes = _future(centre.session, batch)
    assert len(classes) >= 2
    held, overridden, *rest = classes
    centre.session.execute(
        sa.update(ClassSession).where(ClassSession.id == held.id).values(status="held")
    )
    centre.session.commit()
    response = centre.client.post(
        f"/v1/sessions/{overridden.id}/assignment",
        json={"teacher_member_id": str(substitute), "room_id": None},
        headers=centre.headers(),
    )
    assert response.status_code == 200, response.text

    centre.schedule(batch, _slot(second))

    after = {c.id: c for c in _future(centre.session, batch)}
    assert after[held.id].teacher_member_id == first
    assert after[overridden.id].teacher_member_id == substitute
    assert after[overridden.id].assignment_source == "override"
    assert {after[c.id].teacher_member_id for c in rest} <= {second}


# ------------------------------------------------------------------ clashes


def test_a_teacher_cannot_be_given_two_weekly_classes_at_once(centre: Centre) -> None:
    """The second batch's overlapping slot is refused, naming the first."""
    teacher = centre.teacher()
    first, second = centre.batch("Class 9"), centre.batch("Class 10")
    assert centre.schedule(first, _slot(teacher)).status_code == 200  # type: ignore[attr-defined]
    clash = centre.schedule(second, _slot(teacher, start="16:30", end="17:30"))
    assert clash.status_code == 409, clash.text  # type: ignore[attr-defined]
    assert _code(clash) == "CLASS_CLASH"
    details = clash.json()["error"]["details"]  # type: ignore[attr-defined]
    assert (details["batch"], details["with"]) == ("Class 9", "teacher")
    assert (
        centre.session.scalar(
            sa.select(sa.func.count())
            .select_from(ScheduleSlot)
            .where(ScheduleSlot.batch_id == second)
        )
        == 0
    )


def test_a_room_cannot_hold_two_classes_at_once(centre: Centre) -> None:
    """Same for a room, and back-to-back classes are not a clash."""
    room = centre.room("Room 1")
    first, second = centre.batch("Class 9"), centre.batch("Class 10")
    centre.schedule(first, _slot(room=room))
    clash = centre.schedule(second, _slot(room=room))
    assert clash.status_code == 409, clash.text  # type: ignore[attr-defined]
    assert clash.json()["error"]["details"]["with"] == "room"  # type: ignore[attr-defined]
    after = centre.schedule(second, _slot(room=room, start="17:00", end="18:00"))
    assert after.status_code == 200, after.text  # type: ignore[attr-defined]


def test_an_override_into_a_clash_is_refused(centre: Centre) -> None:
    """Substituting a teacher who is already teaching then is refused."""
    busy, other = centre.teacher(), centre.teacher()
    first, second = centre.batch("Class 9"), centre.batch("Class 10")
    centre.schedule(first, _slot(busy))
    centre.schedule(second, _slot(other))
    target = _future(centre.session, second)[0]
    response = centre.client.post(
        f"/v1/sessions/{target.id}/assignment",
        json={"teacher_member_id": str(busy), "room_id": None},
        headers=centre.headers(),
    )
    assert response.status_code == 409, response.text
    assert _code(response) == "CLASS_CLASH"


def test_the_database_refuses_a_double_booking_the_service_did_not_see(
    centre: Centre, restricted_session: Session
) -> None:
    """The exclusion constraint is the guarantee, not the pre-check."""
    teacher = centre.teacher()
    first, second = centre.batch("Class 9"), centre.batch("Class 10")
    centre.schedule(first, _slot(teacher))
    taken = _future(centre.session, first)[0]
    restricted_session.add(
        ClassSession(
            batch_id=second,
            date=taken.date,
            start_time=dt.time(16, 30),
            end_time=dt.time(17, 30),
            status="scheduled",
            origin="ad_hoc",
            attendance_version=0,
            topic_version=0,
            created_at=dt.datetime.now(tz=dt.UTC),
            teacher_member_id=teacher,
            assignment_source="override",
        )
    )
    with pytest.raises(sa.exc.IntegrityError):
        restricted_session.commit()
    restricted_session.rollback()


# ---------------------------------------------------------- swap, timetable


def test_swapping_two_overlapping_classes_exchanges_their_teachers(
    centre: Centre,
) -> None:
    """The swap passes through a moment the constraint would refuse."""
    a, b = centre.teacher(), centre.teacher()
    first, second = centre.batch("Class 9"), centre.batch("Class 10")
    centre.schedule(first, _slot(a))
    centre.schedule(second, _slot(b))
    one, two = _future(centre.session, first)[0], _future(centre.session, second)[0]
    response = centre.client.post(
        "/v1/centre/sessions/swap",
        json={"first_session_id": str(one.id), "second_session_id": str(two.id)},
        headers=centre.headers(),
    )
    assert response.status_code == 200, response.text
    centre.session.expire_all()
    swapped = {
        c.id: c
        for c in centre.session.scalars(
            sa.select(ClassSession).where(ClassSession.id.in_([one.id, two.id]))
        )
    }
    assert (swapped[one.id].teacher_member_id, swapped[two.id].teacher_member_id) == (
        b,
        a,
    )
    assert {c.assignment_source for c in swapped.values()} == {"override"}


def test_a_class_in_another_centre_cannot_be_reassigned_or_swapped(
    api_client: TestClient, owner_session: Session, centre: Centre
) -> None:
    """Their classes are refused alike."""
    other = Centre(api_client, owner_session)
    theirs = other.batch("Theirs")
    other.schedule(theirs, _slot())
    target = _future(owner_session, theirs)[0]
    mine = centre.batch("Mine")
    centre.schedule(mine, _slot())
    own = _future(owner_session, mine)[0]

    assignment = centre.client.post(
        f"/v1/sessions/{target.id}/assignment",
        json={"teacher_member_id": None, "room_id": None},
        headers=centre.headers(),
    )
    assert assignment.status_code in (403, 404), assignment.text
    swap = centre.client.post(
        "/v1/centre/sessions/swap",
        json={"first_session_id": str(own.id), "second_session_id": str(target.id)},
        headers=centre.headers(),
    )
    assert swap.status_code in (403, 404), swap.text


def test_the_timetable_lists_each_class_with_its_teacher_and_room(
    centre: Centre,
) -> None:
    """Across batches, soonest first, with names the manager typed."""
    teacher, room = centre.teacher(), centre.room("Room 1")
    batch = centre.batch("Class 9")
    centre.schedule(batch, _slot(teacher, room))
    day = TOMORROW.isoformat()
    response = centre.client.get(
        f"/v1/centre/timetable?from={day}&to={day}", headers=centre.headers()
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    assert (row["batch_name"], row["room_name"], row["start_time"]) == (
        "Class 9",
        "Room 1",
        "16:00",
    )
    assert row["teacher_member_id"] == str(teacher)
    assert row["teacher_name"].startswith("Teacher ")


def test_the_timetable_refuses_a_range_too_long_to_read(centre: Centre) -> None:
    """A bounded read: at most 31 days."""
    start = TOMORROW
    end = start + dt.timedelta(days=40)
    response = centre.client.get(
        f"/v1/centre/timetable?from={start}&to={end}", headers=centre.headers()
    )
    assert response.status_code == 400, response.text
    assert _code(response) == "TIMETABLE_RANGE_TOO_LONG"


# --------------------------------------------------------------- revocation


def test_removing_a_teacher_frees_their_future_classes(centre: Centre) -> None:
    """Their slots and unheld future classes become unassigned."""
    teacher = centre.teacher()
    batch = centre.batch("Class 9")
    centre.schedule(batch, _slot(teacher))
    revoked = centre.client.post(
        f"/v1/centre/members/{teacher}/revoke", headers=centre.headers()
    )
    assert revoked.status_code == 204, revoked.text
    assert {c.teacher_member_id for c in _future(centre.session, batch)} == {None}
    slot = centre.client.get(
        f"/v1/batches/{batch}/schedule", headers=centre.headers()
    ).json()
    assert slot[0]["teacher_member_id"] is None
