"""The reviews switch reaches the container, defaulting off.

The switch is read from SSM by the release, written into the runtime
env and forwarded by compose. Terraform creates the parameter ``off``
and never touches its value again, so an apply cannot flip it.
"""

from __future__ import annotations

import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "infra" / "modules" / "app" / "deployment_state.tf"
DEPLOY_ROLE = ROOT / "infra" / "bootstrap" / "deploy_role.tf"
COMPOSES = (
    ROOT / "docker-compose.yml",
    ROOT / "deploy" / "docker-compose.staging.yml",
)
SWITCH = "SHIKKHOKPLUS_HUB_REVIEWS"


def test_ssm_switch_parameter_defaults_off_and_ignores_value() -> None:
    text = STATE.read_text()
    block = re.search(
        r'resource "aws_ssm_parameter" "hub_reviews" \{(.*?)\n\}\n', text, re.S
    )

    assert block is not None
    body = block.group(1)
    assert 'name  = "/shikkhokplus/${var.name_prefix}/hub-reviews"' in body or (
        '"/shikkhokplus/${var.name_prefix}/hub-reviews"' in body
    )
    assert re.search(r'type\s*=\s*"String"', body)
    assert re.search(r'value\s*=\s*"off"', body)
    assert re.search(r"ignore_changes\s*=\s*\[value\]", body)


def test_deploy_role_may_read_the_switch() -> None:
    assert '"hub-reviews"' in DEPLOY_ROLE.read_text()


def test_both_compose_files_forward_switch_defaulting_off() -> None:
    for path in COMPOSES:
        document = yaml.safe_load(path.read_text())
        found = False
        for service in document["services"].values():
            environment = service.get("environment") or {}
            if SWITCH in environment:
                found = True
                assert environment[SWITCH] == "${SHIKKHOKPLUS_HUB_REVIEWS:-off}"
        # staging keeps its environment in an anchor the services merge
        for extension, value in document.items():
            if extension.startswith("x-") and isinstance(value, dict):
                if SWITCH in value:
                    found = True
                    assert value[SWITCH] == "${SHIKKHOKPLUS_HUB_REVIEWS:-off}"
        assert found, f"{path.name} does not forward {SWITCH}"


# ---------------------------------------------------------------------------
# The "Switching reviews on" runbook [H4 Task 13]. Turning reviews on
# publishes what families write about a class, so three human checks come
# before the parameter changes: the D9 demand bar, the D8 legal review and
# the D6 declarations (hub spec, owner decisions). The commands the runbook
# gives must name the parameter Terraform actually creates, or a person
# following it writes a parameter nothing reads.
# ---------------------------------------------------------------------------

README = ROOT / "infra" / "README.md"
MAIN = ROOT / "infra" / "main.tf"
VARIABLES = ROOT / "infra" / "variables.tf"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"


def _runbook() -> str:
    """Return the "Switching reviews on" section of ``infra/README.md``.

    :return: The section, from its heading to the next ``## `` heading
    """
    text = README.read_text()
    match = re.search(r"^## Switching reviews on\n(.*?)(?=^## )", text, re.S | re.M)
    assert match is not None, "infra/README.md has no 'Switching reviews on'"
    return match.group(1)


def _steps(section: str) -> list[str]:
    """Split the section's top-level numbered list into its steps.

    :param section: The runbook section
    :return: Each step's text, continuation lines included, in order
    """
    steps: list[str] = []
    for line in section.splitlines():
        if re.match(r"^\d+\. ", line):
            steps.append(line)
        elif steps and (line.startswith(" ") or not line.strip()):
            steps[-1] += "\n" + line
        elif steps:
            break
    return steps


def _switch_paths() -> dict[str, str]:
    """Compute the switch parameter's name per environment from Terraform.

    :return: ``{environment: parameter name}``
    """
    environments = re.search(
        r'variable "environment" \{.*?contains\(\[(.*?)\]', VARIABLES.read_text(), re.S
    )
    assert environments is not None
    prefix = re.search(r'^\s*name_prefix\s*=\s*"(.*?)"', MAIN.read_text(), re.M)
    assert prefix is not None
    app = re.search(r'module "app" \{(.*?)\n\}\n', MAIN.read_text(), re.S)
    assert app is not None
    assert re.search(r"name_prefix\s*=\s*local\.name_prefix\n", app.group(1))
    resource = re.search(
        r'resource "aws_ssm_parameter" "hub_reviews" \{.*?name\s*=\s*"(.*?)"',
        STATE.read_text(),
        re.S,
    )
    assert resource is not None
    paths = {}
    for environment in re.findall(r'"([a-z]+)"', environments.group(1)):
        name_prefix = prefix.group(1).replace("${var.environment}", environment)
        paths[environment] = resource.group(1).replace(
            "${var.name_prefix}", name_prefix
        )
    return paths


def test_switch_paths_are_the_ones_the_release_reads() -> None:
    paths = _switch_paths()
    read = re.search(r'--name "(/shikkhokplus/.*?)/\$1"', DEPLOY.read_text())
    assert read is not None

    assert paths == {
        "staging": "/shikkhokplus/shikkhokplus-staging/hub-reviews",
        "production": "/shikkhokplus/shikkhokplus-production/hub-reviews",
    }
    for environment, path in paths.items():
        released = read.group(1).replace("${ENVIRONMENT}", environment)
        assert f"{released}/hub-reviews" == path


def test_runbook_lists_d8_d9_d6_before_flip() -> None:
    section = _runbook()
    steps = _steps(section)

    def first(pattern: str) -> int:
        for index, step in enumerate(steps):
            if re.search(pattern, step):
                return index
        raise AssertionError(f"no runbook step matches {pattern!r}")

    d9 = first(r"\bD9\b")
    d8 = first(r"\bD8\b")
    d6 = first(r"\bD6\b")
    flip = first(r"aws ssm put-parameter")
    deploy = first(r"(?i)dispatch")
    check = first(r"(?i)batch page in staging shows the reviews\s+section")
    assert len(steps) == 6
    assert [d9, d8, d6, flip, deploy, check] == [0, 1, 2, 3, 4, 5]
    # The D9 step carries the spec's own bars, not a paraphrase of them.
    assert "20%" in steps[d9] and "15%" in steps[d9]

    commands = re.findall(r"aws ssm put-parameter[^\n`]*", section)
    paths = _switch_paths()
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
