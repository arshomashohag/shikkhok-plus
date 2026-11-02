"""The app host's boot script, checked as rendered text.

**Why a Python test reads a shell template.** The scheduled jobs on the
app host -- daily fee-cycle generation, daily session generation and the
hourly freshness check -- ran ``cd /home/ubuntu && docker compose ...``
while the boot script wrote the compose file and its ``.env`` to
``/srv/shikkhokplus`` [OPS-1]. ``docker compose`` with no compose file in
its working directory exits non-zero, so no fee cycle and no class
session was generated in any deployed environment, and the check meant
to notice a stalled generator failed the same way and noticed nothing.

Nothing caught it because nothing ran the template: it is executed only
by cloud-init on a fresh instance, and its output goes to a log file
nobody reads unless something is already visibly wrong. A job that
self-heals looks healthy right up to the day somebody asks why nobody
has been billed.

So the property is asserted here, on every pull request, without Docker,
AWS or PostgreSQL: **every ``docker compose`` invocation in every shell
the template creates runs in the directory the compose file is written
to.** The directory is DERIVED from the template -- the working directory
at the step that fetches ``docker-compose.yml`` -- rather than restated,
so moving the application's home cannot leave this test asserting the
old one.

The same rendering also feeds the two properties a boot script can
break silently: ``bash -n`` on every shell body, and EC2's hard 16 KB
user-data limit, which an earlier apply already hit.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
from dataclasses import dataclass

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "infra" / "modules" / "app" / "user_data.sh.tftpl"
COMPOSE = ROOT / "deploy" / "docker-compose.staging.yml"

#: EC2 rejects user data larger than this, measured before base64
#: encoding. The launch template strips whole-line comments first, and
#: so does :func:`_strip_comments` below, so the figure compared is the
#: figure EC2 sees.
USER_DATA_LIMIT_BYTES = 16 * 1024

#: Values of a realistic LENGTH for every template variable. Lengths
#: matter for the size check; the values themselves never reach a host.
#: A variable the template uses and this map lacks fails the render
#: rather than rendering as an empty string.
TEMPLATE_VALUES: dict[str, str] = {
    "ecr_repository_url": (
        "123456789012.dkr.ecr.us-east-1.amazonaws.com/shikkhokplus-production-backend"
    ),
    "ecr_registry": "123456789012.dkr.ecr.us-east-1.amazonaws.com",
    "name_prefix": "shikkhokplus-production",
    "aws_region": "ap-southeast-1",
    "dns_zone_id": "Z0123456789ABCDEFGHIJ",
    "origin_fqdn": "origin.shikkhokplus-production.example-apex-domain.com",
    "config_bucket": "shikkhokplus-production-config-123456789012",
    "lifecycle_hook_name": "shikkhokplus-production-ready",
    "log_group": "/shikkhokplus/shikkhokplus-production/app",
}


@dataclass(frozen=True)
class ShellBody:
    """One shell program the template creates.

    :ivar name: Where it came from, for failure messages
    :ivar runs_as_ubuntu: Whether it runs as the ``ubuntu`` user, whose
        writes to ``/var/log`` need a file created for it in advance
    :ivar lines: Its lines, in order
    """

    name: str
    runs_as_ubuntu: bool
    lines: tuple[str, ...]


def _render(text: str, values: dict[str, str]) -> str:
    """Render a Terraform template the way ``templatefile`` would.

    Only the subset the boot script uses: ``${name}`` interpolation and
    the ``$${`` / ``%%{`` escapes. A directive (``%{ if ... }``) is
    refused rather than ignored, so a template that starts using one
    fails here instead of being checked as if it were plain text.

    :param text: The template source
    :param values: The variables to substitute
    :return: The rendered script
    """
    if re.search(r"(?<!%)%\{", text):
        raise AssertionError("template directives are not rendered by this test")

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise AssertionError(f"template variable {name!r} has no test value")
        return values[name]

    rendered = re.sub(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)\}", substitute, text)
    return rendered.replace("$${", "${").replace("%%{", "%{")


def _strip_comments(script: str) -> str:
    """Strip whole-line comments, exactly as the launch template does.

    Mirrors the ``for line in split(...) : line if ...`` expression in
    ``infra/modules/app/main.tf``: a line whose first non-blank
    character is ``#`` is dropped unless it is a shebang.

    :param script: The rendered script
    :return: What EC2 receives
    """
    kept = [
        line
        for line in script.split("\n")
        if not line.strip().startswith("#") or line.strip().startswith("#!")
    ]
    return "\n".join(kept)


def _shell_bodies(script: str) -> list[ShellBody]:
    """Split the script into the shells it runs or installs.

    The boot script itself is one body. Every heredoc whose content is
    a shell program -- a cron file, a helper script -- is another, with
    its own working directory: a ``cd`` in the boot script does not
    carry into a cron job.

    :param script: The rendered script
    :return: The bodies, the boot script first
    """
    lines = script.split("\n")
    main: list[str] = []
    bodies: list[ShellBody] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        main.append(line)
        heredoc = re.search(r"<<-?\s*'?([A-Z_]+)'?", line)
        index += 1
        if heredoc is None:
            continue
        terminator = heredoc.group(1)
        content: list[str] = []
        while index < len(lines) and lines[index].strip() != terminator:
            content.append(lines[index])
            index += 1
        index += 1  # the terminator itself
        target = line
        if terminator == "CRON":
            # A cron line is `<schedule> <user> <command>`; the command
            # is a shell of its own, run as that user.
            for entry in content:
                fields = entry.split(None, 6)
                if len(fields) == 7 and not entry.lstrip().startswith("#"):
                    bodies.append(
                        ShellBody(
                            name=f"cron entry in {target.strip()}",
                            runs_as_ubuntu=fields[5] == "ubuntu",
                            lines=(fields[6],),
                        )
                    )
        elif content and content[0].startswith("#!/bin/bash"):
            bodies.append(
                ShellBody(
                    name=f"script written by {target.strip()}",
                    runs_as_ubuntu=True,
                    lines=tuple(content),
                )
            )
    return [ShellBody("the boot script", False, tuple(main)), *bodies]


_CD = re.compile(r"(?:^|&&|;|\|\|)\s*cd\s+(\S+)")


def _compose_violations(body: ShellBody, app_dir: str) -> list[str]:
    """Find ``docker compose`` calls not running in ``app_dir``.

    :param body: The shell to read
    :param app_dir: Where the compose file and ``.env`` live
    :return: One message per offending line
    """
    cwd: str | None = None
    found: list[str] = []
    for raw in body.lines:
        line = re.sub(r"(^|\s)#.*$", "", raw).strip()
        if not line:
            continue
        compose_at = line.find("docker compose")
        for cd in _CD.finditer(line):
            if compose_at == -1 or cd.start() < compose_at:
                cwd = cd.group(1).rstrip(";")
        if compose_at == -1:
            continue
        pinned = f"--project-directory {app_dir}" in line
        if not pinned and cwd != app_dir:
            found.append(f"{body.name}: runs in {cwd!r}, not {app_dir!r}: {line}")
    return found


def _app_dir(bodies: list[ShellBody]) -> str:
    """Return the directory the boot script writes the compose file to.

    :param bodies: The parsed shells
    :return: The working directory at the step that fetches it
    """
    cwd: str | None = None
    for raw in bodies[0].lines:
        line = raw.strip()
        for cd in _CD.finditer(line):
            cwd = cd.group(1)
        if "docker-compose.yml" in line and "s3 cp" in line:
            assert cwd is not None, "the compose file is fetched with no cd before it"
            return cwd
    raise AssertionError("the template no longer fetches docker-compose.yml")


@pytest.fixture(scope="module")
def rendered() -> str:
    return _render(TEMPLATE.read_text(), TEMPLATE_VALUES)


def test_every_compose_invocation_runs_where_the_compose_file_is(
    rendered: str,
) -> None:
    bodies = _shell_bodies(rendered)
    app_dir = _app_dir(bodies)

    violations = [v for body in bodies for v in _compose_violations(body, app_dir)]

    assert violations == []
    # Not vacuous: the cron entries and the freshness script must have
    # been found and must each contain an invocation. A parser that
    # stopped seeing them would pass the assertion above on nothing.
    with_compose = [
        b.name for b in bodies if any("docker compose" in x for x in b.lines)
    ]
    assert len(with_compose) >= 4, with_compose


def test_the_guard_fires_on_the_shape_that_shipped() -> None:
    # The exact line that ran in every environment until this fix.
    shipped = ShellBody(
        name="cron",
        runs_as_ubuntu=True,
        lines=(
            "cd /home/ubuntu && docker compose run --rm api "
            "python -m app.fees.commands generate",
        ),
    )
    pinned = ShellBody(
        name="cron",
        runs_as_ubuntu=True,
        lines=("docker compose --project-directory /srv/x run --rm api true",),
    )

    assert _compose_violations(shipped, "/srv/shikkhokplus") != []
    assert _compose_violations(pinned, "/srv/x") == []


def test_logs_written_as_ubuntu_exist_before_the_job_runs(rendered: str) -> None:
    # A cron job running as `ubuntu` cannot create a file in /var/log,
    # which is root-owned. The `>>` redirection then fails, and bash
    # does not run the command at all -- the job never starts, and the
    # error goes to cron's mail, which nobody reads.
    bodies = _shell_bodies(rendered)
    boot = "\n".join(bodies[0].lines)

    appended = {
        path
        for body in bodies[1:]
        if body.runs_as_ubuntu
        for line in body.lines
        for path in re.findall(r">>\s*(/var/log/\S+)", line)
    }

    assert appended, "no ubuntu-run job appends to a log; the parser found nothing"
    missing = [
        path
        for path in sorted(appended)
        if not re.search(rf"install\b[^\n]*-o ubuntu[^\n]*{re.escape(path)}", boot)
    ]
    assert missing == []


def test_every_shell_body_parses(rendered: str, tmp_path: pathlib.Path) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    # The whole script as cloud-init runs it, heredocs included, then
    # every program it installs on its own.
    programs = [("the boot script", rendered)] + [
        (body.name, "\n".join(body.lines)) for body in _shell_bodies(rendered)[1:]
    ]
    for number, (name, text) in enumerate(programs):
        script = tmp_path / f"body{number}.sh"
        script.write_text(text + "\n")
        result = subprocess.run(  # noqa: S603 -- a fixed binary on a file we wrote
            [bash, "-n", str(script)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"


def test_rendered_user_data_fits_the_ec2_limit(rendered: str) -> None:
    size = len(_strip_comments(rendered).encode())

    assert size < USER_DATA_LIMIT_BYTES, (
        f"user data is {size} bytes after comment stripping; EC2 refuses "
        f"more than {USER_DATA_LIMIT_BYTES}. Move a static file to the "
        "config bucket, as docker-compose.yml already is."
    )


def test_no_secret_reaches_the_template() -> None:
    # user_data is readable by anyone with
    # ec2:DescribeLaunchTemplateVersions and by any process that can
    # reach IMDS, and every launch-template version keeps it [OPS-4].
    # The host reads its secrets from SSM; the template may only carry
    # names, paths and identifiers.
    used = set(
        re.findall(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)\}", TEMPLATE.read_text())
    )
    secret_shaped = {
        name for name in used if re.search(r"secret|password|token|database_url", name)
    }

    assert used, "the template interpolates nothing; the parser found nothing"
    assert secret_shaped == set()
    # And the main.tf call site passes no such key either.
    call_site = (TEMPLATE.parent / "main.tf").read_text()
    templatefile_args = call_site[call_site.index("templatefile(") :]
    templatefile_args = templatefile_args[: templatefile_args.index("}))")]
    assert not re.search(
        r"^\s*\w*(secret|password|database_url)\w*\s*=", templatefile_args, re.M
    )


def test_the_owner_url_reaches_only_the_migrate_service() -> None:
    # The API and every scheduled job run as shikkhok_app [OPS-5]. The
    # owner's URL may appear only in the `migrate` service, which the
    # boot script runs for `alembic upgrade head` and to set the
    # restricted role's password -- never in `api`.
    compose = yaml.safe_load(COMPOSE.read_text())
    services = compose["services"]

    api_env = services["api"]["environment"]
    assert "SHIKKHOKPLUS_MIGRATION_DATABASE_URL" not in api_env
    assert "MIGRATION" not in str(api_env.get("SHIKKHOKPLUS_DATABASE_URL"))
    assert "migrate" in services
    assert "SHIKKHOKPLUS_MIGRATION_DATABASE_URL" in services["migrate"]["environment"]
    # The migrate service never starts with `up`: it has a profile.
    assert services["migrate"].get("profiles")
