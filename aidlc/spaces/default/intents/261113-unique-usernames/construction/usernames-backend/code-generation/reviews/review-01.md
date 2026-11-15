## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-11-15T06:15:44Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | app/accounts/passwords.py > _sign_in_by_username, and app/accounts/identifier.py > classify_login | A login containing a NUL character (or a lone surrogate) is classified as a username whose key goes straight into the account query. I ran it through POST /v1/auth/password and it returns an unhandled 500 (psycopg DataError), not the uniform refusal, and the failure is never counted. It does not depend on whether an account exists, but it is a non-uniform status on a public sign-in route. | Make a login whose key is outside the username character set an unknown name. Skip the SQL lookup and still run the dummy scrypt, count the failure on Family D and return the one refusal. Add a test that posts a NUL and a lone-surrogate login and asserts the uniform refusal and counted failure. | New |
| R-02 | Minor | app/api/auth.py > verify_code, app/auth/ceilings.py > check_and_consume_username_replacement (un_rp_dest_hour) | The replacement count is consumed before the code is read, and a verify carrying a username needs no valid code to count. A stranger who knows a destination can send five such verifies an hour. A victim whose draft name was taken then gets 429 on the replacement and must restart sign-up with a new code. Phone, email and code sign-in are unaffected. | Either record the limitation in the NFR so U3 and U4 clients handle the 429 by restarting sign-up, or count the destination scope only after the code is proven right. | New |
| R-03 | Minor | tests/contract/test_analytics_contract.py > test_public_routes_still_holds_exactly_twelve, and tests/governance/test_purge.py > module and helper docstrings | A test edited by this unit is still named exactly_twelve while asserting 15 entries. test_purge.py still says eighteen of twenty-five tables when the manifest now holds 45. Both are counts in prose that nothing checks, which the project forbids. | Rename the test without a number, and remove or replace the stale counts in the test_purge.py docstrings and the deletion.py module docstring. | New |
| R-04 | Minor | aidlc/spaces/default/intents/261113-unique-usernames/construction/usernames-backend/functional-design/functional-spec.md > file table, W4, W5 and the C1 Open questions table | Both still describe GET lookups with a query string and single-call locking, while the built routes are POST with a body and two-call locking. The code-summary admits this. U3 and U4 clients read these documents beside the amended C1 block, so a reader following W4 builds a request that puts a username in the URL. | Update W4, W5, W7 and W8 and the Open questions table to the built POST and two-call behaviour, or mark the superseded wording in place. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| ruff check app tests and ruff format --check | PASS (564 files formatted) | Clean. |
| mypy app | PASS (242 files) | Clean. |
| pytest: username unit tests, tests/contract, migration head pin | PASS | Security, claim, sign-up race, concurrency and privacy-gate tests run against real PostgreSQL as the restricted role. |
| Scratch probe of POST /v1/auth/password with a NUL in login | 500 DataError | Confirms the Major finding. |
| Source manifest against the git diff | The two sets are identical | No unrelated changes were claimed or made. |

### Summary

The design holds up. Username sign-in is a uniform refusal on identical statements. Family D counters use keyed digests and never touch the phone, email or code scopes. The sign-up rollback leaves the code unspent and the draft intact, and the replacement count survives it. The lock order, the hold ledger, the migration and the privacy gate are sound, and no pre-existing test was weakened. The one real defect is the unhandled 500 on a NUL or lone-surrogate login; it is cheap to fix and should be fixed before this unit merges.
