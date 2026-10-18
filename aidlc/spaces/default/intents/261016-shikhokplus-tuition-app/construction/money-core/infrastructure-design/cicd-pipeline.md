# CI/CD Pipeline — `money-core` (U1), and the project skeleton it establishes

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`

> **This Unit provisions no infrastructure.** No compute, no database, no
> network, no DNS, no queue, no cache, no deployment target. The stage's
> per-kind applicability reflects that: a `library` Unit produces this file
> and `traceability.json`, and no infrastructure specification or monitoring
> design.
>
> What B1 genuinely builds is **the backend pipeline every later Bolt
> inherits**. `team.md` sequences the toolchain at skeleton time, and skeleton
> time is B1 — so this document specifies the project skeleton with B1's own
> steps filled in, and marks the slots later Bolts extend. Describing it as
> U1's private pipeline would describe something that does not exist and
> leave B2 to reinvent the foundation.

## Sources

- [stage] `infrastructure-design-questions.md` — Q1 (project not private), Q2
  (one entrypoint), Q3 (minute budget), Q4 (no deployment), Q5 (branch
  protection), Q6 (secrets scanning), Q7 (caching)
- [upstream] `construction/money-core/nfr-design/security-design.md` — Part B
  gate pipeline, NFR9.26–NFR9.32
- [upstream] `construction/money-core/nfr-design/logical-components.md` — §E
  (what Infrastructure Design needs from this Unit, and what it does not)
- [upstream] `construction/money-core/nfr-requirements/tech-stack-decisions.md`
- [upstream] `construction/money-core/functional-design/functional-spec.md` —
  §2 operations and §7 (why no UI surface), which fix what the test steps run
- [upstream] `inception/domain-design/components.md` — the component
  catalogue, which places the Money component and its two chokepoints
- [upstream] `inception/contract-design/contract-summary.md` — §B.5 and §E.1,
  the money wire form the schema assertions check against
- [upstream] `inception/delivery-planning/bolt-plan.md` — B1 DoD
- [team] `## Testing Posture` (one command, CI, budget), `## Deployment`
  (scanning speeds, lockfiles, tagging), `## Way of Working` (trunk-based,
  squash-merge)

---

## A. The one entrypoint

**A single `make check` target runs the identical sequence locally and in
CI.** Not a similar sequence — the same one, with CI invoking the same target
a developer does.

`team.md` gives the reason in terms specific to this project: *a gate
reproducible only by pushing is a gate that gets bypassed*, and for a solo
build that is the single most important property of the gate. A CI-only
pipeline means the only way to find out whether a change passes is to push and
wait, which trains the developer to push speculatively and to stop reading the
result.

**The blocking suite requires no secret.** This is already required — the SMS
gateway is stubbed in tests — and for B1 it is absolute: this Unit has no
credential dependency of any kind. Step 11 needs the **Android SDK**, which is
a toolchain rather than a credential — installable unauthenticated and
cacheable between runs — and needs no keystore, no emulator and no signing. A
fresh clone runs the complete gate immediately.

**The invariant is about credentials, not toolchains**, and the distinction is
worth stating because it is the one that stays checkable. A toolchain is
installable by anyone who clones the repository; a credential is not. B3's
testcontainers will need a Docker daemon by the same reasoning — an
environmental prerequisite, not a secret — and whether the invariant should
also cover prerequisites is B3's question rather than this Unit's.

**The first exception is already scheduled, and naming it now is the point.**
B4's DEX scan is pinned by its DoD to the **R8-minified release build**, which
needs a **signing keystore** — a credential `team.md` does not list among its
three named secrets (gateway credentials, JWT signing key, database URL). So
the erosion this paragraph warns about is not hypothetical; it arrives at B4
with a fourth secret nobody has named.

**Settled here rather than discovered there:**

- The keystore is a **fourth named secret**, and gets the same treatment as
  the other three: parameter store in Phase 2, environment variable in Phase
  1, and a written, exercised-once rotation runbook.
- The DEX scan sits **outside the per-push blocking suite** and inside the
  release gate, where B4's DoD already places the rest of the release-build
  checks. A per-push gate that cannot run on a fresh clone is exactly the
  CI-only gate this section exists to prevent.
- **The invariant to defend, stated so it can be checked**: every step in the
  per-push blocking suite runs on a fresh clone with no credential. A step
  needing one belongs in the release gate, and moving it there is the default
  answer rather than a negotiation.

---

## B. The B1 gate, in order

Ordered cheapest-first so a cheap failure never waits behind an expensive one.

| # | Step | Blocks on | ~Cost |
|---|---|---|---|
| 1 | Secrets scan | Any match — no severity threshold | ~1s |
| 2 | Lockfile / checksum verification, **both surfaces** | Drift or a failed checksum, Python or Gradle | ~2s |
| 3 | Format + lint, **including Gate 2** (raw decimal banned outside the money module) | Any violation | ~1s |
| 4 | Type check, strict over this module | Any error | ~5s |
| 5 | Unit tests + **branch coverage below 100%** | Failure or shortfall | ~5s |
| 6 | **Gate 1**, both violation fixtures, **both gate-configuration assertions** | A gate that does not fire, or one whose scope no longer covers the tree | ~2s |
| 7 | Named-test manifest check | An entry with no matching test | ~1s |
| 8 | Locale completeness | A supported locale with no rendering specification | ~1s |
| 9 | Coverage-scope check (NFR9.31b) | A module importing the money type that is neither in the covered set nor on the allowlist | ~1s |
| 10 | Property test over randomized histories | Any identity violation | ~20s |
| 11 | **Kotlin compile + local JVM serialization test** — see below | A float assignable to the money type; a serializer accepting a JSON number | 60–120s |

**Total: roughly two to three minutes**, dominated by the Gradle step. Steps 1–2 block absolutely because they are
binary, near-zero false positive and always actionable by whoever just pushed.

### Step 11 exists because B1 ships Kotlin, and an earlier draft of this
### document missed that

**This Unit is not Python-only.** `unit-of-work.md`'s U1 row states that the
Kotlin `Money` value class *ships in the app*, and B1's Definition of Done
requires the `@JvmInline value class Money(BigDecimal)` **with a serializer
that reads only a JSON string and fails loudly on a number**. `team.md`
further requires a loud-failure serialization test per money-carrying model
class.

An earlier version of this pipeline was entirely Python and placed the first
Android job at B4. **The concrete failure that allows**: B1 merges with a
serializer that quietly accepts a JSON number and converts it, `make check` is
green, and the first job capable of catching it runs **three Bolts later**.
That is precisely the lenient-decoder failure `team.md` names as *the actual
failure mode* — occurring on the one surface whose reviewer has no declared
Kotlin experience, which is exactly where a mechanical gate matters most.

**What step 11 is, and deliberately is not:**

| Included | Excluded, and why |
|---|---|
| Assemble the `:app` module's debug variant far enough to compile `core/model` | No emulator — nothing here needs a device |
| The money value class and its serializer | No AAB, no signing, no R8 — those are B4's and need a keystore |
| One **local JVM unit test** (`testDebugUnitTest`) asserting a JSON string decodes and a **JSON number fails loudly** | No instrumented test — nothing here runs on a device |
| The package-scoped float ban (detekt), narrowly configured | No Compose UI test, no full Android lint sweep — B4 owns those |

**It needs the Android SDK, and an earlier draft of this step wrongly said it
did not.** The draft specified a plain-JVM compile with no SDK. That build
does not exist in this project's module layout: `unit-of-work.md` places every
Android Unit as a **feature package inside the single `:app` Gradle module**,
and `team.md` settles the same point deliberately — *packages in ONE Gradle
module for V1, not Gradle modules*. A package inside a
`com.android.application` module requires the Android Gradle Plugin and
`compileSdk` 36 to compile at all.

**The alternative was to split `core/model` into a separate pure-JVM Gradle
module, and it is rejected**: that reopens a settled decision recorded in two
artifacts, for the convenience of this pipeline step. A CI step is not a
reason to change the project's module structure.

So step 11 is an **SDK-using job without a credential**: it needs the Android
SDK (installable unauthenticated, cached between runs) but no keystore, no
emulator and no signing. §A's invariant is about *credentials*, not about
toolchains, and this step does not breach it.

**Cost: realistically 60–120 seconds** for a cold Gradle run, not the ~45s an
earlier draft claimed. The headroom is large enough that the imprecision
changes nothing — but §E's dependency cache must now carry a **Gradle** key,
which is a correctness matter rather than a speed one (see §E).

> **The alternative, rejected but recorded.** The Kotlin deliverables could
> move to B4 and B1's DoD be amended — the same move §F.2 contemplates for
> `format(locale)`. Rejected because the Kotlin money type is the *client half
> of the same boundary* this Unit exists to establish, and splitting a
> boundary across four Bolts means the backend half ships with nothing
> enforcing the contract on the other side. Deferring the gate is cheap;
> deferring the gate on a type that is already shipping is not.

**What fixes this list** is the module's own surface rather than a generic
template: `functional-spec.md` §2 enumerates the eleven operations the unit
tests at step 5 must cover, and §7 records that this Unit has no UI, which is
why no browser, emulator or screenshot step appears anywhere above.
`components.md` places the Money component and its two chokepoints in the
catalogue, which is what makes steps 3 and 6 checks on a *named* boundary
rather than on a convention.

**Not in B1, and why** — the two schema assertions of NFR9.30 need a migrated
database and a generated OpenAPI document, neither of which B1 has. They are
**authored here** and **first execute from B3** (database column type and
precision) and **B2** (OpenAPI money pattern and `*_display` pairing), with
`contract-summary.md` §B.5 supplying the canonical money pattern and the
`*_display` pairing rule those assertions check against. This only works if
those Bolts' definitions of done list them, which they currently do not — see
§F.

---

## C. Job layout and what later Bolts add

```
┌─ backend (ubuntu-latest) ──────────────────────┐
│  B1: steps 1–10 above                          │
│  B2: + OpenAPI diff gate, money-pattern         │
│       assertion, route-enumeration harness      │
│  B3: + PostgreSQL 16 service container,         │
│       Alembic-from-zero, restricted-role        │
│       meta-test, column-type assertion          │
└─────────────────────────────────────────────────┘
┌─ android-unit (ubuntu-latest) — from B1 ───────┐
│  step 11: compile core/model inside :app,       │
│  local JVM money serialization test,            │
│  scoped float ban.                              │
│  SDK yes; emulator, signing, secret: NO.        │
│  B4 grows this job: detekt, spotless, full      │
│  unit tests, coverage report, manifest          │
│  allowlist.                                     │
└─────────────────────────────────────────────────┘
┌─ release gate — from B4, on tag ───────────────┐
│  minified-DEX scan ** needs the keystore **,    │
│  dependency CVEs (block), Trivy, Syft SBOM,     │
│  ZAP baseline, size assertion                   │
└─────────────────────────────────────────────────┘
```

**Text fallback.** One backend job exists from B1 and grows: B2 adds the
schema gates and route harness, B3 adds a real PostgreSQL service container
with the Alembic-from-zero migration and the restricted-role meta-test. An
**android-unit job also exists from B1**, carrying step 11 — it compiles
`core/model` inside the `:app` module and runs the money serialization test as
a local JVM unit test. It needs the Android SDK but **no emulator, no signing
and no credential**; B4 grows the same job with detekt, spotless, the full
unit-test suite, the coverage report and the manifest allowlist, and it never
gates a backend change. A release gate, from B4, runs only on a tag and
carries the minified-DEX scan — **the first and only step needing a
credential** — together with the slow scanning that has no place in a per-push
path.

**Why step 11 is the early form of the Android job rather than a separate
JVM one**: the money type lives in `core/model` inside the single `:app`
module, so compiling it requires the Android Gradle Plugin either way.
Splitting it into a pure-JVM module to avoid that would reopen the
one-Gradle-module decision `team.md` and `unit-of-work.md` both settle — a
pipeline step is not a reason to restructure the project. What B1 *does*
exclude is everything that needs a device or a key.

**The split is a cost decision, not an aesthetic one.** `team.md` requires the
backend path to stay under about ten minutes or it will be skipped, and an
Android build is minutes on its own. Splitting also means a backend-only
change never waits on a Kotlin toolchain.

---

## D. Triggers, protection and the merge gate

| Trigger | Runs | Why |
|---|---|---|
| Pull request | Backend job (+ Android from B4) | The diff view is where review actually happens and CI attaches its result there |
| Push to `main` | Same jobs | **The only thing that catches a stale-base merge** |
| Tag | Release gate | Slow scanning, release-blocking |

**Branch protection: on, requiring the CI check; no required-approvals rule.**
A required approval from the sole author is theatre, and `team.md` already
records that pull requests here are a record rather than a negotiation.

**The post-merge run on `main` is the load-bearing half.** With squash-merge
and one reviewer, a PR green against an older `main` can break on merge and
nobody would notice if only PRs were checked. This is cheap and it is the one
protection a solo trunk-based workflow genuinely needs.

---

## E. Caching, scanning speeds, and budget

**Two dependency caches, one per surface, and nothing else.** An earlier draft
said "the lockfile hash", singular — which covered only Python and silently
left the Gradle side uncached and, more importantly, **unverified**. Step 11
introduces a Gradle build, so both surfaces need their own key:

| Surface | Cache key | Verification at step 2 |
|---|---|---|
| Python | `uv.lock` hash | Lockfile drift, checksums |
| **Gradle** | Gradle dependency-lock files + wrapper version | **Dependency locking *and* `dependencyVerification` checksums** |

**The checksum half is the point, not the caching half.** `team.md` is
explicit that `dependencyVerification` is *the only control we have that
detects a tampered or substituted artifact in the Gradle supply chain*, and it
costs one generated file. Step 2 verifying only the Python lockfile would
leave the Kotlin surface — which from B1 onward carries the client half of the
money boundary — with no supply-chain control at all.

The caching rationale below applies to both. It saves
most of the install time and invalidates exactly when it should. Test-result
and incremental-lint caching are rejected: at this scale they save seconds and
introduce a stale cache masking a real failure — the exact defect class this
Unit's whole control set exists to prevent.

**Two scanning speeds, from `team.md`:**

| | Secrets, lockfiles | Dependency CVEs |
|---|---|---|
| **When** | Every push | Annotate every push; **block at the release gate** |
| **Threshold** | None — any match blocks | Critical and High at the gate, each fixed or carrying a dated written exception |

The reasoning is explicitly about solo work: a developer who hits an unfixable
transitive Critical mid-Bolt, with no triage path and no second reviewer,
bypasses the gate once — and after one bypass it is decoration. Two speeds
keep the always-actionable things absolute and give the judgement-requiring
things a place to be judged.

**Budget.** GitHub Actions' free tier for a private repository is 2,000
minutes per month. B1's gate is roughly 90 seconds including the JVM step.

"Checked rather than assumed" was an earlier wording with **no subject, no
cadence, no threshold and no mechanism** — an obligation in a document where
every other control fires mechanically. Replaced with a number and a trigger:

| Consumption | Action |
|---|---|
| Below 60% of 2,000 min | Nothing |
| **At 60%** (1,200 min) | Review which job is consuming it; the Android job is the expected answer |
| **At 80%** (1,600 min) | Move the Android job to CodeBuild, as `team.md` already contemplates — "splitting by cost is cheaper than migrating by platform" |

Checked **monthly, against the Actions usage page**, by the same person who
holds every other role. The thresholds matter more than the cadence: a
60% trigger leaves room to act before a hard stop, and a hard stop at 2,000
means no CI at all until the month rolls over, on a solo project where CI is
the only gate.

---

## F. What B1 establishes, and the two obligations it cannot discharge

**Established here, inherited by every later backend Bolt:**

- the single `make check` entrypoint and the cheapest-first ordering;
- lint and format with the named rule sets, type checking with the strict
  island;
- pytest with the coverage floor wired in, scoped by behaviour (NFR9.31a/b);
- both import gates, their violation fixtures and their configuration
  assertions;
- secrets scanning in both pre-commit and CI;
- dependency lockfiles and checksum verification **on both surfaces** —
  `uv.lock` for Python, Gradle dependency locking plus `dependencyVerification`
  checksums for Kotlin, the latter being the only control that detects a
  tampered Gradle artifact;
- **commit-SHA image tagging convention** — `latest` is never deployed. B1
  builds no image, but the convention is set here because it is a
  supply-chain control that makes a deployed artifact identifiable, and
  retrofitting it after images exist is harder than declaring it now.

**Two obligations this stage records and cannot execute:**

1. **NFR9.32** — the OpenAPI assertion must be added to **B2's** definition of
   done, and the column type-and-precision assertion to **B3's**. Neither
   currently lists them. Until they do, NFR9.30 is a design intention with no
   owner, and both Bolts would pass their stated DoD while the checks never
   exist.
2. **OQ-B1-1** — the Bangla money rendering. It affects what step 8 asserts,
   not how the pipeline runs, but step 8 **cannot pass** while a supported
   locale has no rendering specification. Either the question closes before
   B1's formatting operation is built, or the operation defers out of B1 and
   **B1's own DoD is amended**, since `bolt-plan.md` lists `format(locale)`
   unconditionally.

> Both are cross-Bolt or human decisions that a Unit-scoped stage can name but
> not resolve. Naming them here, in the artifact that specifies the gates, is
> what keeps them from being discovered at the moment the gate first fails.

---

## G. What this Unit does NOT specify

| Usual infrastructure content | Status | Why |
|---|---|---|
| Compute model | **None** | A library has no process of its own |
| Networking topology | **None** | No listener, no egress |
| Storage strategy | **None** | Owns no table, no bucket, no volume |
| Environment layout | **None** | Nothing to promote between environments |
| Database sizing / replication | **None** | B3 owns the first database |
| Cache, queue, CDN, DNS, load balancer | **None** | None exists at this scale, and none is this Unit's |
| Monitoring and alerting design | **None** | Correctness here is established **before** release, not observed at runtime. There is no runtime signal to collect |
| Deployment and rollback | **None** | Ships inside whatever image contains it, first built at B3. Rolls back with that image |

> The per-kind applicability already excludes the infrastructure specification
> and monitoring design for a `library`. Enumerating the absences anyway is
> deliberate: a reader checking whether this Unit needs an alert should find
> the answer and its reason, not an absence they must interpret.

---

## Assumptions & Open Questions

**OQ-B1-1** — the Bangla money rendering, unchanged by this stage. See §F.2.

**NFR9.32** — the cross-Bolt DoD amendments. See §F.1.
