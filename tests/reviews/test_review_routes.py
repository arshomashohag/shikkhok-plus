"""The review routes, end to end through the real application [H4 Task 6].

Each route runs against the restricted database role, with the lens
resolved by the real dependency and the switch read from the environment
per request. The world is arranged through the table-owner session.

Written before the routes existed: the off table (Review Focus 5), the
dependency order that makes an off switch answer ``HUB_REVIEWS_OFF`` and
never ``NOT_AVAILABLE``, and the teacher-lens refusal are authorization
predicates [team: Testing Posture].
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Final

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.ceilings import HUB_REVIEW_ACCOUNT_DAILY, CeilingChecker
from app.hub.public.settings import HUB_REVIEWS_ENV
from app.local_time import bangladesh_today
from app.reviews import authoring
from tests.conftest import bearer
from tests.hub.support import add_member, assign_slot
from tests.reviews.support import (
    PublicBatch,
    account,
    add_review,
    attend,
    guardian_seat,
    hold_classes,
    public_batch,
    public_centre_batch,
    second_batch,
)

#: The reviewer path for one batch.
MY_REVIEW: Final = "/v1/hub/batches/{batch_id}/my-review"

#: Every field the author's review state carries, and nothing else: no
#: seat, no assessment, no timestamp [T3-e, T4-b].
STATE_FIELDS: Final = {
    "standing",
    "waiting_on",
    "eligible_from",
    "can_write",
    "edit_until",
    "review",
}

#: Every field of the author's own review on the wire.
REVIEW_FIELDS: Final = {
    "rating",
    "body",
    "status",
    "rejection_code",
    "tenure",
    "published_month",
    "reply_body",
}

#: Every field of a review as the teacher reads it.
OWNER_REVIEW_FIELDS: Final = {
    "id",
    "batch_id",
    "rating",
    "body",
    "tenure",
    "published_month",
    "reply_body",
    "reply_month",
    "my_reply_status",
    "my_reply_body",
    "my_reply_rejection_code",
}


def _today() -> dt.date:
    """Give Bangladesh's date by the real clock.

    :return: Today in Bangladesh
    """
    return bangladesh_today()


def _month() -> dt.date:
    """Give the first of this month in Bangladesh.

    :return: The date
    """
    return _today().replace(day=1)


def _member(
    session: Session,
    batch_id: uuid.UUID,
    guardian: uuid.UUID,
    *,
    joined_days_ago: int = 100,
    attended: int = 4,
    inactive_days_ago: int | None = None,
) -> uuid.UUID:
    """Seat a guardian's child and record attended classes.

    :param session: An arranging session
    :param batch_id: The batch
    :param guardian: The guardian
    :param joined_days_ago: How long ago the child joined
    :param attended: Classes attended
    :param inactive_days_ago: How long ago the seat stopped, if it did
    :return: The enrollment id
    """
    seat = guardian_seat(
        session,
        batch_id,
        guardian,
        joined_on=_today() - dt.timedelta(days=joined_days_ago),
        inactive_from=(
            None
            if inactive_days_ago is None
            else _today() - dt.timedelta(days=inactive_days_ago)
        ),
    )
    attend(session, hold_classes(session, batch_id, attended), seat)
    return seat


def _publish(session: Session, review_id: uuid.UUID) -> None:
    """Move a stored review to published, this month.

    :param session: An arranging session
    :param review_id: The review
    :return: None
    """
    session.execute(
        sa.text(
            "UPDATE review SET status = 'published', published_month = :m WHERE id = :r"
        ),
        {"m": _month(), "r": review_id},
    )
    session.commit()


def _published(
    session: Session, batch_id: uuid.UUID, ratings: tuple[int, ...]
) -> list[uuid.UUID]:
    """Publish one review per rating, each by a new guardian.

    :param session: An arranging session
    :param batch_id: The batch
    :param ratings: The ratings
    :return: The review ids
    """
    ids = []
    for rating in ratings:
        review_id = add_review(session, batch_id, account(session), rating=rating)
        _publish(session, review_id)
        ids.append(review_id)
    return ids


def _reply(session: Session, review_id: uuid.UUID, *, status: str) -> None:
    """Store a reply directly.

    :param session: An arranging session
    :param review_id: The review
    :param status: ``pending`` or ``published``
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status, published_month) "
            "VALUES (:r, 'Thank you.', CAST(:s AS hub_reply_status), :m)"
        ),
        {"r": review_id, "s": status, "m": _month() if status == "published" else None},
    )
    session.commit()


def _count(session: Session, table: str, where: str, value: uuid.UUID) -> int:
    """Count rows of a table matching one id column.

    :param session: An arranging session
    :param table: ``review`` or ``review_reply``
    :param where: The id column
    :param value: The id
    :return: The count
    """
    session.rollback()
    return int(
        session.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE {where} = :v"),  # noqa: S608
            {"v": value},
        ).scalar_one()
    )


def _error(response: httpx.Response) -> dict[str, object]:
    """Read an error envelope's body.

    :param response: The response
    :return: The ``error`` object
    """
    body = response.json()
    assert set(body) == {"error"}, body
    error = body["error"]
    assert isinstance(error, dict)
    return error


def _refused(
    response: httpx.Response, status: int, code: str, message_key: str
) -> dict[str, object]:
    """Assert a refusal's status, code and message key.

    :param response: The response
    :param status: The expected status
    :param code: The expected code
    :param message_key: The expected message key
    :return: The error object, for further checks
    """
    assert response.status_code == status, response.text
    error = _error(response)
    assert error["code"] == code
    assert error["message_key"] == message_key
    assert error["retryable"] is False
    return error


def test_gated_routes_answer_reviews_off_and_deletes_still_work(
    api_client: TestClient, owner_session: Session
) -> None:
    """Review Focus 5: off refuses every gated route, and only those.

    The author keeps their read and their delete, the teacher keeps theirs,
    and the reviewable list narrows to what the author already reviewed.
    """
    batch = public_batch(owner_session)
    other = second_batch(owner_session, batch.owner_id, title="SSC Chemistry")
    author = account(owner_session)
    seat = _member(owner_session, batch.batch_id, author)
    _member(owner_session, other, author)
    review_id = add_review(owner_session, batch.batch_id, author, enrollment_id=seat)
    _publish(owner_session, review_id)
    _reply(owner_session, review_id, status="published")
    stranger = account(owner_session)
    teacher = bearer(owner_session, batch.teacher_account_id)
    mine = bearer(owner_session, author)
    theirs = bearer(owner_session, stranger)
    path = MY_REVIEW.format(batch_id=batch.batch_id)
    reply = f"/v1/hub/reviews/{review_id}/reply"
    off = (404, "HUB_REVIEWS_OFF", "hub.review.off")

    # Every gated route, for a member, a teacher and a stranger alike: the
    # switch runs before the lens, so nobody learns membership from it.
    for headers in (mine, theirs):
        _refused(api_client.put(path, json={"rating": 2}, headers=headers), *off)
    for headers in (teacher, theirs):
        _refused(api_client.get("/v1/hub/reviews", headers=headers), *off)
        _refused(api_client.put(reply, json={"body": "Thanks"}, headers=headers), *off)

    # The author's read is not gated; it only says nothing can be written.
    read = api_client.get(path, headers=mine)
    assert read.status_code == 200, read.text
    assert read.json()["can_write"] is False
    assert read.json()["review"]["rating"] == 4
    assert read.json()["review"]["reply_body"] == "Thank you."
    # Not gated, so a stranger gets the lens's refusal, not the switch's.
    _refused(
        api_client.get(path, headers=theirs),
        403,
        "NOT_AVAILABLE",
        "authz.lens.not_available",
    )

    # The list keeps only what the caller already reviewed.
    listed = api_client.get("/v1/hub/reviewable", headers=mine)
    assert listed.status_code == 200, listed.text
    assert [(row["batch_id"], row["state"]) for row in listed.json()] == [
        (str(batch.batch_id), "reviewed")
    ]

    # The switch never gates a deletion.
    deleted = api_client.delete(reply, headers=teacher)
    assert deleted.status_code == 204, deleted.text
    assert _count(owner_session, "review_reply", "review_id", review_id) == 0
    assert _count(owner_session, "review", "id", review_id) == 1
    deleted = api_client.delete(path, headers=mine)
    assert deleted.status_code == 204, deleted.text
    assert _count(owner_session, "review", "id", review_id) == 0


@pytest.mark.usefixtures("reviews_on")
def test_end_to_end_create_edit_delete(
    api_client: TestClient, owner_session: Session
) -> None:
    """An eligible guardian lists, writes, edits and deletes one review."""
    batch = public_batch(owner_session, title="HSC Physics", owner_name="Rahim Sir")
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    headers = bearer(owner_session, guardian)
    path = MY_REVIEW.format(batch_id=batch.batch_id)

    listed = api_client.get("/v1/hub/reviewable", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json() == [
        {
            "batch_id": str(batch.batch_id),
            "batch_title": "HSC Physics",
            "owner_public_name": "Rahim Sir",
            "state": "eligible",
            "eligible_from": None,
        }
    ]

    before = api_client.get(path, headers=headers)
    assert before.status_code == 200, before.text
    assert before.json() == {
        "standing": "eligible",
        "waiting_on": None,
        "eligible_from": None,
        "can_write": True,
        "edit_until": None,
        "review": None,
    }

    created = api_client.put(
        path, json={"rating": 5, "body": "  Clear teaching.  "}, headers=headers
    )
    assert created.status_code == 200, created.text
    state = created.json()
    assert set(state) == STATE_FIELDS
    assert set(state["review"]) == REVIEW_FIELDS
    assert state["can_write"] is True
    assert state["edit_until"] == (_today() + dt.timedelta(days=30)).isoformat()
    assert state["review"] == {
        "rating": 5,
        "body": "Clear teaching.",
        "status": "pending",
        "rejection_code": None,
        "tenure": "lt_6m",
        "published_month": None,
        "reply_body": None,
    }
    assert [
        row["state"]
        for row in api_client.get("/v1/hub/reviewable", headers=headers).json()
    ] == ["reviewed"]

    edited = api_client.put(path, json={"rating": 3, "body": "   "}, headers=headers)
    assert edited.status_code == 200, edited.text
    assert edited.json()["review"]["rating"] == 3
    assert edited.json()["review"]["body"] is None

    for _ in range(2):  # deleting is idempotent
        deleted = api_client.delete(path, headers=headers)
        assert deleted.status_code == 204, deleted.text
        assert deleted.content == b""
    after = api_client.get(path, headers=headers)
    assert after.json()["review"] is None
    assert after.json()["standing"] == "eligible"
    assert _count(owner_session, "review", "author_account_id", guardian) == 0


@pytest.mark.usefixtures("reviews_on")
def test_published_review_shows_its_month_never_a_day(
    api_client: TestClient, owner_session: Session
) -> None:
    """A published review's month is ``YYYY-MM`` on the author's wire."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    seat = _member(owner_session, batch.batch_id, guardian)
    review_id = add_review(owner_session, batch.batch_id, guardian, enrollment_id=seat)
    _publish(owner_session, review_id)

    response = api_client.get(
        MY_REVIEW.format(batch_id=batch.batch_id),
        headers=bearer(owner_session, guardian),
    )

    assert response.status_code == 200, response.text
    assert response.json()["review"]["published_month"] == f"{_month():%Y-%m}"


@pytest.mark.usefixtures("reviews_on")
def test_waiting_and_closed_standings_on_the_wire(
    api_client: TestClient, owner_session: Session
) -> None:
    """T3-b: a waiting member is told the day; a closed window has no day."""
    waiting = public_batch(owner_session, title="A waiting batch")
    closed = public_batch(owner_session, title="B closed batch")
    guardian = account(owner_session)
    _member(owner_session, waiting.batch_id, guardian, joined_days_ago=10)
    _member(owner_session, closed.batch_id, guardian, inactive_days_ago=181)
    headers = bearer(owner_session, guardian)
    opens = (_today() - dt.timedelta(days=10) + dt.timedelta(days=30)).isoformat()

    soon = api_client.get(MY_REVIEW.format(batch_id=waiting.batch_id), headers=headers)
    assert soon.status_code == 200, soon.text
    assert soon.json() == {
        "standing": "not_yet",
        "waiting_on": "tenure",
        "eligible_from": opens,
        "can_write": False,
        "edit_until": None,
        "review": None,
    }

    gone = api_client.get(MY_REVIEW.format(batch_id=closed.batch_id), headers=headers)
    assert gone.status_code == 200, gone.text
    assert gone.json()["standing"] == "closed"
    assert gone.json()["eligible_from"] is None
    assert gone.json()["can_write"] is False

    listed = api_client.get("/v1/hub/reviewable", headers=headers).json()
    assert [
        (row["batch_title"], row["state"], row["eligible_from"]) for row in listed
    ] == [("A waiting batch", "not_yet", opens)]


@pytest.mark.usefixtures("reviews_on")
def test_no_date_on_the_wire_while_classes_are_still_needed(
    api_client: TestClient, owner_session: Session
) -> None:
    """FR-c: ``eligible_from`` travels only with tenure alone unmet.

    A family short of both tenure and classes is told it needs classes, on
    the read, the list and the refused write alike, and is given no day.
    """
    batch = public_batch(owner_session, title="A new batch")
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian, joined_days_ago=10, attended=1)
    headers = bearer(owner_session, guardian)
    path = MY_REVIEW.format(batch_id=batch.batch_id)

    read = api_client.get(path, headers=headers)
    assert read.status_code == 200, read.text
    assert (read.json()["waiting_on"], read.json()["eligible_from"]) == (
        "attendance",
        None,
    )

    listed = api_client.get("/v1/hub/reviewable", headers=headers).json()
    assert [(row["state"], row["eligible_from"]) for row in listed] == [
        ("not_yet", None)
    ]

    refused = api_client.put(path, headers=headers, json={"rating": 4})
    assert refused.status_code == 409, refused.text
    error = refused.json()["error"]
    assert error["message_key"] == "hub.review.needs_attendance"
    assert error.get("details") is None


@pytest.mark.usefixtures("reviews_on")
def test_write_validation_strips_before_counting(
    api_client: TestClient, owner_session: Session
) -> None:
    """F14: a body is bounded after stripping; a rating is one to five."""
    batch = public_batch(owner_session)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    headers = bearer(owner_session, guardian)
    path = MY_REVIEW.format(batch_id=batch.batch_id)
    invalid = (422, "REQUEST_INVALID", "error.unexpected")

    for body in ({"rating": 0}, {"rating": 6}, {"rating": 4, "body": "x" * 1001}):
        _refused(api_client.put(path, json=body, headers=headers), *invalid)
    _refused(
        api_client.put(path, json={"rating": 4, "extra": 1}, headers=headers),
        *invalid,
    )
    assert _count(owner_session, "review", "author_account_id", guardian) == 0

    padded = api_client.put(
        path, json={"rating": 4, "body": f"  {'x' * 1000}  "}, headers=headers
    )
    assert padded.status_code == 200, padded.text
    assert padded.json()["review"]["body"] == "x" * 1000


@pytest.mark.usefixtures("reviews_on")
def test_teacher_reads_ratings_and_replies(
    api_client: TestClient, owner_session: Session
) -> None:
    """F13, T2-a: the teacher's read, and a reply written and deleted.

    A rating over the threshold carries its rendered average; one under it
    carries no figure at all, the count included.
    """
    batch = public_batch(owner_session, title="HSC Physics")
    small = second_batch(owner_session, batch.owner_id, title="SSC Chemistry")
    _published(owner_session, batch.batch_id, (5, 4, 4))
    _published(owner_session, small, (1, 2))
    headers = bearer(owner_session, batch.teacher_account_id)

    read = api_client.get("/v1/hub/reviews", headers=headers)
    assert read.status_code == 200, read.text
    body = read.json()
    assert set(body) == {"batches", "reviews"}
    assert body["batches"] == [
        {
            "batch_id": str(batch.batch_id),
            "batch_title": "HSC Physics",
            "review_count": 3,
            "average_tenths": 43,
            "average_label": "4.3",
            "distribution": [0, 0, 0, 2, 1],
        },
        {
            "batch_id": str(small),
            "batch_title": "SSC Chemistry",
            "review_count": None,
            "average_tenths": None,
            "average_label": None,
            "distribution": None,
        },
    ]
    assert len(body["reviews"]) == 3
    for review in body["reviews"]:
        assert set(review) == OWNER_REVIEW_FIELDS
        assert review["batch_id"] == str(batch.batch_id)
        assert review["published_month"] == f"{_month():%Y-%m}"
        assert review["my_reply_status"] is None
    target = body["reviews"][0]["id"]
    reply = f"/v1/hub/reviews/{target}/reply"

    for blank in ("", "    ", "y" * 1001):
        _refused(
            api_client.put(reply, json={"body": blank}, headers=headers),
            422,
            "REQUEST_INVALID",
            "error.unexpected",
        )
    written = api_client.put(reply, json={"body": "  Thank you.  "}, headers=headers)
    assert written.status_code == 200, written.text
    assert set(written.json()) == OWNER_REVIEW_FIELDS
    assert written.json()["id"] == target
    assert written.json()["my_reply_status"] == "pending"
    assert written.json()["my_reply_body"] == "Thank you."
    assert written.json()["reply_body"] is None
    assert written.json()["reply_month"] is None

    deleted = api_client.delete(reply, headers=headers)
    assert deleted.status_code == 204, deleted.text
    again = api_client.get("/v1/hub/reviews", headers=headers).json()
    assert {r["id"]: r["my_reply_status"] for r in again["reviews"]}[target] is None


@pytest.mark.usefixtures("reviews_on")
def test_teacher_sees_a_published_reply_month(
    api_client: TestClient, owner_session: Session
) -> None:
    """A published reply's month is ``YYYY-MM`` too."""
    batch = public_batch(owner_session)
    first, *_ = _published(owner_session, batch.batch_id, (5, 4, 3))
    _reply(owner_session, first, status="published")

    reviews = api_client.get(
        "/v1/hub/reviews", headers=bearer(owner_session, batch.teacher_account_id)
    ).json()["reviews"]

    replied = next(r for r in reviews if r["id"] == str(first))
    assert replied["reply_body"] == "Thank you."
    assert replied["reply_month"] == f"{_month():%Y-%m}"
    assert replied["my_reply_status"] == "published"


@pytest.mark.usefixtures("reviews_on")
def test_teacher_routes_refuse_class_teacher_and_guardian(
    api_client: TestClient, owner_session: Session
) -> None:
    """Only the owner's teacher lens reaches the teacher's review routes."""
    batch = public_centre_batch(owner_session)
    review_id, *_ = _published(owner_session, batch.batch_id, (5, 4, 3))
    member_id, class_teacher = add_member(owner_session, batch.owner_id)
    assign_slot(owner_session, batch.batch_id, member_id)
    guardian = account(owner_session)
    _member(owner_session, batch.batch_id, guardian)
    reply = f"/v1/hub/reviews/{review_id}/reply"
    no_lens = (403, "NO_TEACHER_LENS", "authz.lens.not_available")

    for caller in (class_teacher, guardian):
        headers = bearer(owner_session, caller)
        _refused(api_client.get("/v1/hub/reviews", headers=headers), *no_lens)
        _refused(
            api_client.put(reply, json={"body": "Thanks"}, headers=headers), *no_lens
        )
        _refused(api_client.delete(reply, headers=headers), *no_lens)

    # The centre's manager holds the owner's lens and is answered.
    manager = api_client.get(
        "/v1/hub/reviews", headers=bearer(owner_session, batch.teacher_account_id)
    )
    assert manager.status_code == 200, manager.text
    assert len(manager.json()["reviews"]) == 3


def _eligible(session: Session) -> tuple[PublicBatch, uuid.UUID]:
    """Arrange a public batch and a guardian eligible to review it.

    :param session: An arranging session
    :return: The batch and the guardian
    """
    batch = public_batch(session)
    guardian = account(session)
    _member(session, batch.batch_id, guardian)
    return batch, guardian


def _put_review(
    client: TestClient,
    session: Session,
    batch: PublicBatch,
    guardian: uuid.UUID,
    body: dict[str, object],
) -> httpx.Response:
    """PUT a review as a guardian.

    :param client: The test client
    :param session: An arranging session
    :param batch: The batch
    :param guardian: The guardian
    :param body: The request body
    :return: The response
    """
    return client.put(
        MY_REVIEW.format(batch_id=batch.batch_id),
        json=body,
        headers=bearer(session, guardian),
    )


def _call_off(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Write while reviews are off.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Switches reviews off
    :return: The response
    """
    batch, guardian = _eligible(session)
    monkeypatch.delenv(HUB_REVIEWS_ENV)
    return _put_review(client, session, batch, guardian, {"rating": 4})


def _call_seat(**seat: int) -> Callable[..., httpx.Response]:
    """Build a case writing a first review from a seat that is not eligible.

    :param seat: The seat's arrangement, as :func:`_member` takes it
    :return: The case
    """

    def call(
        client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> httpx.Response:
        del monkeypatch
        batch = public_batch(session)
        guardian = account(session)
        _member(session, batch.batch_id, guardian, **seat)
        return _put_review(client, session, batch, guardian, {"rating": 4})

    return call


def _call_contact(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Write a body carrying a phone number.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    batch, guardian = _eligible(session)
    return _put_review(
        client, session, batch, guardian, {"rating": 4, "body": "Call 01712345678"}
    )


def _call_edit_closed(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Edit a review first submitted 40 days ago.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    batch, guardian = _eligible(session)
    review_id = add_review(session, batch.batch_id, guardian, rating=5)
    session.execute(
        sa.text("UPDATE review SET submitted_at = :t WHERE id = :r"),
        {"t": dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=40), "r": review_id},
    )
    session.commit()
    return _put_review(client, session, batch, guardian, {"rating": 1})


def _call_ceiling(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Make one changing write more than a day allows.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    batch, guardian = _eligible(session)
    for rating in range(1, HUB_REVIEW_ACCOUNT_DAILY + 1):
        spent = _put_review(client, session, batch, guardian, {"rating": rating})
        assert spent.status_code == 200, spent.text
    return _put_review(client, session, batch, guardian, {"rating": 1})


def _call_not_found(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Reply to a review id that was never minted.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    batch = public_batch(session)
    return client.put(
        f"/v1/hub/reviews/{uuid.uuid4()}/reply",
        json={"body": "Thanks"},
        headers=bearer(session, batch.teacher_account_id),
    )


def _call_non_member(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Read the review of a batch the caller has no seat in.

    :param client: The test client
    :param session: An arranging session
    :param monkeypatch: Unused
    :return: The response
    """
    del monkeypatch
    batch = public_batch(session)
    return client.get(
        MY_REVIEW.format(batch_id=batch.batch_id),
        headers=bearer(session, account(session)),
    )


#: One case per row of the global constraints' error table that these
#: routes can answer, plus the reused ``NOT_AVAILABLE``.
#: ``REVIEW_ALREADY_DECIDED`` and ``REVIEW_CODE_INVALID`` are raised only
#: by the administrator's decision route (Task 7), which none of these is.
ERROR_CASES: Final = [
    pytest.param(_call_off, 404, "HUB_REVIEWS_OFF", "hub.review.off", id="off"),
    pytest.param(
        _call_seat(joined_days_ago=10),
        409,
        "REVIEW_NOT_YET_ELIGIBLE",
        "hub.review.not_yet_eligible",
        id="tenure",
    ),
    pytest.param(
        _call_seat(attended=3),
        409,
        "REVIEW_NOT_YET_ELIGIBLE",
        "hub.review.needs_attendance",
        id="attendance",
    ),
    pytest.param(
        _call_seat(inactive_days_ago=181),
        409,
        "REVIEW_NOT_YET_ELIGIBLE",
        "hub.review.window_closed",
        id="closed",
    ),
    pytest.param(
        _call_contact,
        400,
        "REVIEW_CONTAINS_CONTACT",
        "hub.review.contains_contact",
        id="contact",
    ),
    pytest.param(
        _call_edit_closed,
        409,
        "REVIEW_EDIT_CLOSED",
        "hub.review.edit_closed",
        id="edit-closed",
    ),
    pytest.param(
        _call_ceiling, 409, "HUB_REVIEW_CEILING", "hub.review.ceiling", id="ceiling"
    ),
    pytest.param(
        _call_not_found,
        404,
        "REVIEW_NOT_FOUND",
        "hub.review.not_found",
        id="not-found",
    ),
    pytest.param(
        _call_non_member,
        403,
        "NOT_AVAILABLE",
        "authz.lens.not_available",
        id="non-member",
    ),
]

#: The details each case carries; None where the envelope carries none.
ERROR_DETAILS: Final[dict[str, Callable[[], dict[str, str] | None]]] = {
    "hub.review.not_yet_eligible": lambda: {
        "eligible_from": (_today() + dt.timedelta(days=20)).isoformat()
    },
    "hub.review.contains_contact": lambda: {"field": "body"},
}


@pytest.mark.usefixtures("reviews_on")
@pytest.mark.parametrize(("call", "status", "code", "message_key"), ERROR_CASES)
def test_error_envelopes_for_new_codes(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    call: Callable[..., httpx.Response],
    status: int,
    code: str,
    message_key: str,
) -> None:
    """Each code arrives with its status, its key and its details."""
    response = call(api_client, owner_session, monkeypatch)

    error = _refused(response, status, code, message_key)
    expected = ERROR_DETAILS.get(message_key, lambda: None)()
    assert error.get("details") == expected


@pytest.mark.usefixtures("reviews_on")
def test_write_routes_roll_back_on_an_unexpected_error(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-taxonomy failure after the insert leaves no review and no reply."""
    batch, guardian = _eligible(owner_session)
    review_id, *_ = _published(owner_session, batch.batch_id, (5, 4, 3))
    client = TestClient(api_client.app, raise_server_exceptions=False)

    def boom(*args: object, **kwargs: object) -> None:
        msg = "after the insert"
        raise RuntimeError(msg)

    monkeypatch.setattr(authoring, "_spend", boom)
    monkeypatch.setattr(CeilingChecker, "consume_hub_listing_in_transaction", boom)

    review = _put_review(client, owner_session, batch, guardian, {"rating": 4})
    replied = client.put(
        f"/v1/hub/reviews/{review_id}/reply",
        json={"body": "Thanks"},
        headers=bearer(owner_session, batch.teacher_account_id),
    )

    assert review.status_code == 500
    assert replied.status_code == 500
    assert _count(owner_session, "review", "author_account_id", guardian) == 0
    assert _count(owner_session, "review_reply", "review_id", review_id) == 0
