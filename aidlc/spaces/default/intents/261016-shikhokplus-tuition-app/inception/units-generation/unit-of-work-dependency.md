# Unit Dependency Topology

**Stage**: units-generation (2.7)
**Phase**: Inception
**Depth**: Comprehensive

> **Topology only.** This artifact states what *can* depend on what. It does not
> pick a build order and does not identify a critical path — those are Delivery
> Planning's (2.9) economic decisions, made with this DAG as input. Ideation's
> brief published a PU-level order with a named critical path; that order is not
> restated here, deliberately.

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` — the Unit catalogue
- [upstream] `inception/domain-design/components.md` and `decisions.md`
- [upstream] `inception/user-stories/stories.md`

---

## The edge block

```yaml
units:
  - name: money-core
    kind: library
    depends_on: []
  - name: api-contract
    kind: spec
    depends_on: [money-core]
  - name: identity-and-access
    kind: service
    depends_on: [api-contract]
  - name: batches-and-enrollment
    kind: service
    depends_on: [identity-and-access, money-core]
  - name: sessions-and-attendance
    kind: service
    depends_on: [batches-and-enrollment]
  - name: exams-and-marksheets
    kind: service
    depends_on: [batches-and-enrollment]
  - name: fee-cycles-and-ledger
    kind: service
    depends_on: [batches-and-enrollment, money-core]
  - name: payment-claims-and-verification
    kind: service
    depends_on: [fee-cycles-and-ledger]
  - name: teacher-insights
    kind: service
    depends_on: [payment-claims-and-verification, exams-and-marksheets]
  - name: release-packaging
    kind: packaging
    depends_on: [identity-and-access]
  - name: privacy-and-governance
    kind: spec
    depends_on:
      - identity-and-access
      - batches-and-enrollment
      - sessions-and-attendance
      - exams-and-marksheets
      - fee-cycles-and-ledger
      - payment-claims-and-verification
      - teacher-insights
```

**Validated**: 11 units, every `depends_on` name declared, no self-dependency,
single root (`money-core`), acyclic by topological sort.

## The shape

```
U1 money-core
 └─> U2 api-contract
      └─> U3 identity-and-access          [walking skeleton]
           ├─> U10 release-packaging       (independent of all feature work)
           └─> U4 batches-and-enrollment
                ├─> U5 sessions-and-attendance  ─┐
                ├─> U6 exams-and-marksheets      │ mutually independent
                └─> U7 fee-cycles-and-ledger    ─┘
                     └─> U8 payment-claims-and-verification
                          └─> U9 teacher-insights
                               (U9 also needs U6)

U11 privacy-and-governance  <- joins from U3, U4, U5, U6, U7, U8, U9
```

## Edges that are not obvious

Three edges carry reasoning worth stating, because each would plausibly be drawn
differently:

- **`api-contract -> money-core`.** The annotated Pydantic money type is the
  thing the schema serializes. The contract cannot assert "money is a JSON
  string on both sides" before the type that guarantees it exists.
- **`teacher-insights -> exams-and-marksheets`.** US8.4 (next upcoming exam)
  needs U6 and nothing else — the stories explicitly corrected an earlier error
  here, noting the bundled story's dependency was wrong. Carrying all four
  analytics views plus dues in one Unit means U9 inherits both edges.
- **`teacher-insights -> payment-claims-and-verification`, not
  `fee-cycles-and-ledger`.** Earnings, trend and collection rate are computed
  over *received* and *waived* amounts, which exist only once a teacher has
  approved something. Depending on U7 alone would understate it.

The two money edges (`batches-and-enrollment -> money-core`,
`fee-cycles-and-ledger -> money-core`) are redundant through `api-contract`.
They are stated explicitly because they are **import-boundary** dependencies
rather than transport ones: `Batch.default_fee` and `Enrollment.fee_amount` are
Money values and their owning components declare that structurally.

## The wide fan-in on `privacy-and-governance`

U11's seven incoming edges are the decision, not laziness. Its central test
iterates the live schema and asserts every table carries both a disposition and
a retention class. That test is **vacuous until the last table exists**, so
depending on everything is what makes it meaningful.

This creates a real tension that Delivery Planning must handle: U11 is
topologically terminal *and* release-blocking [D-41, RC-4, RC-5]. Flagged here,
not resolved — resolving it is a sequencing decision.

## Integration points

| Between | Integration point |
|---|---|
| U1 and every money-carrying Unit | The `Money` type and its two serialization chokepoints; enforced by import-boundary check rather than convention |
| U2 and every `service` Unit | The committed OpenAPI schema; each Unit's routes must appear in it and pass the schema-diff gate, the route-enumeration test and the schema-wide no-profile-field assertion |
| U3 and every later Unit | The resolved lens, handed to handlers as a data dependency carrying the scoping value — not a side-effecting guard |
| U4 and U5/U6/U7 | `Enrollment` as the privacy pivot: every teacher-facing read downstream is keyed on `enrollment_id`, never on an account id |
| U7 and U8 | The append-only ledger: U8 writes claims and verifications, U7 owns every `LedgerEntry` write |
| U7/U6 and the FCM adapter | Best-effort, post-commit, outside the request transaction; never fails its caller |
| Every table-owning Unit and U11 | Each table must appear in both Governance manifests; a new table reddens CI until its disposition is decided |

## Parallelisable sets

Units with no dependency path between them in either direction. **Parallelisable
here means "safe to reorder or interleave without a merge hazard"** — this is a
solo build, so it does not mean staff concurrently.

- **{U5 `sessions-and-attendance`, U6 `exams-and-marksheets`, U7
  `fee-cycles-and-ledger`}** — the main fan-out once U4 exists. The PU-level
  brief already identified this one.
- **{U10 `release-packaging`} against every feature Unit (U4–U9)** — U10 needs
  only a buildable app and is independent of all feature work thereafter. This
  is the opportunity the PU-level graph hid, and it is the useful one: it
  decouples the whole Play-release toolchain from feature delivery.
- **{U6, U8}** and **{U6, U7}** remain independent past the three-way fan-out:
  U6 never joins the money path, and U9 is where the exam and money branches
  finally meet.
- **{U5, U9}** and **{U10, U11}** are independent by the same reasoning.

Strict chains, not parallelisable: `U1 -> U2 -> U3`, and `U7 -> U8 -> U9`.
U11 is a strict join after everything.

## The walking skeleton

**U3 `identity-and-access`**, and it can run before any later Unit exists.

- Its only predecessors are U1 (a pure value type with no I/O and no database)
  and U2 (a schema plus CI gates). Neither is a running system and both are
  buildable with nothing else present, so U3 is the first Unit that **runs** —
  which is what `org.md` requires of the first Unit.
- It contains the full scope `team.md` binds the skeleton to, in one Unit: a
  Compose screen calling a real FastAPI endpoint reading a real PostgreSQL row
  through real OTP auth on the real Lightsail host, with all seven abuse
  controls and their adversarial tests, datastore-backed counters, the global
  ceiling and its sub-ceilings, JWT `kid` with two verification keys, one
  Alembic migration applied from zero, and both language bundles on screen one.
- **It stands alone at runtime, and U3's migration is what makes that true.**
  Lens resolution *reads* Identity, Ownership and Enrollment — `components.md`
  is explicit that Authorization "reads from Identity, Ownership and Enrollment
  to resolve a lens" — so the resolver issues real queries against the `Owner`
  and `Enrollment` tables even when both return nothing. **Empty is not the
  same as absent**: a query against a table that does not exist fails, so
  "U4 populates them" is not sufficient on its own.

  U3's first Alembic migration therefore **creates the `Owner` and `Enrollment`
  tables as well as its own identity tables**, as empty structures that U3 reads
  and does not write. U4 owns their behaviour — creation, enrollment, the
  dormant-account path, every write — and extends their columns as it needs
  them. This is table-shape only, not an ownership transfer, and it is stated
  here because it is a real scope item of U3 rather than a documentation
  nicety.

  With those tables present the resolver's empty reads are meaningful: a teacher
  with no batches and a person with no enrollments are valid resolvable states,
  and FR1.4 ("an account owning no batches is never offered a teacher lens") is
  the behaviour the skeleton demonstrates. So the skeleton proves the
  computed-lens mechanism, which `team.md` calls the single most structurally
  unusual decision in the system.

  **This does not add a `U3 -> U4` edge.** The dependency runs the other way:
  U4 depends on U3 because it builds on the identity and lens machinery U3
  establishes. U3 creating two empty tables it only reads is not a dependency on
  U4's code, and adding an edge would make the graph cyclic while describing
  nothing real.
- It is verified by the recorded Construction Verification Command as a real
  end-to-end result on a device or emulator against the real backend — not a
  passing test suite and not a design review.

## Assumptions & Open Questions

- **The FCM adapter has a latent U6/U7 ownership question that is deliberately
  not an edge.** Push notifications split by trigger: the fee-due reminder
  (U7) and the marks-entered alert (U6). Whichever Unit is built first owns the
  adapter, the `UNREGISTERED`-deletes-the-token rule and the never-fail-the-
  caller rule; the other reuses it. No `U6 -> U7` edge was added, because that
  would destroy the three-way parallel set for a shared adapter rather than a
  real data dependency. Delivery Planning should know this.
- U11's terminal-and-release-blocking tension, as above.
