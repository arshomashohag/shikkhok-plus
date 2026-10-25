# Reliability Requirements — D1 `signing-up-and-joining`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> D1's reliability surface is two transactions and one migration. The
> migration is the part that cannot be undone, and it runs against live
> staging data.

## Sources

- [upstream] `construction/signing-up-and-joining/functional-design/functional-spec.md` § 5
- [upstream] `construction/signing-up-and-joining/functional-design/rules.md` — BR3.3, BR4.3, BR6.1
- [prior] NFR5, NFR13 of `261016-shikhokplus-tuition-app`
- [team] Deployment practice, 2026-10-22
- [code] `app/errors`, `app/gateway`, read 2026-10-23

---

## Availability

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR18.1 | D1 states no availability target of its own and inherits the product's | Phase 1 is a single Lightsail host with a recreate-style deploy and an accepted short restart window | [team: Deployment] [NFR7] |
| NFR18.2 | Deploys carrying D1 are scheduled outside Bangladesh classroom hours | The existing practice; D1 gives no reason to change it | [team: Deployment] |

**D1 is not latency- or uptime-critical in the way the attendance path is.**
A signup that fails is retried by a person who is already looking at the
screen. That is worth stating because the *migration* in the same unit is the
opposite, and the two should not inherit one another's posture.

---

## The migration

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR19.1 | The migration is forward-only and backward-compatible, and runs as a distinct logged step before the new container serves traffic | Never as a side effect of application start | [team: Deployment] |
| NFR19.2 | The backfill is **conditional**, never a column default | `accepted` where the link names an account, `pending` otherwise | [ADR-013] [spec § 5] |
| NFR19.3 | A verified `pg_dump` to S3 precedes any production run of this migration, with object existence and non-trivial size asserted after upload | An unverified upload is not a backup | [team: Deployment] |
| NFR19.4 | The migration is rehearsed on staging against realistic data before production | Staging exists in Phase 1 for exactly this | [team: Deployment] |

**NFR19.2 is a reliability requirement, not only a correctness one.** A plain
`DEFAULT 'pending'` would withdraw a working lens from every student already
signed in — four units are merged with live staging data, so the failure mode
is a person opening the app and finding their batches gone. That is an
availability incident caused by a schema default, and it is recoverable only
by a second migration after the complaint.

**What cannot be rolled back.** Rollback is redeploying the previous image
tag, which does not revert a migration. The columns are additive and
`NOT NULL` after backfill, so the previous application version continues to
work against the new schema — that is what makes this forward-only migration
safe to pair with a tag rollback.

---

## Transactional integrity

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR19.5 | Account, profile and the optional owner row are created in **one transaction** | A failure in any leaves none of them | [BR3.3] [BR4.1] |
| NFR19.6 | A signup whose OTP dispatch fails leaves the account created | The code is retriable through the existing OTP path; the account is not re-created | [BR4.3] |
| NFR19.7 | No D1 write path resets a decision column | A decision moves only by its holder's accept or decline | [BR6.1] |

**NFR19.6 is the deliberate asymmetry in BR4.3's ordering.** Creating the
account first means a gateway failure leaves a real account with no code sent.
That is the better failure: the person signs in by requesting a new code,
through a path that already exists and is already rate-limited. The
alternative — account creation conditional on a successful send — makes a
third party's outage into a failure to exist.

---

## Failure modes

| Failure | Behaviour | Requirement |
|---|---|---|
| SMS gateway times out | Recorded as `unknown`, not `failed`; one attempt, no automatic retry | [team: Error handling] |
| SMS ceiling breached | `ConflictError`, non-retryable; the person is told, not silently dropped | [NFR12.6] |
| Duplicate signup on one number | The uniqueness constraint reports it; the person is directed to log in | [BR4.4] [NFR6.23] |
| Database connection fails mid-signup | Fail fast; the transaction leaves nothing partial | [NFR19.5] |
| Audit write fails | **Silent to the user, loud to the operator** — the log must not fail the authentication it records | [code: `audit/log.py`] [NFR25.3] |
| Migration fails partway | Alembic's own transaction; the backup from NFR19.3 is the floor | [NFR19.3] |

**The audit-write failure mode is the one with a trap in it.** The component
fails open by design so it cannot break authentication, which makes it
suppressible by someone who can cause write failures. That is only acceptable
because the failure alerts — so the alert is a requirement, not a nicety
(NFR25.3).

---

## Graceful degradation

| Dependency | Tier | Degradation |
|---|---|---|
| PostgreSQL | **Critical** | None. Signup and acceptance are writes; without the database there is nothing to degrade to. |
| SMS gateway | **Critical for completion, not for creation** | The account exists; the code is retriable. [NFR19.6] |
| FCM | Not used by D1 | D3 owns the adapter. |

**There is no offline path in D1.** NFR5 permits offline writes for the
mid-class path only — the topic log and attendance, which are D4's. Signup and
acceptance require connectivity and fail with an explicit retry prompt that
preserves what was typed. A queued signup would be an account that may or may
not exist, which is worse than an error message.

---

## Assumptions & Open Questions

- **Assumed**: the existing post-deploy smoke set covers D1 adequately once
  signup is live. It already exercises OTP issue and verify and authenticated
  lens resolution, which is D1's whole path minus the new write; adding a
  signup call to it is a small, natural extension and is Code Generation's.
- **Open, and D6's**: the retention period and scheduled purge for the signup
  audit events, under the team practice naming auth records as the first data
  class to carry one.
