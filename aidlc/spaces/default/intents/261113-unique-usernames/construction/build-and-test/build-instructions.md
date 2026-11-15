# Build Instructions — Unique usernames

Intent `261113-unique-usernames`, units U1 `usernames-backend`, U2
`contacts-and-invites-backend`, U3 `android-identity` and U4 `web-identity`.
Every command runs from the repository root unless a `cd` is shown. These are
the same targets CI runs (`.github/workflows/check.yml`); there is no separate
CI-only build.

The person's instruction for this stage: "don't wait for my approval. Go with
your recommendations." This stage defines no questions file, so none was
written; the choices made under that instruction are listed under
Assumptions & Open Questions.

## 1. Prerequisites

| Tool | Version CI uses | Version in this run's environment | Needed by |
|---|---|---|---|
| Python | 3.12 (`actions/setup-python`, `requires-python`, Docker base) | 3.13.18 in `.venv` | U1, U2 |
| Docker daemon | runner's own | 29.9.2 (had to be started for this run; see § 4) | U1, U2 integration suite, `image` job |
| JDK | Temurin 17 | OpenJDK 21.0.12.1 | U3 |
| Android SDK | via `setup-gradle` / SDK on runner | present | U3 |
| Gradle | wrapper 8.11.1 | wrapper 8.11.1 | U3 |
| Node.js | 22 | 22.23.4 | U4, `site`, `infra-functions` |

The project targets Python 3.12 everywhere. The local interpreter is 3.13, which
the team practice already records as an environment note: a 3.13-only behaviour
would pass here and fail in CI and in the container. CI's `backend` job and the
`image` job are the 3.12 arbiters.

## 2. Dependency installation

**Backend (U1, U2).** The install reads the hashed lockfile; it never
re-resolves.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python -m pip install -e . --no-deps
```

`requirements.txt` is regenerated only with `make lock`. Neither
`pyproject.toml` nor `requirements.txt` changed in this intent (checked with
`git diff <merge-base> -- pyproject.toml requirements.txt`: no output).

**Android (U3).** Gradle resolves against `android/gradle.lockfile`
(`dependencyLocking { lockAllConfigurations() }`) and verifies artifacts against
`gradle/verification-metadata.xml`. No dependency, lockfile or verification
metadata changed in U3.

**Web (U4).**

```bash
cd web && npm ci --no-audit --no-fund
```

`npm ci` fails if `package.json` and `package-lock.json` disagree. Neither
changed in U4.

## 3. Environment setup

- **No secret is needed** for any build or test command. Test fixtures set
  `SHIKKHOKPLUS_OTP_HMAC_KEY` and the database URLs themselves.
- **Docker must be reachable** for the backend integration suite.
  `tests/conftest.py` starts `postgres:16-alpine` through testcontainers,
  migrates it, and connects the suite as the restricted role `shikkhok_app`.
  Without Docker the integration suite **skips** locally and **fails** when
  `CI=true` is set. Run locally with `CI=true` so a missing daemon is a failure
  rather than a quiet skip, as this run did.
- **Images pulled**: `postgres:16-alpine`, `testcontainers/ryuk`.

## 4. Build and verification commands

| # | Command | What it builds or checks |
|---|---|---|
| B1 | `CI=true make PY=.venv/bin/python lint typecheck test` | Ruff format and check, mypy over `app`, the whole pytest suite (unit and integration) once with a JUnit report, then four coverage reports from the same data: money 100% branch, contact matcher and advisory 100% branch, usernames 100% branch, the rest of `app/` 80% line |
| B2 | JUnit skip check (the CI step "Every test ran", run as written against `build/pytest-junit.xml`) | Fails on any skipped test |
| B3 | `./gradlew :android:testDebugUnitTest :android:detekt :android:lintDebug :android:spotlessCheck :android:verifyCoverageRatchet --no-daemon` | Kotlin compile and JVM unit tests, detekt, Android Lint (HardwareIds fatal), Spotless (Gradle and XML), the JaCoCo ratchet against `android/coverage-floor.txt` |
| B4 | `make web` | `npm ci`, then `npm run check`: generated-file drift (`schema.d.ts` against `openapi.json`, strings against the Android bundles), Prettier, ESLint `--max-warnings 0`, `tsc`, Vitest, the main and admin production builds, and the bundle-separation check |
| B5 | `make site` | Public site build and its tests (not changed by this intent; run because CI runs it) |
| B6 | `make infra-functions` | CloudFront Function tests (not changed by this intent; run because CI runs it) |

`make check` runs B1, the Android suite, the Android quality gates, B4, B5 and
B6 in sequence. CI splits them across jobs; locally they can be run as above.

### Build verification

- B1 exits 0 and prints four `coverage report` tables, each at or above its
  floor. A coverage floor in the `Makefile` or `.coveragerc-backend` is never
  lowered to make this pass.
- B2 prints `<n> tests ran; none skipped.`
- B3 prints `BUILD SUCCESSFUL`; the ratchet line names the measured figure and
  the floor. `android/coverage-floor.txt` stays at its committed value.
- B4 ends with `✓ main and admin bundles are separate`.

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Cannot connect to the Docker daemon` and the integration tests show as skipped | No daemon. In this run's environment the socket file existed but no `dockerd` process was running | Start the daemon (`dockerd &`, or the platform's service), confirm with `docker info`, re-run B1 with `CI=true` |
| pytest is much slower than CI's ~12 minutes | Fewer cores, or another heavy job (Gradle) running at the same time | Expected locally; it is not a failure. CI's `backend` job has a 20-minute cap |
| `requirements.txt does not match pyproject.toml` in CI | A dependency was added to `pyproject.toml` without recompiling | `make lock`, then read the diff. Never hand-edit the lockfile |
| Schema-diff gate fails | `openapi.json` is stale | `make openapi`, then read the diff. Never hand-edit `openapi.json` |
| `check:generated` fails in `make web` | `openapi.json`, `message-keys.json` or the Android string bundles changed without regenerating the web copies | Regenerate with the web generator scripts (`web/scripts/`), then re-run |
| `verifyCoverageRatchet` fails | Kotlin coverage dropped more than 0.5 points below the floor | Add tests. **Do not lower `android/coverage-floor.txt`**, even though the task's message offers it (project Forbidden) |
| Gradle prints "a single-use Daemon process will be forked" | `JAVA_TOOL_OPTIONS` is set in this environment (proxy trust store) | Harmless |

## Sources

- `.github/workflows/check.yml` (jobs, steps, Python 3.12, JDK 17, Node 22).
- `Makefile` targets `lint`, `typecheck`, `test`, `android`, `android-quality`,
  `web`, `site`, `infra-functions`, `lock`, `openapi`.
- `tests/conftest.py` (`_require_docker`, `postgres_url`, `restricted_url`).
- Per-unit `code-generation/unit-test-instructions.md` for U1–U4.
- `aidlc/spaces/default/memory/team.md` § Testing Posture and § Code Style
  (Python 3.12 environment note); `project.md` Forbidden (coverage floors).

## Assumptions & Open Questions

- **Assumption**: the local Python 3.13 interpreter is acceptable for this
  stage's run because CI's `backend` and `image` jobs run 3.12 and are the
  arbiters; this is the team's recorded environment note, not a new decision.
- **Assumption**: starting the local Docker daemon is environment setup inside
  this stage's remit (no application file changes). The brief said the daemon
  was running; it was not, and it was started before any test ran.
- **Open**: none.
