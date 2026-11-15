# Security Requirements — usernames-backend (U1)

Intent `261113-unique-usernames`, unit U1 (kind: service). Each requirement
inherits the ID of the inception NFR it refines (`requirements.md`, NFR1 to
NFR9) and names the verifier that discharges it (project.md: NEVER record an
obligation without its verifier). Rules `BRn.m` and workflows `Wn` are in
`functional-design/rules.md` and `functional-spec.md`. Answers `[Q1]` to
`[Q5]` are in `nfr-requirements-questions.md`. Review findings `R-01` to
`R-09` are in `functional-design/reviews/review-01.md`.

**Where these requirements amend the approved functional design**, they are
listed in § "Amendments to the functional design" at the end. Code Generation
implements the amended form.

Threat summary for this unit. A username is a new, enumerable, low-entropy
identifier on a children's-data app. The failures that matter are these:

- a route other than the availability lookup becomes a fast oracle for whether
  a name exists;
- a stranger who knows a username keeps its owner from signing in, or guesses
  the password faster than the phone or email path allows;
- a username reaches anyone but its owner: another lens, the admin console, a
  log, an audit row, a counter row, a stored hold;
- the sign-in refusal reveals whether a username exists.

## NFR1 — Anti-enumeration

| ID | Requirement | Verifier |
|---|---|---|
| NFR1.1 | A failed username sign-in gives one response for three cases: unknown username, account with no password, and wrong password. Status 400, `code: PASSWORD_NOT_VALID`, `message_key: auth.password.wrong`. Body byte-identical. Headers identical except `X-Correlation-Id`. The same SQL statement sequence runs in all three, with exactly one scrypt evaluation each (BR4.4). The response is also identical to a failed phone or email sign-in. | Integration test, written first: the three full responses, plus a phone failure, compared byte for byte. A statement-capture test (SQLAlchemy `before_cursor_execute`) asserts the same statement texts in the same order. A spy asserts one scrypt call per request |
| NFR1.2 | The three cases take the same time: the work is identical by NFR1.1, and nothing branches on whether the account was found before the scrypt. | NFR1.1's statement and scrypt assertions prove the mechanism. **Nothing automated measures the time.** One manual run on staging: 20 sign-ins each for an unknown username, a password-less account and a wrong password, spread over different usernames so no ceiling refuses. The three medians must be within 10% of each other. Recorded in the Bolt's PR |
| NFR1.3 | A `login` value is classified as email (contains `@`), then phone (parses as a Bangladeshi mobile), then username (BR4.2). A username subject is never judged against FR1: a malformed one is an unknown key and gets NFR1.1's refusal, so a format rule cannot tell a real name from a typo. Only a malformed address with `@` gets a different answer (`email.invalid`), and that answer does not depend on any account. | Unit tests over the classifier, including `01712345678`, `+8801712345678`, `rahim@`, `ra..him` and a 254-character value. An integration test: `ra..him` gets NFR1.1's response |
| NFR1.4 | The public availability lookup answers only `status` (`available`, `unavailable`, `invalid`, `reserved`) and, for `invalid`, `message_key`. A held name and a taken name both answer `unavailable`. Its ceilings are consumed before the candidate is judged, so a refusal cannot depend on the answer (BR3.1, BR3.3). | Integration test, written first: taken, held for nobody, held for an account, and free names; the two unavailable bodies are byte-identical, and the schema has exactly those two properties |
| NFR1.5 | The authenticated availability check differs from the public one only when the name is under a live hold that the caller itself released, or is the caller's own current key (BR3.2). | Integration test, written first: a name held for account A answers `available` to A and `unavailable` to B and to an anonymous caller |
| NFR1.6 | **Authenticated claims are not an unmetered oracle (R-01, [Q2]).** (a) Every `PUT /v1/me/username` that passes the BR1 format check consumes the claim cascade (NFR2.2) through the committing `_consume`. This happens before the password check, before any lock, and before any read of another account or hold. (b) In a rename (W8), the window check comes before the availability check. Under the locks, after the re-read: if the key is unchanged, it is a case-only change (W8a). Otherwise, if the window is closed, the request proceeds only when the target is under a live hold released by the caller and the reclaim allowance is unused (an exempt reclaim, BR6.4). Every other target gets `account.username.change_too_soon` with `details.next_change_at`, without reading whether the target is on another account. Only with the window open does the claim rule (BR6.9) run. So a closed window tells the caller nothing about anybody else's name. | Integration tests, written first: (1) with the window closed, renames to a free name, a name on account B and a name held for nobody give byte-identical responses; (2) the 11th claim in an hour from one account gets 429 `auth.lookup.too_many`, even with a valid, free name; (3) a refused claim leaves the account row and the holds unchanged |
| NFR1.7 | Sign-up stays contact-independent. Every username decision at `POST /v1/accounts` (format, draft-time availability, the new 409) is made before, and without, any read of the contact. After it, the route does what it does today for every contact (BR2.2, BR2.9). | Integration test, written first: a contact with an account and one without, each with a free and then a taken username; the two free-name responses match, and the two taken-name 409s match |

## NFR2 — Rate limits

All counters are rows in the existing `rate_limit_counter` table, written
through the existing cascades in `app/auth/ceilings.py`. "Per /64" means the
caller's `ip_prefix` and "per /48" its `coarse_prefix`. For IPv4 **both are
the /24**, as built, so on IPv4 the effective per-network limit is the
smaller of the two. Windows are fixed UTC clock hours (`_window_start`), not
sliding, so a burst that straddles a boundary can reach twice a limit within
60 minutes. Every bound below is stated per window.

U1 adds twelve scope kinds in four separate families. No family reads
another's rows, on the reasoning `ceilings.py` gives for its existing
cascades. This replaces the five scopes in `entities.md`.

| Family | Scope kind (length) | Counts | Limit | On breach |
|---|---|---|---|---|
| A. Typing lookups | `un_lk_ip_hour` (13) | public (W4) and authenticated (W5) availability checks, per /64 | 30 per hour | refuse 429 `auth.lookup.too_many` |
| A | `un_lk_ip48_hour` (15) | the same, per /48 | 100 per hour | refuse 429 |
| A, B, C | `un_lk_global_hr` (15) | every username-existence answer served (W4, W5, every claim, every replacement), product-wide | `SHIKKHOKPLUS_GLOBAL_HOURLY_USERNAME_LOOKUPS`, default 1000 per hour | alert once on the request that fills it; never refuses |
| B. Claims | `un_cl_acct_hour` (15) | `PUT /v1/me/username` attempts (W7, W8), per account | 10 per hour | refuse 429 `auth.lookup.too_many` |
| B | `un_cl_ip_hour` (13) | the same, per /64 | 30 per hour | refuse 429 |
| B | `un_cl_ip48_hr` (13) | the same, per /48 | 100 per hour | refuse 429 |
| C. Replacements | `un_rp_dest_hour` (15) | verify requests carrying a replacement `username` (W2), per destination (the verify's phone, or `e:` plus the email's hash, the `lk_number_day` value) | 5 per hour | refuse 429 `auth.lookup.too_many` |
| C | `un_rp_ip_hour` (13) | the same, per /64 | 20 per hour | refuse 429 |
| D. Sign-in failures | `un_fail_net_hour` (16) | failed username sign-ins, per username and /64 | 10 per hour | refuse 409 `auth.password.too_many_attempts` |
| D | `un_fail_ip_hour` (15) | failed username sign-ins for any username, per /64 | 20 per hour | refuse 409, username sign-in only |
| D | `un_fail_ip48_hr` (15) | the same, per /48 | 60 per hour | refuse 409, username sign-in only |
| D | `un_fail_hour` (12) | failed username sign-ins, per username, across networks | 20 per hour | per-network block (NFR2.4): refuses only a network that has failed the name 3 times; never refuses a network with fewer |

| ID | Requirement | Verifier |
|---|---|---|
| NFR2.1 | **Family A, the typing lookups (OQ3).** The limits equal the already-added lookup's (`lk_ip_hour` 30, `lk_ip48_hour` 100, `lk_global_hour` 1000), so they are no looser (NFR2). Each check is consumed before anything is read, narrowest first. A refusal consumes nothing, including the refusing scope (`_consume`'s release). Family A has no per-account scope. The authenticated check reveals nothing beyond the public one except the caller's own holds (NFR1.5), and the same caller can use the public lookup, so a per-account limit would bound nothing. A refusal never blocks the form (BR3.4 as amended below): the submission's own check decides. This was sized against the case in functional-spec § 11. On a shared carrier /24, 30 checks an hour serve about five people typing a name with a client debounce of at least 500 ms. Beyond that, people get degraded hints, never a refused sign-up. The debounce is the clients' (U3, U4). | One test per refusing scope at the limit and one past it; one test that the global scope alerts once and refuses nothing; one test that a public and an authenticated check from one /64 draw on one counter |
| NFR2.2 | **Family B, claims (R-01, [Q2]).** `un_cl_acct_hour`, then `un_cl_ip_hour`, then `un_cl_ip48_hr`, consumed through `_consume` at the point NFR1.6(a) fixes, then counted in `un_lk_global_hr`. These are separate from Family A, so people typing on a shared network never stop an existing user finishing the choose-username screen (FR5.2), and claims are never refused because a lookup budget is spent. A person choosing or renaming tries a few names, so 10 per account is generous. The per-network scopes bound one caller holding several accounts. To spend a /24's 30 claims, a stranger needs at least three accounts, each of which cost a verified contact. The blocked person can retry in the next window. This is a stated residual, not a guarantee. | One test per refusing scope at the limit and one past it; NFR1.6's test (2); a test that 30 lookups from a /64 do not refuse a claim from it |
| NFR2.3 | **Family C, replacements (R-03, [Q3]).** `un_rp_dest_hour`, then `un_rp_ip_hour`, consumed in W2 step 3, before the code row is read, through the committing cascade, then counted in `un_lk_global_hr`. Typing lookups never spend it. A correct code can therefore try at most 5 names an hour for its destination, fewer than the 30 the public lookup allows. There is no /48 scope, because the number of destinations one caller can hold live codes for is already bounded by the signup ceilings (3 drafts per contact per day, 10 per /64 and 50 per /48 per hour). **Residual, stated plainly:** the count precedes the code check, so a stranger on the same /64 can spend its 20 with verifies that carry no valid code, and a stranger who knows the victim's contact can spend its 5. In both cases the person can still submit a new draft with another username (`POST /v1/accounts`, then a new code). The approved design's claim that a ceiling only degrades hints does not hold for this step, and BR2.6 and functional-spec § 11 are amended to say so. | One test per refusing scope at the limit and one past it; a test that the 6th replacement for one destination is refused while a 6th for a different destination from the same /64 is accepted; a test that a refused replacement leaves the code verifiable and the draft unchanged |
| NFR2.4 | **Family D, username sign-in failures (R-02, [Q1]).** Before the account lookup, the username path peeks (reads, never increments), in this order, and refuses at the first match: `un_fail_net_hour` ≥ 10; `un_fail_ip_hour` ≥ 20; `un_fail_ip48_hr` ≥ 60; `un_fail_hour` ≥ 20 **and** this network's `un_fail_net_hour` ≥ 3. **Amended at Code Generation** (the code-generation plan's one added decision, settling the open Major in the NFR review): the network condition is ≥ 3, not ≥ 1, so an owner who mistypes once or twice on their own network is not locked out after a stranger fills `un_fail_hour`. On a failure it increments all four, plus the existing alert-only `pwf_global_hour`, each committed. The username path **never reads or writes** `pw_fail_id_hour`, `vf_ip_hour`, `vf_ip48_hour` or `vf_global_hour`. Phone and email password sign-in and code verify are unchanged and read none of the `un_fail_*` scopes. What then holds, replacing BR4.7: (1) a stranger who fills `un_fail_hour` from their own networks cannot refuse the owner's username sign-in from any network on which that username has failed fewer than 3 times in the current window; (2) no username counter ever refuses a code verify, or a phone or email sign-in; (3) a stranger who shares the owner's /64 (on IPv4, the /24) can refuse username sign-in from that network for the rest of the window, by 10 failures on that name or 20 on any names. The owner can still sign in by phone, email or code. This residual is stated, not removed. | Integration tests, written first (`tests/auth/test_username_sign_in.py`): (a) the reviewer's case: fill `un_fail_hour` from three /64s (7, 7 and 6 failures), then the right password from a fourth /64 **succeeds**, and the 21st failure arriving from one of the three is refused; (b) the 11th attempt from one /64 on one name is refused with the right password, and the same name from another /64 succeeds; (c) 20 failures across different names from one /64 refuse a 21st username sign-in from it, while a code verify and a phone password sign-in from the same /64 are not refused; (d) a full `vf_ip_hour` does not refuse a username sign-in; (e) unknown and known usernames are counted identically; and the owner's case: two failures on the owner's own network, then a stranger fills `un_fail_hour` from three others (7 + 7 + 4, so the fill lands on the stranger's last failure), and the owner's right password from the owner's network **succeeds** while the stranger's networks stay refused |
| NFR2.5 | **The per-account guessing bound, recorded against FR4.4 and NFR2 (R-02).** In one window, an attacker can try at most this many passwords against one account. By username: at most 20 before `un_fail_hour` fills; after that, a /64 may go on failing the name only until it has failed it 3 times **counting its earlier failures**, and never more than 10 times in all (`un_fail_net_hour`). So with *k* /64s the username total is at most 20 + 3*k*, and an attacker who spreads round-robin reaches exactly 3*k* once 3*k* ≥ 20. The per-network term is also capped at 60 per /48 on IPv6 (`un_fail_ip48_hr`) and, on IPv4, by the /24 being both the /64 and the /48. By phone: 10 (`pw_fail_id_hour`). By email: 10. So for an account that has all three, the total is **at most 40 plus three per fresh network** per window, and twice that across a boundary. Before U1 it was 20 (phone and email); under the ≥ 1 rule this plan replaced, the per-network term was one, not three. Concurrent requests can exceed each figure by the number in flight, because the peek and the increment are separate statements, as on the built phone and email path. **Divergence from FR4.4 and NFR2.** They say "10 per username per hour", modelled on the phone and email limit, which refuses across all networks. U1 meets 10 per username **per network**. Across networks it allows 20, plus the per-network term, because a hard cross-network limit on an enumerable name would let anyone lock its owner out of it (B in [Q1], rejected). Raising the network condition from 1 to 3 widens that term by a factor of three in exchange for not locking an owner out over their own typos; this is the trade the plan records. Guessing across many networks is made visible by the existing `pwf_global_hour` alert at 300, and by NFR2.11 in observability. | The arithmetic above, checked by NFR2.4's tests (a) and (b) and by a test that counts accepted attempts from 25 distinct /64s inside 3 distinct /48s against one name in one window, round-robin: exactly 3 × 25 = 75 failures are counted (it was 20 + 5 = 25 under the ≥ 1 rule), and every later attempt is refused. This divergence is recorded for the requirements owner in § Amendments |
| NFR2.6 | Every new scope refuses in its own words. `CeilingBreach` maps Families A, B and C to 429 `auth.lookup.too_many` (they join `_LOOKUP_SCOPES`), and Family D to 409 `auth.password.too_many_attempts`, each as a literal key at a `message_key=` site so the key scanner sees it. No new scope falls through to `auth.otp.temporarily_unavailable`. | A parametrized test over every `ScopeKind` member whose value starts with `un_`: it asserts the status and key, and fails for a member it does not list |
| NFR2.7 | Every scope value fits its column: the kinds in `String(16)` (lengths in the table above), and the `un_fail_*` values in 64 characters (NFR3.3). | A test that writes a counter row for each new kind with a maximal value |
| NFR2.8 | **The rename limit (FR7.2).** One ordinary rename per 30 days (exactly 30 × 24 h). One exempt reclaim per window. A case-only change is allowed at any time (BR6.2 to BR6.7). | The functional design's test-first tests: rename on day 0, refused on day 20 with `next_change_at`, allowed on day 30; and the R-10 worked check from W8 as a test |
| NFR2.9 | A breach of a refusing scope writes nothing beyond what the built cascade writes. Family D writes `PASSWORD_CEILING_BREACHED` with no account id, as BR4.6 says. Families A, B and C write no audit row, because they are not authentication events, which matches the built already-added lookup. | Covered by NFR2.4 and NFR2.1's tests, which assert the audit rows |

## NFR3 — Privacy boundary and data protection

| ID | Requirement | Verifier |
|---|---|---|
| NFR3.1 | The username is served only to its owner, on `MeResponse.username` and `UsernameChangeResponse.username`, on routes in `LENS_EXEMPT_AUTHENTICATED`. `username_key` is never served (BR8.1). This is enforced mechanically: `username` and `username_key` join `OWNER_PRIVATE_FIELDS`; a new every-route walk fails on either field outside the two (schema, field) pairs on the lens-exempt routes; `"username"` joins the admin contract's `FORBIDDEN_TOKENS`; a membership test fails if an account column containing `username` exists outside those sets (BR8.2, BR8.3). The privacy suite runs as `shikkhok_app`, behind the existing superuser and row-level-security meta-check, and CI asserts that the integration suite ran (project.md Mandated). | The gate tests themselves, each with a planted-leak fixture that proves the gate fires: a teacher-lens schema, a guardian-lens schema and an admin schema each given a `username` field fail CI |
| NFR3.2 | A hold stores only `key_digest`: lowercase hex HMAC-SHA256 under `SHIKKHOKPLUS_OTP_HMAC_KEY` over `username-hold:v1:` plus the key, computed by one function (BR7.1). No hold row, log line or error carries the text or the key. | Test, written first: place each kind of hold for a sentinel name; then no column of `username_hold` contains the sentinel or its lowercase form, and the digest equals a known HMAC vector |
| NFR3.3 | **Counter values are keyed (R-04, [Q5]).** `un_fail_hour`: `'u:'` plus the first 62 hex characters of HMAC-SHA256 under `SHIKKHOKPLUS_OTP_HMAC_KEY` over `username-counter:v1:` plus the key. `un_fail_net_hour`: the same over `username-counter:v1:` plus the key, `|` and the /64. One function in the Usernames module computes both. The purpose prefixes keep these digests apart from hold digests and OTP digests. An HMAC-derived `'u:'` value still cannot equal a phone, `e:`, `acct:` or prefix value. Rotating the key resets these counters, so one more window of guesses becomes possible. `deploy/README.md` says so beside the hold line (BR7.7). The `rate_limit_counter` disposition basis says that username counters hold a keyed digest. | Tests: known HMAC vectors for both values; a sentinel username leaves no row whose `scope_value` contains it or its unkeyed SHA-256 |
| NFR3.4 | **No username in logs, audit rows, errors, notifications, SMS, email or counter rows (FR9.3, BR8.4).** `USERNAME_SET` and `USERNAME_CHANGED` carry the account id and correlation id only. Error envelopes carry the `message_key` and, for `change_too_soon`, the timestamp. `STRUCTURED_FIELDS` (`app/logging_setup.py`) gains no field that carries a subject, and in particular no `username` or `login`. | A sentinel test. W1 to W9, W8a and every refusal run with a distinctive sentinel username under `caplog` at DEBUG. The test asserts that the sentinel and its lowercase form appear in no captured record (message or `extra`), no `auth_audit_log` row, no `rate_limit_counter` row, no `username_hold` row and no response body other than the owner's `MeResponse` and `UsernameChangeResponse`. A second test asserts that `STRUCTURED_FIELDS` holds neither name |
| NFR3.5 | **No username in a URL (R-09, [Q4]).** Both availability lookups take the candidate in a JSON body: `POST /v1/accounts/username-availability` (public) and `POST /v1/me/username-availability` (authenticated), with request schema `UsernameAvailabilityRequest {username: string, maxLength 64}`. No route U1 adds or changes declares a query or path parameter named `username` or `login`. As a result, the host nginx's default access log (`infra/modules/app/user_data.sh.tftpl` sets no `log_format`) records only `POST /v1/... HTTP/1.1` for these routes, and FR9.3 and BR8.4 hold for that log too. `PUBLIC_ROUTES` gains `("POST", "/v1/accounts/username-availability")`. `LENS_EXEMPT_AUTHENTICATED` gains `("POST", "/v1/me/username-availability")` and `("PUT", "/v1/me/username")`. **Out of U1, recorded:** `GET /v1/accounts/already-added?phone=` and `?email=` (U2) still put a contact into that nginx log, as they do today. U1 does not change that route or claim anything for it. | An OpenAPI walk test: no operation has a parameter named `username` or `login` with `in` other than the body. The route-enumeration and allowlist count tests for the new entries |
| NFR3.6 | **Disclosure text states no unchecked count (R-07; project.md Forbidden).** The count is removed from four places, and each is reworded without a number: the `rate_limit_counter` basis in `app/governance/dispositions.py` (197, "two of the seven scopes"); the deletion note in `app/governance/deletion.py` (243, the same phrase); the `WINDOWS` comment in `app/governance/commands.py` (173-174, "Seven tables; the other eighteen"); and the docstring at `tests/governance/test_deletion.py:433`. The basis gets a reworded sentence, for example "for some scopes a phone number, or a keyed or one-way digest of an email address or a username". `docs/legal/PRIVACY.md` is regenerated from it. `username_hold` gets its disposition entry and retention class (BR7.6, BR7.7). | The existing policy-generation gate (a stale `PRIVACY.md` fails CI) and the governance completeness tests for `username_hold`. **Nothing automated prevents a new count being written into a comment later.** The removal itself is checked in the Bolt's review by a search for the four phrases, recorded in the PR |
| NFR3.7 | **The stale "dormant account" prose is corrected (FR8.4 second half, R-08).** The `Account` docstring (`app/db/models.py` 454-456 and 474-475) and the comment in `otp.py`'s `verify` (`app/auth/otp.py` 535-536) describe accounts as created by verify-first sign-up and `activated_at` as the first successful verify, as functional-spec § 1.3 words it. The `Enrollment` docstring's "dormant" seat (`models.py` 1169) is a current concept and stays. | A unit test: `"dormant"` does not occur in `Account.__doc__`, nor in `inspect.getsource(app.auth.otp.verify)` |
| NFR3.8 | The deletion hold, written in the deletion's one transaction, lasts 30 days with no releasing account (BR7.5). The existing daily retention purge deletes expired holds (BR7.6). | The functional design's tests, written first, through **both** deletion routes |
| NFR3.9 | Forgotten-password recovery and both deletion paths still take a phone or an email only, and gain no `login` field (BR9.1, FR10.1). | Schema tests: a `login` key on those requests is refused 422 as an unknown field (the built auth and deletion schemas declare `extra="forbid"`), and a username in the `email` field is refused as `email.invalid` |

## NFR4 — Test-first (security-relevant subset)

The full test-first set is `reliability-requirements.md` NFR4.1. The security
point: every requirement above marked "written first", together with every
`test_first: true` rule in `rules.md`, is a failing test committed before its
implementation on the Bolt branch.

## Data protection

- At rest: the new columns and `username_hold` are in the existing encrypted
  PostgreSQL storage (project.md: children's data encrypted at rest). U1 adds
  no store.
- In transit: unchanged (TLS at CloudFront, and from CloudFront to the
  origin). After NFR3.5, no username appears in a URL.
- Secrets: one existing secret, `SHIKKHOKPLUS_OTP_HMAC_KEY`, now keys three
  things: OTP digests, hold digests and username counter values. Rotating it
  invalidates in-flight codes (built), releases live holds early (BR7.7) and
  resets username failure counters (NFR3.3). The written, exercised-once
  rotation runbook that team.md asks for does not exist yet. That is recorded
  in functional-spec § 11, and writing it is outside this unit.
- Retention: `username_hold` until `held_until`, purged daily. Username
  counters expire on the counter table's existing 48-hour window and stay
  `NOT_PERSONAL` for deletion, which is now true because they are keyed
  (NFR3.3).

## Amendments to the functional design

These NFRs change approved functional-design text. Code Generation implements
the amended form, and updates `rules.md`, `entities.md` and C1 in the same
change:

1. **BR3.3, BR2.6, `entities.md` RateLimitCounter**: twelve scopes in four
   families (NFR2 table), not five sharing one family.
2. **BR3.4**: a lookup refusal never blocks submission. A claim refusal
   (Family B) and a replacement refusal (Family C) do refuse that submission,
   by design (NFR2.2, NFR2.3).
3. **BR4.5, BR4.7, W3 step 4 and step 7**: the Family D scheme and the restated
   guarantees (NFR2.4). Username failures leave the `vf_*` scopes.
4. **W7, W8**: the claim cascade's position, and window before availability
   (NFR1.6).
5. **W4, W5, C1, BR3.5**: both lookups become `POST` with a body (NFR3.5).
6. **BR4.5 counter values**: keyed (NFR3.3).
7. **FR4.4 and NFR2's "10 per username per hour"** is met per network, not
   across networks. The bound and the reason are in NFR2.5. This is recorded
   here for the requirements owner. U1 does not edit `requirements.md`.
8. **NFR2.4's network condition is ≥ 3, not ≥ 1** (added at Code
   Generation by the plan, settling the open Major in the NFR review), and
   NFR2.5's bound is recomputed for it. Applied to `rules.md` BR4.5 and
   BR4.7.

## Assumptions & Open Questions

- [assumption] Clients debounce typing-time checks by at least 500 ms and skip
  the call for a candidate that fails the client-side format hint (FR11.3
  allows format hints). NFR2.1's sizing assumes this, and the clients (U3, U4)
  own it.
- Checked, not assumed: moving the lookups to `POST` needs no CloudFront
  change. The API's default cache behaviour (`infra/modules/cdn/main.tf`
  245-250) allows `POST` and caches nothing, and the only path-specific
  behaviours are `/v1/admin*`, `/ui` and `/ui/*`.
- Open questions: None. [Q1] to [Q5] settle R-01 to R-04 and R-09. R-05 to
  R-08 are settled in reliability NFR6.1 and NFR4.2, and in NFR3.6 and NFR3.7
  above.

## Sources

- Initial description: the change request in `project-description.json`. [desc]
- Requirements NFR1, NFR2, NFR3, FR3, FR4, FR7, FR8.4, FR9, FR10:
  `inception/requirements-analysis/requirements.md`.
- Functional design (approved): `functional-spec.md` W1 to W10, § 7, § 11;
  `rules.md` BR2 to BR10; `entities.md`; review `reviews/review-01.md` R-01 to
  R-09.
- Contracts: `inception/contract-design/contract-summary.md` C1 and the
  2026-11-14 direction.
- Code read: `app/auth/ceilings.py` (constants 138-309, `ScopeKind` 329-401,
  `CeilingBreach` 472-574, `_consume` 1156-1203, password scopes 806-872),
  `app/auth/hashing.py`, `app/logging_setup.py`, `app/schemas/identifier.py`,
  `app/governance/commands.py` 92-175, `app/governance/deletion.py` 239-250,
  `app/governance/dispositions.py` 197, `app/db/models.py` 454-475 and 1169,
  `app/auth/otp.py` 535, `Dockerfile` 107-134,
  `infra/modules/app/user_data.sh.tftpl` 138-211, `app/api/accounts.py` 255.
- Answers: [Q1] to [Q5] in `nfr-requirements-questions.md`.
- Rules: team.md (Testing Posture; Deployment: secrets leak through logs;
  Code Style: error handling), project.md Forbidden and Mandated.
