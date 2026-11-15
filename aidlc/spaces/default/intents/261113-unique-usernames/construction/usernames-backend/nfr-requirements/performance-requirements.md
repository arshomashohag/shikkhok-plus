# Performance Requirements — usernames-backend (U1)

Intent `261113-unique-usernames`, unit U1 (kind: service). IDs inherit
inception NFR8 (responsiveness). Sign-in timing equality is a security
property and is in `security-requirements.md` NFR1.2. Growth and concurrency
are in `scalability-requirements.md` (NFR8.5 onwards).

project.md forbids discharging a performance obligation with a correctness
test, and requires the artifact to say so plainly when the verifier is
manual. The approach is U2's [Q3], for the same reasons. Automated CI checks
prove the mechanism (index use, a constant statement count). The number
itself comes from one manual timed run on staging. The lookup ceilings (30 an
hour per /64) also rule out load-testing from one host at volume, and the
repository has no load tool. `httpx` is already a pinned dependency.

## Targets

| ID | Requirement | Verifier |
|---|---|---|
| NFR8.1 | Both availability lookups, `POST /v1/accounts/username-availability` and `POST /v1/me/username-availability`, answer within **300 ms at the 95th percentile**, measured end to end from a client through CloudFront to staging under normal load. This is what keeps the live check usable while typing (NFR8). | **Manual.** One timed run with a small `httpx` script: 25 public lookups in one clock hour, and 25 authenticated lookups in the next, so both stay under `un_lk_ip_hour`'s 30. The names are a mix of available, unavailable, invalid and reserved. The p95 of each set of 25 is recorded in the Bolt's PR. **Nothing automated discharges the 300 ms figure.** |
| NFR8.2 | Every read a lookup, a claim or a username sign-in makes is index-backed. `account` by `username_key` uses the unique index on that column. `username_hold` by `key_digest` uses its primary key. The counter upserts use the existing `(scope_kind, scope_value, window_start)` unique index. | A CI test runs `EXPLAIN` on each statement with sequential scans disabled, and asserts an index or primary-key scan on the named index. This proves the mechanism, not the number |
| NFR8.3 | A lookup issues a constant number of statements whatever the size of the tables: no loop over accounts or holds, and no N+1. | A CI statement-count test (SQLAlchemy `before_cursor_execute`). The public and the authenticated lookup issue the same count against a database seeded with 1 account and 1 hold, and one seeded with 1,000 of each. The statements of the authentication dependency are excluded from the authenticated count. This proves the mechanism, not the number |
| NFR8.4 | A username sign-in costs the same as a phone or email sign-in, plus one indexed read (NFR8.2) and the Family D peeks. Its time is dominated by the one scrypt evaluation it shares with them (security NFR1.1). U1 sets no new latency target for sign-in, rename or first choice. They inherit the backend's current behaviour, and rename adds one scrypt for the password check (BR6.1). | NFR8.2's plan test for the username read. The timing comparison is security NFR1.2's manual run |

## Resource constraints

- No new process, worker, cache or host. Two Uvicorn workers on the one
  Lightsail host (`Dockerfile` CMD), as built.
- Each lookup writes three counter rows through committing upserts (Family A
  plus the global count). That is the same write cost per request as the
  built already-added lookup.
- Spend stays under USD 50/month (project.md Mandated). U1 adds nothing that
  is billed.

## Assumptions & Open Questions

- [assumption] "Normal load" on staging means closed-testing traffic, with no
  other test run at the same time. The manual run records the time of day.
- Open questions: None.

## Sources

- Requirements NFR8 and NFR1: `inception/requirements-analysis/requirements.md`.
- Functional design: `functional-spec.md` W3 to W5, § 1.2.
- U2's [Q3] (`construction/contacts-and-invites-backend/nfr-requirements/nfr-requirements-questions.md`)
  for the verifier approach.
- Rules: project.md Forbidden ("never discharge a performance or layout
  obligation with a correctness test") and Corrections 2026-10-23 (say
  plainly when nothing automated discharges an obligation).
