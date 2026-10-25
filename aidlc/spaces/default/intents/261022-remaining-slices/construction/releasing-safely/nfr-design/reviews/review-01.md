## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-25T08:22:55Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | aidlc/spaces/default/intents/261022-remaining-slices/construction/releasing-safely/nfr-design/security-design.md § 3 "The query, run against the live schema" and "Two facts about `0007` that this assertion must survive" | The document's own Sources line says "`0007`'s three columns," and the upstream functional design (`functional-design/entities.md` lines 99-149, 221-223) is explicit that three columns contradict their table's `RETAIN_WITH_BASIS` disposition and must be fixed in `0007`: `enrollment.student_account_id`, `payment_claim.submitted_by_account_id`, and `queued_submission.submitted_by_account_id` ("`queued_submission` is the third"). But § 3 of this document says "`0007` changes **two** `ondelete` values," analyzes "Two of the three columns are `NOT NULL`" without ever saying which two (or naming the third), and its constraint-naming table (the two rows under "Two facts about `0007`") lists only the two `enrollment` constraints — `payment_claim` and `queued_submission` never appear anywhere in the document outside the Sources line. I verified in `app/db/models.py` that `payment_claim.submitted_by_account_id` (line 876) and `queued_submission.submitted_by_account_id` (line 1243) are both `ForeignKey("account.id", ondelete="CASCADE")` and `nullable=False`, matching the functional design's claim and confirming the omission is real, not a false alarm. The § 7 table's "No contradicting CASCADE exists, transitively" and "The assertion reads the database... the two provably disagree on two constraint names today" rows, and the NFR14.83/NFR14.99/NFR14.82 traceability rows claiming "OK" coverage, all inherit this gap: as written, the design only specifies a verifier and a migration scope for two of the three columns the human decision and the upstream functional design require `0007` to fix. | Rewrite § 3 (and § 6 item 4, and the § 7 obligations table) to name and analyze all three columns `0007` must alter: `enrollment.student_account_id`, `payment_claim.submitted_by_account_id`, `queued_submission.submitted_by_account_id`. State explicitly which two are `NOT NULL` (per the functional design, `payment_claim` and `queued_submission`'s columns), confirm or correct the constraint-naming status of the `payment_claim`/`queued_submission` FKs (the functional design says these were "created by `0005`"/"`0006`" using the naming convention, unlike the two drifted `enrollment` constraints — if that is right, say so rather than silently restricting the naming-drift discussion to two constraints that happen to be the only drifted ones), and reconcile the "0007 changes two ondelete values" sentence with the Sources line's "three columns" claim. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Direct code read: `app/auth/otp.py` `verify()` | `SELECT ... FROM otp_request WHERE phone = :phone ORDER BY issued_at DESC LIMIT 1 FOR UPDATE` — confirmed no purpose predicate anywhere in the query | Confirms the § 1 shadowing claim exactly as stated: a naive post-fetch purpose check would let a later sign-in code shadow an earlier, still-valid deletion code. The prescribed fix (predicate in the `WHERE`, beside `phone`) is correct and is the only ordering that preserves "latest row **for that purpose**" semantics. I found no third ordering failure: the single-use (`consumed_at` set under `FOR UPDATE` in the same transaction) and attempt-ceiling mechanics are purpose-agnostic and are unaffected by adding a purpose predicate to the `WHERE` clause. |
| Direct code read: `app/db/models.py` `RateLimitCounter.scope_kind` / `OtpRequest.purpose` | `scope_kind` is `String(16)` (line 447); `purpose` is `String(32)` (line 335) | Confirms the § 2 width claim and arithmetic. Recomputed independently: `del_number_hour`=15, `del_number_day`=14, `del_ip_hour`=11, `del_global_day`=14 (all ≤16, fit); `deletion_number_day`=19, `delete_number_day`=17 (both >16, correctly rejected as not fitting). `purpose="deletion"` is 8 characters against `String(32)`, needs no migration, as claimed. No other width constraint on the counter path was missed. |
| Direct code read: `app/auth/ceilings.py` `ScopeKind`, `_consume`, `_signup_scopes` | Two existing cascades over one `_consume()`; `_signup_scopes` has no global member, with the stated reason ("the OTP cascade's own global daily ceiling" already bounds signup's downstream SMS cost) | Confirms the § 2 claim that signup's no-global reasoning does not transfer to deletion: deletion's hazard is spending the budget sign-in needs, not double-counting its own cost, so `DEL_GLOBAL_DAILY` is correctly required. The narrowest-first + release-on-refusal accounting in `_consume` is real and would be correctly inherited by a `check_and_consume_deletion()` built as a third cascade, as designed — "D6 writes no new `_consume()`" is literally true against the code. |
| Direct code read: `tests/db/test_governance.py` `restricted_session` fixture | `restricted_session` connects as the restricted non-superuser application role (confirmed via the fixture's existing use across `test_lookup.py` and the governance tests) and already runs raw `pg_tables`/`information_schema.columns` queries | Supports § 3's claim that a `pg_constraint` query needs no new fixture or privilege: reading PostgreSQL system catalogs does not require elevated privilege beyond normal `SELECT`, consistent with the document's own honest caveat that this is "the one privacy-suite member where the restricted role buys nothing extra." |
| Direct code read: `app/governance/dispositions.py`, `app/contract/routes.py` | `account`'s current disposition is `ANONYMIZE_IN_PLACE` with a basis arguing for anonymization (phone-number-reuse hazard); `PUBLIC_ROUTES` comment already states "Exactly eight" and the frozenset has 8 entries, including the two pre-declared, unregistered `/account-deletion` routes | Confirms the § 5a / NFR14.101 claim that the `account` entry's basis would be "faithfully published as the reasoning for a hard delete" unless corrected — a real and well-targeted finding. Also confirms the `project.md`-recorded drift finding (comment vs. frozenset count) was already fixed by the time of this unit; no action needed there. |
| Direct code read: `app/db/models.py` FK chain `account → owner → batch → enrollment/batch_subject/...` | `owner.account_id`, `batch.owner_id`, `batch_subject.batch_id` all `ondelete="CASCADE"`, `nullable=False` | Confirms the § 3/§ 4 "owner -> batch" chain is real and matches the functional design's "account --CASCADE--> owner --CASCADE--> batch --> enrollment --> six tables" diagram, supporting the load-bearing claim that BR1.6's refusal (§ 4), not a schema fix, is what closes that exposure. |

### Summary

The § 1 purpose-filter/shadowing analysis, the § 2 ceiling-cascade design (including the scope-name arithmetic and the signup-reasoning distinction), and the § 4 refusal-as-precondition design are each independently verified against the built code and are correct, well-evidenced, and implementable without further architectural guidance. The blocking problem is narrower but real: § 3, the document's own candidate for "the strongest thing this unit builds," is internally inconsistent about how many columns migration `0007` must alter and never names the third one (`queued_submission.submitted_by_account_id`) that the upstream functional design identifies as a `CASCADE`-against-`RETAIN_WITH_BASIS` contradiction requiring the same fix as `payment_claim`. Because the `pg_constraint` assertion in § 3 is the mechanism the whole unit is built to make trustworthy against exactly this kind of silent omission, shipping the design with an incomplete account of its own subject undermines the one section meant to catch that class of error.

---

## Resolution - 2026-10-25

**The Critical was found independently and fixed while this review was
running**, so the reviewer read the pre-fix document. Both arrivals agree on
the defect and on its cause, which is the useful part: it was found twice,
by different routes - the reviewer by cross-checking `entities.md`, the lead
by re-reading the functional design's `0007` enumeration before writing
infrastructure-design.

| Finding | Closed by |
|---|---|
| **Critical** - section 3 says `0007` changes TWO `ondelete` values while the Sources line says three; `payment_claim.submitted_by_account_id` and `queued_submission.submitted_by_account_id` are never named | Corrected throughout: the header table now reads "fixes three edges; nothing stops a FOURTH being added", section 3's body reads "changes three `ondelete` values ... those three columns", and the NOT NULL subsection **names all three explicitly with their nullability** - `enrollment.student_account_id` (nullable), `payment_claim.submitted_by_account_id` and `queued_submission.submitted_by_account_id` (both `NOT NULL`) |

**Verified in the source rather than accepted from either account**:
`app/db/models.py:876` and `:1243` both carry
`ForeignKey("account.id", ondelete="CASCADE")` with `nullable=False`, matching
`entities.md`'s enumeration of three contradicting columns against
`RETAIN_WITH_BASIS` tables.

**The reviewer's framing of WHY it mattered is kept**, because it is sharper
than "a count was wrong": section 3's `pg_constraint` assertion exists
precisely to catch a cascade silently contradicting a retention disposition,
so the design silently omitting one of three such columns undermines the one
mechanism built to prevent that exact failure.

### Four additions made after the reviewer began, which it did not see

Each was found by reading built code or the migration history, and each is
recorded in `traceability.json` as a DESIGN-n row with no upstream id:

- **DESIGN-3** - two of the three columns are `NOT NULL`, so a flip of
  `ondelete` alone fails at migration time. The hazard is the reverse
  ordering, which leaves the cascade live while the schema looks prepared.
- **DESIGN-4** - two constraint NAMES in the database differ from the
  model's, because `0002` renamed a column with `alter_column`, which does
  not rename its constraint. **This is the design reason section 3 reads
  `pg_constraint` rather than ORM metadata**, upgrading that choice from a
  preference to a requirement: a migration written against implied names
  fails on a migrated database and PASSES against a metadata-built one.
- **DESIGN-5** - `tests/db/test_no_d5_migration.py` pins
  `EXPECTED_REVISIONS = 6` and `EXPECTED_HEAD = "0006"`, so `0007` will fail
  it. The pin must move as part of `0007`'s own change, because updating a
  pin with intent and weakening a gate under pressure produce the same diff.
- **DESIGN-6** - `ip_prefix_of` verified at `app/api/auth.py:74`: a /24
  prefix, and an IPv6 address (no dot) becomes its own whole-address scope.
  Neither is fixed here; the consequence recorded is that `DEL_GLOBAL_DAILY`
  is **load-bearing** and the per-IP scope is depth, which is the opposite of
  how a reader would rank them.
