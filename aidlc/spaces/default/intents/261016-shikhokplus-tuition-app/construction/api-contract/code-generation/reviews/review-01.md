## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T10:22:34Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | app/contract/privacy.py > `resolve_lens_type_of` | A route with two separate (non-unioned) lens dependencies silently drops the teacher-facing privacy check if a non-teacher lens happens to resolve first. See note A. | Walk the full dependency tree and collect every lens the route resolves, then apply the teacher-facing check whenever `TeacherLens` is among them, instead of stopping at the first lens found. | New |
| R-02 | Minor | pyproject.toml > `[[tool.mypy.overrides]] module = "app.schemas.*"` comment | The comment claims an `Any`-typed field "appears as an unconstrained schema and is reported" by the privacy gate. The gate classifies fields by name only; it has no schema-shape detection. See note B. | Reword the comment to say the compensation is the named forbidden-field set (`self_name`, `photo_ref`, account-id fields), not a general unconstrained-schema check, so a future reader does not believe an `Any`-typed field is caught generically. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| `make check` (lint, typecheck, test) | PASS — 299 tests, 100% branch on `app/money`, 93.74% line on `app/authz`+`app/contract`+`app/errors`+`app/schemas` against an 80% floor | Confirms the numbers in `code-summary.md`; no coverage gaming found, `app/contract/emit.py`'s coverage omission is honest (it's a thin subprocess entry point whose body is otherwise fully tested) |
| `ruff format --check`, `ruff check` | PASS | Lint/format clean, including the `D` (docstring) ruleset |
| `mypy app` | PASS | No type errors across 26 source files |
| Manual repro: sixth `TaxonomyError` subclass | Static call with a concretely-typed parameter is a mypy `arg-type` error; a generic `TaxonomyError`-typed call site slips past mypy but is caught at runtime by `to_response`'s explicit `TypeError` in the `case _:` arm, and `test_the_closed_union_matches_the_actual_subclasses` catches the union/subclass-set mismatch | Confirms claim 1: neither mechanism alone is sufficient, and together they are. Not a finding. |
| Manual repro: `Any`-typed field in a Pydantic model | Emits `{"title": "Weird"}` with no `type` key (schema-shape evidence); privacy gate catches a same-named owner-private field by name match alone, independent of its type | Confirms claim 2's practical conclusion (Pydantic forces the flag off) but shows the code comment's stated mechanism is wrong — see Minor finding above |
| Manual repro: numeric money field (`float`) | `money_schema_violations` correctly reports `kind="numeric-money"` via `_is_numeric_money_name` | `MONEY_NAME_TOKENS` and the numeric-money branch are wired in and firing; claim 4's concern does not reproduce. Not a finding. (No dedicated test exercises this path in `test_money_schema.py`, which is a coverage gap in the test suite, but the gate code itself is correct and the backend coverage floor is still met — informational only, not raised as a finding given the "no manufactured findings" instruction.) |
| Manual repro: dual-lens route (`TeacherLens` + `GuardianLens` as two separate `Depends()`) | `unlensed_routes` correctly reports clean (route is lensed); `forbidden_fields` reports **zero violations** even though the response leaks `self_name` under the teacher lens | Confirms the Critical finding above |
| Manual check: `security` key inclusion in `ORDER_INSENSITIVE_KEYS` | `_sort_lists` only sorts a list when every element is a string; a realistic `security` list (dicts) is left untouched | Inert/safe inclusion, not a bug. Not a finding. |
| Manual check: `_publish_shared_components` | `app.openapi()` and the committed `openapi.json` both carry `Money`, `ErrorBody`, `ErrorEnvelope` with zero declared routes | Confirms claim 6's design intent works correctly. Not a finding. |
| Manual check: hardcoded secrets, float/double for money | None found in `app/contract`, `app/errors`, `app/schemas`, `app/authz`, `app/main.py` | NEVER rules honoured |

### Summary

The Unit is structurally sound — the schema-diff, money, and route-lens gates are correctly wired, proven to fire against honest fixtures, and all pass `make check` with coverage above both floors. The one real defect is in the privacy gate's lens resolution: `resolve_lens_type_of` stops at the first lens found in an unordered dependency-tree walk, so a route legitimately serving two distinct lenses (a realistic shape the project's own tests acknowledge, e.g. the dual-lens account case) can have its teacher-facing response schema checked against the wrong lens and silently pass with a real privacy leak. This is exactly the failure class ("not a wrong lens, a forgotten one") the Unit's own design philosophy says must fail in CI, and here it does not. It must be fixed before this Unit is relied on as the enforcement mechanism for later Units' privacy boundary.

**Note A — dual-lens privacy gate gap.** `resolve_lens_type_of` (app/contract/privacy.py) does a stack-based DFS over `route.dependant` and returns on the *first* dependency whose resolved return type is a lens. For a route depending on `Annotated[TeacherLens, Depends(_teacher_lens)]` and `Annotated[GuardianLens, Depends(_guardian_lens)]` as two independent parameters (not a `TeacherLens | GuardianLens` union, which `resolve_lens_type` already handles correctly), the stack-pop order picked `GuardianLens` in testing — `forbidden_fields` then skips the route entirely because `resolve_lens_type_of(route) is not TeacherLens`. A hand-built fixture reproduced this: a route returning a model with `self_name` (forbidden under `TeacherLens`) under both a teacher and a guardian dependency passed the gate with zero violations. The route-enumeration gate (`unlensed_routes`) does not share this flaw, since it only needs to know *whether any* lens resolves, not *which one* — the asymmetry is specific to `privacy.py`'s need to pick the authoritative lens for a multi-lens route.

**Note B — overstated compensation comment.** The `pyproject.toml` comment for the `app.schemas.*` mypy override says the privacy gate catches an `Any`-typed field because "an Any-typed field appears as an unconstrained schema and is reported." Verified: `forbidden_fields`/`_classify` in `app/contract/privacy.py` matches purely on field **name** against `OWNER_PRIVATE_FIELDS` and `FORBIDDEN_ACCOUNT_ID_FIELDS`; there is no code path that inspects whether a schema node is "unconstrained" (missing `type`/`properties`). The practical conclusion drawn from the comment — "the property the flag was meant to buy is still enforced" — holds only for the two already-named forbidden field sets, which is probably sufficient for the project's actual threat model, but the comment should describe the real mechanism (name-based matching) rather than a structural one that does not exist, so a future reader does not assume broader coverage than exists.
