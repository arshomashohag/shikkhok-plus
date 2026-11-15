# Integration Test Instructions — Unique usernames

Test strategy: **Standard** (`aidlc-state.md`). Standard asks for key boundary
tests and cross-unit interaction. This file names each cross-unit boundary in
`contract-summary.md` (C1, C2, C3), the automated check that guards it, and the
command that runs it. Where a boundary has no automated check, that is stated
plainly.

## 1. Framework and environment

| Surface | Framework | Real dependency | Precondition that must hold |
|---|---|---|---|
| Backend (U1, U2) | pytest + testcontainers | PostgreSQL 16 (`postgres:16-alpine`) migrated to head, suite connected as `shikkhok_app` | Docker reachable; `tests/conftest.py`'s meta-check asserts `current_user` is not a superuser and row-level security is in force before the privacy suite runs; the JUnit report lists no skipped test |
| Android (U3) | JUnit 4 + Robolectric + Ktor `MockEngine` | none (contract read from the committed `openapi.json`) | the tasks actually execute (not `UP-TO-DATE` from an earlier build) |
| Web (U4) | Vitest + jsdom | none (types generated from the committed `openapi.json`) | `check:generated` passes, so the types match the committed contract |

No test drives a client against a running server. The backend is exercised
through FastAPI's test client against a real database; each client is checked
against the committed `openapi.json`, which the backend's schema-diff gate keeps
equal to what the server generates. The chain is therefore server → committed
contract → client, with a gate at each link, rather than one end-to-end test.

## 2. Boundaries and their checks

### C3 — U1 and U2 inside the backend (shared schema, one in-process call)

| What must hold | Check | Command |
|---|---|---|
| One Alembic chain; both migrations (0037 U2, 0038 U1) apply to a fresh database | `tests/db/test_migration_runs.py`, `tests/db/test_migration_from_head.py`, head pin `tests/db/test_migration_head_pin.py` | B1 |
| `app/db/models.py` describes exactly the migrated schema | `tests/db/test_schema_parity.py` | B1 |
| Sign-up (U1's `create_account_rows`) calls U2's `match_contact`; a linked seat is `pending`, never accepted (FR2.5, FR6.6) | `tests/accounts/test_seat_linking.py`, `tests/accounts/test_verify_first_signup.py`, `tests/accounts/test_contact_matching.py` | B1 |
| The username key and the contact keys are taken in one advisory-lock call in a fixed order (BR10.1, LO-1) | `tests/accounts/test_username_concurrency.py`, `tests/accounts/test_contact_concurrency.py` (two real connections, explicit transaction control) | B1 |
| Deletion places a digest-only username hold inside U2's deletion lock order | `tests/governance/test_deletion_paths.py`, `tests/governance/test_purge.py` | B1 |

### C1 and C2 — backend to the committed contract

| What must hold | Check | Command |
|---|---|---|
| Committed `openapi.json` equals the generated schema | `tests/contract/test_schema_diff.py` | B1, or `make contract` alone |
| No teacher-lens, guardian-lens, admin or other non-owner response carries `username` (FR9.1, FR9.2, NFR3) | `tests/contract/test_privacy_schema.py`, `tests/contract/test_admin_contract.py` | B1 |
| Every route resolves a lens or is in `PUBLIC_ROUTES`, and the count assertion matches (FR3.3) | `tests/contract/test_route_lenses.py` | B1 |
| Every `message_key` the server can emit is in `message-keys.json` | `tests/contract/test_message_keys.py` | B1 |

### C1 and C2 — committed contract to the Android client (U3)

| What must hold | Check | Command |
|---|---|---|
| Every GET the client makes decodes an example built from `openapi.json` | `ContractConformanceTest` | B3 |
| Every write's method, path and body matches `openapi.json` | `WriteContractTest` | B3 |
| Nullable server fields decode their null arm (the gap the two tests above do not cover; `MemberResponse.phone`) | `CentreDtoTest`, `ProfileDtoTest`, `RosterDtoTest`, `UsernameDtoTest` | B3 |
| Every server `message_key` has Bangla and English strings | `MessageKeyCoverageTest` | B3 |

Single-class run:

```bash
./gradlew :android:testDebugUnitTest --no-daemon --rerun \
  --tests 'com.shikkhokplus.app.core.network.ContractConformanceTest' \
  --tests 'com.shikkhokplus.app.core.network.WriteContractTest' \
  --tests 'com.shikkhokplus.app.feature.auth.MessageKeyCoverageTest'
```

### C1 and C2 — committed contract to the web client (U4)

| What must hold | Check | Command |
|---|---|---|
| `web/src/api/schema.d.ts`, `message-keys.json` copy and generated strings equal what `openapi.json` and the Android bundles produce | `npm run check:generated` | B4 |
| Every request and response the client uses type-checks against the generated schema | `tsc -b --noEmit` (`npm run typecheck`) | B4 |
| Every server `message_key` maps to a web string | `src/i18n/i18n.test.ts` | B4 |

`tsc` is a compile-time check: it proves the client's code agrees with the
generated types, not that a live response matches them at runtime.

## 3. External dependencies

- **SMS and email gateways**: the null adapter plus the `outbound` capture
  fixture; tests assert on recorded sends (for example the removed-contact
  notice, sent once after commit).
- **Clock**: injected (`now=`); the 30-day rename window and the hold expiry
  are stepped, never slept.
- **Database**: never mocked. Concurrency tests open two real connections.

## 4. What no automated integration test covers

- **A client against a deployed server.** Nothing automated drives Android or
  web against a running backend in this intent. The CI `image` job builds the
  shipped image, migrates a throwaway PostgreSQL 16 and runs `deploy/smoke.py`
  against it; the post-deploy smoke at `deployment-execution` repeats that on
  staging. Neither exercises a username flow end to end.
- **`MainActivity` root wiring** (U3 review residual): `UsernameGateRoutingTest`
  drives the shared `rootRouteFor` decision, but the wiring inside
  `MainActivity` is covered by review only.
- **`openapi.json` under-declares status codes** for `/v1/me/contact`,
  `/v1/me/contact/remove`, `/v1/auth/verify` and `/v1/auth/password`
  (carried by U3 and U4 as a follow-up for U1/U2). The contract gates compare
  what is declared, so an undeclared status is invisible to them.

## 5. Coverage expectations (Standard)

Key boundaries only: every row in § 2 has at least one named automated check,
and § 4 lists the boundaries that have none. No integration-specific coverage
percentage exists; the backend coverage floors in `build-instructions.md` § 4
include these tests' contribution.

## Sources

- `inception/contract-design/contract-summary.md` (C1, C2, C3).
- Per-unit `code-generation/code-summary.md` and `unit-test-instructions.md`.
- `tests/conftest.py`, `tests/contract/`, `tests/db/`, `tests/accounts/`,
  `tests/governance/`; `android/src/test/.../core/network/`; `web/package.json`
  scripts.
- `.github/workflows/check.yml` (`backend`, `image`, `android-unit`, `web`).

## Assumptions & Open Questions

- **Assumption**: the server → committed contract → client chain, gated at each
  link, is the Standard-strategy integration check for C1 and C2; no live
  client-to-server test is added at this stage (this stage does not change
  application or test code).
- **Open**: the under-declared status codes in § 4 remain a U1/U2 follow-up.
