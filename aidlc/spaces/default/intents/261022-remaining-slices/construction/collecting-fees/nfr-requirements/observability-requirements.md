# Observability Requirements — D3 `collecting-fees`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **D3 is the first thing in this product that acts without a user.** Every
> observability requirement below follows from that: a job nobody watches
> needs someone to notice when it stops, and the money it writes needs to be
> auditable without putting a child's financial record into a log line.
>
> The second problem is the one D1 already solved and D3 must not undo: **a
> ledger is an append-only audit trail by construction**, so most of what
> would otherwise be logging is already a row.

> **`NFRx.y` IDs are GLOBAL across units.** D3's start above the high-water
> mark each base had reached after D2: NFR24 from **.5**, NFR25 from **.8**,
> NFR26 from **.3**.

## Sources

- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  §§ 3, 5.5, 9
- [upstream] `construction/collecting-fees/functional-design/rules.md` — BR3.3,
  BR5.5, BR5.7, BR7.1, BR7.2
- [upstream] `construction/collecting-fees/functional-design/entities.md` —
  `LedgerEntry`, `ReminderEvent`
- [prior] NFR14 of `261016-shikhokplus-tuition-app`;
  `inception/contract-design/contract-summary.md` § G (OQ-1)
- [team] Deployment practice, 2026-10-22
- [code] `app/audit/log.py`, `app/contract/privacy.py`, read 2026-10-23

---

## 1. What must never be logged

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR24.5 | **`PaymentClaim.transaction_id` never reaches a log line**, at any level | Claimant-authored, it identifies a real transaction at a real provider, and OQ-1 asks whether it survives deletion. It joins the phone number, the OTP and the token in the never-log set | [team: Deployment] [OQ-1] |
| NFR24.6 | No log line carries a **money amount tied to an identifiable enrollment** | A balance beside an enrollment id is a child's financial position in a log store with a different retention and a different access control than the table it came from | [NFR14] [RC-1] |
| NFR24.7 | The **collection number** never reaches a log line | It is a teacher's personal payment account, and it is the one teacher-authored field D3 deliberately discloses downward — a narrower audience than a log store's | [BR6.4] [NFR14.32] |
| NFR24.8 | Every error log carries the request or correlation id and nothing identifying; tracebacks are never returned to a client | The correlation id ties a row to a request **without carrying its contents** | [code: `audit/log.py`] [team: Deployment] |

**NFR24.5 is the coordinate addition to an existing rule and is listed first
because it is the one a developer would not think of.** The standing rule
names a phone number, an OTP and a token. A bKash transaction id is not any of
those and is exactly as sensitive: it is a handle on a real payment, authored
by a child or their guardian.

**The structural guarantee that makes NFR24.6 enforceable is already built and
should not be weakened:** the audit row dataclass has **no free-form string
field** but `correlation_id`, asserted by a test — because a `message` or
`note` column is where an amount or a phone number eventually lands, added by
someone debugging in good faith.

---

## 2. The ledger is the audit trail

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR24.9 | Every money movement is a **row, not a log line** | `LedgerEntry` is append-only with `created_by_account_id` and `created_at`. A parallel money log would be a second record that drifts from the first | [BR3.3] [entities] |
| NFR24.10 | `created_by_account_id` is **NULL for job-created entries**, and that is the honest value | Nobody caused it. A synthetic "system" account would make an audit query answering "who charged this student?" return a lie that looks like an answer | [entities: `LedgerEntry`] |
| NFR24.11 | A correction is **visible as history**: the prior decision is retained with its actor and timestamp, and the compensating entries carry their own | Supersession drives what a teacher *sees*; the balance still folds every row, because a compensating pair sums to zero | [BR5.7] [spec § 5.5] |
| NFR24.12 | `ReminderEvent` records **every** send attempt including failures, as `(enrollment, period, channel, sent_at, sent_by, outcome)` | The teacher-facing state is the latest event per `(enrollment, period)`. A boolean or a `last_reminded_at` column cannot express a failed send, a channel, or a second reminder | [BR7.1] [FR10.3] |

**NFR24.10 is a small decision with a disproportionate consequence.** The
question an auditor asks of a fee ledger is *who did this*. A NULL answers
"the scheduled job, which nobody triggered"; a synthetic account id answers
with something that looks like a person.

---

## 3. Alerting

The alert discipline D1 established governs here, and D3 is the first unit
that adds a genuinely alert-worthy failure since.

| ID | Requirement | Alert? | Source |
|---|---|---|---|
| NFR25.8 | The generation job **failing to complete a run** | **Yes** | [BR1.4] |
| NFR25.9 | The generation job **not having run at all** for more than 48 hours | **Yes** — this is the failure a run-failure alert cannot catch | [BR1.4] |
| NFR25.10 | An individual enrollment-period failing within an otherwise successful run | **No** — a counted metric, not a page | [NFR19.8] |
| NFR25.11 | A push notification failing | **No** — recorded as an event outcome [NFR24.12] | [BR7.2] |
| NFR25.12 | A failed pre-migration backup | **Yes** | [team: Deployment] [NFR19.27] |

**NFR25.9 is the requirement that would otherwise be missed, and it is the
most important alert in this file.** A job that fails loudly alerts. A job
whose scheduler was never wired up, or whose container stopped having a
timer, fails **silently and indefinitely** — and because generation is
self-healing, the system looks healthy right up to the moment someone notices
that nobody has been billed since March. The alert must therefore fire on
**absence of success**, not on presence of failure. A run-failure alert alone
monitors a job that is running.

**NFR25.10 is a deliberate non-alert, on D1's reasoning.** The per-enrollment
commit granularity exists so one bad row does not abort a run; paging on one
bad row would convert that resilience into noise, and noise in the same
channel as NFR25.9 trains the operator to ignore the alert that means nobody
is being billed.

---

## 4. Metrics

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR25.13 | Per run: **cycles created, cycles skipped by conflict, enrollment-periods failed** | The skipped count is the self-healing property made visible. On a normal day it is near zero; after an outage it is large and then zero again. A sustained non-zero is a double-scheduling bug | [BR1.3] [BR1.4] |
| NFR25.14 | **Total charged per run** is countable, as an aggregate with no enrollment attached | The one number that would be noticed if the fee resolution broke. A tenfold jump is a defect, and it is invisible in a per-row view | [NFR24.6] |
| NFR25.15 | Payment claims submitted, approved in full, approved partially, and rejected, countable by outcome | The rejection rate is the signal that the claim flow is confusing people, and the partial rate is how often the carry-or-waive choice is exercised | [BR5.6] [spec § 5.2] |
| NFR25.16 | **Verification corrections** are countable | A rising correction rate means teachers are approving wrongly, which is a usability finding about the verification screen rather than a defect report | [BR5.7] |
| NFR25.17 | Push dispatch outcomes are countable by outcome, **including `UNREGISTERED`** | A rising `UNREGISTERED` rate is the token-lifecycle signal, and it is the one push outcome that is not a failure | [NFR19.22] [D-42] |

**Counts only, never the values.** A metric labelled by enrollment id, phone
number or amount is that data in a metrics store [NFR24.6].

**NFR25.14 is the closest this unit gets to a correctness monitor**, and it is
deliberately an aggregate. The fee resolution rule [BR2.4] — enrollment fee
when not NULL, else batch default, with zero a real fee — has a failure mode
where every student is charged the same wrong amount, and no per-row check
notices because every row is internally consistent.

---

## 5. SLIs and SLOs

| ID | SLI | SLO | Source |
|---|---|---|---|
| NFR26.3 | **Generation freshness**: hours since the last successful run | **Under 48**, which is the alert threshold in NFR25.9 rather than a separate number | [BR1.4] |
| NFR26.4 | **Ledger invariant holds**: the per-enrollment identity balances for every enrollment | **Always**, asserted by the property-based test and by the per-cycle invariant, not monitored in production | [spec § 2.2] |
| NFR26.5 | **Duplicate cycles**: rows per `(enrollment_id, period)` | **Exactly one, always** — guaranteed by the unique constraint, so a monitor would watch a value the database cannot produce | [BR1.3] |
| NFR26.6 | Payment claim submission success rate | No target set in V1; measured through the pilot | [OC-5] |

**NFR26.4 and NFR26.5 are SLIs with a target and a test rather than a
monitor, and that is the right shape for both.** The invariant is
machine-checkable before deployment and is already at 100% branch coverage
with a Hypothesis property test; a production threshold on it would be an
admission it might not hold. NFR26.5 is enforced by a database constraint, so
a monitor would be watching for something the constraint makes impossible.
Both are recorded here so they are not later re-invented as dashboards.

**NFR26.3 is the one genuine production SLI in this unit**, because it is the
only property that can degrade without anything raising an error.

**No SLO percentages are invented for V1.** Phase 1 is closed testing with a
small pilot audience, and a 99.x% target set now would be a number nobody
derived from anything — which this project's own practice forbids.

---

## 6. What has no automated verifier

Stated plainly, because a manual check described without this sentence reads,
to the next person, as a verifier.

| Obligation | Verifier | Automated? |
|---|---|---|
| NFR25.9's alert actually fires | A deliberate skipped-run rehearsal in staging before the first production generation | **No.** Nothing automated proves an alert's delivery path works end to end; this is a once-performed manual check |
| Bangla layout on D3's fee screens | A row per screen in `docs/delivery/bangla-layout-check.md` | **No.** The project has no screenshot harness, and the per-screen manual check is the chosen alternative |

---

## Assumptions & Open Questions

- **Assumed**: logs continue to go to the host's standard output and the
  existing collection, with no new sink. D3 adds no observability
  infrastructure and no recurring cost [NFR7.6].
- **Assumed**: the metrics in NFR25.13–NFR25.17 are derivable from application
  logs and from the tables themselves rather than needing a metrics backend.
  Phase 1's budget carries none, and these are low-cardinality counts — several
  of them, including the claim outcome counts, are queries over
  `payment_claim` rather than emitted metrics at all.
- **Open, and the human's**: whether NFR25.9's 48-hour threshold is right. It
  is derived as "two missed daily runs", which is the shortest window that does
  not page on a single transient failure the next run would heal. A monthly
  billing cycle would tolerate longer; a teacher watching for a fee to appear
  would not.
- **Open, and D6's**: the retention period and scheduled purge for
  `reminder_event`. The ledger itself is retained in full by design
  [NFR6.28], but a reminder event is operational rather than financial and is
  the D3 table most plausibly purgeable.
