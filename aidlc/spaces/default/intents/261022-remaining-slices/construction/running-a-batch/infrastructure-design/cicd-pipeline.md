# CI/CD Pipeline — D2 `running-a-batch`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> **No new stage, no new gate, no deploy change.** D2's tests are pytest and
> Robolectric and land inside `make check`. What this document carries that
> the workflows do not: which existing gates D2's work lands behind, and the
> **one prediction D2 is the first to test** — D1's Compose coverage
> exclusion, against four new screens.

## Sources

- [upstream] `construction/running-a-batch/nfr-requirements/tech-stack-decisions.md`
  — the coverage prediction and its two outcomes
- [upstream] `construction/running-a-batch/nfr-design/security-design.md` § 5
  — the verification design
- [upstream] `construction/running-a-batch/functional-design/functional-spec.md`
  — the workflows the tests assert
- [prior] D1's `infrastructure-design/cicd-pipeline.md` — the pipeline shape
- [code] `.github/workflows/check.yml`, `deploy.yml`, `Makefile`,
  `android/coverage.gradle.kts`, read 2026-10-23

---

## Where D2's work lands

| Gate | D2's relationship |
|---|---|
| Gitleaks, with its history-depth precondition | inherited |
| Lockfile install and currency check | inherited; **no dependency added** |
| CVE annotation | inherited |
| `make check` | **where every D2 test lands** |
| Android: money boundary, spotless, detekt, Lint | inherited |
| Android: **coverage ratchet** | **the one gate D2 genuinely tests** |

### What `make check` runs for D2

| D2 obligation | Lands in | Requirement |
|---|---|---|
| `accepted_count` correctness, written from the criterion first | `test` | NFR23.4 |
| Two removal refusals as **distinct** outcomes | `test` | NFR23.5 |
| A declined row renders the number, not the name | `android` | NFR14.28 |
| Six per-screen Bangla rows, the count among them | **manual** | NFR3.3 |
| Back after a child switch | `android` | **NFR23.6** |
| Mapper tests: `isDeclined`, `absent`, `isRemovable` | `android` | BR2.2, BR3.1 |
| Response schema diff | `test` | — |

**No new pipeline stage, and that is the design working.** The gate is one
command locally and in CI, which the team practice names as the single most
important property for a solo build.

---

## The prediction D2 tests

D1 corrected the Compose coverage measurement: JaCoCo cannot instrument
composables under Robolectric — `AuthScreenKt` measured 0 covered lines while
`AuthScreenTest` passed — so `coverage.gradle.kts` excludes `**/*ScreenKt*`
and `**/ui/*Kt*`, and the floor **rose** from 35.26 to 45.84.

**That correction was made while adding three screens. D2 adds four more**,
so this is its first independent test.

| Outcome at `verifyCoverageRatchet` | Means | Action |
|---|---|---|
| Floor holds or rises | The exclusion behaves as intended; D2's mappers are tested and its screens are excluded | Record the new figure |
| **Floor drops** | `**/ui/*Kt*` is catching something that is not a composable | **Narrow the glob.** Do **not** lower the floor |

**The action differs by outcome and that is the point of writing it down.** A
ratchet failure reads as "cover your new code" by default, and here that
diagnosis would be wrong — the screens are covered by Robolectric tests the
measurement cannot see.

**`**/ui/*Kt*` is the suspect half.** It is broader than `**/*ScreenKt*` and
would catch any non-composable file placed in a `ui` package. D2 puts
`InvitationsScreen`-style composables in `feature/*/ui/`, so if a mapper or a
helper lands there it disappears from the denominator silently.

---

## Deploy

Unchanged, and D2 depends on fewer of its properties than D1 did:

| Property | D1 needed it for | D2 |
|---|---|---|
| Migration before the new container serves traffic | The acceptance columns | **not applicable** |
| The SHA tag is the artifact | Rollback | inherited |
| ECR immutable tags | The previous tag still means what it meant | inherited |
| The database is not on the instance | Surviving an ASG refresh | inherited |

**D2's rollback needs no argument.** D1's tag rollback was complete only
because its columns were additive and the old image never read them. D2 moves
no schema, so redeploying the previous tag restores the previous behaviour
unconditionally.

### The smoke gap, unchanged

`deploy.yml`'s final step curls `/health` over SSM. The practice's named smoke
set — OTP issue and verify, authenticated lens resolution, a fee-cycle read —
does not exist.

**D2 neither widens nor narrows it.** It adds screens over endpoints that
already worked, so the difference between "the process answers" and "a person
can use it" is exactly what it was. The gap is D1's to extend and D5/D6's to
complete.

---

## What D2 does not add

| Not added | Why |
|---|---|
| A pipeline stage | Its tests are pytest and Robolectric |
| A dependency | One new package, no new library |
| A deploy step | No migration, no new resource |
| A release-gate change | The download-size assertion is unchanged and measured at the release gate [NFR2.4] |
| A secret | No new external call |

---

## Assumptions & Open Questions

- **Assumed**: the widened `openapi.json` passes the schema-diff gate as a
  reviewable diff, as D1's did.
- **Assumed, with the fallback named**: four new screens do not push the
  Android job past its fifteen-minute timeout. D1 added three and did not, so
  this is watching rather than expecting. **If it does**, the answer is to
  split the Android job — unit tests separate from the Robolectric rendering
  tests, which are the slow half — rather than to raise the timeout. Raising
  it hides a trend; splitting keeps each half's duration legible and keeps a
  Kotlin build from gating a backend PR, which is why the job was split from
  the backend one in the first place.
- **Open, and named for Build and Test**: the ratchet outcome above, with the
  action for each case decided here rather than at the moment of failure.
