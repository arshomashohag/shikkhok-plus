# Discovered Rules — ShikhokPlus

**Stage**: practices-discovery (2.2)
**Phase**: Inception
**Date**: 2026-10-17

On approval these are appended to `aidlc/spaces/default/memory/project.md` under
`## Mandated` and `## Forbidden`, where they bind every later stage
permanently.

**Admission standard applied.** Every rule below traces to a constraint or
decision the human has stated and confirmed — recorded in
`constraint-register.md`, `decision-log.md`, or affirmed at this stage's
interview. Each rule carries its origin. Four rules are new since the lead
draft: three the human explicitly affirmed at Q9 (origin `[Q9]`), and one
covering the account-deletion paths that both drafts had omitted entirely
(origin `[TC-19]`).

Deliberately **excluded**, because this file becomes permanent memory and the
bar for that is a stated human constraint rather than a good idea:

- **Three Q9 candidates the human did not affirm**: integration tests against
  real PostgreSQL rather than SQLite; the money-as-JSON-string assertion on both
  sides; 100% branch coverage on the money module. All three are offered at Q9,
  all three were left unselected, and all three remain in `team-practices.md` as
  practices rather than rules. The reasoning is sound independent of the vote: a
  coverage target written into `## Mandated` cannot be renegotiated when the money
  module is refactored without amending the project's memory, and the real-Postgres
  and JSON-string rules are implementation choices whose *purpose* is already
  secured by the three rules that were affirmed.
- **The reviewers' own strong proposals**, which strengthen the practices but
  carry no stated-human origin: the `Money` value type's internal design, the
  five-class error taxonomy, the route-enumeration test's mechanics, the Ruff rule
  set, the two-speed scanning thresholds, ktlint-via-spotless, one Gradle module.
  Each is now in `team-practices.md` — several carry a human decision at Q3, Q6,
  Q7, Q10 or Q11 that makes them *settled practice*, but settled practice is not
  the same as a permanent `## Mandated` rule, and promoting the mechanism rather
  than the obligation would freeze a tool choice we may outgrow.
- **Framework defaults that arrived from `org.md` via the active scope** rather
  than from the user: trunk-based development, squash-merge, the 80%
  line-coverage floor, deploy-on-merge-to-staging. They already apply through the
  rule chain and need no restating as project-level rules.
- **Decisions that bind the *design* rather than the *practice***: the `Owner`
  indirection, the token lifetimes, the calendar-month fee period. They are
  binding and recorded in the decision log; they belong to Domain Design, not
  here.

---

## Mandated

> **Formatting note.** Each rule below is a single unwrapped line. The promotion
> tool stamps `(affirmed <date>)` per line, so a wrapped rule would be split into
> an orphan paragraph carrying its own stamp mid-sentence. Keep one rule per
> line when editing this file.

- ALWAYS write tests for the money paths — fee-cycle arithmetic, carry-forward, partial approval and waiver — as a non-negotiable deliverable of the work that implements them, never as a follow-up. [TC-20] [D-23] [PU-5.7]
- ALWAYS represent money as fixed-point decimal in BDT: `NUMERIC(12,2)` server-side, a decimal-backed value type in Kotlin, and serialized across the API as a JSON string. [TC-7] [D-20]
- ALWAYS confine money arithmetic to a single module, with the rounding mode declared once in that module, and enforce the boundary with an import-boundary check present from the first commit rather than added after a violation. [D-20] [PU-5.6] [Q9]
- ALWAYS connect database tests as a restricted non-superuser role, with a meta-test asserting that `current_user` is not a superuser and that row-level security is in force before the privacy suite runs. [Q9] [TC-13] [pg-rls]
- ALWAYS test fee-cycle generation idempotency with overlapping concurrent generations, never with sequential calls. [Q9] [TC-12] [D-21]
- ALWAYS enforce fee-cycle generation idempotency with the database unique constraint on `(enrollment_id, period)` and `ON CONFLICT DO NOTHING`, never with an application-level "has this already run" guard. [TC-12] [D-21]
- ALWAYS provide both account-deletion paths — in-app, and an externally accessible route usable without reinstalling the app — as release-blocking V1 deliverables, with a test per path asserting that deletion removes what the Data Safety form claims it removes and retains only what the privacy policy discloses. [TC-19] [RC-4] [RC-5]
- ALWAYS keep every business rule server-side; the Android app holds no business logic and renders only what the server computes. [TC-9] [D-31]
- ALWAYS compute role as a per-request lens from owned batches and enrollments, with no role field on the account and no cached role, and never trust a client-supplied lens hint for authorization. [TC-11] [D-2]
- ALWAYS enforce the student-and-guardian privacy boundary structurally in all three layers — separate tables by writer, PostgreSQL row-level security on `profile`, and teacher-facing response schemas carrying no profile fields — rather than by filtering in individual queries. [TC-13] [D-5] [D-7]
- ALWAYS check a new dependency against the forbidden-identifier set before adding it, since removing an SDK after the Families-policy declaration is far more costly than not adding it. [TC-3] [TC-6] [D-37] [RC-1]
- ALWAYS externalize user-facing strings with Bangla and English present from the start, and verify that longer Bangla text does not break the layout. [TC-15] [D-43]
- ALWAYS encrypt children's data at rest, which disqualifies any hosting or database tier without storage encryption. [RC-8] [D-29]
- ALWAYS target `compileSdk` and `targetSdk` 36 (Android 16), and recheck the Play requirement at release. [TC-1] [D-39]
- ALWAYS raise structural concerns as they arise, and do not raise naming or convention concerns. [OC-6] [D-45]
- ALWAYS treat the Data Safety form, the privacy policy and the Families target-audience declarations as release-blocking V1 deliverables, not follow-ups. [D-41] [RC-4] [RC-5]
- ALWAYS prefer conventional, well-documented Android choices over clever ones, because review depth on that surface is limited — while letting project constraints outrank the sample wherever they conflict. [OC-3] [D-27]
- ALWAYS keep infrastructure spend under USD 50/month. [OC-4]

## Forbidden

- NEVER use `float` or `double` for a money value anywhere in the stack, in any language, in storage, in transit or in memory. [TC-7] [D-20]
- NEVER transmit a device or advertising identifier anywhere: AAID, SIM serial, build serial, BSSID, MAC, SSID, IMEI or IMSI. [TC-3] [D-37]
- NEVER read the device phone number via `TelephonyManager`; the number is always typed by the user. [TC-4] [D-35]
- NEVER request SMS read permission; OTP autofill uses the SMS Retriever API only. [TC-5]
- NEVER add an ads SDK, or an analytics or crash-reporting SDK that transmits a device or advertising identifier. [TC-6] [D-37]
- NEVER run the privacy-boundary test suite as a database superuser or table owner, because both bypass row-level security and the suite would then pass against a broken or entirely absent policy. [Q9] [pg-rls] [TC-13]
- NEVER expose anything a student or guardian writes to any teacher. [TC-13] [D-5]
- NEVER expose student or guardian data to a platform administrator, whose visibility is limited to subscriber information — teacher name, plan and payment status. [TC-14] [D-6]
- NEVER store or log an OTP in plaintext, and never return a response or timing that reveals whether a phone number exists. [D-33] [architecture §7]
- NEVER hardcode a credential, API key, token or secret in the repository or in a built image. [construction-phase rules] [D-33]
- NEVER accept a write without connectivity in V1; there is no local write queue, and a failed write surfaces an explicit retry prompt rather than queueing silently. [TC-8] [D-9]
- NEVER let the Android client compute a fee balance, an authorization decision or any other business rule. [TC-9] [D-31]
- NEVER weaken a defined coverage floor or an affirmed quality target to make a build step pass. [org: Testing Posture]
- NEVER change the package namespace `com.shikkhokplus.app`; it is permanent once published. [TC-2] [D-38]

---

## Assumptions & Open Questions

- **The three Q9 non-affirmations are a deliberate narrowing, and they are worth
  revisiting once.** Real-Postgres-over-SQLite, the both-sides JSON-string
  assertion, and 100% money branch coverage were all offered and all left
  unselected. They remain binding as practices in `team-practices.md` and are
  enforced in CI; what they lack is permanence. If a later stage proposes
  weakening any of them, that is a `team.md` conversation rather than a blocked
  rule, which is the consequence of the narrowing and is stated here so it is not
  discovered as a surprise. [assumption]
- **The `NEVER hardcode a credential` rule has a mixed origin.** It is stated in
  the construction-phase guardrails rather than by the user directly, and is
  implied by D-33's abuse-control posture. It is retained because the cost of
  omitting it exceeds the cost of a slightly over-broad origin. The interview did
  not contradict it. [assumption]
- **RC-8's encryption-at-rest requirement is itself an inference** recorded as
  such in the constraint register: no Families-policy text names encryption at
  rest explicitly. The rule is retained because a hosting tier was already
  rejected on its basis [D-29], which makes it load-bearing regardless.
  [assumption]
- **The two Families build gates are settled practice but not promoted rules.**
  The human affirmed both the merged-manifest permission allowlist and the
  minified-release-DEX scan as failing build gates at Q13.2, and they are
  recorded in `team-practices.md`. They are not in `## Mandated` because the
  *obligation* they serve is already mandated — the forbidden-identifier check
  and the `NEVER transmit a device or advertising identifier` rule — and
  promoting a specific tooling mechanism would freeze the implementation rather
  than the requirement. If the mechanism proves fragile, the obligation still
  binds. [assumption]
- **TC-19's external deletion route implies a web surface the approved
  architecture does not include.** The rule above mandates both paths because the
  constraint does; *what* the external route is — a static page plus an email
  address, a minimal web form, or a public endpoint — is unresolved and has
  architecture and budget consequences the Ideation artifacts do not settle.
  [assumption]
- Rules binding *design* rather than *practice* are deliberately absent here and
  remain binding through the decision log. If later stages need them in memory,
  that is a separate promotion decision. [assumption]

## Sources

- [TC-*], [OC-*], [RC-*] `ideation/feasibility/constraint-register.md` — 20
  technical, 7 organisational, 8 regulatory constraints. TC-19 is the two
  account-deletion paths, sourced there to `[play-deletion] [desc §11]`.
- [D-*] `ideation/approval-handoff/decision-log.md` — 48 Ideation decisions.
- [Q9], [Q13] `practices-discovery-questions.md` — the human's affirmations at
  this stage's interview.
- [PU-*] `ideation/scope-definition/intent-backlog.md`.
- [architecture §7] `ideation/feasibility/architecture-proposal.md`.
- [pg-rls] https://www.postgresql.org/docs/16/ddl-rowsecurity.html — retrieved
  2026-10-17.
- [org: Testing Posture] `aidlc/spaces/default/memory/org.md`.
- [construction-phase rules]
  `aidlc/spaces/default/memory/phases/construction.md` § Security.
