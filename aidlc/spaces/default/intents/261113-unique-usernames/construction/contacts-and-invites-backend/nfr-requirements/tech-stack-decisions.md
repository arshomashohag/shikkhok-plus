# Tech Stack Decisions — contacts-and-invites-backend (U2)

Intent `261113-unique-usernames`, unit U2 (kind: service). Brownfield: U2
extends the existing backend and adds **no new runtime dependency** and no
new development dependency. Every choice below is either the built stack or a
built-in feature of it.

## Decisions

| Concern | Decision | Why | Alternatives rejected |
|---|---|---|---|
| Language and framework | Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2.1 (versions as pinned in `pyproject.toml` and the lockfile) | The built backend. U2 is endpoints and statements inside it | None considered: changing the stack is out of scope |
| Database | PostgreSQL 16, one Alembic chain, one new forward-only revision (reliability NFR7.1) | The built database, with partial indexes, `CHECK` and row locks | None |
| Serialising a save and a match for one contact; serialising one account's contact changes | PostgreSQL transaction-scoped advisory locks, `pg_advisory_xact_lock(hashtextextended(<key>, 0))`, taken through one helper in the order of reliability NFR4.2 | Built in, already used by `replayed_student`, released automatically at commit or rollback, correct across application instances, bounded by the engine's `lock_timeout` | `SELECT ... FOR UPDATE` on a placeholder row (needs a table of contacts that does not exist); `SERIALIZABLE` isolation with retries ([Q1] C: more aborts, and every transaction would need the retry that NFR4.3 confines to deadlocks and serialization failures); an in-process lock (wrong with more than one instance, NFR8.9); Redis (new infrastructure against the USD 50 ceiling) |
| Contact matcher location | One new module, `app/accounts/matching.py`, holding `match_contact`, `lock_contact` and the key helper. The seat and invitation link statements stay with their owners (StudentRoster, CentreMembership), as the functional design assigns them | `app.accounts.*` is already a mypy strict island (`strict = true`, `disallow_any_explicit = true`) and already in the `make test` `--cov` list, so no package is added and no strictness is lost | A new `app.contacts` package: it would need its own strict override and `--cov` entry, for no benefit |
| Change ceiling | One new `ScopeKind` member, `CONTACT_CHANGE_DAILY = "contact_chg_day"`, with a non-committing consume beside the existing committing cascade (BR5.6) | Reuses `rate_limit_counter` and its atomic upsert-and-compare | A counter column on `account` (a second ceiling mechanism, and a write to a row other paths lock) |
| Error mapping and retry | The existing five-class taxonomy and `request_scope` mapping. New keys are `ConflictError` or `ValidationError`. `40001` and `40P01` are retried by one small in-house wrapper, at most 2 retries with jittered backoff, around U2's write units of work and `delete_account`; whatever is still failing after that, and `55P03`, stays `TransientError` (reliability NFR4.3, [Q5]) | team.md Error handling ("a serialization failure is a bounded transaction retry"). The wrapper is a few lines on `random` and `time`, standard library only | A retry library such as `tenacity` (a new dependency for about ten lines); a U2-specific exception handler |
| Notices | The existing SMS and email gateways and their send budgets, called after commit | Nothing new to admit | A queue or outbox for notices (best-effort by design, BR5.9) |
| Tests | pytest, testcontainers PostgreSQL 16, run as the restricted role. Interleaving tests use two sessions on two connections, with the first transaction held open by a `threading.Event`. Hypothesis is not needed | All already pinned. Real PostgreSQL is required for row locks, advisory locks, partial indexes and `CHECK` behaviour | SQLite (emulates none of it, team.md); `pytest-xdist` or `pytest-timeout` (new dependencies for what a held `Event` and `lock_timeout` already bound) |
| Latency measurement | A throwaway `httpx` script run once against staging, with its output in the PR (performance-requirements) | `httpx==0.28.1` is already pinned. [Q3] | Locust or k6 (new dependency for a one-off; [Q3] C) |

No new third-party dependency means no SDK admission note and no
forbidden-identifier check (project.md Mandated). Both are needed only for a
new dependency, and there is none.

## Quality gates this unit must keep (NFR5, NFR6)

| ID | Requirement | Verifier |
|---|---|---|
| NFR5.1 | Backend coverage stays at or above the 80% floor (`make test`, `.coveragerc-backend`), with no decrease from the figure on `main` at the Bolt's branch point. The floor is not weakened to pass (project.md Forbidden). | `make test` in CI; the PR states the before and after figures |
| NFR5.2 | `app/accounts/matching.py` carries **100% branch coverage**, gated in `make test` by a second `coverage report --include='app/accounts/matching.py' --fail-under=100 --rcfile=.coveragerc-backend` pass. Branch data is already collected (`branch = true`). This mirrors the money module's gate ([Q4]). | `make test` in CI |
| NFR5.3 | Any new backend package joins the explicit `--cov` list. U2 plans none, and `test_coverage_scope.py` fails if one appears without an entry. | Existing test |
| NFR6.1 | `/v1` changes are additive, with exactly two exceptions, both recorded as the person's 2026-11-14 direction: `MemberInviteRequest.phone` becomes optional, and `MemberResponse.phone` becomes nullable. The current Android and web clients (U3, U4) read the phone as optional. | Schema-diff gate (NFR9.1), plus review of the diff against C2 |
| NFR6.2 | The phone forms of the already-added lookup, contact add and seat linking keep their behaviour. Their existing tests pass **without modification**, except where a rule changes the expected value: the 409 to 429 change on the lookup refusal (BR4.4), and the erased-seat expectations now that deletion sets markers (NFR3.1). Each such change is named in the PR. | The existing suite; the PR lists every modified pre-existing test and the rule that changed it |

## Assumptions & Open Questions

- [assumption] `app.accounts.*` stays a strict island. It is configured today
  in `pyproject.toml`.
- Open questions: None. [Q1], [Q3] and [Q4] settle the choices that needed
  judgement.

## Sources

- Code read: `pyproject.toml` (pinned dependencies, mypy overrides including
  `app.accounts.*`), `Makefile` (`test` target, `--cov` list, money gate),
  `.coveragerc-backend` (`branch = true`), `app/students/service.py`
  (`replayed_student` advisory lock), `app/auth/ceilings.py`, `app/db/session.py`.
- Requirements NFR5, NFR6 and NFR9: `inception/requirements-analysis/requirements.md`.
- Contracts: `contract-summary.md` C2, C3 and the 2026-11-14 direction.
- Answers: [Q1], [Q3], [Q4] and [Q5] in `nfr-requirements-questions.md`.
- Rules: team.md (Testing Posture: coverage, real PostgreSQL; Code Style:
  error handling), project.md Forbidden and Mandated.
