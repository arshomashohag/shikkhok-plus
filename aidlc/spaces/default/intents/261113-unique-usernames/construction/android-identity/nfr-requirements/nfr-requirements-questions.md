# NFR Requirements Questions — U3 android-identity

Unit `android-identity` (U3, kind `ui`). Five questions the functional design,
the requirements and the built Android toolchain leave open. Everything else
is settled by NFR1–NFR9, the U1 sizing (Family A ceilings assume a client
debounce of at least 500 ms), and what is already built on this branch.

The person instructed: "don't wait for my approval. Go with your
recommendations." Every answer below is the recommended option, A.

## Q1. How long the availability hint may wait for an answer

The HTTP client (`core/network/ApiClient.kt`) installs no timeout plugin, so a
lookup waits for the OkHttp engine's own defaults (not configured in this
repository). A slow lookup would hold the hint at "Checking…" for that long.

A. Bound each availability lookup on the client to 3 seconds (coroutine
   `withTimeout` around the one call, which cancels the request). Past 3 s the
   hint reads "could not check", exactly like a refusal; submission is never
   blocked. No change to the shared client or to any other request.
B. Install Ktor's timeout plugin on the shared client with a global timeout.
C. Leave it to the engine defaults.
D. Bound it to 1 second.
E. Bound it to 10 seconds.
X. Other (please specify)

[Answer]: A

## Q2. How the ViewModel state-sequence tests observe a StateFlow

The functional design names Turbine for asserting emitted sequences. Turbine
is **not** on this branch's classpath (no entry in `gradle/libs.versions.toml`,
no test importing `app.cash.turbine`); the existing ViewModel tests use
`kotlinx-coroutines-test` (`runTest`, a test dispatcher, `advanceUntilIdle`).

A. Add no dependency. Sequence assertions collect the StateFlow into a list in
   the test's `backgroundScope` under `UnconfinedTestDispatcher`, the existing
   coroutines-test idiom; code generation reads "Turbine" in the functional
   design as "an emitted-sequence assertion".
B. Add Turbine as a test-only dependency (with a lockfile and checksum update).
C. Assert only final states, not sequences.
D. Test sequences through Robolectric UI tests only.
E. Write a small in-repo test helper that wraps collection.
X. Other (please specify)

[Answer]: A

## Q3. The foreground re-check while the account read is failing

The functional design (W4 step 8) re-reads `GET /v1/me` while the session is
`Failed`, on each return to the foreground and on an interval while in the
foreground, so the choose-username gate cannot be skipped for a whole
session by one transient failure.

A. Every 30 seconds while the app is in the foreground and the state is
   `Failed`, plus once on each return to the foreground; no backoff; stops the
   moment the state leaves `Failed` or the app leaves the foreground. Cost is
   bounded at 120 requests per foreground hour for a device whose reads keep
   failing, and zero otherwise.
B. Exponential backoff from 30 seconds up to 10 minutes.
C. Only on return to the foreground, no interval.
D. Every 10 seconds.
E. Every 5 minutes.
X. Other (please specify)

[Answer]: A

## Q4. How the low-end-device latency targets are verified

No Macrobenchmark harness exists on this branch, and the project has already
recorded that a latency obligation with no automated verifier is a manual
pilot check, stated as such (project.md Corrections, 2026-10-23).

A. Two verifiers. (1) The client's own timing logic — debounce, single
   in-flight request, the 3 s bound, latest-wins — is unit-tested in virtual
   time. (2) The perceived budget (hint answered within 1 s of the pause on a
   low-end device on a mobile network; gate first frame not preceded by the
   picker or home) is a timed manual check on the pilot's low-end device,
   recorded per screen. Nothing automated discharges (2), and the artifact says
   so.
B. Build a Macrobenchmark harness in this unit.
C. Rely on the backend's 300 ms p95 alone.
D. Manual check only, no unit tests of timing logic.
E. No verifier; treat it as best effort.
X. Other (please specify)

[Answer]: A

## Q5. Making "no identifier in a log line" mechanical on Android

There is no `android.util.Log` call and no Ktor logging plugin in
`android/src/main` today (searched), but nothing prevents one: neither
`detekt.yml` nor `lint.xml` forbids it. A request-body logger would print
usernames, passwords and codes.

A. Add `android.util.Log` and `io.ktor.client.plugins.logging.*` to
   `detekt.yml`'s existing, active `ForbiddenImport` list in this unit, so a
   log call or a request logger is refused at commit time. There are no
   existing uses, so the rule lands green. Stated limit: `println` and a
   fully qualified `android.util.Log.d(…)` with no import are not caught.
   `println` is a builtin, not an import, and `ForbiddenMethodCall` needs the
   type-resolved detekt run this project does not use (`detekt.yml` records
   the same limit for `Double`). Those two remain review's to catch.
B. Rely on review.
C. Allow `Log` but forbid it in release builds only (ProGuard strip).
D. Add a Timber-style wrapper that redacts.
E. Forbid only the Ktor logging plugin.
X. Other (please specify)

[Answer]: A
