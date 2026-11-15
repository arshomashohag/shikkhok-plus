# Test Results — Unique usernames

Run on 2026-11-15 against commit `4599f51` (branch
`ccr-7315fe9c-esalr9`, merge base `cb20fd1`), from the repository root, with no
application or test file changed by this stage. The person's instruction for
this stage: "don't wait for my approval. Go with your recommendations."

## 1. Environment precondition: the Docker daemon

The brief stated the Docker daemon was running. It was not: `/var/run/docker.sock`
existed, but no `dockerd` process was running and the socket refused
connections. Running the backend suite in that state would have skipped the
whole integration half (locally) and still exited 0. Before any test ran, the
daemon was started (`dockerd`, version 29.9.2), confirmed with `docker info`,
and the backend suite was then run with `CI=true`, under which
`tests/conftest.py` **fails** rather than skips when Docker is missing.

## 2. Commands, exit codes and counts

| # | Command | Exit | Result |
|---|---|---|---|
| B1 | `CI=true make PY=.venv/bin/python lint typecheck test` | **0** | Ruff format: 564 files already formatted. Ruff check: all checks passed. mypy: no issues in 242 source files. pytest: **3101 tests, 0 failed, 0 errors, 0 skipped**, 1514.99 s (JUnit `build/pytest-junit.xml`; `addopts = "-q"` suppresses pytest's own summary line, so the JUnit report is the count of record). Four coverage reports passed their floors (§ 3) |
| B2 | CI step "Every test ran", run as written against `build/pytest-junit.xml` | **0** | 3101 testcases, none skipped |
| B3a | `./gradlew :android:testDebugUnitTest :android:detekt :android:lintDebug :android:spotlessCheck :android:verifyCoverageRatchet --no-daemon` | 0 | **Not evidence.** Every task was `UP-TO-DATE`: Gradle reused an earlier build's outputs and executed no test. Re-run with `--rerun-tasks` |
| B3b | the same with `--rerun-tasks` (backend suite running at the same time; load average about 6 on 4 cores) | **1** | `testDebugUnitTest`: **2099 tests, 1 failed** (`UsernameGateRoutingTest`, § 5). detekt and Spotless ran and passed; `lintDebug`, `jacocoDebugReport` and `verifyCoverageRatchet` did not execute because Gradle stopped at the failed task |
| B3c | `./gradlew :android:testDebugUnitTest --no-daemon --rerun --tests 'com.shikkhokplus.app.navigation.UsernameGateRoutingTest'`, three times, unchanged code | **0, 0, 0** | 7 of 7 passed each time; the failing test took 0.197 s, 0.328 s, 0.218 s |
| B3d | B3 with `--rerun-tasks`, after the backend suite finished | **0** | `testDebugUnitTest`: **2099 tests, 0 failed, 0 skipped** (228 classes). detekt: 0 issues. Android Lint: **0 errors, 113 warnings**. Spotless (Gradle and XML): clean. Ratchet: **90.39% (11513/12737 lines)** against committed floor **90.05%** |
| B4 | `make web` | **0** | `npm ci` (554 packages). `check:generated`: generated files are current. Prettier: clean. ESLint `--max-warnings 0`: clean. `tsc -b --noEmit`: clean. Vitest: **75 files, 1148 tests passed** (none skipped or failed). Main build 252 modules, admin build 109 modules. `check:bundles`: main and admin bundles are separate |
| B5 | `make site` | **0** | 48 tests, 48 passed, 0 skipped |
| B6 | `make infra-functions` | **0** | 29 tests, 29 passed, 0 skipped |
| S1 | `.venv/bin/python -m pip_audit --requirement requirements.txt --desc --strict --progress-spinner off` | **0** | No known vulnerabilities found |
| S2 | `cd web && npm audit --omit=dev --audit-level=low` | **0** | Found 0 vulnerabilities (shipped dependencies) |
| S3 | `cd web && npm audit --audit-level=high` | **0** | 12 vulnerabilities (2 low, 10 moderate) in the whole tree, none high or critical. Annotating only, as in CI |
| I1 | Local reproduction of CI's `image` job (`docker build --target runtime`, Python version check, migrate, `deploy/smoke.py`) | **build 1** | `apt-get update` inside the build container could not resolve `deb.debian.org` (this sandbox's network). Nothing after the build could run (import 125, migrate 125, smoke 1, all because the image did not exist). An environment limit, not a code failure. Making it pass here would mean injecting the proxy CA into the build, so the image would no longer be the one that ships; that was not done |

**Not run locally**: Gitleaks (CI `backend` job) and osv-scanner (CI
`android-unit` job, annotating). Neither binary is installed here, and
downloading the CI-pinned osv-scanner was refused by this environment's
permission policy, so no download was attempted for Gitleaks either. The
"Lockfile is current" CI step was not run: `pyproject.toml` and
`requirements.txt` are unchanged against the merge base, so its result is
`main`'s.

### Per-unit commands (deduplicated)

The backend per-unit commands in U1's and U2's `unit-test-instructions.md` are
strict subsets of B1, so they were not run a second time. The JUnit report
shows each named file present and green:

| Scope | Files | Tests in B1 | Failed or skipped |
|---|---|---|---|
| U1 named files | 8 | 204 (193 at build, plus 11 from review round 1) | 0 |
| U2 named files (including the review-round sentinel and index files) | 11 | 173 | 0 |
| Contract and schema gates both units name | 6 | 70 | 0 |

The Android per-unit commands are subsets of B3; the web per-unit commands are
subsets of B4's Vitest run.

## 3. Coverage

| Scope | Floor | Measured | Source |
|---|---|---|---|
| Backend, rest of `app/` | 80% line, no decrease from 96% | **96%** (15046 statements, 461 missed; 2828 branches, 253 partial) | B1, fourth report |
| `app/money/*` | 100% branch | **100%** (344 statements, 104 branches) | B1 |
| `app/accounts/matching.py`, `app/db/advisory.py` | 100% branch | **100%** (42 statements, 4 branches) | B1 |
| `app/accounts/usernames.py` | 100% branch | **100%** (200 statements, 52 branches) | B1 |
| Android, whole module (JaCoCo line, screens excluded) | ratchet: not more than 0.5 points below `android/coverage-floor.txt` | **90.39%** against **90.05%** | B3d |
| Web | none defined (U4 TSD-3) | not measured, not claimed | — |

No floor was changed. `git diff cb20fd1 -- android/coverage-floor.txt
.coveragerc-backend pyproject.toml` is empty; the only `Makefile` change in this
intent adds two 100% branch reports (matcher and usernames).

## 4. Contract gates (brief item 4)

| Gate | Result |
|---|---|
| Backend schema-diff gate, `tests/contract/test_schema_diff.py` | 8 of 8 passed (B1) |
| Schema parity, `tests/db/test_schema_parity.py` | 6 of 6 passed (B1) |
| Android `ContractConformanceTest` | 3 of 3 passed (B3d) |
| Android `WriteContractTest` | 2 of 2 passed (B3d) |
| Android `MessageKeyCoverageTest` | 3 of 3 passed (B3d) |
| Android `CentreDtoTest` (the nullable `phone` arm the two contract tests cannot see) | 5 of 5 passed (B3d) |
| Web `npm run check:generated` | generated files are current (B4) |

## 5. Failure details

**`com.shikkhokplus.app.navigation.UsernameGateRoutingTest` › "failed read then
foreground re-check showing true replaces the lens-free graph with the gate"**
failed once, in B3b.

```
androidx.compose.ui.test.ComposeTimeoutException: Condition still not satisfied after 5000 ms
    at androidx.compose.ui.test.junit4.AndroidComposeTestRule.waitUntil(AndroidComposeTestRule.android.kt:306)
    at com.shikkhokplus.app.navigation.UsernameGateRoutingTest.settleUntil(UsernameGateRoutingTest.kt:232)
    at com.shikkhokplus.app.navigation.UsernameGateRoutingTest.failed read then foreground re-check showing true replaces the lens-free graph with the gate(UsernameGateRoutingTest.kt:210)
```

- Line 210 is the first wait, `settleUntil { reads.get() >= 2 && present(HOME) }`,
  under `compose.waitUntil(TIMEOUT_MS = 5_000L)`. That budget is **wall-clock**
  time, while the two reads go through the mock HTTP engine on a real
  dispatcher.
- The test took 5.124 s when it failed. In the four later executions it took
  0.197 s, 0.328 s and 0.218 s (three isolated runs) and 0.057 s (the full
  B3d run).
- It failed while the backend suite and Gradle shared 4 cores (load average
  about 6).
- **Diagnosis**: a test whose pass depends on machine load; it fails
  intermittently, not deterministically. Nothing indicates a product defect: the
  same assertion passed in every unloaded run. Under the brief, nothing was
  changed and nothing was skipped.
- **Risk if left**: the CI `android-unit` job runs on a shared runner and can hit
  the same 5 s budget under load, which would fail a pull request
  intermittently.
- **Candidate fixes, with estimated impact** (none applied; this belongs to U3
  Code Generation):
  1. Wait on the virtual clock rather than wall-clock: drive the HTTP mock on the
     test dispatcher, so `settleUntil` cannot run out of real time. Effort: S, one
     test file. Cost: none. Risk: low. Removes the cause.
  2. Raise `TIMEOUT_MS` for this wait (for example to 20 s). Effort: XS. Cost:
     none. Risk: masks rather than removes the cause; a slower runner can still
     hit it.
  3. Leave it and re-run on failure. Effort: none. Risk: an intermittently red
     gate, which this team's practice treats as the start of gate erosion.

## 6. Target Verification Matrix verdict counts

186 targets in `build-and-test-summary.md` § Target Verification Matrix:
**170 Met, 0 Not Met, 16 Unverified**.

The 16 Unverified targets are:

- **Owned by `deployment-execution`** (the only later stage in this plan): ten
  staging readings. U1 NFR1.2 (timing medians), NFR7.2 (migration duration),
  NFR7.4, NFR8.1 (lookup p95); U2 NFR7.2, NFR8.1, NFR8.2, NFR8.6, NFR8.7; and the
  U2 NFR7.3 rollback rule on the release checklist.
- **Owned by CI**: G15 (image job), G16 (Gitleaks), G17 (osv-scanner).
- **No owning stage in this plan** (manual pilot checks): G21 (FR11.2 Bangla
  layout, 34 rows), U3 NFR8.4 and U4 NFR8.4 (device latency, 7 rows).

**Nothing automated discharges any of the staging or manual items.**

## 7. Failure handling outcome

By the stage's failure predicate, this run **has not succeeded**:

- one command (B3b) failed;
- 16 targets are Unverified.

Rung 1 (in-stage fix) does not apply:

- the flaky test needs a test-code change, which is U3's;
- the Unverified items need staging, a device, a person, or CI.

Rung 2 classified the flaky test as a test-code issue with the impact-estimated
candidates in § 5. No loop-back was fired from inside this delegated run: the
orchestrator owns that decision under the brief. So this file carries no Loop-Back Log
entry.

## Sources

- Command output kept in this session's scratchpad logs (backend, android,
  android2, android3, ugr1–3, web, site, infra, image, pip-audit and npm audit
  runs); figures above are copied from them.
- `build/pytest-junit.xml`; `android/build/test-results/testDebugUnitTest/*.xml`;
  `android/build/reports/{lint-results-debug.txt,detekt/detekt.xml}`.
- `.github/workflows/check.yml`; `Makefile`; `tests/conftest.py`.
- Per-unit `code-generation/{code-summary.md,unit-test-instructions.md}` for
  U1–U4.

## Assumptions & Open Questions

- **Assumption**: B3d is the Android result of record. B3b's failure is kept
  above in full, not overwritten, and is surfaced as a finding.
- **Assumption**: starting `dockerd` was in-remit environment setup.
- **Open**: whether to reopen U3 Code Generation for the `UsernameGateRoutingTest`
  timing dependency (§ 5). Recommendation: candidate 1.
- **Open**: G15–G17 are settled by CI on the pull request, not by this run.
