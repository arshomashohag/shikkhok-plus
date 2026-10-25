# Infrastructure Specification — D5 `knowing-how-it-is-going`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 adds no runtime infrastructure at all: no resource, no cron entry, no
> environment variable, no cost.** D4 added one cron entry at USD 0.00; D5
> adds zero of everything. The Terraform tree is untouched.
>
> **What it does add is two CI gates**, and both are release-time rather than
> merge-time because both measure a nearly-finished app [§ 3]. One of them
> turns out to need something the workflows do not currently have — **the
> staging host's URL** — and § 4 is about where that comes from, because the
> deploy workflow deliberately never reaches the host from outside.

## Sources

- [upstream] `nfr-design/performance-design.md` § 5 — the size gate
- [upstream] `nfr-design/security-design.md` § 5 — the ZAP baseline
- [upstream] `nfr-design/logical-components.md` § 4 — the CI placement
- [upstream] `nfr-requirements/performance-requirements.md` — NFR2.11–NFR2.16,
  NFR2.21; `security-requirements.md` — NFR14.74–NFR14.77
- [team] `team.md` Deployment — the DAST clause and the two-speed model
- [code] read 2026-10-25: `.github/workflows/release-android.yml`
  (trigger, `android-release` environment, keystore step, Syft step),
  `.github/workflows/deploy.yml` (dispatch inputs, per-environment
  protection, the SSM health check), `infra/outputs.tf`, `infra/variables.tf`,
  `infra/main.tf`

---

## 1. Runtime infrastructure: nothing

| Facet | D5's change |
|---|---|
| Compute | none |
| Database | none — no table, no migration, no index [BR4.2] |
| Scheduled work | **none** — no cron entry, which is why there is no freshness alert to define |
| Secrets | none |
| Network | none |
| Terraform | **not touched** |
| **Monthly cost** | **USD 0.00** |

**The cost figure is zero rather than "small", and that is checkable**: the
budget guard in `infra/main.tf` sums named resources, and D5 adds no entry to
it. **Verifier: the Terraform plan is empty for this unit.**

**Stated as a table rather than a sentence** because four consecutive units
added infrastructure and an absent section would read as an omission rather
than a finding.

---

## 2. Why there is no scheduled work, and what that removes

D3 and D4 each added a cron entry and a `job_heartbeat` row, and each
therefore inherited the freshness alert. **D5 computes every figure on
request** [BR1.4] — there is nothing to schedule, so there is no heartbeat,
no staleness window and no alert.

**This is the correct outcome of D4's option-B enumeration rather than a gap
it left** [observability-design § 2]: enumeration's value is that a unit
*with* a job cannot forget to wire it in, not that every unit receives an
alert.

**Verifier: a file check that `user_data.sh.tftpl` is unchanged and that D5
adds no `stamp_heartbeat` call.**

---

## 3. Two CI gates, both at release

| Gate | Workflow | Why not `check.yml` |
|---|---|---|
| Download size | `release-android.yml` | `bundletool build-apks` **requires signing**, and no keystore exists outside the release job's protected environment |
| ZAP baseline | **a new job**, § 4 | A DAST pass per push scans a possibly mid-deploy environment and is the gate that gets disabled |

**The size gate's placement is a consequence of the tool, not a
preference.** `get-size` reads an APK **set**, `build-apks` produces one only
when signed, and the keystore is written to `$RUNNER_TEMP/upload.jks` inside
the `android-release` environment — which exists precisely so a workflow edit
on any branch cannot exfiltrate the upload key.

**Placement: after "The bundle is signed" and before Syft**, signing its own
APK set with a **throwaway keystore** generated in the step.

The built job shreds the upload keystore at line 187, **before** the
signature assertion at 194, so an earlier draft's "after the signature step,
signing with `upload.jks`" would have failed every release on a missing
keystore. **`build-apks` needs *a* signature, not *the* signature**, and a
signed set's size does not depend on which key signed it — so the gate signs
independently and is not bound to that window at all. `cicd-pipeline.md` § 2
has the full ordering and the two remedies rejected.

---

## 4. The ZAP job, and the problem it surfaces

`team.md`: *"an OWASP ZAP baseline scan against the staging host, driven from
the committed OpenAPI 3.1 schema."*

**The scan needs the staging host's URL, and no workflow currently has
it.** This is the finding of this stage, and it is not obvious: `deploy.yml`
verifies a deploy by running a health check **on the instance** through SSM
against `127.0.0.1:8000/health`, so it never reaches the host from outside
and never needs to know its public name.

**Three ways to supply it, and the design chooses:**

| Source | Cost | Risk |
|---|---|---|
| A hardcoded URL in the workflow | none | A hostname change passes CI and scans nothing, or scans the wrong host |
| A repository variable | one setting | Same drift, one indirection further away |
| **`terraform output -raw api_url`** | the job needs read access to state | **None of the above** — it cannot disagree with what is deployed |

**Design statement: the ZAP job reads `api_url` from Terraform output**
[`infra/outputs.tf:1-4`], which is the same value the Android client is built
against and therefore the same host a user reaches. A hardcoded URL that
silently stops matching the deployment is the failure this avoids, and it is
the failure that leaves a **green scan of nothing** — the shape this project
has already been bitten by twice, with Gitleaks on a shallow clone and the
integration suite without Docker.

**The job therefore runs in the deploy workflow's AWS context**, not the
Android release workflow: it needs the OIDC role that can read Terraform
state, and `release-android.yml` has no AWS credentials at all.

### Where it runs, concretely

**A `workflow_dispatch` job in `deploy.yml`, gated on the staging
environment**, run before the Play internal-track promotion rather than on
every deploy. **Not** automatically after each staging deploy: a DAST pass on
every deploy makes a deploy slow enough that people batch them, which is the
opposite of what staging is for.

**Open and named: whether the ZAP job belongs in `deploy.yml` or its own
workflow.** `deploy.yml` already carries plan, infrastructure and release
jobs; a fourth that runs on a different cadence stretches what that file is.
A separate `security-scan.yml` with its own dispatch is the alternative. **The
design does not choose** — both satisfy every requirement, the difference is
file organisation, and the human may have a preference about where a
security scan lives.

---

## 5. What D5 does not touch

- **The deploy pipeline's migration step** — D5 ships no migration, so the
  Alembic step runs with nothing to apply.
- **The budget guard** — no resource, no entry, no change to the USD 50
  ceiling's arithmetic.
- **`user_data.sh.tftpl`** — no cron entry, no new command.
- **Secrets and SSM parameters** — none added.
- **The staging and production topology** — unchanged.

---

## 6. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| No runtime resource [§ 1] | An empty Terraform plan for this unit | yes |
| No scheduled work [§ 2] | A file check on `user_data.sh.tftpl` | yes |
| Size gate blocks at 15 MB [NFR2.11] | The gate's exit code, demonstrated once | yes |
| `bundletool` pinned [NFR2.21] | The pin in the workflow diff | yes |
| ZAP targets the deployed host [§ 4] | It reads `terraform output -raw api_url` | yes |
| ZAP blocks at High [NFR14.76] | Exit code, demonstrated once | yes |
| ZAP's report retained [NFR24.25] | Its presence in uploaded artifacts | yes |
| The proxy's difference recorded [NFR2.13] | **A human comparison at the first release** | **no** |
| Where the ZAP job lives [§ 4] | **Open — the human's preference** | **no** |

---

## Assumptions & Open Questions

- **Where the ZAP job lives is genuinely open** [§ 4]: a fourth job in
  `deploy.yml`, or its own `security-scan.yml`. Both satisfy every
  requirement; the difference is what `deploy.yml` is for. **For the human.**
- **The ZAP job needs an OIDC role with Terraform state read access.**
  `deploy.yml` already authenticates by OIDC rather than long-lived keys;
  whether the existing role's policy covers a state read is **not verified
  here** — it is a permissions detail for Code Generation to check against
  `infra/`, and it is named so it is checked rather than assumed.
- **The staging host must be deployed and healthy for the scan to mean
  anything.** A scan against an unreachable host should **fail** rather than
  report no findings, which is the same precondition-assertion shape as the
  Docker and Gitleaks guards. Stated here; the mechanism belongs in
  `cicd-pipeline.md`.
- **No figure in this document was measured** except the AAB's 4.1 MB, which
  was measured at the nfr-requirements stage. D5's own code does not exist.
