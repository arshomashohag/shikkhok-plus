# Technology Stack

## Languages and runtimes

| Language | Version | Where | Target |
|---|---|---|---|
| Python | **3.12** (`requires-python = ">=3.12"`, `target-version = "py312"`, `python_version = "3.12"`) | `app/`, `tests/`, `migrations/`, `scripts/` | `python:3.12-slim-bookworm` |
| Kotlin | **2.0.21** | `android/src/` | JVM 17 bytecode |
| SQL | PostgreSQL 16 dialect | migrations, raw statements in `authz/` | `postgres:16-alpine` |
| HCL | Terraform **>= 1.10, < 2.0** | `infra/` | AWS provider `~> 5.70` |
| Kotlin DSL | Gradle 8.11.1 | build scripts | |

> **Note on the local interpreter.** The project declares Python 3.12, and
> the Docker image is 3.12. The interpreter available during this scan was
> **3.13.2** (`~/.pyenv/versions/3.13.2`), and the full suite passes on it.
> That is a divergence between the declared target and the machine the
> author is running, not a defect, but a 3.13-only behaviour could pass
> locally and fail in the container. CI pins `python-version: "3.12"`.

## Backend

### Framework and core libraries

Declared in `pyproject.toml` as **lower bounds only** (`>=`), with no upper
pin and no lockfile. Installed versions were read from the local environment
on 2026-10-22.

| Library | Declared | Installed | Purpose |
|---|---|---|---|
| FastAPI | `>=0.115` | 0.143.5 | the HTTP application, dependency injection, OpenAPI generation |
| Pydantic | `>=2.9` | 2.14.1 | request/response models, the shared `Money` component |
| SQLAlchemy | `>=2.0` | 2.1.5 | ORM, `TypeDecorator` for the money column |
| Alembic | `>=1.13` | 1.20.0 | migrations |
| psycopg (binary) | `>=3.2` | 3.3.6 | PostgreSQL driver |
| PyJWT | `>=2.9` | 2.15.1 | HS256 access tokens with `kid` |
| httpx | `>=0.27` | 0.28.1 | the SMS gateway client |
| uvicorn[standard] | `>=0.30` | 0.54.0 | the ASGI server |

The `uvicorn` entry carries a comment worth repeating, because it describes a
real gap that existed for two units: it was absent until recently "because
nothing had ever RUN the app — every test drove it through `TestClient`,
which is exactly why the device leg stayed unverified for two Bolts."

### Development and test libraries

| Library | Declared | Installed | Purpose |
|---|---|---|---|
| pytest | `>=8.3` | 8.4.1 | the test runner |
| pytest-cov | `>=5.0` | 7.1.0 | the two coverage floors |
| Hypothesis | `>=6.112` | 6.170.1 | the property test over randomized ledger histories |
| mypy | `>=1.11` | **2.4.0** | type checking, with strict islands |
| Ruff | `>=0.6` | 0.17.1 | formatter, linter, import-boundary gate, SAST |
| testcontainers[postgres] | `>=4.8` | 4.15.0 | a real PostgreSQL 16 per test session |

`pytest-mock` 3.14.1 is installed but is **not declared** in
`pyproject.toml`. Nothing in `tests/` appears to depend on it; it is most
likely ambient in the environment rather than a used dependency.

### Quality toolchain, as configured in `pyproject.toml`

Everything is in one file, which is the stated reason Ruff was chosen over a
Black + Flake8 + isort chain: speed at the commit boundary.

**Ruff** — `line-length = 88` (a deliberate, documented departure from the
79 in the global Python standard; 88 is Ruff's default so the formatter runs
unconfigured on the setting most likely to be mis-set). Selected rule sets:

| Set | Why this project selected it |
|---|---|
| `E`, `F`, `W` | baseline |
| `I` | import order, replacing isort |
| `UP` | pyupgrade, keeping 3.12 idiom |
| `B` | bugbear — mutable default args are a real defect class in FastAPI dependency signatures |
| `ASYNC` | a sync SQLAlchemy call inside `async def` serializes the whole event loop on a 2 GB host |
| `S` | the bandit subset — **this is the project's SAST tool**, claimed explicitly |
| `DTZ` | naive datetimes — fee periods are calendar-month-with-clamp in a non-UTC country |
| `BLE` | bare `except Exception` |
| `D` | Sphinx-style docstrings, across the whole backend |
| `RUF` | |

Ignored: `D203` and `D213` only, each because it conflicts with another `D`
rule. Per-file ignores: `tests/**` relaxes `S101` and the docstring rules;
**`app/money/**` is set to an explicitly empty list**, so its permission to
import `decimal` comes from being the banned-API carve-out rather than from
an exemption — and `test_gate2_config_scope` asserts that carve-out resolves
to exactly that path and never a parent.

**mypy** — global baseline `disallow_untyped_defs = true`,
`warn_unused_ignores`, `warn_redundant_casts`, `check_untyped_defs`. Two
strict islands:

- `app.money.*` — `strict = true` **plus** `disallow_any_explicit = true`
- `app.schemas.*` — `strict = true`, with `disallow_any_explicit`
  deliberately **off** and roughly 25 lines of reasoning recorded in the
  file: Pydantic's `BaseModel` is generic over `Any`, so the flag produces
  one unavoidable error per model whose only remedy is a per-line
  `# type: ignore`, and a file dense with ignores silences real findings
  too. The comment states precisely what is and is not compensated and
  calls the residual gap "real and accepted, not covered".

`app.authz.*` is named in the team practice as the third strict island and
**is not configured**. See `code-quality-assessment.md`.

**Coverage** — two separate runs, because the floors genuinely differ:

- `[tool.coverage]` in `pyproject.toml`: `source = ["app/money"]`,
  `branch = true`, `fail_under = 100`.
- `.coveragerc-backend`: everything else, `--cov-fail-under=80`, omitting
  `app/contract/emit.py` (a `python -m` entry point whose body *is* the
  subprocess the determinism test invokes).

The money configuration has **no `exclude_lines` beyond the defaults**, and
one `exclude_also` entry: `assert_never\(unreachable\)`. The comment names
this "the one sanctioned exclusion" and explains the distinction that
matters — a configuration entry is reviewed, enumerable and greppable, while
a `# pragma: no cover` comment is invisible in a diff among the lines it
exempts.

## Android

| Component | Version | Note |
|---|---|---|
| Android Gradle Plugin | **8.7.3** | |
| Kotlin | **2.0.21** | with the Compose compiler plugin and kotlinx-serialization plugin |
| Gradle wrapper | **8.11.1** | |
| `compileSdk` / `targetSdk` | **36** (Android 16) | mandated, rechecked at release |
| `minSdk` | **24** | |
| Java source/target | **17** | |
| Compose BOM | **2024.10.01** | pins every Compose artifact from one version |
| activity-compose | 1.9.3 | |
| lifecycle-viewmodel-compose | 2.8.7 | |
| kotlinx-serialization-json | 1.7.3 | |
| kotlinx-coroutines-test | 1.9.0 | |
| Ktor client | **2.3.12** | core, okhttp engine, content-negotiation, kotlinx-json, mock |
| androidx.security-crypto | 1.1.0-alpha06 | `EncryptedSharedPreferences` for the refresh token |
| Robolectric | 4.14.1 | runs Compose UI tests on the JVM |
| kotlin-test / kotlin-test-junit | 2.0.21 | |

Three choices here are decisions rather than defaults, each recorded in
`gradle/libs.versions.toml`:

- **Ktor, not Retrofit.** Not a preference — KSP could not parse eight
  untouched files on this Kotlin/AGP pairing. Ktor is pure Kotlin, uses the
  serialization plugin already present, and adds no annotation processor.
- **Robolectric**, so the Compose OTP-entry obligation is checkable in
  `make check` rather than only on a device.
- **`security-crypto` at an alpha version**, accepted because plain
  `SharedPreferences` leaves a 30-day refresh token readable via adb on a
  rooted phone. This is the only non-stable dependency in the project.

### Release configuration

`isMinifyEnabled = true` and `isShrinkResources = true` on release, with R8.
The minification is not primarily for size: the DEX gate scans the
**minified** build, because a debug build can differ in which dependencies
are present and the release AAB is what ships.

Signing reads four values from the environment and is **absent** when they
are, producing an unsigned build — correct for a local `assembleRelease`,
which must not silently produce something that looks uploadable. `versionCode`
and `versionName` come from Gradle properties supplied by CI, because Play
rejects a `versionCode` that is not strictly greater than every previous one
and that is not reversible.

`API_BASE_URL` has **no default on release**: every possible default is wrong
(a developer's machine shipped to a phone, or a production host reached from
a test build).

### What is NOT in the Android toolchain

The team practice names ktlint via spotless as the formatter and detekt as a
backstop. **Neither plugin is in `android/build.gradle.kts`, nor in any
build script, nor in `libs.versions.toml`.** There is also no `lint.xml`
raising `HardwareIds` to fatal, and no Kotlin coverage report. See
`code-quality-assessment.md`.

## Database

**PostgreSQL 16.** `postgres:16-alpine` in both `docker-compose.yml` and the
test container.

Features the project depends on and that are the reason SQLite is excluded
from testing:

- **Row-level security**, with `FORCE` so it applies to the table owner too.
- `NUMERIC(12,2)` for every money column, via one `TypeDecorator`.
- `set_config(key, value, true)` — transaction-local session variables, so a
  pooled connection cannot carry one request's account id into the next.
- Partial indexes, and `ON CONFLICT DO NOTHING` (relied on by the unbuilt
  fee-cycle work).
- A restricted non-superuser role, `shikkhok_app`, created by migration
  `0001` with explicit grants.

## Infrastructure and delivery

| Component | Version / choice |
|---|---|
| Terraform | `>= 1.10, < 2.0` — the floor is real: the S3 backend uses `use_lockfile`, which 1.9 lacks |
| AWS provider | `~> 5.70` (lockfile records 5.100.0) |
| State backend | S3 with `use_lockfile` (S3-native locking, no DynamoDB table) |
| Container base | `python:3.12-slim-bookworm`, multi-stage, non-root `USER app`, `HEALTHCHECK` hitting `/health` |
| Registry | Amazon ECR, images tagged by commit SHA; `latest` is never deployed |
| Edge | CloudFront + ACM (certificate in `us-east-1`) |
| DNS | Route 53 hosted zone with delegation |
| Compute | EC2, one instance per environment |
| CI | GitHub Actions — `check.yml`, `deploy.yml`, `release-android.yml` |
| Secrets scanning | Gitleaks (`gitleaks/gitleaks-action@v2`), blocking |
| SBOM | Syft, at the Android release gate only |
| Release notes | `scripts/release_notes.py` |

AWS authentication from CI is **OIDC** (`id-token: write`,
`aws-actions/configure-aws-credentials@v4` with a role), not long-lived keys.

### External services

- **BulkSMSBD** — the SMS gateway (`app/gateway/bulksmsbd.py`). The adapter
  asserts `https` in its constructor and attempts each send **once** with no
  automatic retry; a timeout is recorded as `unknown` rather than `failed`,
  because the SMS may have been delivered.
- **Google Play** — distribution. Store assets are committed under
  `store_listing/`.

No analytics, crash-reporting, ads or push SDK is present on either surface.
FCM is named in the plan as belonging to the unbuilt fee unit and has no
dependency entry today.

## Sources

- [code] `pyproject.toml`, read 2026-10-22 at commit `b14b1fa`
- [code] `gradle/libs.versions.toml`, `android/build.gradle.kts`,
  `gradle.properties`, `gradle/wrapper/gradle-wrapper.properties`
- [code] `infra/versions.tf`, `infra/.terraform.lock.hcl`
- [code] `Dockerfile`, `docker-compose.yml`
- [verified] installed Python package versions from `pip list`, 2026-10-22
- [verified] absence of ktlint, spotless, detekt, `lint.xml` by `grep`
  across all build scripts and version catalogues
