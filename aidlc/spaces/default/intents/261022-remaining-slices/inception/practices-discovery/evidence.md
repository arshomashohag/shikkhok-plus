# Practices Discovery — Evidence

Re-run of stage 2.2 for the `261022-remaining-slices` record. Lead-only:
`Collaborators` is `off` for the `classic` scope, `support_agents` was empty,
so Step 3 was skipped and no contribution files exist. Lead:
`aidlc-pipeline-deploy-agent`.

**Run date**: 2026-10-22. **Repository state inspected**: commit `4e4b4d4`
(`docs(codekb): scan the codebase for the remaining-slices record`), on branch
`planning/shikhokplus-ideation-inception`. The code knowledge base this run
consumes was written against commit `b14b1fa`; no application code changed
between the two, only workflow records.

---

## What this run was scoped to

The user was offered three options — re-derive the practices from scratch, run
it focused on the gaps, or skip the stage — and chose **run it focused on the
gaps**. The practices affirmed on 2026-10-16 through this stage's gate are
therefore the **current affirmed baseline**, not a blank slate, and were not
re-litigated. The testing posture (`Methodology: custom` with its predicate
ordering), money-as-a-type, the lens-as-data-dependency design, the error
taxonomy, the deployment stance and the code style are carried forward intact.

The work of this run is **reconciliation**: three affirmed practices are
demonstrably not implemented in the code, and this is the stage where that
mismatch gets resolved. For each, the question posed was the same — does the
practice become work, get amended, or get accepted as-is with the reason
recorded?

---

## What the lead inspected

### Reverse-engineering artifacts (the scan this stage consumes)

Read in full:

- `aidlc/spaces/default/codekb/shikkhok-plus/code-quality-assessment.md` — test
  coverage figures, lint/type/static-analysis results, the Android toolchain
  section, the six specific findings, and the nineteen-row technical debt
  register.
- `aidlc/spaces/default/codekb/shikkhok-plus/dependencies.md` — how dependencies
  are declared and resolved on each surface, the supply-chain control table
  (practice versus built state, row by row), the internal package graphs, and
  the dependency risk summary.

Consulted for context: `technology-stack.md` (referenced for versions),
`architecture.md`, `code-structure.md`, `component-inventory.md` (listed, not
read in full — the three gaps are tooling gaps and these describe structure,
which is not in dispute).

### Planning artifacts

- `aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/inception/delivery-planning/bolt-plan.md`
  — sections A (what is already built), B (the six remaining units and the
  grouping rationale), the D5 and D6 detail, section D (gating), and the open
  questions. This is where the D1–D6 assignment targets come from, and where
  the autonomy amendment under Way of Working is sourced.
- `aidlc/spaces/default/intents/261022-remaining-slices/aidlc-state.md` — project
  type (Brownfield), scope (`classic`), collaborators off, construction
  checkpoints enabled, and the stage list.

### Affirmed baseline

- `aidlc/spaces/default/memory/team.md` — all five sections, read as the current
  affirmed baseline per Step 2's re-run clause.
- `aidlc/spaces/default/memory/project.md` — the twelve `NEVER` and nineteen
  `ALWAYS` rules, read to avoid duplicating them in `discovered-rules.md`.
- `aidlc/spaces/default/memory/org.md` and `phases/inception.md` — read as the
  broader layers the team layer must not contradict.

### Agent knowledge (delegated knowledge preflight)

`.claude/knowledge/aidlc-shared/` (`rules-reading.md`, `brownfield.md`,
`verification.md`, `ai-dlc-principles.md`, and the remaining files listed) and
`.claude/knowledge/aidlc-pipeline-deploy-agent/` (`cicd-patterns.md`,
`deployment-strategies.md`, `branching-strategies.md`).
`aidlc/spaces/default/knowledge/` exists and is empty, so no space-level team
knowledge applied.

---

## What the lead verified independently

The scan is recent and its method is sound, but a practices reconciliation that
takes a scan's word for an absence would be asserting from reasoning rather than
checking — the exact failure this project's own Corrections warn against. Every
load-bearing absence below was re-checked directly at commit `4e4b4d4`.

| Claim | How it was checked | Result |
|---|---|---|
| No Python lockfile | `ls uv.lock requirements*.txt` | Both absent. No match for either name |
| No Gradle locking or checksum verification | `ls gradle.lockfile android/gradle.lockfile gradle/verification-metadata.xml`; `grep` for `dependencyLocking` and `dependencyVerification` across build scripts | All absent |
| CI step mislabelled | `sed -n '80,95p' .github/workflows/check.yml` | Confirmed verbatim: comment `# Step 2. Lockfile verification, Python side.` immediately above `run: python -m pip install -e ".[dev,api]"` |
| No CVE scanning | `ls .github/dependabot.yml .security-exceptions.md`; `grep -rniE 'dependabot|pip-audit|trivy|osv-scanner|safety|snyk|grype' .github/ Makefile` | Both files absent. The only grep hit anywhere was an unrelated prose line in `release-android.yml:284` about the Data Safety form |
| No Android quality toolchain | `grep -rnE 'ktlint|spotless|detekt|jacoco|kover|paparazzi|roborazzi|screenshot'` across `android/`, `gradle/`, root Gradle files | No hit in any build script. The only source hits were the word "screenshot" in icon XML comments and one reference to detekt **inside a test docstring** (see below) |
| No `lint.xml` | `find . -name 'lint.xml'` | No result anywhere in the repository |
| Android plugin set | `grep -n 'plugins\|alias(' android/build.gradle.kts` | Exactly four: Android application, Kotlin Android, Kotlin serialization, Compose compiler. No quality plugin |
| Android surface size | `find android/src/main -name '*.kt' \| wc -l`; same for test trees | **32** main source files, **15** test files, three feature packages (`auth`, `batches`, `roster`), five `core` packages |
| Both string bundles complete | `grep -c '<string'` on both `strings.xml` files | **53 and 53.** The hard half of the Bangla obligation is genuinely done |

One verification produced a finding the scan reported but did not quote, and it
is the most telling single piece of evidence in this run.
`android/src/test/kotlin/com/shikkhokplus/app/core/model/NoFloatingPointTest.kt`
carries this in its class docstring:

> Detekt will carry the same rule once it arrives with the packaging Bolt. This
> test exists now because the rule is needed from the first commit that ships a
> model class, not from the Bolt that happens to install detekt.

The instinct is right and the sentence is also the gap stated precisely: the
rule was needed from the first commit, the mechanism was assigned to a Bolt by
name, and that Bolt did not arrive. The hand-written backstop is doing detekt's
job for one rule in one package, which is why the money ban is in fact still
enforced — and nothing is doing it for anything else.

**Corrections to the scan: none.** Every absence the brief named was reproduced.
The scan's figures for coverage (91% backend, 100% money branch, 615 tests) and
its lint/type results were not independently re-run — they require executing the
suite and the scan recorded the commands that produced them — so they are
carried as reported, attributed, and marked as measured on 2026-10-22 rather
than as verified by this stage.

---

## The three gaps, and the recommendation on each

Each follows the same frame: what it costs to close now, what it costs to leave,
and where in D1–D6 the work lands.

### Gap 1 — No lockfile on either application surface

**Recommendation: this becomes work, before D1, and before the CVE work.**

The practice is not wrong. It names the right two mechanisms for the right two
reasons, and its sentence about Gradle checksum verification being "the only
control we have that detects a tampered or substituted artifact" is accurate and
still unanswered. Nothing about the built state argues the practice should be
amended.

What makes this the first item rather than one of three is that it is the
**precondition for gap 2**. A CVE scanner pointed at `mypy>=1.11` reports on a
version range; pointed at a lockfile it reports on the build. Closing the CVE
gap while leaving this one produces findings nobody can act on and a release
gate that blocks on fiction — a worse state than the honest nothing we have now.

The drift is already measurable: `mypy>=1.11` resolved to **2.4.0**, a major
version nobody chose; `fastapi>=0.115` to 0.143.5; `sqlalchemy>=2.0` to 2.1.5.
`pytest-mock` is installed and undeclared, and on an unlocked project the
repository cannot tell you whether that is ambient or real.

The mislabelled CI step is a distinct, smaller item with the same fix. It is
worth calling out separately because of who the next reader is: on a solo build,
the person who reads `# Step 2. Lockfile verification` in six months is the same
person who wrote it, with nobody to contradict their recollection that the
control exists.

*Cost to close*: hours, mostly generated rather than authored. *Cost to leave*:
compounds with every dependency added across six units, and silently nullifies
the next gap's fix.

### Gap 2 — No CVE scanning anywhere

**Recommendation: this becomes work. Per-push half before D1 (after the
lockfiles), release-gate half in D6.**

The two-speed model should be preserved exactly as affirmed, and the reason
given for it in 2026-10-16 has not weakened: a solo developer who hits an
unfixable transitive Critical mid-Bolt, with no triage path and no second
reviewer, bypasses the gate once — and after one bypass it is decoration. A
simpler single hard gate would be easier to build and would not survive first
contact.

The split across units is natural rather than invented. The per-push half is
`pip-audit`, `osv-scanner` and a Dependabot config: three small files, no new
concepts, and it starts producing information immediately. The release-gate half
needs the `.security-exceptions.md` format, its expiry check and Trivy, all of
which are release-gate machinery that D6 is already building.

On what it costs to leave: this is a children's-data application going to a Play
Families track. A known-vulnerable transitive dependency reaching the store is
the worst-consequence failure mode in the product and the only one the project
currently has no instrument of any kind for. Play's pre-launch report is the sole
net, and the affirmed practice already states why that is not a control.

Worth recording as the honest counter-argument: the project's **secrets** half of
the same blocking rule is present and unusually well built, with a precondition
assertion guarding Gitleaks against the shallow-clone false pass. The team's
security instincts are good. This gap is coverage of the dependency surface
specifically, not a general posture problem.

### Gap 3 — The entire Android quality toolchain is absent

**Recommendation: this becomes work, before D1, as one toolchain commit ahead of
the unit rather than inside it.**

This is the one where the sequencing argument is decisive rather than merely
supportive. **All six remaining units ship Android screens** — D1 signup and
acceptance, D2 roster and guardian view, D3 fee and payment, D4 attendance and
marks, D5 insights, D6 deletion flows. The cost curve has one shape: cheapest
before D1, most expensive after D6.

The concrete driver is `spotlessApply`. The first run reformats the whole module
— **32 Kotlin source files today**, a reviewable one-commit diff. After six more
units of screens it is a diff nobody reads, which is exactly the argument the
2026-10-16 practice made when it said the formatter is "decided at project
setup, because the first reformat is a whole-module diff". The practice
anticipated this precise failure and the project then did the thing the practice
warned against.

Beyond style there is one real hole: **the release gates are the only Kotlin
checks and they run on `bundleRelease` only.** Between commit and release,
nothing checks Kotlin except `testDebugUnitTest`. A `TelephonyManager`
reference — forbidden by a `NEVER` in `project.md` and by [TC-4, D-35] — can sit
on `main` through every PR and be found at release time on the build that was
about to ship. The practice named Semgrep for exactly this and Semgrep is also
absent; of the five project-specific rules it was to carry, four turned out
enforced by something stronger, and this is the fifth.

Two consequences stated plainly, as the brief asks:

1. **This lands on the surface the practice itself calls the thinnest-reviewed**
   [OC-3]. The whole rationale for mechanical enforcement is that review on this
   surface is done by a reviewer still learning the platform. The surface with
   the weakest human check has the weakest mechanical check.
2. **The Bangla layout obligation currently has no verifier at all.** Both
   bundles are complete at 53 strings each and no user-facing string is
   hard-coded — the hard half is done. But of the two verifiers the practice
   offered, screenshot tests or an explicit per-screen manual check, **neither
   exists**, across three shipped screens. The practice's own closing sentence
   applies to itself: an unverifiable obligation is a wish.

The Kotlin coverage ratchet is the fourth piece and has a timing property worth
naming: the practice arms the no-decrease rule "once three Android Bolts have
merged", and three have. Starting the report now costs one plugin line and
baselines against three features; starting it after D6 baselines against the
finished app and ratchets nothing.

*Cost to close*: small and falling due now. *Cost to leave*: compounds six
times, and keeps the commit-time `TelephonyManager` hole open across all of it.

### The two smaller items

**`app.authz` is a declared mypy strict island that was never configured.**
`pyproject.toml` has `app.money.*` and `app.schemas.*`; the comment says
`app.authz.*` waits for U3's resolvers, and U3 shipped — `resolve.py`,
`summary.py`, `annotations.py` and `rls.py` all exist. The deferral was correct
reasoning (an override naming a non-existent module is dead configuration) with
no trigger watching for its own condition. Practical exposure is small, since
`disallow_untyped_defs` is global and `mypy app` is clean, but `strict = true`
adds three checks on the module that decides authorization, and D1 extends that
module. **XS effort, before D1.** Recorded because it is the same failure as the
three large gaps in miniature, which is what makes the new "a deferred control
names its unit" rule worth having.

**`PUBLIC_ROUTES` holds six entries under a comment asserting five**, two of them
allowlisting `/account-deletion` paths no handler registers. This is
pre-declared D6 scope rather than a live hole — nothing is reachable, so no
authorization gap exists. Two things still follow: the allowlist is currently
wider than the application, and a comment stating a number that nothing checks
is a false claim sitting in the one file whose job is to be exact. **Fix the
comment before D1; D6 lands handlers against entries that already exist.**

---

## Is anything in the affirmed practices now *wrong* rather than merely unimplemented?

Three items, and only one is a substantive change.

1. **"Construction is gated through the payment slice, then autonomous" is now
   unresolvable as written.** The payment slice was the platform-subscription
   boundary and that boundary no longer exists — the app charges nobody.
   Delivery planning already settled this [Q8] and this stage follows it rather
   than re-deciding it. The practice is amended to state autonomy for the
   remaining units with the standing human stops unchanged. **This is a real
   amendment, and it is adopting a decision already made elsewhere, not a new
   one.**

2. **"Arriving with the Bolt that first needs them" is a defective clause**, not
   a wrong intention. It names no Bolt, and a Kotlin formatter is first *needed*
   by the first Kotlin file — so a reading that defers it indefinitely is
   available and is what happened. Replaced by the rule that a deferred control
   names the deliverable unit that installs it. **Amendment to the mechanism of
   a practice, not to its substance.**

3. **"A green `main`, not just a green PR" has an unverifiable status.** The
   obligation moved to GitHub's "Require branches to be up to date before
   merging" when the on-merge run was removed on 2026-10-19 at the user's
   instruction. That setting is repository configuration and **cannot be read
   from the repository**, so this run cannot say whether the obligation is in
   force. This is not wrong and not drift — it is a genuine blind spot, flagged
   rather than resolved.

Everything else held up. The practices that were implemented were implemented
closely and in several cases better than written: the money boundary's two
opposing import mechanisms with fixtures proving each fires, the privacy
suite's superuser meta-check enforced by two independent mechanisms, and the
DEX scan's whole-identifier matching after a bare `contains` produced a false
positive. The project's defining habit — checking the check — is the practice
file's "where a rule is important, it is mechanical" working as intended.

---

## What the scan missed or under-weighted

Stated narrowly; the scan is good and these are small.

- **The scan treated the Android cluster as four debt rows (3, 4, 5, 12) and
  noted at the end that they are one cluster.** For a practices decision the
  cluster framing is the load-bearing one, because the cost argument
  (`spotlessApply` on 32 files now versus after six units) applies to the group
  and to the timing, not to any individual row. Ordering the register by severity
  obscures that the cheapest moment to act on all four is the same moment.
- **The scan did not connect gap 1 to gap 2 as a precondition.** It lists both at
  High severity in the same register. The dependency between them — locking must
  land first or the scanner reports on ranges — changes the *order* of the work
  and is the reason this artifact sequences them rather than listing them.
- **The `NoFloatingPointTest` docstring is evidence about process, not just about
  the money rule.** The scan cites the test as coverage. Read as process
  evidence it is the clearest statement available of how the toolchain gap
  opened: a correctly-reasoned deferral to a named Bolt, with nothing watching
  for the Bolt. That is what the new "a deferred control names its unit" rule
  exists to prevent, and it came from reading the code rather than the register.
- **Nothing in the scan or this run examined the `android/build/` tree's
  staleness, the Macrobenchmark question's resolution, or the branch-protection
  setting.** The first is irrelevant, the second is explicitly an open question
  owned by delivery planning, and the third is not readable from here.

---

## Uncertainty, stated plainly

- **Branch protection ("Require branches to be up to date before merging") could
  not be checked.** It is repository configuration. If it is off, the "green
  `main`" obligation has no verifier at all. A thirty-second check in the
  repository settings resolves it and is worth doing before D1.
- **The coverage, lint and type figures are carried from the scan, not re-run.**
  91% backend line, 100% money branch, 615 tests, clean Ruff and mypy. The scan
  names the commands that produced each. This stage reproduced the *absences*,
  which is where the decisions turn, and did not re-execute the suite.
- **Whether the Bangla verifier should be screenshot tests or a documented
  per-screen manual check is a human judgement and is left open.** Both are
  acceptable by the affirmed practice and the trade is real: Roborazzi or
  Paparazzi is a plugin plus a baseline-image workflow with ongoing maintenance;
  a manual checklist costs nothing to set up and depends on someone doing it each
  time. The recommendation is only that *one* of them exists before more screens
  land.
- **The Macrobenchmark sequencing is not resolved here.** The harness is assigned
  to D5 while the attendance screen it measures lands in D4. The delivery plan
  records this as an open question and owns it. This stage's only position is the
  affirmed one: a Compose correctness test does not discharge a latency
  obligation.
- **`pytest-mock` 3.14.1 installed and undeclared** could not be resolved to
  either "ambient in the author's environment" or "real undeclared dependency",
  because an unlocked project cannot answer that from the repository. It becomes
  answerable the moment gap 1 closes.
- **No support contributions exist and none were expected.** Collaborators are
  off for this scope, so there was no independent quality, developer or devsecops
  pass over this draft. On a stage whose subject is quality tooling, that is
  worth naming: the draft had one author and the human gate is its only review.

---

## Sources

- [code] `.github/workflows/check.yml`, `deploy.yml`, `release-android.yml`;
  `android/build.gradle.kts`, `android/release-gates.gradle.kts`;
  `pyproject.toml`; `app/contract/routes.py`; `app/main.py`;
  `android/src/test/kotlin/com/shikkhokplus/app/core/model/NoFloatingPointTest.kt`;
  `android/src/main/res/values/strings.xml`, `values-bn/strings.xml` — read or
  checked 2026-10-22 at commit `4e4b4d4`
- [verified] absences reproduced by direct `ls`, `find` and `grep` as tabulated
  above, 2026-10-22
- [artifact] `aidlc/spaces/default/codekb/shikkhok-plus/code-quality-assessment.md`,
  `dependencies.md` — scan of 2026-10-22 at commit `b14b1fa`, fingerprint
  `7599d153`
- [artifact] `aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/inception/delivery-planning/bolt-plan.md`
  — the approved six-unit plan and its gating section
- [memory] `aidlc/spaces/default/memory/team.md`, `project.md`, `org.md`,
  `phases/inception.md` — the affirmed baseline of 2026-10-16
- [human] the scoping choice for this run: re-derive, focus on the gaps, or
  skip — the user chose to run it focused on the gaps
