## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-23T14:50:15Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | security-design.md > Section 2, "The two new fields" | Says the schema-wide invariant "covers" the new fields without a new test, but the gate is a forbidden-name exclusion list, not an allowlist, so an unnamed field passes by omission rather than by being actively checked | State explicitly that coverage is passive (the new fields are simply never on the forbidden list) so a future reader does not read "covered" as "actively verified safe" | New |
| R-02 | Minor | performance-design.md > Section 1, "The count" | The conditional aggregate (FILTER) is confirmed as a first-of-its-kind construct in this codebase (verified: no FILTER usage anywhere in app/), but the design does not note whether SQLAlchemy's `.filter()` on a function element has been smoke-tested against the project's pinned SQLAlchemy 2.1.5, only that the library "exposes" it | Note that a quick syntax check against the pinned SQLAlchemy version is worth doing in Code Generation, since this is the first use of the construct | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| traceability (nfr-design, traceability.json) | passed | Every NFRx.y in the coverage list resolves and cites prose that addresses it |
| required-sections (security-design.md) | passed | Template sections present |
| required-sections (performance-design.md) | passed | Template sections present |
| required-sections (logical-components.md) | passed | Template sections present |
| upstream-coverage (security-design.md) | passed | Cites nfr-requirements and functional-design rules it draws from |
| upstream-coverage (performance-design.md) | passed | Cites nfr-requirements and functional-design rules it draws from |
| upstream-coverage (logical-components.md) | passed | Cites nfr-requirements and prior-unit logical-components it draws from |

### Summary

Every verifiable claim against live code checked out: `list_batches` (service.py:448-495) is reproduced accurately as three bounded statements; no `FILTER` aggregate exists anywhere in `app/`, confirming the stated caveat that the conditional-aggregate choice is a first; `remove_enrollment` genuinely refuses on two independent conditions (acceptance via `_nobody_accepted` and the two `relink_blocked_at` erasure markers) and `RosterRowResponse` today carries neither the planned decision fields nor the erasure markers, so the stated client-derivation hazard is real; `list_guardian_children` has no decision predicate of its own and is safe only via `GuardianLens` grant, exactly as claimed. The child-switch mechanism (a selection rather than a navigation push, eliminating the back-stack entry) is sound and does genuinely relocate rather than merely rename the problem — there is no server-side way to distinguish a legitimate second request from a stale Back navigation, so the UI-structural fix is the only available lever. The unit's `ui` typing and its claim of no infrastructure/migration impact both check out against the repository. Two minor documentation-precision gaps noted above do not block readiness.
