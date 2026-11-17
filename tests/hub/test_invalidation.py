"""The CloudFront invalidation outbox and every takedown path that feeds it.

Public owner and batch pages are cached at the edge for up to ten minutes,
so a takedown that only changed a row would leave the page served from the
cache. Every takedown therefore writes ``cdn_invalidation`` rows **in its own
transaction**: a rolled-back takedown leaves no row, and a committed one
cannot lose its row. The drain sends unsent rows in one ``CreateInvalidation``
batch, after the request commits and every ten minutes from cron.

Rows are arranged as the table owner; each service under test is handed the
application role's session, so the role's grants on the outbox are exercised.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field
from typing import Final

import boto3
import pytest
import sqlalchemy as sa
from botocore.stub import Stubber
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.authz.lenses import CentreMemberLens, PlatformAdminLens, TeacherLens
from app.batches.service import BatchChanges, update_batch
from app.db.models import HUB_INVALIDATION_JOB, BatchSubject
from app.governance.deletion import delete_account
from app.hub.listings import batches, owner
from app.hub.listings.batches import BatchListingUpdate
from app.hub.listings.member_consent import set_public_name_consent
from app.hub.listings.owner import OwnerListingUpdate
from app.hub.public import cloudfront, commands, invalidation
from app.moderation import suspension
from tests.batches.conftest import make_teacher
from tests.conftest import bearer
from tests.hub.support import add_member, assign_slot, centre_with_manager

NOW: Final[dt.datetime] = dt.datetime(2026, 11, 17, 9, 0, tzinfo=dt.UTC)

#: Every enqueue carries the sitemap, which lists what a takedown removes.
SITEMAP: Final[str] = "/hub/sitemap.xml"


@dataclass
class _Recorder:
    """A stand-in CloudFront that records each request, or fails.

    :ivar calls: ``(paths, caller_reference)`` per request
    :ivar fail: Raise instead of recording
    """

    calls: list[tuple[list[str], str]] = field(default_factory=list)
    fail: bool = False

    def create_invalidation(self, paths: list[str], caller_reference: str) -> str:
        """Record one request.

        :param paths: The paths
        :param caller_reference: The idempotency key
        :return: A fake invalidation id
        :raises RuntimeError: When told to fail
        """
        if self.fail:
            raise RuntimeError("cloudfront unavailable")
        self.calls.append((list(paths), caller_reference))
        return f"I{len(self.calls)}EXAMPLE"


@dataclass(frozen=True, slots=True)
class _Row:
    """One outbox row as the table owner reads it."""

    path: str
    sent_at: dt.datetime | None
    aws_id: str | None
    attempts: int


def _rows(session: Session) -> list[_Row]:
    """Read every outbox row, fresh, oldest first.

    :param session: The arranging session
    :return: The rows
    """
    session.rollback()
    return [
        _Row(r.path, r.sent_at, r.aws_id, r.attempts)
        for r in session.execute(
            sa.text(
                "SELECT path, sent_at, aws_id, attempts FROM cdn_invalidation "
                "ORDER BY requested_at, path"
            )
        )
    ]


def _paths(session: Session) -> set[str]:
    """Read the set of enqueued paths.

    :param session: The arranging session
    :return: The paths
    """
    return {row.path for row in _rows(session)}


def _owner_listing(
    session: Session, owner_id: uuid.UUID, slug: str, status: str = "published"
) -> None:
    """Insert a complete owner listing.

    :param session: An arranging session
    :param owner_id: The owner
    :param slug: Its slug
    :param status: Its status
    :return: None
    """
    district = session.execute(
        sa.text("SELECT code FROM bd_area WHERE kind = 'district' LIMIT 1")
    ).scalar_one()
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "headline_en, bio_en, district_code, published_at) VALUES "
            "(:o, :slug, CAST(:st AS hub_listing_status), 'Rahim Sir', "
            "'Maths', 'Teaching since 2010', :d, now())"
        ),
        {"o": owner_id, "slug": slug, "st": status, "d": district},
    )
    session.commit()


def _batch_listing(
    session: Session,
    owner_id: uuid.UUID,
    batch_id: uuid.UUID,
    slug: str,
    status: str = "published",
) -> None:
    """Insert a complete batch listing, and the subject it needs.

    :param session: An arranging session
    :param owner_id: The batch's owner
    :param batch_id: The batch
    :param slug: Its slug
    :param status: Its status
    :return: None
    """
    session.add(BatchSubject(batch_id=batch_id, name="Maths"))
    session.commit()
    session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, slug, status, "
            "public_title, description_en, class_levels, subject_tags, mode, "
            "show_fee, show_schedule, published_at) VALUES "
            "(:b, :o, :slug, CAST(:st AS hub_listing_status), 'Class 9 maths', "
            "'Weekly practice', CAST(ARRAY['class_9'] AS varchar[]), "
            "CAST(ARRAY['maths'] AS varchar[]), 'in_person', false, false, now())"
        ),
        {"b": batch_id, "o": owner_id, "slug": slug, "st": status},
    )
    session.commit()


def _tutor(session: Session, slug: str = "rahim-sir") -> tuple[TeacherLens, uuid.UUID]:
    """Arrange a solo tutor whose owner and batch listings are published.

    :param session: An arranging session
    :param slug: The owner's slug
    :return: ``(lens, batch_id)``; the batch's slug is ``class-9-maths``
    """
    teacher = make_teacher(session)
    _owner_listing(session, teacher.owner_id, slug)
    _batch_listing(session, teacher.owner_id, teacher.batch_id, "class-9-maths")
    lens = TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)
    return lens, teacher.batch_id


def test_paths_put_the_wildcard_only_at_the_end() -> None:
    """CloudFront accepts ``*`` only as a path's last character.

    :return: None
    """
    generated = [
        *invalidation.owner_paths("rahim-sir"),
        *invalidation.batch_paths("rahim-sir", "class-9-maths"),
        invalidation.SITEMAP_PATH,
    ]

    assert invalidation.owner_paths("rahim-sir") == [
        "/hub/en/t/rahim-sir*",
        "/hub/bn/t/rahim-sir*",
    ]
    assert invalidation.batch_paths("rahim-sir", "class-9-maths") == [
        "/hub/en/t/rahim-sir/class-9-maths",
        "/hub/bn/t/rahim-sir/class-9-maths",
    ]
    assert invalidation.SITEMAP_PATH == SITEMAP
    for path in generated:
        assert path.startswith("/")
        assert "*" not in path[:-1], path


def test_enqueue_refuses_a_path_cloudfront_would_reject(
    restricted_session: Session,
) -> None:
    """A hand-written path with an inner wildcard never reaches the outbox.

    :param restricted_session: The application role's session
    :return: None
    """
    with pytest.raises(ValueError, match="wildcard"):
        invalidation.enqueue(restricted_session, ["/hub/en/t/*/x"], NOW)
    with pytest.raises(ValueError, match="absolute"):
        invalidation.enqueue(restricted_session, ["hub/en/t/x"], NOW)


def test_suspension_enqueues_invalidation_in_same_transaction(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review Focus 2: the row commits with the suspension, or not at all.

    The suspension's own commit is replaced by a flush and the transaction
    is then rolled back: the row existed inside it and is gone with it, as
    the suspension is. Run for real, both commit together, and the drain
    sends the owner's prefix in both locales with the sitemap.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param monkeypatch: The patcher
    :return: None
    """
    lens, _ = _tutor(owner_session)
    admin = PlatformAdminLens(account_id=make_teacher(owner_session).account_id)
    expected = {*invalidation.owner_paths("rahim-sir"), SITEMAP}

    monkeypatch.setattr(restricted_session, "commit", restricted_session.flush)
    suspension.set(restricted_session, admin, lens.owner_id, True, "misleading", NOW)
    inside = set(
        restricted_session.execute(sa.text("SELECT path FROM cdn_invalidation"))
        .scalars()
        .all()
    )
    assert inside == expected
    restricted_session.rollback()
    monkeypatch.undo()

    assert _rows(owner_session) == []
    status = owner_session.execute(
        sa.text("SELECT status::text FROM owner_listing WHERE owner_id = :o"),
        {"o": lens.owner_id},
    ).scalar_one()
    assert status == "published"

    suspension.set(restricted_session, admin, lens.owner_id, True, "misleading", NOW)

    assert _paths(owner_session) == expected
    recorder = _Recorder()
    assert invalidation.drain(restricted_session, recorder, NOW) == len(expected)
    assert len(recorder.calls) == 1
    assert set(recorder.calls[0][0]) == expected


def test_lifting_a_suspension_enqueues_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    """Lifting republishes nothing, so there is nothing to evict.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    teacher = make_teacher(owner_session)
    _owner_listing(owner_session, teacher.owner_id, "rahim-sir", status="suspended")
    admin = PlatformAdminLens(account_id=make_teacher(owner_session).account_id)

    suspension.set(
        restricted_session, admin, teacher.owner_id, False, "misleading", NOW
    )

    assert _rows(owner_session) == []


def test_owner_unpublish_and_batch_unpublish_enqueue(
    owner_session: Session, restricted_session: Session
) -> None:
    """Unpublishing evicts the owner's prefix, or the one batch's pages.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _tutor(owner_session)

    batches.unpublish(restricted_session, lens, batch_id, NOW)
    assert _paths(owner_session) == {
        *invalidation.batch_paths("rahim-sir", "class-9-maths"),
        SITEMAP,
    }
    owner_session.execute(sa.text("TRUNCATE cdn_invalidation"))
    owner_session.commit()

    owner.unpublish(restricted_session, lens, NOW)
    assert _paths(owner_session) == {*invalidation.owner_paths("rahim-sir"), SITEMAP}
    owner_session.execute(sa.text("TRUNCATE cdn_invalidation"))
    owner_session.commit()

    # Unpublishing what is already hidden changes nothing and evicts nothing.
    owner.unpublish(restricted_session, lens, NOW)
    batches.unpublish(restricted_session, lens, batch_id, NOW)
    assert _rows(owner_session) == []


def test_slug_change_enqueues_old_path(
    owner_session: Session, restricted_session: Session
) -> None:
    """A live listing's old slug is evicted when the slug changes.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _tutor(owner_session)

    batches.upsert(
        restricted_session, lens, batch_id, BatchListingUpdate(slug="class-9-new")
    )
    assert _paths(owner_session) == {
        *invalidation.batch_paths("rahim-sir", "class-9-maths"),
        SITEMAP,
    }
    owner_session.execute(sa.text("TRUNCATE cdn_invalidation"))
    owner_session.commit()

    owner.update(restricted_session, lens, OwnerListingUpdate(slug="rahim-new"))
    assert _paths(owner_session) == {*invalidation.owner_paths("rahim-sir"), SITEMAP}
    owner_session.execute(sa.text("TRUNCATE cdn_invalidation"))
    owner_session.commit()

    # An edit that keeps the slug evicts nothing.
    owner.update(restricted_session, lens, OwnerListingUpdate(headline_en="Physics"))
    assert _rows(owner_session) == []


def test_slug_change_on_a_draft_enqueues_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    """A draft was never public, so its old slug was never cached.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    teacher = make_teacher(owner_session)
    _owner_listing(owner_session, teacher.owner_id, "rahim-sir", status="draft")
    lens = TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)

    owner.update(restricted_session, lens, OwnerListingUpdate(slug="rahim-new"))

    assert _rows(owner_session) == []


def test_hide_for_inactive_batch_enqueues(
    owner_session: Session, restricted_session: Session
) -> None:
    """Retiring a batch evicts its pages in the retirement's transaction.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, batch_id = _tutor(owner_session)

    update_batch(
        restricted_session,
        lens=lens,
        batch_id=batch_id,
        changes=BatchChanges(active=False),
    )

    assert _paths(owner_session) == {
        *invalidation.batch_paths("rahim-sir", "class-9-maths"),
        SITEMAP,
    }


def test_consent_withdrawal_enqueues_invalidation(
    owner_session: Session, restricted_session: Session
) -> None:
    """Review Focus 5: withdrawing consent evicts the centre's whole prefix.

    The owner page names teachers on its batch cards as the batch pages do,
    so the owner prefix -- which covers every batch page -- is enqueued
    rather than each batch path alone.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    centre = centre_with_manager(owner_session)
    member_id, account_id = add_member(
        owner_session, centre.owner_id, name="Karim Sir", consented=True
    )
    assign_slot(owner_session, centre.batch_id, member_id)
    _owner_listing(owner_session, centre.owner_id, "udoy-coaching")
    _batch_listing(owner_session, centre.owner_id, centre.batch_id, "class-9-maths")
    lens = CentreMemberLens(
        account_id=account_id, owner_id=centre.owner_id, member_id=member_id
    )

    set_public_name_consent(restricted_session, lens, False, NOW)
    assert _paths(owner_session) == {
        *invalidation.owner_paths("udoy-coaching"),
        SITEMAP,
    }
    owner_session.execute(sa.text("TRUNCATE cdn_invalidation"))
    owner_session.commit()

    # Withdrawing again, or agreeing, takes nothing down.
    set_public_name_consent(restricted_session, lens, False, NOW)
    set_public_name_consent(restricted_session, lens, True, NOW)
    assert _rows(owner_session) == []


def test_solo_owner_deletion_enqueues(
    owner_session: Session, restricted_session: Session
) -> None:
    """A solo owner who deletes their account has their prefix evicted.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens, _ = _tutor(owner_session)
    phone = owner_session.execute(
        sa.text("SELECT phone FROM account WHERE id = :a"), {"a": lens.account_id}
    ).scalar_one()

    delete_account(restricted_session, phone)

    assert _paths(owner_session) == {*invalidation.owner_paths("rahim-sir"), SITEMAP}


def test_drain_batches_and_stamps(
    owner_session: Session, restricted_session: Session
) -> None:
    """Unsent rows go oldest first in one request, up to the limit, stamped.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    later = NOW + dt.timedelta(seconds=1)
    invalidation.enqueue(restricted_session, invalidation.owner_paths("aaa"), NOW)
    invalidation.enqueue(
        restricted_session, invalidation.batch_paths("bbb", "ccc"), later
    )
    restricted_session.commit()
    recorder = _Recorder()

    sent = invalidation.drain(restricted_session, recorder, NOW, limit=3)

    assert sent == 3
    assert len(recorder.calls) == 1
    paths, reference = recorder.calls[0]
    assert set(paths) == {*invalidation.owner_paths("aaa"), SITEMAP}
    assert len(paths) == 3
    assert reference
    stamped = [r for r in _rows(owner_session) if r.sent_at is not None]
    assert len(stamped) == 3
    assert {r.aws_id for r in stamped} == {"I1EXAMPLE"}

    assert invalidation.drain(restricted_session, recorder, later, limit=50) == 3
    assert set(recorder.calls[1][0]) == {
        *invalidation.batch_paths("bbb", "ccc"),
        SITEMAP,
    }
    assert invalidation.drain(restricted_session, recorder, later) == 0
    assert len(recorder.calls) == 2
    assert all(r.sent_at is not None for r in _rows(owner_session))


def test_drain_sends_a_path_once_however_many_rows_carry_it(
    owner_session: Session, restricted_session: Session
) -> None:
    """Two takedowns' sitemap rows ride one batch as one path.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    invalidation.enqueue(restricted_session, invalidation.owner_paths("aaa"), NOW)
    invalidation.enqueue(restricted_session, invalidation.owner_paths("bbb"), NOW)
    restricted_session.commit()
    recorder = _Recorder()

    assert invalidation.drain(restricted_session, recorder, NOW) == 6

    paths = recorder.calls[0][0]
    assert len(paths) == len(set(paths)) == 5
    assert paths.count(SITEMAP) == 1
    assert all(r.sent_at == NOW for r in _rows(owner_session))


def test_drain_failure_increments_attempts_and_keeps_row(
    owner_session: Session,
    restricted_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed request leaves every row unsent, counted, and logged.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param caplog: The log capture
    :return: None
    """
    invalidation.enqueue(restricted_session, invalidation.owner_paths("aaa"), NOW)
    restricted_session.commit()

    with caplog.at_level(logging.WARNING):
        sent = invalidation.drain(restricted_session, _Recorder(fail=True), NOW)

    assert sent == 0
    rows = _rows(owner_session)
    assert len(rows) == 3
    assert all(r.sent_at is None and r.attempts == 1 for r in rows)
    assert "invalidation" in caplog.text

    recorder = _Recorder()
    assert invalidation.drain(restricted_session, recorder, NOW) == 3
    assert all(r.sent_at is not None for r in _rows(owner_session))


def test_drain_without_distribution_id_noops(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Locally there is no distribution: the drain logs and leaves the rows.

    The heartbeat is still stamped: the job ran and had nowhere to send,
    which is the normal state of a host with no site distribution.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param monkeypatch: The patcher
    :param caplog: The log capture
    :return: None
    """
    monkeypatch.delenv(cloudfront.DISTRIBUTION_ID_ENV, raising=False)
    invalidation.enqueue(restricted_session, invalidation.owner_paths("aaa"), NOW)
    restricted_session.commit()

    assert cloudfront.client_from_environment() is None
    with caplog.at_level(logging.INFO):
        result = commands.run_drain(restricted_session, now=NOW)

    assert result.sent == 0
    assert result.pending == 3
    assert "no site distribution" in caplog.text
    assert all(r.sent_at is None and r.attempts == 0 for r in _rows(owner_session))
    stamped = owner_session.execute(
        sa.text("SELECT last_success_at FROM job_heartbeat WHERE job_name = :j"),
        {"j": HUB_INVALIDATION_JOB},
    ).scalar_one()
    assert stamped == NOW


def test_run_drain_sends_with_the_configured_client(
    owner_session: Session, restricted_session: Session
) -> None:
    """The cron command drains through the client it is given.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    invalidation.enqueue(restricted_session, invalidation.owner_paths("aaa"), NOW)
    restricted_session.commit()
    recorder = _Recorder()

    result = commands.run_drain(restricted_session, now=NOW, client=recorder)

    assert (result.sent, result.pending, result.failed) == (3, 0, 0)
    assert len(recorder.calls) == 1


def test_takedown_route_drains_after_commit(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A takedown request drains its own rows once its transaction committed.

    :param api_client: The application under test
    :param owner_session: An arranging session
    :param monkeypatch: The patcher
    :return: None
    """
    lens, _ = _tutor(owner_session)
    recorder = _Recorder()
    monkeypatch.setattr(cloudfront, "client_from_environment", lambda: recorder)

    response = api_client.post(
        "/v1/hub/listing/unpublish", headers=bearer(owner_session, lens.account_id)
    )

    assert response.status_code == 200
    assert len(recorder.calls) == 1
    assert set(recorder.calls[0][0]) == {
        *invalidation.owner_paths("rahim-sir"),
        SITEMAP,
    }
    assert all(r.sent_at is not None for r in _rows(owner_session))


def test_a_failing_drain_never_reaches_the_response(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CloudFront failing after commit leaves the takedown done and counted.

    :param api_client: The application under test
    :param owner_session: An arranging session
    :param monkeypatch: The patcher
    :return: None
    """
    lens, _ = _tutor(owner_session)
    monkeypatch.setattr(
        cloudfront, "client_from_environment", lambda: _Recorder(fail=True)
    )

    response = api_client.post(
        "/v1/hub/listing/unpublish", headers=bearer(owner_session, lens.account_id)
    )

    assert response.status_code == 200
    rows = _rows(owner_session)
    assert rows
    assert all(r.sent_at is None and r.attempts == 1 for r in rows)


def test_a_request_that_enqueued_nothing_does_not_drain(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ordinary request never builds a client or touches the outbox.

    :param api_client: The application under test
    :param owner_session: An arranging session
    :param monkeypatch: The patcher
    :return: None
    """
    lens, _ = _tutor(owner_session)

    def _refuse() -> None:
        raise AssertionError("an ordinary request built an invalidation client")

    monkeypatch.setattr(cloudfront, "client_from_environment", _refuse)

    response = api_client.get(
        "/v1/hub/listing", headers=bearer(owner_session, lens.account_id)
    )

    assert response.status_code == 200


def test_cloudfront_client_sends_one_batch_to_the_distribution() -> None:
    """The boto3 client sends the paths as one batch to the named distribution.

    :return: None
    """
    sdk = boto3.client(
        "cloudfront",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",  # noqa: S106 - a stub, never sent
    )
    paths = invalidation.owner_paths("aaa")
    with Stubber(sdk) as stub:
        stub.add_response(
            "create_invalidation",
            {
                "Location": "https://cloudfront.amazonaws.com/x",
                "Invalidation": {
                    "Id": "I2J0EXAMPLE",
                    "Status": "InProgress",
                    "CreateTime": NOW,
                    "InvalidationBatch": {
                        "Paths": {"Quantity": 2, "Items": paths},
                        "CallerReference": "ref",
                    },
                },
            },
            {
                "DistributionId": "E123EXAMPLE",
                "InvalidationBatch": {
                    "Paths": {"Quantity": 2, "Items": paths},
                    "CallerReference": "ref",
                },
            },
        )
        client = cloudfront.CloudFrontInvalidationClient("E123EXAMPLE", sdk)

        assert client.create_invalidation(paths, "ref") == "I2J0EXAMPLE"
        stub.assert_no_pending_responses()


def test_client_from_environment_reads_the_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured distribution yields a client; a blank one yields none.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(cloudfront.DISTRIBUTION_ID_ENV, "  ")
    assert cloudfront.client_from_environment() is None

    monkeypatch.setenv(cloudfront.DISTRIBUTION_ID_ENV, "E123EXAMPLE")
    assert isinstance(
        cloudfront.client_from_environment(), cloudfront.CloudFrontInvalidationClient
    )
