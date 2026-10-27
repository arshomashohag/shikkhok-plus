"""The deployment pipeline must never run the test suite.

**A deploy is not a place to discover a red suite.** By the time a
workflow is building an image and applying Terraform, the question
"do the tests pass?" has already been answered — on the pull request,
against the commit under review. Re-running them here buys nothing
and costs two things that matter:

- **Time, at the worst moment.** A production deploy is scheduled
  outside Bangladesh classroom hours precisely because a restart
  during a live class is the failure a teacher will not forgive
  [D-9, TC-8]. Twelve minutes of pytest inside that window is twelve
  minutes of nothing happening.
- **A false sense of what was verified.** A suite run at deploy time
  runs against the deploy runner's environment, not the one the image
  was built from. A pass there does not mean what a pass on the pull
  request means, and treating the two as equivalent is how a gate
  stops meaning anything.

This covers releases as well as deploys, by decision on 2026-10-27.
`release-android.yml` previously ran the Kotlin unit suite with the
reasoning "a release that skipped the tests would be the one release
where skipping them mattered", and that step was removed.

**What that gives up, stated rather than glossed**: a tag can be cut
from a commit no pull request tested, and nothing in the release
workflow would now notice. The checks that remain there — the merged
manifest permission allowlist and the minified DEX identifier scan —
are about the forbidden-identifier set [TC-3, TC-4, D-35, D-37], not
about correctness. The control that replaces the removed step is
discipline about what gets tagged, which is a weaker control than a
job, and saying so here is the honest record.

This is a guard, not a preference: the pipelines do not run tests
today, and the point of asserting it is that nobody can add one later
without this failing first.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

#: Workflows that deploy or release. `check.yml` is deliberately absent
#: — running the suite is its entire job.
DEPLOYMENT_WORKFLOWS: tuple[str, ...] = (
    "deploy.yml",
    "release-android.yml",
)

#: What a test invocation looks like in a `run:` block. Matched against
#: the command text rather than the whole file, so a COMMENT explaining
#: why tests are absent does not trip the guard — the thing being
#: forbidden is the execution, not the word.
TEST_INVOCATIONS: tuple[tuple[str, str], ...] = (
    (r"\bpytest\b", "pytest"),
    (r"\bmake\s+test\b", "make test"),
    (r"\bmake\s+check\b", "make check"),
    (r"\bmake\s+gates\b", "make gates"),
    (r"\bmake\s+contract\b", "make contract"),
    (r"testDebugUnitTest", "the Android unit suite"),
)


def _run_commands(workflow: pathlib.Path) -> str:
    """Extract every shell command a workflow runs.

    Comments inside those commands are stripped, so prose explaining
    why a suite is NOT run here cannot be mistaken for running it.

    :param workflow: The workflow file to read
    :return: The command text, with comments removed
    """
    text = workflow.read_text()
    commands: list[str] = []

    for block in re.finditer(r"^\s*(?:-\s*)?run:\s*(.*)$", text, re.MULTILINE):
        line = block.group(1).strip()
        if line in {"|", ">", "|-", ">-"}:
            # A block scalar: take the indented lines beneath it.
            start = block.end()
            rest = text[start:].split("\n")[1:]
            indent = None
            for candidate in rest:
                if not candidate.strip():
                    continue
                width = len(candidate) - len(candidate.lstrip())
                if indent is None:
                    indent = width
                if width < indent:
                    break
                commands.append(candidate)
            continue
        commands.append(line)

    joined = "\n".join(commands)
    return re.sub(r"#.*$", "", joined, flags=re.MULTILINE)


def test_no_deployment_workflow_runs_the_test_suite() -> None:
    offences: list[str] = []

    for name in DEPLOYMENT_WORKFLOWS:
        workflow = WORKFLOWS / name
        assert workflow.exists(), f"{name} is missing; update this guard"

        commands = _run_commands(workflow)
        for pattern, label in TEST_INVOCATIONS:
            if re.search(pattern, commands):
                offences.append(f"{name} runs {label}")

    assert offences == [], (
        f"a deployment workflow runs tests: {offences}. The suite "
        "belongs on the pull request, where a red result blocks the "
        "merge. At deploy time it delays a release window chosen to "
        "avoid classroom hours, and it verifies the deploy runner "
        "rather than the image being shipped."
    )


def test_the_guard_can_actually_fire() -> None:
    # **Without this, the test above passes on an empty match set and
    # on a parser that silently returns nothing.** That is this
    # project's most-repeated defect shape: a gate that cannot fail.
    pretend = "          pytest tests -q\n"
    stripped = re.sub(r"#.*$", "", pretend, flags=re.MULTILINE)

    assert any(re.search(pattern, stripped) for pattern, _ in TEST_INVOCATIONS), (
        "the patterns no longer match a real invocation"
    )


def test_the_parser_reads_real_commands() -> None:
    # The other half: the patterns can fire, but only against text the
    # parser actually produced. An extractor returning "" would make
    # the guard vacuous while every assertion still passed.
    commands = _run_commands(WORKFLOWS / "deploy.yml")

    assert len(commands.strip()) > 200, (
        "the workflow parser extracted almost nothing; the guard would "
        "pass against any content"
    )
    assert "terraform" in commands.lower() or "docker" in commands.lower(), (
        "the parser did not find the deploy commands it should see"
    )


def test_the_check_workflow_does_run_the_suite() -> None:
    # The inverse, asserted so the two workflows cannot quietly swap
    # roles: tests belong in `check`, and if they ever vanish from it
    # the guard above would pass over a pipeline that tests nothing.
    commands = _run_commands(WORKFLOWS / "check.yml")

    assert re.search(r"\bmake\b", commands), "check.yml stopped running make"
