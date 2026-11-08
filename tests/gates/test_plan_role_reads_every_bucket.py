"""Every bucket the stack manages is reachable by the roles that plan it.

**The plan role could not read two of the four buckets.** The read-only
plan role [C-11] was written when the stack had a config and a web
bucket. The public site (``modules/site``) and the admin UI
(``modules/admin``) each added a bucket, and the infrastructure role's
grant was widened for them while the plan role's was not -- so the
first staging plan after the merge failed on
``s3:GetEncryptionConfiguration`` against the admin bucket, before
anything was deployed. Nothing caught it because the policy is only
exercised by a real ``terraform plan`` against AWS.

So the property is asserted here, on every pull request, without AWS:
**every ``aws_s3_bucket`` name a module declares matches one of the
bucket patterns in the infrastructure role's bucket statement AND in
the plan role's bucket statement.** The names are DERIVED from the
modules rather than restated, so a fifth bucket fails this test instead
of the next deploy.
"""

from __future__ import annotations

import fnmatch
import pathlib
import re

import pytest

INFRA = pathlib.Path(__file__).resolve().parents[2] / "infra"
BOOTSTRAP = INFRA / "bootstrap" / "main.tf"

#: The environment substituted for ``${each.key}`` and ``var.name_prefix``.
ENVIRONMENT = "staging"

#: A stand-in account id, for the suffix every bucket name carries.
ACCOUNT = "123456789012"

#: The bucket statement of each role, by the Sid that names it.
BUCKET_STATEMENTS: dict[str, str] = {
    "infrastructure role": r'sid\s*=\s*"ConfigBucket"',
    "plan role": r'Sid\s*=\s*"ReadOurBuckets"',
}


def _bucket_names() -> list[str]:
    """Render every bucket name the modules declare, for one environment.

    :return: The concrete bucket names
    """
    names: list[str] = []
    pattern = re.compile(
        r'resource\s+"aws_s3_bucket"\s+"\w+"\s*\{[^}]*?\bbucket\s*=\s*"([^"]+)"',
        re.DOTALL,
    )
    for path in sorted((INFRA / "modules").glob("*/*.tf")):
        for template in pattern.findall(path.read_text()):
            rendered = template.replace(
                "${var.name_prefix}", f"shikkhokplus-{ENVIRONMENT}"
            )
            names.append(re.sub(r"\$\{[^}]+\}", ACCOUNT, rendered))
    return names


def _granted_patterns(sid: str) -> list[str]:
    """Read the bucket ARN patterns of one statement, as bucket globs.

    :param sid: A regex matching the statement's Sid line
    :return: The bucket-name globs that statement grants
    """
    text = BOOTSTRAP.read_text()
    start = re.search(sid, text)
    assert start is not None, f"no statement matching {sid}"
    # From the Sid to the end of its resource list: the first "]" after
    # the word "resources"/"Resource", which follows the action list.
    rest = text[start.end() :]
    resources = rest[: rest.index("]", rest.index("esource"))]
    return [
        arn.removeprefix("arn:aws:s3:::").replace("${each.key}", ENVIRONMENT)
        for arn in re.findall(r'"(arn:aws:s3:::[^"/]+)"', resources)
    ]


def test_the_sweep_sees_every_bucket() -> None:
    """Guard against a walk that matches nothing and passes vacuously.

    :return: None
    """
    names = _bucket_names()
    for kind in ("config", "web", "site", "admin"):
        assert any(f"-{kind}-" in name for name in names), (kind, names)


@pytest.mark.parametrize("role", sorted(BUCKET_STATEMENTS))
def test_every_bucket_is_granted(role: str) -> None:
    """Each module's bucket matches a pattern in the role's statement.

    :param role: The role whose bucket statement is checked
    :return: None
    """
    patterns = _granted_patterns(BUCKET_STATEMENTS[role])
    assert patterns, f"the {role}'s bucket statement grants no bucket"
    ungranted = [
        name
        for name in _bucket_names()
        if not any(fnmatch.fnmatchcase(name, glob) for glob in patterns)
    ]
    assert ungranted == [], (
        f"the {role} cannot read these buckets, so a plan fails on them: "
        f"{ungranted}; add each to its bucket statement in "
        "infra/bootstrap/main.tf"
    )
