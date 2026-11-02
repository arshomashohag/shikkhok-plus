"""Ordering and identity properties of the deploy workflow.

The deploy workflow cannot be run from a pull request -- it needs AWS,
an approval and a real environment -- so the properties that make it
safe are asserted on its text instead. Each one is a defect that
shipped, or a control whose absence would be silent:

- **The image is tagged by the commit checked out** [OPS-9]. The
  workflow builds ``inputs.ref`` but tagged, skipped and recorded by
  ``github.sha``, the commit it was dispatched from. A rollback to an
  older ref then redeployed main's image, or pushed old code under
  main's SHA into an IMMUTABLE repository, where it can never be fixed.
"""

from __future__ import annotations

import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"


def _without_comments(text: str) -> str:
    """Drop YAML and shell comment lines, so prose cannot trip a guard.

    :param text: Workflow source
    :return: The same text with whole-line comments removed
    """
    return "\n".join(
        line for line in text.split("\n") if not line.strip().startswith("#")
    )


def _steps(job: str) -> list[dict[str, object]]:
    """Return a job's steps, parsed.

    :param job: The job id
    :return: Its steps, in order
    """
    workflow = yaml.safe_load(DEPLOY.read_text())
    steps: list[dict[str, object]] = workflow["jobs"][job]["steps"]
    return steps


def test_the_dispatching_commit_never_names_the_artifact() -> None:
    code = _without_comments(DEPLOY.read_text())

    assert "github.sha" not in code
    assert "GITHUB_SHA" not in code


def test_every_job_checks_out_the_commit_the_plan_resolved() -> None:
    workflow = yaml.safe_load(DEPLOY.read_text())
    plan_steps = workflow["jobs"]["plan"]["steps"]
    resolve = [s for s in plan_steps if s.get("id") == "commit"]

    assert resolve, "the plan job no longer resolves the commit"
    assert "git rev-parse HEAD" in str(resolve[0]["run"])

    for name, job in workflow["jobs"].items():
        if name == "plan":
            continue
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("actions/checkout"):
                ref = step.get("with", {}).get("ref")
                assert ref == "${{ needs.plan.outputs.sha }}", (name, ref)


def test_the_guard_reads_real_steps() -> None:
    # Not vacuous: the release job exists and pushes by the plan's SHA.
    pushes = [
        s
        for s in _steps("release")
        if str(s.get("uses", "")).startswith("docker/build-push-action")
    ]

    assert pushes
    tags = str(pushes[0]["with"]["tags"])  # type: ignore[index]
    assert re.search(r"needs\.plan\.outputs\.sha", tags)
