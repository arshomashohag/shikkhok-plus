## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-25T02:29:10Z
**Iteration:** 1

### What I verified independently

I read `.github/workflows/release-android.yml`, `check.yml` and `deploy.yml`
in full, plus `infra/outputs.tf`, `infra/modules/cdn/outputs.tf`,
`infra/versions.tf` and `infra/main.tf`, and I resolved every NFR id the three
documents cite against the D5 `nfr-requirements/` files. The four checks the
dispatch named came out as follows.

**Gate placement.** The ZAP half of the forced-placement claim holds and I
confirmed it the way the document now says it did: `release-android.yml`
contains no AWS reference of any kind — no `aws-actions/*` step, no
`role-to-assume`, no `id-token: write` (its `permissions:` block is
`contents: write` only), no region. Every AWS credential in the repository is
in `deploy.yml`. So "the ZAP job cannot live in `release-android.yml`" is a
fact about that file, and the design's reasoning does not collapse.

The size-gate half does **not** hold, and that is the Critical finding below.
The keystore claim is half right: `$RUNNER_TEMP/upload.jks` is indeed written
only inside the `android-release` environment job and no earlier workflow has
it. But the design reads that job's step order wrongly.

**The `api_url` decision.** `output "api_url"` exists in `infra/outputs.tf:1-4`
and forwards `module.cdn.api_url`, which is
`"https://${var.api_subdomain}.${var.domain_name}"`. So the output exists and
returns a URL. Rejecting a hardcoded hostname is right. Two things the design
did not check are below as Major findings: the snippet calls
`terraform output` with no `init`, and `api_url` names the CloudFront-fronted
primary host of a state file rather than the separate `shikkhokplus-rehearsal`
instance.

Flagging the OIDC state-read permission as unverified rather than assuming it
is the right call, and the paragraph added to § 3 while I was reading — that
the scan takes `AWS_DEPLOY_ROLE_ARN` rather than the infrastructure role whose
own comment says it "can create and destroy" — is a genuine improvement and is
correct against `deploy.yml:161-165`.

**The preconditions.** Both are the right preconditions and both are real
guards. `[ -f "$aab" ]` matches what the existing signature step already does
(`release-android.yml`, `The bundle is signed`), and the `/health` probe
addresses the exact vacuous-pass shape. The third vacuous-pass route the
design missed is the Major finding about `zap-baseline.py`'s schema import.

**Built-code assertions, sampled.** `check.yml` needs no change: confirmed —
`make check` is the entrypoint and the Docker precondition is real at
`check.yml:173-180`. `release-android.yml` tag trigger, `android-release`
environment, keystore path and Syft step: all confirmed. `deploy.yml` dispatch
inputs and the SSM `curl -fsS -m 10 http://127.0.0.1:8000/health` that never
reaches the host externally: confirmed at `deploy.yml:432`, and the inference
drawn from it — that no existing job proves external reachability — is sound.
`traceability.json` parses and its structure is as described.

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 2 | The gate is placed after "The bundle is signed" and signs with `$RUNNER_TEMP/upload.jks`, but `release-android.yml` deletes that file in a `Remove the keystore` step (`shred -u`, `if: always()`) that sits between "Build the bundle" and "The bundle is signed". At the named placement the keystore is already gone, so `bundletool build-apks` cannot sign and the gate fails every run. The stated rationale inverts the real order. | Pick one and state it: move the gate between "Build the bundle" and "Remove the keystore"; or move the removal step after the gate, keeping `if: always()`; or sign the APK set with a throwaway debug keystore generated in the step, since only the size figure is needed and the upload key is not. | New |
| R-02 | Major | construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 3, Resolve the staging host | The snippet runs `terraform -chdir=infra output -raw api_url` with no preceding `terraform init`. `infra/versions.tf:39` declares a partial `backend "s3"` whose bucket and key are supplied only by `-backend-config`, and `deploy.yml:175-178` passes both. Without that init the command reads no remote state and fails, or reads a stale local one. | Add the `init` step with `-backend-config="bucket=..."` and `-backend-config="key=staging/terraform.tfstate"`, matching `deploy.yml`, and name the `setup-terraform` pin. | New |
| R-03 | Major | construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 3, Resolve the staging host | `api_url` resolves to `module.cdn.api_url`, the CloudFront-fronted API hostname for whichever state file is initialized. The staging rehearsal host is a separate instance, `shikkhokplus-rehearsal`, behind its own `origin_fqdn`, and `infra/outputs.tf` publishes only its instance id — there is no staging URL output. Which host the scan actually reaches therefore depends entirely on the state key, which the design never names, so "the staging host's URL" is not established. | State that the scan initializes against the staging state key and that `api_url` in that state is the staging URL, or add an output that names the rehearsal host's URL. Either way say which host is scanned. | New |
| R-04 | Major | construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 3, ZAP baseline, and section 4 table | The precondition table treats an unreachable host as the only vacuous-pass route for ZAP, but there is a third: the schema import itself. `zap-baseline.py -f openapi -z "-config <openapi.json>"` is flagged in Assumptions as sketched, and a schema that fails to import leaves ZAP crawling the bare root URL, finding almost nothing, and exiting zero — the same green-scan-of-nothing shape, now hidden behind a `/health` probe that passed. | Add a post-import assertion that the scan actually covered the schema's routes — for example that ZAP's URL count or site tree exceeds a floor derived from the committed `openapi.json` — and add the row to the section 4 table. | New |
| R-05 | Minor | construction/knowing-how-it-is-going/infrastructure-design/cicd-pipeline.md > section 5, Sequencing | The sequence places the ZAP scan before the tag, but the scan reads `api_url` from staging state while `release-android.yml` builds against `vars.ANDROID_API_BASE_URL`. Nothing states those two name the same deployment, so the diagram implies a coverage relationship it does not establish. | State plainly that the scan covers the staging backend and that the build's `ANDROID_API_BASE_URL` is a separately configured value, or name the check that ties them. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| (none declared by the stage) | n/a | Verification was by direct reading of the cited workflows, the Terraform outputs and backend declaration, and the D5 NFR files. |
| NFR id resolution (manual) | PASS | NFR2.11, NFR2.13, NFR2.14, NFR2.21, NFR14.75, NFR14.76, NFR14.77 and NFR24.25 all resolve to real requirements in the D5 `nfr-requirements/` files. |
| `traceability.json` parse | PASS | Parses; keys `stage`, `unit`, `note`, `upstream_ids`, `coverage` as described. |

### Summary

The documents are careful and the reasoning style is the right one for this
project — both gates are placed by argument rather than habit, and the
precondition pattern in section 4 is exactly the correction this record keeps
needing. But the single most load-bearing claim, that the size gate's
placement is forced by the keystore, reads `release-android.yml`'s step order
backwards: the keystore is shredded before the signature step the gate is
placed after, so the gate as written cannot run. That is the fifth instance in
this record of a built-code claim made from too narrow a read, and it is worth
noting that it happened inside the document whose own thesis is that checks
pass without checking. Three Major findings follow the same shape around the
ZAP job's host resolution.

On the open question the dispatch asked me to judge rather than file: leaving
the ZAP job's home — a fourth `deploy.yml` job or its own `security-scan.yml` —
undecided is right. Both genuinely satisfy every requirement, the difference
is what `deploy.yml` is for, and that is a preference the human holds. It is
not an open question carrying a proposed default wearing a question's clothes.

The sequencing in section 5 is right: a scan that blocks after a version
number is spent costs a version number, and `release-android.yml`'s own header
makes the same argument about its `workflow_dispatch` rehearsal input.
