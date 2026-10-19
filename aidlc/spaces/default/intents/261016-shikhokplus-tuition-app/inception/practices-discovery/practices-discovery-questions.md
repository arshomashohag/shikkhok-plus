# Practices Discovery — Interview

**Stage**: practices-discovery (2.2)
**Phase**: Inception
**Depth**: Comprehensive

## Sources

- [org] `aidlc/spaces/default/memory/org.md` — the five matching sections, read as suggested defaults for a greenfield project.
- [team] `aidlc/spaces/default/memory/team.md` — read and found empty; no affirmed baseline exists.
- [lead] `team-practices.md`, `discovered-rules.md`, `evidence.md` — the lead draft.
- [quality] `contributions/aidlc-quality-agent.md` — blind review, testing and CI remit.
- [developer] `contributions/aidlc-developer-agent.md` — blind review, conventions and boundaries remit.
- [security] `contributions/aidlc-devsecops-agent.md` — blind review, scanning and supply-chain remit.
- [pg-rls] https://www.postgresql.org/docs/16/ddl-rowsecurity.html — retrieved 2026-10-17.

---

## Context before you answer

This project is greenfield: there is no code, no CI, and no history to observe,
so nothing here was *discovered*. The lead proposed, three specialists reviewed
the proposal independently without seeing each other's comments, and these
questions are what remains genuinely yours to decide.

Your answers get written into `aidlc/spaces/default/memory/team.md` and
`project.md` as standing rules, so later stages stop asking and future work in
this workspace inherits them.

**Two things the reviews found that are already fixed regardless of your
answers**, because they are defects rather than preferences:

- **The privacy-boundary tests would have certified nothing.** Row-level
  security is the load-bearing layer of your §4 boundary, and PostgreSQL
  documents that superusers and table owners bypass RLS entirely [pg-rls]. A
  test container connects as `postgres`, a superuser — so that suite would pass
  identically whether the policy was correct, broken, or absent. Tests will
  connect as a restricted role with a meta-test asserting RLS is in force.
- **Account deletion was missing from the practices entirely**, while the Data
  Safety form and privacy policy — from the same Play policy page — were both
  mandated. This is the second time it has been dropped in this workflow; the
  reviewer caught the same omission at intent capture. It is being added as a
  Mandated rule with a test obligation.

---

## Q1. Testing methodology: the split, or a uniform rule?

The lead proposes `custom`: write the failing test first for money paths and
authorization rules, implement-then-test everywhere else. The reasoning is that
fee arithmetic has expected values knowable before any code exists — the exact
precondition where test-first pays — and the fee model is already known to be in
revision, so a suite pinning the arithmetic is what makes the next revision safe.
Against that, a Compose test written before the implementation, by someone not
yet fluent in Compose, is as likely to encode a framework misunderstanding as
catch a defect, and would do so with the appearance of rigour.

The quality reviewer agrees with the split but objects that the `Ordering`
sentence **fails open**: it lists seven test-first cases plus "everything else",
so any case nobody anticipated defaults to test-after. It proposes a predicate
instead — test-first whenever the correct output is knowable from the
requirement **and** a wrong answer would be a money or authorization error —
with the seven cases demoted to examples, plus an explicit "does not escape by
being implemented in Kotlin".

- A. `custom` with the predicate-based ordering (the lead's split, the reviewer's precision)
- B. `custom` with the lead's enumerated ordering as drafted
- C. Uniform `test-after` everywhere, with the money paths simply required to have tests
- D. Uniform `tdd` everywhere, accepting that Android Bolts will strain it
- X. Other (please specify)

[Answer]: A

---

## Q2. Does the Android surface get a coverage obligation?

The lead proposes measuring Kotlin coverage without gating on a percentage,
arguing that gating a surface the reviewer cannot yet evaluate produces tests
written to raise a number.

The quality reviewer agrees about the percentage but objects that this leaves
the **thinnest-reviewed surface in the product with no test obligation at all**,
and that the lead's argument justifies dropping the number, not dropping the
obligation. It proposes named obligations instead: a state-machine test per
ViewModel (loading, success, error, retry), a serialization test per
money-carrying model, and a no-decrease ratchet on reported coverage after three
Android Bolts.

- A. Named obligations, no percentage floor (the reviewer's position)
- B. Measure only, no obligations and no floor (the lead's draft)
- C. Apply the same 80% line floor to Kotlin as to Python
- D. Named obligations now, and revisit a percentage floor after the first three Android Bolts
- X. Other (please specify)

[Answer]: C — REVISED to A at the follow-up (Q13). The 80% line floor on Kotlin
was reconsidered together with Q6's merge gate: three hard gates on the
least-familiar surface with no triage path invites the number-raising tests the
floor is meant to prevent. Kotlin gets the named obligations plus a
no-decrease ratchet instead. See Q13.

---

## Q3. Where does CI run?

Nobody has decided this, and it is assumed throughout the draft rather than
chosen. It is also a security decision, because it determines where deploy
credentials live.

GitHub Actions is the default assumption: zero setup, and the repository is
already on GitHub. The catch is that Android builds are minute-expensive, and a
private repository's free allowance is limited. CodePipeline with CodeBuild
keeps everything inside the AWS account your budget already covers, at the cost
of real setup time against a timeline that is already the binding constraint.

The quality reviewer's suggestion: GitHub Actions for the pull-request gate,
and move only the Android job to CodeBuild if minutes actually bite.

- A. GitHub Actions throughout, move the Android job later if minutes bite
- B. GitHub Actions throughout and accept paying for minutes if needed
- C. CodePipeline and CodeBuild from the start, inside the AWS account
- D. Make the repository public so Actions minutes are unlimited
- X. Other (please specify)

[Answer]: A

---

## Q4. Does a staging environment exist during closed testing?

The draft's deployment section assumes one. A second Lightsail instance takes
Phase 1 from roughly USD 13 to USD 25 per month — within your USD 50 ceiling,
but it is real money for an audience of twelve testers.

The alternative is local Docker Compose as the only pre-production environment,
promoting straight from local to the closed-testing host. That saves the money
and loses the place where a migration gets rehearsed before it touches real
teacher data.

- A. Yes — a staging Lightsail instance in Phase 1 (~USD 25/month total)
- B. No — local Docker Compose only; promote straight to the testing host
- C. No staging instance, but a disposable one stood up on demand before any migration that touches real data
- X. Other (please specify)

[Answer]: A

---

## Q5. Are the OTP abuse-control tests inside the walking skeleton?

Your architecture specifies seven abuse controls: per-number limits (3/hour,
5/day), per-IP (10/hour), 5-minute single-use OTPs, 5 verify attempts, hashed
storage, enumeration-resistant responses, and a global daily SMS ceiling.

The quality reviewer found **none of them has a test obligation** in the draft.
They live in PU-1, which *is* the walking skeleton, so they are the first thing
built, currently the least tested, and carry direct financial exposure — with
per-SMS billing, abuse is a direct attack on your wallet.

Including them makes the skeleton materially larger, which matters because the
skeleton is meant to prove the pieces connect, not to be feature-complete.

- A. Yes — all seven get tests inside the skeleton Bolt before anything else is built
- B. The financially-exposed ones only (rate limits and the cost ceiling) in the skeleton; the rest with the auth slice
- C. Keep the skeleton thin; the full abuse-control suite lands with the auth slice before closed testing
- X. Other (please specify)

[Answer]: A

---

## Q6. How hard should the merge gate be?

The draft says Critical and High findings block the merge. The security reviewer
objects that a solo developer who hits an unfixable transitive CVE mid-slice,
with no triage path and no second reviewer, will bypass it once — and after
that it is decoration rather than a control.

Its proposal is two speeds: secrets and lockfile integrity block **every** push,
because those are always actionable; dependency CVEs annotate on push and block
at the **release** gate, which your deployment checklist already implies.

- A. Two speeds — secrets and lockfile block every push, CVEs block at release (the reviewer's position)
- B. Critical and High block every merge, as drafted
- C. Everything annotates, nothing blocks; the release checklist is the only gate
- X. Other (please specify)

[Answer]: B — REVISED to A at the follow-up (Q13). Two-speed scanning: secrets
and lockfile integrity block every push; dependency CVEs annotate on push and
block at the release gate. See Q13.

---

## Q7. Is a bytecode scan accepted as a build gate?

This is the control for your sharpest constraint. The Families declaration bars
transmitting advertising and device identifiers, and the draft enforces it by
checking each new dependency in review.

The security reviewer's objection is that the real risk is a **transitive** SDK,
which a reviewer reading a Gradle diff cannot see. What would actually work:
a merged-manifest permission allowlist asserting the absence of
`com.google.android.gms.permission.AD_ID` — the declaration Families review
looks for — plus a scan of the minified release DEX for framework calls like
`getImei`, `getSubscriberId`, `AdvertisingIdClient` and `ANDROID_ID`, which
survive obfuscation because they are framework references. Roughly a 30-line
script, and the highest security value per hour available in this project.

If you decline it, the honest consequence is that the constraint stops being
enforced and starts being hoped for — and the practices should say so rather
than claim a control that does not exist.

- A. Yes — manifest allowlist and DEX scan both as failing build gates
- B. Manifest permission allowlist only; skip the bytecode scan
- C. Neither; rely on review and Play's pre-launch report, and record the constraint as unenforced
- X. Other (please specify)

[Answer]: B — REVISED to A at the follow-up (Q13). Both the manifest permission
allowlist and the minified-release-DEX scan are failing build gates. See Q13.

---

## Q8. Construction autonomy: review each checkpoint, or continue automatically?

Not asked by the framework yet — it comes up at the skeleton checkpoint — but
your answer shapes the practices, so it is better settled here.

The lead recommends **reviewing each checkpoint** until the payment slice is
done, then autonomy. The reasoning: the money and privacy surfaces are where an
unreviewed run of plausible-looking commits is most expensive to unwind, and you
are the only reviewer.

- A. Review each checkpoint through the payment slice, then continue automatically
- B. Review each checkpoint throughout, for every slice
- C. Continue automatically from the start; I will review the diffs
- X. Other (please specify)

[Answer]: A

---

## Q9. Which proposals become permanent rules?

Rules in `discovered-rules.md` are promoted into `project.md` and bind every
later stage and every future piece of work in this workspace. The lead kept it
narrow deliberately — only constraints you have actually stated — which left
several good proposals without a human origin. Affirming one here gives it that
origin.

The quality reviewer's view is that only two belong in permanent memory, because
a target written into `## Mandated` cannot be renegotiated later without
amending the project's memory.

(Select all that should become permanent rules.)

- A. Database tests connect as a restricted non-superuser role, with a meta-test asserting RLS is in force
- B. Fee-cycle idempotency is tested with overlapping concurrent generations, never sequential calls
- C. Money arithmetic confined to one module, with an import-boundary check from the first commit rather than after a violation
- D. Integration tests run against real PostgreSQL, never SQLite
- E. Money crosses the API as a JSON string, asserted on both sides
- F. 100% branch coverage on the money module
- X. Other (please specify — or "A and B only", the reviewer's recommendation)

[Answer]: A, B, C

---

## Q10. Two settings that are invisible once chosen and expensive to change later

The developer reviewer flagged these as the highest cost-of-getting-it-wrong
items in the whole draft, because both are silent: nothing fails, the code just
quietly means something different, and reversing either later rewrites every
money call site or reformats every file.

**Rounding mode.** Python's `Decimal` default is `ROUND_HALF_EVEN` (banker's
rounding: 0.5 rounds to the nearest even digit). Most people expect
`ROUND_HALF_UP` (0.5 always rounds up), which is also what a Bangladeshi teacher
doing arithmetic on paper would do. If a partial payment of 1,250.50 is split or
a rate applied, the two modes disagree — and the mode is set once, centrally, so
it is cheap now and expensive after there is data.

**Line length.** Your global Python standard says 79 characters, which is
`pycodestyle`'s limit. Ruff's default is 88 (Black's). The draft is silent on
this, and changing it later reformats every file, making every subsequent diff
unreadable against history.

(Select one option for each, or use X.)

- A. `ROUND_HALF_UP` and 79 characters (your stated global standard)
- B. `ROUND_HALF_UP` and 88 characters (Ruff/Black default line length)
- C. `ROUND_HALF_EVEN` and 79 characters
- D. `ROUND_HALF_EVEN` and 88 characters
- X. Other (please specify)

[Answer]: B

---

## Q11. Money as a number, or money as a type?

The lead mandates money arithmetic confined to one module. The developer
reviewer's structural objection is that this is still a *convention* — the lint
rule has to know which values carry money, which is exactly what an unfamiliar
reviewer cannot see.

Its alternative: make money a **type**. A `Money` value object owning both the
Pydantic serializer and the SQLAlchemy type decorator, so every money value
passes through two chokepoints it already has to pass — the database and the
API. On the Kotlin side, a `Money` value class with a string-only serializer
makes the float prohibition a **compiler** property rather than a lint rule, and
catches a backend regression emitting a JSON number as a bonus.

It also noted a gap no float ban catches: `Decimal(<float>)` produces a
`Decimal`, so the type check passes while the precision is already lost.

- A. Money as a type on both sides — `Money` value object in Python, `Money` value class in Kotlin (the reviewer's position)
- B. Money as a type in Python only; Kotlin keeps `BigDecimal` with a detekt rule
- C. Keep the lead's single-module convention with lint checks, no value type
- X. Other (please specify)

[Answer]: A

---

## Q12. Anything in the five practice areas you want changed?

The lead's draft covers Way of Working, Walking Skeleton, Testing Posture,
Deployment and Code Style. Beyond the questions above, is there anything in
those sections you disagree with?

Worth knowing: the lead reinterpreted two framework defaults rather than copying
them. The default production gate is "tech lead plus product owner sign-off",
meaningless when one person holds both roles, so it became a checklist you
complete. And practices assuming multiple developers — approval quorum,
code-owner routing — were dropped rather than carried as dead text.

- A. Nothing — the five sections are right as drafted, subject to the answers above
- B. Yes, something specific (please say what)
- X. Other (please specify)

[Answer]: A

---

## Q13. Resolving the gate combination (follow-up to Q2, Q6 and Q7)

Three answers pulled against each other. Q2 (80% line floor on Kotlin) and Q6
(Critical and High block every merge) together produced three hard merge gates
on the surface with no declared experience, no triage path and no second
reviewer — the exact configuration both reviewers predicted would be bypassed
once and then be decoration. Meanwhile Q7 declined the DEX scan, leaving
enforcement hardest where risk is visible (published CVEs, fixable) and absent
where it is invisible (a transitive SDK reading a prohibited identifier, which
is the release-blocking constraint and which a Gradle diff cannot show).

**Q13.1 — the two gates**

- A. Soften both to the reviewers' positions
- B. Keep both as originally answered
- C. Keep the Kotlin floor, soften the CVE gate
- D. Keep the CVE gate, soften the Kotlin floor
- X. Other (please specify)

[Answer]: A. Soften both. Kotlin gets named obligations — a state-machine test
per ViewModel (loading, success, error, retry), a serialization test per
money-carrying model — plus a no-decrease ratchet on reported coverage after
three Android Bolts, and no percentage floor. Scanning runs at two speeds:
secrets and lockfile/checksum integrity block every push because they are
always actionable; dependency CVEs annotate on push and block at the release
gate. This supersedes Q2's `C` and Q6's `B`.

**Q13.2 — the Families identifier control**

- A. Add the DEX scan after all
- B. Manifest allowlist only, with the gap recorded as partially enforced
- C. Allowlist now, DEX scan before the first Play submission
- X. Other (please specify)

[Answer]: A. Add the DEX scan. Both controls are failing build gates: a
merged-manifest permission allowlist asserting the absence of
`com.google.android.gms.permission.AD_ID`, and a scan of the minified release
DEX for framework references including `getImei`, `getSubscriberId`,
`getSimSerialNumber`, `Build.getSerial`, `getBSSID`, `AdvertisingIdClient` and
`ANDROID_ID`, which survive obfuscation because they are framework calls. This
supersedes Q7's `B`. Rationale: the allowlist alone catches only an SDK that
declares `AD_ID`; one reading `ANDROID_ID` or calling `getImei` declares no
permission at all, and review has already been established as an insufficient
control for a transitive dependency.

---

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

- Testing methodology is `custom` with the predicate ordering: test-first
  whenever the correct output is knowable from the requirement and a wrong
  answer would be a money or authorization error, with the seven named cases as
  examples rather than the whole list, and no escape by being written in Kotlin.
- Android testing carries named obligations and no percentage floor: a
  state-machine test per ViewModel covering loading, success, error and retry; a
  serialization test per money-carrying model; and a no-decrease ratchet on
  reported coverage after three Android Bolts.
- CI runs on GitHub Actions, with the Android job moving to CodeBuild only if
  minutes become a real constraint.
- A staging Lightsail instance exists in Phase 1, taking Phase 1 hosting to
  roughly USD 25 per month against the USD 50 ceiling.
- All seven OTP abuse controls get tests inside the walking skeleton Bolt,
  before anything else is built: per-number 3/hour and 5/day, per-IP 10/hour,
  5-minute single-use OTP, 5 verify attempts then invalidate, hashed and
  never-logged OTP storage, enumeration-resistant responses, and the global
  daily SMS ceiling.
- Scanning runs at two speeds: secrets and lockfile or checksum integrity block
  every push; dependency CVEs annotate on push and block at the release gate.
- The Families identifier constraint is enforced by two failing build gates: a
  merged-manifest permission allowlist asserting the absence of
  `com.google.android.gms.permission.AD_ID`, and a scan of the minified release
  DEX for framework references including `getImei`, `getSubscriberId`,
  `getSimSerialNumber`, `Build.getSerial`, `getBSSID`, `AdvertisingIdClient` and
  `ANDROID_ID`.
- Construction reviews each checkpoint through the payment slice, then continues
  automatically.
- Three proposals become permanent rules in `project.md`: database tests connect
  as a restricted non-superuser role with a meta-test asserting row-level
  security is in force; fee-cycle idempotency is tested with overlapping
  concurrent generations rather than sequential calls; and money arithmetic is
  confined to one module with an import-boundary check from the first commit.
- Rounding mode is `ROUND_HALF_UP` and the line length is 88 characters. The
  line length is a deliberate project-level departure from the stated global
  79-character Python standard.
- Money is a type on both surfaces: a `Money` value object in Python owning its
  Pydantic serializer and SQLAlchemy type decorator, and a `Money` value class
  in Kotlin with a string-only serializer, making the float prohibition a
  compiler property rather than a lint rule.
- Nothing else in the five practice areas changes.
- Two defects found by the blind reviews are fixed regardless of the answers
  above: database privacy tests will connect as a restricted role, because
  PostgreSQL superusers and table owners bypass row-level security and a
  superuser-run suite would pass against an absent policy; and the two
  account-deletion paths are added as a Mandated rule with a test obligation,
  having been omitted from the practices entirely.

[Answer]: Looks correct

---
