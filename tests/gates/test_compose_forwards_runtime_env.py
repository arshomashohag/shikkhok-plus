"""Every variable the deploy writes must reach the container.

The deploy writes the runtime env into SSM, the boot script writes it to
the host's ``.env``, and ``docker compose`` then hands the container
**only the variables its ``environment:`` block names**. A variable the
deploy writes and compose does not list is read by nothing, silently.

That is how two-step verification shipped broken: the MFA keyring was
written to ``.env`` on every deploy and never forwarded, so every
enrollment raised ``MfaKeyError: SHIKKHOKPLUS_MFA_ACTIVE_KID=''``, and
the admin phones, edge secret and networks never arrived either.
"""

from __future__ import annotations

import base64
import pathlib
import re

import pytest
import yaml

from app.auth import mfa_crypto
from app.config import LOCAL_DEV_MFA_KEY

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"
STAGING_COMPOSE = ROOT / "deploy" / "docker-compose.staging.yml"
LOCAL_COMPOSE = ROOT / "docker-compose.yml"

#: ``echo "SHIKKHOKPLUS_NAME=...`` -- how the deploy writes runtime.env.
_WRITTEN = re.compile(r'^\s*echo\s+"(SHIKKHOKPLUS_[A-Z0-9_]+)=', re.MULTILINE)


def _written_by_deploy() -> set[str]:
    """Read the variable names the deploy writes into the runtime env.

    :return: The names
    """
    return set(_WRITTEN.findall(DEPLOY.read_text()))


def _compose_environment(path: pathlib.Path, service: str) -> dict[str, str]:
    """Read one service's ``environment:`` block, anchors merged.

    :param path: The compose file
    :param service: The service name
    :return: Variable name to its raw interpolation
    """
    document = yaml.safe_load(path.read_text())
    return {
        key: str(value)
        for key, value in document["services"][service]["environment"].items()
    }


def test_the_deploy_writes_variables_at_all() -> None:
    # Guards the regex: a reformatted deploy step matching nothing would
    # make the forwarding test below pass vacuously.
    written = _written_by_deploy()
    assert "SHIKKHOKPLUS_OTP_HMAC_KEY" in written
    assert "SHIKKHOKPLUS_MFA_KEYS" in written


@pytest.mark.parametrize("service", ["api", "migrate"])
def test_every_variable_the_deploy_writes_reaches_the_container(
    service: str,
) -> None:
    forwarded = _compose_environment(STAGING_COMPOSE, service)
    missing = sorted(_written_by_deploy() - forwarded.keys())
    assert not missing, (
        f"the deploy writes {missing} but {STAGING_COMPOSE.name} does not "
        f"forward them to {service!r}; add them to x-app-environment"
    )


def test_the_local_default_keyring_lets_a_fresh_clone_enroll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _compose_environment(LOCAL_COMPOSE, "api")
    for name in (mfa_crypto.MFA_KEYS_ENV, mfa_crypto.MFA_ACTIVE_KID_ENV):
        default = re.fullmatch(r"\$\{\w+:-(.*)\}", environment[name])
        assert default is not None, f"{name} has no default in docker-compose.yml"
        monkeypatch.setenv(name, default.group(1))
    assert mfa_crypto.keyring_configured()


def test_the_local_default_key_is_the_one_production_refuses() -> None:
    # The refusal in app/config.py matches this exact string; a key
    # changed in one place and not the other would slip through.
    environment = _compose_environment(LOCAL_COMPOSE, "api")
    assert LOCAL_DEV_MFA_KEY in environment[mfa_crypto.MFA_KEYS_ENV]
    assert len(base64.b64decode(LOCAL_DEV_MFA_KEY)) == 32
