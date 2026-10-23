# Bolt Plan — the six remaining units

**Stage**: delivery-planning (2.9)
**Phase**: Inception
**Record**: 261022-remaining-slices

> A **Bolt** is one build pass over a piece of the work, ending in something
> that runs. Here one Bolt is one unit: six Bolts, serial.
>
> The sequence was settled at the 2026-10-22 re-cut and is not re-derived.
> This file carries it for this record's units, with the schema and
> authorization decisions from Domain Design folded into each Definition of
> Done.

## Sources

- [upstream] `inception/units-generation/` — the six units and their DAG
- [upstream] `inception/domain-design/decisions.md` — ADR-009..014
- [upstream] `inception/refined-mockups/mockups.md` — the artboards per unit
- [upstream] `inception/user-stories/stories.md` — what each Bolt delivers;
  the Definitions of Done below are its acceptance criteria grouped by unit
- [upstream] `inception/practices-discovery/team-practices.md` — the gating
  decision, the `make check` entrypoint, and the controls assigned before D1
- [prior] the approved re-cut at
  `261016-shikhokplus-tuition-app/inception/delivery-planning/bolt-plan.md`

---

## Way of working

Trunk-based, squash-merge, one commit per Bolt named by its slug. Serial
execution: this is a solo build with no second worker. Unit-major iteration
with checkpoints enabled.

**No walking skeleton.** It was built and human-checkpointed at B3 in the
prior record; the ceremony does not recur.

---

## The sequence

| # | Bolt | Unit | Why here |
|---|---|---|---|
| 1 | `d1-signing-up-and-joining` | D1 | DAG root, and absolutely forced: nothing else can be demonstrated by a real person until an account can exist. Today a teacher exists only by hand-inserting a database row. |
| 2 | `d2-running-a-batch` | D2 | Forced after D1, and the cheapest Bolt by a wide margin — no new endpoints, screens over nine that already work. It converts a large amount of already-paid-for backend into something usable. |
| 3 | `d3-collecting-fees` | D3 | DAG-forced after D2. Chosen ahead of D4 because the fee model is known to be in revision [D-18], and pinning its arithmetic under test is what makes that revision cheap rather than frightening. |
| 4 | `d4-teaching-and-recording` | D4 | DAG-forced after D2. Deferred past money deliberately: the largest surface, carrying the offline queue, but none of it is money or privacy risk and nothing waits on it except insights. |
| 5 | `d5-knowing-how-it-is-going` | D5 | Forced: reads both D3's fees and D4's exams. |
| 6 | `d6-releasing-safely` | D6 | Topologically terminal and release-blocking. Its schema-iterating test is vacuous until the last table exists. |

Five of six positions are DAG-forced. The one free choice — D3 before D4 — is
argued in `risk-and-sequencing-rationale.md`.

**No WSJF scoring**, for the reason the prior record recorded and which still
holds: every remaining capability is Must Have, so cost of delay is constant
across all six, and five positions are forced. A model whose value axis does
not vary is not a model.

---

## Per-Bolt Definition of Done

Every Bolt inherits, without restatement: tests per the affirmed predicate in
`team-practices.md`; `make check` green locally and in CI; squash-merge as one
conventional commit; a governance row for every table its migration creates;
and **a row in `docs/delivery/bangla-layout-check.md` for every screen it
ships** — a screen with no row means an incomplete unit [FR0.2].

Each Bolt's stories are listed below; their acceptance criteria in
`stories.md` are the Definition of Done, and the Confidence Hypothesis names
the one that would hurt most if it were wrong.

### Bolt 1 — `d1-signing-up-and-joining`

**The Bolt that makes the app usable by someone who has never used it.**

**Stories** [stories.md]: US1.2, US1.5, US1.10, US1.11, US1.12, US1.13,
US1.16. US1.8's OTP controls must still hold afterwards, byte-identical.

Schema: two enum decision columns on `Enrollment`, `NOT NULL`, no column
default, **conditionally backfilled** — `accepted` where the link already names
an account, `pending` otherwise [ADR-013]. A nullable `address` on `Profile`
[ADR-010].

Authorization: `InvitationLens` as a fourth `Lens` subtype, resolved by its own
statement [ADR-011]. **And the change without which the rest is decoration**:
`_LENS_QUERY` and `_SUMMARY_QUERY` both gain `decision = 'accepted'`
[ADR-014].

API: `POST /v1/accounts`; the already-added lookup, naming neither teacher nor
batch; accept, decline and un-decline; signup's own per-number and per-IP
ceilings.

Screens: `O1` five states, `O2`, `O3`, `O4` seven states, `O5`.

**Confidence hypothesis.** *A phone number typed by a teacher grants that
account no student or guardian lens until the account holder accepts, and
`GET /v1/me` reports no count for an unaccepted seat.* Falsified by: either
query granting on the old evidence. **This test fails against today's code**,
which is what makes it worth writing.

### Bolt 2 — `d2-running-a-batch`

**Stories** [stories.md]: US1.3, US1.15, US2.1, US2.2, US2.3, US2.4, US2.5,
US2.6.

Screens over built endpoints, plus the roster's per-link state and the
batch-level accepted count. `T6`, `T7` with its sixth-column states, `T8`,
create-batch, remove-student, `G1`. Settles OQ-7.

**Confidence hypothesis.** *A teacher adding a student who never accepts sees
that seat as pending indefinitely and can correct the number; one who accepts
changes state without the teacher acting.* Falsified by: a roster that cannot
distinguish the two — the mistyped-digit failure this state exists to catch.

### Bolt 3 — `d3-collecting-fees`

**Stories** [stories.md]: US1.14, US5.1–US5.7, US6.1–US6.4.

The ledger, fee cycles, payments, verification. **Inherits US1.14 in full**
[AC1.14.1–AC1.14.4]: D1 sets the decision, D3 is where it first touches money.
Mandatory money tests, test-first by the predicate. 100% branch coverage on the
money module. Idempotency tested with overlapping concurrent generations.

**Confidence hypothesis.** *A partial payment approved for less than claimed
leaves the originating period relieved and the receiving period charged such
that the enrollment total is unchanged; an approval exceeding the claim becomes
a credit rather than a negative outstanding.*

### Bolt 4 — `d4-teaching-and-recording`

**Stories** [stories.md]: US3.1–US3.6, US4.1–US4.7.

Sessions, attendance with the four-state offline queue, the conflict-resolution
screen, exams and marksheets. **No Macrobenchmark harness** [human,
2026-10-23]: PU-3.6's mid-class latency obligation is discharged by a named
manual check during the pilot — a full batch's attendance marked on a low-end
device, timed, with the result recorded — and never by a Compose correctness
test.

**Confidence hypothesis.** *An attendance roster composed offline against
version N, submitted after the roster moved to N+1, is refused as `conflicted`
— never `failed`, never silently applied — and re-applying writes, because it
carries a fresh `client_mutation_id`.*

### Bolt 5 — `d5-knowing-how-it-is-going`

**Stories** [stories.md]: US7.1, US8.1–US8.4.

Cross-batch dues, earnings, trend, next exam. Ships without `collection_rate`
while OQ-2 is open. Plus the 15 MB assertion, Syft and the ZAP baseline — each
measures a nearly-finished app, which is why it belongs here.

**Confidence hypothesis.** *A student who left mid-year owing money appears on
the cross-batch dues screen; an active student owing nothing does not.*

### Bolt 6 — `d6-releasing-safely`

**Stories** [stories.md]: US1.6, US1.7, US10.1.

Both governance manifests complete, both deletion paths with a test per path,
the idempotent chunked purge, and the **privacy policy generated from the
manifests** — including [ADR-012]'s disclosure that a declined seat keeps the
teacher-typed name, with a test asserting the generated text says so.

**OQ-1 and OQ-5 must close before this Bolt starts** — start conditions, not
completion criteria.

**Confidence hypothesis.** *After a guardian deletes their account, every
column the policy says is removed is absent and every column it says is
retained is present, asserted row by row against the manifest.*

---

## Gating

**Construction runs autonomously**, carried forward from the 2026-10-22
decision and affirmed in `team-practices.md` under Way of Working: the earlier
practice gated through the payment slice, and that slice was the
platform-subscription boundary, which no longer exists. The fee system remains
in D3 and remains the most consequential arithmetic in the product; it no
longer marks a *gating* boundary.

**The verification command is `make check`**, approved 2026-10-23. It is the
same entrypoint locally and in CI, which `team-practices.md` names as the
single most important property of the gate for a solo build: a gate
reproducible only by pushing is a gate that gets bypassed.

Human stops that remain regardless: Plan Approval, summary confirmation,
verification-command selection, and any failure.

---

## Settled here

**The Macrobenchmark harness: not built.** The approved plan framed this as a
two-way choice and I closed it one way at Units Generation without asking,
which the review correctly called an overstep. Put back to the human, it was
answered on 2026-10-23: *"Manual pilot check instead — No harness. PU-3.6
carries an explicit named manual check during the pilot, and D4 stays focused
on the offline queue and the conflict screen."*

So PU-3.6 has **no automated verification in V1**. Its verifier is a named
manual check in D4's Definition of Done: a full batch's attendance marked on a
low-end device during the pilot, timed, with the result written down. Both
options were acceptable per the affirmed posture; what remains **not**
acceptable is discharging a performance obligation with a Compose correctness
test, and recording "no automated verifier" openly is what keeps that
distinction honest rather than quietly eroded.

## Assumptions & Open Questions

- **Assumed**: D3 before D4, on the fee-revision argument. The DAG permits
  either.
- **No schedule is stated.** Four Bolts of real velocity data now exist in
  this project; an invented range would be less honest than deriving one from
  that.
