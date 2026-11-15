# Reliability Requirements — contacts-and-invites-backend (U2)

Intent `261113-unique-usernames`, unit U2 (kind: service). The IDs inherit
inception NFRs. The inception list has no reliability or concurrency NFR of
its own. Concurrency correctness here exists to keep link and decision
outcomes right, which is the authorization concern NFR4 makes test-first, so
the lock order, the retry and their tests are carried as NFR4.x. Migration
safety is NFR7 and the contract is NFR9.

Revised after review `reviews/review-01.md` (R-01, R-02, R-03). The orchestrator
decided the changes under the person's instruction "Go with your
recommendations". [Q5] records the retry decision that supersedes [Q1]'s
"no server-side retry".

## Availability and degradation

- U2 adds no new runtime dependency to the request path and no availability
  target of its own. Its routes share the single backend container and
  database (Phase 1 staging on Lightsail, team.md Deployment).
- The only external call U2 adds is the removed-contact notice, sent after
  commit (NFR4.7). If the SMS or email gateway is down, the notice is not
  sent. The person's request still succeeds and nothing is rolled back.

## NFR4 — Test-first, concurrency and failure handling

### NFR4.1 Test-first set

The following are written as failing tests **before** their implementation,
and the Bolt branch history shows each test commit before its
implementation commit (team.md: Testing Posture, the authorization
predicate):

- BR2.1, BR2.3, BR2.4, BR2.6, BR3.2, BR3.3, BR3.4, BR3.5, BR3.6, BR4.2, BR4.3,
  BR5.2, BR5.3, BR5.5, BR5.7 and BR5.13;
- NFR1.1, NFR1.4, NFR2.5 and NFR3.1 (security-requirements.md).

Verifier: the Bolt branch's commit order, read in review. The squash on
`main` hides it, which is why the branch is the record.

### NFR4.2 The lock order U2 enforces on the tables it writes (review-02 R-08, R-10, R-11; review-01 R-01, R-02)

**Scope of the claim.** This order governs the tables U2 writes, and the keys
U2 introduces: advisory keys, `otp_request`, `enrollment`, `owner_member`
and `account`. Every U2 path, and the U2-owned steps of account deletion,
follow it. Account deletion also runs legacy statements that U2 does not
reorder: batch retirement, `unassign_member`, ending memberships, the
account-scoped deletes, and the foreign-key cascades of `DELETE FROM
account`. For those, U2 makes **no** claim that a cycle is impossible.
Residual deadlocks there are named below and absorbed by NFR4.3's bounded
retry.

**LO-1. Advisory keys first, all of them, before any row lock in LO-2.** A
transaction takes every transaction-scoped advisory lock it needs
(`pg_advisory_xact_lock(hashtextextended(<key>, 0))`, the form
`replayed_student` already uses) before it locks or writes any row in an
LO-2 table. The one exception is the unlocked read LO-3 allows for W7. Keys
are taken by namespace, and by ascending 64-bit key within a namespace:

1. `student:<owner>:<client_mutation_id>` (existing, create replay only);
2. `account:<account uuid>`;
3. `contact:<kind>:<canonical value>`.

The existing attempt-recording commit that a wrong code or a wrong password
makes ends the request, so no lock outlives it.

**LO-2. Then row locks in one table order:** `otp_request` (the code being
spent), then `enrollment` (ascending `id`), then `owner_member` (ascending
`id`), then `account`. The `account` row is last on every U2 path: it is
locked by the contact `UPDATE` or the account `DELETE`, or implicitly by the
`KEY SHARE` a link write takes on its target.

**LO-3. Which keys each path takes, and in what sequence.**

| Path | Keys and sequence |
|---|---|
| Teacher save: student create, edit or revive; every seat creation through `seat_for` (W1, W2, enroll, add-to-batch, batch add-seat) | A `contact:` key for every contact recorded on each affected link **before and after** the change; then the seat rows in ascending `id` |
| Centre invitation (W3) | A `contact:` key for each given contact |
| Account creation (W4) | The `contact:` key of the account's contact, taken **before** the account row is inserted (LO-5) |
| Contact add verify (W5, W6) | `account:` for the acting account and `contact:` for the destination, which the request names. Then the `contact` code row is spent |
| **Replacement verify (W7 steps 5 to 11)** | (a) An **unlocked** read selects the latest unexpired `contact_replace` row for the request's destination whose requester is this account, and records its `id`, destination, requester and expiry. No row matched is the existing code refusal. (b) Take `account:` for the acting account, then `contact:` for the **old** value (the contact of that kind the account holds now) and for the **new** destination, in LO-1 order. (c) Select the same row `FOR UPDATE` **by `id`** and re-check that its destination, requester, purpose and expiry are unchanged and that it is unconsumed. On any difference the request is refused as an invalid code, with an attempt recorded against that row only, exactly as a wrong code is. (d) Spend it and continue as W7 steps 8 to 11 |
| Contact removal (W8) | `account:` for the acting account, and `contact:` for the value being removed |
| Replacement request (W7 steps 1 to 4) | None. It changes no seat, invitation or account row, and it delivers a code before its commit, which is why NFR4.3 does not retry it |
| Account deletion (security NFR3.1) | After the unlocked read that finds the account: `account:`, then a re-read of its contacts, then `contact:` for every contact it holds. Then, after the destination-scoped deletes and before any legacy statement: the account's `enrollment` rows (either link is the account) `FOR UPDATE` in ascending `id`, with the markers set; then the account's live `owner_member` rows (`account_id` is the account, `revoked_at IS NULL`) `FOR UPDATE` in ascending `id`. Only then do the unordered legacy statements run, ending with `DELETE FROM account` |

**LO-4. No explicit account `FOR UPDATE` before seat rows.** W5 to W8 stop
locking the account row up front. The `account:` key now does what that lock
did:

- it serialises two contact changes on one account, and a deletion of that
  account;
- it makes the last-contact check (BR5.5) and the "already holds this kind"
  check reliable.

In W5 to W7 the steps run in this order:

1. check that the destination is free;
2. take a savepoint;
3. run `match_contact`;
4. `UPDATE` the account;
5. discard drafts;
6. write the audit row;
7. commit.

A unique-index violation on the `UPDATE` rolls back to the savepoint, the
spent code is committed, and the answer is `account.contact.taken`, as built
today.

**LO-5. Account creation takes its contact key first.** U2 provides
`lock_contact(session, contact)`, and `create_account_rows` calls it before
the account `INSERT`. Otherwise a sign-up and a W5 add of the same contact
could wait on each other: one waits on the unique index, the other on the
advisory key. This is a one-line change in a U1-owned function, so it is a
**C3 amendment**: U2 owns the call. Advisory locks are re-entrant within one
transaction, so `match_contact` then finds its key already held.

**Pairs proven free of a cycle.** Each pair below shares an advisory key that
is taken first, or touches disjoint rows:

- **A teacher save and a contact add or replacement verify.** The matcher
  updates only empty links that record its contact, and a save touching such
  a link holds that contact's key, whether the contact is the old value or
  the new. This is review-02 R-08's example.
- **A contact verify or removal and deletion of the same account.** Both hold
  `account:`.
- **A teacher save and the U2-owned steps of deletion.** A save that resolves
  a target to the account holds one of that account's contact keys, and
  deletion holds all of them.
- **Accept or decline and the matcher.** These are conditioned single-statement
  updates on disjoint links (one names the holder, the other is empty). Both
  take no account lock, and changing a decision column fires no foreign-key
  check.

**Pairs that cannot be ruled out** (resolved by NFR4.3's retry, not by
ordering):

1. **Deletion of A against a centre manager's member revoke**
   (`app/centres/service.py:333-354` locks `owner_member` rows without an
   order). The revoke can hold a row whose `invited_by_account_id` is A while
   it waits for A's own membership row. Meanwhile deletion holds A's row
   (pre-locked) and its `DELETE FROM account` cascades `SET NULL` onto the
   `invited_by` row.
2. **Deletion of A against any path that updates a row referencing A** that
   the `DELETE` cascade sets to null. Examples are `owner.account_id`, fee
   claims and ledger entries that A verified, marks and attendance that A
   recorded, and help messages: the cascade locks those rows in heap order,
   after deletion has taken its other locks.
3. **Deletion of A's batches (`_RETIRE_OWNED_BATCHES`) against concurrent
   batch updates** on those batches.
4. **`unassign_member` inside deletion** (schedule slots, sessions, exams)
   against concurrent scheduling or exam edits in the same centre.

A deadlock in these pairs aborts one side with `40P01`. If deletion is the
victim, NFR4.3 re-runs it. If the legacy path is the victim, it answers
`TransientError` `retryable: true` exactly as today. U2 does not change
legacy paths.

| Verifier | What it asserts |
|---|---|
| Interleaving tests (two connections, the first transaction held open; both start orders; as `shikkhok_app`) | Each test asserts no `40P01` and that both finish within `lock_timeout` (5 s). (1) R-08: account A holds phone D and adds email C, while a teacher saves a link recording D and C. (2) A teacher edit moves a link's contact from C to D while A verifies C. (3) A sign-up on C while account B adds C: exactly one holds C. (4) Deletion of A while A removes a contact. (5) Deletion of A while a teacher edit relinks a seat to A: either the seat ends with A's link cleared and its marker set, or the edit, run after deletion, finds no account and leaves the link empty; never a cleared link without a marker. (6) The R-10 shape: accept on two seats while a teacher edit locks them ascending |
| **W7 re-check test** | Between the unlocked read and the locked re-read, a second transaction consumes the row, or expires it, or a newer row for the same destination and requester is issued. Each time, the verify is refused as an invalid code, does not spend another row, and records its attempt only on the row it read |
| **Deletion against revoke test** (residual pair 1) | Deletion of A interleaved with a revoke that touches a membership A invited and A's own membership. The deletion caller never receives `40P01`, because NFR4.3 absorbs it. Afterwards A's seats are blocked and A's memberships are revoked. The revoke either succeeds or answers `retryable: true` |
| Code check, in review | Every U2 call to `pg_advisory_xact_lock` comes before the first LO-2 row lock of its transaction, apart from W7's unlocked read. One helper owns key computation and ordering |

### NFR4.3 Bounded server-side retry (team.md Error handling; review-01 R-03; [Q5])

- SQLSTATEs **`40001`** (serialization failure) and **`40P01`** (deadlock
  detected) roll the whole transaction back. U2 then **re-runs the whole
  unit of work** in a fresh transaction: **at most 2 retries** (3 attempts in
  all), with jittered backoff of uniform 10–50 ms before the first retry and
  50–150 ms before the second.
- Each re-run starts from the unit of work's first statement after any
  committed attempt record, so it repeats the code consumption and the
  password check. A rolled-back attempt left nothing durable: no link, no
  counter increment, no spent code, no contact change.
- If the last attempt also fails with `40001` or `40P01`, the request fails
  as `TransientError`, `code: SERVICE_UNAVAILABLE`, `retryable: true`,
  through the existing `request_scope` mapping.
- **Scope:** the retry wraps exactly these, each safe to re-run because
  nothing leaves the process before its commit:
  - the W1 and W2 student saves (and every `seat_for` caller);
  - the W3 invitation;
  - W5, W6 and W7 verify;
  - W8 removal;
  - `delete_account`, including the code consumption its two routes perform
    in the same transaction.
- **Not wrapped:**
  - the W7 replacement request, because it delivers a code before its
    commit;
  - W4, account creation, which runs in U1's verify transaction and keeps
    today's classification;
  - every legacy route.
- **`55P03` (lock not available, from `lock_timeout`) is not retried.** It
  maps to `TransientError`, `retryable: true`, as today. Waiting 5 s again
  would only lengthen the request.
- Every retry is logged once (observability NFR4.10).
- The lock order (NFR4.2) remains the primary control. Within U2-ordered
  pairs, a retry in staging is a defect to investigate. Within the residual
  pairs it is the designed resolution.

| Verifier | What it asserts |
|---|---|
| Forced-deadlock test | A `40P01` injected once into a W7 verify after `match_contact` (a test hook raises `OperationalError` with that SQLSTATE on the first attempt only). The response is 200, the contact is replaced exactly once, the links are written once, `contact_chg_day` is incremented once, and the code is spent once |
| Exhausted-retry test | The same hook fires on all 3 attempts. The response is `retryable: true`, the contact is unchanged, the code still verifies afterwards, and the count is unchanged |
| No double send | Across both tests, the SMS and email gateway stubs record **zero** sends before the final commit and **exactly one** notice for the success case (W8 removal variant) |
| `55P03` not retried | A forced `55P03` produces one attempt and a `retryable: true` response |
| Deletion retry | A `40P01` injected once into `delete_account` after the markers are set. Deletion completes, the markers are set once, and `DeletionResult` counts are those of one run |

### NFR4.4 Lock waits stay within the engine's bounds

U2 runs inside the existing engine bounds (`app/db/session.py`, pinned by
`tests/db/test_engine_bounds.py`): `lock_timeout` 5 s, `statement_timeout`
15 s, `idle_in_transaction_session_timeout` 60 s. U2 never overrides them with
`SET LOCAL`. `lock_timeout` also bounds advisory-lock waits.

The worst case for a retried request is 3 attempts, each bounded by these
timeouts, plus at most 200 ms of backoff.

Verifier: the existing engine-bounds test, plus a test that `app/` contains no
`SET LOCAL lock_timeout` or `statement_timeout` outside `migrations/env.py`.

### NFR4.5 A contact change commits all of its parts once

A replacement or removal commits its contact write, its `contact_chg_day`
increment, its spent code (replacement), its links (replacement) and its audit
row in one commit, or none of them (BR5.4, BR5.6). This holds across retries
(NFR4.3).

Verifier: the two BR5.6 tests named in functional-spec § 5, plus NFR4.3's
forced-deadlock test.

### NFR4.6 Matching is atomic with its trigger and idempotent

- `match_contact` never commits. It runs in the transaction of the write that
  made the contact verified (BR3.1). A rollback of account creation (for
  example U1's username-unavailable outcome) undoes its links, and a retried
  verify links again.
- Running it twice changes nothing (BR3.8).

Verifier: tests that force a rollback after `match_contact` in account
creation and in contact add, and assert no link survives; and a test that runs
`match_contact` twice and compares the rows.

### NFR4.7 The notice is sent after commit and never fails the request

The removed-contact notice is sent after the change commits, once, with no
retry. A gateway exception, a timeout or a budget refusal is logged
(observability NFR4.9) and never raised to the person, and the committed
change stands (BR5.9, team.md Error handling: the FCM-style exception). No U2
transaction does network I/O while it holds an advisory key or a row lock.
Because the notice is outside the retried unit of work (NFR4.3), a retry can
never send it twice.

Verifier: a test with a gateway stub that raises, which asserts a 200
`MeResponse`, the contact removed, and one outcome log line. A test asserts
the gateway is called only after commit (the stub checks
`session.in_transaction()` is false).

## NFR7 — Migration safety

| ID | Requirement | Verifier |
|---|---|---|
| NFR7.1 | One forward-only Alembic revision. The new columns are all nullable with no default: `student.student_email`, `student.guardian_email`, `enrollment.student_email`, `enrollment.guardian_email`, `owner_member.invited_email` (text, at most 254), and `otp_request.requested_by_account_id` (FK `account.id` `ON DELETE SET NULL`). `owner_member.invited_phone` drops `NOT NULL` and gains the at-least-one `CHECK`; every existing row holds a phone or `""`, so the check validates without a rewrite. The indexes of scalability NFR8.8 are added in the same revision. No `UPDATE` touches an existing row. | The schema-parity test and the migration-from-head test, extended to apply this revision to a database seeded with phone-only rows and assert they are unchanged |
| NFR7.2 | The migration runs as the deploy's own logged step, before the new container serves traffic. It is rehearsed on staging, under `migrations/env.py`'s `lock_timeout` of 10 s, and finishes in **at most 10 s** on staging. Production has the verified `pg_dump` to S3 first (team.md Deployment). | The staging deploy log's migrate-step duration, recorded in the Bolt's PR. **This is a manual reading. Nothing automated checks the 10 s figure.** |
| NFR7.3 | **Rollback window.** Rolling back to the previous image tag is safe except in one case: once an email-only invitation exists, the previous image's `MemberResponse.phone: str` cannot serialise that centre's member list. Rollback after the first email-only invitation is therefore a roll-forward fix. This is accepted: there are no production users, and the person's direction removed old-client compatibility. | Written in the U2 deploy notes; checked off on the release checklist |

## NFR9 — The committed contract

| ID | Requirement | Verifier |
|---|---|---|
| NFR9.1 | Every request and response change in C2, plus the nullable `MemberResponse.phone` and the new `/v1/me/contact/remove`, is in the regenerated committed `openapi.json`. | The existing schema-diff gate |
| NFR9.2 | The new keys are added to `message-keys.json` and to both clients' Bangla and English bundles in the same change: `student.email.taken`, `account.contact.last_one`, `account.contact.change_limit`, `account.contact.password_required`, `account.contact.admin_locked`, and `auth.lookup.too_many` (whichever of U1 or U2 merges first adds it). | The backend key test and `MessageKeyCoverageTest` |

## Backup and recovery

Nothing new. U2's data lives in existing tables covered by the Phase 1
`pg_dump` and the Phase 2 RDS snapshot (team.md Deployment). Advisory locks
are transaction-scoped and vanish with their connection.

## Assumptions & Open Questions

- [assumption] Staging tables are small enough that the `owner_member`
  `CHECK` validation and the index builds finish well inside 10 s. NFR7.2's
  reading confirms it.
- [assumption] The two deletion routes consume their code and call
  `delete_account` in one transaction, so NFR4.3 can wrap both as one unit of
  work. If code generation finds otherwise, the retry wraps `delete_account`
  alone, and that is safe because the code row is deleted by the deletion
  itself.
- C3 amendment needed: the LO-5 `lock_contact` call in `create_account_rows`,
  and `app/governance/deletion.py` as a shared file (security NFR3.1).
- Open questions: None. [Q5] settles the retry decision.

## Sources

- Requirements NFR4, NFR7 and NFR9: `inception/requirements-analysis/requirements.md`.
- Functional design: `functional-spec.md` W1 to W9 and § 7; `rules.md` BR2.6,
  BR2.7, BR3.1, BR3.8, BR5.3 to BR5.6, BR5.9 and BR5.12; review
  `reviews/review-02.md` R-08 to R-11.
- This stage's review: `nfr-requirements/reviews/review-01.md` R-01, R-02 and
  R-03.
- Contracts: `contract-summary.md` C2, C3 and the 2026-11-14 direction.
- Code read: `app/request_scope.py`, `app/db/session.py`, `migrations/env.py`,
  `app/accounts/contact.py`, `app/students/service.py` (`replayed_student`),
  `app/governance/deletion.py` (lines 394-421: legacy statements and the final
  `DELETE`), `app/db/models.py`.
- Answers: [Q2] and [Q5] in `nfr-requirements-questions.md` ([Q1]'s
  no-retry clause is superseded by [Q5]).
- Rules: team.md (Testing Posture; Code Style: Error handling, "a
  serialization failure is a bounded transaction retry"; Deployment),
  project.md Mandated, construction.md Error Handling.
