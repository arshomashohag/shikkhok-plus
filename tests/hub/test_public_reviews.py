"""Reviews and ratings on the public pages, and search sorted by rating.

Every request goes through the real application against the restricted
database role, and every rating and review reaches a page only through
``hub_public_rating`` and ``hub_public_review`` as the hub reader. Rows are
arranged as the table owner.

The threshold is the views' [Task 2]; these tests prove the pages add
nothing the views withhold. Below three published reviews a batch shows the
same line whatever its count -- 0, 1 or 2 -- so the page says nothing a
teacher who knows which family just became eligible could use [F18, T9-a].
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from html.parser import HTMLParser
from typing import Final

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.html import HUB_PAGE_CSP
from app.contract.privacy import REVIEW_FORBIDDEN_FIELDS
from app.hub.public import queries
from app.hub.public.messages import MESSAGES, Locale, t
from app.hub.public.ratings import month_label, tenths_label
from app.hub.public.registry import registered_views
from app.hub.public.settings import SITE_URL_ENV, WEB_APP_URL_ENV
from app.hub.public.views import HubReply, HubReview, RatingSummary
from tests.batches.conftest import _account, make_teacher
from tests.conftest import bearer

SITE: Final[str] = "https://site.example.test"
WEB_APP: Final[str] = "https://app.example.test"

#: The page CSP, verbatim from the plan's global constraints.
PAGE_CSP: Final[str] = (
    "default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)

#: The month published reviews carry unless a test says otherwise.
NOVEMBER: Final[dt.date] = dt.date(2026, 11, 1)
OCTOBER: Final[dt.date] = dt.date(2026, 10, 1)

#: A fixed base for ``published_at``, so relevance order is deterministic.
BASE: Final[dt.datetime] = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.UTC)

#: The batch slug every tutor here lists.
BATCH: Final[str] = "class-9-maths"

#: The review section, as a page renders it.
_SECTION: Final[re.Pattern[str]] = re.compile(
    r'<section class="reviews".*?</section>', re.DOTALL
)


def _client(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Point the page settings at distinctive origins.

    :param api_client: The test client
    :param monkeypatch: The patcher
    :return: The same client
    """
    monkeypatch.setenv(SITE_URL_ENV, SITE)
    monkeypatch.setenv(WEB_APP_URL_ENV, WEB_APP)
    return api_client


def _tutor(
    session: Session,
    slug: str,
    *,
    published_at: dt.datetime = BASE,
    batch_slug: str = BATCH,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Arrange a published tutor with one published batch.

    :param session: An arranging session
    :param slug: The owner's slug, also its public name
    :param published_at: When the owner listing was published
    :param batch_slug: The batch listing's slug
    :return: ``(owner_id, batch_id)``
    """
    teacher = make_teacher(session, name=f"Private batch of {slug}")
    session.execute(
        sa.text(
            "INSERT INTO owner_listing (owner_id, slug, status, public_name, "
            "headline_en, published_at) VALUES (:o, :slug, 'published', :slug, "
            "'Maths tutor', :at)"
        ),
        {"o": teacher.owner_id, "slug": slug, "at": published_at},
    )
    session.commit()
    _listing(session, teacher.owner_id, teacher.batch_id, batch_slug)
    return teacher.owner_id, teacher.batch_id


def _listing(
    session: Session, owner_id: uuid.UUID, batch_id: uuid.UUID, slug: str
) -> None:
    """Publish one batch listing.

    :param session: An arranging session
    :param owner_id: The batch's owner
    :param batch_id: The batch
    :param slug: The listing's slug
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, slug, status, "
            "public_title, class_levels, subject_tags, show_fee, show_schedule, "
            "published_at) VALUES (:b, :o, :slug, 'published', :title, "
            "ARRAY['class_9']::varchar[], ARRAY['maths']::varchar[], false, "
            "false, :at)"
        ),
        {
            "b": batch_id,
            "o": owner_id,
            "slug": slug,
            "title": f"Title {slug}",
            "at": BASE,
        },
    )
    session.commit()


def _second_batch(session: Session, owner_id: uuid.UUID, slug: str) -> uuid.UUID:
    """Give an owner another published batch.

    :param session: An arranging session
    :param owner_id: The owner
    :param slug: The new listing's slug
    :return: The batch id
    """
    batch_id: uuid.UUID = session.execute(
        sa.text(
            "INSERT INTO batch (id, owner_id, name, default_fee, fee_due_day, "
            "marksheet_visible, active, created_at) VALUES (gen_random_uuid(), "
            ":o, 'Private second batch', 1500.00, 10, true, true, now()) "
            "RETURNING id"
        ),
        {"o": owner_id},
    ).scalar_one()
    session.commit()
    _listing(session, owner_id, batch_id, slug)
    return batch_id


def _review(
    session: Session,
    batch_id: uuid.UUID,
    rating: int,
    *,
    body: str | None = None,
    month: dt.date = NOVEMBER,
    tenure: str = "lt_6m",
    review_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one published review by a fresh guardian.

    :param session: An arranging session
    :param batch_id: The reviewed batch
    :param rating: 1 to 5
    :param body: Its text; a unique one by default
    :param month: The first of the month it was published in
    :param tenure: Its tenure bucket
    :param review_id: Its id, or a random one
    :return: The review id
    """
    new_id: uuid.UUID = session.execute(
        sa.text(
            "INSERT INTO review (id, batch_id, author_account_id, author_role, "
            "rating, body, status, tenure_bucket, published_month) VALUES "
            "(:id, :b, :a, 'guardian', :r, :body, 'published', "
            "CAST(:tenure AS hub_review_tenure), :m) RETURNING id"
        ),
        {
            "id": review_id or uuid.uuid4(),
            "b": batch_id,
            "a": _account(session),
            "r": rating,
            "body": body if body is not None else f"body-{uuid.uuid4().hex}",
            "tenure": tenure,
            "m": month,
        },
    ).scalar_one()
    session.commit()
    return new_id


def _reviews(session: Session, batch_id: uuid.UUID, ratings: list[int]) -> list[str]:
    """Publish one review per rating, each with a unique body.

    :param session: An arranging session
    :param batch_id: The reviewed batch
    :param ratings: The ratings
    :return: The bodies
    """
    bodies = []
    for rating in ratings:
        body = f"body-{uuid.uuid4().hex}"
        _review(session, batch_id, rating, body=body)
        bodies.append(body)
    return bodies


def _reply(session: Session, review_id: uuid.UUID, status: str, body: str) -> None:
    """Insert the reply to one review.

    :param session: An arranging session
    :param review_id: The review answered
    :param status: ``published`` or ``pending``
    :param body: The reply's text
    :return: None
    """
    session.execute(
        sa.text(
            "INSERT INTO review_reply (review_id, body, status, published_month) "
            "VALUES (:r, :body, CAST(:st AS hub_reply_status), :m)"
        ),
        {
            "r": review_id,
            "body": body,
            "st": status,
            "m": NOVEMBER if status == "published" else None,
        },
    )
    session.commit()


def _section(body: str) -> str:
    """Cut a page's review section out of it.

    :param body: The page
    :return: The section's HTML
    """
    match = _SECTION.search(body)
    assert match, "the page has no review section"
    return match.group(0)


def _order(body: str, locale: str) -> list[str]:
    """List the owner slugs a search page shows, in order.

    :param body: The search page
    :param locale: Its locale
    :return: The slugs
    """
    return re.findall(rf'<h2><a href="/hub/{locale}/t/([^"/]+)">', body)


def _summary_text(locale: Locale, average: str, count: int) -> str:
    """Spell a shown rating as the pages do.

    :param locale: The page's locale
    :param average: The average, e.g. ``4.3``
    :param count: The review count
    :return: The text
    """
    out_of = t("rating_out_of", locale, average=average)
    return f"{out_of} · {t('reviews_count', locale, count=count)}"


# ---------------------------------------------------------------------------
# Wording: the verbatim labels, months and threshold line
# ---------------------------------------------------------------------------


def test_review_copy_is_verbatim() -> None:
    """The three labels and the below-threshold line read exactly as decided."""
    assert {key: MESSAGES[key] for key in MESSAGES if key.startswith("review_by_")} == {
        "review_by_lt_6m": {
            "en": "Verified guardian · enrolled under 6 months",
            "bn": "যাচাইকৃত অভিভাবক · 6 মাসের কম সময় ধরে ভর্তি",
        },
        "review_by_6_12m": {
            "en": "Verified guardian · enrolled 6–12 months",  # noqa: RUF001 -- the decided copy's en dash
            "bn": "যাচাইকৃত অভিভাবক · 6–12 মাস ধরে ভর্তি",  # noqa: RUF001 -- the decided copy's en dash
        },
        "review_by_gt_1y": {
            "en": "Verified guardian · enrolled over 1 year",
            "bn": "যাচাইকৃত অভিভাবক · 1 বছরের বেশি সময় ধরে ভর্তি",
        },
    }
    assert MESSAGES["reviews_below_threshold"] == {
        "en": "Ratings appear once a class has 3 reviews.",
        "bn": "কোনো ক্লাসে 3টি রিভিউ হলে রেটিং দেখা যাবে।",
    }
    assert _summary_text("en", "4.3", 7) == "4.3 out of 5 · 7 reviews"


@pytest.mark.parametrize(
    ("month", "en", "bn"),
    [
        (1, "Jan", "জানুয়ারি"),
        (2, "Feb", "ফেব্রুয়ারি"),
        (3, "Mar", "মার্চ"),
        (4, "Apr", "এপ্রিল"),
        (5, "May", "মে"),
        (6, "Jun", "জুন"),
        (7, "Jul", "জুলাই"),
        (8, "Aug", "আগস্ট"),
        (9, "Sep", "সেপ্টেম্বর"),
        (10, "Oct", "অক্টোবর"),
        (11, "Nov", "নভেম্বর"),
        (12, "Dec", "ডিসেম্বর"),
    ],
)
def test_month_label_is_month_and_year_in_latin_digits(
    month: int, en: str, bn: str
) -> None:
    """A month reads as its name and the year, never a day.

    :param month: The month number
    :param en: Its English name
    :param bn: Its Bangla name
    :return: None
    """
    assert month_label(dt.date(2026, month, 1), "en") == f"{en} 2026"
    assert month_label(dt.date(2026, month, 1), "bn") == f"{bn} 2026"


@pytest.mark.parametrize(
    ("tenths", "label"), [(43, "4.3"), (50, "5.0"), (10, "1.0"), (47, "4.7")]
)
def test_tenths_label_by_integer_ops(tenths: int, label: str) -> None:
    """Integer tenths render as one decimal place, with no float.

    :param tenths: The average in tenths
    :param label: How it reads
    :return: None
    """
    assert tenths_label(tenths) == label


def test_public_review_models_carry_no_review_forbidden_field() -> None:
    """No identity, seat or exact time is a field of what a page shows."""
    assert HubReview in registered_views()
    fields = {
        *HubReview.model_fields,
        *HubReply.model_fields,
        *RatingSummary.model_fields,
    }
    assert fields & REVIEW_FORBIDDEN_FIELDS == set()
    assert set(HubReview.model_fields) == {
        "review_id",
        "rating",
        "body",
        "author_label",
        "month_label",
        "reply",
    }
    assert set(HubReply.model_fields) == {"body", "month_label"}


# ---------------------------------------------------------------------------
# The batch page
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("reviews_on")
def test_batch_page_shows_reviews_only_at_threshold(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """0 and 2 reviews read identically and show no number; 3 show everything.

    Review Focus 2 and T9-a: below the threshold the section is the same
    line whatever the count, so 0, 1 and 2 cannot be told apart.
    """
    client = _client(api_client, monkeypatch)
    _tutor(owner_session, "none-yet")
    _, two = _tutor(owner_session, "two-so-far")
    _, three = _tutor(owner_session, "three-now")
    hidden = _reviews(owner_session, two, [5, 4])
    shown = _reviews(owner_session, three, [5, 4, 4])

    for locale in ("en", "bn"):
        pages = {
            slug: client.get(f"/hub/{locale}/t/{slug}/{BATCH}")
            for slug in ("none-yet", "two-so-far", "three-now")
        }
        for response in pages.values():
            assert response.status_code == 200, response.text
        below = _section(pages["none-yet"].text)
        assert _section(pages["two-so-far"].text) == below
        assert t("reviews_below_threshold", locale) in below
        # The only number in the section is the threshold's own "3".
        text = re.sub(r"<[^>]+>", "", below)
        assert not re.search(
            r"\d", text.replace(t("reviews_below_threshold", locale), "")
        )
        two_page = pages["two-so-far"].text
        assert t("reviews_count", locale, count=2) not in two_page
        assert [body for body in hidden if body in two_page] == []
        assert "<meter" not in two_page

        full = _section(pages["three-now"].text)
        assert t("reviews_below_threshold", locale) not in full
        assert _summary_text(locale, "4.3", 3) in full
        assert all(body in full for body in shown)
        assert full.count("<meter") == 5


@pytest.mark.parametrize("drop", ["held", "removed", "pending", "deleted"])
@pytest.mark.usefixtures("reviews_on")
def test_drop_below_threshold_hides_everything_public(
    api_client: TestClient,
    owner_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    drop: str,
) -> None:
    """From 3 published to 2, the batch page, owner card and sort forget it.

    Review Focus 2: held, removed, edited back to pending or deleted, the
    text, average and distribution leave the batch page, the rating leaves
    the owner card on every page, and the sort score falls to the prior.

    :param drop: How the third review leaves ``published``
    """
    client = _client(api_client, monkeypatch)
    _, batch = _tutor(owner_session, "a-rated", published_at=BASE)
    _tutor(owner_session, "b-unrated", published_at=BASE + dt.timedelta(days=1))
    bodies = _reviews(owner_session, batch, [5, 5, 5])
    summary = {locale: _summary_text(locale, "5.0", 3) for locale in ("en", "bn")}

    def pages(locale: str) -> dict[str, str]:
        """Fetch the pages the rating can reach.

        :param locale: The locale
        :return: Body by page name
        """
        return {
            "batch": client.get(f"/hub/{locale}/t/a-rated/{BATCH}").text,
            "owner": client.get(f"/hub/{locale}/t/a-rated").text,
            "search": client.get(f"/hub/{locale}").text,
            "sorted": client.get(f"/hub/{locale}?sort=rating").text,
        }

    for locale in ("en", "bn"):
        before = pages(locale)
        assert all(body in before["batch"] for body in bodies)
        for name in ("batch", "owner", "search"):
            assert summary[locale] in before[name], name
        assert _order(before["search"], locale) == ["b-unrated", "a-rated"]
        assert _order(before["sorted"], locale) == ["a-rated", "b-unrated"]

    third = owner_session.execute(
        sa.text("SELECT id FROM review WHERE body = :b"), {"b": bodies[2]}
    ).scalar_one()
    if drop == "deleted":
        owner_session.execute(sa.text("DELETE FROM review WHERE id = :r"), {"r": third})
    else:
        owner_session.execute(
            sa.text(
                "UPDATE review SET status = CAST(:st AS hub_review_status), "
                "published_month = CASE WHEN :st = 'held' THEN published_month END, "
                "rejection_code = CASE WHEN :st = 'removed' THEN 'abusive' END "
                "WHERE id = :r"
            ),
            {"st": drop, "r": third},
        )
    owner_session.commit()

    for locale in ("en", "bn"):
        after = pages(locale)
        assert [body for body in bodies if body in after["batch"]] == []
        assert t("reviews_below_threshold", locale) in after["batch"]
        assert "<meter" not in after["batch"]
        for name, body in after.items():
            assert t("rating_out_of", locale, average="5.0") not in body, name
        assert _order(after["sorted"], locale) == ["b-unrated", "a-rated"]


@pytest.mark.usefixtures("reviews_on")
def test_label_month_and_order(
    owner_session: Session, restricted_session: Session
) -> None:
    """Newest month first, then id; a tenure label and a month, never a day.

    T2-c: submission order must not leak, so within a month the order is by
    the random id. The first review inserted carries the larger id.
    """
    _, batch = _tutor(owner_session, "ordered")
    late, early = sorted((uuid.uuid4(), uuid.uuid4()), reverse=True)
    _review(owner_session, batch, 4, review_id=late, tenure="lt_6m")
    _review(owner_session, batch, 5, month=OCTOBER, tenure="gt_1y")
    _review(owner_session, batch, 3, review_id=early, tenure="6_12m")

    pages = {}
    for locale in ("en", "bn"):
        page = queries.batch_page(restricted_session, locale, "ordered", BATCH)
        restricted_session.rollback()
        assert page is not None
        pages[locale] = page

    en, bn = pages["en"].reviews, pages["bn"].reviews
    assert [r.review_id for r in en][:2] == [early, late]
    assert [r.rating for r in en] == [3, 4, 5]
    assert [r.month_label for r in en] == ["Nov 2026", "Nov 2026", "Oct 2026"]
    assert [r.month_label for r in bn] == ["নভেম্বর 2026", "নভেম্বর 2026", "অক্টোবর 2026"]
    assert [r.author_label for r in en] == [
        "Verified guardian · enrolled 6–12 months",  # noqa: RUF001 -- the decided copy's en dash
        "Verified guardian · enrolled under 6 months",
        "Verified guardian · enrolled over 1 year",
    ]
    assert [r.author_label for r in bn] == [
        "যাচাইকৃত অভিভাবক · 6–12 মাস ধরে ভর্তি",  # noqa: RUF001 -- the decided copy's en dash
        "যাচাইকৃত অভিভাবক · 6 মাসের কম সময় ধরে ভর্তি",
        "যাচাইকৃত অভিভাবক · 1 বছরের বেশি সময় ধরে ভর্তি",
    ]
    rendered = pages["en"].model_dump_json()
    for day in ("2026-11-01", "2026-10-01", "01 Nov", "1 Nov"):
        assert day not in rendered


@pytest.mark.usefixtures("reviews_on")
def test_batch_page_shows_at_most_fifty_most_recent_with_a_note(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Volume: at most 50 reviews on a page, newest month first, and a note.

    Fifty-one published: the October one is the oldest and is left out, the
    count still says 51, and the page says it shows the 50 most recent.
    Exactly fifty: all shown, and no note.
    """
    client = _client(api_client, monkeypatch)
    _, capped = _tutor(owner_session, "fifty-one")
    _, full = _tutor(owner_session, "exactly-fifty")
    oldest = f"body-{uuid.uuid4().hex}"
    _review(owner_session, capped, 4, body=oldest, month=OCTOBER)
    newest = _reviews(owner_session, capped, [5] * 50)
    _reviews(owner_session, full, [4] * 50)

    for locale in ("en", "bn"):
        section = _section(client.get(f"/hub/{locale}/t/fifty-one/{BATCH}").text)
        assert section.count('<li class="review"') == 50
        assert all(body in section for body in newest)
        assert oldest not in section
        assert t("reviews_count", locale, count=51) in section
        assert t("reviews_most_recent", locale, shown=50) in section

        whole = _section(client.get(f"/hub/{locale}/t/exactly-fifty/{BATCH}").text)
        assert whole.count('<li class="review"') == 50
        assert t("reviews_most_recent", locale, shown=50) not in whole


@pytest.mark.usefixtures("reviews_on")
def test_review_and_reply_report_links(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each review links its report; only a published reply is shown and linked."""
    client = _client(api_client, monkeypatch)
    _, batch = _tutor(owner_session, "replied")
    answered, waiting, plain = (
        _review(owner_session, batch, rating) for rating in (5, 4, 3)
    )
    _reply(owner_session, answered, "published", "Thank you, published reply")
    _reply(owner_session, waiting, "pending", "Pending reply text")

    for locale in ("en", "bn"):
        body = client.get(f"/hub/{locale}/t/replied/{BATCH}").text
        for review_id in (answered, waiting, plain):
            href = f"{WEB_APP}/ui/hub-report?kind=review&amp;id={review_id}"
            assert f'href="{href}"' in body
        assert f"kind=reply&amp;id={answered}" in body
        assert f"kind=reply&amp;id={waiting}" not in body
        assert f"kind=reply&amp;id={plain}" not in body
        assert "Thank you, published reply" in body
        assert t("reply_heading", locale) in body
        assert "Pending reply text" not in body
        assert body.count(t("report_review", locale)) == 3
        assert body.count(t("report_reply", locale)) == 1


@pytest.mark.usefixtures("reviews_on")
def test_owner_card_rating_uses_only_qualifying_batches(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The owner card averages batches at the threshold, never one below it.

    Call 12: folding the two-review batch in would read 16/5 = 3.2 over 5
    reviews and leak its ratings through the owner's average.
    """
    client = _client(api_client, monkeypatch)
    owner_id, qualifying = _tutor(owner_session, "mixed")
    below = _second_batch(owner_session, owner_id, "small-batch")
    _reviews(owner_session, qualifying, [5, 5, 4])
    _reviews(owner_session, below, [1, 1])
    _, lonely = _tutor(owner_session, "only-small")
    _reviews(owner_session, lonely, [5, 5])

    page = queries.owner_page(restricted_session, "en", "mixed")
    restricted_session.rollback()
    assert page is not None
    assert page.owner.rating == RatingSummary(
        state="shown",
        count=3,
        average_tenths=47,
        average_label="4.7",
        distribution=None,
    )
    cards = {card.slug: card.rating for card in page.batches}
    assert cards["small-batch"] == RatingSummary(state="below_threshold")
    assert cards[BATCH] is not None and cards[BATCH].average_label == "4.7"
    alone = queries.owner_page(restricted_session, "en", "only-small")
    restricted_session.rollback()
    assert alone is not None and alone.owner.rating is None

    for locale in ("en", "bn"):
        summary = _summary_text(locale, "4.7", 3)
        for path in ("", "/t/mixed", f"/t/mixed/{BATCH}", "/t/mixed/small-batch"):
            body = client.get(f"/hub/{locale}{path}").text
            assert t("rating_out_of", locale, average="3.2") not in body, path
            if path.endswith("small-batch"):
                assert t("reviews_below_threshold", locale) in body
            else:
                assert summary in body, path
        only = client.get(f"/hub/{locale}/t/only-small").text
        assert t("rating_out_of", locale, average="5.0") not in only


@pytest.mark.usefixtures("reviews_on")
def test_sort_by_rating_orders_by_bayesian_score(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prior 3.5, weight 5: [5,5,5] 4063, [5,4,4] 3813, none 3500.

    Relevance (newest first) is arranged as the exact reverse, so only the
    score can produce the expected order. The fourth owner, 48 over 10, has
    a lower average than [5,5,5] and a higher score (4367): an order by
    plain average would put it second.
    """
    client = _client(api_client, monkeypatch)
    arranged = (
        ("many-good", [5] * 8 + [4] * 2),
        ("all-fives", [5, 5, 5]),
        ("mostly-fours", [5, 4, 4]),
        ("unrated", []),
    )
    for days, (slug, ratings) in enumerate(arranged):
        _, batch = _tutor(owner_session, slug, published_at=BASE + dt.timedelta(days))
        _reviews(owner_session, batch, ratings)
    expected = [slug for slug, _ in arranged]

    def search(sort: str | None) -> list[str]:
        """Search everything as the hub reader.

        :param sort: The sort key
        :return: The slugs in order
        """
        found = queries.search(
            restricted_session,
            locale="en",
            q=None,
            district=None,
            upazila=None,
            subject=None,
            level=None,
            page=1,
            sort=sort,
        )
        restricted_session.rollback()
        assert found.offers_sort
        return [card.slug for card in found.results]

    assert search("rating") == expected
    assert search(None) == expected[::-1]
    assert search("relevance") == expected[::-1]
    assert search("anything") == expected[::-1]

    for locale in ("en", "bn"):
        body = client.get(f"/hub/{locale}?sort=rating").text
        assert _order(body, locale) == expected
        assert '<select id="sort" name="sort">' in body
        assert '<option value="rating" selected>' in body
        assert f'href="{SITE}/hub/{locale}?sort=rating"' in body
        plain = client.get(f"/hub/{locale}").text
        assert _order(plain, locale) == expected[::-1]
        assert '<option value="relevance" selected>' in plain


@pytest.mark.usefixtures("reviews_off")
def test_switch_off_hides_reviews_on_every_public_page(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the switch off, nothing of reviews reaches any public page.

    Review Focus 5: no review section, no rating, no report link for a
    review or reply, no sort choice in either locale, and ``?sort=rating``
    answers the relevance page byte for byte.
    """
    client = _client(api_client, monkeypatch)
    _, batch = _tutor(owner_session, "a-rated", published_at=BASE)
    _tutor(owner_session, "b-unrated", published_at=BASE + dt.timedelta(days=1))
    bodies = _reviews(owner_session, batch, [5, 5, 5])
    first = owner_session.execute(
        sa.text("SELECT id FROM review WHERE body = :b"), {"b": bodies[0]}
    ).scalar_one()
    _reply(owner_session, first, "published", "A published reply")

    for locale in ("en", "bn"):
        paths = (
            f"/hub/{locale}",
            f"/hub/{locale}?sort=rating",
            f"/hub/{locale}/t/a-rated",
            f"/hub/{locale}/t/a-rated/{BATCH}",
        )
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, path
            text = response.text
            assert 'class="reviews"' not in text, path
            assert "rating" not in text.lower(), path
            assert "kind=review" not in text and "kind=reply" not in text, path
            assert 'name="sort"' not in text, path
            assert t("reviews_below_threshold", locale) not in text, path
            assert [body for body in bodies if body in text] == [], path
            assert "A published reply" not in text, path
        plain = client.get(f"/hub/{locale}")
        assert client.get(f"/hub/{locale}?sort=rating").content == plain.content
        assert _order(plain.text, locale) == ["b-unrated", "a-rated"]


@pytest.mark.usefixtures("reviews_on")
def test_page_csp_unchanged_and_no_inline_style(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pages with reviews keep the CSP and carry no style or script of their own."""
    client = _client(api_client, monkeypatch)
    _, batch = _tutor(owner_session, "styled")
    first = _review(owner_session, batch, 5)
    _reviews(owner_session, batch, [4, 3])
    _reply(owner_session, first, "published", "Reply")

    assert HUB_PAGE_CSP == PAGE_CSP
    for locale in ("en", "bn"):
        for path in (
            f"/hub/{locale}?sort=rating",
            f"/hub/{locale}/t/styled",
            f"/hub/{locale}/t/styled/{BATCH}",
        ):
            response = client.get(path)
            assert response.headers["content-security-policy"] == PAGE_CSP, path
            page = _Tags()
            page.feed(response.text)
            assert "style" not in page.names, path
            for name, attrs in page.tags:
                assert "style" not in attrs, (path, name)
                assert not [a for a in attrs if a.startswith("on")], (path, name)
                if name == "script":
                    assert attrs == {"type": "application/ld+json"}, path
        batch_page = client.get(f"/hub/{locale}/t/styled/{BATCH}").text
        assert "<meter" in batch_page


@pytest.mark.usefixtures("reviews_on")
def test_preview_shows_card_ratings_and_no_review_section(
    api_client: TestClient, owner_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner's preview rates its cards from the views and shows no reviews.

    F19: card ratings only, read from the views, only while the switch is
    on; no review text, no review section, no report link.
    """
    client = _client(api_client, monkeypatch)
    owner_id, batch = _tutor(owner_session, "previewed")
    bodies = _reviews(owner_session, batch, [5, 4, 4])
    account_id = owner_session.execute(
        sa.text("SELECT account_id FROM owner WHERE id = :o"), {"o": owner_id}
    ).scalar_one()
    headers = bearer(owner_session, account_id)

    for locale in ("en", "bn"):
        body = client.get(
            f"/v1/hub/listing/preview?locale={locale}", headers=headers
        ).text
        assert body.count(_summary_text(locale, "4.3", 3)) == 2
        assert 'class="reviews"' not in body
        assert "kind=review" not in body
        assert [text for text in bodies if text in body] == []

    monkeypatch.setenv("SHIKKHOKPLUS_HUB_REVIEWS", "off")
    for locale in ("en", "bn"):
        body = client.get(
            f"/v1/hub/listing/preview?locale={locale}", headers=headers
        ).text
        assert t("rating_out_of", locale, average="4.3") not in body


class _Tags(HTMLParser):
    """Collect every start tag of a page, as a browser would parse it."""

    def __init__(self) -> None:
        """Start empty."""
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    @property
    def names(self) -> set[str]:
        """Name every tag seen.

        :return: The tag names
        """
        return {name for name, _ in self.tags}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record a start tag.

        :param tag: The tag name
        :param attrs: Its attributes
        :return: None
        """
        self.tags.append((tag, dict(attrs)))
