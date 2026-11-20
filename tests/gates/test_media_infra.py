"""The hub's photo storage: bucket, edge behaviour, role and host credentials.

Photos are uploaded straight to a private bucket by presigned POST,
sanitised by a Lambda, approved by an administrator and served from
``public/`` through the site distribution at ``/m/*``. The API container
still cannot reach the instance role (IMDS hop limit 1, OPS-4); it holds
only short-lived credentials for a role whose every permission is on the
bucket's four prefixes, written by a host cron job [H3 deviation 1].

None of this can be exercised without AWS, so the properties are asserted
on the Terraform, the boot template and the compose file as text, and the
host script that writes the credentials is run against stand-ins for
``aws`` and ``chgrp``.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import pathlib
import re
import shutil
import stat
import subprocess

import pytest
import yaml

from tests.gates.test_deploy_workflow import _run_record_step
from tests.gates.test_user_data_template import (
    TEMPLATE,
    TEMPLATE_VALUES,
    _render,
    _shell_bodies,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"
MEDIA = INFRA / "modules" / "media"
SITE = INFRA / "modules" / "site" / "main.tf"
APP = INFRA / "modules" / "app" / "main.tf"
ROOT_TF = INFRA / "main.tf"
BOOTSTRAP = INFRA / "bootstrap" / "main.tf"
DEPLOY_ROLE = INFRA / "bootstrap" / "deploy_role.tf"
COMPOSE = ROOT / "deploy" / "docker-compose.staging.yml"
DOCKERFILE = ROOT / "Dockerfile"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"

SCRIPT = "/usr/local/bin/shikkhokplus-media-creds"
CREDS_DIR = "/srv/shikkhokplus/media-creds"
CREDS_LOG = "/var/log/shikkhokplus-media-creds.log"
MOUNT = "/run/media-creds"

#: The four prefixes the photo pipeline uses, and nothing else.
PREFIXES = ("quarantine/", "staged/", "public/", "archive/")


def _block(text: str, header: str) -> str:
    """Return one HCL block, from its header to its matching brace.

    :param text: The file
    :param header: A regex matching the block's header up to its ``{``
    :return: The block's text, braces included
    """
    match = re.search(header + r"\s*\{", text)
    assert match is not None, f"no block matching {header!r}"
    depth = 0
    for index in range(match.end() - 1, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[match.start() : index + 1]
    raise AssertionError(f"unbalanced block {header!r}")


def _media_main() -> str:
    """Read the media module's main file.

    :return: Its text
    """
    return (MEDIA / "main.tf").read_text()


def _statements(policy: str) -> dict[str, str]:
    """Split a jsonencode'd policy into its statements, by Sid.

    :param policy: The text holding the statements
    :return: Each statement's text, keyed by its Sid
    """
    found: dict[str, str] = {}
    for match in re.finditer(r'Sid\s*=\s*"(\w+)"', policy):
        start = policy.rfind("{", 0, match.start())
        found[match.group(1)] = _block(policy[start:], r"")
    return found


def _list(text: str, key: str) -> list[str]:
    """Read a ``key = [ ... ]`` (or ``key = "..."``) as its string items.

    :param text: The block holding it
    :param key: The attribute name
    :return: The quoted items, in order
    """
    match = re.search(rf'\b{re.escape(key)}\s*=\s*(\[[^\]]*\]|"[^"\n]*")', text)
    assert match is not None, f"no {key} in {text[:80]!r}"
    return re.findall(r'"([^"]*)"', match.group(1))


# ---------------------------------------------------------------------------
# The bucket
# ---------------------------------------------------------------------------


def test_media_bucket_blocks_public_access_and_expires_prefixes() -> None:
    text = _media_main()

    bucket = _block(text, r'resource\s+"aws_s3_bucket"\s+"media"')
    # Account-suffixed, as the config, web, site and admin buckets are.
    assert re.search(
        r'bucket\s*=\s*"\$\{var\.name_prefix\}-media-'
        r'\$\{data\.aws_caller_identity\.current\.account_id\}"',
        bucket,
    )

    block = _block(text, r'resource\s+"aws_s3_bucket_public_access_block"\s+"media"')
    for flag in (
        "block_public_acls",
        "block_public_policy",
        "ignore_public_acls",
        "restrict_public_buckets",
    ):
        assert re.search(rf"{flag}\s*=\s*true", block), flag

    sse = _block(
        text,
        r'resource\s+"aws_s3_bucket_server_side_encryption_configuration"\s+"media"',
    )
    assert re.search(r'sse_algorithm\s*=\s*"AES256"', sse)

    ownership = _block(text, r'resource\s+"aws_s3_bucket_ownership_controls"\s+"media"')
    assert re.search(r'object_ownership\s*=\s*"BucketOwnerEnforced"', ownership)

    # No versioning: a deleted photo must be gone, not a noncurrent version.
    assert "aws_s3_bucket_versioning" not in text

    lifecycle = _block(
        text, r'resource\s+"aws_s3_bucket_lifecycle_configuration"\s+"media"'
    )
    expiries = {
        prefix: int(days)
        for prefix, days in re.findall(
            r'prefix\s*=\s*"([a-z]+/)"\s*\}\s*expiration\s*\{\s*days\s*=\s*(\d+)',
            lifecycle,
        )
    }
    assert expiries == {"quarantine/": 1, "staged/": 30}
    # The late-upload backstop is the quarantine lifecycle's day, as the
    # constant's comment states [I1].
    from app.hub.media.objects import LATE_UPLOAD_BACKSTOP

    assert dt.timedelta(days=expiries["quarantine/"]) == LATE_UPLOAD_BACKSTOP
    assert "public/" not in lifecycle
    assert "archive/" not in lifecycle


def test_media_bucket_accepts_posts_from_the_web_app_only() -> None:
    text = _media_main()
    cors = _block(text, r'resource\s+"aws_s3_bucket_cors_configuration"\s+"media"')

    assert _list(cors, "allowed_methods") == ["POST"]
    assert re.search(r"allowed_origins\s*=\s*\[\s*var\.web_app_origin\s*\]", cors)
    assert "*" not in cors.replace("/*", "")
    # A presigned POST is a form post: no header beyond the safelisted
    # Content-Type is needed, so none is allowed.
    assert "allowed_headers" not in cors or _list(cors, "allowed_headers") == []
    assert "expose_headers" not in cors

    # The origin is the one the API's report link is built from: web-url
    # less its /ui/ path, as deploy.yml derives SHIKKHOKPLUS_WEB_APP_URL.
    module = _block(ROOT_TF.read_text(), r'module\s+"media"')
    assert re.search(
        r'web_app_origin\s*=\s*trimsuffix\(module\.cdn\.web_url,\s*"/ui/"\)', module
    )


def test_cloudfront_reads_only_the_public_prefix_of_the_bucket() -> None:
    policy = _block(_media_main(), r'resource\s+"aws_s3_bucket_policy"\s+"media"')
    statements = _statements(policy)

    read = statements["CloudFrontReadsPublicPhotos"]
    assert re.search(
        r'Principal\s*=\s*\{\s*Service\s*=\s*"cloudfront\.amazonaws\.com"', read
    )
    assert _list(read, "Action") == ["s3:GetObject"]
    assert _list(read, "Resource") == ["${aws_s3_bucket.media.arn}/public/*"]
    assert re.search(r'"AWS:SourceArn"\s*=\s*var\.site_distribution_arn', read)
    assert "DenyInsecureTransport" in statements
    assert set(statements) == {"CloudFrontReadsPublicPhotos", "DenyInsecureTransport"}


# ---------------------------------------------------------------------------
# The /m/* behaviour on the site distribution
# ---------------------------------------------------------------------------


def test_cdn_serves_only_public_prefix_with_sandbox_headers() -> None:
    site = SITE.read_text()

    origin = re.search(
        r"origin\s*\{\s*domain_name\s*=\s*var\.media_bucket_regional_domain\s*"
        r"origin_id\s*=\s*local\.media_origin_id\s*"
        r"origin_access_control_id\s*=\s*aws_cloudfront_origin_access_control\.media\.id",
        site,
    )
    assert origin is not None, "the media bucket is not an OAC origin"
    oac = _block(site, r'resource\s+"aws_cloudfront_origin_access_control"\s+"media"')
    assert re.search(r'signing_behavior\s*=\s*"always"', oac)

    behaviours = [
        _block(site[m.start() :], r"ordered_cache_behavior")
        for m in re.finditer(r"ordered_cache_behavior\s*\{", site)
    ]
    media = [b for b in behaviours if '"/m/*"' in b]
    assert len(media) == 1, behaviours
    media_behaviour = media[0]
    assert re.search(r"target_origin_id\s*=\s*local\.media_origin_id", media_behaviour)
    assert _list(media_behaviour, "allowed_methods") == ["GET", "HEAD"]
    assert _list(media_behaviour, "cached_methods") == ["GET", "HEAD"]
    assert re.search(
        r"cache_policy_id\s*=\s*data\.aws_cloudfront_cache_policy\.optimized\.id",
        media_behaviour,
    )
    assert re.search(
        r"response_headers_policy_id\s*=\s*"
        r"aws_cloudfront_response_headers_policy\.images\.id",
        media_behaviour,
    )
    assert "origin_request_policy_id" not in media_behaviour
    # The one function: the path map /m/{key}/{w}.webp -> public/{key}/...,
    # never the site router.
    functions = re.findall(r"function_arn\s*=\s*(\S+)", media_behaviour)
    assert functions == ["aws_cloudfront_function.media_path.arn"]
    assert re.search(
        r'name\s*=\s*"Managed-CachingOptimized"',
        _block(site, r'data\s+"aws_cloudfront_cache_policy"\s+"optimized"'),
    )

    images = _block(
        site, r'resource\s+"aws_cloudfront_response_headers_policy"\s+"images"'
    )
    custom = dict(
        re.findall(
            r'header\s*=\s*"([^"]+)"\s*value\s*=\s*"([^"]+)"\s*override\s*=\s*true',
            images,
        )
    )
    # Content-Type is the object's own (image/webp, stored by the sanitiser
    # and the approval copy), not a header the edge forces.
    assert custom == {"Cache-Control": "public, max-age=31536000, immutable"}
    assert not re.search(r'header\s*=\s*"Content-Type"', images, re.IGNORECASE)
    assert re.search(r"content_type_options\s*\{\s*override\s*=\s*true\s*\}", images)
    csp = re.search(
        r'content_security_policy\s*=\s*"([^"]+)"\s*override\s*=\s*true', images
    )
    assert csp is not None
    assert csp.group(1) == "default-src 'none'; sandbox"


def test_the_path_map_reaches_only_the_public_prefix() -> None:
    source = (SITE.parent / "functions" / "media-path.js").read_text()
    resource = _block(
        SITE.read_text(), r'resource\s+"aws_cloudfront_function"\s+"media_path"'
    )

    assert re.search(r'runtime\s*=\s*"cloudfront-js-2\.0"', resource)
    assert 'functions/media-path.js")' in resource
    assert "'/public/'" in source
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    # The behavioural cases live in media-path.test.mjs (`make
    # infra-functions`); this proves the file exists and passes.
    result = subprocess.run(  # noqa: S603 -- a fixed binary on our own test
        [node, "--test", str(SITE.parent / "functions" / "media-path.test.mjs")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_root_wires_the_bucket_into_the_site() -> None:
    root = ROOT_TF.read_text()
    site = _block(root, r'module\s+"site"')
    media = _block(root, r'module\s+"media"')

    assert re.search(
        r"media_bucket_regional_domain\s*=\s*module\.media\.media_bucket_regional_domain",
        site,
    )
    assert re.search(
        r"site_distribution_arn\s*=\s*module\.site\.distribution_arn", media
    )
    outputs = (MEDIA / "outputs.tf").read_text()
    for name in ("media_bucket", "media_bucket_regional_domain", "media_role_arn"):
        assert re.search(rf'output\s+"{name}"', outputs), name


# ---------------------------------------------------------------------------
# The media role and who may assume it
# ---------------------------------------------------------------------------


def test_media_role_scoped_to_four_prefixes() -> None:
    text = _media_main()
    role = _block(text, r'resource\s+"aws_iam_role"\s+"media"')
    assert re.search(r'name\s*=\s*"\$\{var\.name_prefix\}-media"', role)
    assert re.search(r'path\s*=\s*"/shikkhokplus/"', role)
    assert re.search(r"permissions_boundary\s*=\s*var\.permissions_boundary_arn", role)

    policy = _block(text, r'resource\s+"aws_iam_role_policy"\s+"media"')
    statements = _statements(policy)
    bucket = "${aws_s3_bucket.media.arn}"

    granted = {
        sid: (_list(body, "Action"), _list(body, "Resource"))
        for sid, body in statements.items()
    }
    assert granted == {
        "SignUploads": (["s3:PutObject"], [f"{bucket}/quarantine/*"]),
        "ReadResults": (
            ["s3:GetObject"],
            [f"{bucket}/staged/*", f"{bucket}/archive/*"],
        ),
        "FreezeToArchive": (["s3:PutObject"], [f"{bucket}/archive/*"]),
        "PublishFromArchive": (["s3:PutObject"], [f"{bucket}/public/*"]),
        "DeleteObjects": (
            ["s3:DeleteObject"],
            [f"{bucket}/{prefix}*" for prefix in PREFIXES],
        ),
        "ListOwnPrefixes": (["s3:ListBucket"], [bucket]),
    }
    assert "Deny" not in policy and "NotAction" not in policy
    # A write to archive/ or public/ must be a copy, and from one prefix only
    # [final review minor 5, I1]: completion freezes staged/ into archive/,
    # and public/ is filled from archive/ alone. A compromised container can
    # put no bytes of its own where CloudFront serves them, nor copy
    # unfrozen staged/ bytes there.
    name = "${aws_s3_bucket.media.bucket}"
    for sid, source_folder in (
        ("FreezeToArchive", "staged"),
        ("PublishFromArchive", "archive"),
    ):
        copy = statements[sid]
        assert re.search(r"StringLike\s*=", copy), sid
        source = re.search(r'"s3:x-amz-copy-source"\s*=\s*\[([^\]]*)\]', copy)
        assert source is not None, sid
        assert sorted(re.findall(r'"([^"]*)"', source.group(1))) == sorted(
            f"{lead}{name}/{source_folder}/*" for lead in ("", "/")
        ), sid
    # No other statement grants a write to either prefix.
    for sid, (actions, resources) in granted.items():
        if sid in ("FreezeToArchive", "PublishFromArchive", "DeleteObjects"):
            continue
        assert not any(
            r.startswith((f"{bucket}/public/", f"{bucket}/archive/"))
            for r in resources
            if "s3:PutObject" in actions
        ), sid
    listing = statements["ListOwnPrefixes"]
    condition = re.search(r'"s3:prefix"\s*=\s*\[([^\]]*)\]', listing)
    assert condition is not None
    assert re.findall(r'"([^"]*)"', condition.group(1)) == [f"{p}*" for p in PREFIXES]
    assert re.search(r"StringLike\s*=", listing)


def test_instance_role_may_only_assume_media_role() -> None:
    text = _media_main()
    role = _block(text, r'resource\s+"aws_iam_role"\s+"media"')
    trust = role[role.index("assume_role_policy") :]
    assert re.search(
        r"Principal\s*=\s*\{\s*AWS\s*=\s*var\.instance_role_arn\s*\}", trust
    )
    assert _list(trust, "Action") == ["sts:AssumeRole"]
    assert "Service" not in trust

    app = APP.read_text()
    assume = _block(app, r'resource\s+"aws_iam_role_policy"\s+"media_assume"')
    assert re.search(
        r"count\s*=\s*var\.media_role\s*==\s*null\s*\?\s*0\s*:\s*1", assume
    )
    assert re.search(r"role\s*=\s*aws_iam_role\.instance\.id", assume)
    assert _list(assume, "Action") == ["sts:AssumeRole"]
    assert re.search(r"Resource\s*=\s*var\.media_role\.arn", assume)
    # No other inline policy on the host's role grants anything in STS.
    granting = [
        name
        for name in re.findall(r'resource\s+"aws_iam_role_policy"\s+"(\w+)"', app)
        if '"sts:' in _block(app, rf'resource\s+"aws_iam_role_policy"\s+"{name}"')
    ]
    assert granting == ["media_assume"]

    root = ROOT_TF.read_text()
    primary = _block(root, r'module\s+"app"')
    rehearsal = _block(root, r'module\s+"staging_app"')
    media = _block(root, r'module\s+"media"')
    assert re.search(
        r"media_role\s*=\s*\{\s*arn\s*=\s*module\.media\.media_role_arn\s*\}",
        primary,
    )
    assert "media_role" not in rehearsal
    assert re.search(r"instance_role_arn\s*=\s*module\.app\.instance_role_arn", media)

    # The boundary caps the host at this one role, and the role at the
    # bucket's objects.
    boundary = _block(
        BOOTSTRAP.read_text(), r'resource\s+"aws_iam_policy"\s+"environment_boundary"'
    )
    statements = _statements(boundary)
    assume_ceiling = statements["AssumeMediaRole"]
    assert _list(assume_ceiling, "Action") == ["sts:AssumeRole"]
    assert _list(assume_ceiling, "Resource") == [
        "arn:aws:iam::${local.account_id}:role/shikkhokplus/shikkhokplus-${each.key}-media"
    ]
    objects = statements["MediaObjects"]
    assert _list(objects, "Action") == ["s3:*Object*"]
    assert _list(objects, "Resource") == [
        "arn:aws:s3:::shikkhokplus-${each.key}-media-*/*"
    ]
    listing = statements["MediaList"]
    assert _list(listing, "Action") == ["s3:ListBucket"]
    assert _list(listing, "Resource") == [
        "arn:aws:s3:::shikkhokplus-${each.key}-media-*"
    ]


def test_the_infrastructure_role_may_manage_the_bucket_and_its_notification() -> None:
    text = BOOTSTRAP.read_text()
    start = text.index('sid    = "ConfigBucket"')
    statement = text[start : text.index("statement {", start)]
    for action in (
        "s3:PutBucketCORS",
        "s3:PutLifecycleConfiguration",
        "s3:GetBucketOwnershipControls",
        "s3:PutBucketOwnershipControls",
        "s3:GetBucketNotification",
        "s3:PutBucketNotification",
    ):
        assert f'"{action}"' in statement, action
    assert '"arn:aws:s3:::shikkhokplus-${each.key}-media-*"' in statement


# ---------------------------------------------------------------------------
# The host's credentials
# ---------------------------------------------------------------------------


def _rendered() -> str:
    """Render the boot template with the test values.

    :return: The script
    """
    return _render(TEMPLATE.read_text(), TEMPLATE_VALUES)


def _script(values: dict[str, str] = TEMPLATE_VALUES) -> str:
    """Return the credentials script as the boot script installs it.

    :param values: The template variables
    :return: Its text
    """
    for body in _shell_bodies(_render(TEMPLATE.read_text(), values)):
        if f"cat > {SCRIPT}" in body.name:
            return "\n".join(body.lines)
    raise AssertionError(f"the template no longer installs {SCRIPT}")


def test_host_refreshes_media_creds_every_15_minutes_and_at_boot() -> None:
    rendered = _rendered()
    boot = "\n".join(_shell_bodies(rendered)[0].lines)

    entry = f"*/15 * * * * root {SCRIPT} >> {CREDS_LOG} 2>&1"
    assert entry in rendered
    assert re.search(rf"install\b[^\n]*-m 0640[^\n]*{re.escape(CREDS_LOG)}", boot)
    assert re.search(rf"install -d\b[^\n]*-g 10001[^\n]*{re.escape(CREDS_DIR)}", boot)

    # Run once at boot, logged, BEFORE compose starts the api that reads it.
    first_run = boot.index(f"{SCRIPT} >> {CREDS_LOG}")
    installed = boot.index(f"cat > {SCRIPT}")
    started = boot.index("docker compose up -d")
    assert installed < first_run < started

    script = _script()
    assert "aws sts assume-role" in script
    assert "--duration-seconds 3600" in script
    assert f'role_arn="{TEMPLATE_VALUES["media_role_arn"]}"' in script
    assert "mv -f" in script

    source = TEMPLATE.read_text()
    main_tf = APP.read_text()
    assert 'role_arn="${media_role_arn}"' in source
    assert re.search(r'media_role_arn\s*=\s*try\(var\.media_role\.arn,\s*""\)', main_tf)


def test_the_object_drain_runs_inside_the_running_container() -> None:
    # Every two minutes, as the CDN sender does; inside the running
    # container (`exec`, never `run --rm` on a 2 GB host), where the media
    # credentials are mounted; never two at once; into a log that exists
    # before the first run, since the job runs as ubuntu.
    rendered = _rendered()
    boot = "\n".join(_shell_bodies(rendered)[0].lines)
    log = "/var/log/shikkhokplus-hub-media-objects.log"
    entry = (
        "*/2 * * * * ubuntu cd /srv/shikkhokplus && flock -n "
        "/run/lock/shikkhokplus-hub-media-objects.lock docker compose exec -T api "
        f"python -m app.hub.media.commands drain >> {log} 2>&1"
    )

    assert entry in rendered
    assert re.search(rf"install\b[^\n]*-o ubuntu[^\n]*{re.escape(log)}", boot)


def test_the_credentials_group_is_the_containers() -> None:
    # The container runs as `app`, uid 10001, whose own group useradd
    # creates with the same id; the file is group-readable by that id.
    dockerfile = DOCKERFILE.read_text()
    uid = re.search(r"useradd\b[^\n]*--uid (\d+) app", dockerfile)
    assert uid is not None
    script = _script()

    assert f"chgrp {uid.group(1)} " in script
    assert "chmod 0640 " in script


@pytest.fixture
def host(tmp_path: pathlib.Path) -> pathlib.Path:
    """Build stand-ins for ``aws`` and ``chgrp`` that record their calls.

    :param tmp_path: A scratch directory
    :return: The directory holding ``bin/``, the credentials dir and logs
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "creds").mkdir()
    (tmp_path / "lock").mkdir()
    aws = bin_dir / "aws"
    aws.write_text(
        "#!/bin/bash\n"
        'printf "%s\\n" "$@" > "$STUB_DIR/aws.args"\n'
        'if [ "$STUB_AWS" = fail ]; then\n'
        '  echo "An error occurred (AccessDenied) when calling AssumeRole" >&2\n'
        "  exit 254\n"
        "fi\n"
        'if [ "$STUB_AWS" = garbage ]; then echo "None"; exit 0; fi\n'
        "printf 'ASIAEXAMPLEEXAMPLE01\\t"  # gitleaks:allow -- fixture
        "secret/Key+Value0123456789abcdefABCDEF\\t"
        "IQoJb3JpZ2luX2VjEXAMPLETOKEN==\\t2026-11-18T13:00:00+00:00\\n'\n"
    )
    chgrp = bin_dir / "chgrp"
    chgrp.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$STUB_DIR/chgrp.log"\n')
    for stub in (aws, chgrp):
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return tmp_path


def _run(
    host: pathlib.Path, *, aws: str = "ok", role_arn: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the rendered credentials script against the stand-ins.

    The credentials directory and the lock are moved into the scratch
    directory; nothing else in the script is changed.

    :param host: The stand-ins' directory
    :param aws: ``ok``, ``fail`` (AccessDenied) or ``garbage`` (unreadable)
    :param role_arn: The role the template receives; default the test value
    :return: The finished process
    """
    values = dict(TEMPLATE_VALUES)
    if role_arn is not None:
        values["media_role_arn"] = role_arn
    text = _script(values)
    text = text.replace(CREDS_DIR, str(host / "creds")).replace(
        "/run/lock/", f"{host / 'lock'}/"
    )
    script = host / "media-creds.sh"
    script.write_text(text + "\n")
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    return subprocess.run(  # noqa: S603 -- a script this test rendered
        [bash, str(script)],
        env={
            **os.environ,
            "PATH": f"{host / 'bin'}:{os.environ['PATH']}",
            "STUB_DIR": str(host),
            "STUB_AWS": aws,
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_creds_script_writes_the_ini_the_sdk_reads(host: pathlib.Path) -> None:
    result = _run(host)

    assert result.returncode == 0, result.stdout + result.stderr
    args = (host / "aws.args").read_text().splitlines()
    assert args[:2] == ["sts", "assume-role"]
    assert args[args.index("--role-arn") + 1] == TEMPLATE_VALUES["media_role_arn"]
    assert args[args.index("--duration-seconds") + 1] == "3600"
    assert args[args.index("--region") + 1] == TEMPLATE_VALUES["aws_region"]

    written = host / "creds" / "credentials"
    assert written.read_text() == (
        "[default]\n"
        "aws_access_key_id = ASIAEXAMPLEEXAMPLE01\n"  # gitleaks:allow -- fixture
        "aws_secret_access_key = secret/Key+Value0123456789abcdefABCDEF\n"
        "aws_session_token = IQoJb3JpZ2luX2VjEXAMPLETOKEN==\n"
    )
    assert stat.S_IMODE(written.stat().st_mode) == 0o640
    chgrp = (host / "chgrp.log").read_text().splitlines()
    assert len(chgrp) == 1 and chgrp[0].startswith("10001 ")
    # Only the final file remains: the temporary one was renamed, not copied.
    assert [p.name for p in (host / "creds").iterdir()] == ["credentials"]
    # Nothing secret reaches the log.
    for secret in ("secret/Key", "IQoJb3JpZ2lu", "ASIAEXAMPLE"):
        assert secret not in result.stdout + result.stderr
    assert "2026-11-18T13:00:00" in result.stdout


@pytest.mark.parametrize("failure", ["fail", "garbage"])
def test_a_failed_assume_role_keeps_the_previous_credentials(
    host: pathlib.Path, failure: str
) -> None:
    previous = host / "creds" / "credentials"
    previous.write_text("[default]\naws_access_key_id = ASIAPREVIOUS\n")

    result = _run(host, aws=failure)

    assert result.returncode != 0
    assert previous.read_text() == "[default]\naws_access_key_id = ASIAPREVIOUS\n"
    assert [p.name for p in (host / "creds").iterdir()] == ["credentials"]
    assert not (host / "chgrp.log").exists()
    if failure == "fail":
        assert "AccessDenied" in result.stdout


def test_a_host_with_no_media_role_writes_nothing(host: pathlib.Path) -> None:
    # The rehearsal host: no role to assume, so nothing to write -- and no
    # failure, because there is nothing wrong.
    result = _run(host, role_arn="")

    assert result.returncode == 0
    assert not (host / "aws.args").exists()
    assert list((host / "creds").iterdir()) == []
    assert "no media role" in result.stdout


# ---------------------------------------------------------------------------
# The container
# ---------------------------------------------------------------------------


def test_compose_mounts_creds_read_only() -> None:
    services = yaml.safe_load(COMPOSE.read_text())["services"]
    api = services["api"]

    assert f"{CREDS_DIR}:{MOUNT}:ro" in api["volumes"]
    environment = api["environment"]
    assert environment["AWS_SHARED_CREDENTIALS_FILE"] == f"{MOUNT}/credentials"
    assert environment["AWS_REGION"] == "${AWS_REGION:-}"
    assert environment["SHIKKHOKPLUS_MEDIA_BUCKET"] == "${SHIKKHOKPLUS_MEDIA_BUCKET:-}"
    # No fallback to IMDS when the file is missing: hop limit 1 would make
    # every such call time out rather than fail.
    assert environment["AWS_EC2_METADATA_DISABLED"] == "true"
    assert services["migrate"]["environment"]["AWS_EC2_METADATA_DISABLED"] == "true"
    # The migrate service is the schema owner and never touches S3.
    migrate = services["migrate"]
    assert "volumes" not in migrate
    assert "AWS_SHARED_CREDENTIALS_FILE" not in migrate["environment"]


#: The bucket the stand-in SSM names: account-suffixed.
_BUCKET = "shikkhokplus-staging-media-123456789012"

_MEDIA_PARAMS = {
    "media-bucket": "shikkhokplus-staging-media-123456789012",
    "media-bucket-domain": f"{_BUCKET}.s3.ap-south-1.amazonaws.com",
}


def test_the_release_writes_the_bucket_and_its_region(tmp_path: pathlib.Path) -> None:
    finished, _, runtime = _run_record_step(tmp_path, **_MEDIA_PARAMS)

    assert finished.returncode == 0, finished.stdout + finished.stderr
    assert runtime["SHIKKHOKPLUS_MEDIA_BUCKET"] == _BUCKET
    assert runtime["AWS_REGION"] == "ap-south-1"
    output = (tmp_path / "github-output").read_text()
    assert (
        f"media_origin=https://{_BUCKET}.s3.ap-south-1.amazonaws.com"
        in output.splitlines()
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"media-bucket": None},
        {"media-bucket-domain": None},
        # A legacy global endpoint names no region, and the CSP would not
        # match what the SDK signs for.
        {"media-bucket-domain": f"{_BUCKET}.s3.amazonaws.com"},
        {"media-bucket-domain": "another-bucket.s3.ap-south-1.amazonaws.com"},
        # The pre-suffix name: not the bucket Terraform now creates.
        {
            "media-bucket": "shikkhokplus-staging-media",
            "media-bucket-domain": (
                "shikkhokplus-staging-media.s3.ap-south-1.amazonaws.com"
            ),
        },
    ],
    ids=["no-bucket", "no-domain", "global-endpoint", "other-bucket", "unsuffixed"],
)
def test_no_media_bucket_stops_the_release_before_anything_is_written(
    tmp_path: pathlib.Path, overrides: dict[str, str | None]
) -> None:
    finished, calls, runtime = _run_record_step(
        tmp_path, **{**_MEDIA_PARAMS, **overrides}
    )

    assert finished.returncode != 0
    assert "media" in finished.stdout
    assert not [c for c in calls if c.startswith("ssm put-parameter")]
    assert runtime == {}


def test_the_root_publishes_what_the_release_reads() -> None:
    root = ROOT_TF.read_text()
    for name, value in (
        ("media-bucket", "module.media.media_bucket"),
        ("media-bucket-domain", "module.media.media_bucket_regional_domain"),
    ):
        assert re.search(
            r'name\s*=\s*"/shikkhokplus/\$\{local\.name_prefix\}/'
            + re.escape(name)
            + r'"\s*type\s*=\s*"String"\s*value\s*=\s*'
            + re.escape(value),
            root,
        ), name
        assert f'"{name}"' in DEPLOY_ROLE.read_text(), name


def test_both_web_builds_name_the_bucket_endpoint() -> None:
    workflow = yaml.safe_load(DEPLOY.read_text())
    jobs = workflow["jobs"]
    origin = "${{ needs.release.outputs.media_origin }}"

    assert jobs["release"]["outputs"]["media_origin"] == (
        "${{ steps.record.outputs.media_origin }}"
    )
    web = [
        s for s in jobs["web"]["steps"] if s.get("name") == "Check and build for /ui/"
    ]
    admin = [s for s in jobs["admin"]["steps"] if s.get("name") == "Build the admin UI"]
    assert web[0]["env"]["VITE_MEDIA_ORIGIN"] == origin
    assert admin[0]["env"]["VITE_MEDIA_ORIGIN"] == origin


# ---------------------------------------------------------------------------
# The budget
# ---------------------------------------------------------------------------


def test_cost_breakdown_has_media_lines() -> None:
    root = ROOT_TF.read_text()
    breakdown = _block(root, r"cost_breakdown\s*=")

    media = re.search(r"((?:\s*#[^\n]*\n)+)\s*media\s*=\s*0\.09\n", breakdown)
    image_lambda = re.search(
        r"((?:\s*#[^\n]*\n)+)\s*image_lambda\s*=\s*0\.00\n", breakdown
    )
    assert media is not None, "no `media = 0.09` line with its arithmetic above it"
    assert image_lambda is not None, "no `image_lambda = 0.00` line with its reasoning"
    assert "free tier" in image_lambda.group(1).lower()

    # The comment states the arithmetic, and a number in a comment is a
    # claim (project.md): every figure it states is recomputed here.
    comment = " ".join(
        line.strip().lstrip("#").strip() for line in media.group(1).splitlines()
    )
    for figure in (
        "3 x 12 x 0.3 MB x 300 = 1,080 MB per copy",
        "about 3.2 GB",
        "USD 0.023/GB-month = USD 0.0745",
        "2,000 write-class",
        "USD 0.005 per 1,000 = USD 0.01",
        "5,000 at USD 0.0004 per 1,000 = USD 0.002",
        "USD 0.0865, rounded up",
    ):
        assert figure in comment, figure
    per_copy_mb = 12 * 0.3 * 300
    assert math.isclose(per_copy_mb, 1080)
    held_gb = 3 * per_copy_mb / 1000
    assert round(held_gb, 1) == 3.2
    storage = held_gb * 0.023
    assert math.isclose(storage, 0.07452, rel_tol=1e-3)
    total = storage + 2000 * 0.005 / 1000 + 5000 * 0.0004 / 1000
    assert math.isclose(total, 0.0865, abs_tol=0.0001)
    assert 0 <= 0.09 - total < 0.01
