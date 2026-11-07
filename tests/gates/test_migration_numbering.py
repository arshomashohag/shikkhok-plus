"""Revisions form one line of zero-padded numbers, each greater than the last.

**This is the precondition the boot's rollback depends on** [C-12].
``python -m app.db.commands migrate-if-behind`` must decide whether a
database revision the booting image has never seen is LATER than its
own head -- and the image cannot read that from its scripts, which by
definition lack the newer revision. It decides from the ids: an unknown
revision numbered after the head is a later one on the same line.

That inference is sound only while every revision is a zero-padded
integer greater than its parent, on a single line. It does NOT need the
numbers to be consecutive -- the decision compares magnitudes only -- so
a skipped number passes here. What it cannot survive is a revision
numbered BELOW one already on the line: inserting one under a revision
a database has already applied would make that database look ahead of
an image that is in fact newer. Should the numbering break -- a
hash-named revision, a merge, a number out of order -- the change must
fail here, where the consequence can be explained, rather than on a
host that refuses to boot.
"""

from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db.commands import ALEMBIC_INI


def _script() -> ScriptDirectory:
    """Load this repository's migration scripts.

    :return: The script directory ``alembic.ini`` names
    """
    return ScriptDirectory.from_config(Config(ALEMBIC_INI))


def test_there_is_one_head() -> None:
    assert len(_script().get_heads()) == 1


def test_every_revision_is_a_padded_number_after_its_parent() -> None:
    revisions = list(_script().walk_revisions())
    assert len(revisions) > 1, "no migrations found; the guard would be vacuous"

    width = len(revisions[0].revision)
    problems: list[str] = []
    for revision in revisions:
        rid = revision.revision
        if not (rid.isdigit() and len(rid) == width):
            problems.append(f"{rid}: not a {width}-digit number")
            continue
        parent = revision.down_revision
        if parent is None:
            if int(rid) != 1:
                problems.append(f"{rid}: a root that is not the first revision")
            continue
        if not isinstance(parent, str):
            problems.append(f"{rid}: merges {parent}, so history is not one line")
            continue
        if not parent.isdigit() or int(parent) >= int(rid):
            problems.append(f"{rid}: follows {parent}, which is not numbered below it")

    assert problems == [], (
        f"{problems}. migrate-if-behind decides that an unknown database "
        "revision is a later one by comparing numbers; that is only sound "
        "while revisions are one zero-padded line, increasing [C-12]."
    )
