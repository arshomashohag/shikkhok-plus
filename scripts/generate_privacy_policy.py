"""Generate the privacy policy's factual region from the governance manifest.

``docs/legal/README.md`` has been headed *"The policy is generated from
the schema, not written beside it"* since before any generator existed.
The text underneath it was hand-written AGAINST the schema and verified
by a five-row table of manual checks -- careful work, and not what the
heading claimed. **This makes the heading true.**

The argument for it is evidence rather than principle, and this unit was
handed the evidence: ``dispositions.py`` said the account row was
anonymized, ``PRIVACY.md`` promised the phone number was "deleted
permanently", and ``README.md``'s own table said "hard delete". Three
documents, three answers, nothing failing. **A regenerate-and-compare
gate is what would have caught that**, and it is the same shape as the
built OpenAPI schema-diff gate for the same reason: a committed artifact
derived from code must be regenerated in the change that alters its
source, or it becomes a claim about an older version.

Three properties make it worth more than the sentence it replaces.

**It writes between MARKERS, and the marker region is the unit of
comparison** [NFR16.6]. Generating the whole document would discard the
prose a person wrote and a reviewer read -- the contact address, the
reasoning a parent needs about a teacher's business record, the
plain-language summary. What is generated is the part that can silently
stop matching the code: which data is deleted, which is kept, and for
how long.

**It is DETERMINISTIC** [NFR16.7]: same manifest, same bytes. No
timestamp, no iteration over an unordered mapping. A generator that
emitted the date would make every build a diff and the gate would become
noise within a week -- which is how a gate stops being read and then
stops being a gate.

**It emits ADR-012's disclosure** [NFR14.89, BR2.2]: that a
teacher-typed name survives the account's deletion. A person who declined
a seat still appears in a teacher's record under a name they did not
choose. That is the sharpest edge of this product's privacy model, and a
policy omitting it is a false statement to a regulator about children's
data.

**What this does NOT close** [NFR14.90]: nothing mechanically prevents a
factual claim being written in the prose OUTSIDE the markers, where the
comparison does not reach. Removing the rival hand-written table shrinks
that surface; it does not close it. Named here rather than rounded up.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Final

from app.governance.dispositions import (
    DISPOSITIONS,
    Disposition,
    RetentionClass,
    TableGovernance,
)

#: The committed policy, relative to the repository root.
POLICY_PATH: Final = Path("docs/legal/PRIVACY.md")

#: The region boundaries. HTML comments, so they are invisible in every
#: renderer Play might read the policy through while staying obvious in
#: the source a reviewer reads.
BEGIN_MARKER: Final = "<!-- BEGIN GENERATED: governance manifest -->"
END_MARKER: Final = "<!-- END GENERATED: governance manifest -->"

#: How each disposition reads to a person who is not a developer. The
#: policy is read by parents and by a regulator, so the manifest's enum
#: names never reach the page.
_DISPOSITION_HEADING: Final[dict[Disposition, str]] = {
    Disposition.HARD_DELETE: "Deleted outright when you delete your account",
    Disposition.ANONYMIZE_IN_PLACE: (
        "Kept, with the details that identify you removed"
    ),
    # **States the survival explicitly.** This is the heading a
    # regulator reads over the rows that outlive an erasure request, so
    # it says so in the heading rather than leaving it to be inferred
    # from the word "kept".
    Disposition.RETAIN_WITH_BASIS: (
        "Kept even after you delete your account, because the same "
        "record is someone else's too"
    ),
    # **This heading must do two jobs at once, and the second is the
    # reason it is this long.** It has to stop a reader concluding these
    # rows are deleted with the account -- the false claim that put this
    # section here -- without letting them conclude instead that we are
    # quietly keeping personal data under a reassuring label. So the
    # heading itself says the records are not about a person, and the
    # paragraph under it says what they are and why a deletion leaves
    # them alone. A heading reading "Kept" alone would have swapped one
    # wrong impression for another.
    Disposition.NOT_PERSONAL: (
        "Not about you, and not changed when you delete your account"
    ),
}

#: Plain-language retention windows.
#:
#: **``LIFE_OF_ACCOUNT`` must NOT be phrased as "until the account is
#: deleted", and getting this wrong produced a false disclosure in this
#: generator's first output.** The retention class and the disposition
#: answer different questions: retention is what removes a row with NO
#: deletion request, and disposition is what a deletion request does.
#: Rendering ``LIFE_OF_ACCOUNT`` as "until the account is deleted" put
#: that phrase in the "Kept, because someone else has a claim" table --
#: against rows that by definition SURVIVE the account's deletion -- and
#: told a regulator the opposite of what the code does, on the exact
#: point ADR-012 exists to disclose. It is phrased as a non-answer here
#: because it IS one: no amount of elapsed time removes these rows, and
#: what a deletion does to them is the table they are listed under.
_RETENTION_TEXT: Final[dict[RetentionClass, str]] = {
    RetentionClass.DAYS_7: "7 days",
    RetentionClass.HOURS_48: "48 hours",
    RetentionClass.MONTHS_12: "12 months",
    RetentionClass.UNTIL_EXPIRY_PLUS_30_DAYS: "30 days after it expires",
    RetentionClass.LIFE_OF_ACCOUNT: "no time limit",
}

#: What each table holds, in words a parent reads. **A table with no
#: entry here is a generator failure, not a row labelled by its own
#: name**: ``queued_submission`` or ``batch_subject`` on a page a
#: regulator reads is a schema dump pretending to be a disclosure.
_TABLE_DESCRIPTION: Final[dict[str, str]] = {
    "account": "Your phone number and account record",
    "profile": "Your own name, photo and address",
    "otp_request": "One-time sign-in codes, stored only as hashes",
    "verify_attempt": "Failed and successful sign-in attempts",
    "refresh_token": "Session tokens, stored only as hashes",
    "rate_limit_counter": "Counters that limit sign-in attempts",
    "auth_audit_log": "A sign-in audit record carrying no name or code",
    "staging_sms_outbox": "Test-only message records, never used in production",
    "owner": "The link between a class and the teacher who runs it",
    "batch": "A class a teacher runs",
    "batch_subject": "A subject within a class",
    "schedule_slot": "A class's weekly timetable",
    "hidden_batch_preference": "Which classes you have hidden from your own view",
    "enrollment": "A student's place in a class, including the name the teacher typed",
    "fee_cycle": "The record that a fee was due for a month",
    "ledger_entry": "Amounts charged, paid and waived",
    "payment_claim": "A payment you reported, and the teacher's decision on it",
    "reminder_event": "A record that a teacher sent a fee reminder",
    "notification": "Messages in your in-app inbox, such as a fee reminder",
    "job_heartbeat": "When our scheduled jobs last ran; it names nobody",
    "session": "A class that was held, on a date",
    "queued_submission": "A record that a teacher's entry was received",
    "attendance": "Whether a student attended a class",
    "exam": "An exam a teacher set",
    "mark": "A student's exam result",
    "announcement": "A note a teacher posted to a class",
}


def describe(table: str) -> str:
    """Render one table's plain-language description.

    :param table: The table name, from the manifest
    :return: The description a person reads
    :raises KeyError: If the manifest carries a table this generator
        cannot describe. **Deliberately fatal**: the alternative is
        publishing a raw table name on the document a regulator reads,
        and a later unit adding a table is exactly when somebody must
        decide how to describe it to a parent.
    """
    try:
        return _TABLE_DESCRIPTION[table]
    except KeyError:
        raise KeyError(
            f"{table!r} is in the governance manifest but has no "
            "plain-language description, so the generated policy would "
            "show a database table name to a parent. Add one to "
            "_TABLE_DESCRIPTION in this file."
        ) from None


def _rows_by_disposition(
    disposition: Disposition,
) -> list[tuple[str, TableGovernance]]:
    """Select the manifest's entries for one disposition, in name order.

    **Sorted, which is what makes the output deterministic.** A dict is
    insertion-ordered in Python, so iterating the manifest directly would
    produce stable bytes today and reorder the whole document the first
    time someone moved an entry -- a diff of the entire generated region
    for a change that altered nothing.

    :param disposition: The disposition to select
    :return: ``(table, governance)`` pairs, ordered by table name
    """
    # Sorted by the DESCRIPTION, which is what a reader sees. Sorting by
    # the table name is equally deterministic and produces a list that
    # looks unordered on the page, because the column shown is not the
    # column sorted. The table name is the tie-break so the order is
    # still total if two tables ever share a description.
    return sorted(
        (
            (table, governance)
            for table, governance in DISPOSITIONS.items()
            if governance.disposition is disposition
        ),
        key=lambda pair: (describe(pair[0]), pair[0]),
    )


def disclosure() -> str:
    """Render ADR-012's disclosure, derived from the manifest [BR2.2].

    **Derived rather than hard-coded.** The sentence is emitted because
    ``enrollment`` is ``RETAIN_WITH_BASIS``; if that entry ever became
    ``HARD_DELETE``, the policy would stop claiming a name survives --
    which is the correct behaviour and the reason this reads the
    manifest rather than printing a constant.

    :return: The disclosure paragraph
    :raises KeyError: If the manifest has no ``enrollment`` entry
    """
    governance = DISPOSITIONS["enrollment"]
    if governance.disposition is Disposition.HARD_DELETE:
        return (
            "When you delete your account, the record of your place in a "
            "class is removed with it, including the name the teacher "
            "entered for you."
        )

    return (
        "**The name a teacher typed for you stays in that teacher's "
        "record.** When a teacher invites someone to a class they enter "
        "a name for that place themselves. That name belongs to the "
        "teacher's own record of the class, so it remains after you "
        "delete your account -- and it remains even if you declined the "
        "invitation and never used the app. It is not shown to anyone "
        "but that teacher. If you want it removed, contact us at the "
        "address at the top of this page and we will raise it with the "
        "teacher concerned."
    )


def teacher_disclosure() -> str:
    """Say what happens to a teacher's classes when they delete.

    **Derived from the manifest, like :func:`disclosure`.** Emitted as a
    retention statement because ``owner`` is ``RETAIN_WITH_BASIS``; were
    it ever ``HARD_DELETE``, the classes would go with the teacher and the
    page would say so instead.

    :return: The paragraph
    :raises KeyError: If the manifest has no ``owner`` entry
    """
    if DISPOSITIONS["owner"].disposition is Disposition.HARD_DELETE:
        return (
            "When a teacher deletes their account, their classes and "
            "every record in them are removed with it."
        )

    return (
        "**A teacher's classes stay with their students.** If you are a "
        "teacher and delete your account, your sign-in, your own name "
        "and address are removed, and so are your name and payment number on each "
        "of your classes. The classes themselves stay as read-only "
        "history for your students and their guardians: their "
        "record of who came to each class, their results and fee records are theirs too. No new fees "
        "fall due on those classes, and amounts already recorded as "
        "owed stay on the records, where nobody can collect them."
    )


def manifest_digest() -> str:
    """Hash every field of the manifest, including each ``basis``.

    **This is what puts the ``basis`` field inside the drift gate**
    [NFR14.101, BR2.3], and it exists because the obvious design does
    not. A generator rendering only the disposition and the retention
    class COMPARES only those: editing a ``basis`` then changes nothing
    on the page, ``make check`` stays green, and the manifest's stated
    reasoning drifts away from the published reasoning with nothing
    watching. Measured on this generator's own first version, by
    mutating a basis and finding the gate silent -- on precisely the
    field NFR14.101 is about.

    **The alternative was rendering each basis onto the page, and it
    was tried and rejected.** The basis strings are written for a
    developer reading the manifest: they name ``display_name``,
    ``RETAIN_WITH_BASIS``, ``U5``, ``U6`` and "five columns". Publishing
    them verbatim would put schema vocabulary on the document a
    regulator reads, which is the failure
    ``test_no_raw_table_name_appears_in_the_generated_region`` exists to
    prevent. A digest covers the field without publishing it.

    **It is not a substitute for a human reading the change.** A changed
    digest says the manifest moved, not that the policy is now wrong;
    what it guarantees is that nobody can move it silently.

    :return: A hex digest over the sorted manifest
    """
    payload = "\n".join(
        f"{table}\x1f{governance.disposition.value}"
        f"\x1f{governance.retention.value}\x1f{governance.basis}"
        for table, governance in sorted(DISPOSITIONS.items())
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _manifest_digest_line() -> str:
    """Render the digest as a comment rather than as prose.

    An HTML comment, so it is inside the compared region and invisible
    to a parent reading the rendered page. The explanatory sentence
    rides along because a bare hash in a legal document is the kind of
    thing a later reader deletes as noise.

    :return: The comment line
    """
    return (
        "<!-- governance manifest digest: "
        f"{manifest_digest()}\n"
        "     Covers every disposition, retention class and basis, so a\n"
        "     change to any of them fails the drift gate even when it\n"
        "     does not alter the text above. Regenerate; do not edit. -->"
    )


def render() -> str:
    """Render the generated region, without its markers.

    :return: Markdown text, beginning and ending with a newline
    """
    lines: list[str] = [
        "",
        "> This section is generated from the application's own data",
        "> rules. If the code changes and this text is not regenerated,",
        "> our build fails. It cannot quietly describe an older version.",
        "",
    ]

    # **Order matters to the reader, and NOT_PERSONAL goes LAST.** The
    # first two headings answer "what happens to my data", which is what
    # a parent opened the page for; the last one answers "what is this
    # other table then", which is only interesting once the first
    # question is settled. Leading with it would also put the least
    # consequential rows above the disclosure that a teacher-typed name
    # survives.
    for disposition in (
        Disposition.HARD_DELETE,
        Disposition.ANONYMIZE_IN_PLACE,
        Disposition.RETAIN_WITH_BASIS,
        Disposition.NOT_PERSONAL,
    ):
        rows = _rows_by_disposition(disposition)
        if not rows:
            continue

        lines += [
            f"### {_DISPOSITION_HEADING[disposition]}",
            "",
        ]
        if disposition is Disposition.NOT_PERSONAL:
            # **"one line per scheduled job", not "a single running
            # total"** [review R-04, 2026-10-25]. `job_heartbeat` is
            # keyed on `job_name` and upserted with
            # `on_conflict_do_update`, so it holds one row per job --
            # three today, and a fourth with the next scheduled job.
            # The earlier wording said "a single", which was simply
            # untrue of the table it described.
            #
            # The claim that matters to a regulator is the one after
            # it -- that the table never grows with the PEOPLE using
            # the service -- and that was true either way, which is
            # exactly why the false half survived a careful read. A
            # generated document is not true because it is generated.
            lines += [
                "These records are about how the service itself is "
                "running, not about any person. They hold no name, no "
                "phone number and nothing you wrote, and they are not "
                "linked to your account, so there is nothing in them "
                "for a deletion request to remove. We say so here "
                "rather than leaving them off the page: the counters "
                "below are what stop somebody flooding a phone number "
                "with sign-in codes, and clearing them on request "
                "would turn account deletion into a way of switching "
                "that protection off. Where the table below gives a "
                "time, the record clears itself after it; where it "
                "says there is no time limit, it is one line per "
                "scheduled job, overwritten on each run rather than "
                "appended to, so it never grows with the people using "
                "the service.",
                "",
            ]
        lines += [
            # **"Removed anyway after", not "Kept for".** The column is
            # the RETENTION window -- what removes a row when nobody has
            # asked for anything -- and the heading above it already
            # states what a deletion request does. Labelling it "Kept
            # for" invited the two to be read as one answer, which is
            # how this generator's first output claimed that records
            # surviving deletion were kept "until the account is
            # deleted".
            "| Data | Removed anyway after |",
            "|---|---|",
        ]
        lines += [
            f"| {describe(table)} | {_RETENTION_TEXT[governance.retention]} |"
            for table, governance in rows
        ]
        lines.append("")

    lines += [disclosure(), "", teacher_disclosure(), "", _manifest_digest_line(), ""]
    return "\n".join(lines)


def generated_document(current: str) -> str:
    """Produce the policy with its generated region replaced.

    Only the region between the markers is touched. Everything outside
    them -- the prose a person wrote and a reviewer read -- is returned
    byte for byte.

    :param current: The committed policy's full text
    :return: The policy with a current generated region
    :raises ValueError: If the markers are missing or out of order,
        which is a corrupted document rather than drift and must not be
        "fixed" by appending a second region
    """
    begin = current.find(BEGIN_MARKER)
    end = current.find(END_MARKER)

    if begin == -1 or end == -1:
        raise ValueError(
            f"{POLICY_PATH} is missing its generated-region markers. "
            f"Expected {BEGIN_MARKER!r} and {END_MARKER!r}."
        )
    if end < begin:
        raise ValueError(f"{POLICY_PATH}'s end marker precedes its begin marker.")

    head = current[: begin + len(BEGIN_MARKER)]
    tail = current[end:]
    return f"{head}\n{render()}{tail}"


def main() -> int:
    """Regenerate the policy, or check it for drift.

    ``--check`` is the gate's shape and ``--write`` is the only
    sanctioned fix, exactly as ``make openapi`` is for the contract. The
    asymmetry is deliberate: hand-editing the committed file to turn a
    red check green inverts the control into a rubber stamp, and it
    looks precisely like fixing the problem.

    :return: 0 when the file is current or was written, 1 on drift
    """
    parser = argparse.ArgumentParser(description="Generate the privacy policy.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the committed file is stale; write nothing",
    )
    parser.add_argument("--path", default=str(POLICY_PATH))
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"{path} does not exist.", file=sys.stderr)
        return 1

    current = path.read_text(encoding="utf-8")
    expected = generated_document(current)

    if current == expected:
        print(f"{path} is current.")
        return 0

    if args.check:
        print(
            f"{path} is stale. Run `python3 -m scripts.generate_privacy_policy` "
            "to regenerate it, then READ THE DIFF: it is a change to what "
            "this product tells a regulator about children's data.",
            file=sys.stderr,
        )
        return 1

    path.write_text(expected, encoding="utf-8")
    print(f"{path} regenerated — now read the diff.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
