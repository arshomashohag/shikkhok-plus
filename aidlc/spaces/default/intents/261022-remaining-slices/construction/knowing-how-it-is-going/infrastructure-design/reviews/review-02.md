## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-25T02:35:15Z
**Iteration:** 2

### What I verified independently

**The keystore remedy, judged rather than accepted.** The dispatch asked me not
to take the reasoning on trust, so I took the claim apart. The step order the
design tabulates is exactly right against the file: `Build the bundle` at 173,
`Remove the keystore` (`if: always()`, `shred -u`) at 187, `The bundle is
signed` at 194, `SBOM` at 208. A gate signing with `upload.jks` after 194 would
indeed have failed every release.

The remedy's load-bearing sentence as first written was *"a signed set's size
does not depend on which key signed it"*, and that sentence is **false as
stated**. The APK Signing Block is bytes inside the archive, and it carries the
signing certificate: a different DN length, a different key size, a different
validity window and different extensions all move the total. A throwaway
`keytool -genkeypair` certificate and a real Play upload certificate do not
produce byte-identical sets.

What matters is the magnitude, and there the remedy survives comfortably. A v2
signing block for a single signer is on the order of 1-4 KB; the measured
headroom is 11.4 MB (4.1 MB against the 15 MB ceiling). The error is about
0.03% of the margin, and it is strictly smaller than the proxy error the
document already discloses under NFR2.13, where density, language and SDK are
held at defaults. For a ceiling check, "within a few KB" is the right property
and the gate has it.

**§ 2 was revised while I was reading it, and the revision is the correct
one.** The current text now states the limit in its own voice — *"the size is
not exactly key-independent"* — quantifies it at 1-4 KB against 11.4 MB, and
reframes the gate's claim as *"within a few KB of the signed artifact's size,
not identical to it"*. That is the finding I had drafted, already applied, and
applied better than a reviewer's one-line remedy would have been: it keeps the
comparison to the NFR2.13 proxy error, which is what makes the bound
meaningful rather than merely small. I note one residual below, at Minor, and
it is a comment-versus-prose mismatch rather than a design defect.

Position-independence, the property the remedy was actually chosen for, holds
unconditionally: once the gate generates its own key it needs only a built AAB,
so no later reordering of the shred step can break it.

**The `terraform init` snippet against the real backend.** `infra/versions.tf`
declares `backend "s3"` with `key`, `region`, `encrypt` and `use_lockfile`
inline but **no `bucket`** — a partial backend, exactly as the design says, and
the comment there gives the reason (S3 names are globally unique, so a fork
cannot share one). So `bucket` must come from `-backend-config`, and the
snippet supplies it from `vars.TF_STATE_BUCKET`, which is the same variable
`deploy.yml` uses and which `deploy.yml` asserts non-empty at line 94 before
use.

The key is the more interesting half. `deploy.yml:178` builds it as
`key=${{ inputs.environment }}/terraform.tfstate`, and `environment` is a
`choice` input whose options are exactly `[staging, production]` with
`staging` the default. So `staging/terraform.tfstate` is a key `deploy.yml`
provably constructs, not an invented one. The inline `key = "phase1/..."` in
`versions.tf` is overridden by `-backend-config` in both cases, which is why
the design's parenthetical that deploy.yml "overrides the key per environment"
is accurate. The init is correct against the real backend.

**Which host `api_url` names.** `infra/outputs.tf:1-4` forwards
`module.cdn.api_url`. The rehearsal host is `module.staging_app` in
`infra/main.tf:174-192`, created only when `enable_staging_instance` is true,
with `origin_fqdn = "rehearsal-${var.origin_subdomain}..."`, and
`infra/outputs.tf` publishes only its `staging_instance_id` — there is no URL
output for it. So the revised claim holds on both halves: `api_url` is the
primary host of whichever state key is loaded, and it is not the rehearsal
host. `infra/variables.tf:130-136` independently confirms the naming trap the
design sidesteps — *"the primary host already is staging"* — which is the very
confusion that made iteration 1's finding worth raising.

**The schema-import assertion.** `openapi.json` is OpenAPI 3.1.0 with 46 paths
and 52 operations, so a floor derived from it is a real number that exists
today. The property being asserted is sound and it closes a genuine hole. Its
*implementability as written* is where I have a reservation, recorded below at
Major — not because the check is impossible, but because the one sentence
specifying it names a quantity (`the discovered-URL count`) that
`zap-baseline.py` does not print in any parseable form, and the surrounding
invocation has a flag problem that the Assumptions section half-anticipates but
does not name.

**Collateral checks.** `/health` is a real path in `openapi.json`, and the CDN
module has a single `default_cache_behavior` with no path-pattern carve-outs,
so the probe reaches the origin through CloudFront as drawn. The two OIDC roles
are distinct and `deploy.yml:103-104` states the split in its own words; the
narrower choice is correct. The size-gate `-f` assertion duplicates what the
existing signature step already does, which is consistent rather than
redundant. `infrastructure-specification.md` § 3 and `cicd-pipeline.md` § 2 now
tell the same story about the keystore, so the two documents no longer
disagree.

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 2 | The gate is placed after "The bundle is signed" and signs with `$RUNNER_TEMP/upload.jks`, but `release-android.yml` deletes that file in a `Remove the keystore` step (`shred -u`, `if: always()`) that sits between "Build the bundle" and "The bundle is signed". At the named placement the keystore is already gone, so `bundletool build-apks` cannot sign and the gate fails every run. The stated rationale inverts the real order. | Pick one and state it: move the gate between "Build the bundle" and "Remove the keystore"; or move the removal step after the gate, keeping `if: always()`; or sign the APK set with a throwaway debug keystore generated in the step, since only the size figure is needed and the upload key is not. | Resolved (reviewer) |
| R-02 | Major | construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 3, Resolve the staging host | The snippet runs `terraform -chdir=infra output -raw api_url` with no preceding `terraform init`. `infra/versions.tf:39` declares a partial `backend "s3"` whose bucket and key are supplied only by `-backend-config`, and `deploy.yml:175-178` passes both. Without that init the command reads no remote state and fails, or reads a stale local one. | Add the `init` step with `-backend-config="bucket=..."` and `-backend-config="key=staging/terraform.tfstate"`, matching `deploy.yml`, and name the `setup-terraform` pin. | Resolved (reviewer) |
| R-03 | Major | construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 3, Resolve the staging host | `api_url` resolves to `module.cdn.api_url`, the CloudFront-fronted API hostname for whichever state file is initialized. The staging rehearsal host is a separate instance, `shikkhokplus-rehearsal`, behind its own `origin_fqdn`, and `infra/outputs.tf` publishes only its instance id — there is no staging URL output. Which host the scan actually reaches therefore depends entirely on the state key, which the design never names, so "the staging host's URL" is not established. | State that the scan initializes against the staging state key and that `api_url` in that state is the staging URL, or add an output that names the rehearsal host's URL. Either way say which host is scanned. | Resolved (reviewer) |
| R-04 | Major | construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 3, ZAP baseline, and section 4 table | The precondition table treats an unreachable host as the only vacuous-pass route for ZAP, but there is a third: the schema import itself. `zap-baseline.py -f openapi -z "-config <openapi.json>"` is flagged in Assumptions as sketched, and a schema that fails to import leaves ZAP crawling the bare root URL, finding almost nothing, and exiting zero — the same green-scan-of-nothing shape, now hidden behind a `/health` probe that passed. | Add a post-import assertion that the scan actually covered the schema's routes — for example that ZAP's URL count or site tree exceeds a floor derived from the committed `openapi.json` — and add the row to the section 4 table. | Resolved (reviewer) |
| R-05 | Minor | construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 5, Sequencing | The sequence places the ZAP scan before the tag, but the scan reads `api_url` from staging state while `release-android.yml` builds against `vars.ANDROID_API_BASE_URL`. Nothing states those two name the same deployment, so the diagram implies a coverage relationship it does not establish. | State plainly that the scan covers the staging backend and that the build's `ANDROID_API_BASE_URL` is a separately configured value, or name the check that ties them. | Resolved (reviewer) |
| R-06 | Major | aidlc/spaces/default/intents/261022-remaining-slices/construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 3, the ZAP baseline snippet | The two ZAP steps cannot be implemented as written and the gap is larger than the Assumptions note admits. `zap-baseline.py` has no `-f` option and performs no OpenAPI import; the OpenAPI-driven scan is `zap-api-scan.py -f openapi`, a different script with different defaults. Separately, the schema-import assertion asks for a "discovered-URL count", which neither script prints in any parseable form, so the one precondition the design calls the subtle one has no stated source for its number. | Name the script that actually imports the schema and name where the count is read from, for example the JSON report written with `-J` and counted over its site/alert URLs, or a prior explicit import step whose own output is asserted. State the floor as a number derived from the committed schema (52 operations across 46 paths today) and say which of the two it is compared against. | New |
| R-07 | Minor | aidlc/spaces/default/intents/261022-remaining-slices/construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 2, the fenced snippet's comment | The prose above the snippet now correctly states the size is not exactly key-independent, but the comment inside the snippet still asserts the superseded absolute: "a signed set's SIZE does not depend on which key signed it". The snippet is the part that gets copied into the workflow, so the corrected sentence is the one that will not survive into the repository. The project's own rule is that where a comment states a claim, the claim is checked or removed. | Rewrite the in-snippet comment to carry the bounded form, for example that the throwaway key differs from the upload key only by the signing block's few KB, well inside the headroom. | New |
| R-08 | Minor | aidlc/spaces/default/intents/261022-remaining-slices/construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 4 heading and table | The heading reads "The precondition pattern, applied twice" while the table beneath it lists four new guards across the two gates, and the document's own opening banner insists on "three of them, not two". The count in the heading is a claim and it contradicts both the table and the banner. | Retitle to match what the table holds, or state the count as gates rather than assertions so the heading, the banner and the table agree. | New |
| R-09 | Minor | aidlc/spaces/default/intents/261022-remaining-slices/construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 3, the Init step, and section 6 | The init hardcodes `key=staging/terraform.tfstate` while the role, the host and the schema are all resolved rather than fixed. If the scan is ever pointed at production the key is the one thing that will not follow, and it will fail silently in the worst way available: it will read a real state file and scan a real, wrong host. The § 6 obligation row says only that the init precedes `output`, not that the key names the intended environment. | Either state plainly that this job is staging-only by design and that a production scan is out of scope for D5, or parameterise the key from the job's environment input the way `deploy.yml` does, and extend the § 6 row to cover which environment the key names. | New |

> R-01 Reviewer note: The throwaway keystore makes the gate position-independent, and the two rejected remedies are recorded with reasons. The "size is independent of the key" overclaim that rode along with the fix has itself been corrected in the current § 2, which now bounds the error at 1-4 KB against 11.4 MB of headroom.

> R-02 Reviewer note: An explicit `terraform init -input=false` with `-backend-config` for both bucket and key now precedes `output`, and it is correct against the partial backend in `infra/versions.tf`.

> R-03 Reviewer note: The design now states that `api_url` is the primary host of the loaded state key, that loading `staging/terraform.tfstate` is what makes it staging's, and that it is not the rehearsal host. All three verified against `outputs.tf`, `main.tf:174-192` and `variables.tf:130`.

> R-04 Reviewer note: The schema-import assertion is added as a named step and as a § 4 table row. The property is right; a residual about its implementability is filed as a new Major below rather than against this ID.

> R-05 Reviewer note: § 5 now states the arrow is a schedule and not a coverage claim, and names why: nothing ties `api_url` to `vars.ANDROID_API_BASE_URL`.

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| (none declared by the stage) | n/a | Verification was by direct reading of the named workflows, the Terraform backend, outputs, variables and CDN module, and by parsing the committed schema. |
| `openapi.json` parse and operation count | PASS | OpenAPI 3.1.0, 46 paths, 52 operations; `/health` present. The schema-import floor is derivable from a real number today. |
| Backend-config match against `deploy.yml` | PASS | `bucket` absent from `infra/versions.tf` (partial backend) and supplied from `vars.TF_STATE_BUCKET`; `staging/terraform.tfstate` is the key `deploy.yml:178` constructs for the default `staging` choice input. |
| `release-android.yml` step-order check | PASS | Build 173, shred 187 (`if: always()`), signature assertion 194, SBOM 208 — exactly as § 2 tabulates. |
| `api_url` resolution | PASS | Forwards `module.cdn.api_url`; the rehearsal host is `module.staging_app` with its own `origin_fqdn` and no URL output. |

### Summary

Every iteration-1 finding is genuinely fixed, and the keystore remedy holds up
under the scrutiny the dispatch asked for — its one overclaim was corrected in
the document while this review was in progress, and the correction is better
than the one I would have prescribed. What remains is one Major worth the
human's attention before Code Generation: the ZAP snippet names a script and a
countable quantity that do not exist in the form given, so the precondition the
design rightly calls its subtlest is the one an implementer would have to
invent. That is a specification gap rather than a design error, and the design
it specifies is sound.
