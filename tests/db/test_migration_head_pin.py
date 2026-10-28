"""The migration count and head, pinned so a change is deliberate.

**Renamed from ``test_no_d5_migration.py`` in D6.** The original file
asserted that D5 ships no migration, and both of its pinned constants
said so in their names and their docstrings. D6 adds ``0007``, so an
edit that only moved the constants would have left a file describing a
check it no longer performs -- which is how a test comes to mislead the
next reader more than no test would.

What the file asserts is unchanged in substance and is worth keeping:
**the count and the head together**, because either alone is defeatable.
A replaced revision keeps the count and moves the head; a new branch
that is never merged moves neither. Moving this pin is a diff against a
stated number rather than a file quietly appearing in a directory.

The analytics assertion below is D5's and is **not** renamed away: it
asserts an absence that still holds, and absences are what stop being
checked when nobody is looking.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

VERSIONS: Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
)

#: Every revision on disk. D6 added ``0007`` -- the cascade fix -- the
#: first since D4 to move this number; D5 deliberately added none, which
#: is what this file used to be named for. ``0008`` -- canonical phone
#: numbers and ``enrollment.student_phone`` -- moves it again, for the
#: student-linking gap found in the end-to-end audit. ``0009`` -- the
#: in-app notification inbox -- moves it once more.
EXPECTED_REVISIONS: Final[int] = 9

#: The head ``0009`` leaves behind.
EXPECTED_HEAD: Final[str] = "0009"


def _revision_files() -> list[pathlib.Path]:
    """Every migration script on disk, ordered by its numeric prefix.

    :return: The revision files
    """
    return sorted(
        path for path in VERSIONS.glob("*.py") if re.match(r"^\d{4}_", path.name)
    )


def test_the_revision_count_is_the_pinned_one() -> None:
    """``migrations/versions/`` holds exactly the pinned number.

    :return: None
    """
    found = _revision_files()

    assert len(found) == EXPECTED_REVISIONS, (
        f"{len(found)} migration scripts, not {EXPECTED_REVISIONS}: "
        f"{[path.name for path in found]}. A migration arriving without "
        "this number moving is a schema change nobody stated."
    )


def test_the_head_revision_is_the_pinned_one() -> None:
    """The count alone would miss a replaced revision.

    :return: None
    """
    head = _revision_files()[-1]

    assert head.name.startswith(EXPECTED_HEAD), (
        f"the newest migration is {head.name}, not {EXPECTED_HEAD}*."
    )


def test_the_analytics_package_contains_no_ddl() -> None:
    """Nothing in ``app/analytics/`` creates or alters a table.

    D5's own assertion, kept: a migration is not the only way a table
    can appear, and that unit writes nothing at all [NFR19.57].

    :return: None
    """
    package = pathlib.Path(__file__).resolve().parents[2] / "app" / "analytics"
    sources = "\n".join(path.read_text() for path in package.glob("*.py"))

    for statement in ("CREATE TABLE", "ALTER TABLE", "INSERT INTO", "UPDATE "):
        assert statement not in sources.upper(), (
            f"app/analytics/ contains {statement!r}. This unit is "
            "read-only against every table it touches [NFR19.57]."
        )
