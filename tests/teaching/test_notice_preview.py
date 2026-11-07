"""A notice's inbox preview: short, marked when cut, never splitting a letter.

Pure: no database. Written from the rule, not the implementation -- a
body within the limit is whole, a longer one ends in an ellipsis inside
the limit, and a Bangla conjunct or vowel sign stays with its letter.
"""

from __future__ import annotations

import unicodedata

import pytest

from app.teaching.announcements import ELLIPSIS, PREVIEW_LENGTH, notice_preview


def test_a_short_notice_is_kept_whole() -> None:
    assert notice_preview("Class at 5 today") == "Class at 5 today"


def test_a_notice_exactly_at_the_limit_is_kept_whole() -> None:
    body = "a" * PREVIEW_LENGTH
    assert notice_preview(body) == body


def test_a_long_notice_is_cut_inside_the_limit_with_an_ellipsis() -> None:
    preview = notice_preview("b" * (PREVIEW_LENGTH + 1))
    assert preview == "b" * (PREVIEW_LENGTH - 1) + ELLIPSIS
    assert len(preview) == PREVIEW_LENGTH


def test_a_cut_does_not_leave_a_space_before_the_ellipsis() -> None:
    body = "c" * (PREVIEW_LENGTH - 2) + " " + "d" * 10
    assert notice_preview(body) == "c" * (PREVIEW_LENGTH - 2) + ELLIPSIS


@pytest.mark.parametrize(
    "tail",
    [
        # ক্ষ: ka + hasanta + ssa. A cut after the hasanta splits the conjunct.
        "\u0995\u09cd\u09b7",
        # কা: ka + the aa vowel sign. A cut before the sign orphans it.
        "\u0995\u09be",
        # কি: ka + the i vowel sign.
        "\u0995\u09bf",
    ],
)
@pytest.mark.parametrize("offset", [2, 3, 4])
def test_a_bangla_letter_is_never_split(tail: str, offset: int) -> None:
    # Slide the cluster across the plain cut point so every split lands.
    lead = "\u0985" * (PREVIEW_LENGTH - offset)
    body = lead + tail + "\u0986" * 20
    preview = notice_preview(body)

    assert preview.endswith(ELLIPSIS)
    assert len(preview) <= PREVIEW_LENGTH
    kept = preview.removesuffix(ELLIPSIS)
    assert body.startswith(kept)
    # What was dropped must not begin with a mark that belonged to the
    # last kept letter, and the kept text must not end mid-conjunct.
    assert unicodedata.category(body[len(kept)]) not in {"Mn", "Mc"}
    assert not kept.endswith("\u09cd")
