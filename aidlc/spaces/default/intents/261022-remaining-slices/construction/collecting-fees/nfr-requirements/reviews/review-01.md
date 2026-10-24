## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-23T17:43:46Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | tech-stack-decisions.md § 2 and reliability-requirements.md NFR18.5/NFR25.9 | The recommended "host-level cron entry" does not survive a deploy: `deploy.yml`'s "Roll the instance" step replaces the ASG instance and re-runs `user_data` on every deploy, and `infra/modules/app/main.tf:331-333` fixes the ASG at `min_size=max_size=desired_capacity=1`. A cron line added by hand to the running host is wiped the next time anyone deploys, which is exactly the silent-and-indefinite failure NFR25.9 exists to catch — and nothing in either file says the entry must be installed by `user_data` (Terraform-managed) rather than by an operator logging into the box. | State in tech-stack-decisions.md § 2 that the chosen scheduling mechanism (cron or in-process) must be provisioned through `user_data.sh.tftpl`, not applied by hand, and add a sentence to NFR25.9 or NFR18.5 naming "a deploy silently unscheduling generation" as the specific failure the absence-of-success alert must catch. | New |
| R-02 | Minor | scalability-requirements.md NFR6.38 and tech-stack-decisions.md § 2 | Both files state the scheduler decision is cost-indifferent at `desired_capacity = 1` (no double-firing risk) but do not record that this safety is contingent on the ASG staying single-instance — if it is ever raised to 2 for availability, both a host cron and an in-process scheduler would fire twice per node, and only `(enrollment_id, period)`'s unique constraint prevents a double charge. | Add one sentence noting that the idempotency constraint, not the scheduler's own uniqueness, is what remains the actual safety net if instance count ever changes, so a future reader does not mistake single-instance capacity for the guarantee. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| required-sections (all 6 docs) | PASS (per dispatch) | Confirmed structurally sound; not independently re-run, no reason to doubt it |
| traceability | PASS (per dispatch) | `traceability.json`'s 105 IDs cross-checked by spot sampling against the six documents; every sampled citation resolves |

### Verification performed

**NFR9 collision and the remaining ID space.** I independently re-derived the high-water mark for every base (NFR1 through NFR26) by grepping both `261016-shikhokplus-tuition-app` and `261022-remaining-slices` for every `NFR<base>.<n>` occurrence and sorting. For every base with a D3 contribution, the top ID present in the combined corpus is exactly the one D3 itself minted (e.g. `NFR6.39`, `NFR9.38`, `NFR14.47`, `NFR20.23`, `NFR23.10`, `NFR25.17`, `NFR26.6`), confirming no base runs higher anywhere that D3's file failed to account for. This corroborates the dispatch's NFR9 finding rather than contradicting it: NFR9 was recomputed correctly to `.34` and D3's own top is `.38`, consistent with the five collisions the lead caught and fixed.

**Figures recomputed independently, not trusted:**
- Partial approval: charge 1000, claim 1500, approved 600 → two-sided outstanding = charge − approved = 400 (confirmed; `rules.md` BR5.3 states the formula as charged − approved, matching).
- Clamp non-degrading: anchor day 31 generating from a 28-day February (2027) gives due date 2027-02-28; the next period, March 2027 (31 days), uses `min(31, 31) = 31` against the **stored** anchor (31), giving 2027-03-31 — confirmed by `calendar.monthrange`. BR2.2's "`Batch.fee_due_day` is NOT rewritten" is exactly what keeps this non-degrading.
- Five-year ledger fold: 60 students × 240 entries (60 months × 4/month) = 14,400 — confirmed by direct multiplication, and the batch-wide capacity-planning figures (3,000 enrollments × 4/month × 12 = 144,000/yr, ×5 = 720,000) also check out.
- `derive()` single-pass claim: read `app/money/_ledger.py` directly — one `for item in entries` at line 117, a `match` over `LedgerEntryKind` with no nested loop, two `defaultdict`s (`cycle_charged`, `cycle_relieved`) filled inside that same loop. Confirmed as stated.

**RLS decision (NFR14.36/.37).** Read `migrations/versions/0001_initial_identity_schema.py:261-266` directly: `ENABLE ROW LEVEL SECURITY` followed by `FORCE ROW LEVEL SECURITY` on `profile` only — no other table. The reasoning given (an enrollment-scoped table has no `account_id`-shaped column a `USING` clause can test directly; its authorization is a join across `app/authz/resolve.py`'s three branches) is sound: a `USING` clause duplicating that branch logic in SQL would be a second, unmeasured implementation of the same rule, which is exactly the failure mode this project's own corrections log warns about (duplicated business logic drifting from its source of truth). This is a defensible judgment call, documented with its reasoning, revisited on an explicit trigger (NFR14.37) — the bar this project holds decisions to.

**BR6.4 direction (NFR14.32) and `app/contract/privacy.py` read directly.** `is_teacher_facing`/`TeacherLens` and the `OWNER_PRIVATE_FIELDS`/`FORBIDDEN_ACCOUNT_ID_FIELDS` iteration in `privacy.py` genuinely check only the teacher-facing direction (profile fields and account ids must not leak into a teacher-lens response). There is no existing mechanism checking the reverse (a teacher-authored field leaking into an over-broad student/guardian response), confirming the file's claim that this invariant is silent on the new direction. NFR14.32 proposes a new test (one exact-match response schema, scoped to a student/guardian lens on the right enrollment) rather than claiming an existing mechanism covers it — correctly framed as new work, not a restatement of something built.

**NFR12.x omission.** Read `app/contract/routes.py`'s `PUBLIC_ROUTES` directly: exactly 8 unauthenticated routes, all attributable to D1 (signup, lookup, the two pre-declared D6 deletion routes). None belongs to D3's fee/payment surface. The claim that D3 adds no unauthenticated route and therefore mints no `NFR12.x` is correct.

**Verifiers.** Every requirement I sampled across all six files names a target that is either a code-level assertion (branch coverage, statement-count assertion, unique-constraint behavior) or, where none exists, is stated plainly as unverified (observability-requirements.md § 6 explicitly lists the alert-delivery rehearsal and the Bangla layout check as having no automated verifier, in the exact form the project's corrections record requires). No obligation reads as a verifier when it is actually a description of a manual check.

### Summary

The two findings above are genuine and both concern the one real technology decision this unit makes — the scheduler — and both are grounded in code I read directly (`deploy.yml`, `infra/modules/app/main.tf`), not in an unverified claim handed to me mid-review. Neither rises to Critical: the artifact already marks the scheduler choice as "a recommendation, not a fait accompli" pending human decision, and the reliability properties (NFR6.39, NFR19.9/.10) are correctly stated against the job rather than its scheduler, so the job's correctness does not depend on the gap being closed before this stage can be approved — but a developer implementing the recommendation as written would plausibly add the cron line by hand and silently reintroduce the exact failure mode NFR25.9 was written to catch. With one Major and one Minor finding, neither blocking under this project's verdict rule (READY allows any Minor count and up to 2 Major), the artifacts remain implementable: every other load-bearing claim I checked independently — the NFR9 ID collision and its fix, the `derive()` single-pass property, the partial-approval and clamp arithmetic, the RLS decision's reasoning, the BR6.4 directional gap, and the NFR12.x omission — held up under direct verification against the code and upstream artifacts.
