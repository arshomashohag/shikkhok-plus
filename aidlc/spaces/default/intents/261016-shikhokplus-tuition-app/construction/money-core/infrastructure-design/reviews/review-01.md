## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T05:37:13Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/cicd-pipeline.md > §B step table and §C job layout | B1 ships Kotlin deliverables that no B1 gate compiles or tests; §C puts the first Android job at B4 | Add a B1 Kotlin step to §B, or move the Kotlin deliverables out of B1 and record the B1 DoD amendment alongside the §F.2 one. See note A | New |
| R-02 | Major | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/traceability.json > coverage rows NFR9.7 and NFR9.9 | Both rows defer a B1 deliverable to "the Android job, which first exists at B4", so neither NFR has a B1 owner | Re-mark both against whichever B1 step §B gains, or mark them GAP with the same reasoning §F already applies to NFR9.30. See note A | New |
| R-03 | Major | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/cicd-pipeline.md > §A "The blocking suite requires no secret" | The no-secret property is asserted for B1 while §C schedules an Android release-build job that needs a signing keystore, so the named erosion already has a date | Name the Android signing credential in §C as the first scheduled exception and state whether it sits inside or outside the blocking suite. See note B | New |
| R-04 | Minor | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/infrastructure-design/cicd-pipeline.md > §E Budget paragraph | "Checked rather than assumed" names no owner, cadence, threshold or mechanism, so the obligation cannot be shown unmet | State who checks the minute figure, how often, and at what consumed fraction the Android split moves to CodeBuild. See note C | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| required-sections | PASS (reported by stage) | Not re-run; no finding rests on it |
| upstream-coverage | PASS (reported by stage) | All 34 NFR9.x enumerated with a coverage row, as claimed |
| traceability | FAIL on NFR9.30 and NFR9.32 (both GAP) | The two deliberate GAPs are correct and should stay GAP; see note D. The failure is not evidence against the artifact, but the NFR9.7/NFR9.9 finding above is a separate, non-deliberate coverage defect the passing rows conceal |

### Notes

**Note A — the Kotlin half of U1 has no gate anywhere.**
`unit-of-work.md`'s Unit catalogue row for U1 states the deployment model as
"In-process Python package in the backend image; **Kotlin `Money` value class
ships in the app**." `bolt-plan.md` line 93 (B1 DoD) requires it concretely:
"Kotlin `@JvmInline value class Money(BigDecimal)` with a serializer that reads
only a JSON string and fails loudly on a number." `team.md` Testing Posture
adds the test obligation in the same breath: "every money-carrying model class
ships a serialization test proving decode from a JSON string and **loud
failure** on a JSON number, because a lenient decoder that quietly accepts a
number and converts is the actual failure mode and it passes a happy-path-only
both-sides test."

`cicd-pipeline.md` §B's ten steps are entirely Python — lint, mypy, pytest,
both import gates, the manifest check, the locale check, the coverage-scope
check, the property test. §C then states "A separate Android job appears at B4",
and the §G absence table does not mention Kotlin at all.

The concrete failure scenario: B1 merges with a hand-written Kotlin serializer
whose `@Serializable` annotation is missing or whose decode path accepts a JSON
number. Nothing in B1's `make check` compiles Kotlin, so the gate is green. The
first job that would catch it is the B4 Android job, three Bolts later — and by
then B2 has shipped the OpenAPI money pattern and B3 the column assertion, both
of which test the *Python* side and pass. The defect surfaces when a real money
value first reaches a device, which is B3's skeleton at the earliest and B6/B7
realistically. That is precisely the "lenient decoder" failure `team.md` names,
reaching production through the one surface whose reviewer has no declared
Kotlin experience.

This is also the stronger version of the Q1 framing question the brief asks.
The "project skeleton not private pipeline" claim is right in direction —
`team.md` does sequence the toolchain at skeleton time and B1 is skeleton time
— but the document applies it asymmetrically. It confidently claims ownership
of the *backend* skeleton for every later Bolt, while treating B1's own Kotlin
deliverable as someone else's Bolt. Deferring is a defensible answer; deferring
silently is not. Either outcome is acceptable and both need writing down:

- a minimal Kotlin step in B1 (compile plus the one serialization test — it
  needs no emulator, no AAB, no signing, so it costs a Gradle JVM-test
  invocation and does not touch the B4 release-build machinery), or
- the Kotlin deliverables move out of B1 to B4, which **amends B1's DoD** in
  exactly the way §F.2 already contemplates for `format(locale)` — a fallback
  that silently fails the Bolt's own DoD is not a fallback, and §F.2 says so.

**Note B — the no-secret claim and the erosion already scheduled.**
§A says the property "should be defended as later Bolts add jobs, because the
first secret-requiring blocking step silently converts the gate back into a
CI-only one for anyone without credentials." The concern is the right one to
flag and the reasoning is sound. What weakens it is that the document has
already drawn the offending job three lines later: §C's Android job at B4 runs
"merged-manifest allowlist, minified-DEX scan", and the DEX scan is specified
in `bolt-plan.md` B4 DoD as running "on the **R8-minified release build**, never
the debug build". A release build needs a signing config. `team.md` Deployment
lists the keystore nowhere among its three named secrets, so this is an
unnamed fourth.

The failure scenario is mild but real and is exactly the one §A predicts: a
contributor (or the same developer on a fresh machine, or a reconstructed
worktree) runs `make check`, the Android job fails for want of a keystore, and
the response is to mark that job CI-only. At that point the §A invariant is
gone and nobody decided to give it up. Naming the keystore here, as the first
scheduled exception with its placement relative to the blocking suite settled
in advance, costs a sentence and converts an erosion into a decision. A debug
signing config checked into the repo is one legitimate answer; so is placing
the DEX scan outside the blocking suite. The artifact should pick one.

**Note C — the budget obligation as stated is not checkable.**
The 2,000 minutes/month figure for a private repository on the GitHub Free plan
is correct as of this date, so the number is not the defect. `team.md` requires
"the per-month minute budget is stated and monitored against [OC-4]". §E states
it and then says it is "**checked rather than assumed**". That sentence has no
subject, no frequency and no trigger. Compare the surrounding controls, every
one of which fires mechanically: the secrets scan blocks on any match, the
coverage gate blocks below 100%, the coverage-scope check fails on the commit
that adds an unlisted module. `team.md`'s own organising principle is that
"where a rule is important, it is mechanical", and the monitoring obligation is
the one line in this document that is left to a stretched solo developer's
memory.

The scenario this leaves open is slow rather than sharp: B4 onward adds an
Android job and B3 adds a PostgreSQL service container, both of which are
minutes rather than seconds. Consumption climbs across Bolts, nobody looks,
and the first signal is a billing event or a throttled month mid-Bolt — at
which point `team.md`'s stated remedy (move the Android job to CodeBuild) is a
platform migration undertaken under pressure rather than the planned one.
A threshold with a number ("at 60% of 2,000 consumed in a month, the Android
job moves") makes the decision cheap and makes the obligation assertable. This
is Minor because nothing breaks correctness and the headroom at B1 is genuine.

**Note D — the two GAPs are correctly left GAP.**
The brief asks whether this is abdication dressed as honesty. It is not, and
the reasoning in `traceability.json`'s `note` is correct on its own terms:
N/A asserts inapplicability, and NFR9.30 is not inapplicable to U1 — it exists
*because of* U1's chokepoints and U1 authored it. Marking it N/A would make
the sensor green while asserting something false, which is strictly worse than
a red sensor carried to a human. I verified independently that neither B2's nor
B3's DoD in `bolt-plan.md` lists either assertion: B2 enumerates the OpenAPI
file, the diff gate, the taxonomy, the `*_display` rule, the route harness, the
privacy invariant and Schemathesis; B3 enumerates the first migration and the
governance schema test. Both would pass their stated DoD with the assertions
absent.

I also checked whether there is something B1 could do now that was missed.
There is one thing, and it is smaller than the obligation rather than a
substitute for it: `contract-summary.md` §B.5 supplies the canonical money
pattern and the `*_display` pairing rule, so B1 can commit **the assertion code
itself** — the function that iterates a schema and the function that iterates a
column catalogue — as library-level helpers with their own unit tests against
synthetic inputs, leaving B2 and B3 only to wire them to a real subject.
§B already claims the checks are "authored here", so this may be the intent;
if so it is not visible as a pipeline step or a §F bullet, and "authored" is
doing ambiguous work between "designed" and "written". Making it concrete
narrows the gap from "write and wire" to "wire", which materially raises the
chance the DoD amendment actually lands. It does not close NFR9.32, and the
GAP should stand regardless.

**On the attacked points that hold.**
The step ordering is sound and the step list is executable by a Unit with no
database, endpoint or UI on the Python side — I traced each of the ten against
`functional-spec.md` §2 and §7 and found nothing that B1 cannot run and nothing
missing from the backend surface. §D's post-merge-run reasoning is correctly
described: under squash-merge a PR's merge-result commit is not what CI tested
on the PR branch, so a PR green against an older `main` genuinely can land
broken, and the post-merge run is the only check that sees the squashed commit
as `main` actually holds it. §E's caching call is right at this scale — a 35-40
second gate has nothing to gain from test-result caching, and the stale-cache
failure mode is the one class of defect this Unit's whole control set exists to
prevent. §G's absences are correctly absent for a library on every row I
checked against `logical-components.md` §E, which asks Infrastructure Design for
the column type "and nothing else".

### Summary

The document's backend half is sound and its deliberate GAPs are the right
call, but it specifies a Python-only gate for a Bolt whose own Definition of
Done ships a Kotlin value class and serializer — so B1's most review-opaque
deliverable merges with no mechanical check and the traceability rows for
NFR9.7 and NFR9.9 hand it to a Bolt three positions later.
