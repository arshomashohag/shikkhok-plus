# Reliability Requirements — usernames-backend (U1)

Intent `261113-unique-usernames`, unit U1 (kind: service). The IDs inherit
inception NFRs. The inception list has no reliability or concurrency NFR of
its own. As in U2, concurrency correctness exists here to keep authorization
outcomes right (who holds a name, whether a held name can be taken), which is
the concern NFR4 makes test-first, so the lock order and the retry are carried
as NFR4.x. Coverage is NFR5, compatibility NFR6, migration safety NFR7 and the
contract NFR9. Security IDs (NFR1 to NFR3) are in `security-requirements.md`.

U1 reuses U2's mechanisms as built and does not redo them:
`app/db/advisory.py` (`lock_keys`, LO-1 to LO-5), `app/db/retry.py`
(`run_with_retry`), the committing and non-committing consumes in
`app/auth/ceilings.py`, and U2's `delete_account` changes (relink markers,
the account-key re-read, the retry around deletion).

## Availability and degradation

- U1 adds no runtime dependency, process or host. Its routes share the single
  backend container and PostgreSQL (Phase 1 staging on Lightsail, team.md
  Deployment). It has no availability target of its own beyond the
  backend's.
- Degradation, by design: a lookup at its ceiling answers 429 and the form
  can still be submitted, because the submission's own check decides (BR3.4).
  A claim or replacement at its ceiling refuses that submission (security
  NFR2.2, NFR2.3). For a replacement, the person can submit a new draft. For
  a claim, they can try again in the next window. A username sign-in at a
  Family D ceiling refuses that path only. Phone, email and code sign-in are
  unaffected (security NFR2.4).
- No username path calls an external service. No SMS or email is sent by
  any username path (BR8.4).

## NFR4 — Test-first, concurrency and failure handling

### NFR4.1 Test-first set

The following are written as failing tests **before** their implementation,
and the Bolt branch history shows each test commit before its implementation
commit (team.md: Testing Posture, the authorization predicate):

- every rule marked `test_first: true` in `rules.md` (BR1.7, BR2.2 to BR2.6,
  BR2.9, BR3.1, BR3.2, BR3.5, BR4.3 to BR4.7 as amended, BR5.1, BR5.3, BR6.1
  to BR6.6, BR6.9, BR7.1, BR7.2, BR7.4, BR7.5, BR8.1 to BR8.4, BR10.1);
- security NFR1.1, NFR1.4, NFR1.5, NFR1.6, NFR1.7, NFR2.4 and NFR3.2;
- NFR4.2's two-device rename test and NFR4.6's uniqueness race below.

Verifier: the Bolt branch's commit order, read in review. The squash on
`main` hides it, which is why the branch is the record.

### NFR4.2 The lock order, with the username namespace last (BR10.1; R-06)

- `_NAMESPACE_ORDER` in `app/db/advisory.py` becomes `("student", "account",
  "contact", "username")`, with a `username_key(key)` helper that names
  `username:<key>`. Nothing else in the helper changes.
- **Every writer of an existing account's username takes `account:<id>`
  first.** First choice (W7), rename, reclaim and case-only change (W8, W8a),
  and deletion (W9) all do. Account creation writes a row that did not exist,
  so no other transaction can hold its account key.
- **First choice and rename take their keys in two calls (R-06).** First,
  `lock_keys([account:<id>])`, then the account row is re-read `FOR UPDATE`
  (username, `username_key`, `username_changed_at`,
  `username_reclaimed_at`). Then `lock_keys([username:<new key>,
  username:<old key>])`, with the old key taken from that locked re-read
  (absent in a first choice). This replaces functional-spec § 7's single
  call. The old key can no longer be read before the account lock, so the
  stale-read case R-06 describes cannot arise, and no extra re-run path is
  needed. The reviewer's prescribed fix (read, lock, re-read, then re-run on a
  difference) was checked separately and would also work. It was not adopted,
  because it adds a retry path to remove a race this order removes outright
  (team.md Corrections, 2026-10-17). Taking the username keys in a later call
  than the account key keeps to § 7's own rule: username keys come last, and
  no path takes a username key and then an account, contact or student key.
- Sign-up completion takes `contact:*` and `username:<key>` in one call (W2
  step 7). Deletion takes `account:<id>`, re-reads, then takes `contact:*` and
  `username:<key>` in one call (W9).

| Verifier | What it asserts |
|---|---|
| Two-device rename test (two connections, the first transaction held open after its re-read; as `shikkhok_app`) | Account A holds `a1` with the window open. Device 1 renames it to `a2`. Device 2, which read `a1` before device 1 committed, concurrently sends a rename to `a3`. Device 2 waits on `account:A`, re-reads `a2`, finds the window closed and `a3` not held for A, and is refused `change_too_soon`. In a second run, device 2 sends `a1` instead: it re-reads `a2`, and `a1` is held for A, so this is an exempt reclaim. The hold is placed on **`a2`**, the key from the locked re-read, and not on `a1`, which is the stale key R-06 describes. Neither run produces `40P01` |
| Claim against release test | B claims `x` while A renames away from `x`. B is refused in both start orders (functional-spec § 7, "A rename releasing a name") |
| Claim against deletion test | B claims `y` while A, which holds `y`, is deleted. B is refused in both orders, and after the deletion a live hold for nobody exists on `y` |
| Code check, in review | Every U1 call to `lock_keys` is in the order above. One helper names the keys |

### NFR4.3 Bounded server-side retry (BR10.3; team.md Error handling)

- **Wrapped by `run_with_retry`** (`40001`, `40P01`; at most 2 re-runs with
  jittered backoff of 10–50 ms and then 50–150 ms; then `TransientError`,
  `SERVICE_UNAVAILABLE`, `retryable: true`): the first-choice and rename unit
  of work, from the account lock to its commit (W7 steps 2–4, W8 steps 3–7).
  Nothing leaves the process before that commit.
- **Outside the wrapper and committed before it:** the Family B claim cascade
  (security NFR1.6) and the rename's password confirmation (BR6.1). A re-run
  therefore never re-counts a claim or a password failure.
- **Not wrapped:** the verify path (W2). It commits code refusals part-way,
  so it cannot be re-run from its first statement (BR10.3). Its keys are
  ordered, so a cycle is not expected there.
- **Deletion:** U2 already wraps `delete_account` (U2 reliability NFR4.3).
  U1's hold upsert runs inside that same unit, so a re-run upserts the hold
  once: the upsert is idempotent on `key_digest`.
- `55P03` is not retried, as built.

| Verifier | What it asserts |
|---|---|
| Forced-deadlock test | A `40P01` injected once into a rename after the hold upsert. The response is 200, the account has the new name, exactly one hold exists on the old key, `USERNAME_CHANGED` is written once, and `un_cl_acct_hour` was incremented once |
| Exhausted-retry test | The same hook on all 3 attempts. The response is 503 `retryable: true`, the account and holds are unchanged, and `un_cl_acct_hour` was incremented once |
| Deletion retry with a username | A `40P01` injected once into `delete_account` after the hold upsert. One live hold for nobody exists afterwards |

### NFR4.4 The verify rollback keeps the code usable (BR2.4, BR2.5)

A 409 `account.username.unavailable` at verify commits nothing from the
verify transaction. The code is unspent, its attempt count is unchanged, the
draft is as it was, and no account, profile or link row exists. Only the
Family C counters, committed before the code was read, survive (security
NFR2.3).

Verifier: test, written first. Two drafts name one username, the first
verifies, and the second gets 409. Then the second's same code with a free
replacement succeeds, and the account carries the replacement. A third test
sends a taken replacement and gets 409 again, with the code still usable.

### NFR4.5 Engine bounds

U1 runs inside the existing engine bounds (`app/db/session.py`, pinned by
`tests/db/test_engine_bounds.py`): `lock_timeout` 5 s, `statement_timeout`
15 s, `idle_in_transaction_session_timeout` 60 s. It never overrides them.
`lock_timeout` bounds the username advisory waits too. A rename's worst case
is 3 attempts, each within these bounds, plus at most 200 ms of backoff.

Verifier: the existing engine-bounds test, and U2's test that `app/` holds no
`SET LOCAL lock_timeout` or `statement_timeout` outside `migrations/env.py`.

### NFR4.6 Exactly one account wins a name

Two concurrent claims of one key (two sign-up completions, two first choices,
or one of each) end with exactly one account holding it. The other is refused
`account.username.unavailable` (409), never a 500. If any writer reaches the
`username_key` unique constraint, its violation maps to the same refusal
(BR10.2).

Verifier: an overlapping-claims test, written first: N = 8 concurrent first
choices of one name from 8 accounts. Exactly one row holds the key, 7
responses are 409, and none is 5xx. A unit test drives the constraint mapping
by bypassing the advisory key.

### NFR4.7 The hold purge is chunked and re-runnable

The existing retention purge deletes `username_hold` rows whose `held_until`
is strictly before the run's moment, in `CHUNK_SIZE` chunks committed one by
one, and stamps its heartbeat (BR7.6). A killed run resumes on the next. A
failed purge only leaves rows that already read as free (BR6.9).

Verifier: a purge test with live and expired holds, which asserts that only
expired rows go and that a second run deletes nothing.

## NFR5 — Coverage

| ID | Requirement | Verifier |
|---|---|---|
| NFR5.1 | Backend line coverage stays at or above 80%, with no decrease from the figure on `main` before the Bolt. All U1 code lands in packages already in `make test`'s explicit `--cov` list (`app.accounts`, `app.auth`, `app.api`, `app.schemas`, `app.contract`, `app.governance`, `app.db`). No new package is created, so the list does not change. | `make test`'s 80% pass and `test_coverage_scope.py` (which asserts the list against what is on disk) |
| NFR5.2 | `app/accounts/usernames.py` carries a **100% branch** gate: a fourth `coverage report --include` pass in `make test`, beside the money and matcher passes. It decides who may take a name and what a hold is, so its defects live in branches (team.md: the authorization layer is measured by branch coverage). The username namespace added to `app/db/advisory.py` is already under the matcher pass's 100% gate. | The new `make test` pass failing under 100 |

## NFR6 — Compatibility

| ID | Requirement | Verifier |
|---|---|---|
| NFR6.1 | **`PasswordSignInRequest` accepts a login-only body (R-05).** It overrides the inherited `_exactly_one` validator by name, or stops inheriting `IdentifierFields`, and its own validator requires exactly one of `login`, `phone` and `email`. `IdentifierFields` is unchanged (ADR-003). The existing phone-only and email-only bodies keep working (FR4.6). | Schema tests: `{login, password}` accepted; `{phone, password}` and `{email, password}` accepted; none, two, or all three refused 422; `IdentifierFields` still refuses a body with neither phone nor email |
| NFR6.2 | `/v1` changes are additive for the current clients: new optional request fields (`login`, the verify `username`), new response fields (`MeResponse.username`, `username_required`), new routes, and new error statuses on existing routes (409 on `POST /v1/accounts`, 429 on `POST /v1/auth/verify` and `PUT /v1/me/username`). `SignupRequest.username` is required, which is accepted under the 2026-11-14 direction: compatibility with app versions installed before this change is not a constraint. | The schema-diff gate (NFR9.1) and the C1 review of the diff |
| NFR6.3 | **Rolling back to the previous image tag is safe.** The new columns are nullable, and the previous image neither reads nor writes them. A sign-up completed on the previous image creates an account with no username (`username_required` on roll-forward). One stated cost: a deletion run on the previous image places no hold, so that name is free at once. This is accepted, because there are no production users and the window is a rollback. | Written in the U1 deploy notes; checked off on the release checklist |

## NFR7 — Migration safety

| ID | Requirement | Verifier |
|---|---|---|
| NFR7.1 | One forward-only Alembic revision after `0037_contacts_and_email_invites` (functional-spec § 8). `account`: four nullable columns, the unique constraint on `username_key`, and the both-or-neither and shape checks (BR1.9). `pending_signup`: nullable `username`. Then `username_hold`. No `UPDATE` touches an existing row, and no column has a default. The checks validate without a rewrite, because every existing row is null on both columns. | The schema-parity test, and the migration-from-head test extended to apply this revision to a seeded database and assert the existing rows are unchanged |
| NFR7.2 | The migration runs as the deploy's own logged step, before the new container serves traffic, rehearsed on staging under `migrations/env.py`'s `lock_timeout`, and finishes in **at most 10 s** on staging. Production has the verified `pg_dump` to S3 first (team.md Deployment). | The staging deploy log's migrate-step duration, recorded in the Bolt's PR. **This is a manual reading. Nothing automated checks the 10 s figure.** |
| NFR7.3 | The downgrade is not exercised in production. The rollback path is NFR6.3 (previous image, columns left in place). | NFR6.3 |

## NFR9 — The committed contract

| ID | Requirement | Verifier |
|---|---|---|
| NFR9.1 | Every C1 change is in the regenerated committed `openapi.json`. That includes this stage's amendments: the two lookups as `POST` with `UsernameAvailabilityRequest`; 429 on `PUT /v1/me/username` and `POST /v1/auth/verify`; 409 on `POST /v1/accounts`; the built statuses (400 for taxonomy refusals, 422 for schema refusals, functional-spec § 10 issue 1). C1's prose in `contract-summary.md` is corrected in the same change. | The existing schema-diff gate |
| NFR9.2 | `message-keys.json` and both clients' bundles gain the C1 keys plus `account.username.password_required`. `account.username.retry_limit` is not added (functional-spec § 6). `auth.lookup.too_many` already exists (U2 merged first). | The backend key test and `MessageKeyCoverageTest` |

## Backup and recovery

Nothing new. `username_hold` and the new columns are in existing PostgreSQL
storage, covered by the Phase 1 `pg_dump` and the Phase 2 RDS snapshot
(team.md Deployment). A restore brings holds back with their `held_until`, and
an expired one reads as free (BR7.2). Rotating `SHIKKHOKPLUS_OTP_HMAC_KEY`
after a restore releases restored holds early (BR7.7).

## Assumptions & Open Questions

- [assumption] Staging tables are small enough that the new checks and the
  unique index build within 10 s. NFR7.2's reading confirms it.
- [assumption] U2's retry around `delete_account` wraps the code consumption
  and the deletion as one unit (U2's own assumption). If not, the hold upsert
  is still idempotent.
- Open questions: None.

## Sources

- Requirements NFR4 to NFR7 and NFR9: `inception/requirements-analysis/requirements.md`.
- Functional design: `functional-spec.md` W2, W7 to W10, § 7, § 8, § 10;
  `rules.md` BR2.4, BR2.5, BR6, BR7.5, BR7.6, BR10; review
  `reviews/review-01.md` R-05, R-06.
- U2's NFRs: `construction/contacts-and-invites-backend/nfr-requirements/reliability-requirements.md`
  (LO-1 to LO-5, NFR4.3, NFR4.4).
- Contracts: `contract-summary.md` C1, C3 and the 2026-11-14 direction.
- Code read: `app/db/advisory.py`, `app/db/retry.py`,
  `app/schemas/identifier.py`, `Makefile` (coverage passes, 222-267),
  `app/governance/commands.py`.
- Rules: team.md (Testing Posture; Corrections 2026-10-17; Code Style: Error
  handling; Deployment), project.md Mandated.
