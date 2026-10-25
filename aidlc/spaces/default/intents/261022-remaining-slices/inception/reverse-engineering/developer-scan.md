**Collaborator:** aidlc-developer-agent

# Developer Scan Handoff — shikkhok-plus

**Stage**: reverse-engineering (2.1)
**Mode**: pipeline, lead-only (collaborators off, so the developer is the sole
and final link and both scanned and synthesized)
**Date**: 2026-10-22
**Commit**: b14b1fab94768602a0e396e03ec32b079ffb9cf4

## Scan scope

- **Repo**: `shikkhok-plus` (single, unrecorded project-root repo)
- **Store check**: `NO_STORE` — first scan, so a full scan of `./`
- **Pre-scan snapshot**: `store_generation: none`,
  `source_fingerprint: git:7599d1532485cb8715d7d2aee3a583674ebb01d3`
- **Post-scan verification**: the scope block validates and the fingerprint
  still matches the source, so nothing moved underneath the scan
- **Analyzed paths**: `./` — the whole repository. Build outputs, dependency
  folders and tool caches were left unopened; AI-DLC's own install (`.claude/`
  and the `aidlc/` workspace) is not the project's code and was not scanned.

## Artifacts produced

All nine, at `aidlc/spaces/default/codekb/shikkhok-plus/`:
`business-overview.md`, `architecture.md`, `code-structure.md`,
`api-documentation.md`, `component-inventory.md`, `technology-stack.md`,
`dependencies.md`, `code-quality-assessment.md`,
`reverse-engineering-timestamp.md`.

26 components inventoried — 14 backend, 8 Android, 3 infrastructure, plus
`MainActivity` — alongside an explicit absence table for the feature areas
with no code yet.

## Verified by running, not by reading

| Check | Result |
|---|---|
| `pytest tests` | 615 passed, 35 s |
| `app/money` branch coverage | 100.00%, `fail_under = 100` reached, no inline pragmas |
| Backend line coverage | 91%, against an 80% floor |
| `pytest tests/privacy tests/db tests/batches` | 115 passed against a real PostgreSQL 16 container |
| `ruff check` / `ruff format --check` | Clean, 135 files |
| `mypy app` | Clean, 65 files |
| Kotlin tests | 137 `@Test` functions |
| `openapi.json` | 12 operations across 11 paths, reconciled against the four registered routers |

## The five project invariants

All five hold, and the mechanisms are real rather than aspirational.

- **Money never float or double** — four independent gates, including a
  `TypeError` at the column bind and a compile-error value class in Kotlin.
- **No role column** — none exists anywhere; migration 0002 deletes the
  earlier one.
- **Privacy boundary structural in three layers** — row-level security uses
  `ENABLE` *and* `FORCE`, with `set_config(..., true)` so the context is
  transaction-local.
- **Every endpoint names its lens** — the gate enumerates
  `app.state.included_routers` and matches on the return annotation, not the
  function name.
- **No device or advertising identifier** — the DEX scan looks for the
  lowercase value `android_id` rather than the field name.

## Drift between a written decision and the code

Three items, each verified independently at the conductor's end before being
reported.

1. **`app.authz` is a declared mypy strict island and is not configured.**
   `pyproject.toml` configures `app.money.*` and `app.schemas.*` only. The
   comment says authz "stays unconfigured until U3 creates its resolvers"; U3
   shipped, the resolvers exist, and the override was never added.
2. **`PUBLIC_ROUTES` allowlists two routes that do not exist.**
   `app/contract/routes.py:33-49` carries a six-entry frozenset under a comment
   stating "exactly five, and the count is asserted".
   `("GET", "/account-deletion")` and `("POST", "/account-deletion")` are
   asserted present by `tests/contract/test_route_lenses.py:86-87`, and no
   handler registers either path. **Not a live hole** — nothing is reachable —
   but it is pre-declared D6 scope, and D6 should land handlers against
   entries that already exist.
3. **`.github/workflows/check.yml:88` is labelled "Step 2. Lockfile
   verification, Python side" and runs `pip install -e ".[dev,api]"`** — an
   unpinned resolve. The label describes a control that is not there.

## Largest gaps — absences rather than defects

- **No lockfile on either application surface.** No `uv.lock`, no
  `requirements.txt`, no `gradle.lockfile`, no `verification-metadata.xml`,
  against a practice mandating both from the skeleton. Measurable today:
  `mypy>=1.11` resolved to 2.4.0. Terraform is the one properly locked surface.
- **No CVE scanning anywhere** — no Dependabot, pip-audit, Trivy, osv-scanner
  or `.security-exceptions.md`.
- **The whole Android quality toolchain is absent** — no ktlint, spotless,
  detekt, `lint.xml`, Kotlin coverage report (so no ratchet), or screenshot
  testing. This lands on the surface the team practice itself calls the
  thinnest-reviewed, and it means the **Bangla layout obligation currently has
  no verifier**: both bundles are complete at 53 strings each, but neither
  named verifier exists.
- **The release gates are the only Kotlin checks** and run on `bundleRelease`
  only, so a `TelephonyManager` call could sit on `main` through every PR.

## One note for the consumer

The **error envelope is published as a component but referenced by no
operation's responses** (`app/main.py:144-182` injects it explicitly). A client
author reading `openapi.json` learns from no operation that a 403 or 409
returns it, and a ZAP pass driven from this schema would not know which error
shapes to expect. D3 is the first unit with declared error responses and the
natural place to close it.

## Two things worth knowing about the existing gates

- **Two gates once passed against zero routes.** `isinstance(route, APIRoute)`
  over `app.routes` matched nothing in this FastAPI version, so both the route
  gate and the privacy gate reported clean while checking nothing. Found and
  fixed; a count cross-check now guards it. Several docstrings in this codebase
  record defects found by deliberate injection, which is why that one surfaced.
- **`RosterRowResponse.status` already exists** with `dormant`/`active`/
  `inactive`. D2's pending state is a fourth enum value plus backing columns,
  not a new field.
