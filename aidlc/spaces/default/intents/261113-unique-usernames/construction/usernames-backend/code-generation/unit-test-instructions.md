# Unit Test Instructions — usernames-backend (U1)

## Framework and setup

- pytest as configured in `pyproject.toml`; integration tests use testcontainers
  with PostgreSQL 16 (`postgres:16-alpine`), connecting as the restricted
  `shikkhok_app` role behind the existing superuser and row-level-security
  meta-check in `tests/conftest.py`.
- **Docker is required**; without it the integration tests skip, and a skip is
  not a pass. Confirm the integration tests are reported as passed.
- Use the project virtualenv: `.venv/bin/python` (pinned requirements installed).
- `SHIKKHOKPLUS_OTP_HMAC_KEY` is set by the existing test fixtures; hold and
  counter digests are asserted against known HMAC vectors computed in the test.

## Commands (this unit only)

Run from the repository root:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/accounts/test_usernames.py \
  tests/accounts/test_username_claims.py \
  tests/accounts/test_username_sentinels.py \
  tests/accounts/test_username_concurrency.py \
  tests/accounts/test_verify_first_signup.py \
  tests/accounts/test_signup.py \
  tests/auth/test_username_sign_in.py \
  tests/governance/test_deletion_paths.py
```

Contract and schema gates this unit touches:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/contract/test_privacy_schema.py \
  tests/contract/test_admin_contract.py \
  tests/contract/test_route_lenses.py \
  tests/contract/test_message_keys.py \
  tests/contract/test_schema_diff.py \
  tests/db/test_schema_parity.py
```

Branch coverage of the usernames module (100% required):

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/accounts/test_usernames.py tests/accounts/test_username_claims.py \
  --cov=app.accounts.usernames --cov-branch --cov-report=term-missing --cov-fail-under=100
```

Test-first steps (plan Steps 4–9) run the named file alone and record its
failing output before the matching implementation step, for example:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider tests/auth/test_username_sign_in.py
```

## Coverage targets

- Backend line coverage stays at or above 80% overall with no decrease from the
  last measured figure (96% after U2); the floor may not be lowered.
- `app.accounts.usernames`: 100% branch coverage.
- Every `test_first: true` rule and every NFR verifier marked "written first"
  has a named test seen failing before its implementation.

## Volume (Standard strategy)

Five to eight tests per changed component (usernames module, sign-up and
verify, sign-in, lookups, claims and rename, privacy gates, deletion hold, lock
order), plus the concurrency and sentinel tests. About 80 tests in total.

## Mocking and stubbing

- SMS and email gateways: the existing null adapter and the `outbound` capture
  fixture U2 added.
- Time: inject the clock the services already accept (`now=`) to step through
  the 30-day window and the hold expiry; never sleep.
- Network prefixes for the ceilings: set the client address per request the way
  the existing ceiling tests do (`tests/auth/test_password_ceilings.py`).
- No database mocking: concurrency tests open two real connections and
  interleave them with explicit transaction control.

## Test data

- Accounts and drafts through the existing helpers in
  `tests/accounts/signup_support.py` and `tests/accounts/conftest.py`; add a
  small helper there for creating an account with a username.
- A distinctive sentinel username (for example `zq_sentinel_77`) in the
  sentinel test; reserved test phone ranges and `example.com` addresses only.
