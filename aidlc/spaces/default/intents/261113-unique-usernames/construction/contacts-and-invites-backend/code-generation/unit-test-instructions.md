# Unit Test Instructions — contacts-and-invites-backend (U2)

## Framework and setup

- pytest, as configured in `pyproject.toml`; integration tests use testcontainers
  with a real PostgreSQL 16 container, connecting as the restricted
  `shikkhok_app` role (the meta-test in `tests/conftest.py` asserts it is not a
  superuser and that row-level security is in force).
- **Docker is required.** Without a reachable Docker daemon the integration
  tests are skipped at module level; a skip is not a pass. Confirm the run
  reports the integration tests as passed, not skipped.
- Dependencies: the backend's pinned development requirements (the lock file the
  repository's CI installs from), installed into the project virtualenv.

## Commands (this unit only)

Run from the repository root:

```bash
python -m pytest -q -p no:cacheprovider \
  tests/accounts/test_contact_matching.py \
  tests/accounts/test_contact_change.py \
  tests/accounts/test_contact_concurrency.py \
  tests/accounts/test_lookup.py \
  tests/accounts/test_seat_linking.py \
  tests/students/test_students.py \
  tests/batches/test_roster_states.py \
  tests/centres/test_centres.py \
  tests/governance/test_deletion_paths.py
```

Contract and schema gates touched by this unit:

```bash
python -m pytest -q -p no:cacheprovider \
  tests/contract/test_privacy_schema.py \
  tests/contract/test_admin_contract.py \
  tests/contract/test_route_lenses.py \
  tests/contract/test_message_keys.py \
  tests/contract/test_schema_diff.py \
  tests/db/test_schema_parity.py
```

Branch coverage of the matcher (100% required):

```bash
python -m pytest -q -p no:cacheprovider \
  tests/accounts/test_contact_matching.py tests/accounts/test_seat_linking.py \
  --cov=app.accounts.matching --cov-branch --cov-report=term-missing --cov-fail-under=100
```

Test-first steps (plan Steps 4–8) run the named file alone and record the
failing output before the implementation step, for example:

```bash
python -m pytest -q -p no:cacheprovider tests/accounts/test_contact_matching.py
```

## Coverage targets

- Backend line coverage stays at or above 80% overall with no decrease from the
  last measured figure (`make test` reports it; the floor may not be lowered).
- `app.accounts.matching`: 100% branch coverage.
- Every rule marked `test_first: true` in `functional-design/rules.md` has a
  named test that was seen failing first.

## Volume (Standard strategy)

Five to eight tests per changed component (matcher, roster/students, centres,
lookup, contact change, deletion, retry wrapper), plus the two-connection
concurrency tests NFR4.2 names. About 60 tests in total.

## Mocking and stubbing

- The SMS and email gateways use the existing null adapter; tests assert on the
  recorded sends (the removed-contact notice is sent once, after commit, and a
  gateway failure does not fail the request).
- No mocking of the database: concurrency and locking tests open two real
  connections against the container and interleave them with explicit
  transaction control.
- A forced `40P01` is produced by a real two-connection deadlock, not a mock.

## Test data

- Build accounts, students, seats and centre invitations through the existing
  test factories and fixtures in `tests/accounts/conftest.py` and
  `tests/accounts/signup_support.py`; add small helpers there for email-only
  records rather than per-test SQL.
- Use reserved test domains (`example.com`) and test phone ranges already used
  by the suite; never a real address or number.
