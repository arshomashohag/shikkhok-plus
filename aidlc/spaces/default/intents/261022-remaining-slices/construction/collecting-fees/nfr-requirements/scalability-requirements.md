# Scalability Requirements — D3 `collecting-fees`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> D3 is the first unit whose tables grow **on a schedule rather than on a
> person's action**. Every table before it grew when someone tapped
> something; `fee_cycle` and `ledger_entry` grow because a clock said so.
>
> That is also what makes the concurrency requirement non-negotiable: the
> writer is a job, and Phase 1 runs more than one worker.

> **`NFRx.y` IDs are GLOBAL across units.** D3's start above the high-water
> mark each base had reached after D2: NFR6 from **.26**, NFR7 from **.6**.
> A bare `NFR6.21` is a **citation** of D1's requirement, not an ID defined
> here.

## Sources

- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  §§ 3.1, 3.2, 3.3, 11
- [upstream] `construction/collecting-fees/functional-design/rules.md` — BR1.3,
  BR1.4, BR1.5, BR4.1
- [upstream] `construction/collecting-fees/functional-design/entities.md`
- [upstream] `inception/requirements-analysis/requirements.md` — NFR20, NFR21
- [prior] NFR6, NFR7 of `261016-shikhokplus-tuition-app`
- [code] `app/db/models.py:302`, `tests/auth/test_ceilings.py:283`, read
  2026-10-23

---

## 1. Growth

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR6.26 | D3 does not raise or lower the scale ceiling | 100 teachers, a few thousand students | [NFR6] |
| NFR6.27 | `fee_cycle` grows at **one row per generating enrollment per month**, and that rate is the design | At the ceiling — say 3,000 enrollments — that is 3,000 rows a month and **36,000 a year**. Small, predictable, and bounded by enrollments rather than by traffic | [BR1.1] [NFR6] |
| NFR6.28 | `ledger_entry` grows **without bound** and V1 accepts it, with the arithmetic shown rather than assumed | At 3,000 enrollments and four entries a month: 12,000 rows a month, **144,000 a year**, **720,000 over five years** — unremarkable on `db.t4g.micro`, and every read is enrollment-filtered | [NFR20.14] [NFR6] |
| NFR6.29 | `payment_claim` and `reminder_event` grow at **person-driven and job-driven rates respectively**, both below the ledger's | A claim exists only when someone submits one; a reminder event only when a teacher sends one | [entities] |

**NFR6.28 is a recorded acceptance, not an omission.** The project has an
instructive precedent here: `rate_limit_counter` was found at D1 with a
declared 48-hour retention and **nothing enforcing it** — a decision made in
the right place with nothing behind it. The failure that time was a declared
disposition with no job. This time the position is the opposite and is stated
plainly: **the ledger is retained in full by design**, because an append-only
financial record whose old rows are deleted no longer reconstructs the balance
it claims to derive. The disposition row [NFR10.15] is where that is recorded
formally.

---

## 2. Concurrency — the requirement this unit exists to get right

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR6.30 | Idempotency is the **database unique constraint** on `(enrollment_id, period)` with `ON CONFLICT DO NOTHING`; an application-level "has this run?" guard is forbidden | Such a guard **passes a sequential test and fails with two workers**, which Phase 1 has | [BR1.3] [project: ALWAYS-rule] |
| NFR6.31 | The `charge` entry is appended **if and only if the insert created a row** | The row's creation is the idempotency token; the conflict path appends nothing. This ordering is the whole double-charge defence | [spec § 3.1 steps 7-8] |
| NFR6.32 | The concurrency test uses **real threads released from a barrier**, contending on the same `(enrollment_id, period)` at the same moment | A sequential two-run test passes against an implementation with **no atomicity at all** — the exact implementation the constraint exists to prevent | [AC5.1.2] [team: Testing Posture] |
| NFR6.33 | The assertion is on the **outcome**: exactly one cycle row exists, and the ledger's charged total equals one period's charge | Not on an internal call count, which would couple the test to the implementation it is meant to constrain | [AC5.1.2] |
| NFR6.34 | **Across-day idempotency** is tested separately: day N, then N+1, then N+1 again; the row set and the ledger total are identical after the second and third runs | Concurrency alone does not reach this case, and it is the one the daily self-healing job [BR1.4] depends on | [AC5.1.3] [team: Testing Posture] |

**NFR6.32 and NFR6.34 are two obligations, and the second is not covered by
the first.** This is stated twice — here and in the functional spec — because
the natural reading of "test idempotency" satisfies one of them.

**The precedent exists and D3 should follow it rather than invent a second
one.** `tests/auth/test_ceilings.py:283` —
`test_genuinely_concurrent_requests_never_exceed_the_limit` — is the built
pattern, and the same file carries the warning this obligation most needs,
beside a test renamed after it was found to run two checkers one after the
other:

> A test whose NAME claims a property it does not exercise is worse than no
> test, because the next reader believes the property is covered.

**The constraint shape also has a precedent.** `RateLimitCounter`'s
`UniqueConstraint` at `app/db/models.py:302` carries the reasoning already —
two workers racing on one window cannot both read a stale count, because the
second conflicts. D3 is the same shape with `DO NOTHING` in place of
`DO UPDATE`.

**This obligation has been deferred since the practices were written.** Team
memory records it as *"lands in D3 and has not been exercised yet, because fee
cycles are not built."* D3 is where it lands.

---

## 3. Other concurrent paths

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR6.35 | Two verifications racing on one claim converge on **one decision**; the second is a `ConflictError` rather than a second set of ledger entries | Double-crediting a payment is a money error, and corrections are a distinct path | [BR5.7] [NFR14.45] |
| NFR6.36 | Credit application is computed and appended **inside the same transaction as the charge**, after it | Computed before the charge, `min(available, owed)` is `min(available, 0)` and applies nothing — a silent no-op rather than an error | [BR4.3] [BR4.5] |
| NFR6.37 | Two generation workers applying credit to one enrollment cannot spend the same credit twice | Guarded by NFR6.30: only the worker whose insert created the row appends anything at all | [NFR6.31] [BR4.4] |

**NFR6.37 is why the charge-insert ordering matters beyond double-charging.**
Credit is enrollment-scoped [BR4.1], so two workers generating two different
periods for one enrollment at the same moment could each see the same
available credit. The insert-conflict gate is what serialises them.

---

## 4. The job as a scaling surface

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR6.38 | **D3 introduces the product's first scheduled job**, and the scheduling mechanism is a new surface rather than an existing one | I searched `app/`, `infra/`, `.github/workflows/` and the `Makefile` for a scheduler, cron, APScheduler or Celery and found none. The only `cron` hit is unrelated (`infra/modules/cdn/main.tf`) | [BR1.4] [code, read 2026-10-23] |
| NFR6.39 | The job's safety does **not** depend on it running exactly once | It may run twice, overlap itself, or miss three days; NFR6.30 and NFR6.34 make all three safe. That is what permits the cheapest scheduler available | [BR1.4] |
| NFR7.6 | The scheduler adds **no recurring cost** and stays within the USD 50/month ceiling | Satisfiable on the existing host; see `tech-stack-decisions.md` § 2, where the choice is recorded | [NFR7] [OC-4] |

**NFR6.39 is the requirement that makes the technology choice easy.** A job
whose correctness depends on exactly-once delivery needs a scheduler with
leader election and locking. This one does not, because the database
constraint is the lock — so a container-level timer is adequate, and that is
what keeps NFR7.6 satisfiable.

---

## 5. Capacity planning

| Quantity | Before D3 | After D3 | Bound |
|---|---|---|---|
| `fee_cycle` rows | Table does not exist | One per generating enrollment per month | Enrollments × months [NFR6.27] |
| `ledger_entry` rows | Table does not exist | Two to four per enrollment per month | **Unbounded, accepted** [NFR6.28] |
| `payment_claim` rows | Table does not exist | One per submission | Person-driven |
| `reminder_event` rows | Table does not exist | One per reminder, including failures | Teacher-driven |
| Statements per fee view | — | Constant in roster size | [NFR20.16] |
| Scheduled jobs | **None in the product** | One daily | [NFR6.38] |

**Four new tables is the largest schema change of this record**, which is why
the governance obligation [NFR10.15] is a release gate rather than a note: the
schema-iterating test fails on a live table with no disposition.

---

## Assumptions & Open Questions

- **Assumed**: 3,000 enrollments as the working figure for "a few thousand
  students" in the row-count arithmetic. NFR6 states the ceiling in words
  rather than a number; 3,000 is the upper reading of it, so the figures are
  the pessimistic ones.
- **Assumed**: four entries per enrollment per month in the ledger arithmetic,
  matching the performance file's generous bound.
- **Assumed**: no partitioning, no archival and no read replica in V1. Each
  would be a real mechanism for a problem that does not exist at this scale,
  and ADR-002 already names the mitigation that would come first [NFR20.15].
- **Open, and D5's**: the cross-batch dues query spans every batch a student
  belongs to rather than one teacher's batch, so it is the first read whose
  fold is not bounded by class size.
