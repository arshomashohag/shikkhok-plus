# Discovered Rules

> Hard constraints only, in the stamped `ALWAYS` / `NEVER` form. These are
> appended to `aidlc/spaces/default/memory/project.md` on promotion.
>
> **This is a re-run against an affirmed baseline.** The twelve `NEVER` and
> nineteen `ALWAYS` rules affirmed on 2026-10-16 are already in `project.md`,
> are unchanged, and are **deliberately not restated here** — the promotion
> path appends rather than replaces, so restating them would duplicate every
> one. Only genuinely new constraints appear below, each arising from a gap
> this run verified in the built code rather than from a fresh human
> preference.
>
> The rules below are deliberately few. Most of what this run found is
> *sequencing* — when a control is installed — which belongs in
> `team-practices.md` and not in a permanent `ALWAYS`. A rule earns a place
> here only if it should still hold after D6 ships.

## Mandated

- ALWAYS lock dependency resolution on every surface that has a package manager, and make the CI install read the lockfile rather than re-resolve; a CI step may not be labelled as a lockfile or verification check unless it performs one. [team: Deployment] [check.yml:88] (affirmed 2026-10-22)
- ALWAYS pair a mechanical control named in a practice with the deliverable unit that installs it, and treat a unit as incomplete while a control assigned to it is missing. [team: Way of Working] (affirmed 2026-10-22)
- ALWAYS enforce the forbidden-identifier set at commit time as well as at release time, so a forbidden framework reference cannot reach `main` and be found only on the build that was about to ship. [TC-3] [TC-4] [D-35] [D-37] (affirmed 2026-10-22)
- ALWAYS assert that a test suite's precondition held before treating its pass as evidence, so a suite that silently skipped is never read as a suite that passed. [tests/conftest.py] [pg-rls] (affirmed 2026-10-22)

## Forbidden

- NEVER record an obligation without naming the verifier that discharges it, and never discharge a performance or layout obligation with a correctness test. [TC-15] [TC-17] [D-43] [PU-3.6] (affirmed 2026-10-22)
- NEVER let a comment state a count, a version or a scope that nothing checks; where a comment states a number, the number is a claim and either a test asserts it or the number comes out. [app/contract/routes.py:33-49] (affirmed 2026-10-22)
