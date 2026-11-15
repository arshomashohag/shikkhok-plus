# Cross-Unit Traceability — Unique usernames

Step 10 gate. Enumerates every `FR` and `NFR` in
`inception/requirements-analysis/requirements.md` (48 FRs, 9 NFRs). The
`user-stories` stage was skipped in this plan, so there are no three-segment
`AC` IDs to enumerate. Inputs:

- `construction/<unit>/code-generation/traceability.json` for U1–U4. There is
  no stage-level code-generation `traceability.json`.
- For the NFRs, each unit's `nfr-requirements/traceability.json`.

Every `OK` target path in the four code-generation files was checked on disk:
**381 paths, all present.**

"Verified in this run" names the tests that exercise the requirement, and
whether the command running them passed in this run:

- **B1** — backend, 3101 passed, 0 skipped;
- **B3d** — Android, 2099 passed, 0 skipped;
- **B4** — web, 1148 passed.

The backend tests are reached through the chain FR → business rule (BR) in
`functional-design/traceability.json` → the plan step that names the test file.

## Verdict

**FAIL by the strict gate.** Ten IDs have no `OK` entry in any code-generation
`traceability.json`:

- **FR11.2** (Bangla layout) is `Deferred` in U3 and U4. Its verifier is the
  manual table in `docs/delivery/bangla-layout-check.md`: 34 rows, all *not yet
  checked*. **Nothing automated discharges it.**
- **NFR1–NFR9** are recorded only at the `nfr-requirements` level, where each is
  `OK` and decomposed into detailed unit targets (NFRx.y). The code-generation
  files trace those detailed targets, not the bare inception IDs. This is a
  record-keeping gap, not missing coverage. Their measured parts (NFR7
  duration, NFR8 latency, and the NFR1 timing medians) are Unverified and owned
  by `deployment-execution`.

**Substantively:**

- 47 of 48 FRs are `OK` in at least one unit, with their tests passing in this
  run.
- Every NFR's automated targets passed.
- The uncovered items are the manual and staging obligations listed under
  Deferred and manual.

## Functional requirements

| ID | Units (status) | Owning target | Verified in this run by | Result |
|---|---|---|---|---|
| FR1.1 | U1 OK | `app/accounts/usernames.py` | `tests/accounts/test_usernames.py` (BR1.2, 1.3, 1.9) — B1 | OK |
| FR1.2 | U1 OK | `app/accounts/usernames.py` | `test_usernames.py` (BR1.4, 1.5) — B1 | OK |
| FR1.3 | U1 OK | `migrations/versions/0038_usernames.py` | `test_usernames.py` (BR1.7 case-insensitive key), `test_username_claims.py`, `test_username_concurrency.py` (BR10.2) — B1 | OK |
| FR1.4 | U1 OK | `tests/accounts/test_usernames.py` | `test_usernames.py` (BR1.1 trim) — B1 | OK |
| FR1.5 | U1 OK | `app/accounts/usernames.py` | `test_usernames.py` (BR1.8 reserved list) — B1 | OK |
| FR1.6 | U1 OK, U3 OK | `tests/accounts/test_usernames.py`; `core/ui/UsernameField.kt`, strings | `test_usernames.py`, `test_message_keys.py` — B1; `UsernameFieldTest`, `MessageKeyCoverageTest` — B3d; `i18n.test.ts`, `UsernameField.test.tsx` — B4 | OK |
| FR2.1 | U1, U3, U4 OK | `app/auth/pending.py`; `SignupViewModel.kt`; `SignUp.tsx` | `test_verify_first_signup.py`, `test_signup.py` — B1; `SignupViewModelTest`, `SignupStateMapperTest`, `HttpSignupRepositoryTest` — B3d; `SignUp.test.tsx` — B4 | OK |
| FR2.2 | U1, U3, U4 OK | `app/accounts/service.py`; `ReplaceUsernameStep.kt`; `ReplaceUsernameStep.tsx` | `test_verify_first_signup.py` (BR2.4–2.6), `test_username_concurrency.py` — B1; `ReplaceUsernameStepTest`, `AuthViewModelTest` — B3d; `PasswordCode.test.tsx`, `SignUp.test.tsx` — B4 | OK |
| FR2.3 | U1 OK | `tests/accounts/test_verify_first_signup.py` | same file (BR2.3, a draft reserves nothing) — B1 | OK |
| FR2.4 | U1 OK | `tests/accounts/test_verify_first_signup.py` | same file (BR2.2, BR2.9: identical response with or without an account) — B1 | OK |
| FR2.5 | U2 OK | `app/accounts/service.py` | `test_seat_linking.py`, `test_contact_matching.py` (BR3.4 pending, never accepted) — B1 | OK |
| FR3.1 | U1, U3, U4 OK | `app/accounts/usernames.py`; `UsernameAvailability.kt`; `availability.ts` | `test_username_claims.py` (BR3.1, BR3.2) — B1; `UsernameAvailabilityCheckerTest`, `AvailabilityMapperTest` — B3d; `availability.test.ts`, `useUsernameAvailability.test.ts` — B4 | OK |
| FR3.2 | U1, U3, U4 OK | `app/auth/ceilings.py`; checker files | `test_username_claims.py`, `test_verify_first_signup.py` (Family A, C ceilings) — B1; `UsernameAvailabilityCheckerTest` (stop after 429) — B3d; `useUsernameAvailability.test.ts` — B4 | OK |
| FR3.3 | U1 OK | `app/contract/routes.py` | `tests/contract/test_route_lenses.py` (`PUBLIC_ROUTES` and its count) — B1 | OK |
| FR4.1 | U1, U3, U4 OK | `app/accounts/identifier.py`; `LoginField.kt`; `SignIn.tsx` | `tests/auth/test_username_sign_in.py` (BR4.1, 4.2 classification) — B1; `HttpAuthLoginTest`, `AuthViewModelTest` — B3d; `SignIn.test.tsx` — B4 | OK |
| FR4.2 | U1, U3, U4 OK | `tests/auth/test_username_sign_in.py` | same (BR4.3 phone and email unchanged) — B1; `AuthScreenTest` — B3d; `SignIn.test.tsx` — B4 | OK |
| FR4.3 | U1 OK | `app/accounts/passwords.py` | `test_username_sign_in.py` (BR4.4: identical full responses) — B1 | OK |
| FR4.4 | U1 OK | `app/auth/ceilings.py` | `test_username_sign_in.py` (Family D, BR4.5–4.7; 25 /64s in 3 /48s counts 75 failures) — B1 | OK |
| FR4.5 | U1 OK | `tests/auth/test_username_sign_in.py` | same (BR4.8 second step unchanged) — B1 | OK |
| FR4.6 | U1 OK | `app/schemas/auth.py` | `test_username_sign_in.py`, `test_schema_diff.py` — B1 | OK |
| FR5.1 | U1, U3, U4 OK | `app/api/me.py`; `ProfileDto.kt`; `session.tsx` | `test_username_claims.py` (BR5.1 flag) — B1; `ProfileDtoTest`, `SessionStateMapperTest` — B3d; `session.test.ts` — B4 | OK |
| FR5.2 | U3, U4 OK | `SessionUiState.kt`, `RootRoute.kt`; `App.tsx`, `ChooseUsernameGate.tsx` | `UsernameGateRoutingTest`, `ChooseUsernameGateTest`, `SessionViewModelTest` — B3d (see the flaky-test note below); `usernameGate.routing.test.tsx`, `ChooseUsernameGate.test.tsx` — B4 | OK |
| FR5.3 | U1, U3, U4 OK | `tests/accounts/test_username_claims.py`; `SessionViewModel.kt`; `session.tsx` | `test_username_claims.py` (BR5.2 server does not refuse) — B1; `SessionViewModelTest` — B3d; `usernameGate.routing.test.tsx` — B4 | OK |
| FR5.4 | U1, U3, U4 OK | `app/accounts/usernames.py` | `test_username_claims.py` (BR5.3 no password, no limit) — B1; `ChooseUsernameViewModelTest` — B3d; `ChooseUsernameGate.test.tsx` — B4 | OK |
| FR6.1 | U2, U3, U4 OK | `app/students/service.py` | `tests/students/test_students.py` (BR1.1, 1.5, 1.6) — B1; `TeacherStudentDtoTest`, `HttpTeacherStudentsRepositoryTest` — B3d; `people.test.tsx` — B4 | OK |
| FR6.2 | U2, U3, U4 OK | `app/students/service.py` | `test_students.py` (BR1.2, 1.3 per-teacher uniqueness, `student.email.taken`) — B1; `StudentsStateMapperTest` — B3d; `people.test.tsx` — B4 | OK |
| FR6.3 | U2, U3, U4 OK | `app/schemas/students.py` | `test_privacy_schema.py` (BR1.4 teacher-written fields only on teacher responses) — B1; `StudentsStateMapperTest` — B3d; `students.test.tsx`, `mappers.test.ts` — B4 | OK |
| FR6.4 | U2, U3, U4 OK | `app/centres/service.py`; `CentreDto.kt`; `Members.tsx` | `tests/centres/test_centres.py` — B1; `CentreDtoTest`, `HttpCentresRepositoryTest`, `CentresViewModelsTest` — B3d; `Members.test.ts`, `centre.screens.test.tsx` — B4 | OK |
| FR6.5 | U2 OK | `app/accounts/matching.py` | `test_contact_matching.py`, `test_seat_linking.py`, `test_contact_change.py` (match on add and verify) — B1 | OK |
| FR6.6 | U2 OK | `tests/accounts/test_contact_matching.py` | same (BR3.4 pending, BR3.5 never relinked, BR3.6 blocked seats) — B1 | OK |
| FR6.7 | U2, U3, U4 OK | `app/accounts/service.py` | `tests/accounts/test_lookup.py` (BR4.2, 4.3) — B1; `HttpSignupRepositoryTest` — B3d; `SignUp.test.tsx` — B4 | OK |
| FR7.1 | U1, U3*, U4 OK | `app/accounts/passwords.py` | `test_username_claims.py` (BR6.1 password required) — B1; `UsernameViewModelTest` — B3d; `username.test.tsx` — B4 | OK |
| FR7.2 | U1, U3* OK | `tests/accounts/test_username_claims.py` | same (BR6.2: refused on day 20 with `next_change_at`, allowed on day 30) — B1; `UsernameStateMapperTest` — B3d; `username.test.tsx` — B4 | OK |
| FR7.3 | U1 OK | `app/accounts/usernames.py` | `test_usernames.py` (BR7.2, 7.3 hold), `test_username_claims.py` (BR6.4–6.6 reclaim) — B1 | OK |
| FR7.4 | U1 OK | `app/auth/hashing.py` | `test_usernames.py` (BR7.1 keyed HMAC known vector), `test_deletion_paths.py` (BR7.5) — B1 | OK |
| FR7.5 | U1, U3*, U4 OK | `tests/accounts/test_username_claims.py` | same (BR6.8 no sign-out) — B1; `UsernameViewModelTest` — B3d; `username.test.tsx` — B4 | OK |
| FR8.1 | U2, U3*, U4 OK | `app/accounts/contact.py` | `test_contact_change.py` — B1; `ContactsViewModelTest` — B3d; `contacts.test.tsx` — B4 | OK |
| FR8.2 | U2, U3, U4 OK | `app/api/credentials.py` | `test_contact_change.py` (BR5.2, 5.3), `test_contact_concurrency.py` — B1; `ReplaceContactViewModelTest` — B3d; `contacts.test.tsx` — B4 | OK |
| FR8.3 | U2 OK | `tests/accounts/test_contact_change.py` | same (BR5.7 removal unlinks nothing) — B1; `contacts.test.tsx` — B4 | OK |
| FR8.4 | U2, U3*, U4 OK | `app/accounts/contact.py` | `test_contact_change.py` (BR5.5 last contact refused), `test_schema_parity.py` (stale prose corrected with the model) — B1; `RemoveContactViewModelTest` — B3d; `contacts.test.tsx` — B4 | OK |
| FR9.1 | U1 OK | `tests/contract/test_privacy_schema.py` | same (BR8.1, every-route walk with planted-leak fixtures) — B1 | OK |
| FR9.2 | U1 OK | `tests/contract/test_admin_contract.py` | same plus `test_privacy_schema.py` (BR8.2, 8.3) — B1 | OK |
| FR9.3 | U1 OK | `tests/accounts/test_username_sentinels.py` | same (BR8.4), `tests/audit` audit-event tests — B1; `NoLoggingTest` — B3d; `noIdentifierLeaks.test.tsx` — B4 | OK |
| FR10.1 | U1, U3 OK | `tests/accounts/test_verify_first_signup.py` | same, `test_deletion_paths.py` (BR9.1) — B1; `AuthScreenTest` — B3d; `PasswordCode.test.tsx` — B4 | OK |
| FR10.2 | U1 OK | `tests/governance/test_deletion_paths.py` | same, `tests/governance/test_purge.py` (BR7.5–7.7), privacy-policy manifest — B1 | OK |
| FR11.1 | U3, U4 OK | `res/values*/strings.xml`; `i18n/generated/*`, `i18n/web/*.{en,bn}.json` | `MessageKeyCoverageTest` and the screen tests — B3d; `i18n.test.ts`, `check:generated` — B4 | OK |
| FR11.2 | U3 Deferred, U4 Deferred | `docs/delivery/bangla-layout-check.md` | **Manual only; nothing automated discharges it.** U3 14 rows, U4 20 rows, all *not yet checked* | **Uncovered (Deferred)** |
| FR11.3 | U3, U4 OK | `feature/auth/MessageKeys.kt`; `identifier.ts` | `EmailShapeTest`, `UsernameFieldTest`, `SignupStateMapperTest` — B3d; `identifier.test.ts` — B4 | OK |

\* **U3 label defect.** U3's code-generation `traceability.json` maps FR7.1,
FR7.2 and FR7.5 to contact files (`Contacts.kt`, `ReplaceContact.kt`,
`RemoveContact.kt`), and FR8.1 and FR8.4 to username files (`Username.kt`). The
FR7 and FR8 labels are swapped. The files exist and are tested, and U1 and U4
trace the same IDs correctly, so no FR loses coverage. The record should be
corrected. The "Verified" column above names the correct U3 tests.

**Flaky-test note (FR5.2).** `UsernameGateRoutingTest` failed once under load
in this stage and passed in four later executions. See `test-results.md` § 5.

## Non-functional requirements

| ID | Decomposed into (nfr-requirements traceability, all `OK`) | Automated verification in this run | Not automated | Result |
|---|---|---|---|---|
| NFR1 Anti-enumeration | U1 NFR1.1–1.7; U2 NFR1.1–1.4; U3 and U4 NFR1.1–1.4 | `test_username_sign_in.py` (full-response equality), `test_verify_first_signup.py`, `test_username_claims.py`, `test_lookup.py` — B1; `AvailabilityMapperTest` — B3d; `availability.test.ts`, `SignIn.test.tsx` — B4 | **U1 NFR1.2 timing medians**: manual staging run, `deployment-execution` | Automated parts OK; timing Unverified |
| NFR2 Rate limits | U1 NFR2.1–2.12; U2 NFR2.1–2.6; U3 NFR2.1–2.3; U4 NFR2.1–2.3 | each ceiling driven to its limit and one past: `test_username_sign_in.py`, `test_username_claims.py`, `test_verify_first_signup.py`, `test_ceilings.py`, `test_contact_change.py` — B1; client stop-after-429 — B3d, B4 | — | OK |
| NFR3 Privacy boundary | U1 NFR3.1–3.10; U2 NFR3.1–3.9; U3 NFR3.1–3.14; U4 NFR3.1–3.17 | `test_privacy_schema.py`, `test_admin_contract.py`, `test_rls_meta.py` (6/6, restricted role, RLS forced), sentinel tests — B1; source scans — B3d, B4 | — | OK |
| NFR4 Test-first where the predicate holds | U1 NFR4.1–4.8; U2 NFR4.1–4.10; U3 and U4 NFR4.1 | the tests exist and pass — B1. Test-first ordering is process evidence: the red lines recorded in each unit's `code-summary.md`, reviewed READY | the ordering itself cannot be re-observed by a later run | OK (process evidence) |
| NFR5 Coverage | U1 NFR5.1–5.2; U2 NFR5.1–5.3; U3 NFR5.1, 5.4; U4 NFR5.1–5.2 | backend 96% line; money, matcher and usernames 100% branch; `test_coverage_scope.py`; Kotlin 90.39% against an unchanged 90.05% floor; `namedTests.test.ts` | — | OK |
| NFR6 Compatibility | U1 NFR6.1–6.3; U2 NFR6.1–6.2; U3 and U4 NFR6.1–6.3 | `test_username_sign_in.py` (old `phone`/`email` request shape), `test_seat_linking.py`, `test_schema_diff.py` — B1; unknown-field tolerance in `CentreDtoTest`, DTO tests — B3d; mapper fixtures with an extra field — B4 | — | OK (narrowed to current clients by the 2026-11-14 direction in `contract-summary.md`) |
| NFR7 Migration safety | U1 NFR7.1–7.4; U2 NFR7.1–7.3 | `test_migration_runs.py`, `test_migration_from_head.py`, `test_migration_head_pin.py`, `test_schema_parity.py` (nullable columns, forward-only chain) — B1 | **NFR7.2 migration duration (≤ 10 s on staging)**, U1 NFR7.4 logged step, U2 NFR7.3 rollback rule: manual, `deployment-execution`. The CI `image` job's migrate step could not be reproduced locally | Automated parts OK; staging parts Unverified |
| NFR8 Responsiveness | U1 NFR8.1–8.8; U2 NFR8.1–8.11; U3 and U4 NFR8.1–8.6 | mechanism checks: index usability (`test_contact_indexes.py`), constant statement count, no I/O under lock, client debounce and 3 s bound — B1, B3d, B4 | **U1 NFR8.1 lookup p95 ≤ 300 ms on staging**, U2 NFR8.1/8.2/8.6/8.7: manual, `deployment-execution`. **NFR8.4 device latency** (U3 4 screens, U4 3 screens): manual pilot check, no owning stage | Mechanism OK; figures Unverified |
| NFR9 Committed contract | U1, U2 NFR9.1–9.2; U3, U4 NFR9.1 | `test_schema_diff.py` 8/8, `test_message_keys.py` — B1; `ContractConformanceTest`, `WriteContractTest` — B3d; `check:generated` — B4 | under-declared status codes on four operations are invisible to the gate (carried follow-up) | OK |

## Deferred and manual (not automated)

Each item below names its verifier. **Nothing automated discharges any of them.**

| Item | Verifier | Owner | State |
|---|---|---|---|
| FR11.2 Bangla layout (U3 14 rows, U4 20 rows) | per-screen manual check at the longest Bangla string, `docs/delivery/bangla-layout-check.md` | manual pilot check; no stage in this plan | not yet checked |
| NFR8.4 hint latency on a low-end device (U3 4 screens, U4 3 screens) | timed manual check, same file | manual pilot check; no stage in this plan | not yet checked |
| NFR1.2 (U1) sign-in timing medians within 10% | manual staging run, 20 sign-ins per case | `deployment-execution` | not run |
| NFR7.2 (U1, U2) migration duration ≤ 10 s | staging deploy log | `deployment-execution` | not run |
| NFR8 / U1 NFR8.1 lookup p95 ≤ 300 ms; U2 NFR8.1, 8.2, 8.6, 8.7 | manual staging run (`httpx` script, `EXPLAIN ANALYZE`) | `deployment-execution` | not run |

## Sources

- `inception/requirements-analysis/requirements.md` (FR1.1–FR11.3, NFR1–NFR9).
- `construction/{usernames-backend,contacts-and-invites-backend,android-identity,web-identity}/code-generation/traceability.json`.
- `construction/*/nfr-requirements/traceability.json`;
  `construction/{usernames-backend,contacts-and-invites-backend}/functional-design/traceability.json`
  (FR → BR); each unit's `code-generation-plan.md` steps (BR → test file).
- `test-results.md` (B1, B3d, B4 results and the flaky-test detail).
- `docs/delivery/bangla-layout-check.md`.

## Assumptions & Open Questions

- **Assumption**: NFR1–NFR9 are judged through their unit decomposition,
  because that is where the workflow recorded them. The strict gate still
  reports them as having no code-generation `OK` entry, and that is surfaced
  rather than smoothed over.
- **Assumption**: the U3 FR7 and FR8 swap is a labelling error, not a coverage
  gap. The files and tests named in the table exist and passed.
- **Open**: whether to correct U3's `traceability.json` labels and add bare
  NFR1–NFR9 entries to the code-generation records. That is a record fix for
  the units, not this stage.
- **Open**: FR11.2 and NFR8.4 have no owning stage in this plan; the person
  decides when the manual checks are done.
