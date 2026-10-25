## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-25T08:22:55Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | aidlc/spaces/default/intents/261022-remaining-slices/construction/releasing-safely/nfr-design/security-design.md § 3 "The query, run against the live schema" and "Two facts about `0007` that this assertion must survive" | The document's own Sources line says "`0007`'s three columns," and the upstream functional design (`functional-design/entities.md` lines 99-149, 221-223) is explicit that three columns contradict their table's `RETAIN_WITH_BASIS` disposition and must be fixed in `0007`: `enrollment.student_account_id`, `payment_claim.submitted_by_account_id`, and `queued_submission.submitted_by_account_id` ("`queued_submission` is the third"). But § 3 of this document says "`0007` changes **two** `ondelete` values," analyzes "Two of the three columns are `NOT NULL`" without ever saying which two (or naming the third), and its constraint-naming table (the two rows under "Two facts about `0007`") lists only the two `enrollment` constraints — `payment_claim` and `queued_submission` never appear anywhere in the document outside the Sources line. I verified in `app/db/models.py` that `payment_claim.submitted_by_account_id` (line 876) and `queued_submission.submitted_by_account_id` (line 1243) are both `ForeignKey("account.id", ondelete="CASCADE")` and `nullable=False`, matching the functional design's claim and confirming the omission is real, not a false alarm. The § 7 table's "No contradicting CASCADE exists, transitively" and "The assertion reads the database... the two provably disagree on two constraint names today" rows, and the NFR14.83/NFR14.99/NFR14.82 traceability rows claiming "OK" coverage, all inherit this gap: as written, the design only specifies a verifier and a migration scope for two of the three columns the human decision and the upstream functional design require `0007` to fix. | Rewrite § 3 (and § 6 item 4, and the § 7 obligations table) to name and analyze all three columns `0007` must alter: `enrollment.student_account_id`, `payment_claim.submitted_by_account_id`, `queued_submission.submitted_by_account_id`. State explicitly which two are `NOT NULL` (per the functional design, `payment_claim` and `queued_submission`'s columns), confirm or correct the constraint-naming status of the `payment_claim`/`queued_submission` FKs (the functional design says these were "created by `0005`"/"`0006`" using the naming convention, unlike the two drifted `enrollment` constraints — if that is right, say so rather than silently restricting the naming-drift discussion to two constraints that happen to be the only drifted ones), and reconcile the "0007 changes two ondelete values" sentence with the Sources line's "three columns" claim. | Resolved (reviewer) |
| R-02 | Major | aidlc/spaces/default/intents/261022-remaining-slices/construction/releasing-safely/nfr-design/security-design.md § 3 "`0007` must move a deliberately pinned head" and § 7's "The pinned head moves deliberately" row | The subsection names only `tests/db/test_no_d5_migration.py`'s `EXPECTED_REVISIONS`/`EXPECTED_HEAD` pin as something `0007` will break. I independently found two more revision-pinned assertions that will fail the same way and are not named anywhere in the document: `tests/db/test_migration_from_head.py::test_the_head_revision_advanced` (`assert revision == "0006"`, after a from-`0001` upgrade) and `tests/db/test_migration_runs.py::test_the_schema_is_at_the_head_revision` (`assert revision == "0006"`, against `restricted_session`). A third, more consequential one lives outside `tests/db/` entirely and is of a different kind — not a migration-test pin but an API contract assertion: `tests/auth/test_endpoints.py:194` — `assert body["migration_revision"] == "0006"`, the health-endpoint smoke check the team's own Deployment practice names as part of the post-deploy smoke set. An implementer who updates only the one pin the document names, verifies `make check` is green on the migration suite, and ships would plausibly miss the health-endpoint literal, because it lives in a different test module entirely and nothing in the design points there. (I confirmed `test_migration_rollback_is_total.py`'s `revision == "0001"` assertion is unaffected — it is the failed-migration/rollback path and stays at `0001` regardless of `0007`'s existence, so it is correctly left unnamed.) | Extend the subsection and the § 7 row to name all three revision literals `0007` must update: the two `tests/db/` pins already covered by the same reasoning as `test_no_d5_migration.py`, plus `tests/auth/test_endpoints.py:194`'s `migration_revision` literal. State that the update is one deliberate, reviewable change across all three sites in `0007`'s own commit, for the same "a pin updated with intent and a gate weakened under pressure produce the same diff" reasoning the document already gives for the one pin it names. | New |

> R-01 Reviewer note: Re-read § 3, the header table, and the Sources line against the current document. All three columns `0007` must alter are now named explicitly and consistently: the header table says "`0007` fixes three edges"; § 3's "Why a code-level check would not do" now says "`0007` changes three `ondelete` values"; "Two facts about `0007`" item 1 now names all three (`enrollment.student_account_id`, `payment_claim.submitted_by_account_id`, `queued_submission.submitted_by_account_id`) and correctly states which two are `NOT NULL`; item 2's constraint-naming table is now correctly scoped to only the two `enrollment` constraints that actually drifted (confirmed against `migrations/versions/0001_initial_identity_schema.py:201` and `0002_batches_and_enrollment.py:363`), without overclaiming drift on `payment_claim`/`queued_submission`'s constraints, which the functional design says follow the naming convention. The original gap is fully closed with no residual scoping problem.

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Direct code read: `migrations/versions/0001_initial_identity_schema.py:201`, `0002_batches_and_enrollment.py:363` | `0001` creates `name="fk_enrollment_account_id_account"` (student link, named for the pre-rename column); `0002` creates the guardian FK as `"fk_enrollment_guardian_account"` (hand-named, missing the `_id` segment the convention would produce) | Confirms § 3 item 2's constraint-naming table exactly as stated, verified against the migration source rather than taken from `entities.md`. The reasoning that this is the design reason § 3 must read `pg_constraint` rather than ORM metadata is sound: a metadata-built test would assert against the model's implied names and pass, while the real database's constraints are named differently — exactly the "vacuous pass" pattern this project has hit before (the `fk_enrollment_batch` scheduling note in `test_migration_runs.py` is a second, independent instance of the same `pg_constraint`-vs-metadata discipline already in the codebase, which supports treating this as a real, recurring failure mode rather than a one-off). |
| Direct code read: `tests/db/test_no_d5_migration.py` | `EXPECTED_REVISIONS: Final[int] = 6`, `EXPECTED_HEAD: Final[str] = "0006"`; both asserted by name | Confirms the claim exactly: `0007` existing makes `len(found) == 6` false and the head-prefix check fail. The document's framing ("that is the test working," not a surprise to patch around) is correct and consistent with the project's own forbidden-weakening rule. |
| Direct code read: `tests/db/test_migration_from_head.py`, `tests/db/test_migration_runs.py`, `tests/auth/test_endpoints.py`, `tests/db/test_migration_rollback_is_total.py` | Two further `assert revision == "0006"`-shaped assertions found in `tests/db/`, and one `assert body["migration_revision"] == "0006"` found in `tests/auth/test_endpoints.py:194`, none named in the design; `test_migration_rollback_is_total.py`'s `"0001"` assertion is a different, unaffected scenario | Grounds the Major finding above. Searched `tests/` broadly by grepping for the literal `"0006"` to avoid missing a pin outside `tests/db/`, which is exactly how the fourth one was found. |
| Computed: `ip_prefix_of("2001:db8::1")`, `ip_prefix_of("::1")`, `ip_prefix_of("192.168.1.55")` | `ip_prefix_of` returns the address unchanged for any IPv6 literal (no `.` present) and the first three octets for IPv4 | Confirms the § 2 IPv6 claim precisely: an IPv6 caller's whole address becomes its own `scope_value`, so each address gets an independent `DEL_IP_HOURLY` counter rather than sharing a /24-equivalent bucket. The conclusion that this is worse than the already-accepted IPv4 multi-prefix weakness (an IPv6 /64 delegation gives a single attacker a vastly larger pool of distinct scope values than spanning IPv4 /24s ever could) is sound, and correctly leads to "`DEL_GLOBAL_DAILY` is load-bearing, per-IP is depth" rather than to a prescribed fix. Declining to fix `ip_prefix_of` here is the right call: it is a shared primitive with three existing dependents, and rewriting IPv6 prefix handling in the terminal, release-blocking unit is exactly the kind of change the project's own practices steer away from absent a concrete need. No further ordering failure was found in this analysis. |
| Direct code read: `app/governance/dispositions.py`, `tests/conftest.py`, `tests/db/test_unit_boundaries.py` | No test in the current suite builds its schema from ORM metadata rather than from real migrations; `Base.metadata.tables` is referenced once, for a membership check, not schema creation | DESIGN-4's "vacuous pass" framing is phrased as a general hazard pattern ("a test suite that builds its schema from metadata stays green"), not a claim that such a test currently exists and is silently passing. That phrasing is accurate and does not overclaim; no finding here. |
| Re-read of § 5a in full | Text is byte-for-byte identical to the version reviewed in iteration 1 (already verified against `app/governance/dispositions.py` and `app/contract/routes.py` in that pass and found correct) | §5a is not actually new to this iteration — it was present and already reviewed in iteration 1's pass, where it was found to accurately cover NFR14.88/89/90/16.6/16.7/14.101/17.10/17.11 with NFR14.90 correctly marked partly-automated. No new verification needed; flagged here only so the record is accurate about what changed between iterations. |

### Summary

The Critical finding from iteration 1 is fully and cleanly fixed: `0007`'s three columns are now named consistently everywhere in the document, with the constraint-naming table correctly scoped to the two FKs that actually drifted rather than overclaiming drift on all three. Of the newly-added material, the §1 shadowing analysis was unchanged and remains correct; the §2 IPv6/`ip_prefix_of` analysis is accurate, well-evidenced, and draws the right conclusion without a mistaken prescribed fix; and the §3 constraint-naming addition is verified correct against the actual migration source. One new Major finding remains: the "pinned head" subsection and its traceability row, while correct about the one test they name, understate the blast radius of adding `0007` — two more `tests/db/` assertions and one `tests/auth/` API-contract assertion pin the same `"0006"` literal and will break identically, and the one outside `tests/db/` is the kind an implementer following only this document's pointer would plausibly miss. One Major finding, with zero Critical findings, meets the READY threshold (NOT-READY requires any Critical or more than two Major findings); the finding should still be weighed and addressed before implementation, since a missed revision literal in a health-endpoint smoke test is exactly the kind of thing that surfaces as a confusing CI failure rather than as a design gap.

---

## Resolution - 2026-10-25

**Verdict READY; the one Major is closed.** The Critical from iteration 1 was
confirmed closed, and the reviewer verified the two drifted constraint names
independently against `0001:201` and `0002:363` rather than trusting
`entities.md` - as did the lead, separately. Three arrivals at the same two
names from the migration sources.

| Finding | Closed by |
|---|---|
| **Major** - the pinned-revision blast radius named ONE test and there are FOUR | Section 3 now carries the full table, verified by grep: `test_no_d5_migration.py:29`, `test_migration_from_head.py:142`, `test_migration_runs.py:121`, and **`tests/auth/test_endpoints.py:194`**. The fourth is the sharp one and was independently confirmed: it is NOT a migration test but `body["migration_revision"]` from `/health`, which `team.md`'s Deployment practice makes part of the post-deploy SMOKE set - so a stale literal means the smoke check asserts an old revision against a freshly migrated host. `test_migration_rollback_is_total.py:117`'s `"0001"` is named as a deliberate EXCLUSION, because a blanket replace of the literal is right and a blanket replace of "the revision literal" is not |

**Why the incomplete version was wrong in a way worth recording**, and this
is now in the document itself: naming one test made the change look like a
one-line pin update, so the other three would have surfaced as confusing CI
failures mid-build - exactly the pressure under which a constant gets edited
to make a test pass rather than updated with intent. That is the failure
`project.md` forbids, and the two actions produce the same diff.

### One addition made after this pass began

**DESIGN-8**, and it is the only claim in this document produced by running
something rather than reading it. The governance suite records a near-miss:
an ungranted table is invisible to the restricted role in
`information_schema`, so *"every gate above silently stops covering it"* -
the money assertion skipped `batch.default_fee` until the grant was added.
Section 3's query runs as that same role, so the obvious fear is that it
inherits the same narrowing.

**Measured against a real PostgreSQL 16**: two child tables with
`ON DELETE CASCADE`, `SELECT` granted on one only, both catalogs queried as
the restricted role. `information_schema.tables` saw the granted child only;
**`pg_constraint` saw both.** It is a system catalog and is not
permission-filtered by table grant.

**So section 3 does not inherit the narrowing - and it is a property of the
CATALOG CHOICE, not of care.** A future reader simplifying it to
`information_schema.referential_constraints` would reintroduce the narrowing
silently, and the test would keep passing.

### Noted for the record

The reviewer observes that section 5a was present in iteration 1 and
reviewed then, contrary to the re-dispatch brief's description of it as a
later addition. The brief was wrong on that point; the four genuinely later
additions were DESIGN-3 through DESIGN-6.
