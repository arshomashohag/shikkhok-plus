"""The join-requests switch reaches the container, defaulting off.

The switch is read from SSM by the release, written into the runtime
env and forwarded by compose. Terraform creates the parameter ``off``
and never touches its value again, so an apply cannot flip it. The
release's own reading of it lives in ``test_deploy_workflow.py``, beside
the record-step harness it needs.
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
SWITCH = "SHIKKHOKPLUS_HUB_ENQUIRIES"
README = ROOT / "infra" / "README.md"
MAIN = ROOT / "infra" / "main.tf"
VARIABLES = ROOT / "infra" / "variables.tf"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"


def _parameter_block() -> str:
    """Return the body of the ``hub_enquiries`` SSM parameter resource.

    :return: The text between its braces
    """
    block = re.search(
        r'resource "aws_ssm_parameter" "hub_enquiries" \{(.*?)\n\}\n',
        STATE.read_text(),
        re.S,
    )
    assert block is not None, "deployment_state.tf has no hub_enquiries parameter"
    return block.group(1)


def test_ssm_switch_parameter_defaults_off_and_ignores_value() -> None:
    body = _parameter_block()

    assert re.search(
        r'name\s*=\s*"/shikkhokplus/\$\{var\.name_prefix\}/hub-enquiries"', body
    )
    assert re.search(r'type\s*=\s*"String"', body)
    assert re.search(r'value\s*=\s*"off"', body)
    assert re.search(r"ignore_changes\s*=\s*\[value\]", body)


def test_deploy_role_may_read_the_enquiries_switch() -> None:
    granted = re.search(
        r'Sid\s*=\s*"PublicUrl".*?Resource\s*=\s*\[(.*?)\]\s*:',
        DEPLOY_ROLE.read_text(),
        re.S,
    )
    assert granted is not None
    assert '"hub-enquiries"' in granted.group(1)


def test_both_compose_files_forward_switch_defaulting_off() -> None:
    for path in COMPOSES:
        document = yaml.safe_load(path.read_text())
        found = False
        for service in document["services"].values():
            environment = service.get("environment") or {}
            if SWITCH in environment:
                found = True
                assert environment[SWITCH] == "${SHIKKHOKPLUS_HUB_ENQUIRIES:-off}"
        # staging keeps its environment in an anchor the services merge
        for extension, value in document.items():
            if extension.startswith("x-") and isinstance(value, dict):
                if SWITCH in value:
                    found = True
                    assert value[SWITCH] == "${SHIKKHOKPLUS_HUB_ENQUIRIES:-off}"
        assert found, f"{path.name} does not forward {SWITCH}"


# ---------------------------------------------------------------------------
# The "Switching join requests on" runbook. Task 1 writes the parameter
# table and the deploy-role paragraph; Task 10 adds the human checks that
# come before the flip. The table must name the parameter Terraform
# actually creates, or a person following it writes a parameter nothing
# reads.
# ---------------------------------------------------------------------------


def _runbook() -> str:
    """Return the "Switching join requests on" section of ``infra/README.md``.

    :return: The section, from its heading to the next ``## `` heading
    """
    text = README.read_text()
    match = re.search(
        r"^## Switching join requests on\n(.*?)(?=^## )", text, re.S | re.M
    )
    assert match is not None, "infra/README.md has no 'Switching join requests on'"
    return match.group(1)


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
    resource = re.search(r'name\s*=\s*"(.*?)"', _parameter_block())
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
    assert re.search(r"\$\(ses_param hub-enquiries\)", DEPLOY.read_text())

    assert paths == {
        "staging": "/shikkhokplus/shikkhokplus-staging/hub-enquiries",
        "production": "/shikkhokplus/shikkhokplus-production/hub-enquiries",
    }
    for environment, path in paths.items():
        released = read.group(1).replace("${ENVIRONMENT}", environment)
        assert f"{released}/hub-enquiries" == path


def test_runbook_tables_the_parameter_terraform_creates() -> None:
    section = _runbook()

    for environment, path in _switch_paths().items():
        assert f"| {environment} | `{path}` |" in section
    assert "test_hub_enquiries_switch_infra.py" in section


def test_runbook_says_the_deploy_role_must_read_it() -> None:
    section = _runbook()

    assert "**The deploy role must be able to read it.**" in section
    assert "Cannot read the hub join requests switch" in section
    assert "bootstrap/deploy_role.tf" in section


def test_runbook_names_the_message_the_release_stops_with() -> None:
    # The runbook tells a person what to do when the release stops; the
    # sentence it quotes must be the one the release prints.
    quoted = re.search(r'"(Cannot read the hub join requests switch)"', _runbook())
    assert quoted is not None
    assert f"::error::{quoted.group(1)}" in DEPLOY.read_text()
