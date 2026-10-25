## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-25T02:07:47Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | construction/knowing-how-it-is-going/nfr-requirements/performance-requirements.md > NFR2.13 | NFR2.13 states the computed figure and the Play Console figure as the same quantity: "bundletool's per-ABI download size is the same quantity Play reports, computed from the same bundle". They are close but not identical. `get-size total --dimensions ABI` varies only the ABI dimension and holds screen density, language and SDK level at their defaults, so it reports a figure over a collapsed configuration set; the Console reports the download for one concrete device configuration. The gate's own output is required to assert the identity, so the overstatement gets written into the release gate's failure message, which is where a future reader will trust it most. The headroom makes the difference immaterial today (4.1 MB measured against a 15 MB ceiling) but the claim will outlive the headroom | Restate NFR2.13 as a close proxy rather than the same quantity: say that bundletool computes the download size from the same bundle while varying ABI only, that density, language and SDK are held at defaults, and that the figures may therefore differ by a small margin. Keep the one-off Console comparison, and have it record the observed difference rather than merely confirm faithfulness | New |
| R-02 | Minor | construction/knowing-how-it-is-going/nfr-requirements/performance-requirements.md > section 3, NFR2.12 comparison table | The table's right-hand column describes the bundletool row as "the download size Play would serve", which is the same overstatement as NFR2.13 in shorter form, and the left-hand row describing the transcribed form as measuring "exactly what NFR2 names" sharpens the contrast in the wrong direction | Soften the bundletool row to name what it computes and from which dimensions, so the table and the corrected NFR2.13 agree | New |
| R-03 | Minor | construction/knowing-how-it-is-going/nfr-requirements/tech-stack-decisions.md > NFR2.15, Assumptions | NFR2.15 adds bundletool as a CI dependency and the assumptions note says "nothing in this project pins it yet, and the pinning decision belongs with the lockfile practice". The lockfile practice is assigned to "before D1" and has not landed, so deferring to it leaves this new dependency with no pin and no owner. An unpinned tool that computes the number a release gate blocks on can change the number between runs | Either pin the bundletool version at the point it is added in the release workflow, or state explicitly that it ships unpinned and name what would catch a figure that moves because the tool changed rather than because the bundle did | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| None listed in the dispatch | n/a | No validation tools were named for this stage; the checks below were performed by direct reading of the cited code and artifacts |

### Summary

The documents are implementable and unusually well grounded: of the six built-code assertions I sampled, all six reproduced exactly, and the two figures the release gate depends on reproduced byte-for-byte. The one concern worth the human's attention at the gate is that NFR2.13 states the bundletool proxy and the Play Console figure as the same quantity when they are a close proxy, and it requires that identity to be written into the gate's own output.

**What I verified independently, and how.**

NFR2's wording was read directly from the prior record's `requirements.md:192` and matches D5's quotation verbatim, including the `arm64-v8a` split and "asserted at the release gate" — so D5's claim that the measurement choice was already specified, and is not open, is correct. `[NFR2-note]` is indeed cited there with no definition, as the brief notes.

The arithmetic in section 1 is correct: 5 × 20 = 100 seats, 100 × 30 = ~3,000 ledger rows. Both inputs are labelled as assumptions where they are not upstream facts — the five-batch figure is traceable to D4's `performance-design.md:181` and `scalability-design.md:60`, where it is itself labelled an assumption, and the ~30 rows per seat is labelled as this document's own estimate.

On built code I sampled six claims. `app/db/models.py:936-937` does state that `amount` is always non-negative with the sign in the kind, and `:927` does state `period` is a plain string rather than a foreign key, with the carry-forward reasoning D5 summarises. `app/authz/lenses.py:31-41` is `TeacherLens` carrying `owner_id`, with the "the lens object handed to a handler is the scoping value" sentence quoted accurately. `tests/contract/test_route_lenses.py` asserts the count at both line 76 and line 104, and the count is eight, matching NFR14.68. `pyproject.toml` configures five strict mypy islands (`app.money`, `app.schemas`, `app.authz`, `app.accounts`, `app.fees`), so NFR17.9's five is right and `team.md`'s three is the stale source. No ZAP reference exists in any workflow; Syft does, at `release-android.yml:213-215`. `app/fees/balances.py:72` is `oldest_unpaid_period` taking a single enrollment, which makes NFR20.32's named hazard a real one rather than a general principle restated.

I also reproduced the two measured figures in section 3, since those are the ones the gate depends on: the AAB is 4,291,524 bytes and carries exactly the four `.so` entries at the sizes quoted. The document's point that the dependency list reads as an app with no native code while the artifact ships four ABIs is correct and worth the space it takes.

The nine Deferred rows each name a real obligation with a stated reason, and none reads as unaddressed work wearing a label. Three are honest statements that review is the only verifier (NFR24.21–NFR24.23, the logging prohibitions), and I agree no cheap mechanism was missed — a log scanner built for one unit would be narrower than the rule. NFR14.70 and NFR14.72 are recorded decisions rather than gaps. NFR6.63 names an unwatched trigger and says so. NFR2.13 is the one Deferred row whose underlying claim I have taken a finding on, above.

NFR14.77's characterisation of the ZAP baseline is accurate. A baseline scan driven from a schema with no token does reach only unauthenticated surface, and what it then verifies is that authenticated routes refuse without a token. Stating it is worth doing: with eight public routes and the rest lens-gated, a green baseline run here really does mean little more than that, and it would otherwise be reported as "the API passed a security scan".

On coverage of the functional design's risks: BR1.6's N+1 trap is covered three times over by NFR20.31, NFR20.32 and NFR20.33, with NFR20.32 naming the specific built function that makes the trap live. BR2.1's double-count is covered by NFR19.50, which cites both the correct total of 2000 and the defect's 2500; I recomputed the worked case from `rules.md` (M1: 1000 + 500 = 1500; M2: 500 + 0 = 500; total 2000, against 2500 when `credit_apply` is counted) and both figures are right. BR2.6's `period`-not-`created_at` grouping, BR1.5/BR2.2/BR2.3/BR3.4's four distinct kinds of nothing, and BR1.7's declined seat all carry a requirement with a named verifier. I found no rule in D5's scope whose risk is unaddressed.

One note on `traceability.json`: it traces the 82 NFR ids rather than the BR rules, which is the correct scope for this stage — BR coverage belongs to the functional design — so its lack of BR entries is not a gap.
