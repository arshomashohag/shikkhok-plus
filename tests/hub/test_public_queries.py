"""The public read service: search, owner and batch pages, the sitemap.

Every function here reads only the four public views, as the hub reader.
Rows are arranged as the table owner; the service is handed the
application role's session and drops to the reader itself, so the reader's
grants are the only thing these tests exercise.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Final

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import HUB_CLASS_LEVELS, Batch
from app.hub.public import normalise, queries
from app.hub.public.messages import t
from app.hub.public.settings import SITE_URL_ENV, site_url
from app.hub.public.views import HubBatchCard, HubOwnerCard
from app.money import Money
from tests.batches.conftest import make_teacher
from tests.hub.support import add_member, assign_slot, centre_with_manager

#: Dhaka district, Dhaka North City Corporation and its Mirpur thana.
DHAKA: Final[str] = "BD3026"
DNCC: Final[str] = "BD30262500"
MIRPUR: Final[str] = "MT3026250003"
#: Savar, a rural upazila of Dhaka district.
SAVAR: Final[str] = "BD30260072"
#: Chattogram district and one of its upazilas.
CHATTOGRAM: Final[str] = "BD2015"
SITAKUNDA: Final[str] = "BD20150086"

#: A fixed base for ``published_at``, so ordering is deterministic.
BASE: Final[dt.datetime] = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.UTC)


def _owner_listing(
    session: Session,
    owner_id: uuid.UUID,
    *,
    slug: str,
    status: str = "published",
    public_name: str | None = None,
    latin: str | None = None,
    headline_en: str | None = "Maths tutor",
    headline_bn: str | None = None,
    district: str | None = DHAKA,
    upazila: str | None = None,
    published_at: dt.datetime = BASE,
) -> None:
    """Insert one owner listing.

    :param session: An arranging session
    :param owner_id: The owner
    :param slug: The listing's slug
    :param status: The listing status
    :param public_name: The public name; defaults from the slug
    :param latin: The owner's Latin spelling of the name
    :param headline_en: The English headline
    :param headline_bn: The Bangla headline
    :param district: The district code
    :param upazila: The upazila, city corporation or metro thana code
    :param published_at: When it was published
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "public_name_latin, headline_en, headline_bn, bio_en, bio_bn, "
            "qualifications, district_code, upazila_code, "
            "public_contact_phone, published_at) VALUES "
            "(:o, :slug, CAST(:st AS hub_listing_status), :name, :latin, "
            ":hen, :hbn, 'Teaching since 2010', 'বিশ বছর', 'MSc', :d, :u, "
            "'+8801711000000', :at)"
        ),
        {
            "o": owner_id,
            "slug": slug,
            "st": status,
            "name": public_name or f"Name of {slug}",
            "latin": latin,
            "hen": headline_en,
            "hbn": headline_bn,
            "d": district,
            "u": upazila,
            "at": published_at,
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
    title: str = "Class 9 maths",
    class_levels: tuple[str, ...] = ("class_9",),
    subject_tags: tuple[str, ...] = ("maths",),
    show_fee: bool = True,
    show_schedule: bool = True,
) -> None:
    """Insert one batch listing.

    :param session: An arranging session
    :param batch_id: The batch
    :param owner_id: The batch's owner
    :param slug: The listing's slug
    :param status: The listing status
    :param title: The public title
    :param class_levels: The class levels taught
    :param subject_tags: The subject tags
    :param show_fee: Whether the fee is public
    :param show_schedule: Whether the timetable is public
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, slug, status, "
            "public_title, description_en, description_bn, syllabus_en, "
            "class_levels, subject_tags, curriculum, mode, show_fee, "
            "show_schedule, published_at) VALUES "
            "(:b, :o, :slug, CAST(:st AS hub_listing_status), :title, "
            "'Weekly practice', 'সাপ্তাহিক অনুশীলন', 'Algebra', "
            "CAST(:levels AS varchar[]), CAST(:tags AS varchar[]), "
            "'national_bangla', 'in_person', :fee, :sched, now())"
        ),
        {
            "b": batch_id,
            "o": owner_id,
            "slug": slug,
            "st": status,
            "title": title,
            "levels": list(class_levels),
            "tags": list(subject_tags),
            "fee": show_fee,
            "sched": show_schedule,
        },
    )
    session.commit()


def _tutor(
    session: Session, slug: str, **listing: object
) -> tuple[uuid.UUID, uuid.UUID]:
    """Arrange a solo tutor with a published owner listing, no batch listing.

    :param session: An arranging session
    :param slug: The owner's slug
    :param listing: Overrides for :func:`_owner_listing`
    :return: ``(owner_id, batch_id)``
    """
    teacher = make_teacher(session)
    _owner_listing(session, teacher.owner_id, slug=slug, **listing)  # type: ignore[arg-type]
    return teacher.owner_id, teacher.batch_id


def _extra_batch(
    session: Session, owner_id: uuid.UUID, *, active: bool = True
) -> uuid.UUID:
    """Give an owner one more batch.

    :param session: An arranging session
    :param owner_id: The owner
    :param active: Whether the batch is running
    :return: The batch id
    """
    batch = Batch(
        owner_id=owner_id,
        name="Private batch name",
        default_fee=Money("900.00"),
        fee_due_day=10,
        marksheet_visible=True,
        active=active,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(batch)
    session.commit()
    return batch.id


def _slugs(cards: list[HubOwnerCard]) -> list[str]:
    """Read the slugs of a result list, in order.

    :param cards: Search results
    :return: Their slugs
    """
    return [card.slug for card in cards]


def _search(session: Session, **kwargs: object) -> list[str]:
    """Search with every filter defaulted off, and return the result slugs.

    :param session: The application role's session
    :param kwargs: Overrides for the search arguments
    :return: The slugs, in rank order
    """
    arguments: dict[str, object] = {
        "locale": "en",
        "q": None,
        "district": None,
        "upazila": None,
        "subject": None,
        "level": None,
        "page": 1,
    }
    arguments.update(kwargs)
    page = queries.search(session, **arguments)  # type: ignore[arg-type]
    session.rollback()
    return _slugs(page.results)


def test_query_terms_normalise() -> None:
    """NFC, zero-width removal, Bangla digits, case, and the caps."""
    assert normalise.query_terms("  ঢাকা  PHYSICS ") == ["ঢাকা", "physics"]
    assert normalise.query_terms("মিরপুর‍") == ["মিরপুর"]
    assert normalise.query_terms("﻿ক্লাস ১০​") == ["ক্লাস", "10"]
    assert normalise.query_terms("a & b | !c (d):* 'e'") == ["a", "b", "c", "d", "e"]
    assert normalise.query_terms("   ") == []
    assert normalise.query_terms(" ".join(f"w{i}" for i in range(12))) == [
        f"w{i}" for i in range(8)
    ]
    assert normalise.query_terms("x" * 60) == ["x" * 40]
    # NFC: a decomposed sequence becomes its composed form.
    assert normalise.query_terms("é") == ["é"]


def test_class_levels_match_the_listing_vocabulary() -> None:
    """The public copy of the class-level vocabulary is the editor's own."""
    assert queries.CLASS_LEVELS == HUB_CLASS_LEVELS


def test_search_finds_by_bangla_and_latin_name(
    owner_session: Session, restricted_session: Session
) -> None:
    """The Bangla name, the owner's Latin spelling, and a prefix all match.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    _tutor(owner_session, "rahim-sir", public_name="রহিম স্যার", latin="Rahim Sir")
    _tutor(owner_session, "karim-sir", public_name="করিম স্যার", latin="Karim Sir")

    assert _search(restricted_session, q="রহিম") == ["rahim-sir"]
    assert _search(restricted_session, q="Rahim") == ["rahim-sir"]
    assert _search(restricted_session, q="rah") == ["rahim-sir"]
    assert _search(restricted_session, q="স্যার") == ["karim-sir", "rahim-sir"]
    assert _search(restricted_session, q="nobody") == []


def test_search_ranks_by_relevance_then_newest(
    owner_session: Session, restricted_session: Session
) -> None:
    """A closer match outranks a newer one; equal matches go newest first.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    strong_owner, strong_batch = _tutor(
        owner_session, "strong", headline_en="Physics physics", published_at=BASE
    )
    _batch_listing(owner_session, strong_batch, strong_owner, title="Physics")
    weak_owner, weak_batch = _tutor(
        owner_session,
        "weak",
        headline_en="Chemistry",
        published_at=BASE + dt.timedelta(days=1),
    )
    _batch_listing(owner_session, weak_batch, weak_owner, title="Physics")

    assert _search(restricted_session, q="physics") == ["strong", "weak"]
    assert _search(restricted_session, q=None) == ["weak", "strong"]


def test_search_normalises_bangla_input(
    owner_session: Session, restricted_session: Session
) -> None:
    """Review Focus 3: messy Bangla input matches and never raises.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    owner_id, batch_id = _tutor(
        owner_session,
        "rahim-sir",
        public_name="রহিম স্যার",
        latin="Rahim Sir",
        headline_bn="ঢাকায় মিরপুরে পদার্থবিজ্ঞান",
    )
    _batch_listing(
        owner_session,
        batch_id,
        owner_id,
        title="Class 10 physics",
        subject_tags=("physics",),
    )
    _tutor(owner_session, "other-tutor", headline_en="Chemistry")

    # Each spelling reaches the tutor; each term may match the owner's own
    # text or any of its batches' text.
    for q in (
        "ঢাকা  physics",
        "মিরপুর‍",
        "class ১০",
        "রহিম Sir",
        "​রহিম﻿",
    ):
        assert _search(restricted_session, q=q) == ["rahim-sir"], q

    # Input that is not a word at all is never an error.
    for q in ("a & b | !c", "'", "(:*", "\\", "‍", "   ", "ঢাকা" * 50):
        _search(restricted_session, q=q)


def test_search_matches_bangla_digits_typed_either_way(
    owner_session: Session, restricted_session: Session
) -> None:
    """A listing written with Bangla digits is found by Bangla or Latin digits.

    The stored text is normalised as the query is, so the digit set the
    owner typed and the one the reader types need not agree.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    owner_id, batch_id = _tutor(owner_session, "bangla-digits")
    _batch_listing(
        owner_session,
        batch_id,
        owner_id,
        title="ক্লাস \u09e7\u09e6 গণিত",
        subject_tags=("গণিত",),
    )
    _tutor(owner_session, "other-tutor", headline_en="Chemistry")

    for q in ("ক্লাস \u09e7\u09e6", "ক্লাস 10", "\u09e7\u09e6", "10"):
        assert _search(restricted_session, q=q) == ["bangla-digits"], q


def test_search_matches_precomposed_and_decomposed_bangla(
    owner_session: Session, restricted_session: Session
) -> None:
    """ড় and য় match whether the owner or the reader typed them precomposed.

    U+09DC (ড়) and U+09DF (য়) are NFC composition exclusions: NFC splits
    each into a base letter and a nukta. Both sides are normalised, so all
    four pairings match.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    precomposed_read = "প\u09dcাই"  # পড়াই with U+09DC
    decomposed_read = "প\u09a1\u09bcাই"  # the same word, base plus nukta
    precomposed_dhaka = "ঢাকা\u09df"  # ঢাকায় with U+09DF
    decomposed_dhaka = "ঢাকা\u09af\u09bc"
    _tutor(
        owner_session,
        "typed-precomposed",
        headline_bn=f"{precomposed_dhaka} {precomposed_read}",
    )
    owner_id, batch_id = _tutor(owner_session, "typed-decomposed", headline_bn=None)
    _batch_listing(
        owner_session,
        batch_id,
        owner_id,
        title=f"{decomposed_dhaka} {decomposed_read}",
    )

    for q in (precomposed_read, decomposed_read, precomposed_dhaka, decomposed_dhaka):
        assert set(_search(restricted_session, q=q)) == {
            "typed-precomposed",
            "typed-decomposed",
        }, ascii(q)


def test_search_filters_district_city_corporation_and_level(
    owner_session: Session, restricted_session: Session
) -> None:
    """Area, subject and level filters, and an unknown level ignored.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    arranged = {
        "mirpur": (DHAKA, MIRPUR, ("class_9",), ("Physics",)),
        "dncc": (DHAKA, DNCC, ("class_10",), ("maths",)),
        "savar": (DHAKA, SAVAR, ("class_10",), ("maths",)),
        "ctg": (CHATTOGRAM, SITAKUNDA, ("class_9",), ("maths",)),
    }
    for slug, (district, upazila, levels, tags) in arranged.items():
        owner_id, batch_id = _tutor(
            owner_session, f"t-{slug}", district=district, upazila=upazila
        )
        _batch_listing(
            owner_session, batch_id, owner_id, class_levels=levels, subject_tags=tags
        )

    def found(**kwargs: object) -> set[str]:
        return set(_search(restricted_session, **kwargs))

    assert found(district=DHAKA) == {"t-mirpur", "t-dncc", "t-savar"}
    assert found(upazila=DNCC) == {"t-mirpur", "t-dncc"}
    assert found(upazila=MIRPUR) == {"t-mirpur"}
    assert found(upazila=SAVAR) == {"t-savar"}
    assert found(level="class_9") == {"t-mirpur", "t-ctg"}
    assert found(level="class_9", district=DHAKA) == {"t-mirpur"}
    assert found(subject="physics") == {"t-mirpur"}
    assert found(level="not-a-level") == {f"t-{s}" for s in arranged}

    page = queries.search(
        restricted_session,
        locale="en",
        q=None,
        district=DHAKA,
        upazila=None,
        subject=None,
        level="not-a-level",
        page=1,
    )
    assert page.filters.level is None
    assert page.filters.district == DHAKA
    card = next(c for c in page.results if c.slug == "t-mirpur")
    assert card.area_names.model_dump() == {
        "en": "Mirpur, Dhaka",
        "bn": "মিরপুর, ঢাকা",
    }


def test_search_page_past_end_is_empty(
    owner_session: Session, restricted_session: Session
) -> None:
    """Twenty per page, newest first, and a page past the end is empty.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    for i in range(21):
        _tutor(
            owner_session, f"tutor-{i:02d}", published_at=BASE + dt.timedelta(hours=i)
        )

    def page(n: int) -> tuple[list[str], int, int, int]:
        found = queries.search(
            restricted_session,
            locale="en",
            q=None,
            district=None,
            upazila=None,
            subject=None,
            level=None,
            page=n,
        )
        restricted_session.rollback()
        return _slugs(found.results), found.page, found.pages, found.total

    first, number, pages, total = page(1)
    assert (number, pages, total) == (1, 2, 21)
    assert first == [f"tutor-{i:02d}" for i in range(20, 0, -1)]
    assert page(2)[0] == ["tutor-00"]
    assert page(3) == ([], 3, 2, 21)
    assert page(10**12)[0] == []
    assert page(0)[1] == 1


@pytest.mark.parametrize("status", ["draft", "hidden", "suspended"])
def test_owner_page_none_for_draft_hidden_suspended_missing(
    owner_session: Session, restricted_session: Session, status: str
) -> None:
    """Only a published owner has a page; it lists only its visible batches.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param status: An owner listing status that is not public
    :return: None
    """
    owner_id, batch_id = _tutor(owner_session, "live-tutor", upazila=MIRPUR)
    _batch_listing(owner_session, batch_id, owner_id)
    _batch_listing(
        owner_session,
        _extra_batch(owner_session, owner_id),
        owner_id,
        slug="draft-batch",
        status="draft",
    )
    dark_owner, dark_batch = _tutor(owner_session, "dark-tutor", status=status)
    _batch_listing(owner_session, dark_batch, dark_owner)

    assert queries.owner_page(restricted_session, "en", "dark-tutor") is None
    restricted_session.rollback()
    assert queries.owner_page(restricted_session, "en", "no-such-tutor") is None
    restricted_session.rollback()
    page = queries.owner_page(restricted_session, "bn", "live-tutor")

    assert page is not None
    assert page.owner.report_id == owner_id
    assert page.owner.area_names.model_dump() == {
        "en": "Mirpur, Dhaka",
        "bn": "মিরপুর, ঢাকা",
    }
    assert (page.headline, page.bio) == ("Maths tutor", "বিশ বছর")
    assert page.public_contact_phone == "+8801711000000"
    assert page.street_address is None
    assert [b.slug for b in page.batches] == ["class-9-maths"]


def test_batch_page_none_for_retired_or_unpublished_parent(
    owner_session: Session, restricted_session: Session
) -> None:
    """A batch page needs its listing, its batch and its owner all live.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    owner_id, batch_id = _tutor(owner_session, "live-tutor")
    _batch_listing(owner_session, batch_id, owner_id)
    retired = _extra_batch(owner_session, owner_id, active=False)
    _batch_listing(owner_session, retired, owner_id, slug="retired")
    drafty = _extra_batch(owner_session, owner_id)
    _batch_listing(owner_session, drafty, owner_id, slug="drafty", status="draft")
    hidden_owner, hidden_batch = _tutor(owner_session, "gone-tutor", status="hidden")
    _batch_listing(owner_session, hidden_batch, hidden_owner)

    def page(owner_slug: str, batch_slug: str) -> object:
        found = queries.batch_page(restricted_session, "en", owner_slug, batch_slug)
        restricted_session.rollback()
        return found

    assert page("live-tutor", "retired") is None
    assert page("live-tutor", "drafty") is None
    assert page("live-tutor", "missing") is None
    assert page("gone-tutor", "class-9-maths") is None
    assert page("other-tutor", "class-9-maths") is None

    live = queries.batch_page(restricted_session, "en", "live-tutor", "class-9-maths")
    assert live is not None
    assert live.owner.slug == "live-tutor"
    assert live.batch.report_id == batch_id
    assert (live.description, live.syllabus) == ("Weekly practice", "Algebra")
    assert live.batch.schedule == []


def test_centre_faculty_fallback_localised(
    owner_session: Session, restricted_session: Session
) -> None:
    """A centre names consented teachers, else "Centre faculty" per locale.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    centre = centre_with_manager(owner_session)
    unnamed, _ = add_member(owner_session, centre.owner_id, name="Hidden Sir")
    assign_slot(owner_session, centre.batch_id, unnamed)
    _owner_listing(owner_session, centre.owner_id, slug="udoy-coaching")
    _batch_listing(owner_session, centre.batch_id, centre.owner_id)
    solo_owner, solo_batch = _tutor(owner_session, "rahim-sir", public_name="রহিম")
    _batch_listing(owner_session, solo_batch, solo_owner)

    def names(locale: str, owner_slug: str) -> list[str]:
        found = queries.batch_page(
            restricted_session,
            locale,  # type: ignore[arg-type]
            owner_slug,
            "class-9-maths",
        )
        restricted_session.rollback()
        assert found is not None
        return found.batch.teacher_names

    assert names("en", "udoy-coaching") == ["Centre faculty"]
    assert names("bn", "udoy-coaching") == ["সেন্টারের শিক্ষকবৃন্দ"]
    assert t("centre_faculty", "bn") == "সেন্টারের শিক্ষকবৃন্দ"
    assert names("en", "rahim-sir") == ["রহিম"]

    named, _ = add_member(owner_session, centre.owner_id, consented=True)
    assign_slot(owner_session, centre.batch_id, named)
    assert names("bn", "udoy-coaching") == ["Karim Sir"]


def test_fee_formatted_by_money_module_only_when_shown(
    owner_session: Session, restricted_session: Session
) -> None:
    """The fee is a ``Money`` and its display is ``Money.format``; else None.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    shown_owner, shown_batch = _tutor(owner_session, "fee-shown")
    _batch_listing(owner_session, shown_batch, shown_owner)
    hidden_owner, hidden_batch = _tutor(owner_session, "fee-hidden")
    _batch_listing(
        owner_session, hidden_batch, hidden_owner, show_fee=False, show_schedule=False
    )

    def card(locale: str, owner_slug: str) -> HubBatchCard:
        found = queries.batch_page(
            restricted_session,
            locale,  # type: ignore[arg-type]
            owner_slug,
            "class-9-maths",
        )
        restricted_session.rollback()
        assert found is not None
        return found.batch

    bn = card("bn", "fee-shown")
    assert bn.fee == Money("1500.00")
    assert bn.fee_display == Money("1500.00").format("bn") == "৳1,500"
    assert card("en", "fee-shown").fee_display == Money("1500.00").format("en")
    hidden = card("bn", "fee-hidden")
    assert (hidden.fee, hidden.fee_display, hidden.schedule) == (None, None, None)


def test_sitemap_lists_only_published_with_both_locales(
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Published owners and batches, each in both locales with alternates.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(SITE_URL_ENV, "https://shikkhokplus.example/")
    owner_id, batch_id = _tutor(owner_session, "live-tutor")
    _batch_listing(owner_session, batch_id, owner_id)
    draft_owner, draft_batch = _tutor(owner_session, "draft-tutor", status="draft")
    _batch_listing(owner_session, draft_batch, draft_owner)
    hidden_owner, hidden_batch = _tutor(owner_session, "gone-tutor", status="hidden")
    _batch_listing(owner_session, hidden_batch, hidden_owner)

    found = queries.sitemap(restricted_session)

    origin = "https://shikkhokplus.example"
    paths = ["/t/live-tutor", "/t/live-tutor/class-9-maths"]
    assert [u.loc for u in found.urls] == [
        f"{origin}/hub/{locale}{path}" for path in paths for locale in ("en", "bn")
    ]
    for url in found.urls:
        path = url.loc.split("/hub/", 1)[1].split("/", 1)[1]
        assert [(a.hreflang, a.href) for a in url.alternates] == [
            ("en", f"{origin}/hub/en/{path}"),
            ("bn", f"{origin}/hub/bn/{path}"),
            ("x-default", f"{origin}/hub/en/{path}"),
        ]


def test_site_url_defaults_to_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset, the site origin is ``http://localhost``.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.delenv(SITE_URL_ENV, raising=False)
    assert site_url() == "http://localhost"
