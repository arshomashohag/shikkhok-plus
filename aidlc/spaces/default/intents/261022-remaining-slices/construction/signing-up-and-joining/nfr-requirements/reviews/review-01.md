## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-23T02:21:44Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | tech-stack-decisions.md > "One item on that list is genuinely still open" | Claims no Kotlin coverage report exists, verified 2026-10-23. `android/coverage.gradle.kts` is applied from `build.gradle.kts:265`, registers a JaCoCo report, and a committed `coverage-floor.txt` (30.95) was added the same day by commit eec0f92. The ratchet already exists. | Re-verify the Android toolchain state against the current tree and correct the claim: either the ratchet is live and the open item is closed, or state precisely what remains missing. | New |
| R-02 | Minor | scalability-requirements.md > NFR6.22 | States flatly that nothing bounds `rate_limit_counter` growth and frames purge-vs-accept as fully open. `app/governance/dispositions.py` already declares a retention class (HOURS_48, HARD_DELETE) for this exact table with a stated basis. Only the scheduled purge job is missing, not the retention decision. | Acknowledge the existing governance entry and narrow the gap to "the declared 48-hour retention has no enforcing job," rather than presenting the whole bound as undecided. | New |
| R-03 | Minor | security-requirements.md, performance-requirements.md, reliability-requirements.md, observability-requirements.md > NFR18.x, NFR19.x, NFR24.x-26.x | These five NFR number blocks (availability, migration safety, logging, alerting, SLI/SLO) have no base entry in requirements.md (which stops at NFR23) and are absent from traceability.json's upstream_ids, with no N/A-with-justification recorded for them either. | Either anchor these blocks to an inception source or a unit-level rule, or add them to traceability.json as unit-invented NFRs with an explicit justification, per the stage's own traceability contract. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| traceability | PASS | All four declared upstream_ids (NFR20-23) are covered by derived IDs; it does not flag the NFR18/19/24-26 blocks because they are never enumerated as upstream_ids in the first place. |
| required-sections | PASS | security-requirements.md carries the required sections. |
| upstream-coverage | PASS | Upstream artifacts are cited and used. |
| linter | N/A | No `.ts`/`.js` files among these artifacts; sensor correctly declined to fire. |
| type-check | N/A | No `.ts`/`.tsx` files among these artifacts; sensor correctly declined to fire. |

### ID-collision and citation verification

Independently rebuilt the full set of `NFRx.y` IDs *defined* (table row first cell) across all four merged units of the prior record (`api-contract`, `batches-and-enrollment`, `identity-and-access`, `money-core`) and compared against every ID defined in this unit's six artifacts: zero collisions. The stated high-water marks (NFR6 from .20, NFR7 from .5, NFR10 from .13, NFR12 from .3, NFR13 from .4, NFR14 from .22) are in fact one tick more conservative than the true maxima found in the prior record (actual maxima: .18, .4, .12, .2, .3, .21 respectively), so the numbering is safe with margin. The two bare citations flagged for scrutiny, `NFR6.1` and `NFR12.1`, are both genuinely defined in the prior record's `identity-and-access`/`api-contract` artifacts and are used here only as citations (never redefined). No ID is cited in these six files without resolving either to a row defined here or to a prior-record ID.

### Live-code claim verification

- `app/auth/ceilings.py`: confirmed — `ScopeKind` declaration order is stated and used as evaluation order, `_scopes()` is a hardcoded static list, only `ScopeKind.GLOBAL_DAILY` calls `fire_ceiling_alert`, counters are upserted into the `rate_limit_counter` table (datastore-backed), and a refused scope's increment is released via `_release`.
- `app/audit/log.py`: confirmed — `AuthEvent` is a closed `enum.Enum`, the row has no free-form string field besides `correlation_id`, and the write path fails open with a `critical` log on failure.
- `app/db/models.py:267` / migration `0001`: confirmed — `rate_limit_counter` has no purge, cleanup, or expiry logic anywhere in `app/` (only INSERT/UPDATE for increment and decrement). A retention class does exist for this table in `app/governance/dispositions.py`, which the artifact does not mention (see Minor finding above).
- `app/authz/resolve.py`: confirmed — `_LENS_QUERY` is a single `sa.text` statement, the guardian branch uses `ORDER BY created_at, id LIMIT 1` exactly as NFR20.1/20.3 describe.
- `pyproject.toml`: confirmed — `app.authz.*` is configured with `strict = true` and `disallow_any_explicit = true` at line 208, matching the artifact's claim (cited as "~207-210"). The companion claims that spotless, detekt and `android/lint.xml`'s `HardwareIds` fatal rule exist are also confirmed. The claim that no Kotlin coverage report exists is **not** confirmed (see Major finding above).

### Summary

The ID-renumbering fix from the prior NOT-READY review holds up under independent verification: no collisions, no dangling internal references, and the bare prior-record citations are genuine. Most live-code assertions this draft makes are accurate and specific. The one Major finding is a factual claim about the Android toolchain that a same-day commit already contradicts, which the human should know before treating that line item as a confirmed gap for a future unit to close. The two Minor findings are narrower than they first appear but worth tightening: the scalability gap is half-closed already, and five NFR blocks were invented without a traceability record, which is a process gap rather than a design flaw. None of these rises to Critical, and the Major finding is a single item whose fix is a one-line correction, not a design change, so it does not block approval.
