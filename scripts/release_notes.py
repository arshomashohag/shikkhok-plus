"""Generate release notes from conventional commits.

``team.md`` records that commits are conventional-commit shaped "so the
Bolt squash commit and release notes can be generated rather than
written". This is the thing that cashes that in.

Two outputs, because they have different audiences and different
limits: a ``CHANGELOG.md`` section for the repository, and a plain
Play release-notes file capped at the 500 characters Play enforces.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from typing import Final

#: Play truncates anything longer, silently, per language.
PLAY_NOTE_LIMIT: Final = 500

#: Conventional-commit prefix to the heading a reader understands.
#: Ordered: a reader scanning a changelog wants what is new first and
#: what broke last.
SECTIONS: Final = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Performance",
    "refactor": "Changed",
    "docs": "Documentation",
    "build": "Build",
    "ci": "Build",
    "test": "Tests",
    "chore": "Internal",
}

#: Not shown to users of the app. A teacher reading the Play listing
#: does not care that a CI workflow changed.
INTERNAL: Final = frozenset({"Build", "Tests", "Internal", "Documentation"})

_COMMIT = re.compile(
    r"^(?P<type>[a-z]+)"
    r"(?:\((?P<scope>[^)]*)\))?"
    r"(?P<breaking>!)?"
    r": (?P<subject>.+)$"
)


@dataclass(frozen=True, slots=True)
class Change:
    """One parsed conventional commit.

    :ivar section: The heading this change belongs under
    :ivar scope: The commit's scope, if it declared one
    :ivar subject: The commit subject, without its prefix
    :ivar breaking: Whether the commit marked itself breaking
    """

    section: str
    scope: str | None
    subject: str
    breaking: bool

    def rendered(self) -> str:
        """Render as a changelog bullet.

        :return: The bullet text, without its leading dash
        """
        prefix = f"**{self.scope}**: " if self.scope else ""
        return f"{prefix}{self.subject}"


def previous_tag() -> str | None:
    """Find the most recent release tag.

    :return: The tag name, or None when no release has been tagged
    """
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "--match", "v*"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None


def commits_since(tag: str | None) -> list[str]:
    """Read commit subjects since a tag.

    :param tag: The tag to start after, or None for all history
    :return: Commit subject lines, newest first
    """
    span = f"{tag}..HEAD" if tag else "HEAD"
    result = subprocess.run(
        ["git", "log", span, "--pretty=format:%s", "--no-merges"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def parse(subjects: list[str]) -> list[Change]:
    """Parse conventional-commit subjects.

    Subjects that do not match the convention are kept under
    ``Changed`` rather than discarded: a dropped commit is a release
    note that silently omits a real change, which is worse than an
    untidy one.

    :param subjects: Raw commit subject lines
    :return: Parsed changes
    """
    changes: list[Change] = []
    for subject in subjects:
        match = _COMMIT.match(subject)
        if match is None:
            changes.append(Change("Changed", None, subject, False))
            continue
        section = SECTIONS.get(match["type"], "Changed")
        changes.append(
            Change(
                section=section,
                scope=match["scope"] or None,
                subject=match["subject"],
                breaking=bool(match["breaking"]),
            )
        )
    return changes


def changelog_section(version: str, changes: list[Change]) -> str:
    """Render the CHANGELOG.md section for a version.

    :param version: The version being released
    :param changes: The changes it contains
    :return: Markdown, ending in a blank line
    """
    lines = [f"## {version} - {date.today().isoformat()}", ""]

    breaking = [c for c in changes if c.breaking]
    if breaking:
        lines += ["### Breaking", ""]
        lines += [f"- {c.rendered()}" for c in breaking]
        lines.append("")

    for heading in ("Added", "Fixed", "Performance", "Changed"):
        items = [c for c in changes if c.section == heading and not c.breaking]
        if items:
            lines += [f"### {heading}", ""]
            lines += [f"- {c.rendered()}" for c in items]
            lines.append("")

    internal = [
        c for c in changes if c.section in INTERNAL and not c.breaking
    ]
    if internal:
        lines += ["### Internal", ""]
        lines += [f"- {c.rendered()}" for c in internal]
        lines.append("")

    if len(lines) == 2:
        lines += ["No user-visible changes.", ""]

    return "\n".join(lines)


def play_notes(changes: list[Change]) -> str:
    """Render a DRAFT of the Play release notes.

    **A draft, and the distinction matters.** These are generated from
    commit subjects, which are written for developers -- "retire the
    seed script" and "count cannot derive from an unknown ARN" are
    accurate and meaningless to a teacher reading the store listing.
    A release pipeline that published these unedited would be shipping
    an infrastructure changelog to parents.

    So this produces a starting point that the release workflow commits
    for editing, never something uploaded directly. Internal sections
    are dropped and the result is capped at Play's limit, which Play
    otherwise enforces by truncating silently.

    :param changes: The changes in this release
    :return: Plain text of at most PLAY_NOTE_LIMIT characters
    """
    visible = [c for c in changes if c.section not in INTERNAL]
    if not visible:
        return "Stability and performance improvements."

    lines: list[str] = []
    for c in visible:
        bullet = f"- {c.subject}"
        # Measured BEFORE appending, so Play never truncates mid-word.
        if len("\n".join(lines + [bullet])) > PLAY_NOTE_LIMIT:
            break
        lines.append(bullet)

    return "\n".join(lines) or "Stability and performance improvements."


def main() -> int:
    """Generate release notes.

    :return: Process exit code
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--changelog", default="CHANGELOG.md")
    parser.add_argument("--play-notes", default=None)
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Write nothing; print the section to stdout",
    )
    args = parser.parse_args()

    tag = previous_tag()
    subjects = commits_since(tag)
    if not subjects:
        print(
            f"No commits since {tag or 'the start of history'}.",
            file=sys.stderr,
        )
        return 1

    changes = parse(subjects)
    section = changelog_section(args.version, changes)

    if args.print_only:
        print(section)
        return 0

    import pathlib

    path = pathlib.Path(args.changelog)
    existing = path.read_text() if path.exists() else (
        "# Changelog\n\n"
        "Generated from conventional commits by "
        "`scripts/release_notes.py`.\n\n"
    )
    header, _, body = existing.partition("\n\n")
    intro, _, rest = body.partition("\n\n")
    path.write_text(f"{header}\n\n{intro}\n\n{section}\n{rest}".rstrip() + "\n")

    if args.play_notes:
        pathlib.Path(args.play_notes).write_text(play_notes(changes) + "\n")

    print(f"{len(changes)} change(s) since {tag or 'the start'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
