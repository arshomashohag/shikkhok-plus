## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T05:41:13Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/cicd-pipeline.md > §B step table and §C job layout | B1 ships Kotlin deliverables that no B1 gate compiles or tests; §C puts the first Android job at B4 | Add a B1 Kotlin step to §B, or move the Kotlin deliverables out of B1 and record the B1 DoD amendment alongside the §F.2 one. See note A | Resolved (reviewer) |
| R-02 | Major | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/traceability.json > coverage rows NFR9.7 and NFR9.9 | Both rows defer a B1 deliverable to "the Android job, which first exists at B4", so neither NFR has a B1 owner | Re-mark both against whichever B1 step §B gains, or mark them GAP with the same reasoning §F already applies to NFR9.30. See note A | Resolved (reviewer) |
| R-03 | Major | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/cicd-pipeline.md > §A "The blocking suite requires no secret" | The no-secret property is asserted for B1 while §C schedules an Android release-build job that needs a signing keystore, so the named erosion already has a date | Name the Android signing credential in §C as the first scheduled exception and state whether it sits inside or outside the blocking suite. See note B | Resolved (reviewer) |
| R-04 | Minor | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/cicd-pipeline.md > §E Budget paragraph | "Checked rather than assumed" names no owner, cadence, threshold or mechanism, so the obligation cannot be shown unmet | State who checks the minute figure, how often, and at what consumed fraction the Android split moves to CodeBuild. See note C | Resolved (reviewer) |
| R-05 | Critical | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/cicd-pipeline.md > §B step 11 and §C jvm job | Step 11 compiles a "shared model package" with no SDK, but U1's Kotlin money type lives in `core/model` inside the single `:app` Android module, which cannot compile without the Android Gradle Plugin and `compileSdk` 36 | Either specify the separate plain-JVM Gradle module the step needs and reconcile it with the single-`:app`-module decision, or make step 11 an SDK-using job and withdraw the no-SDK claim in §A and §C | New |
| R-06 | Major | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/traceability.json > upstream_ids and the NFR9.33 coverage row | NFR9.33 appears in `upstream_ids` but exists in no upstream artifact; the upstream NFR9 series ends at NFR9.32 | Either carry the invariant as a stage decision in `reverse` as the other unnumbered decisions are carried, or route it upstream so the id has an owner; do not list a self-minted id among upstream requirements | New |
| R-07 | Major | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/cicd-pipeline.md > §B step 2, §E caching, §F established list | Step 11 adds a Gradle build, but step 2 verifies only "the lockfile", §E caches only the lockfile hash, and §F establishes only "dependency lockfiles" — no Gradle dependency locking or `dependencyVerification` counterpart | Extend step 2, the §E cache key and §F's established list to cover the Gradle lockfile and checksum verification, or state why the Kotlin surface is exempt until B4 | New |
| R-08 | Minor | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/cicd-pipeline.md > §G absences table | §G still enumerates absences for a Python-only library and does not record that B1 now carries a Kotlin toolchain job, leaving the one surface §G readers check for Android concerns silent | Add a §G row for the Kotlin/JVM surface stating what step 11 covers and what remains B4's, so the absence list matches the pipeline it describes | New |

> R-01 Reviewer note: Step 11 gives B1's Kotlin deliverable a B1 gate; §C shows the `jvm` job from B1; the rejected alternative is recorded. The finding as written is closed. Step 11's own feasibility is a separate new finding

> R-02 Reviewer note: NFR9.7 and NFR9.9 are OK against step 11, with the correction and its reasoning stated in both rows and the file note

> R-03 Reviewer note: The keystore is named as a fourth secret, the DEX scan sits in the release gate, and the invariant is stated checkably. §C's android box carries the pointer

> R-04 Reviewer note: 60% review trigger, 80% CodeBuild move, monthly cadence against the Actions usage page. Obligation is now assertable

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| required-sections | PASS (reported by stage) | Not re-run; no finding rests on it |
| upstream-coverage | PASS (reported by stage) | Checks that deliverables cite the consumed artifacts; it does not validate `upstream_ids` membership, which is how the NFR9.33 defect passes silently |
| traceability | FAIL on NFR9.30 and NFR9.32 only | Both GAPs remain correct. The failure is not evidence against the artifact |

### Notes

**On the central new finding — step 11 as specified cannot run.**

This is the fix's load-bearing assumption and the brief asked for it to be
checked carefully, so I traced where the Kotlin money type actually lives.
`unit-of-work.md` states the deployment model once and without qualification:
"Every Android Unit is a **feature package inside the single `:app` Gradle
module**." `team.md` Code Style settles the same question deliberately and
records it as the one place the project does not copy the Google sample: "we
keep it as **packages in ONE Gradle module for V1, not Gradle modules**", with
`core/model { domain models incl. Money }` shown as a package inside that one
module. `:app` is an `com.android.application` module targeting `compileSdk`
36 per the affirmed project rule.

A package inside an Android application module is not compilable by a plain
JVM Gradle invocation. The Android Gradle Plugin must be applied to configure
the variant that owns that source set, and the plugin requires an installed
SDK platform. So the specified step — "a plain JVM compile with no SDK and no
signing" over "the shared model package" — describes a build that does not
exist in this project's module layout.

The concrete failure scenario: B1 is implemented against this document, the
developer adds a `jvm` CI job running something like `./gradlew :app:testDebugUnitTest`
or a `:core:model:test` task, and gets either a missing-SDK failure or a
missing-project failure on the first run. The resolution taken under pressure
is the one §A exists to prevent — install the SDK into the job, at which point
the job is an Android job, the 45-second estimate is wrong by minutes, and the
no-secret framing in §A and §C is describing a job that no longer matches it.
The alternative resolution, creating a standalone `:money-model` JVM module,
is a real option but it reopens the single-module decision that `team.md`
settled with stated reasoning, and no upstream artifact in this Unit's
pass-list authorises that change.

Both resolutions are legitimate; neither is written down. That is the same
defect shape R-01 named and the fix otherwise closed well: the Kotlin
obligation is now visible, but the mechanism given to discharge it is not yet
executable as described. I am grading it Critical rather than Major because a
developer cannot build from this step without an architectural decision the
document does not contain, which is the stated READY bar.

A narrower note that does not change the grade: `@JvmInline value class` and
`kotlinx.serialization` are both plain-Kotlin features and would compile fine
in a genuine JVM module, and detekt runs on source without an SDK. The problem
is not the language features, it is the module the code is specified to live
in. If the project did adopt a separate JVM module for `core/model`, the step
would be sound and the cost estimate would be roughly right.

**On the ~45s estimate and the §E cache.**

Taking the estimate on its own terms, a cold Gradle run in CI — daemon start,
toolchain resolution, dependency resolution, Kotlin compile of a handful of
files, one test — is realistically 60–120 seconds, not 45, and §E's cache does
not help because it is keyed on "the lockfile hash, and nothing else" with no
Gradle entry. The ~80–90 second total is therefore optimistic. I have not
raised this as a finding of its own because the headroom §E documents is
enormous (90s against a 2,000-minute monthly budget) and nothing downstream
depends on the figure; the cache gap itself is covered by the Major finding
above, where it matters for the checksum control rather than for speed.

**On NFR9.33.**

I searched the whole upstream set — `nfr-design/security-design.md`,
`nfr-requirements/`, and `inception/` — and NFR9.33 appears nowhere. The
security design's numbering ends at NFR9.32. The id was minted by this stage
to carry the R-03 invariant, which is a reasonable thing to want, but
`upstream_ids` is the enumeration of upstream requirements and the file already
has the right home for stage-originated decisions: the `reverse` array, which
carries `pipeline-is-the-project-skeleton`, `single-entrypoint-no-secret`,
`post-merge-run-on-main` and `dependency-cache-only` exactly this way, each
marked N/A with its reasoning.

The failure this creates is quiet and is the reason I grade it Major rather
than Minor. The `upstream-coverage` sensor checks that deliverables cite the
consumed artifacts, not that every `upstream_ids` entry resolves to a real
upstream requirement, so nothing mechanical will ever catch it. The count
check the orchestrator ran — 35 ids, 35 rows, no missing or extra — is
satisfied precisely because the id was added to both sides. The next reader
reconciling this Unit's NFRs against the security design finds 34 there and 35
here and has to work out which one is fictional, and a later stage that tries
to trace NFR9.33 to its requirement finds nothing. Moving it to `reverse`
costs one edit and keeps the invariant fully recorded.

**On the two GAPs, and iteration 1's suggestion.**

The GAPs remain correct and should stay GAP; nothing changed upstream. On the
specific question the brief asks: declining to pre-commit the assertion helpers
is acceptable scope discipline, not an omission, and I am not raising it. My
own iteration-1 note said it does not close NFR9.32 and the GAP stands
regardless, and the §F.1 wording is now explicit that the checks are "authored
here" and "first execute from B3 and B2" with the DoD amendment named as the
blocker. The ambiguity I flagged between "designed" and "written" is narrowed
enough that a reader of §F.1 knows what is owed and by whom. Adding the helpers
would be a genuine improvement to the odds the amendment lands, but it is work
in another Bolt's service and a Unit-scoped stage is right to leave it.

**On §A's invariant against B2 and B3.**

The brief asks whether anything besides the DEX scan already violates "every
per-push blocking step runs on a fresh clone with no credential". Checking the
two DoDs: B2 is the OpenAPI file, the diff gate, the taxonomy, the route
harness, the schema-wide invariant and Schemathesis — all local, no credential.
B3's integration tests use testcontainers against a real Postgres, which needs
a Docker daemon but no credential, and `team.md` settles the gateway question
in the invariant's favour: "the blocking suite needs no secret to run locally,
which means the SMS gateway is stubbed in tests and the sandbox-credential
question affects staging only, never CI." So the invariant holds across B2 and
B3 as their DoDs stand, and the DEX scan is correctly identified as the first
and only scheduled exception. One thing worth the author's attention without
being a finding: a Docker daemon is an environmental prerequisite rather than a
credential, so it does not breach the invariant as worded, but a fresh clone on
a machine without Docker cannot run B3's blocking suite either. The invariant
is about credentials and says so; whether it should also cover environmental
prerequisites is a question for B3's own infrastructure stage, not this one.

**On what else the fixes touched.**

§F's obligations are unchanged and still correct — the two it records are the
same two, and step 11 added no obligation it cannot discharge. §D is untouched
and still sound. §E's budget table is the R-04 fix and is clean. §G is the one
place the fixes left stale, and that is the Minor finding above: the table
reasons entirely about a Python library with no UI, and its "no browser,
emulator or screenshot step" logic in §B is still right, but a reader who goes
to §G to ask "does this Unit touch Android tooling" now gets silence where the
answer became yes.

### Summary

The four prior findings are all genuinely closed — R-01's fix in particular is
well reasoned and records its rejected alternative — but the mechanism it
introduces does not survive contact with the project's settled single-`:app`
Gradle module decision, so B1's Kotlin gate is specified as a build that cannot
run, and the fix also minted an upstream requirement id that no upstream
artifact defines.
