"""The seven public hub views: what the hub reader can see, and nothing else.

Public pages read only ``hub_public_owner``, ``hub_public_batch``,
``hub_public_teacher_name``, ``hub_public_area``, ``hub_public_media``
(``0043``; its rows are probed in ``test_hub_public_media_view.py``), and
``hub_public_review`` and ``hub_public_rating`` (``0045``; probed in
``test_hub_public_review_view.py``), and only as ``shikkhok_hub_reader``.
A view runs with its owner's rights and bypasses row-level security, so
what a view selects IS the boundary: these tests read every view as the
reader and arrange rows as the table owner.
"""

from __future__ import annotations

import re
import uuid
from typing import Final

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.hub.public.db import as_hub_reader
from tests.batches.conftest import make_teacher
from tests.hub.support import add_member, assign_slot, centre_with_manager

#: The seven views public pages may read.
VIEWS: Final[frozenset[str]] = frozenset(
    {
        "hub_public_owner",
        "hub_public_batch",
        "hub_public_teacher_name",
        "hub_public_area",
        "hub_public_media",
        "hub_public_review",
        "hub_public_rating",
    }
)

#: Tables no view may read, by name.
PRIVATE_TABLES: Final[tuple[str, ...]] = (
    "profile",
    "account",
    "enrollment",
    "student",
    "payment_method",
)

#: Columns of readable tables that no view may read, by ``(table, column)``:
#: a class's private name, the number a centre typed for a member, and
#: everything that would join a review or reply to a person, a seat or a
#: moment finer than a month.
PRIVATE_COLUMNS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("batch", "name"),
        ("owner_member", "invited_phone"),
        ("review", "author_account_id"),
        ("review", "enrollment_id"),
        ("review", "submitted_at"),
        ("review", "edited_at"),
        ("review", "approved_at"),
        ("review", "decided_at"),
        ("review", "decided_by_account_id"),
        ("review_reply", "written_by_account_id"),
        ("review_reply", "created_at"),
        ("review_reply", "edited_at"),
        ("review_reply", "decided_at"),
        ("review_reply", "decided_by_account_id"),
    }
)


def _owner_listing(
    session: Session,
    owner_id: uuid.UUID,
    *,
    slug: str,
    status: str = "published",
    street_address: str | None = None,
) -> None:
    """Insert one owner listing with every field the views show.

    :param session: An arranging session
    :param owner_id: The owner
    :param slug: The listing's slug
    :param status: The listing status
    :param street_address: A centre's address, if any
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "headline_en, bio_bn, street_address, published_at) VALUES "
            "(:o, :slug, CAST(:st AS hub_listing_status), :name, 'Maths', "
            "'গণিত', :street, now())"
        ),
        {
            "o": owner_id,
            "slug": slug,
            "st": status,
            "name": f"Name of {slug}",
            "street": street_address,
        },
    )
    session.commit()


def _batch_listing(
    session: Session,
    batch_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    slug: str = "class-9-maths",
    status: str = "published",
    show_fee: bool = True,
    show_schedule: bool = True,
) -> None:
    """Insert one batch listing.

    :param session: An arranging session
    :param batch_id: The batch
    :param owner_id: The batch's owner
    :param slug: The listing's slug
    :param status: The listing status
    :param show_fee: Whether the fee is public
    :param show_schedule: Whether the timetable is public
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, slug, status, "
            "public_title, description_en, class_levels, subject_tags, "
            "show_fee, show_schedule, published_at) VALUES "
            "(:b, :o, :slug, CAST(:st AS hub_listing_status), 'Class 9 maths', "
            "'Weekly maths', '{class_9}', '{maths}', :fee, :sched, now())"
        ),
        {
            "b": batch_id,
            "o": owner_id,
            "slug": slug,
            "st": status,
            "fee": show_fee,
            "sched": show_schedule,
        },
    )
    session.commit()


def _slot(
    session: Session, batch_id: uuid.UUID, weekday: int, start: str, end: str
) -> None:
    """Add one weekly slot to a batch.

    :param session: An arranging session
    :param batch_id: The batch
    :param weekday: 0-6, Monday first
    :param start: ``HH:MM``
    :param end: ``HH:MM``
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO schedule_slot (id, batch_id, weekday, start_time, "
            "end_time) VALUES (gen_random_uuid(), :b, :w, "
            "CAST(:s AS time), CAST(:e AS time))"
        ),
        {"b": batch_id, "w": weekday, "s": start, "e": end},
    )
    session.commit()


def _published_tutor(session: Session, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Arrange a solo tutor with a published listing and published batch.

    :param session: An arranging session
    :param slug: The owner's slug
    :return: ``(owner_id, batch_id)``
    """
    teacher = make_teacher(session)
    _owner_listing(session, teacher.owner_id, slug=slug)
    _batch_listing(session, teacher.batch_id, teacher.owner_id)
    return teacher.owner_id, teacher.batch_id


def _visible(session: Session) -> dict[str, set[str]]:
    """Read every view's keys as the hub reader.

    :param session: The application role's session; left as the reader
    :return: Owner ids, batch ids, and ``batch_id:name`` pairs, as text
    """
    as_hub_reader(session)
    owners = session.execute(sa.text("SELECT owner_id FROM hub_public_owner"))
    batches = session.execute(sa.text("SELECT batch_id FROM hub_public_batch"))
    names = session.execute(
        sa.text("SELECT batch_id, name FROM hub_public_teacher_name")
    )
    return {
        "owners": {str(r[0]) for r in owners},
        "batches": {str(r[0]) for r in batches},
        "names": {f"{r[0]}:{r[1]}" for r in names},
    }


def test_hub_reader_reads_only_the_seven_views(restricted_session: Session) -> None:
    """The reader may SELECT the seven views and ``bd_area``, nothing else.

    ``listing_media`` and ``media_object_task`` (``0043``) are among the
    "nothing else": the reader sees a photo only through ``hub_public_media``.
    So are ``review`` and ``review_reply`` (``0045``): the reader sees a
    review only through ``hub_public_review`` and ``hub_public_rating``.

    ``bd_area`` was granted to the reader by ``0035`` (H0) and stays: the
    public area view is a passthrough of it. No relation is writable.

    :param restricted_session: A session as the application role
    :return: None
    """
    as_hub_reader(restricted_session)
    rows = restricted_session.execute(
        sa.text(
            "SELECT c.relname, has_table_privilege(c.oid, 'SELECT') AS can_read, "
            "has_table_privilege(c.oid, 'INSERT') OR "
            "has_table_privilege(c.oid, 'UPDATE') OR "
            "has_table_privilege(c.oid, 'DELETE') AS can_write "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'm', 'p', 'f')"
        )
    ).all()

    # Not vacuous: the whole schema was enumerated.
    assert len(rows) > 50
    assert {r.relname for r in rows if r.can_read} == VIEWS | {"bd_area"}
    assert [r.relname for r in rows if r.can_write] == []


def test_views_do_not_reference_private_tables(restricted_session: Session) -> None:
    """No view names a private table, or reads a private column, in text or in fact.

    The text is what a reviewer reads; ``pg_depend`` is what PostgreSQL
    resolved, so a column reached through an alias is still caught.

    :param restricted_session: A session as the application role
    :return: None
    """
    definitions = dict(
        restricted_session.execute(
            sa.text(
                "SELECT viewname, definition FROM pg_views "
                "WHERE schemaname = 'public' AND viewname = ANY(:v)"
            ),
            {"v": sorted(VIEWS)},
        ).all()
    )
    assert set(definitions) == VIEWS
    for view, text in definitions.items():
        for table in PRIVATE_TABLES:
            assert not re.search(rf"\b{table}\b", text), (view, table)
        assert not re.search(r"\b(batch|b)\.name\b", text), view

    depends = restricted_session.execute(
        sa.text(
            "SELECT DISTINCT v.relname AS view, t.relname AS tbl, "
            "a.attname AS col FROM pg_rewrite r "
            "JOIN pg_class v ON v.oid = r.ev_class "
            "JOIN pg_depend d ON d.classid = 'pg_rewrite'::regclass "
            "AND d.objid = r.oid "
            "JOIN pg_class t ON t.oid = d.refobjid "
            "LEFT JOIN pg_attribute a ON a.attrelid = t.oid "
            "AND a.attnum = d.refobjsubid "
            "WHERE v.relname = ANY(:v) AND t.oid <> v.oid"
        ),
        {"v": sorted(VIEWS)},
    ).all()
    tables = {row.tbl for row in depends}
    assert "owner_listing" in tables  # not vacuous
    assert tables.isdisjoint(PRIVATE_TABLES), tables
    read = {(row.tbl, row.col) for row in depends}
    assert ("review", "rating") in read  # the review columns are walked
    assert read.isdisjoint(PRIVATE_COLUMNS), sorted(read & PRIVATE_COLUMNS)


@pytest.mark.parametrize("status", ["draft", "hidden", "suspended"])
def test_draft_owner_absent_from_views(
    owner_session: Session, restricted_session: Session, status: str
) -> None:
    """An owner not published is in no view, nor is any batch under it.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :param status: An owner listing status that is not public
    :return: None
    """
    live_owner, live_batch = _published_tutor(owner_session, "live-tutor")
    teacher = make_teacher(owner_session)
    _owner_listing(owner_session, teacher.owner_id, slug="never-live", status=status)
    _batch_listing(owner_session, teacher.batch_id, teacher.owner_id)

    seen = _visible(restricted_session)

    assert seen["owners"] == {str(live_owner)}
    assert seen["batches"] == {str(live_batch)}


def test_batch_under_unpublished_owner_is_invisible_everywhere(
    owner_session: Session, restricted_session: Session
) -> None:
    """Unpublishing the owner hides batches whose own rows stay ``published``.

    Review Focus 1: the batch listing is not touched by an owner unpublish,
    so every view must check the owner listing as well.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    centre = centre_with_manager(owner_session)
    member, _ = add_member(owner_session, centre.owner_id, consented=True)
    assign_slot(owner_session, centre.batch_id, member)
    _owner_listing(owner_session, centre.owner_id, slug="udoy-coaching")
    _batch_listing(owner_session, centre.batch_id, centre.owner_id)

    before = _visible(restricted_session)
    restricted_session.rollback()
    assert before["batches"] == {str(centre.batch_id)}
    assert before["names"] == {f"{centre.batch_id}:Karim Sir"}

    owner_session.execute(
        sa.text("UPDATE owner_listing SET status = 'hidden' WHERE owner_id = :o"),
        {"o": centre.owner_id},
    )
    owner_session.commit()
    after = _visible(restricted_session)

    still = owner_session.execute(
        sa.text("SELECT status::text FROM batch_listing WHERE batch_id = :b"),
        {"b": centre.batch_id},
    ).scalar_one()
    assert still == "published"
    assert after == {"owners": set(), "batches": set(), "names": set()}


@pytest.mark.parametrize("status", ["draft", "hidden", "suspended"])
def test_unpublished_batch_listing_absent_under_published_owner(
    owner_session: Session, restricted_session: Session, status: str
) -> None:
    """A batch listing that is not itself published is in no batch view.

    The owner is published and a consented member teaches the batch, so
    the batch listing's own status is the only thing keeping it out.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :param status: A batch listing status that is not public
    :return: None
    """
    centre = centre_with_manager(owner_session)
    member, _ = add_member(owner_session, centre.owner_id, consented=True)
    assign_slot(owner_session, centre.batch_id, member)
    _owner_listing(owner_session, centre.owner_id, slug="udoy-coaching")
    _batch_listing(owner_session, centre.batch_id, centre.owner_id, status=status)

    seen = _visible(restricted_session)

    assert seen == {"owners": {str(centre.owner_id)}, "batches": set(), "names": set()}


def test_inactive_batch_absent(
    owner_session: Session, restricted_session: Session
) -> None:
    """A retired batch leaves the batch and teacher-name views.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    centre = centre_with_manager(owner_session)
    member, _ = add_member(owner_session, centre.owner_id, consented=True)
    assign_slot(owner_session, centre.batch_id, member)
    _owner_listing(owner_session, centre.owner_id, slug="udoy-coaching")
    _batch_listing(owner_session, centre.batch_id, centre.owner_id)
    owner_session.execute(
        sa.text("UPDATE batch SET active = false WHERE id = :b"),
        {"b": centre.batch_id},
    )
    owner_session.commit()

    seen = _visible(restricted_session)

    assert seen["owners"] == {str(centre.owner_id)}
    assert seen["batches"] == set()
    assert seen["names"] == set()


def test_fee_null_unless_show_fee(
    owner_session: Session, restricted_session: Session
) -> None:
    """The batch's default fee is public only where the owner chose it.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    shown = make_teacher(owner_session)
    _owner_listing(owner_session, shown.owner_id, slug="fee-shown")
    _batch_listing(owner_session, shown.batch_id, shown.owner_id, show_fee=True)
    hidden = make_teacher(owner_session)
    _owner_listing(owner_session, hidden.owner_id, slug="fee-hidden")
    _batch_listing(owner_session, hidden.batch_id, hidden.owner_id, show_fee=False)

    as_hub_reader(restricted_session)
    fees = dict(
        restricted_session.execute(
            sa.text("SELECT owner_slug, fee::text FROM hub_public_batch")
        ).all()
    )

    assert fees == {"fee-shown": "1500.00", "fee-hidden": None}


def test_schedule_null_unless_show_schedule(
    owner_session: Session, restricted_session: Session
) -> None:
    """The timetable is a JSON array of slots, or NULL when not shown.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    shown = make_teacher(owner_session)
    _owner_listing(owner_session, shown.owner_id, slug="times-shown")
    _batch_listing(owner_session, shown.batch_id, shown.owner_id, show_schedule=True)
    _slot(owner_session, shown.batch_id, 3, "18:30", "19:30")
    _slot(owner_session, shown.batch_id, 1, "16:00", "17:15")
    hidden = make_teacher(owner_session)
    _owner_listing(owner_session, hidden.owner_id, slug="times-hidden")
    _batch_listing(owner_session, hidden.batch_id, hidden.owner_id, show_schedule=False)
    _slot(owner_session, hidden.batch_id, 2, "10:00", "11:00")
    empty = make_teacher(owner_session)
    _owner_listing(owner_session, empty.owner_id, slug="times-empty")
    _batch_listing(owner_session, empty.batch_id, empty.owner_id, show_schedule=True)

    as_hub_reader(restricted_session)
    schedules = dict(
        restricted_session.execute(
            sa.text("SELECT owner_slug, schedule FROM hub_public_batch")
        ).all()
    )

    assert schedules == {
        "times-shown": [
            {"weekday": 1, "start": "16:00", "end": "17:15"},
            {"weekday": 3, "start": "18:30", "end": "19:30"},
        ],
        "times-hidden": None,
        "times-empty": [],
    }


def test_unconsented_member_absent_from_teacher_name_view(
    owner_session: Session, restricted_session: Session
) -> None:
    """Only accepted, unrevoked, consented members of the centre are named.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    centre = centre_with_manager(owner_session)
    for kwargs in (
        {"name": "Named Sir", "consented": True},
        {"name": "Unconsented Sir", "consented": False},
        {"name": "Revoked Sir", "consented": True, "revoked": True},
        {"name": "Pending Sir", "consented": True, "decision": "pending"},
    ):
        member, _ = add_member(owner_session, centre.owner_id, **kwargs)
        assign_slot(owner_session, centre.batch_id, member)
    _owner_listing(owner_session, centre.owner_id, slug="udoy-coaching")
    _batch_listing(owner_session, centre.batch_id, centre.owner_id)

    seen = _visible(restricted_session)

    assert seen["names"] == {f"{centre.batch_id}:Named Sir"}


def test_street_address_only_for_centres(
    owner_session: Session, restricted_session: Session
) -> None:
    """The owner view carries a centre's address and the owner ids report links use.

    :param owner_session: An arranging session
    :param restricted_session: A session as the application role
    :return: None
    """
    centre = centre_with_manager(owner_session)
    _owner_listing(
        owner_session,
        centre.owner_id,
        slug="udoy-coaching",
        street_address="12 Lake Road",
    )

    as_hub_reader(restricted_session)
    row = restricted_session.execute(
        sa.text(
            "SELECT owner_id, kind::text AS kind, street_address, runs_classes "
            "FROM hub_public_owner"
        )
    ).one()

    assert (row.owner_id, row.kind, row.street_address, row.runs_classes) == (
        centre.owner_id,
        "organisation",
        "12 Lake Road",
        False,
    )


def test_views_are_security_barrier(restricted_session: Session) -> None:
    """Every public view is declared ``security_barrier``.

    :param restricted_session: A session as the application role
    :return: None
    """
    options = dict(
        restricted_session.execute(
            sa.text(
                "SELECT c.relname, c.reloptions FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = ANY(:v) "
                "AND c.relkind = 'v'"
            ),
            {"v": sorted(VIEWS)},
        ).all()
    )

    assert set(options) == VIEWS
    assert {v: "security_barrier=true" in (o or []) for v, o in options.items()} == {
        v: True for v in VIEWS
    }
