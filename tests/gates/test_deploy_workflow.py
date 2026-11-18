"""Ordering and identity properties of the deploy workflow.

The deploy workflow cannot be run from a pull request -- it needs AWS,
an approval and a real environment -- so the properties that make it
safe are asserted on its text instead. Each one is a defect that
shipped, or a control whose absence would be silent:

- **The image is tagged by the commit checked out** [OPS-9]. The
  workflow builds ``inputs.ref`` but tagged, skipped and recorded by
  ``github.sha``, the commit it was dispatched from. A rollback to an
  older ref then redeployed main's image, or pushed old code under
  main's SHA into an IMMUTABLE repository, where it can never be fixed.
- **A deploy is not an outage, and a failed one undoes itself** [OPS-6].
  The refresh launches before it terminates; the smoke goes through the
  public URL; a failure after the release was recorded restores the
  previous one.
- **No host can migrate before a named restore point exists** [OPS-7].
  The new host runs ``alembic upgrade head`` at boot, so the snapshot
  must be complete before the deployment state is written -- a failed
  snapshot then changes nothing.
"""

from __future__ import annotations

import fnmatch
import http.server
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import threading
import urllib.parse
from collections.abc import Iterator
from types import ModuleType

import pytest
import yaml

from app.api.html import HUB_PAGE_CSP
from app.hub.listings.shared import SLUG
from app.hub.public import render
from app.hub.public.settings import SITE_URL_ENV
from app.hub.public.views import HubSearchFilters, HubSearchPage

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"
ROLL = ROOT / "deploy" / "roll.sh"


def _without_comments(text: str) -> str:
    """Drop YAML and shell comment lines, so prose cannot trip a guard.

    :param text: Workflow source
    :return: The same text with whole-line comments removed
    """
    return "\n".join(
        line for line in text.split("\n") if not line.strip().startswith("#")
    )


def _steps(job: str) -> list[dict[str, object]]:
    """Return a job's steps, parsed.

    :param job: The job id
    :return: Its steps, in order
    """
    workflow = yaml.safe_load(DEPLOY.read_text())
    steps: list[dict[str, object]] = workflow["jobs"][job]["steps"]
    return steps


def test_the_dispatching_commit_never_names_the_artifact() -> None:
    code = _without_comments(DEPLOY.read_text())

    assert "github.sha" not in code
    assert "GITHUB_SHA" not in code


def test_every_job_checks_out_the_commit_the_plan_resolved() -> None:
    workflow = yaml.safe_load(DEPLOY.read_text())
    plan_steps = workflow["jobs"]["plan"]["steps"]
    resolve = [s for s in plan_steps if s.get("id") == "commit"]

    assert resolve, "the plan job no longer resolves the commit"
    assert "git rev-parse HEAD" in str(resolve[0]["run"])

    for name, job in workflow["jobs"].items():
        if name == "plan":
            continue
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("actions/checkout"):
                ref = step.get("with", {}).get("ref")
                assert ref == "${{ needs.plan.outputs.sha }}", (name, ref)


def test_the_guard_reads_real_steps() -> None:
    # Not vacuous: the release job exists and pushes by the plan's SHA.
    pushes = [
        s
        for s in _steps("release")
        if str(s.get("uses", "")).startswith("docker/build-push-action")
    ]

    assert pushes
    tags = str(pushes[0]["with"]["tags"])  # type: ignore[index]
    assert re.search(r"needs\.plan\.outputs\.sha", tags)


def test_the_refresh_launches_before_it_terminates() -> None:
    roll = ROLL.read_text()

    assert '"MinHealthyPercentage":100' in roll
    assert '"MaxHealthyPercentage":200' in roll
    assert 'MinHealthyPercentage":0' not in roll
    steps = _steps("release")
    runs = [str(s.get("run", "")) for s in steps]
    assert any("deploy/roll.sh" in r for r in runs)


def test_the_smoke_goes_through_the_public_url() -> None:
    smoke = [s for s in _steps("release") if s.get("id") == "smoke"]

    assert smoke, "the release job has no smoke step"
    run = str(smoke[0]["run"])
    assert "deploy/smoke.py" in run
    assert "/api-url" in run
    assert "127.0.0.1" not in run


def test_a_failed_release_is_rolled_back() -> None:
    steps = _steps("release")
    ids = [s.get("id") for s in steps]
    rollback = [s for s in steps if "Roll back" in str(s.get("name", ""))]

    assert len(rollback) == 1
    assert "failure()" in str(rollback[0]["if"])
    assert "steps.record.outcome" in str(rollback[0]["if"])
    # The previous release is captured before it is overwritten.
    assert ids.index("previous") < ids.index("record") < ids.index("roll")


def test_the_database_is_snapshotted_before_anything_can_migrate() -> None:
    steps = _steps("release")
    ids = [s.get("id") for s in steps]

    assert "snapshot" in ids
    assert ids.index("snapshot") < ids.index("record") < ids.index("roll")
    run = str(steps[ids.index("snapshot")]["run"])
    assert "create-db-snapshot" in run
    assert "wait db-snapshot-available" in run
    # A step that tolerated failure would let the deploy proceed with
    # no restore point, which is exactly the absence this exists for.
    assert not steps[ids.index("snapshot")].get("continue-on-error")


def test_every_environment_trusts_only_the_header_nginx_overwrites() -> None:
    # A production process refuses to start without this setting, and
    # staging must exercise the same path, so the deploy writes it into
    # the runtime env for every environment rather than per-environment
    # configuration that could differ.
    record = [s for s in _steps("release") if s.get("id") == "record"]

    assert record
    assert "SHIKKHOKPLUS_TRUSTED_CLIENT_IP_HEADER=X-Client-Address" in str(
        record[0]["run"]
    )


def test_production_is_gated_on_dependency_cves_before_anything_changes() -> None:
    # The blocking half of the two-speed CVE model [OPS-19]: in the plan
    # job, which every other job needs, so a blocked release has applied
    # no Terraform and pushed no image.
    steps = _steps("plan")
    gate = [s for s in steps if "deploy/cve_gate.py" in str(s.get("run", ""))]

    assert len(gate) == 1
    assert "production" in str(gate[0].get("if", ""))
    assert not gate[0].get("continue-on-error")
    assert ".security-exceptions.md" in str(gate[0]["run"])


# ---------------------------------------------------------------------------
# C-10: nothing is deployed that CI did not pass.
# ---------------------------------------------------------------------------

CHECK = ROOT / ".github" / "workflows" / "check.yml"
WORKFLOWS = ROOT / ".github" / "workflows"


def _first_index(steps: list[dict[str, object]], predicate: object) -> int:
    """Return the index of the first step a predicate accepts.

    :param steps: The steps
    :param predicate: A callable taking one step
    :return: The index
    """
    for index, step in enumerate(steps):
        if predicate(step):  # type: ignore[operator]
            return index
    raise AssertionError("no step matched")


def test_the_deploy_requires_every_check_job_to_have_passed() -> None:
    # The required names are compared with check.yml's real job names,
    # so a job renamed or added there cannot leave this asserting a
    # list nobody runs.
    check_jobs = yaml.safe_load(CHECK.read_text())["jobs"]
    names = {str(job.get("name", key)) for key, job in check_jobs.items()}

    steps = _steps("plan")
    evidence = [s for s in steps if "check-runs" in str(s.get("run", ""))]
    assert len(evidence) == 1
    required = set(str(evidence[0]["env"]["REQUIRED"]).split())  # type: ignore[index]
    assert required == names
    assert '"success"' in str(evidence[0]["run"])
    assert not evidence[0].get("continue-on-error")

    # Before any credential exists, so an unpassed commit touches nothing.
    first_credential = _first_index(
        steps,
        lambda s: "configure-aws-credentials" in str(s.get("uses", "")),
    )
    assert steps.index(evidence[0]) < first_credential


def test_production_deploys_only_a_commit_on_main() -> None:
    steps = _steps("plan")
    on_main = [s for s in steps if "compare/main..." in str(s.get("run", ""))]

    assert len(on_main) == 1
    assert "production" in str(on_main[0].get("if", ""))


def test_the_ref_never_reaches_a_shell_by_interpolation() -> None:
    workflow = yaml.safe_load(DEPLOY.read_text())
    for name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            assert "inputs.ref" not in str(step.get("run", "")), (
                name,
                step.get("name"),
            )


def test_check_runs_on_the_commit_that_lands_on_main() -> None:
    # Without it a squash commit on main has no check result, and the
    # deploy would refuse every commit on main.
    triggers = yaml.safe_load(CHECK.read_text())[True]  # YAML 1.1 reads `on` as True

    assert triggers["push"]["branches"] == ["main"]


# ---------------------------------------------------------------------------
# C-11: the plan exists, and is shown, before the approval that applies it.
# ---------------------------------------------------------------------------


def test_the_plan_is_made_before_the_infra_approval_and_applied_verbatim() -> None:
    workflow = yaml.safe_load(DEPLOY.read_text())
    assert workflow["defaults"]["run"]["shell"] == "bash", "pipefail is off"

    plan_runs = " ".join(str(s.get("run", "")) for s in _steps("plan"))
    assert "terraform plan" in plan_runs
    assert "-out=tfplan" in plan_runs
    assert "terraform apply" not in plan_runs

    infra = workflow["jobs"]["infrastructure"]
    assert infra["environment"] == "${{ inputs.environment }}-infra"
    infra_runs = " ".join(str(s.get("run", "")) for s in infra["steps"])
    assert "terraform plan" not in infra_runs
    assert "terraform apply -input=false tfplan" in infra_runs
    assert "sha256sum tfplan" in infra_runs
    assert "plan_sha256" in str(infra["steps"])


def test_the_state_region_matches_the_backend() -> None:
    versions = (ROOT / "infra" / "versions.tf").read_text()
    backend = re.search(r'backend "s3" \{(.*?)\n  \}', versions, re.DOTALL)
    assert backend is not None
    region = re.search(r'region\s*=\s*"([^"]+)"', backend.group(1))
    assert region is not None

    env = yaml.safe_load(DEPLOY.read_text())["env"]
    assert env["TF_STATE_REGION"] == region.group(1)


# ---------------------------------------------------------------------------
# C-12: an interrupted deploy is rolled back too, and the tag is written last.
# ---------------------------------------------------------------------------


def test_a_cancelled_release_is_rolled_back() -> None:
    rollback = [s for s in _steps("release") if "Roll back" in str(s.get("name", ""))]

    assert "cancelled()" in str(rollback[0]["if"])


def test_the_image_tag_is_written_after_the_runtime_env() -> None:
    record = [s for s in _steps("release") if s.get("id") == "record"]
    run = str(record[0]["run"])

    assert run.index("/runtime-env") < run.index("/image-tag")


def test_production_has_no_sms_fallbacks() -> None:
    # A placeholder hash passes the app's length check and a ceiling of
    # 50 passes its presence check, so a production fallback defeated
    # both [C-19]. The staging defaults sit in the branch after `else`.
    record = [s for s in _steps("release") if s.get("id") == "record"]
    run = str(record[0]["run"])
    production, _, staging = run.partition("else")

    assert ":-AAAAAAAAAAA" not in production
    assert ":-50" not in production
    assert ":-AAAAAAAAAAA" in staging


# ---------------------------------------------------------------------------
# C-32: every action is pinned, and no checkout leaves its token behind.
# ---------------------------------------------------------------------------


def _all_steps() -> list[tuple[str, dict[str, object]]]:
    """Every step of every workflow, with where it came from.

    :return: ``(workflow/job, step)`` pairs
    """
    found: list[tuple[str, dict[str, object]]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text())
        for name, job in workflow["jobs"].items():
            found.extend((f"{path.name}/{name}", step) for step in job.get("steps", []))
    return found


def test_every_action_is_pinned_to_a_commit() -> None:
    steps = _all_steps()
    uses = [(where, str(s["uses"])) for where, s in steps if "uses" in s]
    assert len(uses) > 10, "the parser found almost no actions"

    loose = [
        (where, use)
        for where, use in uses
        if not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", use)
    ]
    assert loose == [], (
        f"{loose}: a tag can be re-pointed at new code; a commit cannot. "
        "Pin the full SHA with the version in a trailing comment."
    )


def test_every_version_comment_names_a_version() -> None:
    lines = [
        line
        for path in WORKFLOWS.glob("*.yml")
        for line in path.read_text().splitlines()
        if re.search(r"uses:\s*\S+@[0-9a-f]{40}", line)
    ]

    assert lines
    assert all(re.search(r"# v\d+\.\d+\.\d+\s*$", line) for line in lines), [
        line for line in lines if not re.search(r"# v\d+\.\d+\.\d+\s*$", line)
    ]


def test_no_checkout_persists_its_credentials() -> None:
    checkouts = [
        (where, step)
        for where, step in _all_steps()
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert checkouts

    persisted = [
        where
        for where, step in checkouts
        if (step.get("with") or {}).get("persist-credentials") is not False  # type: ignore[union-attr]
    ]
    assert persisted == [], f"{persisted}: no job here pushes with git"


# ---------------------------------------------------------------------------
# ARC-7: the keyring is checked for the shape the application boots on.
# ---------------------------------------------------------------------------

#: A secret long enough for the application's 32-byte floor.
_LONG = "s" * 32


def _keyring_step() -> dict[str, object]:
    """Return the plan job's keyring check.

    :return: The step
    """
    named = [s for s in _steps("plan") if s.get("name") == "Check the signing keyring"]
    assert len(named) == 1
    return named[0]


def _keyring_env() -> dict[str, str]:
    """Return the keyring step's declared environment.

    :return: Variable name to value
    """
    declared = _keyring_step()["env"]
    assert isinstance(declared, dict)
    return {str(name): str(value) for name, value in declared.items()}


def _run_keyring_check(keys: str) -> subprocess.CompletedProcess[str]:
    """Run the step's script as Actions runs it, against one keyring.

    :param keys: The value of the secret
    :return: The finished process
    """
    env = _keyring_env()
    env.update({"JWT_KEYS": keys, "PATH": os.environ["PATH"]})
    return subprocess.run(  # noqa: S603 -- a fixed interpreter and our own script
        [  # noqa: S607 -- bash from PATH, as the runner finds it
            "bash",
            "--noprofile",
            "--norc",
            "-eo",
            "pipefail",
            "-c",
            str(_keyring_step()["run"]),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.mark.parametrize(
    "keys",
    [f"k1:{_LONG}", f"k0:{_LONG}x, k1 : {_LONG}y ,"],
    ids=["one-key", "rotation-with-spaces"],
)
def test_a_keyring_the_application_boots_on_passes(keys: str) -> None:
    """A well-formed keyring holding the active kid is accepted.

    :param keys: The secret's value
    :return: None
    """
    finished = _run_keyring_check(keys)

    assert finished.returncode == 0, finished.stdout + finished.stderr


@pytest.mark.parametrize(
    "keys",
    [
        "",
        _LONG,
        f"k1{_LONG}",
        f":{_LONG}",
        "k1:",
        f"k1:{_LONG[:31]}",
        f"k2:{_LONG}",
        f"k1:{_LONG},k2",
    ],
    ids=[
        "empty",
        "no-colon",
        "no-colon-prefixed",
        "no-kid",
        "no-secret",
        "short-key",
        "active-kid-absent",
        "second-entry-malformed",
    ],
)
def test_a_keyring_the_application_would_refuse_fails_the_preflight(
    keys: str,
) -> None:
    """Each refusal the application would make at boot is made here first.

    The output never carries key material: each problem names an entry
    by position or a key by its id.

    :param keys: The secret's value
    :return: None
    """
    finished = _run_keyring_check(keys)

    assert finished.returncode != 0
    output = finished.stdout + finished.stderr
    assert "::error::" in output
    assert _LONG[:31] not in output


@pytest.mark.parametrize(
    "keys",
    [
        f"k1:{_LONG}",
        f"k0:{_LONG}x, k1 : {_LONG}y ,",
        _LONG,
        f":{_LONG}",
        "k1:",
        f"k1:{_LONG[:31]}",
        f"k2:{_LONG}",
        f"k1:{_LONG},k2",
        f"k1:{_LONG},,",
    ],
)
def test_the_preflight_agrees_with_the_application(
    keys: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The preflight refuses exactly the keyrings the application refuses.

    :param keys: The secret's value
    :param monkeypatch: The patcher
    :return: None
    """
    from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, keyring_problem

    monkeypatch.setenv(JWT_KEYS_ENV, keys)
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, _keyring_env()["JWT_ACTIVE_KID"])

    boots = keyring_problem() is None
    passes = _run_keyring_check(keys).returncode == 0

    assert passes == boots


def test_the_preflight_checks_the_kid_the_release_writes() -> None:
    """The kid the env file activates is the one the keyring must hold.

    :return: None
    """
    record = [s for s in _steps("release") if s.get("id") == "record"]
    written = re.findall(r"SHIKKHOKPLUS_JWT_ACTIVE_KID=(\w+)", str(record[0]["run"]))

    assert written == [_keyring_env()["JWT_ACTIVE_KID"]]


# ---------------------------------------------------------------------------
# The public hub's stylesheet [H2]. The site build ships it under
# hub-assets/, but the pages that link it are rendered by the API, which
# deploys separately and is cached at the edge for up to ten minutes. The
# site's prune may therefore never delete a hub-assets/ key: a page still
# linking the previous name would lose its styling.
# ---------------------------------------------------------------------------

#: A stand-in ``aws`` that logs every call and lists the given bucket keys.
_FAKE_AWS = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$AWS_LOG"
if [ "$1 $2" = "s3api list-objects-v2" ]; then
  printf '%s' "$BUCKET_KEYS"
fi
"""


def _site_step(name: str) -> dict[str, object]:
    """Return one named step of the site job.

    :param name: The step's name
    :return: The step
    """
    named = [s for s in _steps("site") if s.get("name") == name]
    assert len(named) == 1, name
    return named[0]


def _run_site_step(
    name: str, tmp_path: pathlib.Path, dist: list[str], bucket: list[str]
) -> list[str]:
    """Run a site step's script against a fake bucket, as Actions runs it.

    :param name: The step's name
    :param tmp_path: A scratch directory
    :param dist: The files the new build holds, relative to ``site/dist``
    :param bucket: The keys the bucket holds before the step
    :return: Each ``aws`` invocation, one argument string per call
    """
    built = tmp_path / "dist"
    for rel in dist:
        (built / rel).parent.mkdir(parents=True, exist_ok=True)
        (built / rel).write_text("x")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "aws"
    fake.write_text(_FAKE_AWS)
    fake.chmod(0o755)
    log = tmp_path / "aws.log"
    log.write_text("")
    result = subprocess.run(  # noqa: S603 -- a fixed interpreter and our own script
        [  # noqa: S607 -- bash from PATH, as the runner finds it
            "bash",
            "--noprofile",
            "--norc",
            "-eo",
            "pipefail",
            "-c",
            str(_site_step(name)["run"]),
        ],
        cwd=built,
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "BUCKET": "site-bucket",
            "AWS_LOG": str(log),
            "BUCKET_KEYS": "\t".join(bucket),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return log.read_text().splitlines()


def test_the_site_prune_keeps_every_hub_stylesheet(tmp_path: pathlib.Path) -> None:
    """Old hub stylesheets survive the prune; other stale keys do not.

    :param tmp_path: A scratch directory
    :return: None
    """
    calls = _run_site_step(
        "Prune old files",
        tmp_path,
        dist=["index.html", "assets/site.new.css", "hub-assets/hub.000000000002.css"],
        bucket=[
            "index.html",
            "assets/site.new.css",
            "assets/site.old.css",
            "hub-assets/hub.000000000001.css",
            "hub-assets/hub.000000000002.css",
        ],
    )
    removed = [call for call in calls if call.startswith("s3 rm ")]

    assert removed == ["s3 rm s3://site-bucket/assets/site.old.css --only-show-errors"]


def test_the_site_upload_ships_the_hub_stylesheet_immutable(
    tmp_path: pathlib.Path,
) -> None:
    """hub-assets/ is uploaded as CSS, cached for a year and immutable.

    :param tmp_path: A scratch directory
    :return: None
    """
    calls = _run_site_step(
        "Upload",
        tmp_path,
        dist=["index.html", "hub-assets/hub.000000000002.css"],
        bucket=[],
    )
    hub = [call for call in calls if "s3://site-bucket/hub-assets/" in call]

    assert hub == [
        "s3 cp hub-assets s3://site-bucket/hub-assets/ --recursive "
        "--only-show-errors --exclude * --include *.css "
        "--content-type text/css; charset=utf-8 "
        "--cache-control public, max-age=31536000, immutable"
    ]


# ---------------------------------------------------------------------------
# Android App Links [H2 task 9]. The "Report this page" link on a hub page
# opens /ui/hub-report on the web-app host, and the app's intent filter
# claims that path with autoVerify. Android verifies the claim by fetching
# /.well-known/assetlinks.json from the same host -- which is the API's
# distribution, so the file lives at the web bucket's root, beside ui/.
# Each link below is exercised for real only by a deploy against AWS and a
# phone, so each is asserted here.
# ---------------------------------------------------------------------------

CDN_MAIN = ROOT / "infra" / "modules" / "cdn" / "main.tf"
CDN_WEB = ROOT / "infra" / "modules" / "cdn" / "web.tf"
DEPLOY_ROLE = ROOT / "infra" / "bootstrap" / "deploy_role.tf"

#: The one path Android fetches to verify an App Link.
_ASSETLINKS = "/.well-known/assetlinks.json"

#: The web job's two app-links steps: validate and build, then copy.
_BUILD_STEP = "Build the Android app-links file"
_PUBLISH_STEP = "Publish the Android app-links file"

#: A well-formed SHA-256 certificate fingerprint, as keytool prints it.
_FINGERPRINT = ":".join(["AB"] * 31 + ["0F"])

#: A stand-in ``aws``: answers the SSM read and keeps what ``s3 cp`` sends.
_FAKE_AWS_SSM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$AWS_LOG"
if [ "$1 $2" = "ssm get-parameter" ]; then
  [ "$PARAM_STATE" = "missing" ] && { echo "ParameterNotFound" >&2; exit 254; }
  printf '%s\\n' "$PARAM_VALUE"
fi
if [ "$1 $2" = "s3 cp" ]; then
  cp "$3" "$CAPTURE"
fi
"""


def _web_step(name: str) -> dict[str, object]:
    """Return one named step of the web job.

    :param name: The step's name
    :return: The step
    """
    named = [s for s in _steps("web") if s.get("name") == name]
    assert len(named) == 1, name
    return named[0]


def _run_assetlinks_step(
    tmp_path: pathlib.Path, value: str, state: str = "set"
) -> tuple[subprocess.CompletedProcess[str], list[str], pathlib.Path]:
    """Run the app-links steps as Actions runs them, against a fake AWS.

    The build step runs first; the publish step only when it succeeded,
    as Actions would (Upload sits between them).

    :param tmp_path: A scratch directory
    :param value: What SSM holds for ``android-cert-sha256``
    :param state: ``set``, or ``missing`` for a parameter that does not exist
    :return: The last finished process, each ``aws`` call, and the uploaded file
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "aws"
    fake.write_text(_FAKE_AWS_SSM)
    fake.chmod(0o755)
    log = tmp_path / "aws.log"
    log.write_text("")
    capture = tmp_path / "uploaded.json"
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "BUCKET": "web-bucket",
        "ENVIRONMENT": "staging",
        "RUNNER_TEMP": str(tmp_path),
        "AWS_LOG": str(log),
        "CAPTURE": str(capture),
        "PARAM_VALUE": value,
        "PARAM_STATE": state,
    }
    for name in (_BUILD_STEP, _PUBLISH_STEP):
        finished = subprocess.run(  # noqa: S603 -- a fixed interpreter and our own script
            [  # noqa: S607 -- bash from PATH, as the runner finds it
                "bash",
                "--noprofile",
                "--norc",
                "-eo",
                "pipefail",
                "-c",
                str(_web_step(name)["run"]),
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if finished.returncode != 0:
            break
    return finished, log.read_text().splitlines(), capture


def test_deploy_writes_assetlinks_with_package_and_fingerprint(
    tmp_path: pathlib.Path,
) -> None:
    """The uploaded file names the app's package and the SSM fingerprint.

    :param tmp_path: A scratch directory
    :return: None
    """
    finished, calls, uploaded = _run_assetlinks_step(tmp_path, _FINGERPRINT.lower())

    assert finished.returncode == 0, finished.stdout + finished.stderr
    reads = [c for c in calls if c.startswith("ssm get-parameter")]
    assert reads == [
        "ssm get-parameter --name /shikkhokplus/shikkhokplus-staging/"
        "android-cert-sha256 --query Parameter.Value --output text"
    ]
    assert json.loads(uploaded.read_text()) == [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": "com.shikkhokplus.app",
                "sha256_cert_fingerprints": [_FINGERPRINT],
            },
        }
    ]
    uploads = [c for c in calls if c.startswith("s3 cp ")]
    assert len(uploads) == 1
    assert uploads[0].endswith(
        "s3://web-bucket/.well-known/assetlinks.json --only-show-errors "
        "--content-type application/json --cache-control max-age=3600"
    )


def test_deploy_lists_every_fingerprint_the_parameter_holds(
    tmp_path: pathlib.Path,
) -> None:
    """Play's app-signing key and the upload key can both be listed.

    :param tmp_path: A scratch directory
    :return: None
    """
    other = ":".join(["12"] * 32)
    finished, _, uploaded = _run_assetlinks_step(tmp_path, f"{_FINGERPRINT}, {other}")

    assert finished.returncode == 0, finished.stdout + finished.stderr
    target = json.loads(uploaded.read_text())[0]["target"]
    assert target["sha256_cert_fingerprints"] == [_FINGERPRINT, other]


@pytest.mark.parametrize(
    ("value", "state"),
    [
        ("", "missing"),
        ("", "set"),
        ("None", "set"),
        ("AB:CD", "set"),
        (f"{_FINGERPRINT},", "set"),
        (_FINGERPRINT.replace("AB", "XY", 1), "set"),
    ],
    ids=["unset", "empty", "none", "short", "trailing-comma", "not-hex"],
)
def test_deploy_refuses_assetlinks_without_a_fingerprint(
    tmp_path: pathlib.Path, value: str, state: str
) -> None:
    """An unset or malformed parameter fails the step and uploads nothing.

    A file naming no valid fingerprint would publish, verify nothing, and
    leave every report link opening the browser with nothing reporting why.

    :param tmp_path: A scratch directory
    :param value: What SSM holds
    :param state: Whether the parameter exists
    :return: None
    """
    finished, calls, uploaded = _run_assetlinks_step(tmp_path, value, state)

    assert finished.returncode != 0
    output = finished.stdout + finished.stderr
    assert "::error::" in output
    # Both manual steps, so the run says how to fix it rather than what broke.
    assert "android-cert-sha256" in output
    assert "infra/bootstrap" in output
    assert not [c for c in calls if c.startswith("s3 ")]
    assert not uploaded.exists()


def test_the_fingerprint_is_validated_before_the_web_release_goes_live() -> None:
    """A bad parameter fails the job before Upload changes anything.

    Upload syncs the new index.html and prunes old assets, so a failure
    after it would leave a red deploy whose new build is live and never
    smoked. Only the copy of the already-built file follows Upload, and the
    file is invalidated with the rest.

    :return: None
    """
    names = [s.get("name") for s in _steps("web")]

    assert (
        names.index("Resolve where it goes")
        < names.index(_BUILD_STEP)
        < names.index("Upload")
        < names.index(_PUBLISH_STEP)
        < names.index("Invalidate")
    )
    assert "ssm" not in str(_web_step(_PUBLISH_STEP)["run"])
    assert _web_step(_PUBLISH_STEP)["env"] == {
        "BUCKET": "${{ steps.target.outputs.bucket }}"
    }
    assert f'"{_ASSETLINKS}"' in str(_web_step("Invalidate")["run"])


def _behaviours(text: str) -> list[dict[str, object]]:
    """Read each ordered behaviour of the API distribution, in order.

    A ``dynamic`` block contributes one behaviour per ``for_each`` value.

    :param text: ``infra/modules/cdn/main.tf``
    :return: Per behaviour: its path, origin, methods, cache policy and
        whether a viewer function is attached
    """
    start = text.index('resource "aws_cloudfront_distribution" "api"')
    body = text[start:]
    found: list[dict[str, object]] = []
    for match in re.finditer(
        r'(dynamic "ordered_cache_behavior"|ordered_cache_behavior) \{', body
    ):
        depth, end = 0, match.end() - 1
        for end in range(match.end() - 1, len(body)):
            depth += {"{": 1, "}": -1}.get(body[end], 0)
            if depth == 0:
                break
        block = _without_comments(body[match.start() : end])
        if match.group(1).startswith("dynamic"):
            each = re.search(r"for_each\s*=\s*\[([^\]]*)\]", block)
            assert each is not None
            paths = re.findall(r'"([^"]+)"', each.group(1))
        else:
            paths = re.findall(r'path_pattern\s*=\s*"([^"]+)"', block)
        methods = re.search(r"allowed_methods\s*=\s*\[([^\]]*)\]", block)
        assert methods is not None
        policy = re.search(r"cache_policy_id\s*=\s*(\S+)", block)
        assert policy is not None
        origin = re.search(r'target_origin_id\s*=\s*"([^"]+)"', block)
        assert origin is not None
        found += [
            {
                "path": path,
                "origin": origin.group(1),
                "methods": re.findall(r'"([A-Z]+)"', methods.group(1)),
                "policy": policy.group(1),
                "function": "function_association" in block,
            }
            for path in paths
        ]
    return found


def test_cdn_routes_assetlinks_to_web_origin() -> None:
    """Exactly the file's path goes to the bucket, ahead of any wider match.

    CloudFront takes the first behaviour whose pattern matches, so no
    earlier pattern may also match the path, or that one would answer.

    :return: None
    """
    behaviours = _behaviours(CDN_MAIN.read_text())
    paths = [b["path"] for b in behaviours]
    # Guards the parse: a walk finding nothing would pass vacuously.
    assert {"/v1/admin*", "/hub*", "/ui", "/ui/*"} <= set(paths), paths

    ours = [b for b in behaviours if b["path"] == _ASSETLINKS]
    assert ours == [
        {
            "path": _ASSETLINKS,
            "origin": "shikkhokplus-web",
            "methods": ["GET", "HEAD"],
            "policy": "data.aws_cloudfront_cache_policy.optimized.id",
            "function": False,
        }
    ]
    earlier = paths[: paths.index(_ASSETLINKS)]
    assert not [p for p in earlier if fnmatch.fnmatchcase(_ASSETLINKS, str(p))]


def test_the_web_bucket_lets_cloudfront_read_assetlinks() -> None:
    """The bucket policy admits the distribution to the file, not the root.

    :return: None
    """
    text = CDN_WEB.read_text()
    statement = text[text.index('Sid       = "CloudFrontReadsTheWebClient"') :]
    statement = statement[: statement.index("},\n      {")]

    assert f'"${{aws_s3_bucket.web.arn}}{_ASSETLINKS}"' in statement
    assert '"${aws_s3_bucket.web.arn}/*"' not in statement


def test_the_deploy_role_may_publish_assetlinks() -> None:
    """The role reads the fingerprint and writes exactly the one file.

    :return: None
    """
    text = DEPLOY_ROLE.read_text()
    urls = text[text.index('Sid    = "PublicUrl"') :]
    urls = urls[: urls.index("Sid", 1)]
    objects = text[text.index('Sid    = "WebBucketObjects"') :]
    objects = objects[: objects.index("Sid", 1)]

    assert '"android-cert-sha256"' in urls
    assert f'"arn:aws:s3:::shikkhokplus-${{each.key}}-web-*{_ASSETLINKS}"' in objects


def test_the_web_build_names_the_site_the_release_read() -> None:
    """The web client is built with the public site's origin [H2 task 10].

    "View public page" links there and the page's CSP adds it to
    ``style-src`` for the hub preview's stylesheet, so the value is baked
    in at build time. It is the same ``site-url`` parameter the release
    already reads for the API's runtime env, handed over as a job output,
    so the web build keeps running before the web job holds AWS
    credentials.

    :return: None
    """
    workflow = yaml.safe_load(DEPLOY.read_text())
    release = workflow["jobs"]["release"]
    record = [s for s in release["steps"] if s.get("id") == "record"]
    build = _web_step("Check and build for /ui/")
    names = [s.get("name") for s in _steps("web")]

    assert release["outputs"]["site_url"] == "${{ steps.record.outputs.site_url }}"
    assert 'echo "site_url=${SITE_URL}" >> "$GITHUB_OUTPUT"' in str(record[0]["run"])
    assert "release" in workflow["jobs"]["web"]["needs"]
    assert build["env"] == {
        "WEB_BASE": "/ui/",
        "VITE_SITE_URL": "${{ needs.release.outputs.site_url }}",
        # The photo bucket's endpoint, for the CSP [H3 task 2].
        "VITE_MEDIA_ORIGIN": "${{ needs.release.outputs.media_origin }}",
    }
    credentials = [
        i
        for i, step in enumerate(_steps("web"))
        if "configure-aws-credentials" in str(step.get("uses"))
    ]
    assert names.index("Check and build for /ui/") < credentials[0]


# ---------------------------------------------------------------------------
# The public hub, smoked after the API and the site have both shipped
# [H2 task 11]. The pages are rendered by the API and served only through
# the site's distribution, so neither the API smoke nor the site smoke
# reaches them. CloudFront answers a hub 404 -- and a 403 -- with the
# site's own 404 page, so an origin-secret mismatch reads as a missing
# page: the smoke must see a 200 carrying the hub's own CSP before it can
# call anything else a pass [R9].
# ---------------------------------------------------------------------------

COMPOSE_STAGING = ROOT / "deploy" / "docker-compose.staging.yml"


def _load_smoke() -> ModuleType:
    """Import ``deploy/smoke.py``, which is a script rather than a package.

    :return: The module
    """
    spec = importlib.util.spec_from_file_location(
        "smoke_for_hub", ROOT / "deploy" / "smoke.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke = _load_smoke()

#: The site's own policy, which a page served from the bucket carries.
_SITE_CSP = "default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'"


def _landing_page() -> str:
    """Render the real, empty ``/hub/en`` landing page.

    :return: The HTML the API would send
    """
    view = HubSearchPage(
        query=None,
        filters=HubSearchFilters(district=None, upazila=None, subject=None, level=None),
        districts=[],
        upazilas=[],
        cities=[],
        results=[],
        page=1,
        pages=1,
        total=0,
    )
    return render.page(view, "search.html", "en")


class _HubHost(http.server.BaseHTTPRequestHandler):
    """The site host (or, with ``server.api``, the API host).

    ``server.behaviour`` names the one thing that is broken.
    """

    def log_message(self, format: str, *args: object) -> None:
        """Stay quiet.

        :param format: Unused
        :param args: Unused
        :return: None
        """

    def _send(
        self, status: int, body: str, csp: str = HUB_PAGE_CSP, kind: str = "text/html"
    ) -> None:
        """Write one answer.

        :param status: The HTTP status
        :param body: The body
        :param csp: The Content-Security-Policy header
        :param kind: The Content-Type
        :return: None
        """
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Security-Policy", csp)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        """Answer as the site distribution, or the API's, would.

        :return: None
        """
        behaviour = self.server.behaviour  # type: ignore[attr-defined]
        url = urllib.parse.urlsplit(self.path)
        if self.server.api:  # type: ignore[attr-defined]
            # The API distribution's hub-block function.
            if url.path.startswith("/hub") and behaviour != "api-serves-hub":
                self._send(404, "not found", csp=_SITE_CSP)
            else:
                self._send(200, _landing_page())
            return
        site = self.server.origin  # type: ignore[attr-defined]
        absent = f"/hub/en/t/{smoke.ABSENT_SLUG}"
        if url.path == "/hub/en" and url.query:
            if behaviour == "query-passed":
                self._send(200, _landing_page())
            else:
                self._send(400, "Bad Request", csp=_SITE_CSP)
        elif url.path == "/hub/en":
            page = _landing_page()
            if behaviour == "origin-refused":
                self._send(404, "<h1>Page not found</h1>", csp=_SITE_CSP)
            elif behaviour == "site-csp":
                self._send(200, page, csp=_SITE_CSP)
            elif behaviour == "localhost-canonical":
                self._send(200, page.replace(site, "http://localhost"))
            else:
                self._send(200, page)
        elif url.path == "/hub/sitemap.xml" and behaviour != "no-sitemap":
            self._send(200, "<urlset/>", kind="application/xml")
        elif url.path == absent and behaviour == "soft-404":
            self._send(200, _landing_page())
        elif url.path == render.STYLESHEET_PATH and behaviour != "no-stylesheet":
            self._send(200, "body{}", csp=_SITE_CSP, kind="text/css; charset=utf-8")
        else:
            self._send(404, "<h1>Page not found</h1>", csp=_SITE_CSP)


def _serve(behaviour: str, *, api: bool) -> http.server.ThreadingHTTPServer:
    """Bind one stand-in host on a free local port, not yet serving.

    :param behaviour: What is broken
    :param api: True for the API host, False for the site host
    :return: The server
    """
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _HubHost)
    server.behaviour = behaviour  # type: ignore[attr-defined]
    server.api = api  # type: ignore[attr-defined]
    server.origin = f"http://127.0.0.1:{server.server_address[1]}"  # type: ignore[attr-defined]
    return server


@pytest.fixture
def hub(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[str, str]]:
    """Serve a stand-in site host and API host.

    The landing page is the real render, with the site's origin as
    ``SHIKKHOKPLUS_SITE_URL``, as the deploy sets it.

    :param request: Carries the behaviour to break, via indirect params
    :param monkeypatch: Sets the site origin for the renderer
    :return: A context manager yielding the site and API base URLs
    """
    behaviour = getattr(request, "param", "ok")
    servers = [_serve(behaviour, api=False), _serve(behaviour, api=True)]
    monkeypatch.setenv(SITE_URL_ENV, servers[0].origin)  # type: ignore[attr-defined]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield servers[0].origin, servers[1].origin + "/"  # type: ignore[attr-defined]
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def test_a_working_hub_passes_the_smoke(hub: tuple[str, str]) -> None:
    site, api = hub

    outcome = smoke.smoke_hub(site + "/", api, attempts=1, interval=0)

    assert outcome == (
        f"the hub answers at {site}/hub/en with its own CSP, the sitemap, "
        "the stylesheet, a 400 for an unknown query key and a 404 for an "
        "unknown teacher, and the API host refuses it"
    )


@pytest.mark.parametrize(
    ("hub", "reason"),
    [
        ("origin-refused", r"/hub/en answered 404"),
        ("site-csp", r"Content-Security-Policy"),
        ("localhost-canonical", r"canonical"),
        ("no-stylesheet", r"stylesheet .* answered 404"),
        ("no-sitemap", r"/hub/sitemap.xml answered 404"),
        ("query-passed", r"\?utm=x answered 200, not 400"),
        ("soft-404", r"no_such_teacher answered 200, not 404"),
        ("api-serves-hub", r"API host's .*/hub/en answered 200, not 404"),
    ],
    indirect=["hub"],
)
def test_a_broken_hub_fails_the_smoke(hub: tuple[str, str], reason: str) -> None:
    site, api = hub

    with pytest.raises(RuntimeError, match=reason):
        smoke.smoke_hub(site, api, attempts=1, interval=0)


def test_the_hub_smoke_expects_the_policy_the_api_sends() -> None:
    # smoke.py imports nothing from app/ (it runs on a bare runner), so
    # its copy of the policy is held to the API's here.
    assert smoke.HUB_PAGE_CSP == HUB_PAGE_CSP


def test_the_absent_teacher_can_never_be_a_listing() -> None:
    # Outside the slug pattern, so no publish can ever make it a 200.
    assert not SLUG.fullmatch(smoke.ABSENT_SLUG)


def test_deploy_smokes_hub_routes() -> None:
    """A job after the release and the site smokes the hub through both.

    The URLs come from the two jobs as outputs, so the hub job holds no
    AWS credentials, and reach the shell through the environment.

    :return: None
    """
    workflow = yaml.safe_load(DEPLOY.read_text())
    jobs = workflow["jobs"]
    hub_job = jobs["hub"]
    runs = [s for s in hub_job["steps"] if "deploy/smoke.py" in str(s.get("run", ""))]

    assert {"plan", "release", "site"} <= set(hub_job["needs"])
    assert len(runs) == 1
    run = str(runs[0]["run"])
    assert re.search(r'deploy/smoke\.py "\$SITE_URL" --hub --api-url "\$API_URL"', run)
    assert "${{" not in run
    assert runs[0]["env"] == {
        "SITE_URL": "${{ needs.site.outputs.url }}",
        "API_URL": "${{ needs.release.outputs.api_url }}",
    }
    assert not any(
        "configure-aws-credentials" in str(s.get("uses")) for s in hub_job["steps"]
    )

    assert jobs["site"]["outputs"]["url"] == "${{ steps.target.outputs.url }}"
    assert jobs["release"]["outputs"]["api_url"] == "${{ steps.smoke.outputs.api_url }}"
    smoke_step = next(s for s in _steps("release") if s.get("id") == "smoke")
    assert 'echo "api_url=${url}" >> "$GITHUB_OUTPUT"' in str(smoke_step["run"])


# ---------------------------------------------------------------------------
# The two origins the hub's pages are built from reach the container [R1]:
# the public site (canonical, hreflang, sitemap) and the web app (the
# report link, at /ui/hub-report). The release step is run here against a
# stand-in ``aws`` and the runtime env it would store is read back.
# ---------------------------------------------------------------------------

#: A stand-in ``aws``: answers each SSM read from ``$PARAMS/<name>`` and
#: keeps what a ``put-parameter --value file://...`` stores.
_FAKE_AWS_RECORD = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$AWS_LOG"
name="" value="" prev=""
for arg in "$@"; do
  [ "$prev" = "--name" ] && name="$arg"
  [ "$prev" = "--value" ] && value="$arg"
  prev="$arg"
done
key="${name##*/}"
if [ "$1 $2" = "ssm get-parameter" ]; then
  [ -f "$PARAMS/$key" ] || { echo "ParameterNotFound" >&2; exit 254; }
  cat "$PARAMS/$key"
fi
if [ "$1 $2" = "ssm put-parameter" ] && [ "${value#file://}" != "$value" ]; then
  cp "${value#file://}" "$CAPTURE/$key"
fi
"""

#: What SSM holds for every parameter the record step reads.
_RECORD_PARAMS = {
    "admin-edge-secret": "A" * 40,
    "ses-smtp-username": "AKIA" + "B" * 16,
    "ses-smtp-password": "c" * 44,
    "email-from": "ShikkhokPlus <codes@example.test>",
    "ses-configuration-set": "shikkhokplus-staging",
    "ses-smtp-host": "email-smtp.us-east-1.amazonaws.com",
    "site-url": "https://site.example.test",
    "web-url": "https://app.example.test/ui/",
    "media-bucket": "shikkhokplus-staging-media-123456789012",
    "media-bucket-domain": (
        "shikkhokplus-staging-media-123456789012.s3.us-east-1.amazonaws.com"
    ),
}


def _run_record_step(
    tmp_path: pathlib.Path, **overrides: str | None
) -> tuple[subprocess.CompletedProcess[str], list[str], dict[str, str]]:
    """Run the release's record step against a stand-in SSM.

    :param tmp_path: A scratch directory
    :param overrides: Parameter values to replace; None removes one
    :return: The process, each ``aws`` call, and the stored runtime env
    """
    params = tmp_path / "params"
    capture = tmp_path / "capture"
    bin_dir = tmp_path / "bin"
    for directory in (params, capture, bin_dir):
        directory.mkdir()
    for key, value in {**_RECORD_PARAMS, **overrides}.items():
        if value is not None:
            (params / key).write_text(value + "\n")
    fake = bin_dir / "aws"
    fake.write_text(_FAKE_AWS_RECORD)
    fake.chmod(0o755)
    log = tmp_path / "aws.log"
    log.write_text("")
    output = tmp_path / "github-output"
    record = next(s for s in _steps("release") if s.get("id") == "record")
    finished = subprocess.run(  # noqa: S603 -- a fixed interpreter and our own script
        [  # noqa: S607 -- bash from PATH, as the runner finds it
            "bash",
            "--noprofile",
            "--norc",
            "-eo",
            "pipefail",
            "-c",
            str(record["run"]),
        ],
        cwd=tmp_path,
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "ENVIRONMENT": "staging",
            "SHA": "0" * 40,
            "GITHUB_OUTPUT": str(output),
            "AWS_LOG": str(log),
            "PARAMS": str(params),
            "CAPTURE": str(capture),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    stored = capture / "runtime-env"
    runtime: dict[str, str] = {}
    if stored.exists():
        for line in stored.read_text().splitlines():
            key, _, value = line.partition("=")
            runtime[key] = value
    return finished, log.read_text().splitlines(), runtime


@pytest.mark.parametrize(
    ("web_url", "origin"),
    [
        ("https://app.example.test/ui/", "https://app.example.test"),
        # A web client with no hostname of its own is served by the API's.
        ("https://api.example.test/ui/", "https://api.example.test"),
    ],
)
def test_the_container_gets_the_site_and_web_app_origins(
    tmp_path: pathlib.Path, web_url: str, origin: str
) -> None:
    finished, _, runtime = _run_record_step(tmp_path, **{"web-url": web_url})

    assert finished.returncode == 0, finished.stdout + finished.stderr
    assert runtime["SHIKKHOKPLUS_SITE_URL"] == "https://site.example.test"
    assert runtime["SHIKKHOKPLUS_WEB_APP_URL"] == origin


@pytest.mark.parametrize(
    "web_url",
    [None, "http://app.example.test/ui/", "None"],
    ids=["unset", "plain-http", "aws-prints-None"],
)
def test_no_web_app_origin_stops_the_release_before_anything_is_written(
    tmp_path: pathlib.Path, web_url: str | None
) -> None:
    finished, calls, runtime = _run_record_step(tmp_path, **{"web-url": web_url})

    assert finished.returncode != 0
    assert "web-url" in finished.stdout
    assert not [c for c in calls if c.startswith("ssm put-parameter")]
    assert runtime == {}


@pytest.mark.parametrize("name", ["SHIKKHOKPLUS_SITE_URL", "SHIKKHOKPLUS_WEB_APP_URL"])
def test_compose_hands_both_origins_to_the_container(name: str) -> None:
    document = yaml.safe_load(COMPOSE_STAGING.read_text())

    for service in ("api", "migrate"):
        environment = document["services"][service]["environment"]
        assert environment[name] == f"${{{name}:-}}", service


# ---------------------------------------------------------------------------
# The hub's three scheduled jobs (badge refresh, demand question, edge
# invalidation sender) are cron entries the boot script writes. They reach
# a host only when one boots from the new launch template, so the deploy
# that ships their code must also replace the host: the release waits for
# the apply, and rolls the group, whose template is $Latest, every time.
# ---------------------------------------------------------------------------


def test_every_deploy_boots_a_host_from_the_applied_template() -> None:
    workflow = yaml.safe_load(DEPLOY.read_text())
    roll = [s for s in _steps("release") if s.get("id") == "roll"]
    asg = (ROOT / "infra" / "modules" / "app" / "main.tf").read_text()

    assert "infrastructure" in workflow["jobs"]["release"]["needs"]
    assert "if" not in workflow["jobs"]["release"]
    assert len(roll) == 1
    assert "if" not in roll[0]
    assert "deploy/roll.sh" in str(roll[0]["run"])
    assert re.search(
        r"launch_template\s*\{\s*id\s*=\s*aws_launch_template\.app\.id\s*"
        r'version\s*=\s*"\$Latest"',
        asg,
    )


def test_bootstrap_creates_the_parameter_the_web_deploy_reads() -> None:
    """``infra/bootstrap`` writes the App Link fingerprint where deploy reads it.

    The web deploy reads ``/shikkhokplus/shikkhokplus-${ENVIRONMENT}/
    android-cert-sha256`` in its AWS_REGION and fails without it. Bootstrap
    creates it from ``android_cert_sha256``, so the two names and the region
    must agree or the parameter lands where nothing looks.
    """
    tf = (ROOT / "infra" / "bootstrap" / "android_app_links.tf").read_text()
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    region = yaml.safe_load(workflow)["env"]["AWS_REGION"]

    assert (
        'name="/shikkhokplus/shikkhokplus-${ENVIRONMENT}/android-cert-sha256"'
        in workflow
    )
    assert (
        'name        = "/shikkhokplus/shikkhokplus-${each.key}/android-cert-sha256"'
        in tf
    )
    assert f'region = "{region}"' in tf
    assert "for_each = var.android_cert_sha256 == null" in tf
