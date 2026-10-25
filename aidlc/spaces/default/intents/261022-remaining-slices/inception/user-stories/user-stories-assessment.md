# User Stories — Assessment

**Stage**: user-stories (2.4)
**Phase**: Inception
**Record**: 261022-remaining-slices

## Decision: **Execute**, narrowly

## Rationale

The stage's own skip test asks whether stories add value: skip for pure
refactoring, isolated bug fixes, infrastructure-only work or developer tooling.
None of those describe this work — all six remaining units are user-facing, and
the whole point of the re-cut is that a unit is not done until a person can do
the thing on a phone.

But the ordinary reason to run this stage does not apply either. **45 stories
already exist**, written 2026-10-17, traced to requirements and gated. They
cover every capability D1–D6 will build, and their `US{n}.{m}` and
`AC{n}.{m}.{seq}` IDs are permanent traceability keys that four built Units
reference. Re-deriving them would be waste and renumbering them would break the
chain.

So this stage runs for the same reason Requirements Analysis did: **the
acceptance model contradicts stories that were written before it existed**, and
a contradicted acceptance criterion is worse than a contradicted requirement,
because a criterion is what someone writes a test against.

## What is contradicted

Read from the prior record at
`261016-shikhokplus-tuition-app/inception/user-stories/stories.md`:

| Story / criterion | What it says | Why it is now wrong |
|---|---|---|
| **US1.2** — "Student or guardian claims a dormant record" | *"I want to sign in with the number my teacher recorded… **without anyone inviting me**"* | Exactly backwards. The invitation is now the mechanism, and signing in no longer claims anything. |
| **AC1.2.1** | Signing in activates the account and the recorded batches appear | Signing in no longer grants a lens. Acceptance does. [FR1.9a] |
| **AC1.2.2 / AC1.2.3** | Which lenses are offered at sign-in | Still right in shape, but each now requires the seat to be **accepted** before its lens is offered. [FR1.4a] |
| **AC1.3.2** | *"no notification, invitation or reminder is ever sent to that number"* | An invitation is precisely what a pending seat now is. |
| **AC1.3.3** | A dormant enrollment is deliberately **not** marked on the roster, because "dormant is the normal state early in a batch's life and decorating most rows would flag normality as a problem" | The reasoning was sound for dormant and is wrong for pending and declined, which are exactly the states that must be visible so a mistyped number is caught. [FR1.9h] |
| **AC1.6.2** | On a student's account deletion, "the enrollment reverts to dormant" | Carries the FR11.1 defect into a testable criterion: reverting silently clears a decline. [FR11.1a] |

Six criteria across four stories, plus one story whose premise is inverted.

**That count was wrong, and the review found the rest.** Three more criteria in
US1.3 — AC1.3.4, AC1.3.5 and AC1.3.6 — are written in sign-in terms ("has ever
signed in", "9 of 12 have signed in", "never claimed vs claimed and then
deleted") and are equally contradicted. So is **AC2.5.1** in US2.5, which
permits removal only while dormant and therefore, once dormant collapses into
pending, forbids removing any seat a teacher creates — blocking the recovery
path from a mistyped number. The true count is **ten criteria across five
stories**. The sweep in this assessment stopped at the stories whose titles
mentioned acceptance; it should have swept every criterion that mentioned
signing in or dormancy.

## Factors considered

- **Project type**: brownfield, four Units merged, six remaining.
- **User-facing scope**: total. Every remaining unit ships screens.
- **Complexity signals**: the acceptance state machine is new, has four states
  and two independent per-link markers, and governs an authorization decision.
  That is the kind of logic acceptance criteria exist for.
- **Personas**: unchanged. Teacher, student, guardian and operator are already
  defined in the prior record and nothing in the re-cut adds or alters one.

## Where stories add the most value here

1. **The acceptance state machine.** Four states, two markers, and a
   reversibility rule that differs by actor — the person may un-decline, the
   teacher may not. Each transition is an authorization decision, so each needs
   a criterion someone can write a test against.
2. **The money consequences of declining.** Generation stops, accrued cycles
   void as an append-only reversal, and an un-decline does not resurrect them.
   Three separate assertions, none obvious from the requirement alone.
3. **What a pending person sees.** A bounded read of three teacher-authored
   fields through a lens that does not exist yet.

## What this stage does NOT do

Re-derive the 45 existing stories, renumber any ID, or restate criteria that
remain correct. New stories continue the existing numbering rather than
restarting it, and superseded criteria are named explicitly alongside their
replacements.
