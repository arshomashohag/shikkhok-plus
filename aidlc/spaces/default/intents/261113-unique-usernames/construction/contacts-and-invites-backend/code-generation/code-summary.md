# Code Summary — contacts-and-invites-backend (U2)

Built against the approved plan (`code-generation-plan.md`, Steps 1–24; Step 25
is this file, `source-manifest.json` and `traceability.json`).

## Files

- **Migration and models**: `migrations/versions/0034_contacts_and_email_invites.py` (new), `app/db/models.py`.
- **New modules**: `app/accounts/matching.py` (`match_contact`, `lock_contact`, `lock_account`), `app/db/advisory.py` (advisory-key naming and ordering, LO-1), `app/db/retry.py` (`run_with_retry`).
- **Services**: `app/accounts/identifier.py` (`resolve_link_target`, `optional_email`), `app/accounts/service.py` (matcher wired into `create_account_rows` with keys taken before the insert; email lookup; `link_phone_seats` removed), `app/accounts/contact.py` (add, replace request and verify, remove), `app/students/service.py` (seat linking, relink blocking, save-path locking, email recording and identification), `app/batches/service.py` (guardian state, roster emails), `app/centres/memberships.py`, `app/centres/service.py`, `app/auth/otp.py` (`contact_replace` purpose bound to its requester; locked re-check), `app/auth/ceilings.py` (`contact_chg_day`, non-committing consume, lookup refusal as 429), `app/auth/delivery.py` and `app/gateway/template.py` (removed-contact notice), `app/governance/deletion.py` (keys, locked re-read, relink markers, replacement-code purge), `app/governance/dispositions.py`, `app/audit/log.py` (`CONTACT_REPLACED`, `CONTACT_REMOVED`), `app/errors/_classes.py` and `handler.py` (`ConflictError.status` 409 or 429).
- **API, schemas, logging**: `app/api/credentials.py` (new `POST /v1/me/contact/remove`), `accounts.py`, `students.py`, `batches.py`, `centres.py`, `deletion.py`; `app/schemas/identifier.py`, `students.py`, `centres.py`, `batches.py`; `app/contract/routes.py`; `app/logging_setup.py`, `app/request_scope.py`.
- **Contract and generated**: `openapi.json` (regenerated), `message-keys.json` (6 new keys), `docs/legal/PRIVACY.md` (manifest digest), `Makefile` (100% branch gate on the matcher and advisory modules).
- **Tests**: new `tests/accounts/test_contact_matching.py`, `test_contact_change.py`, `test_contact_concurrency.py`, `contact_support.py`; extended lookup, students, roster, centres, deletion, privacy, admin-contract, route-lens, logging and conftest tests; migration-head pins moved to 0034.

## Key decisions

- The advisory-key helper is a leaf module, `app/db/advisory.py`, because placing it in `matching.py` would create an import cycle (the matcher imports the roster, which needs the locks). The 100% branch gate covers both modules.
- HTTP 429 for the lookup ceilings is carried by `ConflictError` with an optional `status`, not a sixth error class; `retryable` stays false.
- The bounded retry wraps the unit of work (student saves, seat creation, centre invite, contact add and replacement verify, removal, `delete_account`), not the HTTP request; on the external deletion route it wraps `delete_account` alone because `otp.verify` commits first. The replacement request step is not wrapped.
- Replacement verify follows LO-3: unlocked read, account and contact keys, then `FOR UPDATE` by id with a re-check that the row is still the latest for its requester.
- The removed-contact SMS notice is English only (one GSM-7 segment, like the OTP text); the email notice is Bangla and English. The notice is best-effort and catches a bare exception by documented precedent.

## Test coverage

- `make PY=.venv/bin/python lint typecheck test`: Ruff and format clean, mypy clean (240 files), **2918 passed, 0 failed, 0 skipped** (baseline before the unit: 2846 passed). Integration tests ran against PostgreSQL 16 as `shikkhok_app`, none skipped.
- Coverage: backend 96% line (baseline 96%, floor 80%); money module 100% branch; matcher and advisory modules 100% branch.
- Unit-scoped command (9 files): 156 passed. Contract gates and schema parity: 160 passed.
- Test-first evidence (each run before its implementation): Step 4 matcher `6 failed, 2 passed`; Step 5 students `8 failed, 16 passed` (including the edit-versus-accept race resetting an accepted link); Step 6 lookup `5 failed, 11 passed`; Step 7 contact change `8 failed`; Step 8 deletion markers `4 failed`.

## Review round 1 fixes

- A replacement refused because another account holds the destination no longer consumes the daily change count (test-first: `assert 1 == 0` before the fix).
- One account never holds two live memberships in one centre: matching skips such an invitation and inviting such an account is refused `centre.member.already_invited` (test-first: `assert 2 == 1` and `201 != 409` before the fix).
- Reviving an archived student refuses a contact change on an accepted or erased link and a second seat in one batch, like an edit (test-first: `201 != 409` before the fix).
- New verifiers: `tests/accounts/test_contact_sentinels.py` (no sentinel phone, email or code in log records, audit rows or error bodies across teacher save, centre invite, both lookups, replacement, removal and in-app deletion; the test client's own request-URL logger is excluded because the deployed server runs without an access log), `tests/accounts/test_contact_indexes.py` (the partial email indexes are usable by every matcher and lookup statement; the change counters and replacement codes are purged by age), and the add-then-delete race test in `tests/governance/test_deletion_paths.py`. The race test was written after the deletion code it checks, so it has no red line.
- The creator's own email on their centre manager row is kept, consistent with the existing phone behaviour.
- After the fixes: `make lint typecheck test` 2931 passed, 0 failed, 0 skipped; backend 96%; matcher and advisory modules 100% branch.

## Deviations from the plan

- **Client strings outstanding.** The six new message keys are published; the Android `MessageKeyCoverageTest` and the web i18n test will fail until U3 and U4 add their strings. The Android, web, site and infra parts of `make check` were not run in this unit.
- **Tests not built**: the deletion-versus-revoke residual-pair test (that pair is resolved by the bounded retry, which is tested on its own).
- **Manual only**: the NFR8.1, 8.2, 8.6 and 8.7 latency figures and the NFR7.2 migration duration come from the manual staging run; nothing automated discharges them.
- **Process slips by the builder**: one edit to `app/db/models.py` was made with a script and one batch of Step 5 tests was appended with a shell heredoc, instead of the file tools; an accidental reformat of four old migrations was reverted.
