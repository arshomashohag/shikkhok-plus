# CI/CD Pipeline — D5 `knowing-how-it-is-going`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **`check.yml` does not change at all.** D5's two new gates are both
> release-time: the size gate needs a **built AAB**, and the ZAP scan needs a
> **deployed host**, neither of which a merge-time job has.
>
> **Both gates have the same failure mode and it is the one this project
> keeps meeting**: a check that passes because it checked nothing. Gitleaks
> reported clean on a shallow clone; the integration suite reported green
> having skipped 24 of 28 tests. **§ 4 specifies FOUR precondition
> assertions** across the two gates, because the subtlest vacuous pass here
> hides *behind* another precondition that passed [§ 3].

## Sources

- [upstream] `nfr-design/performance-design.md` § 5 — the size gate's steps
- [upstream] `nfr-design/security-design.md` § 5 — the ZAP job
- [upstream] this stage's `infrastructure-specification.md` §§ 3, 4
- [upstream] `nfr-requirements/performance-requirements.md` — NFR2.11–NFR2.16,
  NFR2.21; `security-requirements.md` — NFR14.74–NFR14.77
- [team] `team.md` Deployment — the two-speed model, the DAST clause
- [code] read 2026-10-25: `.github/workflows/release-android.yml`,
  `.github/workflows/check.yml`, `.github/workflows/deploy.yml`,
  `infra/outputs.tf`

---

## 1. What does not change

| Workflow | D5's change |
|---|---|
| `check.yml` | **none** |
| `deploy.yml` | **one job**, possibly — see § 3 and its open question |
| `release-android.yml` | **one step** |
| `terraform` paths | none |

**`check.yml` is untouched and that is worth stating**, because D5 adds
backend modules and tests and the natural assumption is that the merge gate
grows. It does not: `make check` already runs the whole suite, and D5's tests
are ordinary members of it.

**The Docker precondition step added earlier this session covers D5's tests
too** — its integration tests run against real PostgreSQL like every other
unit's, and a runner that lost Docker would now fail rather than skip them.

---

## 2. The download-size gate

**One step in `release-android.yml`.** An earlier draft placed it by
reasoning about what the neighbouring steps are *for*, and the built job's
actual order makes that placement fail every run:

| Line | Step |
|---|---|
| 173 | Build the bundle |
| **187** | **Remove the keystore** — `if: always()`, `shred -u` |
| 194 | The bundle is signed |
| 208 | SBOM (Syft) |

**The keystore is destroyed at 187, before the signature assertion at 194.**
An earlier draft placed the size gate "after the signature step", which is
**after the keystore is gone** — and since `bundletool build-apks` cannot
produce an APK set without signing, that gate would have failed **every
release**, on a missing file rather than on a size.

**Design statement: the size gate signs the APK set with a THROWAWAY
keystore generated in its own step, and is therefore not bound to that
window at all.**

Three remedies exist and this is the third:

| Remedy | Why not |
|---|---|
| Place the gate between 173 and 187 | Works, but makes the gate's position depend on a security step's position; a later reader moving either breaks the other silently |
| Move "Remove the keystore" after the gate | **Rejected.** That step exists so the upload key does not outlive its use, and it already runs `if: always()` to survive a failure. Widening its window trades a real security property for convenience |
| **A throwaway keystore** | **Chosen** |

**The upload key is not needed, because only the size figure is.**
`build-apks` requires *a* signature, not *the* signature. A
`keytool -genkeypair` into `$RUNNER_TEMP` costs one command, **never touches
the upload key**, and makes the gate independent of where the shred step
sits.

**The honest limit, stated rather than claimed away: the size is not exactly
key-independent.** A signature block is bytes in the APK, so a certificate
of a different size shifts the figure. **Quantified rather than hand-waved**:
a signing block is on the order of 1–4 KB, against **11.4 MB of headroom**
(4.1 MB measured, 15 MB ceiling) — **0.036% of the margin**. The proxy's
density-and-language approximation [NFR2.13] is already a larger source of
difference than the key is.

**So the gate's claim is "within a few KB of the signed artifact's size",
not "identical to it"** — which is what a ceiling check needs. Should the
headroom ever shrink to the point where kilobytes decide the verdict, the
right response is to stop shipping at the ceiling, not to re-engineer the
gate.

**The gate therefore runs after "The bundle is signed"** — its original
intended position, and the one where the clearer signature error has already
fired — **and before Syft**, so a bundle failing the ceiling is not
inventoried.

**The throwaway keystore also removes a trap the other two remedies carry**:
with either of them, the gate's correctness depends on its neighbours' order,
so a later reader rearranging steps for an unrelated reason breaks it — and
breaks it into "fails every release", which at least fails loudly. Signing
independently makes the gate correct wherever a built AAB exists.

```
- name: The download size is under the ceiling
  run: |
    # Pinned and checksum-verified [NFR2.21].
    <install bundletool at the pinned version; verify its checksum>

    aab=android/build/outputs/bundle/release/android-release.aab
    [ -f "$aab" ] || { echo "::error::No AAB at $aab"; exit 1; }

    bundletool build-apks --bundle="$aab" \
      --output="$RUNNER_TEMP/app.apks" \
      --ks="$RUNNER_TEMP/size-check.jks" --ks-pass=... --ks-key-alias=...
    # A THROWAWAY key generated in this step, never the upload key:
    # build-apks needs A signature, not THE signature. The size is
    # NOT exactly key-independent -- the signing block carries the
    # certificate -- but it moves by ~1-4 KB against 11.4 MB of
    # headroom, smaller than the NFR2.13 proxy error already
    # disclosed. See the prose above.

    bundletool get-size total --apks="$RUNNER_TEMP/app.apks" \
      --dimensions=ABI
    # arm64-v8a's row against 15 MB [NFR2.11]. A CLOSE PROXY for
    # Play's figure, not the same quantity: density, language and
    # SDK are held at defaults [NFR2.13].
```

**The AAB-exists assertion is the precondition** [§ 4]: without it,
`build-apks` fails on a missing file with an opaque tool error rather than a
message naming what went wrong — which is exactly why the existing signature
step asserts the same thing.

**The gate fails rather than warns** [NFR2.14], demonstrated once against a
lowered threshold.

**Headroom, measured: 4.1 MB against 15 MB.** A gate breached on the day it
is written gets lowered rather than respected.

---

## 3. The ZAP API-scan job

**It cannot live in `release-android.yml`**, which has no AWS credentials,
and **it should not live in `check.yml`**, which would scan a possibly
mid-deploy environment on every push and become the gate that gets disabled
[NFR14.75].

**It needs three things**: the staging host's URL, the committed schema, and
an OIDC role that can read Terraform state.

**There are two OIDC roles and the scan must use the narrower one.** Checked
in `deploy.yml`: `AWS_DEPLOY_ROLE_ARN` is assumed by the plan and release
jobs, while `AWS_ROLE_ARN` is **the infrastructure role, whose own comment
says it "can create and destroy"**. A ZAP scan reads one Terraform output and
sends HTTP requests; it has no business holding a role that can destroy the
host it is scanning. **Design statement: the ZAP job assumes
`AWS_DEPLOY_ROLE_ARN`** — and if that role turns out to lack state-read
permission, the fix is to widen it by that one permission rather than to
reach for the infrastructure role.

*(Also confirmed while checking: `release-android.yml` contains **no** AWS
reference of any kind — not a role, not a region, not an action. The claim
that the ZAP job cannot live there is a fact about that file rather than an
inference from its purpose.)*

```
- name: Init                      # REQUIRED -- see below
  working-directory: infra
  run: |
    # The backend is PARTIAL [infra/versions.tf:39-44]: the bucket
    # is not hardcoded, and deploy.yml overrides the key PER
    # ENVIRONMENT. Without this init, `terraform output` reads no
    # remote state at all.
    terraform init -input=false \
      -backend-config="bucket=${{ vars.TF_STATE_BUCKET }}" \
      -backend-config="key=${{ inputs.environment }}/terraform.tfstate"
    # The key comes from the job's OWN dispatch input, matching
    # deploy.yml:178. Hardcoding `staging/` would be worse than it
    # looks: a production run would then read a REAL state file and
    # scan a REAL host -- the wrong one -- with every other input
    # (role, URL, schema) correctly resolved. It would not fail; it
    # would succeed against the wrong target.
    #
    # The job's input DEFAULTS to staging and team.md places the
    # scan before the internal-track promotion, so staging is the
    # expected value -- but it is a default, not an assumption.

- name: Resolve the host to scan
  working-directory: infra
  run: |
    # NOT a hardcoded URL: a hostname that stops matching the
    # deployment leaves a GREEN SCAN OF NOTHING, the shape
    # Gitleaks-on-a-shallow-clone and the Docker skip both had.
    #
    # `api_url` is the CloudFront-fronted PRIMARY host OF THE
    # LOADED STATE KEY. The init above is
    # what makes this the staging deployment's own URL. It is NOT
    # the rehearsal host [infra/main.tf:192], which has its own
    # origin_fqdn and no URL output.
    url=$(terraform output -raw api_url)
    [ -n "$url" ] || { echo "::error::No api_url in state."; exit 1; }

- name: The host answers before we scan it
  run: |
    # A baseline scan of an unreachable host finds nothing and
    # exits zero. Assert reachability FIRST [§ 4].
    curl -fsS -m 15 "$url/health" >/dev/null \
      || { echo "::error::$url/health did not answer; a scan now
                 would report no findings because it found no app."
           exit 1; }

- name: The schema imported           # THE THIRD VACUOUS PASS
  run: |
    # A schema that fails to import leaves ZAP crawling the bare
    # root URL, finding almost nothing, exiting zero -- a green
    # scan of nothing HIDDEN BEHIND a /health probe that passed.
    #
    # THE PROPERTY: the scan visited at least as many distinct
    # paths as the schema declares. Measured 2026-10-25,
    # openapi.json declares 46 paths and 52 operations, so a run
    # reporting a handful of URLs did not import the schema.
    #
    # THE MECHANISM is the part to confirm at implementation, and
    # review found neither script prints a parseable URL count:
    # read it from ZAP's JSON report (-J), which lists the sites
    # and URLs the scan touched, and fail when the distinct-path
    # count falls below the schema's. NOT from stdout.

- name: ZAP API scan
  run: |
    # zap-api-scan.py, NOT zap-baseline.py -- corrected 2026-10-25
    # after review. `zap-baseline.py` has NO -f option and performs
    # no OpenAPI import; it crawls from a URL. The API script is the
    # one that reads a schema, which is what team.md's "driven from
    # the committed OpenAPI 3.1 schema" requires.
    #
    # It takes the SCHEMA as its target and learns the host from the
    # schema's server URL or an override -- not a URL to crawl.
    zap-api-scan.py -t openapi.json -f openapi \
                    -z "-config replacer...$url"
    # High or above blocks; lower annotates [NFR14.76].
```

**Three preconditions, not two, and the third is the subtle one.** The
`/health` probe proves the host is up; it says nothing about whether ZAP
understood the schema. A failed import degrades the scan to a root-URL crawl
that finds nothing and exits zero — **and the probe that just passed makes
that look like a clean scan of a healthy host.** A precondition that hides a
vacuous pass is worse than none, which is why this one is specified rather
than left to ZAP's exit code.

**Open, and the human's: whether this is a fourth job in `deploy.yml` or its
own `security-scan.yml`.** `deploy.yml` already carries plan, infrastructure
and release jobs on a deploy cadence; this one runs before a Play promotion,
which is a different rhythm. **Both satisfy every requirement** — the
difference is what `deploy.yml` is for, and that is a preference worth
asking about rather than deciding quietly.

### What a green ZAP run means

**It reaches only the unauthenticated surface** [NFR14.77] — the scan carries
no token. So a pass means **every authenticated route refuses without one**,
which is real and worth checking. It does **not** mean authenticated routes
are free of findings.

**Stated in the job's own comment**, not only here, because "the API passed a
security scan" is how a green DAST run gets reported upward.

---

## 4. The precondition pattern, applied four times

This project has met the same defect three times: **a check that passes
because it checked nothing.**

| Check | How it passed without checking | Guard |
|---|---|---|
| Gitleaks | A shallow clone — *"no leaks found in partial scan"*, 0 bytes read | A commit-count assertion, built from the first commit |
| `make check` | No Docker — 24 of 28 tests skipped, exit 0 | A `docker info` assertion, **added this session** |
| **Size gate** | A missing AAB | **`[ -f "$aab" ]`, § 2** |
| **ZAP** | An unreachable host — no findings, exit 0 | **A `/health` probe, § 3** |
| **ZAP** | A schema that failed to import — a root-URL crawl, exit 0, **behind a probe that passed** | **A discovered-URL count, § 3** |
| **ZAP** | No `terraform init` — `output` reads no state, an empty URL | **`[ -n "$url" ]` after an explicit init, § 3** |

**Both new gates get their precondition asserted in the same commit that
introduces them**, rather than after someone notices. That is the only part
of this pattern the project has been getting wrong: each of the first two
guards was added *after* the hole was found, and the Docker one three days
after it was assigned.

---

## 5. Sequencing

```
merge  →  check.yml (unchanged; D5's tests run inside make check)
          ↓
deploy →  deploy.yml  →  staging deployed and healthy
          ↓
scan   →  ZAP baseline against the deployed staging host   [§ 3]
          ↓
tag    →  release-android.yml
            build → signed? → SIZE GATE → Syft → notes     [§ 2]
          ↓
          Play internal track
```

**The ZAP scan precedes the tag**, because `team.md` places it before the
internal-track promotion and because a scan that blocks after a version
number is spent costs a version number. `release-android.yml`'s own header
makes the same argument for its dry-run dispatch input.

**What the arrow between them does NOT establish.** The scan reads `api_url`
from **staging** state; the release builds the client against
`vars.ANDROID_API_BASE_URL`. **Nothing in the repository states those name
the same deployment**, so the diagram's ordering is a schedule, not a
coverage claim — a clean scan of staging says nothing about the host the
built APK will talk to if the two differ. Stated because a sequence diagram
is read as implying coverage, and here it implies more than it earns.

---

## 6. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| `check.yml` unchanged [§ 1] | The workflow diff | yes |
| Size gate blocks at 15 MB [NFR2.11, NFR2.14] | Exit code, demonstrated once against a lowered threshold | yes |
| `bundletool` pinned and checksummed [NFR2.21] | The pin in the diff | yes |
| The AAB exists before `build-apks` [§ 4] | The `-f` assertion | yes |
| ZAP targets the deployed host [§ 3] | It reads `terraform output -raw api_url` | yes |
| The host answers before the scan [§ 4] | The `/health` probe | yes |
| **The schema actually imported** [§ 3] | A discovered-URL count against the operation count | yes |
| The scan uses the narrow deploy role [§ 3] | The role named in the job | yes |
| Terraform `init` precedes `output` [§ 3] | The init step, keyed by the job's own environment input | yes |
| ZAP blocks at High [NFR14.76] | Exit code, demonstrated once | yes |
| ZAP's report retained [NFR24.25] | Its presence in uploaded artifacts | yes |
| The proxy's difference recorded [NFR2.13] | **A human comparison at the first release** | **no** |
| Which workflow hosts the ZAP job [§ 3] | **Open — the human's preference** | **no** |

---

## Assumptions & Open Questions

- **Where the ZAP job lives is open** [§ 3]: a fourth job in `deploy.yml` or
  its own `security-scan.yml`. Both satisfy every requirement. **For the
  human.**
- **Whether `AWS_DEPLOY_ROLE_ARN` can read Terraform state is NOT verified
  here**, and § 3 now names *which* role rather than "the existing OIDC
  role" — there are two, and the other one can destroy infrastructure.
  Whether the deploy role's policy covers a state read is a permissions
  detail to check against `infra/` at Code Generation. **Named so it is
  checked rather than assumed, and named specifically so the check is not
  satisfied by reaching for the wrong role.**
- **The script is `zap-api-scan.py`, not `zap-baseline.py`** — corrected
  2026-10-25 after review found that baseline has **no `-f` option and
  performs no schema import at all**. The error originated in
  `nfr-design/security-design.md` § 5 and was carried here; both are fixed.
  **The exact flags are still sketched** and should be confirmed against the
  pinned ZAP version — but the script name is now right, which is what
  "driven from the committed OpenAPI schema" actually requires.
- **The schema-import assertion names a property and a source, not a
  command** [§ 3]. The property is checkable and its threshold is a measured
  number — `openapi.json` declares **46 paths and 52 operations** as of
  2026-10-25 — but **whether ZAP's report exposes a path count in a form a
  shell step can read is NOT verified here**. Named precisely so
  implementation confirms it against the pinned ZAP version rather than
  discovering mid-build that the assertion has no data to read. **If it turns
  out ZAP exposes no such count, the precondition needs a different
  mechanism, not dropping** — it is the one guarding the vacuous pass that
  hides behind a passing probe.
- **The one-off Console comparison** [NFR2.13] has no owner beyond "the first
  release". It is a human step and is stated as one.
- **Every figure here was measured or cited**: the AAB at 4.1 MB
  (measured 2026-10-25), the 24-of-28 skip count (measured this session), and
  the workflow structure (read from the files).
