"""The CloudFront invalidation outbox and every takedown path that feeds it.

Public owner and batch pages are cached at the edge for up to ten minutes,
so a takedown that only changed a row would leave the page served from the
cache. Every takedown therefore writes ``cdn_invalidation`` rows **in its own
transaction**: a rolled-back takedown leaves no row, and a committed one
cannot lose its row. Nothing in the container calls AWS [R8]: the host's
cron claims rows through ``app.hub.public.commands``, sends them with its own
AWS CLI, and acks or fails them; the container half is tested here, the host
script in ``tests/gates/test_hub_invalidation_host.py``.

Rows are arranged as the table owner; each service under test is handed the
application role's session, so the role's grants on the outbox are exercised.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Final

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.authz.lenses import CentreMemberLens, PlatformAdminLens, TeacherLens
from app.batches.service import BatchChanges, update_batch
from app.centres.service import revoke_member
from app.db.models import HUB_INVALIDATION_JOB, BatchSubject, Staff
from app.governance.deletion import delete_account
from app.hub.listings import batches, owner
from app.hub.listings.batches import BatchListingUpdate
from app.hub.listings.member_consent import set_public_name_consent
from app.hub.listings.owner import OwnerListingUpdate
from app.hub.public import commands, invalidation
from app.moderation import suspension
from app.money import Money
from app.staff.service import leave
from tests.batches.conftest import make_teacher
from tests.hub.support import (
    CentreFixture,
    add_member,
    assign_slot,
    centre_with_manager,
)

NOW: Final[dt.datetime] = dt.datetime(2026, 11, 17, 9, 0, tzinfo=dt.UTC)

#: Every enqueue carries the sitemap, which lists what a takedown removes.
SITEMAP: Final[str] = "/hub/sitemap.xml"


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
    the suspension is. Run for real, both commit together, and the next
    claim offers the owner's prefix in both locales with the sitemap.

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
    offered = commands.claim(restricted_session, now=NOW)
    assert set(offered.paths) == expected
    assert commands.ack(restricted_session, offered.ids, "I2J0EXAMPLE", NOW) == 3
    assert all(r.aws_id == "I2J0EXAMPLE" for r in _rows(owner_session))


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


def _named_member(
    session: Session, *, consented: bool = True
) -> tuple[CentreFixture, uuid.UUID, uuid.UUID]:
    """Arrange a published centre naming one teaching member, or not.

    :param session: An arranging session
    :param consented: Whether the member agreed to be named
    :return: ``(centre, member_id, member_account_id)``
    """
    centre = centre_with_manager(session)
    member_id, account_id = add_member(
        session, centre.owner_id, name="Karim Sir", consented=consented
    )
    assign_slot(session, centre.batch_id, member_id)
    _owner_listing(session, centre.owner_id, "udoy-coaching")
    _batch_listing(session, centre.owner_id, centre.batch_id, "class-9-maths")
    return centre, member_id, account_id


def _manager(centre: CentreFixture) -> TeacherLens:
    """Build the centre manager's lens.

    :param centre: The centre
    :return: The lens
    """
    return TeacherLens(account_id=centre.manager_account_id, owner_id=centre.owner_id)


def test_member_revocation_enqueues_invalidation(
    owner_session: Session, restricted_session: Session
) -> None:
    """A named member whose membership ends leaves the centre's pages.

    The same exposure as withdrawing consent, so the same owner prefix.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    centre, member_id, _ = _named_member(owner_session)

    revoke_member(
        restricted_session, lens=_manager(centre), member_id=member_id, now=NOW
    )

    assert _paths(owner_session) == {
        *invalidation.owner_paths("udoy-coaching"),
        SITEMAP,
    }


def test_revoking_an_unnamed_member_enqueues_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    """A member who never consented was on no page, so nothing is evicted.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    centre, member_id, _ = _named_member(owner_session, consented=False)

    revoke_member(
        restricted_session, lens=_manager(centre), member_id=member_id, now=NOW
    )

    assert _rows(owner_session) == []


def test_staff_leaving_enqueues_invalidation(
    owner_session: Session, restricted_session: Session
) -> None:
    """Recording that a named teacher left ends their membership and evicts.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    centre, member_id, _ = _named_member(owner_session)
    staff = Staff(
        owner_id=centre.owner_id,
        kind="teacher",
        display_name="Karim Sir",
        member_id=member_id,
        pay_basis="monthly",
        pay_rate=Money("8000.00"),
        joined_on=dt.date(2026, 1, 1),
        created_at=NOW,
    )
    owner_session.add(staff)
    owner_session.commit()

    leave(
        restricted_session,
        lens=_manager(centre),
        staff_id=staff.id,
        left_on=dt.date(2026, 11, 17),
        now=NOW,
    )

    assert _paths(owner_session) == {
        *invalidation.owner_paths("udoy-coaching"),
        SITEMAP,
    }


def test_named_member_account_deletion_enqueues(
    owner_session: Session, restricted_session: Session
) -> None:
    """A named member deleting their own account evicts the centre's pages.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    _, _, account_id = _named_member(owner_session)
    phone = owner_session.execute(
        sa.text("SELECT phone FROM account WHERE id = :a"), {"a": account_id}
    ).scalar_one()

    delete_account(restricted_session, phone)

    assert _paths(owner_session) == {
        *invalidation.owner_paths("udoy-coaching"),
        SITEMAP,
    }


def _heartbeat(session: Session) -> tuple[dt.datetime, int, int, int]:
    """Read this job's heartbeat row.

    :param session: The arranging session
    :return: ``(last_success_at, offered, still_waiting, retrying)``
    """
    session.rollback()
    row = session.execute(
        sa.text(
            "SELECT last_success_at, cycles_created, cycles_skipped, "
            "periods_failed FROM job_heartbeat WHERE job_name = :j"
        ),
        {"j": HUB_INVALIDATION_JOB},
    ).one()
    return row[0], row[1], row[2], row[3]


def test_claim_offers_oldest_first_up_to_limit_and_records_heartbeat(
    owner_session: Session, restricted_session: Session
) -> None:
    """A claim offers the oldest rows, de-duplicated, and stamps the job.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    invalidation.enqueue(restricted_session, invalidation.owner_paths("aaa"), NOW)
    invalidation.enqueue(
        restricted_session, invalidation.batch_paths("bbb", "ccc"), NOW
    )
    restricted_session.commit()

    first = commands.claim(restricted_session, limit=3, now=NOW)

    assert set(first.paths) == {*invalidation.owner_paths("aaa"), SITEMAP}
    assert first.ids == sorted(first.ids)
    assert len(first.ids) == 3
    assert str(uuid.UUID(first.caller_reference)) == first.caller_reference
    assert _heartbeat(owner_session) == (NOW, 3, 3, 0)

    # Claiming does not send: the same rows are offered until acked.
    again = commands.claim(restricted_session, limit=3, now=NOW)
    assert again.ids == first.ids
    assert again.caller_reference != first.caller_reference

    assert commands.ack(restricted_session, first.ids, "I1EXAMPLE", NOW) == 3
    second = commands.claim(restricted_session, now=NOW)
    assert set(second.paths) == {*invalidation.batch_paths("bbb", "ccc"), SITEMAP}
    assert commands.ack(restricted_session, second.ids, "I2EXAMPLE", NOW) == 3

    rows = _rows(owner_session)
    assert all(r.sent_at == NOW for r in rows)
    assert {r.aws_id for r in rows} == {"I1EXAMPLE", "I2EXAMPLE"}
    # A late ack for rows already sent changes nothing.
    assert commands.ack(restricted_session, first.ids, "I9EXAMPLE", NOW) == 0


def test_claim_offers_a_path_once_however_many_rows_carry_it(
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

    offered = commands.claim(restricted_session, now=NOW)

    assert len(offered.ids) == 6
    assert len(offered.paths) == len(set(offered.paths)) == 5
    assert offered.paths.count(SITEMAP) == 1
    assert commands.ack(restricted_session, offered.ids, "I1EXAMPLE", NOW) == 6
    assert all(r.sent_at == NOW for r in _rows(owner_session))


def test_empty_claim_still_records_heartbeat(
    owner_session: Session, restricted_session: Session
) -> None:
    """Nothing to send is the normal case, and the job still registers fresh.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    offered = commands.claim(restricted_session, now=NOW)

    assert offered.ids == []
    assert offered.paths == []
    assert json.loads(offered.to_json())["paths"] == []
    assert _heartbeat(owner_session) == (NOW, 0, 0, 0)


def test_fail_increments_attempts_and_keeps_row(
    owner_session: Session,
    restricted_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed send leaves every row unsent, counted, logged and offered again.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param caplog: The log capture
    :return: None
    """
    invalidation.enqueue(restricted_session, invalidation.owner_paths("aaa"), NOW)
    restricted_session.commit()
    offered = commands.claim(restricted_session, now=NOW)

    with caplog.at_level(logging.WARNING):
        assert commands.fail(restricted_session, offered.ids) == 3

    assert "invalidation failed" in caplog.text
    rows = _rows(owner_session)
    assert all(r.sent_at is None and r.attempts == 1 for r in rows)
    retried = commands.claim(restricted_session, now=NOW)
    assert retried.ids == offered.ids
    assert _heartbeat(owner_session) == (NOW, 3, 0, 3)


def test_ack_refuses_a_malformed_invalidation_id(
    restricted_session: Session,
) -> None:
    """Only a CloudFront-shaped id is stored.

    :param restricted_session: The application role's session
    :return: None
    """
    with pytest.raises(ValueError, match="invalidation id"):
        commands.ack(restricted_session, [1], "not an id", NOW)


@pytest.mark.parametrize("text", ["", "a,b", "0", "-1", "1,,x"])
def test_ids_must_be_positive_integers(text: str) -> None:
    """``--ids`` takes positive integers, comma-separated, and nothing else.

    :param text: A malformed argument
    :return: None
    """
    with pytest.raises(argparse.ArgumentTypeError):
        commands.parse_ids(text)


def test_command_line_claims_acks_and_fails(
    owner_session: Session,
    restricted_session: Session,
    restricted_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The verbs the host script runs, through their entry point.

    ``claim`` prints exactly one JSON line and nothing else on stdout.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param restricted_engine: The application role's engine
    :param monkeypatch: The patcher
    :param capsys: The output capture
    :return: None
    """
    monkeypatch.setattr(commands, "build_engine", lambda: restricted_engine)
    invalidation.enqueue(restricted_session, invalidation.owner_paths("aaa"), NOW)
    invalidation.enqueue(restricted_session, invalidation.owner_paths("bbb"), NOW)
    restricted_session.commit()

    assert commands.main(["claim", "--limit", "3"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    first = json.loads(out)
    assert set(first) == {"caller_reference", "ids", "paths"}
    assert len(first["ids"]) == 3

    ids = ",".join(str(i) for i in first["ids"])
    assert commands.main(["ack", "--ids", ids, "--aws-id", "I2J0EXAMPLE"]) == 0
    assert commands.main(["claim"]) == 0
    rest = json.loads(capsys.readouterr().out)
    rest_ids = ",".join(str(i) for i in rest["ids"])
    assert commands.main(["fail", "--ids", rest_ids]) == 0
    assert commands.main(["ack", "--ids", rest_ids, "--aws-id", "bad id"]) == 2
    assert capsys.readouterr().out == ""

    rows = _rows(owner_session)
    assert sum(r.aws_id == "I2J0EXAMPLE" for r in rows) == 3
    assert sum(r.sent_at is None and r.attempts == 1 for r in rows) == 3
