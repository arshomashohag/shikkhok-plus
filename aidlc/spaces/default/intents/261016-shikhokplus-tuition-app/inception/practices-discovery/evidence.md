# Evidence — Practices Discovery

**Stage**: practices-discovery (2.2)
**Phase**: Inception
**Participants**: `aidlc-pipeline-deploy-agent` (lead, Steps 2 and 5),
`aidlc-quality-agent`, `aidlc-developer-agent`, `aidlc-devsecops-agent` (blind
support reviews, Step 3), and the human (interview, Step 4)
**Date**: 2026-10-17

**The headline finding: there were no observed practices to discover.** This is
a greenfield project. The repository contains the AI-DLC scaffold and a LICENSE
— no application code, no CI configuration, no build files, no linter config, no
deployment manifests, and a git history of two scaffold commits. There was
therefore nothing to infer a team's habits *from*.

That shapes how this stage actually worked. The lead proposed, three specialists
inspected the proposal independently without seeing each other's comments, and
the human chose. The interview was not a confirmation step — it is where the
practices were decided. **Two findings were defects rather than preferences and
were fixed regardless of any answer**; both are documented in full below.

---

## Sources

| Ref | Source | Role |
|---|---|---|
| [stage] | `.claude/aidlc-common/stages/inception/practices-discovery.md` | Stage contract, artifact shapes, the two required Testing Posture fields |
| [org] | `aidlc/spaces/default/memory/org.md` | Suggested defaults for all five sections (greenfield path, Step 2) |
| [team] | `aidlc/spaces/default/memory/team.md` | Checked for an affirmed baseline; found empty |
| [project] | `aidlc/spaces/default/memory/project.md` | Checked; every section empty |
| [phase] | `aidlc/spaces/default/memory/phases/{inception,construction,operation}.md` | Phase guardrails bearing on testing, security and deployment |
| [state] | `<record>/aidlc-state.md` | Project type, scope, depth, test strategy, collaborator switch |
| [arch] | `ideation/feasibility/architecture-proposal.md` | Approved stack, hosting phases, auth design, §7, §8a–f, §10 |
| [constraints] | `ideation/feasibility/constraint-register.md` | TC-1–TC-20, OC-1–OC-7, RC-1–RC-8 |
| [decisions] | `ideation/approval-handoff/decision-log.md` | D-1–D-48 |
| [backlog] | `ideation/scope-definition/intent-backlog.md` | PU-1–PU-8, dependency order, critical path |
| [quality] | `contributions/aidlc-quality-agent.md` | Blind review: testing posture, coverage, CI quality gates |
| [developer] | `contributions/aidlc-developer-agent.md` | Blind review: conventions, layer boundaries, error handling |
| [security] | `contributions/aidlc-devsecops-agent.md` | Blind review: scanning, supply chain, secrets |
| [interview] | `practices-discovery-questions.md` | Q1–Q13 plus the Consolidated Summary Confirmation; the human's answers are authoritative |
| [pg-rls] | https://www.postgresql.org/docs/16/ddl-rowsecurity.html | Retrieved 2026-10-17; verified verbatim that superusers and table owners bypass row-level security |
| [kb] | `.claude/knowledge/aidlc-pipeline-deploy-agent/{cicd-patterns,deployment-strategies,branching-strategies}.md` | CI stage ordering, quality-gate table, deployment-strategy menu |
| [kb-rules] | `.claude/knowledge/aidlc-shared/rules-reading.md` | The empty-template test and the layer fallback chain |
| [git] | `git rev-parse HEAD`, `git log --oneline`, `git branch --show-current` | Repository state |

---

## What was inspected

### By the lead (Step 2)

**Repository and history.** `git log` returns exactly two commits —
`f1a941d Initial commit` and `4ee9225 chore(aidlc): add initial AI-DLC
workspace scaffold`. The working branch is `main`. There are no other branches,
so no branching convention is observable; `main` as the trunk name is the only
fact the repository establishes, and it happens to match the `org.md` default. No
merge commits exist, so whether the team squashes, rebases or merges is
unobservable.

**Working tree.** The project root holds the AI-DLC scaffold (`.claude/`,
`aidlc/`, the harness onboarding files) and a LICENSE. Absent: any `src/` or
application tree, `pyproject.toml`, `requirements.txt`, `build.gradle.kts`,
`settings.gradle.kts`, `gradle/libs.versions.toml`, `Dockerfile`,
`docker-compose.yml`, `alembic.ini`, `.ruff.toml`, `.editorconfig`,
`.pre-commit-config.yaml`, `.github/workflows/`, `buildspec.yml`, any IaC
template. Every one of these is a file whose *presence* would have been evidence;
their absence is why this stage had no observed practices.

**Rule layers, per the `rules-reading.md` empty-template test** [kb-rules §1].
`project.md` and `team.md`: every section's body is HTML comment only — empty.
The fallback therefore descends to `org.md`, which is populated for all five
topics and was the operative layer for the draft. This is exactly the layer-3
case the fallback chain describes, and it is why the drafts were proposals rather
than re-affirmations: there was no prior team position to keep or revise.

**`org.md`, the five matching sections.** Way of Working (trunk-based, base and
target `main`, squash-merge), Walking Skeleton (scope-dependent, `skeleton:`
field governs the ceremony), Testing Posture (default `test-after` with a
layer-then-test ordering; `classic` adds an 80% line floor and CI before merge),
Deployment (deploy on merge to staging, production behind a manual approval),
Code Style (defer to project linter and formatter configuration).

**State.** Project Type Greenfield (source: workspace scan), Scope `classic`,
Plan `android-backend-product`, Depth Comprehensive, Test Strategy
Comprehensive, Review Override adversarial, Collaborators **on**, Learnings on,
Sensors on, Guard Policy off (from scope), Construction Checkpoints enabled,
Construction Iteration unit-major, Construction Execution serial.
`Practices Affirmed Timestamp` empty, confirming a first run.

**Approved Ideation artifacts.** Read in full: the architecture proposal
(including §8a–f and §9's argument against itself), the constraint register's 35
constraints and its six deliberately-not-imposed entries, all 48 decisions
including the five that superseded the initial description, and the intent
backlog's eight proto-Units with their dependency graph and critical path.

**Knowledge base.** The CI stage ordering and quality-gate table from
`cicd-patterns.md`, the deployment-strategy menu from `deployment-strategies.md`,
and the branching-strategy survey and response contract from
`branching-strategies.md`.

### By `aidlc-quality-agent` (testing, coverage, CI remit)

Inspected the lead's Testing Posture section against the constraint register, the
intent backlog's per-Unit task breakdown, and the architecture's §7 auth design.
What it found:

- **The `Ordering` sentence failed open.** It enumerated seven test-first cases
  plus "everything else", so every case nobody anticipated defaulted to
  test-after. Named two concrete cases the enumeration would miss: PU-6.9's
  carry-forward-versus-waive implemented as a UI affordance, and a lens rule
  arriving as a shared dependency rather than as an endpoint change.
- **Right instrument on money coverage, wrong absence on Kotlin.** Endorsed 100%
  branch on the money module and the reasoning behind it, then objected that the
  lead's own argument ("gating a surface nobody can review produces
  number-raising tests") justifies dropping the *percentage*, not the
  *obligation* — leaving the thinnest-reviewed surface in the product with no
  test obligation at all.
- **Branch coverage does not cover money boundaries.** Executing both arms of
  each `if` says nothing about the short-month clamp at day 29/30/31, rounding at
  the half, zero and negative amounts, or an approved amount exceeding the
  claimed amount. Proposed a named test per state transition, a documented
  boundary case per money input, and a Hypothesis property test on the ledger
  invariant `charged - received - forgiven == outstanding`.
- **The RLS superuser defect** — see "Two verified defects" below. This was the
  highest-value single finding in the stage.
- **Schemathesis validates conformance, not correctness.** A teacher-facing
  response schema that wrongly includes profile fields is perfectly conformant, so
  Schemathesis cannot detect the privacy boundary and must not be counted as
  privacy coverage. Proposed an OpenAPI schema-diff gate instead, on the ground
  that a stale committed schema is worse than none because contract tests then
  pass against fiction.
- **Five missing test obligations**, in its own priority order: the seven OTP
  abuse controls (no obligation at all, despite living in the walking-skeleton
  Unit and carrying direct financial exposure); refresh-token rotation reuse
  detection; `inactive_from` date semantics [PU-2.9]; both account-deletion paths
  [TC-19]; and the cross-batch dues query [PU-7.2], driven by balance rather than
  active status.
- **PU-3.6's instrument mismatch.** A Compose UI test asserts behaviour, not
  latency, so it cannot discharge a mid-class speed requirement. Either a
  Macrobenchmark on a low-end profile or an explicit manual pilot check.
- **Toolchain over-scoping.** mypy strict plus Ruff plus ktlint-or-spotless plus
  detekt plus dependency scanning plus secret scanning plus Schemathesis is too
  much to stand up before PU-1 ships; proposed a sequencing so the skeleton Bolt
  does not become a toolchain Bolt.
- **A platform-independent CI gate specification**, with "one command the human
  can run locally that is the same command CI runs" as its most important
  property for a solo build, plus a green-`main` requirement that squash-merge
  with one reviewer makes necessary.

### By `aidlc-developer-agent` (conventions, boundaries, error handling remit)

Inspected the Code Style section and the two structural rules it leaned on, with
a single recurring criticism: *a rule stated as a structural guarantee but
enforced by review*. What it found:

- **Ruff's rule set was never named**, which leaves it at roughly Flake8's
  defaults. Specified the sets with a per-project justification each, including
  two that matter unusually here: `ASYNC`, because a sync SQLAlchemy call inside
  an `async def` silently serializes the event loop on a 2 GB instance; and
  `DTZ`, because fee periods are calendar-month-with-clamp in a non-UTC country
  and a naive `datetime.now()` eventually produces an off-by-one-day due date.
- **Partial-strict mypy as drafted would not work.** mypy strictness is mostly a
  property of what a module can *see*, so "strict on the money module" while it
  imports unchecked code yields either a wall of `Call to untyped function`
  errors silenced into decoration, or `Any` flowing in and strict mode checking
  nothing. The fix is `disallow_untyped_defs = true` as the **global** baseline
  plus an import-closed strict region.
- **Line length was unstated**, which is the one style choice that silently
  changes how code is *written* and cannot be changed cheaply later. Flagged the
  79-versus-88 divergence as a decision being made by accident.
- **`Decimal(<float>)` passes any float ban while losing precision**, because the
  resulting type *is* `Decimal` — the value is just already wrong. Identified this
  as the single most likely way the float prohibition gets violated while passing
  every check in the draft.
- **Money should be a type, not a rule**, with a specific edge table deciding
  what counts as money arithmetic: summation, comparison and percentage inside
  the module; no `__mul__` or `__truediv__`; quantize at construction. The
  decisive argument is that the module then owns the two chokepoints every money
  value must pass anyway — the Pydantic serializer and the SQLAlchemy
  `TypeDecorator` — so a money value physically cannot enter or leave the system
  without passing through it.
- **"Every endpoint names its lens" was still optional.** The failure mode is a
  *forgotten* lens, which produces an endpoint that works perfectly and
  authorizes nothing. Proposed that the lens dependency **return the scoping
  value the query needs**, so a forgotten lens cannot compile, plus a
  route-enumeration test with an explicit `PUBLIC_ROUTES` frozenset and a
  return-annotation match rather than a name match.
- **"Every rule server-side" had no checkable form.** Supplied one: **the API
  returns decisions, not inputs to decisions** — if the client is comparing a
  domain value, the server should have sent a status. Named five erosion paths it
  prevents, in expected order of occurrence.
- **The error-handling rule was not actionable.** Supplied a five-class taxonomy
  where **retryability is a property of the error class**, a single envelope
  carrying a server-provided `retryable` boolean, and four per-boundary rules —
  including that SMS never auto-retries and a timeout is `unknown` rather than
  `failed`, and that an `(enrollment_id, period)` conflict IS the success path
  rather than an error.
- **The Google-sample deference rule had no exception clause** and would, read
  literally, import analytics SDKs, `Double` money, and offline-first write-queue
  scaffolding. Also: ktlint and spotless are not alternatives (spotless runs
  ktlint), and the samples' ~40 Gradle modules should not be copied.
- **File organization by feature with layers inside**, with the reasoning specific
  to this situation rather than general taste: the Bolts are already
  feature-shaped, so a feature layout makes a diff localized and "is this Bolt
  complete" answerable from one folder.
- **UI-state mapping had no home**, which under [TC-9] means it lands in
  composables where it is untestable.
- **Two internal contradictions in the draft**, both resolved below.

### By `aidlc-devsecops-agent` (scanning, supply chain, secrets remit)

Inspected the two draft sentences carrying nearly all the security work
("Dependency and secret scanning run in CI on every push. Critical and High
findings block the merge" and "Every new dependency is checked against this
before it is added"). What it found:

- **No scanning tool was named anywhere**, so a rule that scanning happens was
  not yet a practice. Specified free tools for this exact stack: `pip-audit`,
  OSV-Scanner for Gradle (explicitly *not* OWASP Dependency-Check, whose NVD feed
  is slow, rate-limited without an API key, and noisy on Android transitive
  deps), Gitleaks as pre-commit plus CI backstop, Syft for a per-release SBOM,
  Semgrep for project-specific invariants, and Ruff's `S` ruleset as the SAST
  capability already sitting unclaimed in a tool the draft had chosen.
- **Dependency resolution was not locked anywhere**, so the scanners would be
  scanning a version range rather than the build. `uv.lock` for Python, Gradle
  dependency locking plus `dependencyVerification` checksums for Kotlin — the
  checksums being the only control in the project that detects a tampered or
  substituted Gradle artifact.
- **"Critical and High block every merge" would be bypassed once and then be
  decoration**, with a specific predicted scenario: a solo developer hits an
  unfixable transitive Critical mid-Bolt with no triage path and no second
  reviewer. Proposed the two-speed gate the human later adopted.
- **Review cannot enforce the forbidden-identifier set**, because the risk is a
  *transitive* SDK a reviewer reading a Gradle diff cannot see. Specified the
  four-layer control, of which layers 1 and 2 became the human's answer at Q13.2.
- **Rate-limit counters must be datastore-backed.** A per-process dictionary
  passes every test and silently stops working with multiple Uvicorn workers,
  which Phase 1 will have — a correctness bug presenting as "the limit works in
  testing".
- **The global-only cost ceiling is a denial-of-service lever**: one attacker
  burning it locks out every legitimate teacher for the rest of the day,
  converting a financial attack into an availability attack.
- **Four gaps in the seven abuse controls**: no refresh-token reuse response
  despite the architecture claiming theft is detectable (detectable and not
  actable is not a control); the global-only ceiling above; no rate limiting on
  the authenticated API at all, only on `/auth/*`; and no authentication audit
  log.
- **JWT key rotation was unaddressed.** Without `kid` support and two valid
  verification keys from the first commit, rotating the signing key force-logs-out
  every holder of a 30-day refresh token — at exactly the moment rotation is
  needed.
- **SSM `SecureString` over Secrets Manager**, since SSM is free and paying for
  rotation that is not wired up is a control that does not earn its place.
- **Secrets leak through logs, not only repositories** — and specifically through
  the SMS gateway request body, which carries a phone number and often the OTP.
- **Production access is entirely undefined.** With no admin surface, every
  production operation happens via SSH or `psql` against a live database holding
  children's names, attendance and marks, with no audit trail and nothing
  distinguishing legitimate support from a privacy incident.
- **TC-19 absent from both files** — see "Two verified defects" below.
- **No deletion semantics and no retention policy**, with the specific tension
  named: a student's attendance and marks were written by the teacher and are the
  teacher's record, while the same rows are the child's personal data.
- **R-5 must remain recorded as partially unmitigated.** A penetration test is
  correct to want and unaffordable; the honest substitute is the abuse-control and
  authorization probe suites, and a test suite must not be described as having
  closed R-5.
- **What is theatre at this scale**, declined with reasons: continuous ZAP active
  scanning in CI, SonarQube/SonarCloud, commercial SCA tiers, CodeGuru and
  Inspector, and container CVE scanning as a per-push merge gate.

---

## Two verified defects

Both were found by the reviews, verified independently by the lead, and fixed
regardless of any interview answer, because each is a defect rather than a
preference.

### 1. The privacy-boundary test suite would have certified nothing

Row-level security on `profile` is the load-bearing layer of the [D-7, TC-13]
boundary, and the draft's strongest test obligation was to probe it at the
database level. PostgreSQL 16 documents that **superusers and table owners bypass
row-level security entirely**, verified verbatim at [pg-rls]. A test container
connects as `postgres`, which is a superuser. The suite would therefore have
passed identically against a correct policy, a broken policy, or no policy at
all — the one test obligation most relied upon would have been a silent no-op,
and worse than absent, because its passing would have been read as evidence.

Fixed in two parts: integration tests connect as the same restricted,
non-superuser role the application uses; and a **meta-test asserts that
`current_user` is not a superuser and that row-level security is in force**
(`row_security` on, policy present) before the privacy suite runs. The meta-test
is the part that matters, because the restricted-role rule alone silently
regresses the first time someone changes a connection string.

The human affirmed this as permanent rule Q9(a), and its inverse appears under
`## Forbidden` as well, since the failure mode is a thing done rather than a
thing omitted.

### 2. TC-19 account deletion was missing from both artifacts entirely

Grep-verified: zero occurrences of `TC-19`, `account deletion` or `deletion` in
either `team-practices.md` or `discovered-rules.md` as drafted. Meanwhile RC-4
(the Data Safety form) and RC-5 (the privacy policy) were both mandated as
release-blocking V1 deliverables — and all three constraints come from the **same
Play policy page**. The constraint register records TC-19 as "Two
account-deletion paths: in-app, plus an externally accessible route usable
without reinstalling the app", sourced to `[play-deletion] [desc §11]`, touching
Backend, Android and web.

Fixed as a Mandated rule with `[TC-19]` origin covering both paths, plus a test
obligation per path in the Testing Posture section asserting that deletion
removes what the Data Safety form claims and retains only what the privacy policy
discloses.

**Two things about this omission deserve recording rather than quiet repair.**

First, **this is the second time account deletion was dropped in this
workflow.** The product-lead reviewer caught the same omission in the intent
statement at stage 1.1. A requirement that goes missing twice, in two different
artifacts, written by two different participants, is not an accident of attention
— it is a sign that deletion sits outside the shape of how this system is being
thought about. The system is being designed around what teachers *do*: enroll,
attend, mark, charge, collect. Deletion is the only release-blocking requirement
that is about *undoing* all of that, and it has now been forgotten at both the
intent and the practice level. Later stages should treat it as a known blind spot
rather than as a settled line item, and Domain Design in particular should expect
it to be under-specified rather than merely unspecified.

Second, **the external route implies a web surface the approved architecture does
not currently include.** "Usable without reinstalling the app" means it cannot
live behind the Android client. The architecture proposal covers an Android app
and a FastAPI backend; it does not cover a public web page or form, and the
budget [OC-4] has not costed one. Candidates — a static page plus an email
address, a minimal web form on the same host, or a public endpoint — differ
materially in architecture and cost. This is release-blocking and remains
unresolved; it is carried in both `team-practices.md` and `discovered-rules.md`
as an open question so it reaches Domain Design rather than being discovered at
Play submission.

---

## What was inferred

Everything in this section is reasoning, not observation. Each entry names what
it was reasoned from and how confident it is. Where the interview later decided
the question, that is noted — a decided item is no longer an inference, and the
record should not read as though it still is.

**Way of Working — mostly adopted from `org.md`, with two reinterpretations.**
Trunk-based with squash-merge is taken straight from the default and corroborated
weakly by `main` being the only branch. The first reinterpretation is the review
model: `org.md` writes in a plural team voice, but OC-1 and OC-3 establish a solo
build where the agent writes and one person reviews, so practices assuming
multiple developers — approval quorum, code-owner routing, pairing — have no
referent and were dropped rather than carried as dead text. The second is the
"where a rule is important, it is mechanical" principle, which is not in `org.md`
at all: it emerged from all three reviews converging independently on the same
criticism of review-enforced structure, and it is the organising idea behind the
money type, the lens dependency, the manifest allowlist and the restricted
database role. **Confidence: high on the branching mechanics, high on the
mechanical-enforcement principle** (three independent reviewers reached it from
three different remits), **and the Construction autonomy stance is now decided
rather than inferred** — gated through PU-6, autonomous thereafter [interview Q8].

**Walking Skeleton — reasoned from the dependency graph, then materially enlarged
by the human.** `org.md` describes the ceremony but cannot say what the skeleton
*is*; the backlog can. PU-1 is slice 1, everything depends on it, and the
critical path runs PU-1 → PU-2 → PU-5 → PU-6 → PU-7 [backlog], so no cheaper
candidate exists. **Confidence: high that PU-1 is the right skeleton.** The
specific inclusions were the lead's judgment about which decisions are most
expensive to discover wrong late, and the human then added substantially to them:
all seven OTP abuse controls now carry tests inside the skeleton Bolt [interview
Q5], and JWT `kid` support plus two verification keys were added from the security
review. The skeleton is consequently larger than a minimal connectivity proof,
and `team-practices.md` says so plainly rather than describing it as thin. The
honest trade: PU-1 ships to closed testing with its financial exposure tested,
at the cost of a first Bolt that is a real slice rather than a smoke test.

**Testing Posture — the methodology split survived review; its formulation did
not.** `org.md` defaults to `test-after`. The lead proposed `custom` from three
asymmetries: TC-20 and D-23 make money-path tests mandatory by stated requirement
while no other surface carries that obligation; the money logic is arithmetic
over a ledger with values knowable before implementation, which is the
precondition test-first needs; and OC-3's absence of declared Kotlin experience
means a Compose test written first may encode a framework misunderstanding while
looking rigorous. D-18's revision of the fee model strengthens it further. The
quality reviewer agreed with the split, for the right reason, and then objected
that the `Ordering` sentence — seven cases plus "everything else" — fails open.
**The human adopted the predicate formulation** [interview Q1], and the lead
narrowed the Android exemption while integrating: the draft exempted "the Android
surface", which over-claims; the exemption is properly the **Compose UI layer**,
not all Kotlin, and the predicate explicitly does not escape by being implemented
in Kotlin. **No longer an inference: decided at Q1.**

**Testing Posture — the supporting bullets.** The 80% line floor and
CI-before-merge come from `org.md` via the `classic` scope and are **not**
inferred. Inferred and retained: that the floor is the wrong instrument for the
money module (branch, not line); that the authorization layer should likewise be
branch-measured, because lens resolution is pure branching; that integration
tests need real PostgreSQL, because RLS, `NUMERIC(12,2)`,
`ON CONFLICT DO NOTHING` and partial indexes are the behaviours under test and
SQLite emulates none faithfully; that the JSON-string money transport needs its
own contract assertion on both sides; and that idempotency needs a concurrent
test. **Decided rather than inferred after the interview**: Android carries named
obligations and no percentage floor [Q2 as revised at Q13.1], and three of these
became permanent rules while three did not [Q9]. **Confidence: high on each
individually**, since they follow closely from stated decisions.

**Deployment — the budget did most of the inferring, and the staging question is
now settled.** Deploy-on-merge comes from `org.md`. The production gate was
reinterpreted, since `org.md`'s tech-lead-plus-product-owner sign-off is
meaningless when one person holds both roles [OC-1]. The environment table
follows D-29's phased hosting; the three-environment ceiling and the shared
instance class follow from OC-4. Recreate-style deployment with SHA-tagged image
rollback follows from D-29's rejection of an ALB on cost grounds — blue-green
needs a load balancer the budget excludes. Scheduling production deploys outside
classroom hours is inferred from TC-8 and D-9. The forward-only reviewed-migration
rule and the verified-backup-before-migration rule follow from Alembic plus
Single-AZ plus D-18's known-changing fee model: there is no failover, so the
backup is the recovery path. **The staging assumption the draft flagged as
carrying real cost is now confirmed** — a Lightsail staging instance exists in
Phase 1 at roughly USD 25/month total [Q4] — and **the CI platform is decided**:
GitHub Actions, with the Android job moving to CodeBuild only if minutes bite
[Q3]. **Confidence: high on the cost-driven conclusions, moderate on the
deploy-window and staging-faithfulness judgments.**

**Code Style — the draft named candidates; the reviews named mechanisms.**
`org.md`'s "defer to project configuration" is unactionable when no configuration
exists, so the lead named tools. Three substantial changes came from the
developer review and are now settled by the human: money is a **type** on both
surfaces rather than a single-module convention with lint rules [Q11]; the line
length is **88 characters** as a deliberate project-level departure from the
user's stated global 79 [Q10]; and the rounding mode is **`ROUND_HALF_UP`**
rather than Python's `ROUND_HALF_EVEN` default [Q10]. The 88-character choice is
recorded explicitly as a departure in `team-practices.md` so it is not later
mistaken for an oversight. Still inferred, and carried on the reviewers'
reasoning rather than a human statement: the Ruff rule set, the global
`disallow_untyped_defs` baseline with three strict islands, the docstring scoping,
ktlint-via-spotless, one Gradle module, the feature-first file layout, the
five-class error taxonomy, and the "API returns decisions" formulation.
**Confidence: moderate on the specific tools, high on the structural rules**,
which are either restatements of approved decisions or mechanisms three
independent reviewers argued for.

---

## Interview decisions

The human's answers, as recorded in [interview] and confirmed at the Consolidated
Summary Confirmation. These are authoritative and override both the lead draft
and any reviewer position.

| Ref | Decision |
|---|---|
| Q1 | Methodology `custom` with the quality reviewer's **predicate** ordering; the seven named cases become examples, and no escape by being written in Kotlin. |
| Q2 → Q13.1 | Android carries **named obligations and no percentage floor**: a state-machine test per ViewModel (loading, success, error, retry), a serialization test per money-carrying model, and a no-decrease ratchet on reported Kotlin coverage after three Android Bolts. Supersedes the initially-answered 80% Kotlin line floor. |
| Q3 | CI on **GitHub Actions**, Android job to CodeBuild only if minutes bite. |
| Q4 | **A staging Lightsail instance exists in Phase 1** (~USD 25/month total). The draft's assumption is confirmed. |
| Q5 | **All seven OTP abuse controls get tests inside the walking skeleton Bolt**, before anything else. |
| Q6 → Q13.1 | **Two-speed scanning**: secrets and lockfile/checksum integrity block every push; dependency CVEs annotate on push and block at the release gate. Supersedes the initially-answered per-push Critical/High block. |
| Q7 → Q13.2 | **Both Families gates** as failing builds: the merged-manifest permission allowlist asserting absence of `com.google.android.gms.permission.AD_ID`, and the minified-release-DEX scan for framework references. Supersedes the initially-answered allowlist-only. |
| Q8 | Construction is **gated through the payment slice (PU-6), autonomous thereafter**. |
| Q9 | **Exactly three** proposals become permanent rules: restricted-role database tests with an RLS meta-test; concurrent fee-cycle idempotency testing; money arithmetic in one module with an import-boundary check from the first commit. Real-Postgres-over-SQLite, the JSON-string both-sides assertion, and 100% money branch coverage were **not** affirmed and stay in `team-practices.md` as practices. |
| Q10 | **`ROUND_HALF_UP`** and **88-character** lines, the latter recorded explicitly as a deliberate project-level departure from the stated global 79-character Python standard. |
| Q11 | **Money as a type on both surfaces**: a `Money` value object in Python owning its Pydantic serializer and SQLAlchemy `TypeDecorator`, and a `Money` value class in Kotlin with a string-only serializer. Supersedes the draft's detekt-rule mechanism. |
| Q12 | Nothing else in the five practice areas changes. |

Three of these reversed an earlier answer at the Q13 follow-up, and the reversals
are worth noting as a set rather than individually: Q2 and Q6 as first answered
would have placed three hard merge gates on the least-familiar surface with no
triage path and no second reviewer, which is the configuration both reviewers
predicted would be bypassed once and then be decoration — while Q7 as first
answered left enforcement hardest where risk is visible and fixable (published
CVEs) and absent where it is invisible and release-blocking (a transitive SDK
reading a prohibited identifier). The revised set softens the two gates that
would not have held and hardens the one that had to.

---

## Reviewer conflicts resolved

The three reviews were mutually blind, so they disagreed in places. Where a
reviewer conflicted with the human's answer, the human won without exception.
Where reviewers conflicted with each other or contained an internal
contradiction, the lead resolved it and the resolution is recorded here.

### The two internal contradictions the developer review identified

**(i) Localization versus a server-sent error `message`.** The draft mandated
full Bangla and English localization with no hardcoded user-facing strings [TC-15,
D-43], and separately mandated error handling at every integration boundary —
without noticing that a server-sent English `message` field cannot be localized
by the client. Implemented as drafted, the result is untranslated English error
text in a Bangla-first UI: a user-visible defect that neither rule, read alone,
would have caught.

**Resolution: the error envelope carries `message_key`, not `message`.** The
client owns the string, from `strings.xml`; the server names which string. The
envelope also carries `code` as a stable machine value so the client switches on
it rather than on message text, and a server-provided `retryable` boolean. That
last part matters for a second reason: [TC-9] forbids the client holding business
logic, and inferring retryability from an HTTP status is exactly the client
deciding something. Taking the developer reviewer's position here is
straightforward — it is the only resolution that satisfies both original rules
rather than trading one off against the other.

**(ii) "Silent failures are not acceptable" at the FCM boundary.** The draft
stated this absolutely, in a construction-phase guardrail that also says errors
must be surfaced to the caller or logged. At the FCM boundary the absolute
reading is wrong: a push notification is best-effort, and failing the attendance
write that triggered it because a push could not be delivered would be a serious
defect.

**Resolution: the rule keeps its force and gains one stated exception.** Push
dispatch happens after commit, outside the request transaction, and its failure
is **logged and not surfaced**. An `UNREGISTERED` response is not an error at all
but a signal to delete the stored token [D-42]. The phase guardrail's own wording
— "surfaced to the caller **or logged**" — already permits this, so the exception
is a clarification of the guardrail rather than a departure from it; what was
wrong was the draft's absolute restatement. It is now written as an explicit
exception, because the alternative is that someone implements it wrongly in
either direction: failing the operation, or swallowing the failure unlogged.

### Reviewer-versus-reviewer and reviewer-versus-lead

- **Which proposals belong in permanent memory.** The quality reviewer argued for
  only two rules (restricted-role tests, concurrent idempotency), explicitly
  arguing the 100% branch target and the JSON-string assertion belong in
  `team-practices.md` because "a target in `## Mandated` cannot be renegotiated".
  The developer and security reviews both pushed for the money import-boundary
  check to be mandatory from the first commit. **Resolved by the human at Q9**:
  three rules, which is the quality reviewer's two plus the import-boundary check
  the other two argued for. The quality reviewer's reasoning about targets was
  sound and is preserved in the exclusion section of `discovered-rules.md`.
- **Semgrep versus Ruff/import-linter for the money boundary.** The security
  review wanted a Semgrep rule written now; the developer review wanted Ruff
  `flake8-tidy-imports` banned-api plus an import-linter test. **Took the
  developer reviewer's mechanism as primary** and kept Semgrep as a complement.
  Reason: banning raw `decimal` imports outside the module is a stronger control
  than pattern-matching arithmetic, because it blocks the *precondition* rather
  than enumerating the *expressions* — any money arithmetic outside the module
  needs `Decimal` or a float, and both are then unavailable. The import-linter
  test additionally catches the plausible violation neither pattern-matcher would
  (`app.money` accepting a `Session`). Semgrep remains for the invariants no
  import rule expresses: no un-lensed route handler, no `TelephonyManager`
  reference in Kotlin.
- **Docstring scope: the user's global standard versus the developer review.**
  The user's stated global Python standard mandates Sphinx docstrings on every
  function, class and module. The developer review objected that "every public
  function" on an agent-written codebase produces signature restatements that
  drift and then actively mislead a stretched reviewer. **Took the reviewer's
  narrowing**: module docstrings everywhere, function docstrings mandatory in the
  money and authorization modules and wherever correctness depends on something
  absent from the signature, enforced by path-scoped Ruff `D` rules.

  **RESOLVED at the affirmation gate: the narrowing was rejected and the global
  standard applies strictly.** The lead correctly flagged that this departure had
  weaker affirmation than the line length — it appeared only inside the developer
  contribution, and Q12's "nothing else changes" was the closest thing to
  approval it had. Raised as an explicit question rather than allowed to ride in
  on that, and the user chose the global standard: Sphinx docstrings on every
  module, class and function, with `:param`, `:return` and `:raises`, enforced by
  unscoped Ruff `D` rules across the backend. The reviewer's drift argument was
  considered and rejected on the grounds that a drifting docstring is a reason to
  update it in the same change rather than to omit it.

  Consequence: the 88-character line length [Q10] is now the **only** deliberate
  project-level departure from the stated global Python standard.
- **OWASP Dependency-Check versus OSV-Scanner for Gradle.** The security review
  named Dependency-Check as "the better-known answer and the wrong one here", for
  three specific reasons (slow NVD feed, rate-limited without an API key, noisy
  on Android transitive deps) and recommended OSV-Scanner for a single findings
  format across both surfaces. **Took OSV-Scanner.** No other reviewer had a
  position; the reasoning is concrete and the one-format argument is worth real
  money in reviewer attention on a solo build.
- **Secrets Manager versus SSM Parameter Store.** The lead draft said "Secrets
  Manager or SSM Parameter Store" without choosing. **Took the security review's
  SSM `SecureString`**, on its argument that paying for rotation that is not
  wired up is a control that does not earn its place. Nothing conflicts.
- **Coverage instrument on the authorization layer.** Only the quality review
  raised it: 80% *line* coverage on lens resolution is near-meaningless because
  the code is pure branching. **Adopted as branch coverage.** It tightens rather
  than weakens the scope-derived floor, so it does not run into the
  never-weaken-a-floor rule.

### Reviewer material declined

- **The quality review's expiry on the Android test-first exemption** — moving
  ViewModel-level tests to test-first after two Android Bolts. Declined as a
  separate mechanism, because the human's adopted predicate already covers it:
  a ViewModel change that meets the predicate is test-first from the first Bolt,
  and one that does not meet it is test-after permanently, with no expiry needed.
  Adding a date-based ratchet on top would reintroduce exactly the enumeration
  logic the predicate replaced. The substance survives in the narrowing of the
  exemption from "Android" to "the Compose UI layer".
- **Property-based testing as a requirement.** The quality review proposed a
  Hypothesis test on the ledger invariant. Kept, but as one named test rather
  than a general property-based-testing practice, since the invariant is specific
  and a broad Hypothesis mandate would be a tooling commitment nobody asked for.
- **A per-token request ceiling on the authenticated API.** The security review
  ranked this third of four gaps and noted the blast radius is one account's data
  given RLS and lens resolution. Recorded as a practice-level concern in the
  Deployment section's audit-log and access discussion, but **not** added to the
  skeleton scope, which the human already enlarged considerably at Q5. It belongs
  to Domain Design.
- **A full data-retention schedule.** The security review wanted a stated period
  per data class. Adopted for the auth records, where the answer is
  uncontroversial; left open for the child academic records, which need the
  teacher's-record-versus-child's-data view the human has not given. Recorded as
  an open question rather than invented.
- **The theatre list** — continuous ZAP active scanning, SonarQube/SonarCloud,
  commercial SCA tiers, CodeGuru, Inspector, container CVE scanning as a per-push
  gate. All declined, on the security review's own reasoning, and recorded here
  so the decision is traceable rather than appearing as an omission.

---

## Unresolved uncertainty

Ordered by how much the answer changes what happens next. The interview closed
nine of the lead draft's ten items; what follows is what remains, including items
the reviews opened.

1. **What the external account-deletion route actually is** [TC-19]. A static
   page plus an email address, a minimal web form on the same host, or a public
   endpoint. It is release-blocking, it implies a web surface the approved
   architecture does not include, and the budget [OC-4] has not costed it. This
   is the highest-consequence open item in the stage and it is the second
   occurrence of the same requirement going missing.
2. **Deletion dispositions per table**, and therefore what the privacy policy can
   say. The teacher's-record-versus-child's-data tension is real and unresolved:
   attendance and marks were written by the teacher and are also the child's
   personal data. [RC-5] requires the policy to state what is retained and why,
   so this blocks a release deliverable. Belongs to Domain Design.
3. **Retention periods for the child academic records.** The auth records are
   settled in principle (days, not months) but not numerically; the academic
   records wait on item 2.
4. **The Construction Verification Command.** Must be human-authorized and is not
   yet recorded. `team-practices.md` says what it must demonstrate but cannot name
   it.
5. **Whether the SMS gateway has a sandbox, and whether its API exposes the OTP
   in a loggable request body.** No vendor is chosen [arch §10]. The first changes
   the deployment posture; the second is a security requirement to check during
   vendor evaluation. Both should be asked in the same breath.
6. **PU-3.6's verification instrument**: a Macrobenchmark on a low-end device
   profile, or an explicit manual pilot check. What is settled is that a Compose
   UI test does not discharge it; which of the two acceptable answers applies is
   for Delivery Planning.
7. **The per-number and per-IP sub-ceiling thresholds** beneath the global SMS
   ceiling, and what a legitimate user sees when the breaker trips. The *need*
   for a tier beneath the global ceiling is settled; the numbers are not.
8. **Whether CI minutes count against the USD 50 ceiling** [OC-4] or sit outside
   it. It decides whether the Android job can run on every push, which is why the
   job is split from the backend job regardless.
9. **The AWS region**, `ap-southeast-1` versus `ap-south-1` [D-30], pending a
   Dhaka latency measurement. It changes no practice but blocks provisioning the
   staging environment [Q4] now commits to.
10. **Production support access beyond the developer's own.** If a pilot teacher
    ever needs support requiring someone to look at their data, the named-role and
    session-logging controls need to exist before the pilot rather than after.

**R-5 remains partially unmitigated and must stay recorded that way.** A
penetration test is correct to want and unaffordable at this budget. The
abuse-control test suite and the authorization probe suite are the honest
substitute and neither closes R-5. This is not an open question so much as a
standing correction to any later artifact that might describe the test suites as
having closed it.

Two meta-observations worth naming:

- **A greenfield practices "discovery" is a proposal dressed as a finding, and
  this stage worked because three reviewers treated it that way.** All three
  reviews converged independently on the same structural criticism from three
  different remits — that the draft's most important rules were enforced by
  review, which on a solo build with one stretched reviewer is the weakest
  available mechanism. That convergence, not any individual finding, is the
  strongest evidence the stage produced, and it is why "where a rule is
  important, it is mechanical" ended up in the Way of Working section.
- **The reviews contained substantially more good material than the twelve
  interview answers resolve**, and the integration absorbed it on the lead's
  judgment rather than leaving it in the contribution files. The error taxonomy,
  the five erosion paths, the Ruff rule set, the lens-returns-the-scoping-value
  mechanism, the file layout, the audit log, the production-access controls, and
  the locked dependency resolution all entered `team-practices.md` without a
  specific human answer behind them. They are therefore *practices* and not
  *rules*, which is the correct status for them — but the affirmation gate is
  where the human sees them for the first time as a set, and that is worth saying
  plainly rather than letting approval of a five-section document stand in for
  review of each.

---

## Assumptions & Open Questions

- ~~The docstring narrowing is a partial departure from the user's stated global
  Python standard.~~ **Resolved at the affirmation gate**: raised as an explicit
  question, the narrowing was rejected, and the global standard applies strictly
  — Sphinx docstrings on every module, class and function with `:param`,
  `:return` and `:raises`, enforced by unscoped Ruff `D` rules. The
  88-character line length is now the only deliberate departure from that
  standard.
- **The reviews contributed substantially more than the thirteen interview
  questions resolved**, and the lead absorbed that material on its own judgment:
  the five-class error taxonomy, the five layer-erosion paths, the Ruff rule
  set, the lens mechanism, the Android file layout, the auth audit log,
  production-access controls and locked dependency resolution. These are
  recorded as practices rather than permanent rules, which is the correct
  status, but approving a five-section document is not the same as having
  reviewed each one. Named here so that is visible rather than assumed.
  [assumption]
- **Confidence labels in this file are the lead's judgment, not a calibrated
  measure.** [assumption]
- **The absence of a file was treated as evidence that no practice exists**,
  rather than as evidence that a practice exists but is uncommitted. On a
  two-commit scaffold repository this is safe. [assumption]
- **The three reviews were blind to each other but not to the lead draft**, so
  their convergence is evidence about the draft rather than independent
  corroboration of each other's positive proposals. Where two reviewers proposed
  the same mechanism, that is genuine convergence; where one proposed something
  no other mentioned, it is one expert's view and is marked as such above.
  [assumption]
- **`git rev-parse HEAD` was run from the project directory** and returned
  `4ee9225958c9faf3ea329de896a04394e029b252`, although the agent environment
  reports the working directory as not a git repository. The commit recorded in
  `practices-discovery-timestamp.md` is the real one. [assumption]
