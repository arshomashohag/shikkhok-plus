# Scalability Requirements — contacts-and-invites-backend (U2)

Intent `261113-unique-usernames`, unit U2 (kind: service). This is a small
unit on a small deployment: one backend container and one PostgreSQL 16, with
a staging Lightsail instance in Phase 1 and RDS `db.t4g.micro` Single-AZ in
Phase 2 (team.md Deployment). The goal is narrow: what U2 adds must not turn
into a full-table scan, an unbounded table or an in-process assumption as the
data grows. The IDs inherit NFR8 (responsiveness as data grows) and NFR2
(the ceilings that bound request volume).

## Design point

[assumption] There are no load projections upstream, and the product is
unreleased. U2 is sized for the end of Phase 2's first year:

| Quantity | Design point |
|---|---|
| Accounts | 5,000 |
| Teachers and centres (owners) | 300 |
| `student` rows | 15,000 |
| `enrollment` rows (seats) | 20,000 |
| `owner_member` rows | 2,000 |
| Concurrent in-flight requests | 12 (the pool's 8 + 4 overflow) |
| Contact changes | Bounded at 5 per account per day by NFR2.2 |
| Already-added lookups | Bounded per network by NFR2.1; an alert above 1,000 per hour |

## Requirements

| ID | Requirement | Verifier |
|---|---|---|
| NFR8.8 | The U2 migration adds these indexes, all partial on the email being present: `enrollment(student_email) WHERE student_email IS NOT NULL`; `enrollment(guardian_email) WHERE guardian_email IS NOT NULL`; the unique `student(owner_id, student_email) WHERE student_email IS NOT NULL` (BR1.2); the unique live `owner_member(owner_id, invited_email) WHERE revoked_at IS NULL AND invited_email IS NOT NULL` (BR1.8); and `owner_member(invited_email) WHERE revoked_at IS NULL AND account_id IS NULL AND invited_email IS NOT NULL`, which serves the matcher's invitation statement across centres. These mirror the existing phone indexes (`ix_enrollment_student_phone`, `ix_enrollment_guardian_phone`, `uq_student_owner_phone`, `uq_owner_member_live_phone`). The names follow the existing convention and are fixed by code generation. | The schema-parity test (each index exists in model and migration), plus the CI usability test in performance-requirements NFR8.3 |
| NFR8.9 | Serialisation is correct with more than one application instance. Every lock U2 relies on is a PostgreSQL row lock or a transaction-scoped advisory lock (reliability NFR4.2). U2 uses no in-process mutex, no module-level cache of link targets or contacts, and no cross-request memoisation, in line with team.md's ban on cross-request caching in authorization. | Code check, in review. The interleaving tests already use separate connections, which is how separate instances behave |
| NFR8.10 | U2 adds no table that grows without a bound. The new `contact_chg_day` counters are rows in `rate_limit_counter`, removed by its existing 48-hour expiry like every other scope. `contact_replace` codes are `otp_request` rows, removed by the existing code purge and by deletion (NFR3.2). The new columns grow only with existing rows. | The existing counter and code purge tests continue to pass with the new scope and purpose included (a test seeds one of each and runs the purge) |
| NFR8.11 | Advisory-key contention is per contact and per account, never global. No U2 path takes a key shared across all accounts or all contacts, so two teachers saving unrelated students never wait on each other. | Code check, in review, of the one key helper; an interleaving test asserts two saves for disjoint contacts proceed concurrently (the second does not block while the first is held open) |

The matcher's cost grows with the rows it links, not with table size. That is
defined once, as performance-requirements NFR8.4 (constant statement count)
together with NFR8.8 above (each statement index-driven), and is not
restated here.

## Scaling triggers

Nothing is triggered at the design point. Two signals would reopen this file:

- the manual staging run (performance NFR8.7) shows any NFR8.3 statement above
  25 ms;
- `lk_global_hour` alerts more than once a week in production, which would mean
  lookup volume rather than abuse.

In either case the next step is a measurement, not a cache.

## Assumptions & Open Questions

- [assumption] The design-point figures are the agent's sizing (no upstream
  projection exists). They are generous for a closed-testing product and are
  used only to size indexes and the manual timing run.
- [assumption] The existing purge that removes expired `rate_limit_counter`
  and `otp_request` rows covers every scope and purpose value, not a fixed
  list. NFR8.10's test is what confirms it.
- Open questions: None.

## Sources

- Requirements NFR2 and NFR8: `inception/requirements-analysis/requirements.md`.
- Functional design: `functional-spec.md` § 8 (schema) and § 7; `entities.md`
  (uniqueness rules); `rules.md` BR1.2, BR1.8, BR3.2, BR3.3 and BR4.3.
- Code read: `app/db/models.py` (enrollment indexes at 1189-1213),
  `app/db/session.py` (pool), `app/auth/ceilings.py`,
  `app/governance/deletion.py` (`rate_limit_counter` 48-hour expiry note).
- Rules: team.md Deployment (environments, budget) and Code Style
  (no cross-request caching in authorization).
