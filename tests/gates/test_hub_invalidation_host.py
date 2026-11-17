"""The hub's CDN invalidations are sent by the HOST, never the container [R8].

The container cannot reach the instance's credentials (IMDS hop limit 1,
OPS-4) and the image carries no AWS SDK. So a host script,
``/usr/local/bin/shikkhokplus-hub-invalidate``, asks the running container
which rows to send (``claim``), calls CloudFront with the host's AWS CLI,
and reports back (``ack`` or ``fail``). This file checks the boot template
that installs it, as rendered text, and then runs the rendered script
against stand-ins for ``docker`` and ``aws``.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import stat
import subprocess

import pytest

from tests.gates.test_user_data_template import (
    TEMPLATE,
    TEMPLATE_VALUES,
    _render,
    _shell_bodies,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = "/usr/local/bin/shikkhokplus-hub-invalidate"
APP_DIR = "/srv/shikkhokplus"
COMMANDS = "python -m app.hub.public.commands"

#: What the stand-in container prints for a claim with rows to send.
CLAIM = {
    "caller_reference": "4f1c0d5e-2b8e-4f43-9d55-6a1f2b0c9e11",
    "ids": [1, 2, 3],
    "paths": ["/hub/en/t/rahim-sir*", "/hub/bn/t/rahim-sir*", "/hub/sitemap.xml"],
}


def _script(values: dict[str, str] = TEMPLATE_VALUES) -> list[str]:
    """Return the sender script's lines as the boot script installs it.

    :param values: The template variables
    :return: The lines, shebang first
    """
    for body in _shell_bodies(_render(TEMPLATE.read_text(), values)):
        if f"cat > {SCRIPT}" in body.name:
            return list(body.lines)
    raise AssertionError(f"the template no longer installs {SCRIPT}")


def _cron_lines() -> list[str]:
    """Return every cron entry's command.

    :return: The commands
    """
    bodies = _shell_bodies(_render(TEMPLATE.read_text(), TEMPLATE_VALUES))
    return [b.lines[0] for b in bodies if b.name.startswith("cron entry in")]


def test_cron_runs_the_sender_every_two_minutes_as_ubuntu() -> None:
    rendered = _render(TEMPLATE.read_text(), TEMPLATE_VALUES)
    entry = (
        f"*/2 * * * * ubuntu {SCRIPT} "
        ">> /var/log/shikkhokplus-hub-invalidation.log 2>&1"
    )

    assert entry in rendered
    assert any(SCRIPT in line for line in _cron_lines())
    assert re.search(
        r"install\b[^\n]*-o ubuntu[^\n]*/var/log/shikkhokplus-hub-invalidation\.log",
        rendered,
    )


def test_sender_execs_into_the_running_container_and_never_starts_one() -> None:
    script = "\n".join(_script())

    for verb in ("claim", "ack", "fail"):
        assert f"docker compose exec -T api {COMMANDS} {verb}" in script, verb
    assert "run --rm" not in script
    assert f"cd {APP_DIR}" in script
    assert "aws cloudfront create-invalidation" in script
    assert "flock -n" in script


def test_the_template_receives_the_distribution_id() -> None:
    source = TEMPLATE.read_text()
    main_tf = (TEMPLATE.parent / "main.tf").read_text()

    assert 'distribution="${site_distribution_id}"' in source
    assert re.search(r"site_distribution_id\s*=\s*local\.site_distribution_id", main_tf)
    assert TEMPLATE_VALUES["site_distribution_id"] in "\n".join(_script())


def test_no_aws_sdk_reaches_the_container() -> None:
    # The whole point of R8: nothing the image installs or imports can call
    # AWS, so the hop-limit decision [OPS-4] keeps holding.
    for manifest in ("pyproject.toml", "requirements.txt"):
        text = (ROOT / manifest).read_text().lower()
        assert "boto3" not in text, manifest
        assert "botocore" not in text, manifest
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "app").rglob("*.py")
        if re.search(r"^\s*(import|from)\s+(boto3|botocore)\b", path.read_text(), re.M)
    ]
    assert offenders == []


@pytest.fixture
def host(tmp_path: pathlib.Path) -> pathlib.Path:
    """Build stand-ins for ``docker`` and ``aws`` that record their calls.

    :param tmp_path: A scratch directory
    :return: The directory holding ``bin/``, the logs and the app dir
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "app").mkdir()
    (tmp_path / "lock").mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/bash\n"
        'echo "$*" >> "$STUB_DIR/docker.log"\n'
        'case "$*" in\n'
        '  "compose ps --status running --services")\n'
        '    [ "$STUB_API_UP" = 1 ] && echo api; exit 0 ;;\n'
        '  *"commands claim"*) cat "$STUB_DIR/claim.json"; exit 0 ;;\n'
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    aws = bin_dir / "aws"
    aws.write_text(
        "#!/bin/bash\n"
        'printf "%s\\n" "$@" > "$STUB_DIR/aws.args"\n'
        'if [ "$STUB_AWS_FAIL" = 1 ]; then echo "AccessDenied" >&2; exit 254; fi\n'
        "echo I2J0EXAMPLE\n"
    )
    for stub in (docker, aws):
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return tmp_path


def _run(
    host: pathlib.Path,
    claim: dict[str, object],
    *,
    api_up: bool = True,
    aws_fails: bool = False,
    distribution: str = TEMPLATE_VALUES["site_distribution_id"],
) -> subprocess.CompletedProcess[str]:
    """Run the rendered sender against the stand-ins.

    The application directory and the lock file are moved into the scratch
    directory; nothing else in the script is changed.

    :param host: The stand-ins' directory
    :param claim: What the stand-in container's ``claim`` prints
    :param api_up: Whether the stand-in reports the api container running
    :param aws_fails: Whether the stand-in CloudFront call fails
    :param distribution: The distribution id the template receives
    :return: The finished process
    """
    values = {**TEMPLATE_VALUES, "site_distribution_id": distribution}
    text = "\n".join(_script(values))
    text = text.replace(APP_DIR, str(host / "app")).replace(
        "/run/lock/", f"{host / 'lock'}/"
    )
    script = host / "sender.sh"
    script.write_text(text + "\n")
    (host / "claim.json").write_text(json.dumps(claim) + "\n")
    env = {
        **os.environ,
        "PATH": f"{host / 'bin'}:{os.environ['PATH']}",
        "STUB_DIR": str(host),
        "STUB_API_UP": "1" if api_up else "0",
        "STUB_AWS_FAIL": "1" if aws_fails else "0",
    }
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    return subprocess.run(  # noqa: S603 - a script this test rendered
        [bash, str(script)], env=env, capture_output=True, text=True, check=False
    )


def _docker_calls(host: pathlib.Path) -> list[str]:
    """Read the stand-in docker's calls.

    :param host: The stand-ins' directory
    :return: One line per call
    """
    log = host / "docker.log"
    return log.read_text().splitlines() if log.exists() else []


def test_sender_sends_the_claim_and_acks_with_the_returned_id(
    host: pathlib.Path,
) -> None:
    result = _run(host, CLAIM)

    assert result.returncode == 0, result.stdout + result.stderr
    args = (host / "aws.args").read_text().splitlines()
    assert args[:2] == ["cloudfront", "create-invalidation"]
    assert args[args.index("--distribution-id") + 1] == "E2QWRUHAPOMQZL"
    batch = json.loads(args[args.index("--invalidation-batch") + 1])
    assert batch == {
        "Paths": {"Quantity": 3, "Items": CLAIM["paths"]},
        "CallerReference": CLAIM["caller_reference"],
    }
    assert (
        f"compose exec -T api {COMMANDS} ack --ids 1,2,3 --aws-id I2J0EXAMPLE"
        in _docker_calls(host)
    )
    assert "sent rows 1,2,3 as I2J0EXAMPLE" in result.stdout


def test_a_failed_send_reports_fail_and_never_acks(host: pathlib.Path) -> None:
    result = _run(host, CLAIM, aws_fails=True)

    assert result.returncode == 1
    calls = _docker_calls(host)
    assert f"compose exec -T api {COMMANDS} fail --ids 1,2,3" in calls
    assert not any(" ack " in call for call in calls)
    assert "AccessDenied" in result.stdout


def test_an_empty_claim_sends_nothing(host: pathlib.Path) -> None:
    result = _run(host, {**CLAIM, "ids": [], "paths": []})

    assert result.returncode == 0
    assert not (host / "aws.args").exists()
    assert [c for c in _docker_calls(host) if "commands" in c] == [
        f"compose exec -T api {COMMANDS} claim"
    ]
    assert result.stdout == ""


def test_a_stopped_container_skips_the_run(host: pathlib.Path) -> None:
    result = _run(host, CLAIM, api_up=False)

    assert result.returncode == 0
    assert not any("commands" in c for c in _docker_calls(host))
    assert "api container not running" in result.stdout


def test_a_host_with_no_distribution_claims_but_sends_nothing(
    host: pathlib.Path,
) -> None:
    # The rehearsal host: the claim still stamps the heartbeat, and changes
    # no row, so the primary host sends what is waiting.
    result = _run(host, CLAIM, distribution="")

    assert result.returncode == 0
    assert not (host / "aws.args").exists()
    assert not any(" ack " in c or " fail " in c for c in _docker_calls(host))
    assert "no site distribution" in result.stdout
