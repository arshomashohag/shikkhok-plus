"""Shared readers for the hub feature switches' infrastructure gates.

Each hub switch (reviews in H4, join requests in H5) is one SSM parameter
Terraform creates ``off``, the release reads and validates, and compose
forwards to the container, with an ``infra/README.md`` runbook naming the
parameter per environment. The gates for each switch ask the same
questions of the same files, so the parsing lives here once:
``test_hub_reviews_switch_infra.py`` and
``test_hub_enquiries_switch_infra.py`` both call it.
"""

from __future__ import annotations

import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "infra" / "modules" / "app" / "deployment_state.tf"
README = ROOT / "infra" / "README.md"
MAIN = ROOT / "infra" / "main.tf"
VARIABLES = ROOT / "infra" / "variables.tf"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"
COMPOSES = (
    ROOT / "docker-compose.yml",
    ROOT / "deploy" / "docker-compose.staging.yml",
)


def parameter_block(resource: str) -> str:
    """Return the body of one ``aws_ssm_parameter`` in the app module's state.

    :param resource: The Terraform resource name, e.g. ``hub_reviews``
    :return: The text between its braces
    """
    block = re.search(
        rf'resource "aws_ssm_parameter" "{resource}" \{{(.*?)\n\}}\n',
        STATE.read_text(),
        re.S,
    )
    assert block is not None, f"deployment_state.tf has no {resource} parameter"
    return block.group(1)


def switch_paths(resource: str) -> dict[str, str]:
    """Compute a switch parameter's name per environment from Terraform.

    Reads the environments ``variables.tf`` admits, the ``name_prefix``
    ``main.tf`` builds from each and passes to the app module, and the
    parameter's own ``name``.

    :param resource: The Terraform resource name, e.g. ``hub_reviews``
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
    name = re.search(r'name\s*=\s*"(.*?)"', parameter_block(resource))
    assert name is not None
    paths = {}
    for environment in re.findall(r'"([a-z]+)"', environments.group(1)):
        name_prefix = prefix.group(1).replace("${var.environment}", environment)
        paths[environment] = name.group(1).replace("${var.name_prefix}", name_prefix)
    return paths


def released_path(parameter: str, environment: str) -> str:
    """Return the SSM name the release reads a parameter from.

    :param parameter: The short name ``ses_param`` is given, e.g.
        ``hub-reviews``
    :param environment: ``staging`` or ``production``
    :return: The full parameter name, as the release builds it
    """
    read = re.search(r'--name "(/shikkhokplus/.*?)/\$1"', DEPLOY.read_text())
    assert read is not None, "deploy.yml has no ses_param reader"
    return f"{read.group(1).replace('${ENVIRONMENT}', environment)}/{parameter}"


def compose_forwards(variable: str) -> dict[str, list[str]]:
    """Read how each compose file forwards one variable to the container.

    Looks in every service's ``environment`` and in every ``x-`` extension,
    because staging keeps its environment in an anchor the services merge.

    :param variable: The environment variable, e.g.
        ``SHIKKHOKPLUS_HUB_REVIEWS``
    :return: ``{compose file name: [each raw value it is given]}``; an
        empty list means the file does not forward it
    """
    found: dict[str, list[str]] = {}
    for path in COMPOSES:
        document = yaml.safe_load(path.read_text())
        values = found.setdefault(path.name, [])
        for service in document["services"].values():
            environment = service.get("environment") or {}
            if variable in environment:
                values.append(environment[variable])
        for extension, value in document.items():
            if extension.startswith("x-") and isinstance(value, dict):
                if variable in value:
                    values.append(value[variable])
    return found


def runbook(heading: str) -> str:
    """Return one ``## `` section of ``infra/README.md``.

    :param heading: The heading's text, without the ``## ``
    :return: The section, from below its heading to the next ``## `` heading
    """
    match = re.search(
        rf"^## {re.escape(heading)}\n(.*?)(?=^## )", README.read_text(), re.S | re.M
    )
    assert match is not None, f"infra/README.md has no {heading!r}"
    return match.group(1)


def steps(section: str) -> list[str]:
    """Split a runbook section's top-level numbered list into its steps.

    :param section: The runbook section
    :return: Each step's text, continuation lines included, in order
    """
    found: list[str] = []
    for line in section.splitlines():
        if re.match(r"^\d+\. ", line):
            found.append(line)
        elif found and (line.startswith(" ") or not line.strip()):
            found[-1] += "\n" + line
        elif found:
            break
    return found
