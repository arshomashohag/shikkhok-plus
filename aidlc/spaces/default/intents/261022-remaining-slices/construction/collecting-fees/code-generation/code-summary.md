# Code Summary — D3 `collecting-fees`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **Every figure in this file was produced by running something**, and
> the command is named beside it. This project's memory records a stage
> whose table asserted its figures were measured when they were
> estimated, and all twelve were wrong while every verdict still passed.

## Sources

- [upstream] `functional-design/rules.md` (BR1.1–BR7.2), `entities.md`,
  `functional-spec.md`
- [upstream] `nfr-design/observability-design.md` § 1,
  `reliability-design.md` §§ 5–6, `security-design.md` §§ 1–4
- [upstream] `infrastructure-design/infrastructure-specification.md` § 3
- [prior] `261016-shikhokplus-tuition-app/inception/domain-design/decisions.md`
  — ADR-002 and the corrected invariant
- [code] `app/money/`, `app/db/models.py`, `app/authz/`, `app/contract/`,
  `tests/auth/test_ceilings.py`, `tests/db/test_governance.py`,
  `infra/modules/app/user_data.sh.tftpl`, read 2026-10-24
- [human] The scheduler choice: cron installed by `user_data.sh.tftpl`

---

## 1. What was built

The fee system in full: five tables, calendar-month generation with a
non-degrading clamp, the daily self-healing job behind a cron entry,
two-sided carry-forward, credit grant and apply, payment claims and
verification with partial approval, the server-computed status enum, the
shared FCM adapter, nine routes, and four Android screens.

**All 54 steps are complete.** The plan file's boxes are ticked.

| Measure | Before | After | Command |
|---|---|---|---|
| Backend tests | 730 | **1023** | `python -m pytest tests` |
| Kotlin tests | 280 | **299** | `./gradlew :android:testDebugUnitTest` |
| Backend line coverage | 91.68% | **91.69%** | `make check` |
| Money module branch | 100.00% | **100.00%** | `make check` |
| Kotlin line coverage | 48.52% | **52.46%** | `verifyCoverageRatchet` |
| Migration head | 0004 | **0005** | `tests/db` |

The Kotlin figure reads 0.08% under the 52.54 floor and the ratchet
passes: that task carries a documented 0.5% tolerance, because "a
ratchet that fires on 0.01% is a ratchet people disable". The drop is
denominator growth from two map entries, not lost coverage — the new
message key is exercised by `MessageKeyCoverageTest`. **The floor was
left at 52.54 rather than lowered**, because lowering a floor to absorb
noise is how a ratchet erodes.

`make check` reports **All gates passed**: ruff format, ruff check, mypy
across 88 files, both coverage floors, the Android suite, spotless,
detekt, lint and the coverage ratchet.

**Docker was reachable for every run.** Stated because D3's tests are
almost entirely integration tests against real PostgreSQL: without it
the suite skips and still exits zero, so a green run would mean the
money paths were never checked. **150** of the new tests are in
`tests/fees` and `tests/notifications` and every one of them took a
database fixture.

### The Kotlin ratchet moved

48.52 → 52.54, and the floor was raised to match when it rose, which
the task prints an explicit instruction to do rather than doing
automatically. A self-raising ratchet records whatever the last run
produced, including a run that skipped tests. It then settled at 52.46
for the reason recorded above, and the floor was **not** moved down.

---

## 2. The separating cases, and what each would have caught

The plan named five obligations. Each is a test whose *wrong* answer is
plausible, which is the property that makes it worth having — a
happy-path test distinguishes neither implementation.

| Case | Correct | The plausible wrong one | Test |
|---|---|---|---|
| Shortfall: charged 1000, claimed 1500, approved 600 | **400.00** | 900.00, from `claimed − approved` | `test_the_shortfall_is_charged_minus_approved_not_claimed_minus_approved` |
| Carry 1000 into a second 1000 charge | **2000.00** | 3000.00, from a one-sided carry | `test_carrying_1000_into_a_second_1000_charge_reads_2000_not_3000` |
| 200 credit against a 1000 charge | **800.00** | 1000.00, missing the `credit_applied` term | `test_credit_granted_in_one_period_is_spent_in_another` |
| Anchor 31 in March, after a February | **2027-03-31** | 2027-03-28, from a degrading clamp | `test_the_clamp_does_not_degrade_the_anchor` |
| Seat fee 0.00 on a batch defaulting to 1000 | **0.00** | 1000.00, from `fee or default` | `test_zero_is_a_real_fee_and_not_a_missing_one` |

**The two concurrency tests are different tests and both exist.**
`test_generation_races.py` releases eight threads from a
`threading.Barrier` against real PostgreSQL and asserts the *outcome* —
one row per `(enrollment_id, period)` and one period's charge, not the
absence of an exception. It cannot reach a re-run on a later day,
because every thread carries the same clock, so
`test_generation_across_days.py` injects time instead and asserts the
row set and ledger total are identical after runs two and three. The
first looks like it already covers generation, which is why the second
is the one that gets dropped.

**The decline asymmetry is tested from both roles.** A student decline
stops generation and voids the accrued balance by a reversal entry; a
guardian decline does neither. This has already produced one defect in
this project on the presentation side, and the guardian half is
asserted directly: `test_a_declined_guardian_link_writes_no_reversal`.

**The heartbeat's zero-cycles case is covered and so is the empty
database.** `test_a_run_that_finds_nothing_due_still_stamps` and
`test_an_empty_database_still_stamps`. Generation is monthly, so most
days legitimately create nothing; a heartbeat written only on
`cycles_created > 0` would go stale for weeks during correct operation
and train the operator to mute the alert.

**`AUTH_403_CODES` is asserted as a set difference, not an equality.**
`AUTH_403_CODES - ALLOWED_NON_RESOURCE == {NOT_AVAILABLE}`. A whole-set
equality would fail against a correct registry, and the fix a future
reader would reach for is deleting the assertion.

---

## 3. Design decisions taken during implementation

### 3.1 `void_accrued_cycles` re-reads the student decision itself

**A test I wrote caught my own implementation.** The first version
voided whatever it was handed, so calling it on a *guardian* decline
would have cleared the student's debt — exactly the defect BR1.7 names,
one layer below where the project last met it. The function now reads
`student_decision` and returns empty when it is not `declined`.

The reasoning is the team's own: a check above a query is one the next
query can bypass, so the condition lives where the write happens. It
also makes the function idempotent, which matters because the daily job
reaches every declined seat again tomorrow.

### 3.2 The client cannot compare money, and the compiler proved it

`FeeStateMapper.toRosterRow` first derived `owesSomething` from
`outstanding > Money.ZERO`. That **did not compile**: the Kotlin `Money`
value class exposes no comparison at all, deliberately, because the
client performs no money arithmetic.

The field now derives from the server's status enum. This is a better
answer than the one I wrote — a seat whose only period is *waived* has a
zero balance and does not owe anything, and both derivations agree there
by luck rather than by reason. The boundary being mechanical rather than
reviewed is what surfaced it.

### 3.3 The collection-number allowlist holds three routes, not one

The security design specifies an equality against a **one**-element set.
The built application has three, and the difference is not a weakening:

- `GET /v1/enrollments/{enrollment_id}/payment-destination` is the
  **downward** disclosure — a teacher's number shown to somebody who is
  not that teacher. This is the entry the design named.
- `GET /v1/batches` and `POST /v1/batches` are the teacher reading and
  writing **their own** number on **their own** batch, which discloses
  it to nobody. They are D2's and predate the design document's
  snapshot of the schema.

The distinction the gate cannot make is made mechanical instead: the
downward route is asserted to resolve **no** teacher lens, and the two
batch routes to resolve **only** a teacher lens. A fourth route carrying
the field fails the equality whichever direction it faces.

### 3.4 `Money.format` was added to `app/money/`, which the plan said not to touch

The plan says "does not touch `app/money/`" in its summary and then
Step 35 requires `Money.format(locale)`, which does not exist there.
The functional spec settles it: § 10 says the method "becomes blocking
here".

Both changes to that package are recorded:

- `format()` plus the `_group_by_lakh` helper in `_money.py`, with
  `tests/money/test_format.py` keeping the package at **100.00% branch**;
- `apply_credit` added to `__all__`. It was always part of the
  arithmetic surface and was private only because nothing outside the
  package had needed it. D3's ledger writer reaching into
  `app.money._ledger` would have been exactly the breach the public
  surface exists to make visible.

No arithmetic was changed. The branch figure is unchanged at 100.00%.

### 3.5 Two `DISPOSITION_VALUES`, deliberately, with a test

`app.db.models` carries the untyped tuple the database enum is built
from; `app.fees.status` carries a `Literal`-typed one, so a membership
test *narrows* and no `cast` is needed at the ORM boundary. One
declaration cannot serve both — the model's must stay importable
without pulling the fee package into the ORM. Two declarations need a
test, so `test_the_two_disposition_declarations_agree` exists, and the
same for the claim statuses.

### 3.6 The freshness check is a service, not a second cron entry

The observability design is explicit that a check sharing the job's
trigger is circular. The job runs from `/etc/cron.d/`; the check runs as
a `Restart=always` systemd service.

**What this does not survive is stated in the file rather than implied.**
Both are written by `user_data.sh.tftpl`, so an instance replacement
wipes and reinstalls both together and the check cannot detect its own
absence. What it covers is every failure short of that — a broken
crontab, a dead cron daemon, a job erroring nightly. The
instance-replacement case is covered by Terraform re-running the script,
which is precisely why the entry is there and not added over SSM.

### 3.7 Two defects the traceability sensor found

**The first traceability file declared 187 upstream ids and mapped
106.** The other 81 were real requirements this unit's own
`nfr-requirements/` defines, and they were invisible until the sensor
ran. Mapping them meant reading each requirement's text against the
built code, and **two of them were not satisfied**.

**The batch fee view was N+1** [NFR20.16, NFR20.17]. `batch_fee_overview`
called `derive_for_enrollment`, a `FeeCycle` lookup and `fee_status` per
seat — and `fee_status` folded the same ledger a second time. Measured
before the fix: **8 statements for 2 seats, 77 for 25**. NFR20.17 is
explicit that D3 "closes what D2 deliberately left open, and must not
close it with a query per seat", which is precisely what it did.

Fixed by fetching the batch's ledger and cycles in two statements and
folding per enrollment in Python, which needed `status_from_entries` —
the pure half of the status computation, so a caller already holding
the rows does not re-read them. `tests/fees/test_query_count.py`
asserts the property (N=2 against N=25) rather than a literal count,
reusing D2's counter harness.

**A concurrent re-verification recorded a second decision** [NFR6.35,
NFR14.45]. There was no `ConflictError` anywhere in `app/fees/`. A
claim has no `(enrollment, period)` uniqueness for the database to
conflict on, so this is the one concurrent path the fee-cycle
constraint does not already cover — and the consequence is
**double-crediting a payment**, a money error.

Proven rather than assumed: with the guard removed, **8 of 8 racing
verifications are accepted** and the 1000.00 claim is credited eight
times. With it, exactly one is accepted and the other seven raise
`ConflictError`.

The guard takes a row lock rather than the conditional `UPDATE` the
design names, because this path writes the status through the ORM
afterwards; both give the same guarantee and the deviation is recorded
in the function's docstring. **A declared correction skips it**: FR9.2
makes every verification correctable, so a guard reading "refuse any
verification of a decided claim" would have settled the race and broken
correction entirely. `test_a_deliberate_correction_is_still_permitted`
is what stops that being the fix.

**Both were the kind of defect a coverage percentage cannot see.** The
N+1 was fully covered by passing tests; the verification race was
covered by tests that never ran two verifications at once.

### 3.8 `fee_cycle.due_date` needed a money-name exemption

It matches both the `fee` and `due` tokens while holding a DATE. Two
`(schema, field)` entries and one `(table, column)` entry, each stating
why, so no exemption widens beyond the property it was reasoned about.
`test_the_real_application_needs_the_allowlist` was updated from
"`fee_due_day` and nothing else" to name both — a claim that had gone
stale the moment this column landed.

---

## 4. The stopgap D2 recorded is now a no-op

`app/main.py` injects `ErrorEnvelope` and `Money` into the generated
document because FastAPI emits a component only when a route references
it. Its docstring said it "stays until a Unit whose routes genuinely
reference them lands, at which point it becomes a no-op rather than a
lie."

**D3 is that unit.** Nine fee routes declare their 400, 401, 403 and 409
responses against `ErrorEnvelope`. The injection is **kept**, because a
future Unit removing the last reference would otherwise drop a component
from the committed contract with the diff gate passing over the absence
— and `test_the_injection_is_now_redundant` asserts the no-op is real,
so the docstring's claim cannot quietly become false again.

---

## 5. Gaps, named

| Gap | Severity | Why it is open |
|---|---|---|
| **The alert's delivery path is unproven** [NFR25.10] | Medium | `check-generation-freshness` computes the right verdict over all three branches and emits `log.critical`, this product's only alert channel. **Nothing automated proves a person receives it.** That is a once-performed skipped-run rehearsal in staging, and it has not been performed. Stated plainly because a manual check described without that sentence reads as a verifier |
| **Four Bangla layout rows are open** [NFR23.9] | Medium | Added to `docs/delivery/bangla-layout-check.md` with each screen's computed longest Bangla string. The check is on a device in Bangla locale; there is still no screenshot harness and code generation cannot perform one |
| **No fee latency measured** [NFR20.13, NFR6.39] | Low | The ledger fold is one linear pass over one enrollment's rows behind `ix_ledger_entry_enrollment_period`. No figure is recorded, so the budget is designed for rather than demonstrated. D5 owns the performance harness |
| **The real FCM adapter does not exist** | Low | By design. `build_push_adapter` returns the null adapter and **refuses to start** if the real one is selected, rather than falling back — a product that believes it is sending reminders and is not is the failure this design is arranged around. A Firebase project, a credential and a device-token table arrive with the Unit that needs real delivery |
| **`fee_due_day` NULL semantics remain an assumption** [BR2.3] | Low | Last-day-of-period is implemented and tested. It is the only default that cannot make a fee due before the month it pays for has been taught, and it degrades to an anchor of 31. **Still flagged for the human**; it changes when teachers who set no due day get paid |
| **OQ-1 is open** | Low | Whether `transaction_id` survives the claimant's deletion. Shipped **nullable**, so the answer is not foreclosed and D6 nulls it in place either way |

**Deliberately not built**, per the plan: any change to the money
arithmetic, ledger compaction, the deletion flows (D6), the cross-batch
dues query (D5), a metrics backend, and the origin 502 fix.

---

## 6. Deviations from the plan

| Step | Deviation | Why |
|---|---|---|
| 33, 54 | **Two requirements were unsatisfied and are now fixed** | § 3.7. The N+1 fee view and the missing verification conflict guard, both found by the traceability sensor rather than by the tests |
| Summary line | `app/money/` was touched | Step 35 requires `Money.format`, which lives there and did not exist. § 3.4 records both changes; branch coverage is unchanged at 100.00% |
| 31 | The allowlist holds three routes, not one | § 3.3. The design predates D2's batch routes; the downward/owner distinction is asserted separately rather than lost |
| 43 | The freshness check is a systemd service, not cron | The design requires the two not share a trigger; § 3.6 records what that does and does not survive |
| 46 | `owesSomething` derives from the status enum | § 3.2. The first version did not compile, and the enum is the better source |
| 22 | `ledger_writer.py` arrived with Phase C, not Phase D | `void_accrued_cycles` is what the Step 16 RED tests exercise, so it had to exist for them to go green |

**Nothing was dropped.** Every step was implemented; the deviations
above are differences in *how*, each with its reasoning.

---

## 7. Where the work landed

| Area | Files |
|---|---|
| Schema | `migrations/versions/0005_fee_system.py`, `app/db/models.py`, `app/governance/dispositions.py` |
| Domain | `app/fees/` — `periods`, `resolution`, `generation`, `balances`, `ledger_writer`, `claims`, `verification`, `status`, `views`, `reminders`, `commands` |
| Notifications | `app/notifications/fcm.py` |
| API | `app/api/fees.py`, `app/schemas/fees.py`, `app/contract/collection_number.py` |
| Money | `app/money/_money.py` (`format`), `app/money/__init__.py` |
| Infrastructure | `infra/modules/app/user_data.sh.tftpl` |
| Android | `core/network/FeeDto.kt`, `feature/fees/` (state, mapper, four screens), both `strings.xml`, `MessageKeys.kt` |
| Tests | `tests/fees/` (13 files), `tests/notifications/` (2), `tests/money/test_format.py`, plus contract and db additions |

`source-manifest.json` lists all 78 paths. `traceability.json` carries
**187 rows — every declared id mapped** — across 164 `OK`, 14 `N/A`, 8
`Deferred` and **1 `GAP`** (`NFR25.10`, the alert's unproven delivery
path). Every id was checked against the upstream artifacts, every
target checked to exist, and no id minted.

Seven of the `N/A` rows are inherited **citations** rather than ids D3
defines — `NFR6.21`, `NFR9.1`, `NFR14.15`, `NFR14.27`, `NFR14.29`,
`NFR20.10`, `NFR20.11` — which the `nfr-requirements/` files state
themselves ("A bare `NFR6.21` is a **citation** of D1's requirement,
not an ID defined here"). They reached `upstream_ids` because the id
scrape matched source brackets. They are classified with that reason
rather than dropped, so a reader can see why each is present.

## Assumptions & Open Questions

- **Assumed, and the human should confirm**: a NULL `fee_due_day` means
  the last day of the period [BR2.3]. Implemented and tested; it changes
  when teachers who set no due day get paid.
- **Assumed**: `Money.format` emits Latin digits, agreeing with the
  client's built `Numerals.kt` rather than deciding independently.
- **Open, and D6's**: OQ-1 — whether `PaymentClaim.transaction_id`
  survives the claimant's deletion. Shipped nullable.
- **Open, and the human's**: the 48-hour staleness threshold, which the
  requirement records as open. Implemented as two missed daily runs with
  the boundary asserted.
- **Decided this turn by the human**: the scheduler is cron installed by
  `user_data.sh.tftpl`.
