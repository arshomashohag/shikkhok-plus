# NFR Requirements Questions — api-contract (U2)

**Stage**: nfr-requirements (3.2)
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`
**Phase**: Construction
**Depth**: Comprehensive

> U2 is a `spec` Unit: **not deployed**. No process, no endpoint, no database,
> no network. It produces the committed OpenAPI 3.1 document, the error
> taxonomy as code with its single handler, the schema-diff gate, and four
> assertions that iterate the generated schema. Most inception NFRs describe a
> running service and do not bind here — which is a finding to record, not an
> empty file to apologise for.
>
> What makes this Unit unusual: its NFRs are mostly **about other Units**. A
> gate written here fails in B3 or B9, which is the entire reason the Unit
> exists. That inverts the normal question from "what must this Unit achieve"
> to "what must this Unit make impossible for everyone else".

---

## Q1 — Which inception NFRs actually bind to a Unit that is never deployed?

NFR1–NFR17 were written for the system. A build-time artifact has no
availability target, no throughput figure and no alerting threshold.

[Answer]: **Four bind directly.**

- **NFR16** (`/v1/` additive; an installed client handles unknown fields
  rather than failing to parse) — this is U2's own requirement more than
  anyone's, because the committed schema and its diff gate are the only
  mechanism that can detect a breaking change before it ships.
- **NFR14** (privacy boundary structural in three layers) — U2 owns the
  third layer, "teacher-facing schemas without profile fields", and asserts
  it schema-wide [BR2.4].
- **NFR9** (money as fixed-point decimal, JSON string in transit, never
  float) — U1 owns the type; U2 owns the **schema-level** assertion, which
  is the half an import rule cannot see [BR2.2].
- **NFR17** (backend coverage: 80% line, branch coverage on the
  authorization layer) — the route-enumeration harness and the four
  fixtures are this Unit's testable surface.

**Two bind partially and are worth stating rather than waving through:**

- **NFR3** (Bangla and English; no hardcoded user-facing strings) — U2 does
  not render anything, but `message_key` rather than `message` [BR1.3] is
  precisely what makes NFR3 achievable for errors. A server-authored English
  string cannot be localized by the client, so an error contract that emitted
  one would make NFR3 unreachable no matter what the Android Bolts did.
- **NFR13** (15-minute access token; 30-day rotating refresh) — U2 owns
  neither, but BR1.6 and BR3.1 encode two consequences of it: the
  `retryable: false`-on-401 reconciliation, and the refresh route's
  lens-exempt-but-authenticated status.

**Everything else is `N/A` with a structural reason** — no process, no
request path, no state, no deployment — recorded per NFR rather than dropped,
so a later reader can see the analysis happened.

---

## Q2 — What is the asset under protection in `security-requirements.md` for a Unit with no data?

This is the stage's review artifact, so the answer decides what gets
adversarially reviewed.

[Answer]: **The asset is the set of guarantees later Units cannot violate
without failing a build.** U2 holds no data, authenticates nobody and
authorizes nothing, so a security document listing access controls would be
boilerplate. The honest version treats U2's gates as the control, and asks the
only question that matters about a control: *can it be satisfied without being
true?*

That question has teeth here, because **every one of U2's four schema
assertions iterates an empty set in B2.** There are no routes, no money
endpoints and no response schemas yet. Four green checks that have never
examined anything is the realistic failure mode, and it is worse than no
checks, because it produces documented confidence.

So the security requirements centre on three properties:

1. **Each gate is proven to fire** by a committed fixture that violates it
   [BR4.1], asserting *which* violation was reported rather than merely that
   something failed.
2. **Each gate is decidable**, not a judgement an implementer makes — the
   `$ref` predicate rather than "carries money" [BR2.2], annotation
   resolution via `get_type_hints` rather than a name match [BR3.2].
3. **No gate can be satisfied by weakening it** — the allowlists are fixed
   at exactly five and exactly one [BR3.1], so a sixth entry is a diff
   against a stated number rather than a line nobody notices.

---

## Q3 — The schema-diff gate: what exactly fails, and can it be bypassed?

`team.md` states that "a stale committed schema is worse than none, because
the contract tests then pass against fiction."

[Answer]: **The committed document must equal the generated one byte for byte,
and CI fails otherwise** [BR2.1]. Two properties make this real rather than
ceremonial:

- **It runs in CI, not only locally.** A gate reproducible only by pushing is
  a gate that gets bypassed; a gate that runs only locally is one that gets
  skipped on a bad afternoon. `team.md`'s "one command, local and in CI" rule
  applies directly.
- **Regeneration is the fix, never editing the committed file.** The
  committed file is an *output*. An implementer who hand-edits it to make the
  diff pass has inverted the control into a rubber stamp, and this is the
  single most likely misuse — it looks like fixing the gate.

**It can be bypassed in exactly one way worth naming**: committing a
regenerated schema without reading the diff. That is not a technical hole and
no check closes it; it is why the diff exists in a pull request where the one
reviewer sees it. Stating it plainly is better than implying the gate is
stronger than it is.

---

## Q4 — Does this Unit have any runtime NFR at all, given the error handler is runtime code?

The handler is the one piece of U2 that executes in production.

[Answer]: **Yes, and exactly one: the handler must not become a failure mode
of its own.** It sits on every error path in the system, so:

- It performs **no I/O** — no database call, no network call, no file read.
  An error handler that can itself fail turns a handled 403 into an unhandled
  500, and does so precisely when the system is already degraded.
- It is **total over the taxonomy**: five classes in, a response out, with no
  branch that can fall through. BR1.1 closes the hierarchy, which is what
  makes totality checkable rather than hoped for.
- Its own `except Exception` is one of the **two sanctioned sites** in the
  backend, the other being the scheduled job's top level.

No latency target is set for it. A target would be unmeasurable here (U2 has
no endpoint to measure) and the real constraint is structural: no I/O means
its cost is bounded by construction rather than by a number someone would
have to defend.

---

## Q5 — NFR17 asks for coverage. What is the coverage target for a Unit whose code is mostly tests?

[Answer]: **The 80% line floor applies to U2's runtime code — the exception
classes and the handler — and that code is small enough to reach 100%
comfortably.** The gates themselves are tests, and measuring a test suite's
coverage of itself is meaningless.

The meaningful target is **not a percentage at all**: it is the four fixtures
of BR4.1. A gate's correctness is demonstrated by its firing on a known
violation, not by a line-coverage figure, and this is the one Unit where the
distinction is sharp enough to be worth stating in a requirements document.

The authorization-layer branch-coverage requirement from NFR17 lands on **U3**,
which owns lens resolution. U2 owns the `Lens` types only; there are no
branches in a type declaration.

---

## Q6 — Is there a tech-stack decision left to make here, or were they all made upstream?

[Answer]: **Three remain, and all three are narrow.**

- **The OpenAPI generation path.** FastAPI generates the document from the
  route and model definitions; the committed file is that output. The
  decision is that **no hand-authored schema fragment is ever merged into
  it**, because a hand-authored fragment is exactly what the diff gate cannot
  distinguish from drift.
- **The schema-diff mechanism.** A byte comparison of the generated document
  against the committed one, rather than a semantic differ. A semantic differ
  would need its own correctness argument and would silently accept a
  reordering that changes nothing — but a byte comparison needs **stable
  serialization**, so key ordering must be deterministic or the gate produces
  false failures and gets disabled.
- **Schemathesis's scope**, already fixed by Functional Design [BR4.2] and
  restated here because it is a tooling decision: it validates conformance and
  **never counts as privacy coverage**, since a response wrongly carrying
  profile fields matches its own declaration perfectly.

Everything else — Python 3.12, FastAPI, Pydantic, pytest, Ruff, mypy — was
decided at B1 and is inherited unchanged.

---

## Assumptions & Open Questions

**None.** [assumption] OQ-B1-1, carried as open through B1 and this Unit's
Functional Design, **closed on 2026-10-18** with the Bangla money rendering
specification recorded at `construction/money-core/nfr-design/security-design.md`
§A.6. It affected the *content* of a `*_display` string, never the structural
pairing rule [BR2.3] that this Unit asserts, so no U2 artifact changes as a
result.

---

## Consolidated Summary Confirmation

U2 is a `spec` Unit that is never deployed, so most inception NFRs do not
bind — recorded per NFR with a structural reason rather than dropped. **Four
bind directly**: NFR16 (the committed schema and its diff gate are the only
mechanism that detects a breaking change before it ships), NFR14 (U2 owns the
third layer of the privacy boundary, asserted schema-wide), NFR9 (U1 owns the
money type; U2 owns the schema-level assertion, which is the half an import
rule cannot see), and NFR17. **Two bind partially**: NFR3, because
`message_key` rather than `message` is what makes localized errors reachable
at all; and NFR13, through the 401 reconciliation and the refresh route's
exempt-but-authenticated status.

**The security artifact's asset is the set of guarantees later Units cannot
violate without failing a build**, because U2 holds no data and authorizes
nothing. The sharp risk is that **all four schema assertions iterate empty
sets in B2** — four green checks that have never examined anything, which is
worse than no checks because it manufactures confidence. The requirements
therefore centre on each gate being proven to fire by a committed fixture,
being decidable rather than a judgement, and not being satisfiable by
weakening it.

The schema-diff gate fails on any byte difference and runs in CI rather than
only locally. **Regeneration is the fix; hand-editing the committed file
inverts the control into a rubber stamp**, and that is the most likely misuse
because it looks like fixing the gate. The one bypass worth naming — committing
a regenerated schema without reading the diff — is closed by review, not by a
check, and saying so is better than implying the gate is stronger than it is.

The error handler is U2's only runtime code and carries one requirement: it
performs **no I/O**, because a handler that can fail turns a handled 403 into
an unhandled 500 exactly when the system is already degraded. No latency
target is set, since the structural constraint bounds its cost better than a
number anyone would have to defend. Coverage: the 80% line floor applies to
the handler and exception classes; the meaningful target is the four fixtures,
not a percentage. NFR17's authorization branch coverage lands on U3.

Three narrow tech-stack decisions remain: no hand-authored schema fragment is
ever merged into the generated document; the diff is a byte comparison, which
requires deterministic key ordering or it produces false failures and gets
disabled; and Schemathesis validates conformance and never counts as privacy
coverage.

Does this all look correct?

[Answer]: Looks correct

---

## Assumption Confirmation

A. Accept assumptions
B. Convert to follow-up questions

[Answer]: A. Accept assumptions
