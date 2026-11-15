# Code Summary — usernames-backend (U1)

Built against the approved plan (`code-generation-plan.md`, Steps 1–23; Step 24
is this file, `source-manifest.json` and `traceability.json`). U2 was already
built on the branch and is reused, not changed in behaviour.

## Files

- **New**: `app/accounts/usernames.py` (rules, keys, reserved list, holds, availability, claim rule, first choice, rename, reclaim, case-only change), `app/schemas/usernames.py`, `migrations/versions/0035_usernames.py`.
- **Modified application code**: `app/db/models.py` (username columns, `username_reclaimed_at`, `UsernameHold`; stale "dormant" prose corrected), `app/db/advisory.py` (`username` namespace, last), `app/auth/ceilings.py` (twelve scopes in four families; refusal keys), `app/auth/hashing.py` (`keyed_digest`), `app/auth/pending.py`, `app/auth/otp.py` (comment), `app/accounts/identifier.py` (`classify_login`), `app/accounts/passwords.py` (username sign-in, `confirm_password`), `app/accounts/service.py`, `app/api/accounts.py`, `app/api/auth.py`, `app/api/me.py`, `app/schemas/accounts.py`, `app/schemas/auth.py`, `app/contract/privacy.py`, `app/contract/routes.py`, `app/governance/deletion.py`, `dispositions.py`, `commands.py`, `app/audit/log.py`.
- **Generated and configuration**: `openapi.json`, `docs/legal/PRIVACY.md`, `message-keys.json`, `scripts/generate_privacy_policy.py`, `deploy/README.md` (key rotation note), `Makefile` (100% branch pass for the usernames module).
- **Tests**: new `tests/accounts/test_usernames.py`, `test_username_claims.py`, `test_username_sentinels.py`, `test_username_concurrency.py`, `tests/auth/test_username_sign_in.py`; extended sign-up, ceiling, audit, centres, privacy, admin-contract, route-lens, analytics-contract, deletion, purge and migration-pin tests.
- **Design records updated (plan Step 23)**: `functional-design/rules.md`, `entities.md`, the C1 block of `inception/contract-design/contract-summary.md`, `nfr-requirements/security-requirements.md` (NFR2.4, NFR2.5, Amendment 8).

## Key decisions

- **Family D cross-network rule**: a network is refused on the cross-network count only after it has failed that username three times, so an owner's typo or two never locks them out after a stranger fills the counter. The bound for *k* networks is at most 20 + 3*k* per window; the test drives 25 /64s in 3 /48s and counts exactly 75 failures.
- **Rename and first choice lock in two calls** (account key, re-read `FOR UPDATE`, then the username keys), run under `run_with_retry`; the claim ceilings and the password check commit before the unit, so a re-run never re-counts them.
- **The rename window is checked before availability**; with the window closed only an exempt reclaim of the caller's own held name proceeds.
- **Deletion places a digest-only hold** inside `delete_account`'s transaction under U2's lock order; `username_hold` has its own retention class (`UNTIL_EXPIRY`).
- **Lookups are `POST` with a body**, so no username reaches a URL or the host's access log.

## Test coverage

- `make PY=.venv/bin/python lint typecheck test`: Ruff and format clean, mypy clean (242 files), **3090 passed, 0 failed, 0 skipped**; integration tests ran against PostgreSQL 16 as `shikkhok_app`.
- Coverage: backend 96% line (unchanged; floor 80%); `app.accounts.usernames` 100% branch; money and matcher passes still 100%.
- Unit-scoped command: 193 passed. Contract and schema gates: 70 passed.
- Test-first evidence (each before its implementation): Step 4 collection error (module absent); Step 5 `24 failed`; Step 6 collection error; Step 7 collection error; Step 8 `15 failed, 55 passed`; Step 9 collection error.

## Deviations from the plan

- **The lock line in `create_account_rows`**: the username key was appended to U2's existing `lock_keys` call there (BR10.1 requires one call with the contact keys); the contact keys, their order and the matcher call are unchanged.
- **Small helpers outside the plan's list**: `confirm_password`, `classify_login` with `UsernameSubject`/`LoginSubject` (the `Identifier` type is not widened), `keyed_digest`, `username_key`, an injectable `utc_now`.
- **Unchecked counts**: removed in the four places NFR3.6 names and in a few adjacent comments being edited; some older counts remain in `test_purge.py` docstrings and the `deletion.py` module docstring.
- **Outstanding**: client strings for the new message keys are U3/U4's; NFR1.2 timing medians and NFR7.2 migration duration are manual staging readings and nothing automated discharges them; the "Open questions" table in `contract-summary.md` and functional-spec W4, W5, W7, W8 still carry pre-amendment wording (GET lookups, single-call locking, `retry_limit`) — the amended rules, NFRs and C1 block are what was built.
- **Process slip by the builder**: `ruff format` over `migrations/` touched four old migrations; restored from HEAD.
