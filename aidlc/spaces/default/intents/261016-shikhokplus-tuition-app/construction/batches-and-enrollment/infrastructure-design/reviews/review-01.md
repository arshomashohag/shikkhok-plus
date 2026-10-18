## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T15:09:19Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | `cicd-pipeline.md` > B. The money gate changes shape here | The row for `batch.fee_due_day` names the remedy as "allowlist," but `app/contract/money_schema.py` (`money_schema_violations`, `_is_numeric_money_name`, `_is_unconstrained_money_name`) has no allowlist or exception parameter today — it is a pure name-token predicate with no per-column suppression hook. No other allowlist mechanism in `app/contract/` covers this gate (`LENS_EXEMPT_AUTHENTICATED` and `PUBLIC_ROUTES` are a different, route-lens gate). A developer reading this table would not know an allowlist capability has to be built into the gate function itself before `batch.fee_due_day` can pass; the text reads as if the lever already exists and only needs an entry added. | State explicitly that `money_schema_violations` currently has no exception mechanism and that adding one (e.g., a `NON_MONEY_ALLOWLIST: frozenset[tuple[str, str]]` checked before the name-token match fires) is part of this Unit's code-generation scope, not a pre-existing lever being extended. | New |
| R-02 | Minor | `infrastructure-specification.md` > B.1 | The claim "the deploy stops at step 4 ... with the data untouched" is correct under the project's actual Alembic configuration (`migrations/env.py` uses `context.begin_transaction()` with no `transactional_ddl=False` override, so Postgres rolls back the whole `upgrade()` function on the guard's `RAISE`), but the document never names this mechanism or cites `env.py`. Given this Unit's record of claims stated as fact that turned out to rest on an unstated or unverified assumption (prior stages: a fabricated container-verification claim, four traceability rows citing absent content), an unqualified "data untouched" claim with no cited mechanism is the same shape of risk even though it happens to be true here. | Add one sentence naming why the rollback is automatic — e.g. "Alembic wraps each revision in one transaction (`migrations/env.py`), so a `RAISE` from the guard rolls back the preceding `ADD COLUMN`/`RENAME COLUMN` statements with it" — so the claim is traceable to a checkable mechanism rather than asserted. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| traceability.json structural check | PASS — 40 `upstream_ids` match 40 `coverage` rows 1:1, no orphans or mismatches; 3 `reverse` rows correctly carry no upstream id | The 40-row traceability table is internally consistent |
| Cross-check vs `migrations/versions/0001_initial_identity_schema.py` and `migrations/env.py` | `0002` migration does not exist yet (expected — U4 code generation has not run); `env.py` confirms default Alembic transactional DDL, no override | Supports the Minor finding above — the mechanism exists but is uncited |
| Cross-check vs `app/db/seed_skeleton.py` | Matches the described shape exactly: one `role='guardian'` row, no student row, removal flagged as a B5 obligation | §B.1's premise is accurate |
| Cross-check vs `app/contract/money_schema.py` and `tests/contract/test_money_schema.py` | Confirmed the gate matches on `MONEY_NAME_TOKENS` including `fee`/`due` against `number`/`integer`-typed fields, so `batch.fee_due_day` (an integer) would indeed be flagged; confirmed no allowlist mechanism exists in that module | Confirms the predicted false positive is real; confirms the Major finding above — the named remedy has no code to attach to yet |
| Cross-check vs `construction/identity-and-access/infrastructure-design/monitoring-design.md` | U3's alert table has exactly six rows (SMS ceiling, gateway balance, backup failed, refresh reuse, audit write failed, smoke failed) | "U3's six alerts stand" is accurate |
| Cross-check vs `construction/identity-and-access/infrastructure-design/infrastructure-specification.md` | Confirms USD 25/50 budget figures match B3's own stated numbers; topology table unchanged | No contradiction with inherited U3 infrastructure |
| Cross-check of N/A traceability rows against `nfr-requirements/*.md` for this Unit | Each N/A row (NFR4.1, NFR4.2, NFR6.11, NFR6.13, NFR10.6, NFR10.7, NFR10.10–10.12, NFR14.12/13/15/17/18/21, NFR8.8–8.10/8.12, NFR6.1/6.3) is genuinely a client-code, query-shape, or test-asserted decision with nothing to provision | No genuinely-provisioned item was waved off as N/A |

### Summary

The deploy-ordering design (seed-row deletion before the fold-guarded migration) is sound and verified against the actual `reliability-design.md` §A.0 rationale and the real `seed_skeleton.py` shape; the "data untouched on refusal" claim holds given the project's actual Alembic transaction configuration, though the artifact never names that mechanism. The one substantive gap is that the CI money-gate "allowlist" remedy for `batch.fee_due_day` describes a lever that does not exist in the current gate code, which a developer implementing this Unit would need to build rather than merely configure — underspecified rather than wrong, and not blocking at this design stage since U4's code has not been generated yet. Both findings are specification gaps correctable with a sentence each, not architectural flaws; the ready verdict holds.
