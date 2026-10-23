## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-23T05:20:23Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | construction/running-a-batch/functional-design/traceability.json > coverage array | Several AC-to-rule mappings do not match what the cited rule actually states, so the coverage looks closed when it is not | See prose below; re-map each row to the rule or spec section that truly discharges it, or mark it Deferred/Partial | New |
| R-02 | Minor | construction/running-a-batch/functional-design/functional-spec.md > section 1, response change table | Proposed fields `accepted_count`/`seat_count` are new names rather than the existing `enrollment_count` on `BatchResponse`, with no note on whether `enrollment_count` is kept, renamed, or duplicated | State explicitly whether `enrollment_count` is retained, renamed to `seat_count`, or both exist, since Code Generation needs one answer | New |
| R-03 | Minor | construction/running-a-batch/functional-design/traceability.json > note field | The note explains the AC-suffix regex gap for five IDs but the coverage array actually lists ten upstream_ids including some with and some without this issue, making it unclear which five are affected | Name the five base-form IDs explicitly in the note or in a dedicated column | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| traceability (sensor fire) | passed | The sensor's own structural check is satisfied; it does not catch semantic mismatches between an AC and the rule it cites, which is what the Major finding above covers |
| required-sections | passed | functional-spec.md carries its required sections |
| upstream-coverage | passed | Declared upstream sources are present and cited |
| linter | not applicable | Filter targets `**/*.{ts,js}`; this stage produces Markdown design artifacts, not source files |
| type-check | not applicable | Filter targets `**/*.{tsx,ts}`; same reason |

### Central claim verification

Verified directly against live code (`app/api/batches.py`, `app/schemas/batches.py`,
`app/batches/service.py`, `app/db/models.py`). `_roster_status`
(`app/api/batches.py:71-85`) computes `dormant | inactive | active` from only
`row.is_dormant` (= `_nobody_accepted`, true when **neither** link is
`accepted`) and `row.inactive_from`. A seat whose student link is `accepted`
and whose guardian link is `declined` is therefore not dormant (one link
accepted), carries no `inactive_from`, and falls through to `active` —
exactly the loss of the split-decision distinction the spec describes. The
claim is accurate and the fix (`student_state`/`guardian_state` fields
alongside the unchanged `status`) is the minimum response-shape widening that
closes it; it does not fold the two axes together, which the spec correctly
identifies as the trap (an earlier merged bug of the same shape, per D1's
BR7.1/BR7.2 sweep).

`guardian_account_id` is confirmed nullable on `Enrollment`
(`app/db/models.py:434`), so the `absent` fourth value is a real case, not a
defensive one, and the reasoning that `pending` would silently inflate the
"outstanding decisions" count by the number of guardian-less seats holds.

BR1.4's inclusion of declined seats in the denominator is internally
consistent with BR1.1 (declined is marked, not removed from the roster) and
with AC1.3.5a's own wording ("9 of 12"), and the stated alternative's failure
mode (a shrinking denominator indistinguishable from a removal) is real and
correctly reasoned.

BR3.1's "read from the server, never derived" instruction is justified, not
cargo-culted: `remove_enrollment` (`app/batches/service.py:294-351`) refuses
on two independently-read conditions — `_nobody_accepted` (decision columns)
and the two erasure-marker columns — neither of which the roster row exposes
today. A client deriving removability from `studentState`/`guardianState`
alone would report a seat as removable when an erasure marker is set, which
is exactly the silent-regression shape D1's own sweep (BR7.1/BR7.2) was
written to stop. The rule is the correct generalization of that lesson, not
an over-application of it.

Scope claim checked against the seven listed endpoints in
`app/api/batches.py`: all seven exist and are lens-resolved today
(`POST /v1/batches`, `GET /v1/batches`, `GET /v1/batches/{id}/roster`,
`POST /v1/batches/{id}/enrollments`, `PATCH
/enrollments/{id}/inactive-from`, `DELETE /enrollments/{id}`,
`GET /v1/guardian/children`). No new route is proposed and none of D2's
scope belongs to D1 (acceptance/decline, which D2 only renders) or D3
(money/fee cycles, which D2 explicitly defers as Open/D3's in both
`functional-spec.md` and `rules.md`). `BatchResponse.enrollment_count`
already exists server-side; D2 proposes `accepted_count`/`seat_count` as
additional fields rather than acknowledging the existing field by name (see
Minor finding).

D2's citation of D1's rules.md (BR1.1, BR5.2, BR5.4, BR7.1, BR7.2) was
checked word-for-word against the source file: all five exist with the
stated IDs and matching semantics, and none is restated with different
wording in D2's own `rules.md` — the eleven D2 rules (BR1.1-1.4, BR2.1-2.3,
BR3.1-3.2, BR4.1-4.2) each cover a distinct presentation/response-shape
decision not already stated by D1. The "What D2 does not re-decide" section
accurately lists the D1 rules it depends on.

`frontend-components.md`'s three named erosion paths (empty-state count
comparison, declined-state comparison, client-side row counting) match the
three concrete places D2's own design would otherwise fall into them
(`BatchesUiState.Empty` vs `Loaded`, `RosterRow.isDeclined`,
`acceptedCount`/`seatCount` sourced from the server) — the document's own
state tables consistently route each of these through a mapper-produced
field rather than a raw comparison, so the design does not visibly violate
the rule it states.

### AC coverage mapping — base-form mismatches

The traceability sensor's structural check passed, but several `coverage`
rows map an AC to a rule whose actual statement (checked against the live
`rules.md` text) does not discharge that AC:

- **AC1.3.2** ("no notification…sent to that number") is mapped to `BR1.1
  BR1.2`, which are "declined marked per row" and "accepted count shown" —
  neither rule addresses notification suppression. The actual discharging
  text is W2 in `functional-spec.md` ("Nothing is sent to the person named")
  and AC1.15.4, which is a separate upstream_id already covered elsewhere.
- **AC1.3.4** ("states pending/accepted/declined…offers a path to correct the
  phone number") is mapped to `BR2.1 BR2.2` (split-seat rendering, absent
  state) — neither addresses a single-seat detail view or a correction path.
  No D2 rule currently covers a correction-path action.
- **AC1.3.6** ("never accepted distinguishable from accepted-then-deleted")
  is mapped to `BR3.2`, which is about the two removal-refusal codes
  (claimed vs erased) at removal time, not about a persistent read-side
  distinction between two already-removed states.
- **AC1.15.1** ("pending stays indefinitely, no expiry, no automatic
  deactivation") is mapped to `BR1.1 BR1.4` (declined-marking, denominator
  inclusion) — neither rule states anything about absence of expiry.

These are classification errors in the coverage table rather than evidence
that the underlying behaviour is unbuilt — the spec and rules elsewhere do
address several of these topics (e.g., AC1.3.4's correction path is implied
by W4's removal-recovery workflow) — but as written the traceability file
overstates how precisely these four criteria are discharged by the rules it
cites, which is a review-worthy gap in the mapping itself rather than in the
design's substance.

### Summary

The central claim — that D2's only backend change is widening the roster
response to expose per-link acceptance state — is verified accurate against
the live code, and the proposed fix is minimal and correctly scoped: it adds
the missing axis without collapsing it into the existing `status` enum or
duplicating logic D1 already owns. Rule citations to D1 are accurate and not
restated. The one substantive issue is in `traceability.json`: four of ten
coverage rows cite a rule that does not actually discharge the stated
acceptance criterion, which should be corrected before this stage's mapping
is relied on for downstream coverage checks, but it does not reflect a gap
in the underlying design.
