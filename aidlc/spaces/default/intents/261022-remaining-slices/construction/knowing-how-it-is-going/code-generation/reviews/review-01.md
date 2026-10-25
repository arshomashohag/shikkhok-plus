## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-25T06:07:52Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | app/api/analytics.py > `read_overview` and `_current_period` | "This month" is computed from `dt.datetime.now(tz=dt.UTC)`, while the design's own assumption says the month is "the server's calendar month in the project's timezone". Bangladesh is UTC+6, so on the 1st of each month between 00:00 and 06:00 local the overview reports the previous month's earnings as "this month". It is not wrong arithmetic, it is the wrong month, and it self-corrects six hours later, which is what makes it hard to notice and hard to report. This matches every other module in the codebase, and fee generation uses the same boundary, so charges and earnings at least agree with each other. | Either state in the module that the project's timezone IS UTC for every date boundary, so the assumption and the code say the same thing, or convert the boundary to local time in both this module and `app/fees/generation.py` together. Do not change one without the other. | New |
| R-02 | Minor | infra/bootstrap/deploy_role.tf > `TerraformStateList` | `s3:ListBucket` is granted on the whole bucket with no `s3:prefix` condition, so the role can enumerate every key in the state bucket, not only the two objects it reads. The comment says it "is scoped to the bucket itself because that is the only resource form it accepts", which is true of the Resource element but omits that the prefix can be narrowed by condition. `GetObject` is correctly pinned to the two exact keys, so this discloses names and not contents, and the stated cost of the grant is understated by exactly that enumeration. | Add a `Condition` with `s3:prefix` limited to `staging/` and `production/`, or amend the comment to state that enumeration across the whole bucket is part of what is granted. | New |
| R-03 | Minor | .github/workflows/security-scan.yml > step "The schema actually imported" | The floor is `declared / 2` recomputed from the committed schema at scan time, so it rises as routes are added, which is the right shape. The residual gap is that a schema importing just over half its paths passes, and the visited/declared ratio is printed per run only, so a slow decline across releases would not be visible anywhere a person looks. | Optional: record the ratio as a percentage in the job summary so a decline is visible over time, or accept the floor with the limitation the workflow already states. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Independent recomputation of BR2.1's fold | correct total 2000.00, defect total 2500.00, month 1 = 1500.00 under both | Confirms the earnings test asserts the only figure that separates the two folds. A per-month assertion on month 1 would pass against the double-count. |
| `openapi.json` path count | 48 paths; `/v1/me/dues` and `/v1/me/overview` each `get` only | Confirms the ZAP floor resolves to 24, and that both new routes exist with no second verb. |
| `collection_rate` search across `app`, `tests`, `android`, `openapi.json` | 3 hits, all negative assertions or a forward-compat decode fixture | BR4.1 holds: no field ships. The contract test asserts absence over the whole serialized document, not only D5's schemas. |
| Read of `app/analytics/dues.py` and `earnings.py` signatures | neither imports `Session`; `dues_rows(seats, ledger)` and `period_totals(entries)` take data already in hand | The N+1 control is structural as claimed, not a convention. |

### Summary

I verified the four load-bearing tests against the defects they exist to catch and all four hold. The earnings test asserts the total at 2000 and explicitly `!= 2500`; I recomputed both folds independently and confirmed month 1 reads 1500 under each, so the total is the only assertion that could have worked. The dues membership test seeds a seat that is both inactive and owing, paired with an active settled seat, so neither half passes alone. The grouping test carries both required fixtures — a receipt restamped into November against an October period, and a `carry_forward` restamped into September — and the carry case fails against the defect with no late payment at all, so it is not redundant with the first. The scope probes assert every figure's value with teacher B seeded adversarially in each of the four directions the design names, including B's exam sooner, which is the one seeding that makes an unscoped `LIMIT 1` visible; the suite also carries positive twins, so it cannot pass against a boundary that denies everything.

The N+1 control is real: `dues.py` and `earnings.py` import no `Session` and take data already in hand, so a per-row query is unreachable rather than discouraged, and `test_query_count.py` grows batches per teacher at two seats per batch, which is the dimension a seat-growing test cannot see. The ZAP reasoning is correct — `-J` writes alert-derived URIs, so a count from it would fail on a clean run and pass on an empty one, while `zap.core.urls()` reached through the `-d` "Total of N URLs" line is the right source; absent-is-a-failure is implemented as stated, with the log tailed before exit 1. The state-read grant is minimal on `GetObject`, needs no KMS decrypt because the state bucket is SSE-S3 rather than CMK-encrypted, and correctly omits write and lock permissions. BR1.7, BR2.4, BR3.3 and BR4.4 each hold in the built code, with the tiebreaker in the `ORDER BY` rather than in Python and neither route declaring any parameter.

Nothing I found is a correctness or authorization defect. The three findings are Minor, and the only one worth the human's attention is the UTC month boundary, because it is a wrong-month report in a six-hour local window rather than a style point — though it is consistent with the whole codebase and agrees with fee generation, which is why it is Minor rather than Major.
