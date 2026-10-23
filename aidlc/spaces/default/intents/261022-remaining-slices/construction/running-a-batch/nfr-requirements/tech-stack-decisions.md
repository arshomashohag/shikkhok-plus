# Tech Stack Decisions — D2 `running-a-batch`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> **D2 selects no technology and adds no dependency.** One new Kotlin package
> and four screens, on the stack D1 just exercised. This file records what D2
> uses, the one thing D2 is the first real test of, and the measurement
> correction it inherits.

## Sources

- [upstream] `aidlc/spaces/default/codekb/shikkhok-plus/technology-stack.md`
- [upstream] `construction/signing-up-and-joining/code-generation/code-summary.md`
  — the Compose coverage correction
- [upstream] this unit's `functional-spec.md` and `frontend-components.md`
- [code] `android/`, `app/`, read 2026-10-23

---

## What D2 uses

| Layer | Technology | D2's use | New? |
|---|---|---|---|
| API | FastAPI | Two response shapes widen; **no new route** | no |
| Schemas | Pydantic | `accepted_count`, `student_state`, `guardian_state` | no |
| Query | SQLAlchemy | One extra aggregate in the batch listing | no |
| Database | PostgreSQL 16 | No migration, no new column | no |
| Client | Compose, Kotlin 2.0.21 | Four new screens, two extended | no |
| Client structure | feature packages, one Gradle module | **`feature/guardian`** added | package only |
| Tests | JUnit, Turbine, Robolectric | Mapper tests plus rendering tests | no |

**No migration.** D2 is the first unit of this record that touches the
database schema not at all — the columns it renders were added by D1.

---

## The one thing D2 is the first real test of

**The Compose coverage correction made at D1.** JaCoCo cannot instrument
composables under Robolectric — `AuthScreenKt` measured 0 covered lines while
`AuthScreenTest` passed — so `coverage.gradle.kts` excludes `**/*ScreenKt*`
and `**/ui/*Kt*` from the denominator, and the ratchet floor rose from 35.26
to **45.84** as a result.

That correction was made while adding three screens. **D2 adds four more**,
so it is the first unit to show whether the exclusion behaves as intended:

| If the correction is right | The floor holds or rises, because the new mappers are tested and the new screens are excluded |
| If it is wrong | The floor drops, meaning the exclusion is catching something that is not a composable |

The second case would be a real finding rather than a reason to lower the
floor — the glob `**/ui/*Kt*` is broader than `**/*ScreenKt*` and could catch
a non-composable file placed in a `ui` package.

**Build and Test is where this is confirmed or falsified**, on D2's
`verifyCoverageRatchet` run — not a narrative aside but a named check with a
named moment. The obligation on that stage is to read a ratchet failure
against this prediction **before** treating it as "cover your new code":

| Outcome at Build and Test | Means | Action |
|---|---|---|
| Floor holds or rises | The exclusion behaves as D1 intended | Record the new figure |
| Floor drops | `**/ui/*Kt*` is catching a non-composable | **Narrow the glob**, do not lower the floor |

Named here because a ratchet failure at that stage reads as "cover your new
code" by default, and the diagnosis would be different.

---

## The one structural choice

**`feature/guardian` as a new package rather than extending
`feature/roster`.** The guardian home is a different lens's view of the same
data: the roster is what a teacher sees of a batch, the child home is what a
guardian sees of one seat. They share a DTO shape and nothing else — different
lens, different route, different navigation.

Putting the guardian screen in `feature/roster` would put two lenses' views in
one package, which is the shape the file-organisation practice exists to
prevent: features split by what a person is doing, not by which table the data
came from.

---

## Satisfied preconditions, unchanged since D1

Recorded as context rather than as work:

| Precondition | State |
|---|---|
| Python and Gradle lockfiles, checksum verification | Delivered |
| CVE scanning, per-push | Delivered |
| Android quality toolchain — spotless, detekt, `lint.xml`, Kover | Delivered; the ratchet floor is now 45.84 |
| `app.authz` and `app.accounts` strict mypy islands | Delivered |

D2 adds no package needing a fifth strict island: its backend change is two
fields on existing schemas in `app.schemas` and `app.api`, both already
covered.

---

## Assumptions & Open Questions

- **Assumed**: the two new roster enums are plain strings in the response,
  matching `status`, rather than a new shared enum type. Three enums with the
  same three values on one response would invite a helper that unifies them,
  and `status` is a different axis.
- **Assumed**: `feature/guardian` needs no new navigation library. The child
  switch is a selection within one screen, which is also what makes the
  back-stack obligation [BR4.2] satisfiable.
- **Open, and not D2's**: Schemathesis remains the outstanding conformance
  half of the API testing story. D2 widens two response shapes, which is
  exactly what it would check, and it is still unassigned by deliberate
  decision.
