"""Every job that records a heartbeat has a cron entry that runs it.

**The retention purge was built, tested and never scheduled** [C-01]:
its heartbeat constant existed, its module wrote the row, and nothing on
any host ever invoked it, so the published retention windows were kept
by nothing. Nothing noticed because the freshness check enumerates the
heartbeat rows that EXIST, and a job that never ran writes none.

So the obligation is asserted from the code side. Every ``*_JOB``
constant in ``app/db/models.py`` names a job; the module that records a
heartbeat under it (``job_name=<CONSTANT>``) is found by reading the
source; and the rendered boot script must install a cron entry running
``python -m <that module>``. A job added without its schedule fails
here, on the pull request.
"""

from __future__ import annotations

import ast
import pathlib
import re

from tests.gates.test_user_data_template import (
    TEMPLATE,
    TEMPLATE_VALUES,
    _render,
    _shell_bodies,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODELS = ROOT / "app" / "db" / "models.py"


def _job_constants() -> set[str]:
    """Collect every module-level ``*_JOB`` string constant in the models.

    :return: The constant names
    """
    tree = ast.parse(MODELS.read_text())
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        else:
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            names.update(name for name in targets if name.endswith("_JOB"))
    return names


def _writers(constant: str) -> set[str]:
    """Find the modules that record a heartbeat under one job name.

    :param constant: The ``*_JOB`` constant
    :return: Dotted module names, e.g. ``app.fees.commands``
    """
    pattern = re.compile(rf"\bjob_name\s*(?::\s*str\s*)?=\s*{constant}\b")
    found: set[str] = set()
    for path in (ROOT / "app").rglob("*.py"):
        if pattern.search(path.read_text()):
            relative = path.relative_to(ROOT).with_suffix("")
            found.add(".".join(relative.parts))
    return found


def _cron_commands() -> list[str]:
    """List every command a cron entry in the boot script runs.

    :return: The command text of each entry
    """
    bodies = _shell_bodies(_render(TEMPLATE.read_text(), TEMPLATE_VALUES))
    return [body.lines[0] for body in bodies if body.name.startswith("cron entry in")]


def test_the_guard_sees_the_jobs_and_the_crontab() -> None:
    # Not vacuous: there are jobs, each has a writer, and cron entries
    # were parsed. A parser returning nothing would pass the test below.
    constants = _job_constants()

    assert {"FEE_GENERATION_JOB", "RETENTION_PURGE_JOB"} <= constants
    assert all(_writers(constant) for constant in constants), {
        constant: _writers(constant) for constant in constants
    }
    assert len(_cron_commands()) >= 2


def test_every_heartbeat_job_is_scheduled() -> None:
    commands = _cron_commands()
    missing: list[str] = []
    for constant in sorted(_job_constants()):
        for module in sorted(_writers(constant)):
            if not any(f"python -m {module} " in f"{c} " for c in commands):
                missing.append(f"{constant} ({module})")

    assert missing == [], (
        f"jobs with no cron entry: {missing}. Add one to "
        "infra/modules/app/user_data.sh.tftpl beside the fee-generation "
        "entry: a job that records a heartbeat but never runs is invisible "
        "to the freshness check, which only sees rows that exist [C-01]."
    )
