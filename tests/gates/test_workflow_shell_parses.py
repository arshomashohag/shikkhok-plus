"""Every shell step in every workflow must parse as bash.

**A step that cannot parse fails only when it runs**, and for
``release-android.yml`` that is after a version tag has been pushed.
v1.8.0's first run died in eleven seconds on an apostrophe inside
``"${APP_LINK_HOST:-(the backend's host)}"``: within double quotes bash
requires the single quote to have a match, so the whole step was a
syntax error. Nothing between the commit and the tag executed that
script, so nothing noticed.

``bash -n`` reads a script without running it, which is exactly the
check that was missing: cheap, deterministic, and run here on the pull
request rather than on the tag.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

BASH = shutil.which("bash")


def _shell_steps() -> list[tuple[str, str]]:
    """Collect every ``run:`` script that executes under bash.

    Steps whose job or step declares a non-bash shell are skipped,
    because ``bash -n`` would judge them by the wrong grammar.

    :return: ``(label, script)`` pairs, one per step
    """
    steps: list[tuple[str, str]] = []
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(workflow.read_text())
        for job_id, job in (document.get("jobs") or {}).items():
            job_shell = (job.get("defaults") or {}).get("run", {}).get("shell", "bash")
            for index, step in enumerate(job.get("steps") or []):
                script = step.get("run")
                if not script:
                    continue
                shell = step.get("shell", job_shell)
                if not str(shell).startswith("bash"):
                    continue
                name = step.get("name", f"step {index}")
                steps.append((f"{workflow.name}:{job_id}:{name}", script))
    return steps


def _parse_error(script: str) -> str | None:
    """Return bash's complaint about a script, or ``None`` if it parses.

    :param script: The step's shell text
    :return: The error output, or ``None``
    """
    assert BASH is not None
    result = subprocess.run(  # noqa: S603 -- fixed argv, script on stdin
        [BASH, "-n"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return None
    # A non-zero exit is a failure even if bash printed nothing.
    return result.stderr.strip() or f"bash -n exited {result.returncode}"


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
def test_every_workflow_shell_step_parses() -> None:
    steps = _shell_steps()
    # **The precondition, asserted**: a loader that found nothing would
    # make the check below pass against any content.
    assert len(steps) > 50, f"found only {len(steps)} shell steps"

    offences = [
        f"{label}: {error}"
        for label, script in steps
        if (error := _parse_error(script)) is not None
    ]
    assert offences == [], "workflow steps that bash cannot parse:\n" + "\n".join(
        offences
    )


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
def test_the_check_can_actually_fire() -> None:
    # The exact shape that broke v1.8.0.
    broken = 'echo "host: ${APP_LINK_HOST:-(the backend' + "'" + 's host)}"\n'
    assert _parse_error(broken) is not None
    assert _parse_error('echo "host: ${APP_LINK_HOST:-(the backend host)}"\n') is None
