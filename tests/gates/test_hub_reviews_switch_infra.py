"""The reviews switch reaches the container, defaulting off.

The switch is read from SSM by the release, written into the runtime
env and forwarded by compose. Terraform creates the parameter ``off``
and never touches its value again, so an apply cannot flip it.
"""

from __future__ import annotations

import pathlib
import re

from tests.gates._hub_switches import (
    compose_forwards,
    parameter_block,
    released_path,
    runbook,
    steps,
    switch_paths,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY_ROLE = ROOT / "infra" / "bootstrap" / "deploy_role.tf"
SWITCH = "SHIKKHOKPLUS_HUB_REVIEWS"


def test_ssm_switch_parameter_defaults_off_and_ignores_value() -> None:
    body = parameter_block("hub_reviews")

    assert 'name  = "/shikkhokplus/${var.name_prefix}/hub-reviews"' in body or (
        '"/shikkhokplus/${var.name_prefix}/hub-reviews"' in body
    )
    assert re.search(r'type\s*=\s*"String"', body)
    assert re.search(r'value\s*=\s*"off"', body)
    assert re.search(r"ignore_changes\s*=\s*\[value\]", body)


def test_deploy_role_may_read_the_switch() -> None:
    assert '"hub-reviews"' in DEPLOY_ROLE.read_text()


def test_both_compose_files_forward_switch_defaulting_off() -> None:
    for name, values in compose_forwards(SWITCH).items():
        assert values, f"{name} does not forward {SWITCH}"
        assert set(values) == {"${SHIKKHOKPLUS_HUB_REVIEWS:-off}"}


# ---------------------------------------------------------------------------
# The "Switching reviews on" runbook [H4 Task 13]. Turning reviews on
# publishes what families write about a class, so three human checks come
# before the parameter changes: the D9 demand bar, the D8 legal review and
# the D6 declarations (hub spec, owner decisions). The commands the runbook
# gives must name the parameter Terraform actually creates, or a person
# following it writes a parameter nothing reads.
# ---------------------------------------------------------------------------


def test_switch_paths_are_the_ones_the_release_reads() -> None:
    paths = switch_paths("hub_reviews")

    assert paths == {
        "staging": "/shikkhokplus/shikkhokplus-staging/hub-reviews",
        "production": "/shikkhokplus/shikkhokplus-production/hub-reviews",
    }
    for environment, path in paths.items():
        assert released_path("hub-reviews", environment) == path


def test_runbook_lists_d8_d9_d6_before_flip() -> None:
    section = runbook("Switching reviews on")
    numbered = steps(section)

    def first(pattern: str) -> int:
        for index, step in enumerate(numbered):
            if re.search(pattern, step):
                return index
        raise AssertionError(f"no runbook step matches {pattern!r}")

    d9 = first(r"\bD9\b")
    d8 = first(r"\bD8\b")
    d6 = first(r"\bD6\b")
    flip = first(r"aws ssm put-parameter")
    deploy = first(r"(?i)dispatch")
    check = first(r"(?i)batch page in staging shows the reviews\s+section")
    assert len(numbered) == 6
    assert [d9, d8, d6, flip, deploy, check] == [0, 1, 2, 3, 4, 5]
    # The D9 step carries the spec's own bars, not a paraphrase of them.
    assert "20%" in numbered[d9] and "15%" in numbered[d9]

    commands = re.findall(r"aws ssm put-parameter[^\n`]*", section)
    paths = switch_paths("hub_reviews")
    named = {
        re.search(r"--name (\S+)", command).group(1)  # type: ignore[union-attr]
        for command in commands
    }
    assert named == set(paths.values()), "a put-parameter names another path"
    for command in commands:
        assert "--overwrite" in command
        assert re.search(r"--value (on|off)\b", command)
    for environment, path in paths.items():
        assert re.search(rf"--name {re.escape(path)} .*--value on\b", section)
        assert f"| {environment} | `{path}` |" in section
    # Switching off is the same command with `off`.
    assert re.search(r"(?i)switch(ing)? off.*`off`", section, re.S)
