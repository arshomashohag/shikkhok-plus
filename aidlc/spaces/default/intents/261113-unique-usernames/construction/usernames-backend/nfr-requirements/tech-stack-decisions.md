# Tech Stack Decisions — usernames-backend (U1)

Intent `261113-unique-usernames`, unit U1 (kind: service). Brownfield: the
stack is fixed by the built backend (team.md Code Style; the code knowledge
base's `technology-stack`). U1 adds **no dependency, service, secret or
infrastructure**. Each row below is a choice U1 makes within that stack, with
the NFRs it serves.

| Concern | Decision | Rationale | Alternatives rejected | Serves |
|---|---|---|---|---|
| Language and framework | Python 3.12, FastAPI and Pydantic v2, as built. The new module `app/accounts/usernames.py` sits inside the existing `app.accounts` strict mypy island and coverage list | No new package, so no change to the coverage list or the strict islands (unit-of-work U1 note) | A new `app.usernames` package (it would need a coverage-list entry and a strict-island override, for no gain) | NFR5.1, NFR5.2 |
| Uniqueness | Plain `UNIQUE` on `account.username_key`, with `CHECK`s for both-or-neither and shape (ADR-001, BR1.9) | A unique index is the race-proof backstop, and it is what the plan test probes | A functional index on `lower(username)` (OQ2, decided at Domain Design) | NFR4.6, NFR8.2 |
| Serialising claims | PostgreSQL transaction-scoped advisory locks through U2's `lock_keys`, with the `username` namespace appended last | Reuses the one built lock-order helper. Correct across the two Uvicorn workers | Row locks on a name table (none exists before the claim); `SERIALIZABLE` (heavier, and needs retries on every path) | NFR4.2 |
| Retry | U2's `run_with_retry` (standard library), for first choice and rename only | Built and tested; nothing new to maintain | A retry library (a new dependency for a dozen lines, U2's tech-stack decision) | NFR4.3 |
| Rate ceilings | Twelve new `ScopeKind` members in the existing `rate_limit_counter` table, through the built `_consume`, `_peek` and `_increment` | Datastore-backed counters are correct across workers (the `ceilings.py` docstring). No column or index change | Redis or an in-process limiter (new infrastructure, or wrong with two workers); a CAPTCHA service (a third-party SDK on a children's-data app, project.md Mandated: check every dependency against the forbidden-identifier set) | NFR2.1 to NFR2.4 |
| Digests | Standard library `hmac` and `hashlib`: HMAC-SHA256 under the existing `SHIKKHOKPLUS_OTP_HMAC_KEY`, with purpose prefixes `username-hold:v1:` and `username-counter:v1:` | One secret, already provisioned and already outside the database. The prefixes keep the three digest uses apart | A new secret (a fourth rotation runbook nobody has written yet, for separation the prefixes already give); unkeyed SHA-256 for counters (reversible with a dictionary, R-04) | NFR3.2, NFR3.3 |
| Transport of the candidate | JSON request bodies for both lookups (`POST`) | Keeps usernames out of the URL, and so out of nginx's default access log, with no infrastructure change | Changing the nginx `log_format` (an infrastructure change that needs the host replaced); keeping `GET` with a stated exception | NFR3.5 |
| Latency evidence | `EXPLAIN` and statement-count tests in pytest; one manual `httpx` timing run on staging (`httpx` is already pinned) | Proves the mechanism in CI and the number by hand, as project.md requires | Locust or k6 (a new tool, and the ceilings stop volume from one host anyway); a CI timing assertion (that would discharge a performance obligation with a correctness test) | NFR8.1 to NFR8.3 |
| Tests | pytest against real PostgreSQL 16 via testcontainers, as `shikkhok_app`, as built | Advisory locks, `CHECK`s, unique violations and `SET NULL` are the behaviours under test | SQLite (it emulates none of them) | NFR3.1, NFR4.1 |
| Alerting | The built `CRITICAL:` metric filter and alarm | It already matches any scope's `CRITICAL` line | A new alarm per scope | NFR2.10 |

## Supply chain

No new direct or transitive dependency, so no SDK admission note is needed
(project.md Mandated). The lockfile and CVE-scan work is the separate
pre-D1 practice in team.md and is not this unit's.

## Assumptions & Open Questions

- Open questions: None.

## Sources

- team.md Code Style (backend, error handling), Testing Posture and
  Deployment; project.md Mandated.
- Domain design `decisions.md` ADR-001, ADR-002, ADR-003, ADR-007.
- U2's `tech-stack-decisions.md` (retry with the standard library).
- Code read: `app/db/advisory.py`, `app/db/retry.py`, `app/auth/ceilings.py`,
  `app/auth/hashing.py`, `Makefile`, `infra/modules/app/user_data.sh.tftpl`,
  `infra/modules/app/monitoring.tf`.
