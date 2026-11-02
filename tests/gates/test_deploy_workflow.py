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
- **A deploy is not an outage, and a failed one undoes itself** [OPS-6].
  The refresh launches before it terminates; the smoke goes through the
  public URL; a failure after the release was recorded restores the
  previous one.
- **No host can migrate before a named restore point exists** [OPS-7].
  The new host runs ``alembic upgrade head`` at boot, so the snapshot
  must be complete before the deployment state is written -- a failed
  snapshot then changes nothing.
"""

from __future__ import annotations

import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"
ROLL = ROOT / "deploy" / "roll.sh"


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


def test_the_refresh_launches_before_it_terminates() -> None:
    roll = ROLL.read_text()

    assert '"MinHealthyPercentage":100' in roll
    assert '"MaxHealthyPercentage":200' in roll
    assert 'MinHealthyPercentage":0' not in roll
    steps = _steps("release")
    runs = [str(s.get("run", "")) for s in steps]
    assert any("deploy/roll.sh" in r for r in runs)


def test_the_smoke_goes_through_the_public_url() -> None:
    smoke = [s for s in _steps("release") if s.get("id") == "smoke"]

    assert smoke, "the release job has no smoke step"
    run = str(smoke[0]["run"])
    assert "deploy/smoke.py" in run
    assert "/api-url" in run
    assert "127.0.0.1" not in run


def test_a_failed_release_is_rolled_back() -> None:
    steps = _steps("release")
    ids = [s.get("id") for s in steps]
    rollback = [s for s in steps if "Roll back" in str(s.get("name", ""))]

    assert len(rollback) == 1
    assert "failure()" in str(rollback[0]["if"])
    assert "steps.record.outcome" in str(rollback[0]["if"])
    # The previous release is captured before it is overwritten.
    assert ids.index("previous") < ids.index("record") < ids.index("roll")


def test_the_database_is_snapshotted_before_anything_can_migrate() -> None:
    steps = _steps("release")
    ids = [s.get("id") for s in steps]

    assert "snapshot" in ids
    assert ids.index("snapshot") < ids.index("record") < ids.index("roll")
    run = str(steps[ids.index("snapshot")]["run"])
    assert "create-db-snapshot" in run
    assert "wait db-snapshot-available" in run
    # A step that tolerated failure would let the deploy proceed with
    # no restore point, which is exactly the absence this exists for.
    assert not steps[ids.index("snapshot")].get("continue-on-error")
