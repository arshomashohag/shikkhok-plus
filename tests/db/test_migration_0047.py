"""``0047`` adds join requests: ``listing_enquiry`` and the enquirable view.

The view's visibility -- who may be messaged at all -- is probed as the hub
reader in ``tests/privacy/test_hub_public_enquirable_view.py``, and the
90-day purge in ``tests/governance/test_enquiry_retention.py``. Here: the two
enums, ``owner_listing.accepts_enquiries``, the table's constraints and
cascades, and that the downgrade restores ``0046``'s shape -- and refuses
while a request exists.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from typing import Final

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import HUB_ENQUIRY_OUTCOME_VALUES, HUB_ENQUIRY_STATUS_VALUES
from app.db.roles import APP_ROLE
from tests.batches.conftest import _account, make_teacher
from tests.db.migration_support import _alembic_config, insert_account, stage_at
from tests.privacy.test_hub_public_views import _batch_listing, _owner_listing

#: Each enum ``0047`` creates and its labels, in declaration order.
ENUMS: Final[dict[str, tuple[str, ...]]] = {
    "hub_enquiry_status": ("open", "closed"),
    "hub_enquiry_outcome": ("added", "not_now", "call_us"),
}

#: The relations ``0047`` creates, and their kinds.
RELATIONS: Final[dict[str, str]] = {
    "listing_enquiry": "r",
    "hub_public_enquirable": "v",
}

#: The public views the application role is granted directly (Call 16).
APP_VIEWS: Final[tuple[str, ...]] = (
    "hub_public_batch",
    "hub_public_enquirable",
    "hub_public_owner",
)

#: The application role's direct grants on the public views, by ACL.
_DIRECT_APP_GRANTS: Final[str] = (
    "SELECT c.relname FROM pg_class c, aclexplode(c.relacl) g "
    "WHERE c.relname = ANY(:v) AND g.grantee = CAST(:r AS regrole) "
    "AND g.privilege_type = 'SELECT' ORDER BY c.relname"
)


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0046``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0046") as engine:
        yield engine


def _staged_listing(connection: Connection, phone: str) -> uuid.UUID:
    """Arrange a published solo listing in a staged database, by raw SQL.

    :param connection: An open connection to the staged database
    :param phone: The teacher's phone number, unique per call
    :return: The owner id
    """
    owner_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO owner (id, account_id, created_at) VALUES (:o, :a, now())"
        ),
        {"o": owner_id, "a": insert_account(connection, phone)},
    )
    connection.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "published_at) VALUES (:o, :s, 'published', 'Rahim Sir', now())"
        ),
        {"o": owner_id, "s": f"tutor-{owner_id.hex[:8]}"},
    )
    return owner_id


def _enquiry(
    session: Session,
    owner_id: uuid.UUID,
    *,
    enquirer: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    student_name: str = "Rafi",
    class_level: str = "class_9",
    message: str | None = None,
    share_contact: bool = True,
    status: str = "open",
    outcome: str | None = None,
    closed_at: dt.datetime | None = None,
) -> uuid.UUID:
    """Insert one join request by raw SQL, letting the server mint its id.

    :param session: An arranging session
    :param owner_id: The owner asked
    :param enquirer: The guardian's account; a fresh one by default
    :param batch_id: The class it is about, if any
    :param student_name: The name the guardian typed
    :param class_level: The class level the guardian chose
    :param message: The optional message
    :param share_contact: Whether the guardian shared their contact
    :param status: ``open`` or ``closed``
    :param outcome: The owner's answer
    :param closed_at: When it was closed
    :return: The new request's id
    """
    enquiry_id: uuid.UUID = session.execute(
        sa.text(
            "INSERT INTO listing_enquiry (owner_id, batch_id, "
            "enquirer_account_id, student_name, class_level, message, "
            "share_contact, status, outcome, created_at, closed_at) VALUES "
            "(:o, :b, :a, :name, :level, :msg, :share, "
            "CAST(:st AS hub_enquiry_status), CAST(:out AS hub_enquiry_outcome), "
            "now(), :closed) RETURNING id"
        ),
        {
            "o": owner_id,
            "b": batch_id,
            "a": enquirer if enquirer is not None else _account(session),
            "name": student_name,
            "level": class_level,
            "msg": message,
            "share": share_contact,
            "st": status,
            "out": outcome,
            "closed": closed_at,
        },
    ).scalar_one()
    return enquiry_id


def _listed_owner(session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    """Arrange a published solo listing with one published batch listing.

    :param session: An arranging session
    :return: ``(owner_id, batch_id)``
    """
    teacher = make_teacher(session)
    _owner_listing(session, teacher.owner_id, slug=f"t-{teacher.owner_id.hex[:8]}")
    _batch_listing(session, teacher.batch_id, teacher.owner_id)
    return teacher.owner_id, teacher.batch_id


def test_0047_creates_table_enums_view_and_column(staged: Engine) -> None:
    """Upgrade adds both enums, the table, the view and the column; downgrade drops all.

    A listing that exists before the upgrade is not opted in: being
    messaged by strangers is a second thing an owner agrees to (Call 3).
    The application role's direct grants on the two ``0040`` views go with
    the downgrade, so ``0046``'s ACLs come back exactly.

    :param staged: The engine staged at ``0046``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    with staged.begin() as connection:
        existing = _staged_listing(connection, "+8801711000470")
        before = connection.execute(
            sa.text(_DIRECT_APP_GRANTS), {"v": list(APP_VIEWS), "r": APP_ROLE}
        ).scalars()
        assert list(before) == []

    command.upgrade(_alembic_config(url), "0047")

    with staged.connect() as connection:
        labels = {
            name: tuple(
                connection.execute(
                    sa.text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = :n ORDER BY e.enumsortorder"
                    ),
                    {"n": name},
                ).scalars()
            )
            for name in ENUMS
        }
        kinds = dict(
            connection.execute(
                sa.text(
                    "SELECT relname, relkind::text FROM pg_class "
                    "WHERE relname = ANY(:r)"
                ),
                {"r": sorted(RELATIONS)},
            ).all()
        )
        accepts = connection.execute(
            sa.text("SELECT accepts_enquiries FROM owner_listing WHERE owner_id = :o"),
            {"o": existing},
        ).scalar_one()
        granted = list(
            connection.execute(
                sa.text(_DIRECT_APP_GRANTS), {"v": list(APP_VIEWS), "r": APP_ROLE}
            ).scalars()
        )
    assert labels == ENUMS
    assert (HUB_ENQUIRY_STATUS_VALUES, HUB_ENQUIRY_OUTCOME_VALUES) == tuple(
        ENUMS.values()
    )
    assert kinds == RELATIONS
    assert accepts is False
    assert granted == list(APP_VIEWS)

    command.downgrade(_alembic_config(url), "0046")

    with staged.connect() as connection:
        left = connection.execute(
            sa.text("SELECT count(*) FROM pg_class WHERE relname = ANY(:r)"),
            {"r": sorted(RELATIONS)},
        ).scalar_one()
        enums_left = connection.execute(
            sa.text("SELECT count(*) FROM pg_type WHERE typname = ANY(:n)"),
            {"n": sorted(ENUMS)},
        ).scalar_one()
        column_left = connection.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'owner_listing' "
                "AND column_name = 'accepts_enquiries'"
            )
        ).scalar_one()
        grants_left = list(
            connection.execute(
                sa.text(_DIRECT_APP_GRANTS), {"v": list(APP_VIEWS), "r": APP_ROLE}
            ).scalars()
        )
    assert (left, enums_left, column_left) == (0, 0, 0)
    assert grants_left == []


def test_downgrade_refuses_while_enquiries_exist(staged: Engine) -> None:
    """A request is what a guardian typed about a child and cannot be rebuilt.

    :param staged: The engine staged at ``0046``
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    command.upgrade(_alembic_config(url), "0047")
    with staged.begin() as connection:
        owner_id = _staged_listing(connection, "+8801711000471")
        connection.execute(
            sa.text(
                "INSERT INTO listing_enquiry (owner_id, enquirer_account_id, "
                "student_name, class_level, share_contact, created_at) VALUES "
                "(:o, :a, 'Rafi', 'class_9', false, now())"
            ),
            {"o": owner_id, "a": insert_account(connection, "+8801711000472")},
        )

    with pytest.raises(Exception, match="Cannot downgrade 0047"):
        command.downgrade(_alembic_config(url), "0046")


def test_share_contact_has_no_default(owner_session: Session) -> None:
    """Whether to share a number is the guardian's answer, never assumed.

    :param owner_session: An arranging session
    :return: None
    """
    owner_id, _ = _listed_owner(owner_session)

    with pytest.raises(IntegrityError, match="share_contact"):
        owner_session.execute(
            sa.text(
                "INSERT INTO listing_enquiry (owner_id, enquirer_account_id, "
                "student_name, class_level, created_at) VALUES "
                "(:o, :a, 'Rafi', 'class_9', now())"
            ),
            {"o": owner_id, "a": _account(owner_session)},
        )


def test_new_request_is_open_with_a_random_id(owner_session: Session) -> None:
    """A request starts open, unanswered, with a server-minted version-4 id.

    :param owner_session: An arranging session
    :return: None
    """
    owner_id, _ = _listed_owner(owner_session)
    enquiry_id = _enquiry(owner_session, owner_id)
    owner_session.commit()

    row = owner_session.execute(
        sa.text(
            "SELECT status::text, outcome, closed_at FROM listing_enquiry WHERE id = :e"
        ),
        {"e": enquiry_id},
    ).one()
    assert tuple(row) == ("open", None, None)
    assert enquiry_id.version == 4


@pytest.mark.parametrize(
    ("status", "outcome", "closed"),
    [
        ("closed", None, True),
        ("closed", "not_now", False),
        ("open", "not_now", False),
        ("open", None, True),
    ],
)
def test_closed_needs_outcome_and_time(
    owner_session: Session, status: str, outcome: str | None, closed: bool
) -> None:
    """A closed request carries both its answer and its time; an open one neither.

    :param owner_session: An arranging session
    :param status: The status tried
    :param outcome: The outcome tried
    :param closed: Whether a closing time is given
    :return: None
    """
    owner_id, _ = _listed_owner(owner_session)
    now = dt.datetime.now(tz=dt.UTC)

    with pytest.raises(IntegrityError, match="ck_listing_enquiry_"):
        _enquiry(
            owner_session,
            owner_id,
            status=status,
            outcome=outcome,
            closed_at=now if closed else None,
        )
    owner_session.rollback()

    _enquiry(owner_session, owner_id, status="closed", outcome="not_now", closed_at=now)
    _enquiry(owner_session, owner_id)
    owner_session.commit()


def test_added_needs_shared_contact(owner_session: Session) -> None:
    """``added`` is refused unless the guardian shared a contact (Call 7).

    Without a contact the owner cannot seat anyone, so the outcome would
    tell the guardian something untrue. The other outcomes need none.

    :param owner_session: An arranging session
    :return: None
    """
    owner_id, _ = _listed_owner(owner_session)
    now = dt.datetime.now(tz=dt.UTC)

    with pytest.raises(IntegrityError, match="ck_listing_enquiry_added_needs_contact"):
        _enquiry(
            owner_session,
            owner_id,
            share_contact=False,
            status="closed",
            outcome="added",
            closed_at=now,
        )
    owner_session.rollback()

    for outcome in ("not_now", "call_us"):
        _enquiry(
            owner_session,
            owner_id,
            share_contact=False,
            status="closed",
            outcome=outcome,
            closed_at=now,
        )
    _enquiry(
        owner_session,
        owner_id,
        share_contact=True,
        status="closed",
        outcome="added",
        closed_at=now,
    )
    owner_session.commit()


def test_one_open_per_owner_and_account(owner_session: Session) -> None:
    """A second open request to one owner is refused; a closed one beside it is not.

    The same guardian may ask another owner, and another guardian this one.

    :param owner_session: An arranging session
    :return: None
    """
    owner_id, _ = _listed_owner(owner_session)
    other_owner, _ = _listed_owner(owner_session)
    guardian = _account(owner_session)
    now = dt.datetime.now(tz=dt.UTC)
    _enquiry(owner_session, owner_id, enquirer=guardian)
    _enquiry(
        owner_session,
        owner_id,
        enquirer=guardian,
        status="closed",
        outcome="not_now",
        closed_at=now,
    )
    _enquiry(owner_session, other_owner, enquirer=guardian)
    _enquiry(owner_session, owner_id)
    owner_session.commit()

    with pytest.raises(IntegrityError, match="uq_listing_enquiry_open"):
        _enquiry(owner_session, owner_id, enquirer=guardian, student_name="Mitu")


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("student_name", "", "ck_listing_enquiry_student_name"),
        ("student_name", "   ", "ck_listing_enquiry_student_name"),
        ("student_name", "x" * 81, "ck_listing_enquiry_student_name"),
        ("message", "", "ck_listing_enquiry_message"),
        ("message", "x" * 301, "ck_listing_enquiry_message"),
        ("class_level", "class_13", "ck_listing_enquiry_class_level"),
    ],
)
def test_enquiry_content_bounds(
    owner_session: Session, column: str, value: str, constraint: str
) -> None:
    """A name is 1 to 80 characters, a message 1 to 300, a class a known level.

    :param owner_session: An arranging session
    :param column: The column given a value outside its bounds
    :param value: That value
    :param constraint: The CHECK that refuses it
    :return: None
    """
    owner_id, _ = _listed_owner(owner_session)
    _enquiry(owner_session, owner_id, student_name="x" * 80, message="x" * 300)
    _enquiry(owner_session, owner_id, student_name="R", message=None, class_level="ssc")
    owner_session.commit()

    with pytest.raises(IntegrityError, match=constraint):
        _enquiry(owner_session, owner_id, **{column: value})  # type: ignore[arg-type]


def test_cascades_follow_the_owner_of_each_row(owner_session: Session) -> None:
    """The guardian's account takes the request; the batch listing only unlinks it.

    :param owner_session: An arranging session
    :return: None
    """
    owner_id, batch_id = _listed_owner(owner_session)
    guardian = _account(owner_session)
    _enquiry(owner_session, owner_id, enquirer=guardian, batch_id=batch_id)
    _enquiry(owner_session, owner_id, batch_id=batch_id)
    owner_session.commit()

    def count(sql: str) -> int:
        return int(owner_session.execute(sa.text(sql)).scalar_one())

    owner_session.execute(
        sa.text("DELETE FROM batch_listing WHERE batch_id = :b"), {"b": batch_id}
    )
    owner_session.commit()
    assert count("SELECT count(*) FROM listing_enquiry") == 2
    assert count("SELECT count(*) FROM listing_enquiry WHERE batch_id IS NULL") == 2

    owner_session.execute(sa.text("DELETE FROM account WHERE id = :a"), {"a": guardian})
    owner_session.commit()
    assert count("SELECT count(*) FROM listing_enquiry") == 1
