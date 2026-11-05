"""A decimal mark and publishing, over HTTP (decided 2026-11-05)."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from tests.batches.conftest import TeacherFixture
from tests.conftest import bearer


def test_a_decimal_mark_round_trips_and_publish_answers_no_content(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    """19.5 is written and read back as 19.5; publishing then succeeds.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param exam: The exam (already published by the fixture)
    :param seat_factory: Makes seats
    :return: None
    """
    seat = seat_factory("Rahim")
    headers = bearer(owner_session, teacher.account_id)

    written = api_client.post(
        f"/v1/exams/{exam}/marks",
        json={"enrollment_id": str(seat), "result_state": "marked", "marks": 19.5},
        headers=headers,
    )
    results = api_client.get(f"/v1/exams/{exam}/results", headers=headers).json()
    published = api_client.post(f"/v1/exams/{exam}/publish", headers=headers)

    assert written.status_code == 204
    assert [row["marks"] for row in results["results"]] == [19.5]
    assert results["exam"]["published"] is True
    assert published.status_code == 204


def test_a_third_decimal_place_is_refused_with_its_key(
    api_client: TestClient,
    owner_session: DbSession,
    teacher: TeacherFixture,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
) -> None:
    """Never rounded silently: the server says why.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param exam: The exam
    :param seat_factory: Makes seats
    :return: None
    """
    seat = seat_factory("Rahim")

    refused = api_client.post(
        f"/v1/exams/{exam}/marks",
        json={"enrollment_id": str(seat), "result_state": "marked", "marks": 19.125},
        headers=bearer(owner_session, teacher.account_id),
    )

    assert refused.status_code == 400
    assert refused.json()["error"]["message_key"] == "marks.too_precise"
