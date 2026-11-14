# Security Requirements — contacts-and-invites-backend (U2)

Intent `261113-unique-usernames`, unit U2 (kind: service). Each requirement
inherits the ID of the inception NFR it refines (`requirements.md`, NFR1 to
NFR9) and names the verifier that discharges it (project.md: NEVER record an
obligation without its verifier). Rules `BRn.m` are in
`functional-design/rules.md`. Answers `[Q1]` to `[Q4]` are in
`nfr-requirements-questions.md`.

Threat summary for this unit. U2 adds three ways for a contact to become an
authorization fact: a teacher records an email, an account verifies one, or a
contact leaves an account. The failures that matter are these:

- a stranger receives a child's seat invitation, which can become a lens;
- a public route becomes an oracle for whether an account or a child's seat
  exists;
- an erased person's records are reattached to whoever takes their contact
  next;
- a contact leaks into a log, audit row or notice.

## NFR1 — Anti-enumeration (U2's surfaces)

| ID | Requirement | Verifier |
|---|---|---|
| NFR1.1 | `GET /v1/accounts/already-added?email=` gives one fixed answer, `already_added: false, display_name: null, role: null`, for three cases: an email recorded on no seat, an email held by an account that is linked to a seat but recorded on no seat, and an email never seen. Status and body are byte-identical across the three, and headers match except `X-Correlation-Id` (BR4.2, BR4.3). | Integration test, written first, comparing the three full responses |
| NFR1.2 | Every lookup consumes the ceiling cascade before it reads anything, so a lookup at a ceiling is refused `429 auth.lookup.too_many` whether or not a seat exists (BR4.4). | Integration test: drive the per-contact ceiling to its limit with a recorded email and with an unrecorded one; both are refused identically |
| NFR1.3 | `POST /v1/me/contact` gives the same contentless acknowledgement, for both add and replacement, whether or not another account holds the destination. The `account.contact.taken` refusal comes only after the code is spent (W7 step 4, BR5.1, BR5.4). | Integration test comparing the full responses for a free and a held destination |
| NFR1.4 | A teacher or centre save never tells the teacher who holds a recorded contact. A save is never refused because the phone and the email belong to different accounts (BR2.1). `StudentResponse`, `RosterRowResponse` and `MemberResponse` show the same states for a recorded contact with an account and without one: both read `pending` until the holder decides. **This holds only after BR1.6 lands.** The built `_guardian_state` (`app/batches/service.py:221`) returns `absent` when `guardian_phone` is null and no account is linked, so today an email-only guardian reads `absent` without an account and `pending` with one, which reveals the account. BR1.6 changes the predicate (and the student list's `has_guardian`) to also read `guardian_email`. NFR1.4 depends on that change. | Integration test, written first, comparing the responses for the two cases, with an email-only guardian among them. It fails against the built predicate and passes once BR1.6 is implemented |

## NFR2 — Rate limits

Values are the constants in `app/auth/ceilings.py` as built. U2 reuses every
existing ceiling and adds exactly one scope.

| ID | Requirement | Verifier |
|---|---|---|
| NFR2.1 | The email form of the already-added lookup uses the existing lookup cascade, with the same counters as the phone form: `lk_number_day` 20 per contact per day, keyed on the contact's `rate_key` (`e:` plus its hash for an email, so no raw email is stored); `lk_ip_hour` 30 per hour per /64 (IPv4 /24); `lk_ip48_hour` 100 per hour per /48; `lk_global_hour` alerts at `SHIKKHOKPLUS_GLOBAL_HOURLY_LOOKUPS` (default 1000) per hour and never refuses. Phone and email lookups share the network counters, so one network gets 30 lookups an hour in total, not 30 of each kind. A refusal is HTTP 429 `auth.lookup.too_many`, `retryable: false`, with no `Retry-After` (BR4.4, [Q2 of functional design]). | One test per refusing scope, at the limit and one past it; one test that the global scope alerts and does not refuse; one test that a phone lookup and an email lookup from one /64 draw on one counter |
| NFR2.2 | New scope `contact_chg_day` (15 characters, within `rate_limit_counter.scope_kind` `String(16)`): at most 5 completed contact replacements or removals per account per UTC day (`_window_start` truncates to UTC midnight). The 6th is refused `account.contact.change_limit`. The replacement request only reads the count. The completed change consumes one count through a non-committing consume inside the change's own transaction (BR5.6). Adding a missing contact does not count. Like every other counter, the scope is `NOT_PERSONAL` for deletion, so deleting the account never resets it. | Tests: 5 changes succeed and the 6th is refused, both at the request step and at verify; a failure forced after the consume leaves the count unchanged and the code unspent (named in functional-spec § 5); the scope string fits the column (insert at its length) |
| NFR2.3 | Replace and remove check the password under the existing per-account password ceiling: `pw_fail_id_hour`, 10 failures per hour on the `acct:` key that `change_password` uses. At the ceiling the answer is `auth.password.too_many_attempts` (409) (BR5.2). | Test: 10 wrong passwords on remove, then the 11th refused by the ceiling even with the right password |
| NFR2.4 | Replacement codes go through the existing send ceilings unchanged: per destination 3 per hour and 5 per day; per /64 10 per hour; per /48 50 per hour. The SMS code uses the budget the contact code uses today, and an emailed code uses `em_global_day` (`SHIKKHOKPLUS_GLOBAL_DAILY_EMAIL`, default 1000). The removed-contact notice uses the same budget as the code for its channel, and a budget refusal means the notice is not sent (BR5.9). Because of NFR2.2, one account can cause at most 5 notices a day. | Tests: a replacement request at the destination's hourly limit is refused as today; a notice with its budget exhausted is not sent and the change still succeeds |
| NFR2.5 | A failed replacement verify (wrong code, no code bound to this account, or another account's code) counts under the existing verify-failure scopes: `vf_ip_hour` 20, `vf_ip48_hour` 60, `vf_global_hour` default 300. It records an attempt only against the row this account selected (BR5.3). | Test, written first, with two accounts: a verify using the other account's code records no attempt on that account's row and increments `vf_ip_hour` |
| NFR2.6 | A breach of `lk_global_hour` must be identifiable from the log line. Today `fire_ceiling_alert` logs `extra={"scope": ...}`, but `scope` is not in `STRUCTURED_FIELDS` (`app/logging_setup.py`), so the printed line reads only "sms ceiling breached". U2 adds `scope` to `STRUCTURED_FIELDS`. | Formatter test: a record with `scope` prints `scope='lk_global_hour'` |

## NFR3 — Privacy and authorization boundary

| ID | Requirement | Verifier |
|---|---|---|
| NFR3.1 | **Erasure blocks relinking (review-02 R-09, [Q2]).** A seat link whose holder erased their account is never linked again by ContactMatching, by a teacher save or by the already-added lookup, whoever later verifies or records that contact. The built deletion does not meet this. `delete_account` (`app/governance/deletion.py:399-421`) deletes the account row and relies on `ON DELETE SET NULL`, and nothing sets a marker when an account is erased. The only code in `app/` that writes the markers is seat creation, which copies a marker that already exists on a sibling seat (`app/students/service.py:498-541`). Only tests set a marker in the first place. The existing phone link statements (`app/accounts/service.py:187-208`) would therefore relink an erased seat today, and U2's email statements would too. **This is a requirement on U2**, because U2's matcher is what would do the relinking. U2 changes `delete_account` so that, in the deletion's single transaction: (1) right after the unlocked read that finds the account, and before the destination-scoped deletes or any other row lock, it takes the account key, re-reads the account row, and takes the key of every contact it now holds, in the lock order of reliability NFR4.2 (LO-1 and LO-3). The `phones` and `emails` sets that drive the destination-scoped deletes are **recomputed from that re-read**, together with the requested destination, so a contact added between the first read and the key (W5) is deleted as well. If the account no longer exists once the key is held (a concurrent deletion finished first), deletion is a **no-op success**: it takes the built absent branch, deleting the requested destination's scoped rows, committing, and returning `existed=False`. (2) After the destination-scoped deletes and before any legacy statement, it selects every `enrollment` row whose `student_account_id` or `guardian_account_id` is the account, `ORDER BY id FOR UPDATE`. (3) It sets `student_relink_blocked_at = now()` where the student link is the account and `guardian_relink_blocked_at = now()` where the guardian link is the account, only where each is still null. (4) It locks the account's live `owner_member` rows `ORDER BY id FOR UPDATE`. (5) It continues as built, with the account row deleted last. The whole function is inside reliability NFR4.3's bounded retry. | Integration tests, written first (the authorization predicate holds), through **both** deletion routes: every seat linked to the account, in either role, has its marker set and its link null; a new account that signs up with the erased phone links none of them, and neither does an existing account that adds the erased email; an unrelated unlinked seat recording the same contact *is* linked (BR3.5, so the block is per link and not per contact); a seat the account never held is untouched; the email form of the lookup answers false for a blocked seat; **add-then-delete race**: account A adds email E (W5 held open past the deletion's first read), then the deletion of A completes, and no `otp_request` or `pending_signup` row for E survives; **vanished account**: two deletions of A interleave and the second returns `existed=False` with no error |
| NFR3.2 | Deleting an account also deletes every `otp_request` row of purpose `contact_replace` whose `requested_by_account_id` is the account, before the account row goes. Without this, that row would keep a destination the account typed beside a code after `SET NULL` cleared its requester. The FK's `ON DELETE SET NULL` stays as a backstop. The deletion scoping map and the disposition note for `otp_request` name the second column, so `test_deletion.py`'s completeness checks still describe what deletion reaches. | Integration test: an account with a pending replacement code to destination D is deleted; no `otp_request` row for D with that requester remains |
| NFR3.3 | `student_email`, `guardian_email` and `invited_email` are teacher-written fields (BR1.4, FR6.3). They appear only in an explicit allowlist of response schemas: `StudentResponse`, `RosterRowResponse` and `MemberResponse`. They are added to the admin contract's forbidden-field list. No account's own `email` is ever read into or written from them. | A schema-walk test over the generated OpenAPI document, in the style of the existing privacy gate: any response schema outside the allowlist that carries one of the three names fails CI. The admin forbidden-field test covers the new names |
| NFR3.4 | No phone number or email address (teacher-recorded, invited, looked up, or an account's own, old or new) appears in any log line, audit row, notice body or error envelope written by U2 code. `CONTACT_REPLACED` and `CONTACT_REMOVED` carry only the account id and the correlation id (BR5.11, team.md: secrets leak through logs). | A sentinel test. Each U2 workflow (W1 to W9 and deletion) runs with distinctive sentinel contacts, under `caplog` at DEBUG. The test asserts that no sentinel appears in any captured record (message or `extra`), in any `auth_audit_log` row, or in any error body |
| NFR3.5 | The removed-contact notice carries no username, no new contact, no account id and no code. It is one fixed server template per language, Bangla and English (BR5.9). | Test that renders both templates for both channels and checks them against the forbidden content |
| NFR3.6 | Every U2 integration test runs as the restricted application role `shikkhok_app`, behind the existing superuser and row-level-security meta-check. CI asserts that the integration suite ran, not that it skipped (team.md, project.md Mandated). `pg_advisory_xact_lock` needs no extra privilege, so U2 grants nothing new. | The existing meta-test and the CI ran-not-skipped assertion. No U2 test opens its own superuser connection (checked in review) |
| NFR3.7 | Authorization controls for contact changes, each with a test written first: the password is required for replace and remove (BR5.2); a replacement code is selected by its requester as part of row selection (BR5.3); the last contact cannot be removed (BR5.5); a contact on the administrator allowlist cannot be removed or replaced, and this is checked at the request and again at verify (BR5.13); removing or replacing a contact never unlinks anything (BR5.7). | The named tests in functional-spec § 5, as the restricted role |
| NFR3.8 | `DeletionResult.rows_deleted` reports how many seat links the deletion blocked, as `enrollment_relink_blocked`, so the deletion's own record shows the step ran. | Asserted in the NFR3.1 tests |

Consequences of NFR3.1, recorded so they are not mistaken for regressions:

- From U2 onwards, `_is_removable` (`app/batches/service.py:246-250`) and the
  edit refusal `student.number_erased` (BR2.4) see real markers for the first
  time. A seat whose holder erased their account can no longer be removed by
  the teacher, and its contact on that link can no longer be edited. This is
  what the built rules already intend; until now nothing triggered it.
- Seats whose holder erased their account **before** U2 ships carry no marker,
  and nothing records which they are. They cannot be backfilled. The product
  has no production deployment (unreleased; closed testing on staging), so the
  exposure is limited to staging data. This is accepted, and the deploy notes
  for U2 say so.
- `app/governance/deletion.py` is also edited by U1, for the username hold
  (FR10.2). C3's list of shared files does not name it. Whichever unit merges
  second rebases, in the same way as the files C3 does list. This file asks
  for it to be added to that list.

## NFR4 — Test-first (security-relevant subset)

The full test-first set and the concurrency tests are in
`reliability-requirements.md` (NFR4.1 to NFR4.6). The security point is
NFR4.1: every BR marked `test_first: true`, together with NFR1.1, NFR1.4,
NFR2.5 and NFR3.1, is a failing test committed before its implementation on
the Bolt branch.

## NFR6, NFR9 — Contract and compatibility (security-relevant)

- The responses U2 changes may gain only the fields C2 names. NFR3.3's
  allowlist is the mechanical guard against a new field that leaks a
  contact.
- New refusal keys (`student.email.taken`, `account.contact.last_one`,
  `account.contact.change_limit`, `account.contact.password_required`,
  `account.contact.admin_locked`, and `auth.lookup.too_many` if U2 merges
  before U1) are message keys, never English text. See
  `reliability-requirements.md` NFR9.

## Data protection

- At rest: the new columns live in the existing encrypted PostgreSQL storage
  (project.md: children's data encrypted at rest). U2 adds no store.
- In transit: unchanged (TLS at the edge). U2 adds no outbound integration
  beyond the existing SMS and email gateways that the notice uses.
- Retention: teacher-recorded emails follow their row's existing disposition
  (`student`, `enrollment` and `owner_member` keep the dispositions they have
  for the recorded phones). The relink marker is a timestamp on a retained
  seat and names nobody. The `enrollment` disposition note in
  `app/governance/dispositions.py` gains one sentence saying the erasure time
  is kept on the seat. If its text feeds the generated privacy policy, the
  policy is regenerated (`scripts/generate_privacy_policy.py`) in the same
  change.

## Assumptions & Open Questions

- The teacher-facing responses stop revealing whether a recorded contact has
  an account only once BR1.6 changes `_guardian_state` and `has_guardian` to
  read `guardian_email`. Today an email-only guardian with no account reads
  `absent` (`app/batches/service.py:221`). NFR1.4's test pins the change.
- [assumption] The removed-contact notice SMS uses the same `SendBudget` as
  the contact code sent to the same channel (functional-spec Assumptions).
  Code generation names the member explicitly.
- Concern, not a question, recorded for the next reader: the approved state
  machine (functional-spec § 3.1) moves a link to RelinkBlocked on erasure even
  when it was only `pending`. A seat a teacher mis-addressed, which the wrong
  person then erased, therefore becomes permanently unremovable and
  uneditable on that link. NFR3.1 implements the approved design as written.
  Changing it would be a functional-design decision.
- Open questions: None. [Q2] settles the erasure mechanism.

## Sources

- Initial description: the change request in `project-description.json`. [desc]
- Requirements NFR1, NFR2, NFR3, NFR4, NFR6, NFR9 and FR6.3, FR6.7, FR8, FR10:
  `inception/requirements-analysis/requirements.md`.
- Functional design (approved): `functional-spec.md` (W1 to W9, § 5, § 7),
  `rules.md` (BR1.4, BR2.1, BR2.4, BR3.5, BR3.6, BR4.2 to BR4.4, BR5.2 to
  BR5.13); review `reviews/review-02.md` R-08 to R-11.
- Contracts: `inception/contract-design/contract-summary.md` C2, C3 and the
  2026-11-14 direction.
- Code read: `app/governance/deletion.py`, `app/db/models.py` (enrollment links
  and markers, `auth_audit_log`), `app/accounts/service.py`,
  `app/accounts/contact.py`, `app/auth/ceilings.py`, `app/audit/log.py`,
  `app/logging_setup.py`, `app/request_scope.py`, `app/batches/service.py`.
- Answers: [Q1] to [Q5] in `nfr-requirements-questions.md` ([Q5] supersedes
  [Q1]'s no-retry clause).
- Review of this stage: `reviews/review-01.md` R-04 and R-05.
- Rules: team.md (Testing Posture, Deployment: secrets in logs; Code Style:
  error handling), project.md Forbidden and Mandated.
