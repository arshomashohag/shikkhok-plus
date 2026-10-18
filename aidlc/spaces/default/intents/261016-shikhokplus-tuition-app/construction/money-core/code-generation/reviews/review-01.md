## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T06:46:11Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | app/money/_ledger.py > derive, per_cycle comprehension | The per-cycle floor silently discards relief, so outstanding overstates the debt whenever relief lands on a cycle already at zero. See note A | Attribute relief at enrollment level, or carry the discarded surplus into a term the identity and the per-cycle floor share | New |
| R-02 | Critical | tests/money/test_ledger_property.py > well_formed_history | The generator cannot reach the histories where note A's defect occurs, so the identity test certifies a subset the system exceeds. See note B | Extend the generator to emit late relief against a relieved cycle, over-relief, and unpaired carries, or state the reachable-history contract and enforce it in the fold | New |
| R-03 | Major | app/money/_ledger.py > carry_forward, apply_credit | `carry_forward` accepts any amount with no relation to what the origin period owes, so an over-carry manufactures debt. See note C | Compute the carried amount inside the module from the origin's derived balance, as `apply_credit` already does for credit | New |
| R-04 | Major | tests/gates/test_import_gates.py > TestGate2Inward, pyproject.toml banned-api | Gate 2 is defeated by `importlib.import_module("decimal")`; Gate 1 misses the same bypass and any deferred in-function import. See note D | Add a dynamic-import check to the AST gate on both directions, and a fixture proving it fires | New |
| R-05 | Minor | app/money/_money.py > apply_rate | A negative-zero rate is accepted and yields `-0.00`, which `is_negative()` reports False but `to_wire` emits as `-0.00`-adjacent state. See note E | Normalise the rate sign check to compare the value, not `is_signed()`, so `Decimal('-0')` is treated as zero | New |
| R-06 | Minor | app/money/_money.py > allocate | `allocate` on a negative amount relies on `to_integral_value` with the ambient context rounding rather than the module's declared mode. See note F | Use the already-quantized `amount` directly rather than re-deriving paisa through a context-sensitive conversion | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| derive() probe, over-relieved cycle | Identity LHS 0.00 vs RHS 1000.00 | Confirms note A; reproduced from valid non-negative entries |
| derive() probe, late payment on carried cycle | Outstanding 2000.00, expected 1600.00 | Confirms note A on a system-producible history |
| ruff check --select TID251 on importlib fixture | PASS (no violation) | Confirms note D; Gate 2 does not see a dynamic import |
| assert_never reachability probe | AssertionError on unknown kind | Exclusion is sound; no finding |

### Summary

The arithmetic of the `Money` type is correct and the eight worked scenarios do hold, but the ledger fold's per-cycle floor destroys the balance identity on histories the system can genuinely produce, and the property test's generator is shaped so it cannot reach any of them.

**Note A — the per-cycle floor discards relief the identity still counts.**
`derive` computes `per_cycle[p] = max(0, cycle_charged[p] - cycle_relieved[p])` and then `total_outstanding = sum(per_cycle)`. The eight totals, however, are unfloored running sums. When relief on one period exceeds that period's charges, the excess relief is thrown away by the floor while remaining fully counted in `total_receipt`, `total_forgiven` or `total_credit_apply` on the identity's left-hand side. The identity then fails. Three reproductions, all from entries that satisfy BR4.1 (non-negative) and every construction rule:

- Over-relief in one cycle: `charge Mar 1000, receipt Mar 1000, forgiveness Mar 1000, charge Apr 1000` gives outstanding 1000.00 with LHS 0.00 — a cycle waived after it was already paid, which is a teacher correcting a mistaken payment approval and is exactly the kind of thing U8's approval flow will produce.
- Late relief against a carried-out cycle: `charge Mar 1000, carried_out Mar 1000, carry_forward Apr 1000, charge Apr 1000, receipt Mar 400` gives outstanding 2000.00. The true answer is 1600.00 — a payment arriving for March after March's balance was carried into April is wholly ordinary, and the money simply vanishes. This is the most likely real occurrence of the three.
- Credit applied in a period with no charge: `charge Mar 1000, receipt Mar 1000, credit_grant Mar 500, credit_apply Apr 500` reports available_credit 0.00 with outstanding 0.00 — the 500 of credit is consumed and relieves nothing.

The test suite's own property test documents the first half of this as "the per-cycle floor working correctly, not an arithmetic defect" and narrows the identity to realistic histories. That reasoning is right about the one-entry case it cites (a receipt against no charge, which the system never writes), and wrong as a general conclusion: the three histories above are realistic, and the floor is still silently eating money. BR4.4 does mandate the per-cycle floor, so the floor itself is not the defect — the defect is that nothing reconciles the discarded surplus against the enrollment-level identity, and nothing detects when discarding occurs. A per-cycle surplus is either enrollment credit or an upstream error; in neither case is discarding it correct.

**Note B — the generator is shaped to the implementation, not the domain.**
`well_formed_history` is structurally incapable of producing any of note A's three histories. It emits relief only within the period it is iterating, caps every receipt and waiver at the running `outstanding` via `apply_credit`, and always pairs `CARRIED_OUT` with `CARRY_FORWARD` in the following period. In other words, the generator pre-enforces precisely the invariants whose violation breaks the identity. That makes `test_identity_and_side_conditions_over_realistic_histories` a check that `derive` agrees with the generator, and the 2000 examples buy much less than they appear to. This matters acutely here because `team.md` records that this project's identity was wrong twice and that randomized testing is what settled it — the randomization has been narrowed to the point where it can no longer play that role. Either the generator must widen to the domain's real shape, or "the histories the system can produce" must become an enforced contract in the fold rather than an assumption held only in the test.

**Note C — `carry_forward` takes the amount on trust.**
`carry_forward(amount, origin, receiver)` accepts any non-negative `Money` with no relation to the origin period's derived balance. `carry_forward(Money(1000), 'Mar', 'Apr')` against a March that charged only 600 produces outstanding 1000.00 and breaks the identity. The module's own stated design principle argues the opposite way for credit: `apply_credit` computes `min(available, owed)` precisely "so that over-application is unrepresentable rather than refused". The same argument applies verbatim to a carry, and the module docstring claims the pairing makes a one-sided carry impossible — it does, but it leaves over-carrying wide open, which has the same arithmetic consequence. Since U7 is the caller and this module is the only place with the fold, computing the carried amount here is both cheap and the only place it can be done safely.

**Note D — both gates miss dynamic and deferred imports.**
`tests/gates/test_import_gates.py` Gate 1 walks `ast.Import` and `ast.ImportFrom` nodes. A module-level `importlib.import_module("app.db.session")` is neither, so a money module acquiring a session by that route passes. Gate 2 inherits the same blind spot twice over: its AST half checks only `"decimal" in _imported_modules(source)`, and its Ruff half is `TID251` banned-api, which matches import statements only. I verified this directly: a file containing `importlib.import_module("decimal")` followed by `Decimal` arithmetic passes `ruff check --select TID251` against the project's real config. A deferred import inside a function body *is* caught by both (both walk the whole tree), and a `TYPE_CHECKING` guard is harmless because it carries no runtime value — so the real gap is the dynamic one. It is a small addition: match `importlib.import_module` and `__import__` call nodes with a string-literal first argument, and ship a third fixture. Without it, the gate's own docstring claim that the boundary is "mechanical rather than review-enforced" is stronger than what the code delivers.

**Note E — negative zero passes the rate guard.**
`apply_rate` rejects a negative rate with `if rate.is_signed() and rate != 0`. `Decimal('-0')` is signed and compares equal to zero, so it passes, and `Money(100).apply_rate(Decimal('-0'))` returns a `Money` whose `amount` is `Decimal('-0.00')`. `is_negative()` returns False on it (correctly, since `-0.00 < 0` is False), so it slips past `to_wire`'s guard and `_floor`, and `str()` renders it as `-0.00` — which fails the module's own `WIRE_PATTERN`, meaning `to_wire` emits a string `parse` would reject. The practical blast radius is small since a `-0` rate is unlikely, but it is a value that round-trips asymmetrically across the chokepoint the module exists to guarantee.

**Note F — `allocate` re-derives paisa through the ambient decimal context.**
`allocate` computes `int(self.amount.scaleb(2).to_integral_value())`. `self.amount` is already quantized to 2dp at construction, so `scaleb(2)` is exact and `to_integral_value` is a no-op in practice — but `to_integral_value` consults the thread's decimal context rounding, not the module's declared `ROUNDING`. `_rounding.py` states that the module has "exactly two rounding points" and that both use the declared constant; this is a third rounding site that the module's own documentation says does not exist. It is currently harmless because the input is always exact, which is why it is Minor rather than Major, but it is a latent dependency on global mutable state in the one module whose whole design premise is purity, and it would become live the moment `amount` were ever constructed by a path that skipped quantization.

Two things I checked and found sound, recorded so they are not re-litigated: the `assert_never(unreachable)` coverage exclusion is legitimate — a `str` not matching any member reaches it and raises `AssertionError` at runtime, so the line is genuinely unreachable only for well-typed inputs and loudly reached otherwise, which is the correct behaviour either way. And the Kotlin `MoneySerializer` non-`JsonDecoder` fallback is safe: `decoder.decodeString()` on a non-JSON format cannot smuggle a number past `Money.of`'s `WIRE_PATTERN`, and `Money.kt`'s `init` requiring `scale() == 2` cannot reject a legitimate value because every construction path runs `setScale(2)` first.
