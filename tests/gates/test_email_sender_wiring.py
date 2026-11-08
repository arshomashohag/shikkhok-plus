"""The SES sender is reachable end to end, without AWS.

``infra/modules/email`` publishes the SMTP credentials and the sender's
settings as SSM parameters; ``deploy.yml`` copies them into the runtime
env; the deploy role must be allowed to read each one; and the IAM user
behind the credentials must be one the plan role can read back and the
infrastructure role can only create under the sender boundary. Each link
is exercised for real only by a deploy against AWS, and a missing one
fails there -- as the plan role's missing buckets did
(test_plan_role_reads_every_bucket.py). So each is asserted here, with the
names DERIVED from the module rather than restated.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
EMAIL_MODULE = ROOT / "infra" / "modules" / "email" / "main.tf"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"
DEPLOY_ROLE = ROOT / "infra" / "bootstrap" / "deploy_role.tf"
BOOTSTRAP = ROOT / "infra" / "bootstrap" / "main.tf"


def _published_parameters() -> list[str]:
    """Read the SSM parameter names the email module publishes.

    :return: The last path segment of each, e.g. ``ses-smtp-password``
    """
    return re.findall(
        r'name\s*=\s*"/shikkhokplus/\$\{var\.name_prefix\}/([a-z0-9-]+)"',
        EMAIL_MODULE.read_text(),
    )


def _statement(text: str, sid: str) -> str:
    """Return the text of one policy statement, from its Sid to the next.

    :param text: The policy file
    :param sid: The statement's Sid
    :return: The statement's text
    """
    start = re.search(rf'[Ss]id\s*=\s*"{sid}"', text)
    assert start is not None, f"no statement {sid}"
    rest = text[start.end() :]
    following = re.search(r'[Ss]id\s*=\s*"', rest)
    return rest[: following.start()] if following else rest


def test_the_module_publishes_the_credentials() -> None:
    # Guards the regex: a walk matching nothing would pass vacuously.
    names = _published_parameters()
    assert {"ses-smtp-username", "ses-smtp-password"} <= set(names), names


def test_the_release_reads_every_published_parameter() -> None:
    read = set(re.findall(r"ses_param\s+([a-z0-9-]+)", DEPLOY.read_text()))
    unread = sorted(set(_published_parameters()) - read)
    assert not unread, f"deploy.yml never reads {unread} into the runtime env"


def test_the_deploy_role_may_read_every_published_parameter() -> None:
    granted = _statement(DEPLOY_ROLE.read_text(), "PublicUrl")
    ungranted = [name for name in _published_parameters() if f'"{name}"' not in granted]
    assert not ungranted, (
        f"the deploy role cannot read {ungranted}, so the release stops at "
        "'Cannot read the SES sender'; add them to its PublicUrl statement"
    )


def test_the_credentials_are_read_before_anything_is_written() -> None:
    text = DEPLOY.read_text()
    read = text.index("ses_param ses-smtp-password")
    written = text.index(
        '--name "/shikkhokplus/shikkhokplus-${ENVIRONMENT}/runtime-env"'
    )
    assert read < written


def test_the_runtime_env_selects_ses() -> None:
    assert 'echo "SHIKKHOKPLUS_EMAIL_ADAPTER=ses"' in DEPLOY.read_text()


def test_the_sender_user_is_bounded_and_named_for_its_environment() -> None:
    text = EMAIL_MODULE.read_text()
    users = re.findall(r'resource\s+"aws_iam_user"\s+"\w+"\s*\{(.*?)\n\}', text, re.S)
    assert users, "no aws_iam_user in the email module"
    for body in users:
        assert re.search(r'name\s*=\s*"\$\{var\.name_prefix\}-', body), body
        assert re.search(r'path\s*=\s*"/shikkhokplus/"', body), body
        assert "permissions_boundary" in body, body


def test_the_infrastructure_role_creates_users_only_under_the_boundary() -> None:
    text = BOOTSTRAP.read_text()
    grant = _statement(text, "GrantUserOnlyWithinTheSenderBoundary")
    assert "iam:CreateUser" in grant and "iam:PermissionsBoundary" in grant
    # And no other statement allows creating a user or giving one a policy.
    for action in ("iam:CreateUser", "iam:PutUserPolicy", "iam:AttachUserPolicy"):
        allows = [
            sid
            for sid in re.findall(r'Sid\s*=\s*"(\w+)"', text)
            if f'"{action}"' in _statement(text, sid)
            and 'Effect   = "Deny"' not in _statement(text, sid)
            and 'Effect = "Deny"' not in _statement(text, sid)
        ]
        expected = (
            []
            if action == "iam:AttachUserPolicy"
            else ["GrantUserOnlyWithinTheSenderBoundary"]
        )
        assert allows == expected, (action, allows)


def test_the_plan_role_reads_back_the_sender() -> None:
    text = BOOTSTRAP.read_text()
    email = _statement(text, "ReadOurEmail")
    assert "ses:GetEmailIdentity" in email
    assert "ses:GetConfigurationSet" in email
    sender = _statement(text, "ReadOurSender")
    for action in ("iam:GetUser", "iam:GetUserPolicy", "iam:ListAccessKeys"):
        assert action in sender, action
    assert "user/shikkhokplus/shikkhokplus-${each.key}-*" in sender
