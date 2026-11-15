# Performance Test Instructions — Unique usernames

Requirement NFR8 (availability lookup within 300 ms at p95 on staging) and the
unit performance requirements (U1 NFR8.x, U2 NFR8.x, U3 and U4 NFR8.x) are the
performance targets for this intent. They split cleanly into two kinds, and
this file keeps them apart, because a correctness test must never be counted
as discharging a performance figure (project Forbidden):

1. **Mechanism checks** that run in the automated suites and prove the
   *shape* that makes the figure achievable (an index is usable, a statement
   count is constant, no network I/O inside a lock, a client debounce and
   timeout behave). They are run by this stage.
2. **Measured figures** that need staging or a real low-end device. **Nothing
   automated discharges any of them.** No load-test harness, Macrobenchmark or
   browser performance harness exists in this repository. They are owned by
   `deployment-execution` (staging readings) or by a manual pilot check (device
   readings), and this stage records them as Unverified.

## 1. Automated mechanism checks (run in this stage)

| Target | What it proves | Check | Command |
|---|---|---|---|
| U1 NFR8.2 | the case-insensitive username lookup is a unique-index read | migration 0038 and `tests/db/test_schema_parity.py` | B1 |
| U1 NFR8.3, NFR8.5, NFR8.8 | availability and claim do a bounded number of statements; no I/O under lock | `tests/accounts/test_usernames.py`, `test_username_claims.py` | B1 |
| U1 NFR8.4 | sign-in by username runs one statement and one (dummy when unknown) scrypt | `tests/auth/test_username_sign_in.py` | B1 |
| U1 NFR8.6 | the hold purge is set-based | `tests/governance/test_purge.py` | B1 |
| U2 NFR8.3, NFR8.10 | every email-matching statement can use its partial index (`EXPLAIN` with `enable_seqscan = off`) | `tests/accounts/test_contact_indexes.py` | B1 |
| U2 NFR8.4 | `match_contact` statement count is equal for 1 and 20 seats | `tests/accounts/test_contact_matching.py` | B1 |
| U2 NFR8.5 | the gateway is never called inside a transaction | `tests/accounts/test_contact_change.py` | B1 |
| U2 NFR8.11 | two-connection contention resolves without deadlock | `tests/accounts/test_contact_concurrency.py` | B1 |
| U3 NFR8.1–8.3, 8.5, 8.6 | 500 ms debounce, latest-wins, 3 s bound, stop after 429, cancellation rethrown, no periodic re-read | `UsernameAvailabilityCheckerTest`, `CallCancellationTest`, `UsernameGateRoutingTest` | B3 |
| U4 NFR8.1–8.3, 8.5–8.8 | the same client behaviours on the web, under fake timers | `useUsernameAvailability.test.ts`, `availability.test.ts`, `ChooseUsernameGate.test.tsx`, `api/client.test.ts` | B4 |

These prove the mechanism, **not the latency**. The client tests run on
virtual or fake time.

## 2. Measured figures (manual; nothing automated discharges them)

| Target | Figure | Where | How (from the unit NFR documents) | Owner |
|---|---|---|---|---|
| NFR8 / U1 NFR8.1 | both availability lookups ≤ 300 ms p95 | staging, through CloudFront | small `httpx` script: 25 public lookups in one clock hour, 25 authenticated in the next (stays under `un_lk_ip_hour` 30); mix of available, unavailable, invalid, reserved; p95 of each set recorded in the PR | `deployment-execution` |
| U1 NFR1.2 | unknown-username, password-less and wrong-password sign-in medians within 10% of each other | staging | 20 sign-ins per case over different usernames so no ceiling refuses | `deployment-execution` |
| U2 NFR8.1 | `GET /v1/accounts/already-added` ≤ 300 ms p95, email and phone forms separately | staging | 25 samples per form, in different clock hours; any 429 voids that form's set | `deployment-execution` |
| U2 NFR8.2 | U2 writes ≤ 500 ms p95 (100 requests each at ≤ 2 rps); contact replace-verify and remove: max of 8 samples ≤ 500 ms | staging | U2 performance-requirements run plan, hours 3 and 4 | `deployment-execution` |
| U2 NFR8.6 | `match_contact` adds ≤ 50 ms to verify | staging | sum of the NFR8.7 statement timings | `deployment-execution` |
| U2 NFR8.7 | each matcher and lookup statement ≤ 25 ms (`EXPLAIN (ANALYZE, BUFFERS)`) | staging, or local PostgreSQL 16 seeded to design-point volume | plans and timings pasted into the PR | `deployment-execution` |
| U1 NFR7.2, U2 NFR7.2 | each migration ≤ 10 s | staging deploy log | read the migrate step's duration | `deployment-execution` |
| U3 NFR8.4 | availability hint answers within 1 s of the debounce pause | pilot low-end Android device, mobile network | five pauses per screen on 4 screens; table in `docs/delivery/bangla-layout-check.md` | manual pilot check; **no stage in this plan owns it** |
| U4 NFR8.4 | the same on the web | browser on the pilot low-end phone | five pauses per screen on 3 screens; same file | manual pilot check; **no stage in this plan owns it** |

Constraints on the staging run, from the U2 run plan: no ceiling override (the
ceilings are module constants in `app/auth/ceilings.py`), one source host on one
/64, four clock hours, no other OTP, sign-up or lookup traffic during the run.

## 3. Regression detection

None automated for latency. Mechanism regressions (a lost index, a per-row
loop, I/O under a lock, a broken debounce) fail the suites in § 1 on every
push.

## Sources

- `inception/requirements-analysis/requirements.md` NFR8, NFR7.
- `construction/usernames-backend/nfr-requirements/performance-requirements.md`,
  `security-requirements.md` (NFR1.2), `reliability-requirements.md` (NFR7.2).
- `construction/contacts-and-invites-backend/nfr-requirements/performance-requirements.md`
  (NFR8.1–8.7 and § The manual run), `reliability-requirements.md`.
- `construction/android-identity/nfr-requirements/performance-requirements.md`,
  `construction/web-identity/nfr-requirements/performance-requirements.md`.
- `docs/delivery/bangla-layout-check.md` (U3 and U4 timing tables, all *not yet
  checked*).
- `aidlc-state.md` (only `deployment-execution` remains; `performance-validation`
  is SKIP).

## Assumptions & Open Questions

- **Assumption**: `deployment-execution` owns the staging readings, because
  every unit's `traceability.json` names "the manual staging run at deployment
  execution" as their verifier. `performance-validation` is skipped in this
  plan.
- **Open**: the two NFR8.4 device-latency checks have no owning stage in this
  plan. They are manual pilot checks; the person decides when they are done.
  Until then they are Unverified.
