"""What account deletion and batch retirement do to a photo's objects [H3 Task 8].

A solo owner's photos are hard-deleted with their account, and a row is not
the photo: the bucket holds ``quarantine/{id}``, ``staged/{id}/``,
``archive/{id}/`` and, while approved, ``public/{key}/``, and the edge caches
``/m/{key}/*``. Every one of those is enqueued in the deletion's transaction,
read before the rows go [Review Focus 5].

A retired batch is the other case [H3 deviation 4]: its photos stay as rows,
leave the page through ``hub_public_media`` (which shows a batch photo only
under an active batch), and no object is deleted.

Rows are arranged as the table owner; the deletion and the retirement run
through the application role's session, so its grants are what is tested.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import BatchChanges, update_batch
from app.governance.deletion import delete_account
from app.hub.media.objects import UPLOAD_WINDOW
from app.hub.media.storage import OBJECT_PREFIX
from app.hub.public import invalidation
from app.hub.public.db import as_hub_reader
from tests.hub.media.support import media_row
from tests.hub.support import add_member, centre_with_manager
from tests.hub.test_public_routes import _published_tutor

#: Every status a photo can be in [0043].
STATUSES: Final[tuple[str, ...]] = (
    "awaiting_upload",
    "processing",
    "pending_review",
    "approved",
    "rejected",
    "withdrawn",
    "held",
)


@dataclass(frozen=True, slots=True)
class _Photo:
    """One arranged photo.

    :ivar media_id: Its id
    :ivar status: Its status
    :ivar public_key: Its key, while approved
    :ivar created_at: When its upload was signed
    """

    media_id: uuid.UUID
    status: str
    public_key: str | None
    created_at: dt.datetime


@dataclass(frozen=True, slots=True)
class _Task:
    """One object-outbox row.

    :ivar prefix: What it deletes
    :ivar requested_at: When it falls due
    """

    prefix: str
    requested_at: dt.datetime


def _phone(session: Session, account_id: uuid.UUID) -> str:
    """Read an account's number.

    :param session: A session
    :param account_id: The account
    :return: Its phone number
    """
    return str(
        session.execute(
            sa.text("SELECT phone FROM account WHERE id = :a"), {"a": account_id}
        ).scalar_one()
    )


def _photos(session: Session, owner_id: uuid.UUID, batch_id: uuid.UUID) -> list[_Photo]:
    """Arrange one photo in every status, plus a second approved one on a batch.

    The in-flight photos were signed a minute ago, so their upload window is
    still open when the deletion runs on the real clock.

    :param session: The arranging session
    :param owner_id: The owner
    :param batch_id: One of the owner's batches
    :return: The photos
    """
    signed = dt.datetime.now(tz=dt.UTC) - dt.timedelta(minutes=1)
    ids = [
        media_row(session, owner_id, status=status, created_at=signed)
        for status in STATUSES
    ]
    ids.append(
        media_row(
            session, owner_id, status="approved", batch_id=batch_id, created_at=signed
        )
    )
    rows = session.execute(
        sa.text(
            "SELECT id, status::text AS status, public_key, created_at "
            "FROM listing_media WHERE id = ANY(:ids)"
        ),
        {"ids": ids},
    ).all()
    return [_Photo(r.id, r.status, r.public_key, r.created_at) for r in rows]


def _tasks(session: Session) -> list[_Task]:
    """Read every object-outbox row.

    :param session: The arranging session
    :return: The rows, oldest first
    """
    session.rollback()
    return [
        _Task(r.prefix, r.requested_at)
        for r in session.execute(
            sa.text("SELECT prefix, requested_at FROM media_object_task ORDER BY id")
        )
    ]


def _paths(session: Session) -> set[str]:
    """Read every CDN outbox path.

    :param session: The arranging session
    :return: The paths
    """
    session.rollback()
    return set(session.execute(sa.text("SELECT path FROM cdn_invalidation")).scalars())


def _expected_prefixes(photo: _Photo) -> set[str]:
    """Every prefix one photo may have objects under.

    :param photo: The photo
    :return: The prefixes
    """
    wanted = {
        f"quarantine/{photo.media_id}",
        f"staged/{photo.media_id}/",
        f"archive/{photo.media_id}/",
    }
    if photo.public_key is not None:
        wanted.add(f"public/{photo.public_key}/")
    return wanted


def _visible(session: Session) -> set[uuid.UUID]:
    """Read the public view as the hub reader, then end the transaction.

    :param session: The application role's session
    :return: The media ids the public pages show
    """
    as_hub_reader(session)
    seen = set(
        session.execute(sa.text("SELECT media_id FROM hub_public_media")).scalars()
    )
    session.rollback()
    return seen


def test_solo_owner_deletion_removes_media_rows_and_enqueues_objects(
    owner_session: Session, restricted_session: Session
) -> None:
    """Review Focus 5: no row survives, every prefix and ``/m/`` path is queued.

    Every status is present, so a held photo -- no key, its public objects
    already gone -- still has ``staged/`` and ``archive/`` deleted, and the
    two in-flight photos have ``quarantine/`` and ``staged/`` queued a second
    time, due when their upload window closes.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    account_id, owner_id, batch_id = _published_tutor(owner_session)
    photos = _photos(owner_session, owner_id, batch_id)
    approved = [p.public_key for p in photos if p.public_key is not None]
    assert len(approved) == 2

    result = delete_account(restricted_session, _phone(owner_session, account_id))

    assert result.rows_deleted["listing_media"] == len(photos)
    remaining = owner_session.execute(
        sa.text("SELECT count(*) FROM listing_media WHERE owner_id = :o"),
        {"o": owner_id},
    ).scalar_one()
    assert remaining == 0

    tasks = _tasks(owner_session)
    wanted = set().union(*(_expected_prefixes(p) for p in photos))
    assert {t.prefix for t in tasks} == wanted

    held = next(p for p in photos if p.status == "held")
    assert {f"staged/{held.media_id}/", f"archive/{held.media_id}/"} <= {
        t.prefix for t in tasks
    }

    for photo in photos:
        later = sorted(
            t.prefix
            for t in tasks
            if t.prefix in {f"quarantine/{photo.media_id}", f"staged/{photo.media_id}/"}
            and t.requested_at == photo.created_at + UPLOAD_WINDOW
        )
        if photo.status in ("awaiting_upload", "processing"):
            assert later == [
                f"quarantine/{photo.media_id}",
                f"staged/{photo.media_id}/",
            ]
        else:
            assert later == []

    paths = _paths(owner_session)
    for key in approved:
        assert invalidation.media_paths(key)[0] in paths
    assert {p for p in paths if p.startswith("/m/")} == {
        f"/m/{key}/*" for key in approved
    }
    assert set(invalidation.owner_paths("rahim-sir")) <= paths


def test_centre_media_survive_manager_deletion(
    owner_session: Session, restricted_session: Session
) -> None:
    """A centre's photos, and their objects, outlive a manager's account.

    Neither the manager's deletion nor a teaching member's touches the
    centre's approved photo: it keeps its row and its key, no object of it is
    queued, and its ``/m/`` path is not evicted.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    centre = centre_with_manager(owner_session)
    centre_photo = media_row(owner_session, centre.owner_id, status="approved")
    key = owner_session.execute(
        sa.text("SELECT public_key FROM listing_media WHERE id = :m"),
        {"m": centre_photo},
    ).scalar_one()
    _, other_account = add_member(owner_session, centre.owner_id, name="Karim Sir")

    delete_account(restricted_session, _phone(owner_session, centre.manager_account_id))
    delete_account(restricted_session, _phone(owner_session, other_account))

    owner_session.rollback()
    survivor = owner_session.execute(
        sa.text("SELECT status::text, public_key FROM listing_media WHERE id = :m"),
        {"m": centre_photo},
    ).one()
    assert tuple(survivor) == ("approved", key)
    assert _tasks(owner_session) == []
    assert not any(p.startswith("/m/") for p in _paths(owner_session))


def test_retired_batch_photos_leave_page_without_object_deletes(
    owner_session: Session, restricted_session: Session
) -> None:
    """Deviation 4: a retired batch unlinks its photos and deletes no object.

    The photo stays approved with its key -- so bringing the batch back and
    republishing shows it again -- leaves ``hub_public_media`` because the
    batch is no longer active, and the only outbox rows are the batch page's
    eviction and the sitemap.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    account_id, owner_id, batch_id = _published_tutor(owner_session)
    photo = media_row(owner_session, owner_id, status="approved", batch_id=batch_id)
    key = owner_session.execute(
        sa.text("SELECT public_key FROM listing_media WHERE id = :m"), {"m": photo}
    ).scalar_one()
    assert photo in _visible(restricted_session)

    update_batch(
        restricted_session,
        lens=TeacherLens(account_id=account_id, owner_id=owner_id),
        batch_id=batch_id,
        changes=BatchChanges(active=False),
    )

    assert photo not in _visible(restricted_session)
    owner_session.rollback()
    kept = owner_session.execute(
        sa.text("SELECT status::text, public_key FROM listing_media WHERE id = :m"),
        {"m": photo},
    ).one()
    assert tuple(kept) == ("approved", key)
    assert _tasks(owner_session) == []
    assert _paths(owner_session) == {
        *invalidation.batch_paths("rahim-sir", "class-9-maths"),
        invalidation.SITEMAP_PATH,
    }


def test_every_enqueued_prefix_matches_the_check_shapes(
    owner_session: Session, restricted_session: Session
) -> None:
    """Every prefix a deletion queues satisfies ``ck_media_object_task_prefix``.

    Checked against the database's own CHECK expression, read from the
    catalogue and evaluated over every queued row, as well as the
    application's :data:`OBJECT_PREFIX` -- over a fixture holding every
    status, so all four shapes are exercised -- and every prefix names one of
    the deleted photos, never a wider folder or another owner's.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    account_id, owner_id, batch_id = _published_tutor(owner_session)
    photos = _photos(owner_session, owner_id, batch_id)

    delete_account(restricted_session, _phone(owner_session, account_id))

    tasks = _tasks(owner_session)
    assert {t.prefix.split("/", 1)[0] for t in tasks} == {
        "quarantine",
        "staged",
        "archive",
        "public",
    }
    for task in tasks:
        assert OBJECT_PREFIX.fullmatch(task.prefix), task.prefix

    check = owner_session.execute(
        sa.text(
            "SELECT pg_get_expr(conbin, conrelid) FROM pg_constraint "
            "WHERE conname = 'ck_media_object_task_prefix'"
        )
    ).scalar_one()
    failing = owner_session.execute(
        sa.text(
            f"SELECT prefix FROM media_object_task WHERE NOT ({check})"  # noqa: S608
        )
    ).all()
    assert failing == []

    owned = set().union(*(_expected_prefixes(p) for p in photos))
    assert {t.prefix for t in tasks} <= owned
