# Units of Work — the six remaining deliverable units

**Stage**: units-generation (2.7)
**Phase**: Inception
**Record**: 261022-remaining-slices

> **The units are already decided.** D1–D6 come from the re-cut approved at
> Delivery Planning on 2026-10-22, and this stage does not re-derive them. It
> writes them in the form the Construction stages consume, with the schema and
> lens decisions from Domain Design folded in.

## Sources

- [upstream] `inception/domain-design/components.md` and `decisions.md` —
  ADR-009..014
- [upstream] `inception/requirements-analysis/requirements.md` — FR0, FR1a
- [upstream] `inception/user-stories/stories.md` — US1.10–US1.16
- [prior] `261016-shikhokplus-tuition-app/inception/delivery-planning/bolt-plan.md`

---

## The decomposition shape

**A unit is one user-visible capability**, delivered as API, screens and tests
together [FR0.1]. That is the change the re-cut made: the previous eleven units
were typed by backend layer, which let a unit be technically done and
practically unusable.

Four units are **built and merged** and are not re-planned: `money-core`,
`api-contract`, `identity-and-access`, `batches-and-enrollment`.

---

## The edge block

```yaml
units:
  - name: signing-up-and-joining
    kind: service
    depends_on: []
  - name: running-a-batch
    kind: ui
    depends_on: [signing-up-and-joining]
  - name: collecting-fees
    kind: service
    depends_on: [running-a-batch]
  - name: teaching-and-recording
    kind: service
    depends_on: [running-a-batch]
  - name: knowing-how-it-is-going
    kind: service
    depends_on: [collecting-fees, teaching-and-recording]
  - name: releasing-safely
    kind: spec
    depends_on:
      - signing-up-and-joining
      - running-a-batch
      - collecting-fees
      - teaching-and-recording
      - knowing-how-it-is-going
```

**Validated**: six units, every `depends_on` name declared, no self-dependency,
single root (`signing-up-and-joining`), acyclic by topological sort.

Every unit also depends on the four already merged. Those edges are omitted
rather than repeated six times: they are satisfied before any of this starts,
and listing them would make the graph describe history rather than order.

---

## Unit responsibilities

### D1 `signing-up-and-joining` — `service`, L — the root

Nothing else can be demonstrated until an account can exist. Today a teacher
exists only by hand-inserting a database row.

**Schema** [ADR-009, ADR-010, ADR-013]. Two enum columns on `Enrollment`,
`student_decision` and `guardian_decision`, each
`pending | accepted | declined`, `NOT NULL`, **no column default**, backfilled
conditionally: `accepted` where the link already names an account, `pending`
otherwise. A nullable `address` on `Profile`. One Alembic migration.

**Authorization** [ADR-011, ADR-014]. `InvitationLens` as a fourth `Lens`
subtype carrying `enrollment_id`, resolved by its own statement. **And the
change without which the rest is decoration**: `_LENS_QUERY` and
`_SUMMARY_QUERY` both gain `decision = 'accepted'` predicates, so a pending
seat grants no lens and `GET /v1/me` counts no unaccepted seat.

**API.** `POST /v1/accounts` taking role, name, phone and address, creating the
`Account` and `Profile`, plus an `Owner` row only for Teacher. A lookup the
signup form calls before rendering, naming neither teacher nor batch. Accept,
decline and un-decline endpoints. Signup's own per-number and per-IP ceilings.

**Screens.** `O1` in five states, `O2`, `O3`, and `O4 · Invitations` in seven.

**Tests, test-first by the predicate** — acceptance transitions are
authorization decisions [team: Testing Posture]. The adversarial one ADR-014
names: an account on only `pending` or `declined` links resolves no student or
guardian lens and reports zero counts. Plus: the OTP path stays byte-identical
for known and unknown numbers after signup exists; picking Teacher creates an
`Owner` and Student does not; a declined seat is not re-prompted on re-add but
is still acceptable by its own holder.

**What D1 does NOT own.** Any money consequence of declining. AC1.14.2a put a
"minimum ledger reversal" here; there is no ledger table until D3 creates one,
so D1 owns the decision-column transition and nothing more. US1.14 is D3's in
full — see the story map.

**Done when.** Someone installs the APK, signs up as a teacher on an unknown
number, and reaches their own empty batch list — and a student whose teacher
added them signs up, sees the name pre-filled with the role locked, and accepts.

### D2 `running-a-batch` — `ui`, M

Screens over endpoints that already work. **No new backend capability** beyond
the roster's acceptance state.

`T6` batch list, `T7` single batch with its roster including the accepted count
and the declined row, `T8` add student, create-batch, remove-student, and `G1`
guardian child home. Settles OQ-7, the guardian-child route shape.

**Done when.** A teacher creates a batch, adds two students, sees them on the
roster with their state, and removes one nobody claimed.

### D3 `collecting-fees` — `service`, XL

Append-only `LedgerEntry` with its seven kinds; the thin `FeeCycle` with its
`(enrollment_id, period)` unique constraint and `ON CONFLICT DO NOTHING`;
calendar-month periods with the short-month clamp; the daily self-healing job;
credit grant and apply; two-sided carry-forward; the server-computed status
enum. Payment claims, verification, partial approval, over-approval becoming
credit. Owns the FCM adapter per OQ-4. `Money.format(locale)` becomes blocking
here.

**Inherits US1.14 in full** [AC1.14.1 through AC1.14.4], including what a
decline does to generation and to accrued cycles. D1 sets the decision; D3 is
where that decision first touches money.

**Done when.** A teacher sees what each student owes, a student submits a
payment, the teacher approves it for less than claimed, and the remainder
carries forward with the enrollment total unchanged — and a declined seat
generates no further cycle, with what accrued voided as a reversal.

### D4 `teaching-and-recording` — `service`, XL

Sessions from weekly recurrence plus ad-hoc; the topic log; the atomic roster
write with optimistic concurrency; the four-state offline queue surviving
restart; the refuse-on-conflict rule and its resolution screen, where re-apply
carries a fresh `client_mutation_id`. Exams, mark entry with correction
history, the anonymised marksheet, the `marksheet_visible` toggle.

**PU-3.6 carries an explicit manual pilot check, not a Macrobenchmark**
[human, 2026-10-23]. The affirmed posture offered two acceptable verifiers and
the human chose the manual one, which keeps D4 focused on the offline queue and
the conflict screen — the genuinely novel work — rather than adding a
benchmarking harness to a unit already sized XL.

**The obligation is not weakened, only differently verified.** D4's Definition
of Done includes a named manual check: marking a full batch's attendance on a
low-end device during the pilot, timed, with the result recorded. What remains
forbidden is discharging it with a Compose correctness test, which asserts
behaviour and not latency. No Macrobenchmark harness is built in V1.

### D5 `knowing-how-it-is-going` — `service`, M

Cross-batch dues driven by outstanding balance and not active status; monthly
earnings and trend; next upcoming exam. Carries OQ-2: the `collection_rate`
field does not ship until its arithmetic is settled. Plus the outstanding half
of release packaging — the 15 MB download-size assertion, Syft and the ZAP
baseline. Each measures a nearly-finished app, which is why they belong here.
**No Macrobenchmark harness**: PU-3.6 takes a manual pilot check instead
[human, 2026-10-23].

### D6 `releasing-safely` — `spec`, L — terminal and release-blocking

Both Governance manifests complete and the schema-iterating test green against
the final schema. Both account-deletion paths with a test per path asserting
deletion removes what the Data Safety form claims and retains what the policy
discloses. The idempotent chunked purge. **The privacy policy generated from
the manifests** — including [ADR-012]'s disclosure that a declined seat keeps
the teacher-typed name, with a test asserting the generated text says so.
Data Safety form content, Play declarations, deletion-confirmation copy.

---

## Standing per-unit obligations

Not units, because they apply to every unit that adds a screen or a table.

| Obligation | Applies to | Verifier |
|---|---|---|
| **Per-screen check** | every screen-bearing unit | a row in `docs/delivery/bangla-layout-check.md` covering the Bangla layout and the named artboard; a screen with no row means an incomplete unit [FR0.2] |
| **Governance row per new table** | every table-creating unit | the schema-iterating test, which fails on a live table with no disposition and retention class |
| **Accessibility and back-stack** | every screen-bearing unit | AC9.4.2 is a privacy case in navigation clothing: Back must never land in another lens's data |
| **Tests per the affirmed predicate** | every unit | test-first where the output is knowable and a wrong answer is a money or authorization error |

---

## Assumptions & Open Questions

- **The four merged units are not re-planned.** Their edges are omitted from
  the graph deliberately, so the order describes what is left rather than what
  happened.
- **D1 is `service` rather than `ui`** despite shipping four screens, because
  its schema and authorization changes are the substance and the screens follow
  them. D2 is the reverse and is typed `ui`.
- **Closed by the human, 2026-10-23**: no Macrobenchmark harness in V1. The
  D5-versus-D4 ordering problem dissolves with it, and PU-3.6 carries a named
  manual pilot check in D4's Definition of Done instead.

---

## What the review changed

Two Critical findings, both identity rather than analysis — the decomposition
was sound and the labelling was not. Plus two Major, one of which is yours to
settle.

| Finding | What was wrong | Closed by |
|---|---|---|
| **No unit carried a short ID or directory name** | Units were identified three ways at once and `D1` resolved to no declared unit, so no downstream tool could join a story-map row to a filesystem path. | A unit-identity table in the story map: `D1` / `signing-up-and-joining` / `d1-signing-up-and-joining`. **The directory half of that was wrong and was corrected on 2026-10-23** — see below. |
| **Traceability failed with 34 findings** | Every coverage target was prose rather than a declared unit name, and the story map carried no story-to-unit mapping the parser could read — its tables had Story and What-it-is columns and never named the unit on the row. The one mechanism that proves no story was dropped was proving nothing. | Rewritten to the `Story / Unit ID / Unit / Directory / Note` shape. **All three sensors now pass.** |
| **D6 was missing two obligations** | The acceptance columns' disposition-and-retention entry, and the two external open questions the approved plan made start conditions for that unit. | Added below |
| **`US1.8` was in `upstream_ids` unexplained** | It is the prior record's story, cited only in an INVEST note. | A row saying so |

**The fix took five attempts, and the reason is worth recording:** I guessed
at the parser's contract from its error message rather than reading it. The
message said "no story-to-unit mappings"; the actual rule is that a cell must
match a declared unit name bounded by whitespace or punctuation, which a
backticked `` `signing-up-and-joining` `` does not. This project already
carries a learning about exactly that, from the contract-design stage on
2026-10-18. Reading `.claude/tools/aidlc-sensor-traceability.ts` took one
minute and ended it.

### The directory name, corrected at Functional Design

*(2026-10-23.)* The identity table gave the directory as
`d1-signing-up-and-joining`, and Construction rejected it on its first unit.
The traceability sensor reads the directory segment of the artifact path and
matches it against the names declared in the YAML block of
`unit-of-work-dependency.md` — the block Construction walks. A prefixed
directory matches nothing there, so the per-unit artifacts resolved to no
declared unit.

**The directory is the declared name, unprefixed.** The `D`-number remains the
ordering label people say, and remains correct in the **Bolt slug**
(`d1-signing-up-and-joining`), which names a branch and a squash commit rather
than a path and where the ordering genuinely helps.

Worth recording plainly: this stage added the identity table precisely because
a unit was identified three ways at once, and then gave one of the three a
fourth spelling. A table that reconciles names is only as good as its agreement
with the tool that consumes them, and nothing checked that agreement until a
sensor did.

### D6's added obligations

- **Disposition and retention for `student_decision` and `guardian_decision`.**
  They sit on `enrollment`, whose manifest entry exists, so the schema-iterating
  test will not fail — which is exactly why this needs saying: the columns would
  pass the mechanical check while the generated policy stayed silent about what
  a decision value reveals.
- **OQ-1 and OQ-5 must close before D6 starts.** The approved plan made these
  start conditions, not completion criteria. OQ-1 (does `PaymentClaim.transaction_id`
  survive the claimant's deletion?) ideally closes before D3, so the
  payment-history schema is not revisited.

### Put back to the human, and answered

**I moved the Macrobenchmark harness from D5 to the start of D4 on my own
judgement, and the review was right that it was not mine to close.** The
approved plan framed it as a live two-way choice — the harness at D4's start,
**or** an explicit manual pilot check — with both acceptable. I argued one
side only, and adding a benchmarking harness to a unit already sized XL is a
cost that wants a person's agreement.

**Asked at this gate and answered on 2026-10-23: the manual pilot check.** D4
loses the harness and PU-3.6 gains a named manual verifier. What the overstep
cost was one question; what it would have cost unflagged is a unit's worth of
tooling nobody chose.
