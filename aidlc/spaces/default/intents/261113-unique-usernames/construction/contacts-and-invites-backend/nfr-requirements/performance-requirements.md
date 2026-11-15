# Performance Requirements — contacts-and-invites-backend (U2)

Intent `261113-unique-usernames`, unit U2 (kind: service). Inception NFR8
sets a responsiveness target for U1's availability lookup only (300 ms p95 on
staging, so a live check is usable while typing). U2 has the same kind of
interaction: the sign-up form calls the already-added lookup as it renders.
This file therefore carries U2's latency targets as NFR8.x, holds U2's public
lookup to NFR8's own figure, and sets one figure for U2's authenticated writes.

**What discharges these targets ([Q3]).** Two automated CI checks prove the
mechanism: index usability (NFR8.3) and a constant statement count (NFR8.4).
The latency numbers themselves (NFR8.1, NFR8.2, NFR8.7) are discharged by one
timed, manual run on staging, and **nothing automated discharges the latency
figures** (project.md: NEVER discharge a performance obligation with a
correctness test; Corrections 2026-10-23).

## Targets

| ID | Requirement | Verifier |
|---|---|---|
| NFR8.1 | `GET /v1/accounts/already-added` answers within **300 ms at p95** on staging, **for each form separately**: 25 email-form samples and 25 phone-form samples, run in different clock hours (run plan hours 1 and 2). Each form stays under the shared per-/64 lookup ceiling of 30 per hour, with 5 to spare, and each sample uses a distinct contact, so the per-contact ceiling of 20 per day is never approached. Over 25 samples, p95 is the 24th value in ascending order, the second-slowest. Any 429 voids that form's sample, which is repeated in a later hour. | Manual staging run (run plan below); results in the Bolt PR. **Manual: nothing automated discharges this figure.** |
| NFR8.2 | U2's authenticated writes on staging. (a) `POST /v1/students` and `PATCH /v1/students/{id}` with both emails set, and `POST /v1/centre/members` by email: **500 ms at p95**, over 100 requests each at no more than 2 requests per second (no per-request ceiling applies; every sample uses distinct emails). (b) `POST /v1/me/contact/verify` as a replacement (including `match_contact`), and `POST /v1/me/contact/remove`: the **maximum of 8 samples each** must be at most 500 ms. Eight is the most the real ceilings allow in one clock hour from one /64 (run plan hours 3 and 4), so the maximum stands in for a p95 that 8 samples cannot support. | Manual staging run; results in the Bolt PR. **Manual: nothing automated discharges this figure.** |
| NFR8.3 | Every statement U2 adds that finds rows by a recorded email can use a partial index: the matcher's student-link, guardian-link and invitation statements, the email lookup, the student-email uniqueness check and the live-invitation check. With `SET LOCAL enable_seqscan = off`, each statement's `EXPLAIN` names the intended index (the index list is scalability-requirements NFR8.8). | Automated integration test in CI. It proves the index is **usable**, not that the query is fast |
| NFR8.4 | `match_contact` issues a constant number of SQL statements for one contact, whatever the number of matching rows: at most one advisory-lock statement, plus one set-based `UPDATE` per link kind (student, guardian, invitation). No per-row loop and no N+1 reads. | Automated test: count statements with a SQLAlchemy `before_cursor_execute` listener for matches of 1 and of 20 seats, and assert the counts are equal |
| NFR8.5 | No U2 transaction does network I/O while it holds an advisory key or a row lock. The notice goes out after commit (reliability NFR4.7), and the replacement code is delivered as in today's issue path. | Automated test: gateway stub asserts it is not inside a transaction when called |
| NFR8.6 | `match_contact` adds at most **50 ms** to the verify transaction that calls it, at the design-point volume (scalability-requirements). | Part of the manual staging run: the NFR8.7 statement timings summed. **Manual.** |
| NFR8.7 | On staging, each statement in NFR8.3 runs in at most **25 ms** (`EXPLAIN (ANALYZE, BUFFERS)` execution time), at the design-point volume or on a local PostgreSQL 16 seeded to it if staging holds less. | Manual run; plans and timings pasted into the Bolt PR. **Manual.** |

## The manual run

**No ceiling override.** The ceilings are module constants in
`app/auth/ceilings.py`, not configuration, so staging runs with the real
values. The plan below is sized to them. It needs one source host on one
/64 (IPv4 /24), four clock hours, and no other OTP, sign-up or lookup traffic
from that address during the run.

| Hour | Measures | Accounts and contacts | The ceiling that sizes it |
|---|---|---|---|
| 1 | Email-form lookup, 25 samples | 25 distinct unrecorded and recorded emails, mixed | `lk_ip_hour` 30 per /64 per hour |
| 2 | Phone-form lookup, 25 samples | 25 distinct numbers | Same counter, reset by the new hour |
| any | Teacher writes, 100 each of student create, edit and centre invite | 1 teacher account and 1 centre-manager account; 300 distinct recorded emails | None per request; at most 2 requests per second |
| 3 | Replacement verify, 8 samples | 2 accounts, R1 and R2, each making 4 phone replacements to 8 distinct new numbers. Codes are read from the staging SMS outbox | Send `PER_IP_HOURLY` 10 per /64 per hour (8 used, 2 spare); per destination 3 per hour (1 used each); `contact_chg_day` 5 per account per day (4 used each) |
| 4 | Removal, 8 samples | 2 more accounts, M1 and M2, each holding a phone and an email. Each runs 4 cycles: remove the phone (measured), then add a **fresh** number by code (not measured), so that it can remove a phone again | 8 add-code sends against the 10 per /64 per hour; a fresh number for each add keeps every destination at 1 per hour; 4 removals each against 5 per account per day |

Totals: 4 contact-change accounts, 1 teacher, 1 centre manager, 16 distinct
new numbers, and about 30 SMS against the sign-in SMS budget (codes plus
notices), which is well under `SHIKKHOKPLUS_GLOBAL_DAILY_SMS`. If two source
hosts on different /64s are available, hours 1 and 2, and hours 3 and 4, may
run in parallel, one host each.

- A short script uses `httpx`, which is already pinned, and records per-request
  wall time and status.
- It runs against staging after the U2 migration and before the Bolt merges.
- The latency sample is taken under ordinary staging load (closed-testing
  traffic, no synthetic background load).
- Its output (sample counts, p50, p95, max, and any 429s) is pasted into the
  Bolt's PR.
- The script is not added to CI, because the public lookup's ceilings make a
  volume run from CI impossible by design. It lives in the PR, not in the
  repository, and is not a maintained tool.

## Resource constraints

- No new process, cache, queue or container. U2 uses the existing connection
  pool (8 + 4 overflow) and adds at most one connection-held transaction per
  request, as today.
- The new indexes add storage on the order of the email column sizes (at
  most 254 bytes per indexed value) on rows that record an email. This is
  negligible at the design point.
- Infrastructure spend is unchanged, under USD 50 per month (OC-4).

## Assumptions & Open Questions

- [assumption] The 500 ms write figure is set by the agent ([Q3] left the
  choice to it). It is the read figure plus the extra work of a write: one
  to four advisory keys, a seat-row lock, and up to three set-based updates.
  Nothing upstream fixes it.
- [assumption] Staging serves the measurement with no competing deploy or
  migration running.
- Open questions: None. [Q3] settles the verifier.

## Sources

- Requirements NFR8 and NFR2: `inception/requirements-analysis/requirements.md`.
- Functional design: `functional-spec.md` W1 to W9; `rules.md` BR3.1, BR3.8,
  BR4.4 and BR5.9.
- Code read: `app/auth/ceilings.py` (lookup and send ceiling values),
  `app/db/session.py` (pool and timeouts), `pyproject.toml` (`httpx==0.28.1`
  pinned).
- Answers: [Q3] in `nfr-requirements-questions.md`.
- Rules: project.md Forbidden (verifier naming, no correctness test for a
  performance obligation) and Corrections (manual verifier sentence).
