"""``0040`` adds the public views, the search columns and the badge column.

The views themselves are probed as the hub reader in
``tests/privacy/test_hub_public_views.py``. Here: the columns, what the two
search vectors index, and that the downgrade restores ``0039``'s shape.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import HUB_SEARCH_NORM_FUNCTION, HUB_TAGS_TEXT_FUNCTION
from app.hub.public.normalise import query_terms
from tests.batches.conftest import make_teacher
from tests.db.migration_support import _alembic_config, stage_at


def _listing(
    session: Session, owner_id: uuid.UUID, *, latin: str | None = None
) -> None:
    """Insert one draft owner listing.

    :param session: An arranging session
    :param owner_id: The owner
    :param latin: The Latin transliteration of the public name, if any
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, public_name, public_name_latin, "
            "headline_bn, qualifications) VALUES "
            "(:o, 'রহিম স্যার', :latin, 'গণিত শিক্ষক', 'MSc Physics')"
        ),
        {"o": owner_id, "latin": latin},
    )
    session.commit()


def _matches(session: Session, table: str, term: str) -> int:
    """Count rows of a listing table whose search vector matches a term.

    :param session: Any session
    :param table: ``owner_listing`` or ``batch_listing``
    :param term: One word
    :return: The count
    """
    return int(
        session.execute(
            sa.text(
                f"SELECT count(*) FROM {table} "  # noqa: S608  test constants
                "WHERE search_text @@ to_tsquery('simple', :t)"
            ),
            {"t": term},
        ).scalar_one()
    )


def test_owner_search_text_indexes_latin_name_and_qualifications(
    owner_session: Session,
) -> None:
    """A Latin name and the qualifications are searchable beside the Bangla.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    _listing(owner_session, teacher.owner_id, latin="Rahim Sir")

    for term in ("rahim", "রহিম", "গণিত", "physics"):
        assert _matches(owner_session, "owner_listing", term) == 1, term


def test_owner_listing_new_columns_default(owner_session: Session) -> None:
    """``public_name_latin`` is optional and ``runs_classes`` starts false.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    _listing(owner_session, teacher.owner_id)

    row = owner_session.execute(
        sa.text("SELECT public_name_latin, runs_classes FROM owner_listing")
    ).one()
    assert tuple(row) == (None, False)
    with pytest.raises(sa.exc.DBAPIError):
        owner_session.execute(
            sa.text("UPDATE owner_listing SET public_name_latin = :v"),
            {"v": "a" * 121},
        )
    owner_session.rollback()


def test_batch_search_text_indexes_title_descriptions_and_tags(
    owner_session: Session,
) -> None:
    """The batch vector covers the title, both descriptions and the tags.

    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session)
    owner_session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, public_title, "
            "description_en, description_bn, subject_tags, show_fee, "
            "show_schedule) VALUES (:b, :o, 'Algebra crash course', "
            "'Weekly practice', 'সাপ্তাহিক অনুশীলন', '{chemistry,biology}', "
            "true, true)"
        ),
        {"b": teacher.batch_id, "o": teacher.owner_id},
    )
    owner_session.commit()

    for term in ("algebra", "practice", "অনুশীলন", "chemistry", "biology"):
        assert _matches(owner_session, "batch_listing", term) == 1, term


def test_batch_search_text_has_a_gin_index(owner_session: Session) -> None:
    """Search over batches is indexed like search over owners.

    :param owner_session: An arranging session
    :return: None
    """
    methods = dict(
        owner_session.execute(
            sa.text(
                "SELECT i.relname, am.amname FROM pg_index x "
                "JOIN pg_class i ON i.oid = x.indexrelid "
                "JOIN pg_class t ON t.oid = x.indrelid "
                "JOIN pg_am am ON am.oid = i.relam "
                "WHERE t.relname IN ('owner_listing', 'batch_listing') "
                "AND i.relname LIKE '%search_text'"
            )
        ).all()
    )

    assert methods == {
        "ix_owner_listing_search_text": "gin",
        "ix_batch_listing_search_text": "gin",
    }


@pytest.mark.parametrize(
    ("name", "definition"),
    [
        ("hub_tags_text", HUB_TAGS_TEXT_FUNCTION),
        ("hub_search_norm", HUB_SEARCH_NORM_FUNCTION),
    ],
)
def test_search_functions_match_the_models_and_are_immutable(
    owner_session: Session, name: str, definition: str
) -> None:
    """Each migrated function is the one the models describe, and immutable.

    :param owner_session: An arranging session
    :param name: The function
    :param definition: The models' ``CREATE FUNCTION`` for it
    :return: None
    """
    row = owner_session.execute(
        sa.text("SELECT prosrc, provolatile FROM pg_proc WHERE proname = :n"),
        {"n": name},
    ).one()

    assert row.provolatile == "i"
    assert "AS $$" + row.prosrc + "$$" in definition


def test_search_norm_matches_the_query_normaliser(owner_session: Session) -> None:
    """The stored-side normaliser agrees with ``query_terms`` term for term.

    :param owner_session: An arranging session
    :return: None
    """
    typed = "\u200bক্লাস \u09e7\u09e6 প\u09dcাই ঢাকা\u09df মিরপুর\u200d Physics e\u0301"
    stored = owner_session.execute(
        sa.text(
            "SELECT array_agg(lexeme ORDER BY lexeme) FROM "
            "unnest(to_tsvector('simple', hub_search_norm(:t)))"
        ),
        {"t": typed},
    ).scalar_one()

    assert stored == sorted(query_terms(typed))


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0040``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0040") as engine:
        yield engine


def _columns(engine: Engine, table: str) -> set[str]:
    """Read a table's column names.

    :param engine: The staged engine
    :param table: The table
    :return: Its columns
    """
    with engine.connect() as connection:
        return set(
            connection.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t"
                ),
                {"t": table},
            ).scalars()
        )


def _views(engine: Engine) -> set[str]:
    """Read the hub views present.

    :param engine: The staged engine
    :return: Their names
    """
    with engine.connect() as connection:
        return set(
            connection.execute(
                sa.text(
                    "SELECT viewname FROM pg_views WHERE viewname LIKE 'hub_public_%'"
                )
            ).scalars()
        )


def test_0040_downgrade_restores_0039_and_re_upgrades(staged: Engine) -> None:
    """Down drops the views and columns; up again rebuilds them.

    :param staged: The staged engine
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    assert len(_views(staged)) == 4

    command.downgrade(_alembic_config(url), "0039")

    assert _views(staged) == set()
    assert {"public_name_latin", "runs_classes"}.isdisjoint(
        _columns(staged, "owner_listing")
    )
    assert "search_text" in _columns(staged, "owner_listing")
    assert "search_text" not in _columns(staged, "batch_listing")

    command.upgrade(_alembic_config(url), "0040")

    assert len(_views(staged)) == 4
    assert {"public_name_latin", "runs_classes", "search_text"} <= _columns(
        staged, "owner_listing"
    )


def test_0040_downgrade_refuses_while_a_latin_name_is_held(staged: Engine) -> None:
    """A Latin name an owner typed is not silently dropped.

    :param staged: The staged engine
    :return: None
    """
    url = staged.url.render_as_string(hide_password=False)
    owner_id = uuid.uuid4()
    with staged.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO owner (id, account_id, created_at, kind, name) "
                "VALUES (:id, NULL, now(), 'organisation', 'Udoy Coaching')"
            ),
            {"id": owner_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO owner_listing (owner_id, public_name, "
                "public_name_latin) VALUES (:o, 'উদয়', 'Udoy')"
            ),
            {"o": owner_id},
        )

    with pytest.raises(Exception, match="Cannot downgrade 0040"):
        command.downgrade(_alembic_config(url), "0039")

    assert "public_name_latin" in _columns(staged, "owner_listing")
