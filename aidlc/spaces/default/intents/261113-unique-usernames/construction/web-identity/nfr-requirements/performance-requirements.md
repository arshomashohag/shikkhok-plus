# Performance Requirements — U4 web-identity

The web client's share of NFR8 (responsiveness) and NFR2 (rate limits). The
server's own targets — the availability lookup's 300 ms p95 on staging
(U1 NFR8) and the Family A ceilings (U1 NFR2.1) — are U1's and are not
restated as client obligations. They are inputs here: U1 sized Family A on
the assumption that clients wait at least 500 ms after typing before asking
(U1 traceability, reverse item `NFR8/client-debounce`), and this unit keeps
that assumption for the web as U3 keeps it for Android.

Every requirement names its verifier. Where the verifier is a manual check,
the row says that nothing automated discharges it. The test files named
below are the ones frontend-components § 8 lists; they run under `vitest run`
inside `npm run check`, which `make web` runs in CI job `web`
(`.github/workflows/check.yml`).

## Requirements

| ID | Requirement | Verifier |
|---|---|---|
| NFR8.1 | **Typing-time debounce.** An availability lookup is sent only after **at least 500 ms** with no edit to the username field. Every edit restarts the wait. An empty trimmed value sends nothing. Applies on sign-up, the Replace step (both owners), the gate and the rename form (functional-spec W1 step 3, § 3.1). | `useUsernameAvailability.test.ts` under `vi.useFakeTimers()`: no request at 499 ms of quiet, one at 500 ms; an edit at 400 ms restarts the wait; empty and whitespace-only text send nothing. |
| NFR8.2 | **One lookup in flight per field, latest wins, answers remembered.** A newer lookup aborts the older one through its `AbortController`. An answer is applied only if it is for the trimmed text still in the field. Answers are remembered per text for the life of the mounted form, so retyping a remembered name sends nothing. | Same file: an edit while a request is held open aborts it (the mock sees `signal.aborted`) and its late answer never renders; a stale answer is dropped; a remembered text makes no call. |
| NFR8.3 | **Bounded wait, held by the checker's own timer** (review R-02). Each availability lookup is bounded at **3 s** measured from the moment the checker starts it. When the 3 s timer fires, the checker itself, without waiting for the request to settle: **(a)** sets `timedOut` and publishes could-not-check; **(b)** retires the request, so it is no longer the current one; **(c)** aborts its `AbortController`. A late settle of the retired request is then dropped by the settle step's first check ("this request is still the current one, else drop"). This ordering is required because the request may not settle at 3 s at all. For a signed-in lookup (gate, rename), `request()` first awaits `renew()` when the access token is stale (`api/client.ts:76-77`), and `renew()` takes no signal and has no timeout (`api/tokens.ts`), so an abort cannot end that wait. It must not take one: NFR8.7 depends on renewal outliving its callers. This **amends frontend-components § 2.2**, which settles the hint only when the request promise settles; code generation follows this row. Past 3 s the hint reads could-not-check, and submission is never blocked (FR3.2). The bound applies to the two availability lookups only; no other request's timing changes. How an abort is kept distinct from being offline is security-requirements NFR8.8. | `useUsernameAvailability.test.ts` with fake timers, three cases. **(1)** A `fetch` mock that **ignores its signal** and never settles: could-not-check at 3,000 ms and not at 2,999 ms. A mock that rejected on abort would let a settle-driven implementation pass, so the mock must not. **(2)** Signed in with a stale access token, `/v1/auth/refresh` held open for 5 s: the hint is could-not-check at 3,000 ms while the refresh is still pending. When the refresh then answers, the lookup's late result changes nothing on screen, and the rotated pair is in storage (NFR8.7). **(3)** A retired request that answers 200 after the 3 s bound leaves the hint at could-not-check, and the next edit checks again. |
| NFR8.4 | **Perceived hint latency on a low-end device.** In a browser on the pilot's low-end Android phone on a mobile network, the hint shows an answer (or "could not check") within **1 second of the pause that ends the debounce**, at the server's p95. Budget, for reading results only: about 300 ms server p95 (U1) plus network round trip plus render. | **Manual.** A timed check for sign-up, the gate and rename, recorded per screen (browser, device, network, observed times) in `docs/delivery/bangla-layout-check.md`, beside the U4 Bangla rows, with the Artboard column `web` (Q4). **Nothing automated discharges this:** no browser performance harness exists in `web/`, and the tests in NFR8.1–8.3 test the client's timing logic under fake timers, not real latency. |
| NFR8.5 | **Gate first render.** For an account whose read says `username_required: true`, the first render after resolving is the gate. No render shows the lens picker, the shell or any route's content first. Reaching the gate costs **no request beyond the `GET /v1/me` the app already makes**, because the flag travels in the same read and one `setSession` call publishes `username-required` (functional-spec W4 steps 1–2). | `ChooseUsernameGate.test.tsx` and `session.test.ts`: `sessionFromMe` with `true` gives `username-required`; first render on a typed URL such as `/settings`, and again after `history.back()`, is the gate, and the picker, shell and route content never render; the fetch mock records exactly one `/v1/me` before the gate shows. This is a routing-correctness test. It does not measure milliseconds, and none is claimed. |
| NFR8.6 | **No periodic re-read, and a bounded visibility re-read.** The web adds no timer-driven re-check: a failed read renders the blocking error card, so no app screen is reachable while the flag is unknown (functional-spec § 9 item 2). While the gate is in **Editing**, one quiet `GET /v1/me` is sent per `visibilitychange` to `visible`, and none in Saving or Rereading. A re-read never publishes `resolving` while the gate shows, so it never flashes the loader. Cost: one read per return to the tab while the gate shows; zero otherwise. | `ChooseUsernameGate.test.tsx`: visibility to visible in Editing sends one read; in Saving and Rereading sends none; "a refresh while the gate shows never renders the resolving loader". |
| NFR2.1 | **No automatic retry, and a 429 ends checking for the form.** A refusal other than 429, a timeout or a transport failure leaves the hint at "could not check" until the person edits the field; nothing re-sends by itself. A 429 `auth.lookup.too_many` stops all further lookups from that mounted form; later edits show the could-not-check text without a request. Submission stays available (FR3.2). | `useUsernameAvailability.test.ts`: after a transport failure the mock sees no call until the next edit; after a 429 it sees **no call at all**, even after further edits and 500 ms of quiet. |
| NFR2.2 | **Writes are sent once per person action.** Sign-up, the Replace retry, the gate's choice, rename, contact replace and remove, and the student Edit sheet are each sent only on the person's action, with the submit control disabled while the request is in flight (functional-spec § 7, double submit). None is retried by the app (TC-8, D-9). A retry is a new press of Retry, offered for a retryable envelope or no response. | The screen tests named in frontend-components § 8 (`SignUp.test.tsx`, `ChooseUsernameGate.test.tsx`, `username.test.tsx`, `contacts.test.tsx`, `people.test.tsx`): a second press while the mock holds the request open sends nothing; Retry after a transport failure resends the same body. |
| NFR2.3 | **What actually bounds the lookup rate.** A 500 ms debounce spaces each lookup from the last edit; it does not bound a rate. Worst case, a person who edits just over every 500 ms sends one lookup per edit: under 7,200 per hour per field (3,600 s ÷ 0.5 s), against Family A's 30 per /64 per hour. That figure is arithmetic on the debounce, not a measurement. The client-side limits are the per-text memory and the single in-flight request (NFR8.2) and the stop-after-429 rule (NFR2.1), which caps a form at the lookups it sends before the server's window is spent, plus none after. **The rate bound is the server's Family A ceiling** (U1 NFR2.1). No client-side minimum interval is added, for U3's reason: any interval short enough to keep the hint useful while typing still exceeds 30 per hour. | NFR2.1's tests. No test asserts a rate, and none is claimed. |

## Not applicable to this unit

- Server throughput, database latency and ceiling values: U1 and U2.
- Bundle size and first load: unchanged in kind. The unit adds screens and no
  dependency (tech-stack TSD-1). No bundle-size budget exists in `web/`, and
  none is introduced; the production build in `npm run check` is the only
  check that the bundles still build.
- Service-worker caching: unchanged (`runtimeCaching: []` in `vite.config.ts`);
  API responses are never cached, so there is no cache freshness target.

## Assumptions & Open Questions

- [assumption] The pilot's low-end Android phone is the device the project
  uses for its other manual pilot checks. It is not named here because no
  device is recorded in this unit's inputs.
- [assumption] NFR8.4's 1 s is a perceived-responsiveness target derived from
  NFR8's purpose ("usable while typing"), kept equal to U3's so the two
  clients are judged by the same budget. It is not a figure from the
  requirements.
- [assumption] Vitest fake timers drive the checker's own `setTimeout`
  timers. The 3 s bound is the checker's timer, not `AbortSignal.timeout()`,
  so the test does not depend on whether jsdom's `AbortSignal.timeout` follows
  faked time.
- Open questions: None.

## Sources

- Requirements: `inception/requirements-analysis/requirements.md` NFR2, NFR8,
  FR3.2, FR5.2.
- Functional design: `construction/web-identity/functional-design/functional-spec.md`
  W1, W4 (steps 1–3, 8–10), § 3.1, § 7, § 9 items 2 and 6;
  `frontend-components.md` § 2.2, § 2.3, § 8.
- U3 reference: `construction/android-identity/nfr-requirements/performance-requirements.md`
  NFR8.1–8.6, NFR2.1–2.3 and its review findings R-02 and R-07.
- U1 sizing assumption: `construction/usernames-backend/nfr-requirements/traceability.json`
  reverse item `NFR8/client-debounce`.
- Code read: `web/package.json` (`check`, `test` scripts; no performance
  tooling), `web/vite.config.ts` (`test` block, `runtimeCaching: []`),
  `web/src/core/useResource.test.tsx` (existing `vi.useFakeTimers` use),
  `.github/workflows/check.yml` (job `web`).
- Project rule: `project.md` Corrections 2026-10-23.
- Answers: `nfr-requirements-questions.md` Q4 [Q4].
