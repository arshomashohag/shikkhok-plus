# Tech Stack Decisions — D1 `signing-up-and-joining`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> **D1 selects no new technology.** The stack is built, configured, locked and
> in CI across four merged units. This file records what D1 uses, the one
> choice genuinely open inside it, and the two places where a *built* tool's
> shape constrains how D1 may use it — which is the useful content here, and
> is not derivable from a dependency list.

## Sources

- [upstream] `aidlc/spaces/default/codekb/shikkhok-plus/technology-stack.md`
  — the scan of the built stack, 2026-10-22
- [upstream] `inception/domain-design/components.md` — the component catalogue
- [upstream] `inception/requirements-analysis/requirements.md` — satisfied
  preconditions
- [code] `app/auth/ceilings.py`, `app/audit/log.py`, `pyproject.toml`, read
  2026-10-23

---

## What D1 uses, all of it already here

| Layer | Technology | D1's use | New? |
|---|---|---|---|
| API | FastAPI | `POST /v1/accounts`, the lookup, accept/decline/un-decline | no |
| Validation | Pydantic | The signup request and invitation response schemas | no |
| ORM | SQLAlchemy | The two decision columns, the address | no |
| Migration | Alembic | One migration, conditional backfill | no |
| Database | PostgreSQL 16 | Enum or check constraint, row-level security on `profile` | no |
| Auth | PyJWT | Unchanged; signup issues no token | no |
| SMS | httpx gateway adapter | Unchanged; signup triggers the existing OTP path | no |
| Client | Compose, Kotlin 2.0.21 | `O1`, `O4`, the `O5` edit half | no |
| Tests | pytest, testcontainers, JUnit, Turbine | Test-first on the acceptance transitions | no |

**Nothing to decide is the correct outcome here**, and it is worth one
sentence rather than a shrug: the unit that opens an unauthenticated write
path into a children's-data application is not the unit in which to introduce
a dependency. The project's own rule is that a new dependency is checked
against the forbidden-identifier set before it is added, because removing an
SDK after the Families declaration is far more costly than not adding it.

---

## The one open choice: how the decision columns are represented

**Decision: a PostgreSQL native enum**, with the alternative recorded because
it is close.

| Option | For | Against |
|---|---|---|
| **Native enum** *(chosen)* | Illegal values unrepresentable at the database level, which is the property this design pays a migration for; the three states are a closed set with no fourth in sight | The schema's first enum; adding a value later is `ALTER TYPE`, which is fine but is a migration |
| Check-constrained text | No new type; a fourth value is a constraint change | The constraint is easier to drop or forget to carry forward; a text column accepts anything until the constraint is checked |

**Why this is a real choice and not a default.** `components.md` flags it
explicitly: there is no existing enum column anywhere in this schema, so
either way D1 sets a precedent. The deciding argument is the one the entity
design already makes for choosing enums over timestamps — *make the illegal
combinations unrepresentable* — and a native enum carries that further down
the stack than a check constraint does.

**What makes this low-risk to reverse**: both forms are a single migration
away from each other, and the application-level type is the same either way.

---

## Two built tools whose shape constrains D1

These are the entries worth having in this file. Neither is a selection; both
are facts about a built component that decide how D1 may extend it.

### `app/auth/ceilings.py` — ordering is the control

The module implements a scope-parameterised cascade over a datastore-backed
counter table. D1 needs signup's own ceilings [BR2.1], and the right move is
new `ScopeKind` members plus a second cascade builder — **not** a parallel
implementation.

Two properties constrain that extension:

- **`ScopeKind`'s declaration order *is* the evaluation order**, stated in the
  enum's own docstring so the cascade cannot drift from the rule by someone
  reordering a dictionary. A new scope is declared in its correct
  narrowest-first position.
- **`_scopes()` is a hardcoded static list**, so a second cascade is a second
  builder rather than a parameter.

The module records that an earlier design checked the global ceiling first and
that **global-first still looks like defence in depth**. A second cascade is
precisely where that would be reintroduced.

### `app/audit/log.py` — a closed vocabulary

`AuthEvent` is a closed enum, deliberately: an open vocabulary is how a
free-form value re-enters a log specified not to have one. D1's signup events
are **named members added to the closed set**, under the same no-free-form-field
rule — not a reason to open it.

---

## Satisfied preconditions, recorded as context

Completed 2026-10-22 ahead of D1, with gates passing. Noted so a reader does
not mistake them for D1's work:

| Precondition | State |
|---|---|
| Python and Gradle lockfiles, checksum verification | Delivered — `requirements.txt` with 1,865 hashes under `--require-hashes`; Gradle locking and verification |
| CVE scanning, per-push half | Delivered — pip-audit per push, Dependabot weekly grouped, `.security-exceptions.md` present |
| Android quality toolchain | Delivered — spotless and detekt in `android/build.gradle.kts`, `android/lint.xml` present with `HardwareIds` fatal |

**ktlint does not run over Kotlin source**, by recorded decision: it cannot
parse the `[AC1.1.6]` traceability tags inside KDoc. detekt, Lint and the
release DEX scan carry the Kotlin checks.

| Kotlin coverage ratchet | Delivered — `android/coverage.gradle.kts` applies JaCoCo and registers `jacocoDebugReport`; `android/coverage-floor.txt` holds the committed floor of **30.95** with no decrease permitted |

**Why these rows were re-verified rather than copied, and what that cost.**
The practice file's "before D1" table is dated 2026-10-22 and was written
against commit `4e4b4d4`. Checked against the tree on 2026-10-23: the
`app.authz` strict island, spotless, detekt, `lint.xml`, the `PUBLIC_ROUTES`
comment **and the Kotlin coverage ratchet** have all since been closed. The
whole list is delivered.

A draft of this file said the ratchet was the one item still outstanding, and
that was wrong twice over. The claim was sourced from the practice file rather
than the tree, and the check that was supposed to correct it only grepped
`android/build.gradle.kts` and `gradle/libs.versions.toml` — while the ratchet
lives in `coverage.gradle.kts`, applied from line 265 of the file I searched,
for the stated reason that a build file inlining every control stops being
readable. The architecture review caught it.

Recorded rather than quietly corrected, because the failure is instructive: a
negative claim ("no coverage report exists") was asserted from two files when
the build system's own convention is to split controls into applied files. A
search that does not follow `apply(from = ...)` cannot support a claim about
what the build does.

---

## Assumptions & Open Questions

- **Checked, and already done — the practice file is stale here.** The team
  practice records `app.authz.*` as a declared strict mypy island that was
  never configured, assigned to "before D1". It **is** configured, at
  `pyproject.toml:207-210`, with both `strict = true` and
  `disallow_any_explicit = true`, and with a comment explaining why the
  Pydantic constraint that forced `disallow_any_explicit` off for
  `app.schemas.*` does not apply here. The practice's note was accurate at
  commit `4e4b4d4` and the gap has since been closed.

  Recorded rather than dropped, because this file first asserted it as an
  outstanding assumption on the practice file's authority alone. D1's
  acceptance work does extend `app.authz`, so the island matters to this
  unit — it simply already protects it.
- **Open, and not D1's**: Schemathesis. The schema-diff gate is built and the
  conformance half is not. The practice records it as a genuine nice-to-have
  with no unit assigned, and assigning one here would be the empty promise
  that practice is correcting.
