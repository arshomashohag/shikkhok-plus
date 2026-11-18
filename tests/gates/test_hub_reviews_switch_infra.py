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
