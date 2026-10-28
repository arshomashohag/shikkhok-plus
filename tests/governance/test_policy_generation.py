"""The privacy-policy generator, and the gate that keeps it current.

**The threat is drift, and this unit was handed the evidence rather than
having to argue it.** Before D6, ``dispositions.py`` said the account row
was anonymized, ``PRIVACY.md`` promised the phone number was "deleted
permanently", and ``docs/legal/README.md``'s own table said "hard
delete". Three documents, three answers, nothing failing. The tests here
are what would have caught that.

**The vacuity trap this file is written against**: asserting a
generator's output against a fixture the generator also produced is
circular -- it proves the function is a function. So the disclosure
tests check for SUBSTANTIVE CONTENT, that the text states a
teacher-typed name survives deletion, rather than that output equals a
recorded blob. A generator that emitted the empty string would satisfy a
round-trip assertion and fail every assertion here.

**NFR14.90 is NOT closed by anything in this file and is not pretended
to be.** Nothing mechanically prevents a factual claim being written in
the prose OUTSIDE the markers, where the comparison does not reach. The
rival hand-written table was removed to shrink that surface; the
obligation remains partly manual.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest

from app.governance.dispositions import (
    DISPOSITIONS,
    Disposition,
    RetentionClass,
)
from scripts.generate_privacy_policy import (
    BEGIN_MARKER,
    END_MARKER,
    POLICY_PATH,
    describe,
    disclosure,
    generated_document,
    manifest_digest,
    render,
)

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = ROOT / POLICY_PATH


def _generated_region(document: str) -> str:
    """Extract the text between the markers.

    :param document: A full policy document
    :return: The generated region, markers excluded
    :raises AssertionError: If the markers are absent or out of order
    """
    begin = document.find(BEGIN_MARKER)
    end = document.find(END_MARKER)
    assert begin != -1 and end > begin, "the document has no generated region"
    return document[begin + len(BEGIN_MARKER) : end]


# ---------------------------------------------------------------------
# The gate itself.
# ---------------------------------------------------------------------


def test_the_committed_policy_matches_the_generated_one() -> None:
    """``PRIVACY.md``'s generated region is current [BR2.3].

    The same shape as the built OpenAPI schema-diff gate, and for the
    same reason: a committed artifact derived from code must be
    regenerated in the change that alters its source, or it becomes a
    claim about an older version.

    Regeneration is the only sanctioned fix. Hand-editing the committed
    file to turn this red check green inverts the control into a rubber
    stamp, and it looks exactly like fixing the problem.

    :return: None
    """
    assert COMMITTED.exists(), f"{POLICY_PATH} is missing"
    current = COMMITTED.read_text(encoding="utf-8")

    assert current == generated_document(current), (
        f"{POLICY_PATH}'s generated region is stale. Run "
        "`python3 -m scripts.generate_privacy_policy`, then READ THE "
        "DIFF: it is a change to what this product tells a regulator "
        "about children's data."
    )


def test_a_changed_basis_or_disposition_makes_the_gate_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drift is detected rather than merely detectable [BR2.3].

    **The test that proves the gate can fire.** Without it, every other
    assertion here is consistent with a comparison that always
    succeeds -- and this project has already shipped one gate whose
    first version matched its own comment.

    A disposition is moved and the committed text is then stale by
    construction, so the gate must report it.

    :param monkeypatch: Used to move one table's disposition
    :return: None
    """
    moved = DISPOSITIONS["attendance"]
    monkeypatch.setitem(
        DISPOSITIONS,
        "attendance",
        type(moved)(
            disposition=Disposition.HARD_DELETE,
            retention=moved.retention,
            basis=moved.basis,
        ),
    )

    current = COMMITTED.read_text(encoding="utf-8")
    assert current != generated_document(current), (
        "a table moved from RETAIN_WITH_BASIS to HARD_DELETE and the "
        "gate did not notice, so it is not comparing the manifest"
    )


def test_a_basis_only_change_also_fails_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing a ``basis`` alone is detected [NFR14.101].

    **The gate's first version missed this, and the miss was on exactly
    the field NFR14.101 is about.** A generator rendering only the
    disposition and the retention class compares only those, so a
    changed ``basis`` altered nothing on the page and ``make check``
    stayed green -- the manifest's stated reasoning free to drift away
    from the published reasoning with nothing watching. The digest is
    what closes it; this is the test that proves it closed.

    The mutation changes ONLY the basis, leaving the disposition and the
    retention class alone, so a gate passing this cannot be passing it
    by noticing something else.

    :param monkeypatch: Used to change one table's basis
    :return: None
    """
    original = DISPOSITIONS["attendance"]
    monkeypatch.setitem(
        DISPOSITIONS,
        "attendance",
        type(original)(
            disposition=original.disposition,
            retention=original.retention,
            basis="A different reason, with the disposition untouched.",
        ),
    )

    current = COMMITTED.read_text(encoding="utf-8")
    assert current != generated_document(current), (
        "a basis changed and the gate stayed green, so the generated "
        "region does not cover the basis field [NFR14.101]"
    )


def test_the_digest_covers_every_manifest_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each of the three fields moves the digest.

    Asserted field by field rather than as "the digest changes", so a
    digest built over two of the three is visible here instead of
    passing on the strength of the field it does cover.

    :param monkeypatch: Used to vary one field at a time
    :return: None
    """
    baseline = manifest_digest()
    original = DISPOSITIONS["mark"]

    variants = {
        "disposition": type(original)(
            disposition=Disposition.HARD_DELETE,
            retention=original.retention,
            basis=original.basis,
        ),
        "retention": type(original)(
            disposition=original.disposition,
            retention=RetentionClass.DAYS_7,
            basis=original.basis,
        ),
        "basis": type(original)(
            disposition=original.disposition,
            retention=original.retention,
            basis="Something else entirely.",
        ),
    }

    for field, variant in variants.items():
        with monkeypatch.context() as patched:
            patched.setitem(DISPOSITIONS, "mark", variant)
            assert manifest_digest() != baseline, (
                f"changing a table's {field} does not change the digest"
            )


def test_the_digest_is_not_published_as_prose() -> None:
    """The digest rides in a comment, not in text a parent reads.

    A hex string in the body of a privacy policy is noise to every
    human who reads the page, and noise in a legal document is what a
    later editor deletes.

    :return: None
    """
    region = render()
    digest = manifest_digest()

    assert digest in region, "the digest is not inside the compared region"
    line = next(line for line in region.splitlines() if digest in line)
    assert line.lstrip().startswith("<!--"), (
        "the digest is rendered as visible prose rather than a comment"
    )


def test_the_check_flag_exits_non_zero_on_drift(tmp_path: Path) -> None:
    """``--check`` is the gate's shape and writes nothing.

    Run as a subprocess because the exit code and the
    write-nothing property are what ``make check`` depends on, and
    neither is observable from calling ``main`` in-process with a
    patched ``sys.argv``.

    :param tmp_path: A scratch directory holding the stale copy
    :return: None
    """
    stale = tmp_path / "PRIVACY.md"
    stale.write_text(
        f"# Policy\n\nProse.\n\n{BEGIN_MARKER}\nstale text\n{END_MARKER}\n",
        encoding="utf-8",
    )
    before = stale.read_text(encoding="utf-8")

    # S603: the only non-literal argument is pytest's own tmp_path, and
    # `check=False` is the point -- the exit code is what is under test.
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.generate_privacy_policy",
            "--check",
            "--path",
            str(stale),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 1, "--check passed over a stale document"
    assert stale.read_text(encoding="utf-8") == before, (
        "--check wrote to the file, so it is a fix rather than a gate"
    )


# ---------------------------------------------------------------------
# Determinism [NFR16.7].
# ---------------------------------------------------------------------


def test_generation_is_deterministic_within_a_process() -> None:
    """Two renders produce identical bytes.

    :return: None
    """
    assert render() == render()


def test_generation_is_deterministic_across_processes() -> None:
    """A separate process produces the same region.

    **A same-run comparison cannot observe the failure this guards
    against.** Python seeds hash randomization once per process, so two
    renders inside one test run share any set-derived ordering by
    construction and agree however unstable the output is. The
    schema-diff gate records the measurement: six interpreter processes
    printing one seven-element set gave six different orderings.

    ``PYTHONHASHSEED`` is deliberately not pinned, for the same reason
    it is not pinned there: pinning it would make this test pass while
    CI, which does not pin it, failed intermittently.

    :return: None
    """
    script = (
        "from scripts.generate_privacy_policy import render; print(render(), end='')"
    )
    # S603: every argument is a module-level literal in this file.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )

    assert result.stdout == render(), (
        "the generated region is not stable across processes, so every "
        "build would produce a diff and the gate would become noise"
    )


def test_the_generated_region_carries_no_date() -> None:
    """No timestamp reaches the output [NFR16.7].

    A generator emitting the date makes every build a diff. The gate
    then fires constantly for no reason, gets ignored, and stops being
    a gate -- which is a worse outcome than not having built it.

    The assertion is over the YEAR rather than a date format, because
    a year is what every date rendering has in common and a format
    check would miss the one spelling nobody anticipated.

    :return: None
    """
    today = dt.datetime.now(tz=dt.UTC).date()

    region = render()
    for year in range(today.year - 1, today.year + 2):
        assert str(year) not in region, (
            f"the generated region contains {year}, which makes every build a diff"
        )


# ---------------------------------------------------------------------
# ADR-012's disclosure [BR2.2, NFR14.89].
# ---------------------------------------------------------------------


def test_the_generated_text_discloses_the_surviving_teacher_typed_name() -> None:
    """The output states that a teacher-typed name survives deletion.

    **Asserted on the GENERATED output, not the committed file**, so it
    fails if the generator stops emitting it rather than only if
    somebody edits the Markdown.

    **Asserted as substance rather than as an exact string.** A
    fixture comparison here would be circular -- it would prove the
    generator is a function. These assertions are about what the
    sentence must TELL a parent: that the name is the teacher's, that
    it remains after deletion, and that declining does not remove it.

    :return: None
    """
    region = render().lower()

    assert "name the teacher" in region or "teacher typed" in region, (
        "the generated policy does not mention the teacher-typed name"
    )
    assert "after you delete your account" in region, (
        "the generated policy does not say the name SURVIVES deletion, "
        "which is the disclosure ADR-012 requires"
    )
    assert "declined" in region, (
        "the generated policy omits the declined-seat case, which is "
        "the sharpest edge of it: a person who never consented still "
        "appears under a name they did not choose"
    )


def test_the_disclosure_is_derived_from_the_manifest_not_hardcoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Making ``enrollment`` hard-delete changes what the policy claims.

    **The anti-vacuity test for the disclosure.** A generator printing
    the sentence unconditionally passes the test above whatever the
    manifest says -- and would keep promising a name survives after a
    later unit decided it should not.

    :param monkeypatch: Used to move the enrollment disposition
    :return: None
    """
    assert "stays in that teacher's record" in disclosure()

    moved = DISPOSITIONS["enrollment"]
    monkeypatch.setitem(
        DISPOSITIONS,
        "enrollment",
        type(moved)(
            disposition=Disposition.HARD_DELETE,
            retention=moved.retention,
            basis=moved.basis,
        ),
    )

    assert "stays in that teacher's record" not in disclosure(), (
        "the disclosure is printed unconditionally rather than derived "
        "from the enrollment disposition"
    )


# ---------------------------------------------------------------------
# The account entry: the disposition AND its basis [NFR14.101].
# ---------------------------------------------------------------------


def test_the_account_entry_is_hard_delete() -> None:
    """The manifest records the human's 2026-10-25 decision [BR1.1].

    :return: None
    """
    assert DISPOSITIONS["account"].disposition is Disposition.HARD_DELETE


def test_the_account_basis_no_longer_argues_against_hard_delete() -> None:
    """The basis was corrected with the disposition [NFR14.101].

    **The subtle half, and the one a mechanical check nearly misses.**
    The generator reads the ``basis`` field. The previous text argued
    FOR anonymization -- that a hard delete would free the number for
    reuse while enrollments still referenced the account -- so
    correcting only the disposition would publish, as the stated
    reasoning for a hard delete, an argument against doing one. That is
    a document mechanically consistent with the code and substantively
    wrong, which is worse than the three-way disagreement it replaced:
    that one was at least visible.

    :return: None
    """
    basis = DISPOSITIONS["account"].basis.lower()

    assert "anonymized rather than removed" not in basis, (
        "the account basis still argues for anonymization while the "
        "disposition is HARD_DELETE [NFR14.101]"
    )
    assert "would free the number for reuse" not in basis, (
        "the account basis still states the hazard as a reason NOT to "
        "hard delete; `0007`'s SET NULL is what closes it"
    )
    assert "removed outright" in basis, (
        "the account basis does not describe what now happens"
    )


# ---------------------------------------------------------------------
# The marker contract [NFR16.6].
# ---------------------------------------------------------------------


def test_only_the_marker_region_changes() -> None:
    """Human prose outside the markers survives byte for byte.

    **The property the whole marker design exists for.** Generating the
    entire document would discard the contact address, the reasoning a
    parent needs, and the plain-language summary -- prose a person
    wrote and a reviewer read.

    :return: None
    """
    original = (
        "# Policy\n\nHand-written intro a reviewer approved.\n\n"
        f"{BEGIN_MARKER}\nstale generated text\n{END_MARKER}\n\n"
        "Hand-written outro, including an em dash — and ৳ in Bangla.\n"
    )

    regenerated = generated_document(original)

    assert regenerated != original, "nothing was regenerated"
    head_marker = original.index(BEGIN_MARKER)
    assert regenerated[:head_marker] == original[:head_marker], (
        "prose BEFORE the markers was modified"
    )
    tail = original[original.index(END_MARKER) :]
    assert regenerated.endswith(tail), "prose AFTER the markers was modified"


def test_a_document_without_markers_is_refused() -> None:
    """A missing marker raises rather than appending a second region.

    A document whose markers have been removed is corrupted, not stale.
    Appending a fresh region would leave two factual tables in one
    policy, which is the rival-source problem this generator exists to
    end.

    :return: None
    """
    with pytest.raises(ValueError, match="missing its generated-region"):
        generated_document("# Policy\n\nNo markers here.\n")


def test_reversed_markers_are_refused() -> None:
    """An end marker before its begin marker raises.

    :return: None
    """
    with pytest.raises(ValueError, match="end marker precedes"):
        generated_document(f"# P\n\n{END_MARKER}\nx\n{BEGIN_MARKER}\n")


def test_regeneration_is_idempotent() -> None:
    """Regenerating an already-current document changes nothing.

    Without this, a correct gate and a generator that appends on every
    run are indistinguishable until the policy has grown three copies
    of its own table.

    :return: None
    """
    current = COMMITTED.read_text(encoding="utf-8")
    once = generated_document(current)
    assert generated_document(once) == once


# ---------------------------------------------------------------------
# What the policy must never show a parent.
# ---------------------------------------------------------------------


def test_every_manifest_table_has_a_plain_language_description() -> None:
    """No database table name reaches the generated page.

    **This fails for a table a later unit adds**, which is the point:
    ``queued_submission`` or ``batch_subject`` on the document a
    regulator reads is a schema dump pretending to be a disclosure, and
    the moment to decide how to describe a table to a parent is when it
    is added.

    :return: None
    """
    missing = [table for table in DISPOSITIONS if not _describable(table)]
    assert missing == [], (
        f"these tables are in the manifest with no plain-language "
        f"description: {sorted(missing)}"
    )


def _describable(table: str) -> bool:
    """Report whether a table has a description.

    :param table: The table name
    :return: True when ``describe`` answers rather than raising
    """
    try:
        describe(table)
    except KeyError:
        return False
    return True


def test_no_raw_table_name_appears_in_the_generated_region() -> None:
    """The output names no table and no enum value.

    The complement of the test above, asserted over the OUTPUT rather
    than over the description map -- so a table name reaching the page
    by some other route is caught too.

    Table names that are ordinary English words a policy legitimately
    uses -- ``session``, ``account`` and the rest of the set below -- are
    excluded; every other table name is not.

    :return: None
    """
    region = render()
    english_words = {"session", "account", "exam", "mark", "batch", "owner"}

    for table in DISPOSITIONS:
        if table in english_words:
            continue
        assert table not in region, (
            f"the generated policy shows the raw table name {table!r}"
        )

    for disposition in Disposition:
        assert disposition.value not in region
    for retention in RetentionClass:
        assert retention.value not in region


def test_life_of_account_is_not_rendered_as_deletion_of_the_account() -> None:
    """``LIFE_OF_ACCOUNT`` never reads "until the account is deleted".

    **This is a regression test for a false disclosure this generator's
    first output actually produced.** Retention and disposition answer
    different questions -- retention is what removes a row when nobody
    has asked for anything; disposition is what a deletion request does
    -- and rendering the class as "until the account is deleted" put
    that phrase against the ``RETAIN_WITH_BASIS`` rows, which by
    definition SURVIVE the account's deletion. The page then told a
    regulator the opposite of what the code does, on exactly the point
    ADR-012 exists to disclose.

    :return: None
    """
    region = _generated_region(
        generated_document(COMMITTED.read_text(encoding="utf-8"))
    )

    retained = [
        table
        for table, governance in DISPOSITIONS.items()
        if governance.disposition is Disposition.RETAIN_WITH_BASIS
    ]
    assert retained, "no RETAIN_WITH_BASIS tables; this test is vacuous"

    heading, _, retained_section = region.partition(
        "### Kept even after you delete your account"
    )
    assert retained_section, (
        "the retained-records section is not headed as surviving "
        "deletion, so a reader cannot tell these rows outlive an "
        "erasure request"
    )
    assert "until the account is deleted" not in retained_section, (
        "a record that SURVIVES account deletion is described as kept "
        "'until the account is deleted'"
    )
    assert heading is not None
