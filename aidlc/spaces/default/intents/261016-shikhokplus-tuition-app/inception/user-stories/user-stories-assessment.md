# User Stories — Execution Assessment

**Stage**: user-stories (2.4)
**Phase**: Inception
**Date**: 2026-10-17

---

## Decision

**Execute.**

---

## Rationale

The stage's skip conditions are pure refactoring, isolated bug fixes,
infrastructure-only work, or developer tooling. This project is none of those.
It is a greenfield, user-facing product with three distinct personas whose
rights over the same records are deliberately asymmetric, which is the exact
case stories exist to clarify.

Three specific signals, each sufficient on its own:

**Three personas with asymmetric rights over shared records.** [desc §4–§8] A
teacher writes; a student and a guardian read the same rows and may write
exactly three things. The asymmetry is the product's hardest design constraint,
and requirements state it as rules while stories state it as behaviour from each
party's side. Both are needed: FR9.4 says the correction mechanism never extends
to student-authored content, but only a story says what the guardian actually
sees when a teacher corrects a mark.

**Complex business logic in the money paths.** [FR5, FR6, FR9] Carry-forward,
partial approval, waiver, mid-period departure and correction history interact.
The requirements enumerate them; acceptance criteria in Given/When/Then form are
what make them testable, and the affirmed testing posture requires test-first
for exactly these paths.

**A read-optimised client that must absorb a future write path.** [desc §5]
Student and guardian views are read-only except three writes, and batch
messaging must later land as a new write path rather than a reshaping. Stories
written per persona make that boundary visible in a way a requirements list does
not.

---

## Factors considered

| Factor | Assessment |
|---|---|
| Project type | Greenfield product, two surfaces (Android + backend) |
| User-facing scope | Entirely user-facing; every requirement has a human actor |
| Persona count | Three active (teacher, student, guardian), plus a deferred platform owner with no V1 surface |
| Business-logic complexity | High in the fee ledger; moderate elsewhere |
| Cross-team coordination | None — solo build, so stories serve specification rather than coordination |
| Requirements maturity | 84 FR and 17 NFR with stable IDs, approved |

The cross-team factor is the one that does **not** apply: with a solo build
there is no team boundary for stories to coordinate across. Their value here is
specification and testability, not alignment.

---

## Where stories add the most value

In priority order, based on where the requirements are rules rather than
behaviour:

1. **The privacy boundary from each side.** [FR9.4, NFR14, desc §4] The rules
   say what must not happen. Stories say what each party sees instead, which is
   what gets built and tested.
2. **The money paths' edge behaviour.** [FR5.6, FR6.6–FR6.8, FR9.1–FR9.3]
   Mid-period departure, reduced approval, waiver and correction history each
   need Given/When/Then criteria before they can be test-first.
3. **The guardian's multi-child, multi-number model.** [FR2.14–FR2.18] This
   emerged from a model change during Requirements Analysis and is the newest,
   least-exercised part of the specification.
4. **Dormant-account behaviour.** [FR1.7–FR1.11] A record that exists but is
   not yet claimed behaves differently for every persona, and the mistyped-number
   case is specified as correct behaviour rather than an error.
5. **The three student and guardian writes.** [desc §5] Narrow by design, and
   the boundary matters more than the features.

---

## Assumptions & Open Questions

- The platform-owner persona has no V1 surface [intent: Q20], so it gets a
  persona entry for completeness but no stories. If that is wrong, the stories
  are missing an actor entirely. [assumption]
- Stories will carry MoSCoW priorities, but every V1 capability was already
  affirmed Must Have at Scope Definition [scope: Q7]. Priorities here therefore
  describe sequencing value within an all-Must-Have set rather than a cut line,
  and the real MVP boundary is Delivery Planning's decision. [assumption]

## Sources

- [desc] Initial description, §4–§8.
- [FR*], [NFR*] `inception/requirements-analysis/requirements.md`.
- [intent: Q20] `ideation/intent-capture/intent-capture-questions.md`.
- [scope: Q7] `ideation/scope-definition/scope-definition-questions.md`.
