# Performance Requirements — U3 android-identity

The Android client's share of NFR8 (responsiveness) and NFR2 (rate limits).
The server's own targets — the availability lookup's 300 ms p95 on staging
(U1 NFR8), the Family A ceilings of 30 per /64 and 100 per /48 per hour
(U1 NFR2.1) — are U1's and are not restated as client obligations. They
matter here as inputs: U1 sized Family A on the assumption that clients wait
at least 500 ms after typing before asking (U1 traceability, reverse item
`NFR8/client-debounce`), so that assumption is this unit's to keep.

Every requirement names its verifier. Where the verifier is a manual check,
the row says that nothing automated discharges it.

## Requirements

| ID | Requirement | Verifier |
|---|---|---|
| NFR8.1 | **Typing-time debounce.** An availability lookup is sent only after **at least 500 ms** with no edit to the username field. Every edit restarts the wait. An empty trimmed value sends nothing. This applies on sign-up, the replacement step, the gate and the rename form (functional-spec W1 step 2). | Unit test in virtual time (`kotlinx-coroutines-test`) on `UsernameAvailabilityChecker`. No request before 500 ms of quiet, one after it, restart on edit, none for empty text. Tests named in frontend-components § 8. |
| NFR8.2 | **One lookup in flight per field, latest wins, answers remembered.** A new lookup is not sent while one is outstanding; the next is sent when the outstanding one settles, if the text has changed. An answer is applied only if its text equals the field's current trimmed text. Answers are remembered per text for the screen's life, so retyping a name sends nothing. | Unit tests on the checker: second edit while one call is suspended, stale answer dropped, remembered text makes no call. |
| NFR8.3 | **Bounded wait, and cancellation kept distinct from failure** (review R-02). As built, the shared helpers `call { }` and `callDiscardingBody { }` (`core/network/HttpAuthRepository.kt:239-308`) catch `Exception`. That arm also catches `CancellationException`, `TimeoutCancellationException` included, and turns it into `TransportFailure`. A timeout or a cancelled stale lookup inside the helper therefore comes back as an ordinary value, and the code after it would go on to publish that value. Three rules: **(a)** both helpers rethrow `CancellationException` before their `Exception` arm, so cancellation propagates as structured concurrency intends; this changes behaviour only for a caller that was cancelled, and that caller no longer receives a value. **(b)** The checker wraps the repository call (outside `call { }`) in `withTimeoutOrNull(3_000)` (Q1). `null` maps explicitly to `CouldNotCheck`; a `TransportFailure` also maps to `CouldNotCheck`, so the two are distinguished in the code but render the same hint. **(c)** A superseded lookup is cancelled by cancelling its `Job`. Its result is never applied: cancellation now propagates out of the helper, and the apply step also checks that the answered text equals the current text. No other request's timeout changes. | `MockEngine` tests through the real `ApiClient.build(engine = …)` and the real repository, with the engine's dispatcher set to the test dispatcher so virtual time drives it: **(1)** a handler that suspends for ever yields `CouldNotCheck` at 3 s and not before; **(2)** a slow handler for text "ab" followed by an edit to "abc" leaves the hint on "abc"'s answer, and "ab"'s late result is never applied; **(3)** a helper test: cancelling the caller of `call { }` while the handler is suspended propagates `CancellationException` and returns no `TransportFailure`. |
| NFR8.4 | **Perceived hint latency on a low-end device.** On the pilot's low-end Android device on a mobile network, the hint shows an answer (or "could not check") within **1 second of the pause that ends the debounce**, at the server's p95. Budget, for reading results only: about 300 ms server p95 (U1) plus network round trip plus render. | **Manual.** Timed check on the pilot's low-end device for sign-up, gate and rename, recorded per screen with device, network and observed times beside the Bangla layout rows (`docs/delivery/bangla-layout-check.md` or the pilot record). **Nothing automated discharges this:** no Macrobenchmark harness exists on this branch, and the unit tests in NFR8.1–8.3 test the client's timing logic, not the device's latency (Q4). |
| NFR8.5 | **Gate first frame.** For an account with `username_required: true`, the first frame composed after the Resolving loader is the choose-username gate. No frame shows the lens picker, the home or More first. Reaching the gate costs **no request beyond the `GET /v1/me` the app already makes** at sign-in and cold start, because the flag travels inside `SessionUiState` (functional-spec W4 steps 1–2). | Robolectric routing test `first composed frame after Resolving is the gate when the read says true`, asserting the picker and home tags never appear (frontend-components § 8). This is a routing-correctness test. It shows the gate is not preceded by another screen; it does not measure milliseconds, and none is claimed. |
| NFR8.6 | **Re-check cost while the account read is failing** (Q3). While signed in and `SessionUiState.Failed`: one quiet `GET /v1/me` on each return to the foreground, and one every **30 seconds** while in the foreground. The re-check stops when the state leaves `Failed` or the app leaves the foreground. Upper bound: 120 requests per foreground hour on a device whose reads keep failing; zero when the read succeeds. No `Resolving` is published, so a re-check never tears down the screen in use. | Unit tests on `SessionViewModel.recheck` (`recheck never publishes Resolving`, `recheck that fails again leaves Failed`). Robolectric test of the re-check effect under a virtual clock (`failed read then foreground re-check …`, frontend-components § 8). The cadence constant is asserted by that test, not stated in a comment. |
| NFR2.1 | **No automatic retry, and a 429 ends checking for the screen.** Any other refusal, a timeout or a transport failure leaves the hint at "could not check" until the person edits the field; nothing re-sends by itself. A 429 `auth.lookup.too_many` means the server's hourly window is spent, so **that screen instance sends no further lookups** (review R-07). Further edits show "could not check now — you can still continue" without a request. Submission stays available (FR3.2). | Unit tests: after a transport failure the fake sees no call until `edited(…)`; after a 429 the fake sees **no call at all**, even after further edits. |
| NFR2.2 | **Writes are sent once per person action.** Sign-up, the verify replacement, the first choice, rename, contact replace and remove are each sent only on the person's tap. Each is ignored while its request is in flight, and is never retried by the app (TC-8, D-9). A retry is a new tap on Retry, offered only where the envelope says `retryable` or no response arrived. | ViewModel tests named in frontend-components § 8 ("double submit ignored", "transport → retry resends the same request"). |
| NFR2.3 | **What actually bounds the lookup rate** (review R-07). A 500 ms debounce spaces each lookup from the last edit; it does not bound a rate. Worst case, a person who types one character just over every 500 ms sends a lookup per character. That is roughly 7,000 per hour per field in theory, against Family A's 30 per /64 per hour. For ordinary typing, one lookup per pause, a ten-character name costs a few lookups; that is an estimate, not a measurement. The client-side limits are the per-text cache (NFR8.2), the single in-flight request (NFR8.2), and the stop-after-429 rule (NFR2.1), which caps a screen at the requests it makes before the server's window is spent plus none after. **The rate bound is the server's Family A ceiling** (U1 NFR2.1). When it is reached, the hint degrades to "could not check" and submission is unaffected. No client-side minimum interval is added: any interval short enough to keep the hint useful while typing would still exceed 30 per hour, so it would add complexity without bounding anything the server does not already bound. | NFR2.1's tests (stop after 429). The theoretical figure is arithmetic on the debounce, stated as such; no test asserts a rate. |

## Not applicable to this unit

- Server throughput, database latency and ceiling values: U1 and U2.
- App start time, list rendering and memory: unchanged by this unit, which
  adds no list larger than two contact cards and no background work besides
  NFR8.6.

## Assumptions & Open Questions

- [assumption] The pilot's low-end device is the same device the project
  uses for its other manual pilot checks; it is not named here because no
  device is recorded in this unit's inputs.
- [assumption] NFR8.4's 1 s is a perceived-responsiveness target derived from
  NFR8's purpose ("usable while typing"), not a figure from the requirements.
- Open questions: None.

## Sources

- Requirements: `inception/requirements-analysis/requirements.md` NFR2, NFR8,
  FR3.2, FR5.2.
- Functional design: `construction/android-identity/functional-design/functional-spec.md`
  W1, W4 (steps 1, 2, 8); `frontend-components.md` § 2.8, § 8.
- U1 sizing assumption: `construction/usernames-backend/nfr-requirements/traceability.json`
  reverse item `NFR8/client-debounce`.
- Code read: `android/src/main/kotlin/com/shikkhokplus/app/core/network/ApiClient.kt`
  (no timeout plugin installed); `gradle/libs.versions.toml` (no Macrobenchmark,
  no Turbine).
- Project rule: `project.md` Corrections 2026-10-23 (a manual verifier is
  recorded together with the statement that nothing automated discharges it).
- Answers: `nfr-requirements-questions.md` Q1, Q3, Q4 [Q1] [Q3] [Q4].
