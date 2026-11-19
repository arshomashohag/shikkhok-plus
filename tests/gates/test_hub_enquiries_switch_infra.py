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

from tests.gates._hub_switches import (
    DEPLOY,
    compose_forwards,
    parameter_block,
    released_path,
    runbook,
    switch_paths,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY_ROLE = ROOT / "infra" / "bootstrap" / "deploy_role.tf"
SWITCH = "SHIKKHOKPLUS_HUB_ENQUIRIES"
RESOURCE = "hub_enquiries"
RUNBOOK = "Switching join requests on"


def test_ssm_switch_parameter_defaults_off_and_ignores_value() -> None:
    body = parameter_block(RESOURCE)

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
    for name, values in compose_forwards(SWITCH).items():
        assert values, f"{name} does not forward {SWITCH}"
        assert set(values) == {"${SHIKKHOKPLUS_HUB_ENQUIRIES:-off}"}


# ---------------------------------------------------------------------------
# The "Switching join requests on" runbook. Task 1 writes the parameter
# table and the deploy-role paragraph; Task 10 adds the human checks that
# come before the flip. The table must name the parameter Terraform
# actually creates, or a person following it writes a parameter nothing
# reads.
# ---------------------------------------------------------------------------


def test_switch_paths_are_the_ones_the_release_reads() -> None:
    paths = switch_paths(RESOURCE)
    assert re.search(r"\$\(ses_param hub-enquiries\)", DEPLOY.read_text())

    assert paths == {
        "staging": "/shikkhokplus/shikkhokplus-staging/hub-enquiries",
        "production": "/shikkhokplus/shikkhokplus-production/hub-enquiries",
    }
    for environment, path in paths.items():
        assert released_path("hub-enquiries", environment) == path


def test_runbook_tables_the_parameter_terraform_creates() -> None:
    section = runbook(RUNBOOK)

    for environment, path in switch_paths(RESOURCE).items():
        assert f"| {environment} | `{path}` |" in section
    assert "test_hub_enquiries_switch_infra.py" in section


def test_runbook_says_the_deploy_role_must_read_it() -> None:
    section = runbook(RUNBOOK)

    assert "**The deploy role must be able to read it.**" in section
    assert "Cannot read the hub join requests switch" in section
    assert "bootstrap/deploy_role.tf" in section


def test_runbook_names_the_message_the_release_stops_with() -> None:
    # The runbook tells a person what to do when the release stops; the
    # sentence it quotes must be the one the release prints.
    quoted = re.search(
        r'"(Cannot read the hub join requests switch)"', runbook(RUNBOOK)
    )
    assert quoted is not None
    assert f"::error::{quoted.group(1)}" in DEPLOY.read_text()
