# Code Summary — D5 `knowing-how-it-is-going`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices
**Built**: 2026-10-25

> **Every figure below was measured by the orchestrator after the build**,
> not copied from a build report. § 6 records the one stale figure a report
> carried and § 5 the one place the build corrected the orchestrator's own
> guidance.

## Sources

- [upstream] `code-generation/code-generation-plan.md`,
  `unit-test-instructions.md`
- [upstream] `functional-design/rules.md` — 22 rules
- [upstream] `nfr-design/`, `infrastructure-design/`
- [measured] 2026-10-25: `make check`, `pytest tests/analytics
  tests/privacy/test_analytics_probes.py`, `terraform fmt -check`, YAML
  parse of all four workflows, and direct inspection of `openapi.json`,
  `dispositions.py`, `migrations/versions/`

---

## 1. The gates, as they actually printed

| Gate | Result |
|---|---|
| `make check` | **All gates passed** |
| Ruff check and format | clean, 265 files |
| mypy | no issues in **112** source files |
| Full backend suite | **1311 passed, 0 failed, 0 skipped** |
| Money module | **100.00%** branch |
| Backend coverage | **92.40%** line, floor 80 (was 92.09 before D5) |
| D5's own tests | **66 passed** |
| Kotlin quality | format, detekt, lint, coverage — all green |
| `dispositions.py` | **25** entries, unchanged |
| `migrations/versions/` | **6** revisions, unchanged — no `0007` |
| `collection_rate` in schema | **0 occurrences** |
| Terraform `fmt -check` | clean |
| All four workflows | parse |

---

## 2. What shipped

**Backend** — `app/analytics/` with `seats.py`, `earnings.py`, `dues.py`,
`upcoming.py`; `app/api/analytics.py` with two routes;
`app/schemas/analytics.py`. **No table, no migration, no column, no
arithmetic added to `app/money/`.**

**Tests** — `tests/analytics/` with eleven modules plus a conftest, and
`tests/privacy/test_analytics_probes.py`.

**Android** — `feature/dues/` and `feature/overview/`, each with a
StateMapper, UiState and `ui/`; `core/network/AnalyticsDto.kt`. **No new
dependency** — no charting library.

**CI** — a download-size step in `release-android.yml`, and a **new
`security-scan.yml`** holding the ZAP job. `check.yml` unchanged.

**Infrastructure** — one policy statement added to
`infra/bootstrap/deploy_role.tf`. No other Terraform change; **USD 0.00/month**.

---

## 3. The size gate, measured and demonstrated failing

**Measured: the arm64-v8a download is 1,854,902 bytes against a 15,728,640
ceiling** — 11.8% of budget, **8.5× headroom**.

**Worth comparing against the AAB's own 4.1 MB**, measured at the
nfr-requirements stage: `get-size` for one ABI is **less than half** the
bundle's bytes. That is exactly why NFR2 names a per-split download rather
than the AAB — asserting the bundle's size against a download ceiling would
have been wrong **and conservative in the wrong direction**, failing builds
that were fine.

**Demonstrated failing rather than trusted.** The comparison is
`[ "$max" -gt "$CEILING_BYTES" ]` with the ceiling in an env var: at
15,728,640 the measured figure passes with exit 0; at 1,000,000 it emits
`::error::Download size 1854902 exceeds 1000000` and exits 1.

**The gate also guards its own parsing** — *"No arm64-v8a row in the get-size
output. The gate measured nothing."* That applies the vacuous-pass
precondition to the gate's parse step rather than only to its inputs.

---

## 4. The two unverified facts, resolved before the build needed them

| Flagged | Answer |
|---|---|
| Can `AWS_DEPLOY_ROLE_ARN` read Terraform state? | **No.** `infra/bootstrap/deploy_role.tf` grants ECR, SSM, KMS-via-SSM, autoscaling and scoped `ssm:SendCommand` — no `s3:`, no `dynamodb:` |
| Does ZAP's report expose a parseable path count? | **Partly** — `-f openapi` and `-J` exist; the JSON's structure is undocumented |

**The first resolved cleanly because the design pre-stated its fix**: *widen
that role by one permission rather than reaching for the infrastructure
role*. Without that clause, "check whether the role can read state" is
satisfiable by switching to `AWS_ROLE_ARN`, which **can** read state and can
also create and destroy — the wrong answer, reached by following the
instruction correctly.

**The grant as built names a cost the design had missed**: Terraform state
contains secrets, including this project's CDN-to-origin shared secret, so a
compromised scan workflow could read it. It is scoped to
`<env>/terraform.tfstate` objects rather than the bucket, carries no
`s3:PutObject` and no lock permission, and the scan passes `-lock=false`
because a read needs no lock.

---

## 5. Where the build corrected the orchestrator

**The ZAP schema-import precondition.** The orchestrator instructed: parse
the path count from ZAP's `-J` JSON report. The build found **the JSON
carries alerts** — so a clean scan produces few or no entries, and a count
from it **would fail on a clean run and pass on an empty one. Backwards.**

It parses `Total of N URLs` from the scan log instead, which
`zap-api-scan.py` computes as `len(zap.core.urls())` — the actual visit log.

**Three properties it added without being told, each closing a hole the
instruction left:**

1. **An absent count is a FAILURE, never a pass.** The line prints only when
   N > 0, and a zero-URL scan makes `zap-api-scan.py` log a WARNING and
   **exit zero** — precisely the vacuous pass the step exists to catch.
2. **A floor, not an equality.** ZAP's URL count includes query-string
   variants; the schema's path count includes templated segments. Asserting
   equality would fail on correct runs.
3. **The limits are written down.** It catches a failed import, a target
   serving nothing, or a root-only crawl. It does **not** catch a partial
   import above the floor, or a correct import whose routes mostly 404.

---

## 6. One stale figure, and why it was stale

The orchestrator measured **46 paths / 52 operations** and passed those to
the build. The workflow comment says **48 / 54**. Verified now: **48 and
54** — the build's figures are right.

**Both were correct when taken.** The orchestrator measured *before* D5
added its two routes; the build measured *after*. **A figure handed to a
subagent carries the authority of the brief, and a measurement taken before
the change it will be compared against is stale the moment that change
lands.**

---

## 7. Fixed during pickup

The build agent **stalled at 600s on its final step** — demonstrating the
size gate failing — with the unit otherwise complete. Rather than
re-dispatch, which risks undoing a finished build, the orchestrator picked
it up:

- **Six lint errors** from its own reformatting: five `D401` docstring-mood
  and one `E501`.
- **The schema-diff gate**, which caught the orchestrator's docstring edit —
  route docstrings publish as the operation `description`, so the gate fires
  on prose as readily as on a contract change. Correct behaviour for a
  published field. Regenerated.
- **The failing demonstration** the stall interrupted (§ 3).

---

## 8. For the human

1. **OQ-2 stays open; `collection_rate` does not ship.** And closing it is
   larger than defining arithmetic: **BR2.1 and AC8.3.4 take opposite sides
   on when a credit counts**, so closing OQ-2 also decides whether two
   figures on one screen may use different month conventions.
2. **Where the ZAP job lives was decided by the build**, which created a
   separate `security-scan.yml`. The alternative was a fourth job in
   `deploy.yml`. Both satisfy every requirement; this is file organisation
   and remains reversible.
3. **The state-read grant has a better long-run shape the build named and did
   not take**: publish `api_url` to SSM under the path this role already
   reads, avoiding state access — and the secret exposure — entirely. It
   costs one `aws_ssm_parameter`. **Worth your judgement.**
4. **Three obligations remain review-only**: no child name, no money amount
   and no dues row in a log line. This is the unit where that risk is highest,
   because a dues row pairs a name with a debt.

---

## Assumptions & Open Questions

- **Nothing here repeats a build report's claim.** Every gate figure was
  re-run; § 6 records the one reported figure that was corrected, and § 5 the
  one instruction the build was right to override.
- **The ZAP job and the size gate have never run in CI.** The size gate's
  arithmetic was demonstrated locally against the measured figure; the ZAP
  job's first real run is its own first evidence, and its `Total of N URLs`
  parse is the assertion most likely to need adjusting against a pinned ZAP
  version.
- **The `/health` probe and the URL-count assertion were not executed**, only
  reviewed — no staging scan has run.
