# Code Summary — `money-core` (U1)

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`

> First code in the project. Every gate passes, and four of them were
> verified by **deliberately breaking what they protect** rather than by
> trusting that they work.

## Sources

- [upstream] `construction/money-core/code-generation/code-generation-plan.md`
  — the approved plan and its Testing Contract
- [upstream] `construction/money-core/code-generation/unit-test-instructions.md`
- [upstream] `construction/money-core/functional-design/rules.md` — 39 rules
- [upstream] `construction/money-core/functional-design/functional-spec.md` —
  §2 operations, §3 worked scenarios, §5 boundary cases
- [upstream] `construction/money-core/nfr-design/security-design.md` —
  NFR9.1–NFR9.32
- [upstream] `construction/money-core/infrastructure-design/cicd-pipeline.md`
- [upstream] `inception/delivery-planning/bolt-plan.md` — B1 DoD, as amended

---

## A. What exists

### A.1 Python — `app/money/`

| File | Contents | Lines |
|---|---|---|
| `__init__.py` | The public surface; every other module is private | 32 |
| `_rounding.py` | `ROUND_HALF_UP`, the 2dp exponent, the ten-digit bound | 36 |
| `_errors.py` | `MoneyValidationError` — the one class | 52 |
| `_money.py` | The `Money` value type | 320 |
| `_kinds.py` | The seven ledger kinds, closed | 83 |
| `_ledger.py` | Entry shape, the fold, derived quantities, `carry_forward` | 212 |
| `wire.py` | The API chokepoint, both directions | 95 |

### A.2 Kotlin — `android/src/main/kotlin/com/shikkhokplus/app/core/model/`

| File | Contents |
|---|---|
| `Money.kt` | `@JvmInline value class Money(BigDecimal)`, scale-checked |
| `MoneySerializer.kt` | Reads **only** a JSON string; fails loudly on a number |

### A.3 Gates and configuration

`pyproject.toml` (Ruff rule sets, mypy strict island, 100% branch coverage
with one named exclusion), `Makefile` (`make check`),
`.github/workflows/check.yml` (two jobs, no secret), `settings.gradle.kts`
and `android/build.gradle.kts`, `gradle/libs.versions.toml`, the Gradle
wrapper, and `.gitignore` entries for both toolchains.

### A.4 Tests

| Suite | Tests |
|---|---|
| `tests/money/test_construction.py` | 20 |
| `tests/money/test_arithmetic.py` | 55 |
| `tests/money/test_ledger.py` | 18 |
| `tests/money/test_ledger_property.py` | 4 (2,000 examples each) |
| `tests/money/test_wire.py` | 28 |
| `tests/money/test_uncovered_paths.py` | 32 |
| `tests/gates/test_import_gates.py` | 6 |
| `tests/test_named_test_manifest.py` | 61 |
| **Python total** | **198** |
| `MoneySerializerTest.kt` | **9** |

---

## B. Verification

```
make check                     198 passed, 100% branch coverage
./gradlew :android:testDebugUnitTest    9 passed
python3 -m mypy app            Success: no issues found in 7 source files
python3 -m ruff check app tests        All checks passed
```

| Gate | Result |
|---|---|
| Format + lint, incl. Gate 2 | clean |
| Type check, strict on `app.money` | clean |
| Branch coverage on `app/money` | **100%** |
| Both import gates + fixtures + config assertions | pass |
| Property test, 2,000 randomized histories | pass |
| Named-test manifest | 30 entries, all resolve |
| Kotlin compile + serialization | pass |

---

## C. Four gates verified by breaking what they protect

A gate nobody has watched fail is a gate nobody knows works. Each of these
was broken deliberately, the failure observed, and the change reverted.

| # | Break | Caught by | Significance |
|---|---|---|---|
| 1 | Added an **eighth ledger kind** without extending the fold | **mypy**, at exactly the `assert_never` line | This is what justifies excluding that one line from coverage. The branch is unreachable *because a stronger check guarantees it* — now demonstrated, not asserted |
| 2 | **Mis-sided a kind** — treated a waiver as cash received | **The worked scenario**, not mypy | The layering the design argued for: static checks catch *omission*, hand-written expectations catch *mis-siding*, neither substitutes for the other |
| 3 | Ran the **real linter** against a raw-decimal import outside the money module | **Gate 2**, in its actual project configuration | Proves the gate, not a reimplementation of its rule |
| 4 | Made the Kotlin serializer **lenient** — accept any primitive's content | `fails loudly on a json number` | The exact failure `team.md` names as *the actual failure mode*, on the surface with the least review depth |

---

## D. What the tools found that I had wrong

Recorded because these are the stage's real findings, not incidental fixes.

**1. Hypothesis refuted a property I had asserted.** I claimed the balance
identity holds over *arbitrary* entry sequences. It shrank a counterexample
to a single entry — a receipt of 0.01 against no charge — where the left side
gives −0.01 and the right 0.00.

That is the per-cycle floor working correctly, not an arithmetic defect: the
floor discards an unmatched relief, because a period cannot owe a negative
amount. But it means the identity is a property of **histories the system can
produce**, where every relief has an obligation to relieve. The claim was too
strong. The test now asserts the floors and the carry pairing
unconditionally, and the identity over well-formed histories, with the
distinction written into the docstring so nobody re-broadens it.

**2. The coverage gate refused the build at 94%,** naming six uncovered
paths. Five were real gaps — non-finite amounts, negation, a non-Decimal
rate, and three of the four comparison operators — and are now tested. The
sixth was the exhaustiveness assertion, which took the single named
configuration exclusion rather than a pragma.

**3. One test of mine was simply wrong.** `test_pair_cancels_at_enrollment_level`
asserted a bare carry pair totals zero. It does not: the origin period floors
at zero while the receiver is charged, so the pair only cancels **against the
charge it relieves**. The eight worked scenarios all passed throughout, which
is what identified the test rather than the fold as the defect. Both the
corrected case and the bare-pair behaviour are now tested, the latter
explicitly so the asymmetry is not later read as a bug.

**4. The manifest check caught two of my own criteria being too thin** —
"Outstanding 400.00, identity balances" states a number without stating what
makes it right. Strengthened rather than padded.

---

## E. Deviations from the plan

**One, and it is a layout correction.** The plan put the Kotlin source under
`app/`. That collides with the Python package of the same name: `app/` would
have held both `app.money` and an Android module whose conventional Gradle
name is also `app`. Kotlin now lives under `android/`, with the published
package namespace `com.shikkhokplus.app` **unchanged** — that is permanent
once published and was not touched.

Everything else follows the plan as approved.

---

## F. Not built, by decision

**`format(locale)` and the locale-completeness check.** Deferred together, as
one unit of work rather than a check with nothing to check. B1's Definition
of Done was amended to match, so the Bolt does not ship failing its own
checklist.

The blocking question is unchanged: the Bangla rendering is unspecified —
digit set, grouping interval, separators, currency symbol. A guessed
rendering shipped to installed phones cannot be withdrawn; a missing one is
additive under the `/v1/` policy. It becomes blocking at **B6**, the first
Bolt whose response assembly needs a display string.

**The two schema assertions.** They need a migrated database and a generated
OpenAPI document, neither of which this Unit has. Their DoD amendments landed
at this stage: **B2** owns the OpenAPI money-pattern assertion, **B3** the
column type-and-precision assertion.

---

## G. What later Bolts inherit

- `make check`, the single entrypoint, identical locally and in CI, needing
  **no secret** on a fresh clone;
- both import gates, their violation fixtures and their configuration
  assertions;
- Ruff with its named rule sets, and mypy's global baseline plus the money
  module's strict island;
- pytest with the branch-coverage floor wired in, scoped by behaviour;
- Hypothesis, available to every later property test;
- the named-test manifest pattern, with its per-entry acceptance criterion;
- the Gradle wrapper, version catalogue and the `android-unit` CI job;
- `.gitignore` coverage for both toolchains, including `local.properties`.

---

## Assumptions & Open Questions

**OQ-B1-1** — the Bangla money rendering. See §F. Blocks B1's formatting
operation and, at B6, the display sibling.

**Two items not yet done in this Bolt**, both from `bolt-plan.md`'s B1 DoD
and both outside Code Generation's scope: the dependency lockfiles
(`uv.lock`; `uv` is not installed in this environment) and Gradle dependency
locking with `dependencyVerification` checksums. Build and Test is where
these land, and the CI workflow already assumes them.
