"""The image sanitiser Lambda's wiring: Terraform, roles, CI, CVEs, isolation.

The handler itself is tested by ``make lambda-test``
(lambdas/image_sanitiser/tests). What is asserted here is everything around
it that only AWS would otherwise exercise: the function's shape and the one
role it runs as, the trigger, the placeholder Terraform creates it from, the
grants the deploy needs to ship its code, the CI job and the CVE and SBOM
wiring -- and that Pillow, the decoder of hostile bytes, never reaches the
API.
"""

from __future__ import annotations

import fnmatch
import pathlib
import re
import zipfile

import yaml

from tests.gates.test_media_infra import _block, _list, _statements

ROOT = pathlib.Path(__file__).resolve().parents[2]
MEDIA = ROOT / "infra" / "modules" / "media"
LAMBDA_TF = MEDIA / "lambda.tf"
PLACEHOLDER = MEDIA / "placeholder"
BOOTSTRAP = ROOT / "infra" / "bootstrap" / "main.tf"
DEPLOY_ROLE = ROOT / "infra" / "bootstrap" / "deploy_role.tf"
WORKFLOWS = ROOT / ".github" / "workflows"
MAKEFILE = ROOT / "Makefile"
LOCKFILE = "lambdas/image_sanitiser/requirements.txt"

#: The function's name in each place that names it, rendered for staging.
FUNCTION = "shikkhokplus-staging-image-sanitiser"
ACCOUNT = "123456789012"


def _lambda_tf() -> str:
    return LAMBDA_TF.read_text()


def _function() -> str:
    return _block(_lambda_tf(), r'resource\s+"aws_lambda_function"\s+"sanitiser"')


# ---------------------------------------------------------------------------
# The function
# ---------------------------------------------------------------------------


def test_the_function_is_arm64_python_with_bounded_concurrency() -> None:
    function = _function()

    assert re.search(r'runtime\s*=\s*"python3\.12"', function)
    assert re.search(r'handler\s*=\s*"handler\.handler"', function)
    assert _list(function, "architectures") == ["arm64"]
    assert re.search(r"memory_size\s*=\s*1024\b", function)
    assert re.search(r"timeout\s*=\s*30\b", function)
    assert re.search(r"reserved_concurrent_executions\s*=\s*2\b", function)
    # No VPC: no route to the database, and nothing to attach.
    assert "vpc_config" not in function
    # No environment: nothing in its configuration is a secret, which is
    # what lets the deploy role read it.
    assert "environment" not in function
    # The same region as the bucket [R5]: the module's default provider,
    # which the root passes nothing over.
    assert "provider" not in function
    root_call = _block((ROOT / "infra" / "main.tf").read_text(), r'module\s+"media"')
    assert "providers" not in root_call


def test_an_upload_gets_one_attempt_and_events_expire() -> None:
    # [R7b] Lambda retries a failed asynchronous invocation twice by
    # default, so a hostile upload that times out or exhausts memory would
    # hold one of the two slots three times over. One attempt, and a
    # throttled event older than five minutes is dropped; `complete`
    # settles an upload with no result [R7c].
    config = _block(
        _lambda_tf(),
        r'resource\s+"aws_lambda_function_event_invoke_config"\s+"sanitiser"',
    )
    assert re.search(
        r"function_name\s*=\s*aws_lambda_function\.sanitiser\.function_name", config
    )
    assert re.search(r"maximum_retry_attempts\s*=\s*0\n", config)
    assert re.search(r"maximum_event_age_in_seconds\s*=\s*300\n", config)
    # Not routed anywhere that would need a grant the role lacks.
    assert "destination_config" not in config

    # The plan role can read the setting back on every refresh.
    plan = _statements(
        _block(BOOTSTRAP.read_text(), r'resource\s+"aws_iam_role_policy"\s+"plan"')
    )
    assert "lambda:GetFunctionEventInvokeConfig" in _list(
        plan["ReadOurFunctions"], "Action"
    )


def test_terraform_creates_the_placeholder_and_never_touches_code_again() -> None:
    function = _function()

    assert re.search(
        r'filename\s*=\s*"\$\{path\.module\}/placeholder/image-sanitiser\.zip"',
        function,
    )
    lifecycle = _block(function, r"lifecycle")
    ignored = re.search(r"ignore_changes\s*=\s*\[([^\]]*)\]", lifecycle)
    assert ignored is not None
    assert {item.strip() for item in ignored.group(1).split(",") if item.strip()} == {
        "filename",
        "source_code_hash",
    }
    # Not archive_file: a zip written during the plan is not on the runner
    # that applies the saved plan.
    assert not re.search(r'(data|resource)\s+"archive_file"', _lambda_tf())


def test_the_placeholder_zip_is_exactly_its_readable_source() -> None:
    with zipfile.ZipFile(PLACEHOLDER / "image-sanitiser.zip") as archive:
        assert archive.namelist() == ["handler.py"]
        packaged = archive.read("handler.py")
    assert packaged == (PLACEHOLDER / "handler.py").read_bytes()
    # It refuses rather than accepting an upload it cannot sanitise.
    assert b"raise RuntimeError" in packaged


def test_the_function_logs_to_a_group_the_grants_cover() -> None:
    text = _lambda_tf()
    group = _block(text, r'resource\s+"aws_cloudwatch_log_group"\s+"sanitiser"')
    assert re.search(
        r'name\s*=\s*"/shikkhokplus/\$\{var\.name_prefix\}/image-sanitiser"', group
    )
    assert re.search(r"retention_in_days\s*=\s*var\.log_retention_days", group)
    variables = (MEDIA / "variables.tf").read_text()
    retention = _block(variables, r'variable\s+"log_retention_days"')
    assert re.search(r"default\s*=\s*30\b", retention)

    logging = _block(_function(), r"logging_config")
    assert re.search(
        r"log_group\s*=\s*aws_cloudwatch_log_group\.sanitiser\.name", logging
    )


def test_the_role_reads_quarantine_writes_staged_and_nothing_else() -> None:
    text = _lambda_tf()
    role = _block(text, r'resource\s+"aws_iam_role"\s+"sanitiser"')
    assert re.search(r'path\s*=\s*"/shikkhokplus/"', role)
    assert re.search(r"permissions_boundary\s*=\s*var\.permissions_boundary_arn", role)
    assert re.search(r'Service\s*=\s*"lambda\.amazonaws\.com"', role)
    assert '"aws:SourceAccount"' in role

    policy = _block(text, r'resource\s+"aws_iam_role_policy"\s+"sanitiser"')
    bucket = "${aws_s3_bucket.media.arn}"
    granted = {
        sid: (_list(body, "Action"), _list(body, "Resource"))
        for sid, body in _statements(policy).items()
    }
    assert granted == {
        "ReadAndRemoveUploads": (
            ["s3:GetObject", "s3:DeleteObject"],
            [f"{bucket}/quarantine/*"],
        ),
        "WriteVariants": (["s3:PutObject"], [f"{bucket}/staged/*"]),
        "OwnLogs": (
            ["logs:CreateLogStream", "logs:PutLogEvents"],
            ["${aws_cloudwatch_log_group.sanitiser.arn}:*"],
        ),
    }
    assert "Deny" not in policy and "NotAction" not in policy
    # Exactly one inline policy for the role, and no managed one.
    assert len(re.findall(r'resource\s+"aws_iam_role_policy"\s+"', text)) == 1
    assert "aws_iam_role_policy_attachment" not in text


def test_s3_invokes_it_for_every_object_created_under_quarantine() -> None:
    text = _lambda_tf()
    notification = _block(
        text, r'resource\s+"aws_s3_bucket_notification"\s+"quarantine"'
    )
    assert re.search(r"bucket\s*=\s*aws_s3_bucket\.media\.id", notification)
    targets = re.findall(r"lambda_function\s*\{", notification)
    assert len(targets) == 1
    assert _list(notification, "events") == ["s3:ObjectCreated:*"]
    assert _list(notification, "filter_prefix") == ["quarantine/"]
    assert re.search(
        r"lambda_function_arn\s*=\s*aws_lambda_function\.sanitiser\.arn", notification
    )
    assert re.search(
        r"depends_on\s*=\s*\[aws_lambda_permission\.s3_invokes_sanitiser\]",
        notification,
    )

    permission = _block(
        text, r'resource\s+"aws_lambda_permission"\s+"s3_invokes_sanitiser"'
    )
    assert re.search(r'principal\s*=\s*"s3\.amazonaws\.com"', permission)
    assert re.search(r'action\s*=\s*"lambda:InvokeFunction"', permission)
    assert re.search(r"source_arn\s*=\s*aws_s3_bucket\.media\.arn", permission)
    assert re.search(
        r"source_account\s*=\s*data\.aws_caller_identity\.current\.account_id",
        permission,
    )
    # One notification resource per bucket is all S3 allows: a second
    # would silently replace this one.
    infra = (ROOT / "infra").rglob("*.tf")
    notifications = [
        path
        for path in infra
        if re.search(r'resource\s+"aws_s3_bucket_notification"', path.read_text())
    ]
    assert notifications == [LAMBDA_TF]


# ---------------------------------------------------------------------------
# Who may create it, and who may ship its code
# ---------------------------------------------------------------------------


def _rendered_name() -> str:
    match = re.search(r'sanitiser_name\s*=\s*"([^"]+)"', _lambda_tf())
    assert match is not None
    return match.group(1).replace("${var.name_prefix}", "shikkhokplus-staging")


def test_the_function_has_one_name_everywhere() -> None:
    assert _rendered_name() == FUNCTION

    deploy = yaml.safe_load((WORKFLOWS / "deploy.yml").read_text())
    ship = [
        step
        for step in deploy["jobs"]["image-sanitiser"]["steps"]
        if "update-function-code" in str(step.get("run", ""))
    ]
    assert len(ship) == 1
    assert (
        ship[0]["env"]["FUNCTION"]
        == "shikkhokplus-${{ inputs.environment }}-image-sanitiser"
    )


def test_the_deploy_role_may_ship_this_function_and_no_other() -> None:
    statements = _statements(DEPLOY_ROLE.read_text())
    ship = statements["ShipTheImageSanitiser"]

    assert _list(ship, "Action") == [
        "lambda:UpdateFunctionCode",
        "lambda:GetFunctionConfiguration",
    ]
    resource = _list(ship, "Resource")
    assert resource == [
        "arn:aws:lambda:*:${data.aws_caller_identity.current.account_id}"
        ":function:shikkhokplus-${each.key}-image-sanitiser"
    ]
    # The seeder's grant is unchanged: its configuration holds the
    # database URL, so the deploy role still may not read it.
    assert _list(statements["MoveTheSeeder"], "Action") == ["lambda:UpdateFunctionCode"]
    granting = [
        sid
        for sid, body in statements.items()
        if '"lambda:GetFunctionConfiguration"' in body
    ]
    assert granting == ["ShipTheImageSanitiser"]


def test_the_infrastructure_role_and_boundary_already_cover_it() -> None:
    # Nothing new in bootstrap for Terraform's half: the seeder's grants
    # and the photo bucket's already reach every resource lambda.tf
    # creates. Asserted against the rendered ARNs, so a renamed function
    # or log group fails here rather than at the first apply.
    bootstrap = BOOTSTRAP.read_text()
    infrastructure = _statements(
        _block(bootstrap, r'resource\s+"aws_iam_role_policy"\s+"ci_infrastructure"')
    )
    boundary = _statements(
        _block(bootstrap, r'resource\s+"aws_iam_policy"\s+"environment_boundary"')
    )
    function_arn = f"arn:aws:lambda:us-east-1:{ACCOUNT}:function:{FUNCTION}"
    group_arn = (
        f"arn:aws:logs:us-east-1:{ACCOUNT}:log-group:"
        "/shikkhokplus/shikkhokplus-staging/image-sanitiser"
    )
    role_arn = f"arn:aws:iam::{ACCOUNT}:role/shikkhokplus/{FUNCTION}"

    def render(pattern: str) -> str:
        return pattern.replace("${local.account_id}", ACCOUNT).replace(
            "${each.key}", "staging"
        )

    def covered(
        sid: str, arn: str, action: str, policy: dict[str, str] = infrastructure
    ) -> bool:
        body = policy[sid]
        return any(
            fnmatch.fnmatchcase(action, a) for a in _list(body, "Action")
        ) and any(fnmatch.fnmatchcase(arn, render(r)) for r in _list(body, "Resource"))

    for action in (
        "lambda:CreateFunction",
        "lambda:PutFunctionConcurrency",
        "lambda:PutFunctionEventInvokeConfig",
        "lambda:AddPermission",
    ):
        assert covered("SeederFunction", function_arn, action), action
    assert covered("Observability", group_arn, "logs:CreateLogGroup")
    assert covered("Observability", group_arn, "logs:PutRetentionPolicy")
    assert covered("GrantOnlyWithinTheBoundary", role_arn, "iam:CreateRole")
    assert covered("PassOnlyToEc2AndLambda", role_arn, "iam:PassRole")
    assert '"lambda.amazonaws.com"' in infrastructure["PassOnlyToEc2AndLambda"]

    # The boundary admits the role's own writes: its log stream and the
    # bucket's objects.
    stream = f"{group_arn}:log-stream:2026/11/18/[$LATEST]abc"
    assert covered("Logs", stream, "logs:PutLogEvents", boundary)
    bucket = f"arn:aws:s3:::shikkhokplus-staging-media-{ACCOUNT}"
    for key, action in (
        ("quarantine/x", "s3:GetObject"),
        ("quarantine/x", "s3:DeleteObject"),
        ("staged/x/320.webp", "s3:PutObject"),
    ):
        assert covered("MediaObjects", f"{bucket}/{key}", action, boundary), action


# ---------------------------------------------------------------------------
# Pillow stays in the Lambda
# ---------------------------------------------------------------------------


def test_pillow_never_reaches_the_api() -> None:
    for manifest in ("pyproject.toml", "requirements.txt", "Dockerfile"):
        text = (ROOT / manifest).read_text().lower()
        assert "pillow" not in text, manifest
    importing = re.compile(r"^\s*(import|from)\s+PIL\b", re.M)
    offenders = [
        str(path.relative_to(ROOT))
        for top in ("app", "scripts", "deploy", "migrations")
        for path in (ROOT / top).rglob("*.py")
        if importing.search(path.read_text())
    ]
    assert offenders == []
    # The image copies app/ and migrations/ only, and the build context
    # does not even carry the Lambda or its package.
    copied = re.findall(
        r"^COPY\s+(?!--from)(\S+)", (ROOT / "Dockerfile").read_text(), re.M
    )
    assert not [path for path in copied if path.startswith(("lambdas", "dist"))]
    ignored = (ROOT / ".dockerignore").read_text().split()
    assert {"lambdas", "dist"} <= set(ignored)


def test_the_lockfile_is_hashed_and_names_only_pillow() -> None:
    text = (ROOT / LOCKFILE).read_text()
    pins = re.findall(r"^([A-Za-z0-9][\w.-]*)==", text, re.M)
    assert pins == ["pillow"]
    assert "--hash=sha256:" in text


# ---------------------------------------------------------------------------
# CI, CVEs and the SBOM
# ---------------------------------------------------------------------------


def _target(name: str) -> str:
    text = MAKEFILE.read_text()
    match = re.search(rf"^{re.escape(name)}:[^\n]*\n((?:\t[^\n]*\n|\n)+)", text, re.M)
    assert match is not None, name
    return match.group(1)


def test_make_check_runs_the_sanitiser_suite() -> None:
    prerequisites = re.search(r"^check:([^\n]*)$", MAKEFILE.read_text(), re.M)
    assert prerequisites is not None
    assert "lambda-test" in prerequisites.group(1).split()

    recipe = _target("lambda-test")
    assert "--require-hashes -r $(LAMBDA_DIR)/requirements.txt" in recipe
    assert "pytest $(LAMBDA_DIR)/tests" in recipe
    assert "ruff check lambdas" in recipe
    assert "mypy -p image_sanitiser" in recipe


def test_the_package_is_built_for_arm64_from_wheels_only() -> None:
    recipe = _target("lambda-image")

    assert "--only-binary :all:" in recipe
    assert "--platform manylinux_2_28_aarch64" in recipe
    assert "--python-version 3.12" in recipe
    assert "--require-hashes -r $(LAMBDA_DIR)/requirements.txt" in recipe
    assert "check_package.py $(LAMBDA_ZIP)" in recipe
    assert re.search(
        r"^LAMBDA_ZIP := dist/image_sanitiser\.zip$", MAKEFILE.read_text(), re.M
    )


def test_ci_has_a_lambda_job_running_the_targets() -> None:
    jobs = yaml.safe_load((WORKFLOWS / "check.yml").read_text())["jobs"]
    job = jobs["lambda"]
    assert job["name"] == "lambda"
    runs = [str(step.get("run", "")) for step in job["steps"]]
    assert "make lambda-test" in runs
    assert "make lambda-image" in runs
    install = next(r for r in runs if "pip install --require-hashes" in r)
    assert "-r requirements.txt" in install


def test_every_audit_covers_the_sanitiser_lockfile() -> None:
    assert LOCKFILE.replace("lambdas/image_sanitiser", "$(LAMBDA_DIR)") in _target(
        "audit"
    )

    deploy = yaml.safe_load((WORKFLOWS / "deploy.yml").read_text())
    gate = next(
        step
        for step in deploy["jobs"]["plan"]["steps"]
        if "deploy/cve_gate.py" in str(step.get("run", ""))
    )
    script = str(gate["run"])
    assert f"pip-audit --requirement {LOCKFILE}" in script
    assert re.search(
        r"cve_gate\.py audit\.json audit-image-sanitiser\.json \\\s*\n\s*"
        r"\.security-exceptions\.md",
        script,
    )

    check = yaml.safe_load((WORKFLOWS / "check.yml").read_text())["jobs"]["lambda"]
    annotate = next(s for s in check["steps"] if "pip-audit" in str(s.get("run", "")))
    assert LOCKFILE in str(annotate["run"])
    assert annotate.get("continue-on-error") is True


def test_the_release_sbom_includes_the_sanitiser_lockfile() -> None:
    release = yaml.safe_load((WORKFLOWS / "release-android.yml").read_text())
    steps = [s for job in release["jobs"].values() for s in job["steps"]]
    sbom = next(s for s in steps if s.get("name") == "SBOM")
    assert f"file:{LOCKFILE}" in str(sbom["run"])
    upload = next(
        s for s in steps if "android-sbom-*.json" in str(s.get("with", {}).get("path"))
    )
    assert "image-sanitiser-sbom-*.json" in str(upload["with"]["path"])
