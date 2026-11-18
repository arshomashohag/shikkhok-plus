"""``0043`` adds owner photos: ``listing_media``, its object outbox and view.

The view itself is probed as the hub reader in
``tests/privacy/test_hub_public_media_view.py``. Here: the enum, the two
tables' constraints, the governance entries, and that the downgrade
restores ``0042``'s shape -- and refuses while it would lose a photo or a
pending object deletion.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import MEDIA_STATUS_VALUES
from app.governance.deletion import HARD_DELETE_SCOPES, Scope
from app.governance.dispositions import DISPOSITIONS, Disposition, RetentionClass
from tests.batches.conftest import make_teacher
from tests.db.migration_support import _alembic_config, insert_account, stage_at

#: The seven statuses, in the order the enum declares them.
STATUSES: Final[tuple[str, ...]] = (
    "awaiting_upload",
    "processing",
    "pending_review",
    "approved",
    "rejected",
    "withdrawn",
    "held",
)


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0042``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0042") as engine:
        yield engine


def _media(
    session: Session,
    owner_id: uuid.UUID,
    *,
    status: str = "pending_review",
    batch_id: uuid.UUID | None = None,
    public_key: str | None = None,
    position: int = 0,
    dimensions: bool | None = None,
) -> uuid.UUID:
    """Insert one ``listing_media`` row.

    :param session: An arranging session
    :param owner_id: The owner
    :param status: Its status
    :param batch_id: Its batch, or None for an owner-level photo
    :param public_key: Its public key; required exactly when approved
    :param position: Its place in the gallery
    :param dimensions: Whether to store a width, height and widths; by
        default exactly when approved, which requires them
    :return: The media id
    """
    media_id = uuid.uuid4()
    sized = status == "approved" if dimensions is None else dimensions
    session.execute(
        sa.text(
            "INSERT INTO listing_media (id, owner_id, batch_id, status, "
            "content_type, byte_size, public_key, position, width, height, "
            "widths) VALUES "
            "(:id, :o, :b, CAST(:st AS media_status), 'image/jpeg', 1024, "
            ":key, :pos, :w, :h, :ws)"
        ),
        {
            "id": media_id,
            "o": owner_id,
            "b": batch_id,
            "st": status,
            "key": public_key,
            "pos": position,
            "w": 1200 if sized else None,
            "h": 800 if sized else None,
            "ws": [320, 960] if sized else None,
        },
    )
    return media_id


def _key() -> str:
    """Make a public key of the stored shape: 32 lower-case hex digits.

    :return: The key
    """
    return uuid.uuid4().hex


def test_0043_creates_media_tables_view_and_enum(staged: Engine) -> None:
    """Upgrade creates the enum, both tables and the view; downgrade drops all.

    :param staged: The engine staged at ``0042``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    command.upgrade(_alembic_config(url), "0043")

    with staged.connect() as connection:
        labels = tuple(
            connection.execute(
                sa.text(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'media_status' ORDER BY e.enumsortorder"
                )
            ).scalars()
        )
        kinds = dict(
            connection.execute(
                sa.text(
                    "SELECT relname, relkind::text FROM pg_class "
                    "WHERE relname IN ('listing_media', 'media_object_task', "
                    "'hub_public_media')"
                )
            ).all()
        )
    assert labels == STATUSES
    assert labels == MEDIA_STATUS_VALUES
    assert kinds == {
        "listing_media": "r",
        "media_object_task": "r",
        "hub_public_media": "v",
    }

    command.downgrade(_alembic_config(url), "0042")

    with staged.connect() as connection:
        left = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_class WHERE relname IN "
                "('listing_media', 'media_object_task', 'hub_public_media')"
            )
        ).scalar_one()
        enum_left = connection.execute(
            sa.text("SELECT count(*) FROM pg_type WHERE typname = 'media_status'")
        ).scalar_one()
    assert (left, enum_left) == (0, 0)


@pytest.mark.parametrize("table", ["listing_media", "media_object_task"])
def test_0043_downgrade_refuses_while_rows_would_be_lost(
    staged: Engine, table: str
) -> None:
    """A photo, or an object deletion not yet done, blocks the downgrade.

    Dropping ``listing_media`` loses what an owner uploaded and typed;
    dropping an undone ``media_object_task`` loses the only record that a
    photo's objects must still be deleted from the bucket.

    :param staged: The engine staged at ``0042``
    :param table: Which table holds the row
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    command.upgrade(_alembic_config(url), "0043")
    with staged.begin() as connection:
        if table == "listing_media":
            owner_id = uuid.uuid4()
            connection.execute(
                sa.text(
                    "INSERT INTO owner (id, account_id, created_at) "
                    "VALUES (:o, :a, now())"
                ),
                {"o": owner_id, "a": insert_account(connection, "+8801711000003")},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO listing_media (id, owner_id, content_type, "
                    "byte_size) VALUES (gen_random_uuid(), :o, 'image/png', 10)"
                ),
                {"o": owner_id},
            )
        else:
            connection.execute(
                sa.text(
                    "INSERT INTO media_object_task (op, prefix, requested_at) "
                    "VALUES ('delete', :p, now())"
                ),
                {"p": f"staged/{uuid.uuid4()}/"},
            )

    with pytest.raises(Exception, match="Cannot downgrade 0043"):
        command.downgrade(_alembic_config(url), "0042")


def test_0043_downgrade_allows_done_object_tasks(staged: Engine) -> None:
    """An outbox holding only finished deletions downgrades cleanly.

    :param staged: The engine staged at ``0042``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    command.upgrade(_alembic_config(url), "0043")
    with staged.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO media_object_task (op, prefix, requested_at, done_at) "
                "VALUES ('delete', :p, now(), now())"
            ),
            {"p": f"archive/{uuid.uuid4()}/"},
        )

    command.downgrade(_alembic_config(url), "0042")

    with staged.connect() as connection:
        gone = connection.execute(
            sa.text("SELECT to_regclass('media_object_task') IS NULL")
        ).scalar_one()
    assert gone is True


@pytest.mark.parametrize("status", STATUSES)
def test_public_key_iff_approved(owner_session: Session, status: str) -> None:
    """``approved`` needs a public key, and no other status may hold one.

    :param owner_session: An arranging session
    :param status: The status to try both ways
    :return: None
    """
    teacher = make_teacher(owner_session)
    wrong_key = None if status == "approved" else _key()

    with pytest.raises(
        IntegrityError, match="ck_listing_media_public_key_iff_approved"
    ):
        _media(owner_session, teacher.owner_id, status=status, public_key=wrong_key)
    owner_session.rollback()

    right_key = _key() if status == "approved" else None
    _media(owner_session, teacher.owner_id, status=status, public_key=right_key)
    owner_session.commit()


@pytest.mark.parametrize(
    ("width", "height", "widths"),
    [(None, 800, [320]), (1200, None, [320]), (1200, 800, None), (1200, 800, [])],
)
def test_approved_needs_dimensions_and_a_variant(
    owner_session: Session,
    width: int | None,
    height: int | None,
    widths: list[int] | None,
) -> None:
    """A public page renders an approved photo from its size and variants.

    :param owner_session: An arranging session
    :param width: The width to store
    :param height: The height to store
    :param widths: The variant widths to store
    :return: None
    """
    teacher = make_teacher(owner_session)
    media_id = _media(
        owner_session, teacher.owner_id, status="approved", public_key=_key()
    )
    owner_session.commit()

    with pytest.raises(IntegrityError, match="ck_listing_media_approved_dimensions"):
        owner_session.execute(
            sa.text(
                "UPDATE listing_media SET width = :w, height = :h, widths = :ws "
                "WHERE id = :m"
            ),
            {"w": width, "h": height, "ws": widths, "m": media_id},
        )
    owner_session.rollback()

    # Any other status may lack them: an upload has no size until decoded.
    _media(owner_session, teacher.owner_id, status="pending_review", dimensions=False)
    owner_session.commit()


@pytest.mark.parametrize(
    "key", ["../../etc/passwd", "ABCDEF0123456789ABCDEF0123456789", "abc"]
)
def test_public_key_is_32_lower_case_hex(owner_session: Session, key: str) -> None:
    """The key becomes an object prefix and a URL segment, so its shape is fixed.

    :param owner_session: An arranging session
    :param key: A key that is not 32 lower-case hex digits
    :return: None
    """
    teacher = make_teacher(owner_session)

    with pytest.raises(IntegrityError, match="ck_listing_media_public_key"):
        _media(owner_session, teacher.owner_id, status="approved", public_key=key)


def test_public_key_is_unique(owner_session: Session) -> None:
    """Two photos never share a public URL.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    key = _key()
    _media(owner_session, teacher.owner_id, status="approved", public_key=key)

    with pytest.raises(IntegrityError, match="uq_listing_media_public_key"):
        _media(
            owner_session,
            teacher.owner_id,
            status="approved",
            public_key=key,
            position=1,
        )


def test_approved_position_is_unique_per_gallery(owner_session: Session) -> None:
    """Two approved photos never share a slot in one gallery.

    The owner-level gallery (``batch_id IS NULL``) is one gallery and each
    batch's is another, so the same position in both is allowed; a photo
    not approved holds no slot.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    _media(owner_session, teacher.owner_id, status="approved", public_key=_key())
    _media(
        owner_session,
        teacher.owner_id,
        status="approved",
        public_key=_key(),
        batch_id=teacher.batch_id,
    )
    _media(owner_session, teacher.owner_id, status="pending_review")
    _media(owner_session, teacher.owner_id, status="held")
    owner_session.commit()

    with pytest.raises(IntegrityError, match="uq_listing_media_approved_position"):
        _media(owner_session, teacher.owner_id, status="approved", public_key=_key())
    owner_session.rollback()

    with pytest.raises(IntegrityError, match="uq_listing_media_approved_position"):
        _media(
            owner_session,
            teacher.owner_id,
            status="approved",
            public_key=_key(),
            batch_id=teacher.batch_id,
        )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("content_type", "image/gif"),
        ("content_type", "image/svg+xml"),
        ("byte_size", 0),
        ("byte_size", 8388609),
        ("widths", [320, 640]),
    ],
)
def test_upload_shape_is_constrained(
    owner_session: Session, column: str, value: object
) -> None:
    """Only the three types, 1 byte to 8 MiB, and the three variant names.

    :param owner_session: An arranging session
    :param column: The column given a value outside its shape
    :param value: That value
    :return: None
    """
    teacher = make_teacher(owner_session)
    values: dict[str, object] = {
        "content_type": "image/webp",
        "byte_size": 8388608,
        "widths": [320, 960, 1600],
    }
    values[column] = value

    with pytest.raises(IntegrityError, match=f"ck_listing_media_{column}"):
        owner_session.execute(
            sa.text(
                "INSERT INTO listing_media (id, owner_id, content_type, "
                "byte_size, widths) VALUES "
                "(gen_random_uuid(), :o, :ct, :size, CAST(:w AS smallint[]))"
            ),
            {
                "o": teacher.owner_id,
                "ct": values["content_type"],
                "size": values["byte_size"],
                "w": values["widths"],
            },
        )


def test_media_goes_with_its_owner_and_its_batch(owner_session: Session) -> None:
    """Both foreign keys cascade.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    _media(owner_session, teacher.owner_id)
    on_batch = _media(owner_session, teacher.owner_id, batch_id=teacher.batch_id)
    owner_session.commit()

    owner_session.execute(
        sa.text("DELETE FROM batch WHERE id = :b"), {"b": teacher.batch_id}
    )
    owner_session.commit()
    left = set(owner_session.execute(sa.text("SELECT id FROM listing_media")).scalars())
    assert on_batch not in left
    assert len(left) == 1

    owner_session.execute(
        sa.text("DELETE FROM owner WHERE id = :o"), {"o": teacher.owner_id}
    )
    owner_session.commit()
    assert (
        owner_session.execute(
            sa.text("SELECT count(*) FROM listing_media")
        ).scalar_one()
        == 0
    )


def _task(session: Session, prefix: str, op: str = "delete") -> None:
    """Insert one outbox row.

    :param session: An arranging session
    :param prefix: The object prefix to delete
    :param op: The operation
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO media_object_task (op, prefix, requested_at) "
            "VALUES (:op, :p, now())"
        ),
        {"op": op, "p": prefix},
    )


def test_object_task_prefix_shapes_only(owner_session: Session) -> None:
    """Exactly the four prefix shapes; anything wider is refused.

    A prefix that matched more than one photo's objects -- ``staged/``
    alone, ``public/`` with a traversal, a stray top-level prefix -- would
    let one delete task empty the bucket, so the shape is a CHECK.

    :param owner_session: An arranging session
    :return: None
    """
    media_id = uuid.uuid4()
    key = _key()
    for prefix in (
        f"quarantine/{media_id}",
        f"staged/{media_id}/",
        f"archive/{media_id}/",
        f"public/{key}/",
    ):
        _task(owner_session, prefix)
    owner_session.commit()

    for prefix in (
        "public/../x",
        "profile/",
        "staged/",
        "public/",
        "quarantine/",
        f"quarantine/{media_id}/",
        f"staged/{media_id}",
        f"staged/{media_id}/320.webp",
        f"public/{key}",
        f"public/{key.upper()}/",
        f"public/{media_id}/",
        f"archive/{str(media_id).upper()}/",
        f"/staged/{media_id}/",
        f"staged/{media_id}/\n",
    ):
        with pytest.raises(IntegrityError, match="ck_media_object_task_prefix"):
            _task(owner_session, prefix)
        owner_session.rollback()


def test_object_task_op_is_delete_only(owner_session: Session) -> None:
    """The outbox only deletes.

    :param owner_session: An arranging session
    :return: None
    """
    with pytest.raises(IntegrityError, match="ck_media_object_task_op"):
        _task(owner_session, f"staged/{uuid.uuid4()}/", op="copy")


def test_media_dispositions() -> None:
    """A solo owner's photos go with them; the outbox is about nobody.

    ``listing_media`` is reached through ``owner``, which deletion keeps,
    so it is ``SOLO_OWNER`` like the listings it illustrates: a centre's
    photos stay when a manager's account is deleted.

    :return: None
    """
    media = DISPOSITIONS["listing_media"]
    outbox = DISPOSITIONS["media_object_task"]

    assert (media.disposition, media.retention) == (
        Disposition.HARD_DELETE,
        RetentionClass.LIFE_OF_ACCOUNT,
    )
    assert (outbox.disposition, outbox.retention) == (
        Disposition.NOT_PERSONAL,
        RetentionClass.DAYS_7,
    )
    assert HARD_DELETE_SCOPES["listing_media"].scope is Scope.SOLO_OWNER
    assert HARD_DELETE_SCOPES["listing_media"].column == "owner_id"
    assert HARD_DELETE_SCOPES["media_object_task"].scope is Scope.NOT_PERSONAL


def test_dimensions_hold_a_wide_image_inside_the_pixel_cap(
    owner_session: Session,
) -> None:
    """A 40000 x 1000 image is 40M pixels, inside the decode cap, and fits.

    SMALLINT would overflow at 32767 and turn a valid upload's ``complete``
    into a server error.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    media_id = _media(owner_session, teacher.owner_id)
    owner_session.execute(
        sa.text("UPDATE listing_media SET width = 40000, height = 1000 WHERE id = :m"),
        {"m": media_id},
    )
    owner_session.commit()

    stored = owner_session.execute(
        sa.text("SELECT width, height FROM listing_media WHERE id = :m"),
        {"m": media_id},
    ).one()
    assert tuple(stored) == (40000, 1000)


def test_media_batch_must_belong_to_its_owner(owner_session: Session) -> None:
    """A photo cannot sit on another owner's batch, by insert or by update.

    An owner-level photo (``batch_id`` NULL) needs no batch at all.

    :param owner_session: An arranging session
    :return: None
    """
    one = make_teacher(owner_session)
    two = make_teacher(owner_session)
    own_level = _media(owner_session, one.owner_id)
    on_own_batch = _media(owner_session, one.owner_id, batch_id=one.batch_id)
    owner_session.commit()

    with pytest.raises(sa.exc.DBAPIError, match="does not match"):
        _media(owner_session, one.owner_id, batch_id=two.batch_id)
    owner_session.rollback()

    for column, value, media_id in (
        ("batch_id", two.batch_id, on_own_batch),
        ("batch_id", two.batch_id, own_level),
        ("owner_id", two.owner_id, on_own_batch),
    ):
        with pytest.raises(sa.exc.DBAPIError, match="does not match"):
            owner_session.execute(
                sa.text(
                    f"UPDATE listing_media SET {column} = :v "  # noqa: S608
                    "WHERE id = :m"
                ),
                {"v": value, "m": media_id},
            )
        owner_session.rollback()

    # Moving an owner-level photo to another owner keeps no batch, so it
    # is allowed; the guard concerns batches only.
    owner_session.execute(
        sa.text("UPDATE listing_media SET owner_id = :o WHERE id = :m"),
        {"o": two.owner_id, "m": own_level},
    )
    owner_session.commit()
