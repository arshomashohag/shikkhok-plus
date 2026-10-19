# Functional Design Questions — api-contract (U2)

**Stage**: functional-design (3.1)
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`
**Phase**: Construction
**Depth**: Comprehensive

> U2 is a `spec` Unit: **not deployed**. It produces a build-time artifact —
> the committed OpenAPI document — and the CI gates that keep every later
> Unit honest against it. It owns no endpoint of its own, which is the point:
> the guarantees it establishes cover routes added in Bolts that do not exist
> yet.

---

## Q1 — The contract contradicts itself on 403 versus 404. Which is right?

`contract-summary.md` says both of these:

- **§ schema (line ~300)**: a resource the lens does not reach returns
  **403**, "also returned for a resource that does not exist under a lens
  that would reach it: a 404/403 distinction would be an existence oracle."
- **§ implementer notes (line ~873)**: calls it "the **404**-instead-of-403
  rule", reasoning that "returning 403 for a resource the caller may not see
  confirms the resource exists."

B2's Definition of Done repeats the second wording. They name opposite
statuses for the same situation.

[Answer]: **Both halves close the oracle; only one of them is implementable
as written, and it is the schema's.** Worked through:

- A split — 403 for unreachable, 404 for absent — **does** leak. Teacher A
  probes ids and reads 403 as a hit, enumerating teacher B's batches. Both
  halves of the contract agree this is wrong.
- **Always 404** closes it: the two cases are indistinguishable.
- **Always 403** closes it equally: also indistinguishable.

So the security property is satisfied by either uniform answer, and the
contradiction is about *wording*, not about a vulnerability. The schema
section wins because it is the normative artifact — it is what generates the
OpenAPI document and what the diff gate compares against — while line 873 is
a prose reminder that got its own rule's name backwards.

**Decision: a uniform `403` for both cases**, carrying `AuthorizationError`.
Two further reasons beyond "the schema says so":

1. **404 is not in the taxonomy at all.** The five classes map to five
   caller behaviours; adding a sixth status with no class behind it would
   mean the envelope's `code` and `retryable` have nothing to carry.
2. **403 is honest to an authenticated caller.** A teacher who mistypes
   their own batch id is told "not yours", not "does not exist" — the latter
   is actively misleading about data they *do* own.

The contradiction is recorded in `rules.md` rather than silently resolved,
because an implementer reading line 873 will otherwise "fix" this back.

---

## Q2 — What does this Unit actually produce, given it is not deployed?

[Answer]: Four things, and none of them is a running service:

1. **The committed OpenAPI 3.1 document** — the contract as a reviewable
   file, so a change shows up as a diff rather than being invisible.
2. **The error taxonomy as code** — five exception classes and the single
   handler mapping them to responses, so no endpoint writes its own
   try/except for them.
3. **The schema-diff gate** — committed must equal generated, or CI fails. A
   stale committed schema is worse than none, because the contract tests then
   pass against fiction.
4. **Three schema-wide assertions** that iterate the generated document
   rather than naming endpoints: the money pattern, the `*_display` pairing,
   and the no-profile-field privacy invariant.

The fourth is the one that justifies this Unit existing separately. A
per-endpoint test covers the endpoints someone remembered; iterating the
schema covers the endpoint added in B9 after everyone stopped thinking about
it.

---

## Q3 — The route-enumeration harness has no routes to enumerate yet. Is it still B2's?

[Answer]: **Yes, and that is exactly why it belongs here.** The harness runs
against the real application object at collection time, so it reddens CI on
the commit that adds an unlensed endpoint — which will be a commit in B3 or
later. Writing it in the Unit that *has* endpoints would mean writing it
after the first endpoint already exists, which is the wrong order: the gate
should predate the thing it guards.

With no routes, the harness asserts over an empty set and passes trivially.
That is a real risk — a check that has never fired is a check nobody knows
works — so it ships with a **fixture route that deliberately lacks a lens**,
asserted to be caught. Same reasoning as B1's import-gate fixtures.

`PUBLIC_ROUTES` is an explicit frozenset, empty in B2 and populated as the
public endpoints arrive. Adding to it is a reviewable, deliberate act.

---

## Q4 — How does the money-pattern assertion work before any money endpoint exists?

This assertion was authored at B1's NFR Design, which could not run it, and
added to B2's DoD at Code Generation.

[Answer]: Same shape as Q3 and the same honesty problem. It iterates the
generated schema for fields matching the money contract and asserts each
against `^[0-9]+\.[0-9]{2}$`, plus the rule that any `*_display` sibling is
accompanied by its canonical `amount` field.

With no money endpoint it passes over an empty set, so it also ships with a
**fixture schema** carrying a money field typed as a free-form string and a
`*_display` with no sibling, both asserted to fail. Without that, B2 would
record a green check that has never once looked at a real money field.

---

## Q5 — Which lens types does U2 define, given U3 owns lens resolution?

[Answer]: U2 defines the **type hierarchy** — a `Lens` base and the three
subtypes — and nothing that resolves one. U3 owns resolution, the database
query and the row-level-security context.

The split matters because the route harness matches on *the dependency's
return annotation being a `Lens` subtype*, never on the function's name. That
check needs the type to exist; it does not need anything that produces one.
Name-matching is how this check gets defeated by a rename, which is why the
type is the thing.

Response-schema separation rides on the same types: a lens type parameterizes
which response models an endpoint may return, so a teacher-lens endpoint
returning a student-private response is a type error rather than a review
finding.

---

## Q6 — Is the `retryable` boolean derived or stored?

[Answer]: **Derived from the exception class, at the handler, never set per
raise site.** That is the whole point of the taxonomy: retryability is
decided once by choosing a class, and every layer above reads it off the
type.

A per-raise-site boolean would let two raise sites of the same class disagree,
which is the condition the closed hierarchy exists to prevent. The handler
maps class → status → `retryable`, and that mapping is a single table.

---

## Q7 — Schemathesis is wired here. What is it allowed to count as?

[Answer]: **Conformance, and never privacy coverage** — stated in writing in
the artifact, because the distinction is easy to lose and expensive to lose.

A teacher-facing response schema that wrongly includes profile fields is
perfectly *conformant*: it matches its own declaration. Schemathesis would
pass it. What catches that is the schema-wide invariant of Q2.4, which
iterates the document and asserts no teacher-lens response carries a field
from the owner-private set.

So Schemathesis is kept for unexpected 500s, type and required-field drift,
and auth present on every route — and the artifact says plainly that a green
Schemathesis run is not evidence about privacy.

---

## Assumptions & Open Questions

**Carried from B1, unchanged**: the Bangla money rendering (OQ-B1-1). It
affects what the `*_display` pairing assertion checks the *content* of, not
whether the pairing rule holds. The pairing is structural and testable now.

---

## Consolidated Summary Confirmation

U2 is a `spec` Unit producing a build-time contract and the CI gates that
keep later Units honest: the committed OpenAPI document, the five-class error
taxonomy with its single handler, the schema-diff gate, and three assertions
that **iterate the generated schema** rather than naming endpoints — so they
cover routes added in Bolts that do not exist yet.

**A contradiction in the upstream contract is resolved here rather than
silently**: the schema section says 403 for both an unreachable and an absent
resource, while an implementer note calls it the "404-instead-of-403 rule".
Both close the enumeration oracle, so this is a wording conflict rather than
a vulnerability. The schema wins — it is the normative artifact, 404 is not
in the taxonomy, and 403 is honest to an authenticated caller who mistyped
their own id. The contradiction is recorded in `rules.md` so nobody "fixes"
it back.

The route harness and the money-pattern assertion both run against an empty
set in B2, so each ships with a **deliberately failing fixture** — a route
without a lens, and a money field typed as a free-form string. A check that
has never fired is a check nobody knows works. U2 defines the lens *types*;
U3 owns resolution. `retryable` is derived from the exception class at the
handler, never set per raise site. Schemathesis validates conformance and is
stated in writing never to count as privacy coverage.

Does this all look correct?

[Answer]: Looks correct

---

## Assumption Confirmation

A. Accept assumptions
B. Convert to follow-up questions

[Answer]: A. Accept assumptions
