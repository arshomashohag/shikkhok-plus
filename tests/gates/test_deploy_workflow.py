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

import os
import pathlib
import re
import subprocess

import pytest
import yaml

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
