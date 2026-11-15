# NFR Requirements Questions — usernames-backend (U1)

Intent `261113-unique-usernames`. These are the only questions that need
judgement. Everything else is already decided by the requirements (NFR1 to
NFR9), the approved functional design, U2's built mechanisms, team.md and
project.md, and goes straight into the artifacts. The availability-lookup
limits (OQ3) are not a question: NFR2 says "no looser than the already-added
lookup", so they are set equal to it (security-requirements NFR2.1). The
latency verifier follows U2's [Q3] for the same reasons and is not asked
again.

The person said: "don't wait for my approval. Go with your recommendations."
So each answer is the recommended option, listed as A, and the agent made the
choice.

## Question 1: How are failed username sign-ins counted, so that a stranger cannot keep a known username refused and guessing stays bounded?

Context: review-01 R-02. The approved design refuses a username at 30 failures
an hour across all networks (`un_fail_hour`), which three networks fill at 10
each, and usernames are enumerable through the public lookup. So anyone can
keep any known username's sign-in refused for about 30 requests an hour. The
design also counts username failures in the shared per-/64 and per-/48
failed-verify counters (`vf_ip_hour` 20, `vf_ip48_hour` 60), which every code
verify reads, so username guessing on a shared carrier /24 also stops code
sign-in there. Any per-username limit that refuses every network can be used
to lock the owner out. Any limit that refuses no network leaves guessing
bounded only by how many networks an attacker has.

A. Refuse per username and network (`un_fail_net_hour`, 10 an hour). Give username failures their own per-/64 and per-/48 counters (`un_fail_ip_hour` 20, `un_fail_ip48_hr` 60), so they never touch the code-verify counters. Keep the cross-network per-username counter (`un_fail_hour`) at 20 an hour, but when it is full refuse only networks that have already failed that username in the current window. A clean network always gets through. Record the resulting per-account bound across username, phone and email against FR4.4 and NFR2.
B. A hard cross-network limit of 10 per username an hour, as FR4.4 reads literally, accepting that a stranger can lock out the username path (phone and email sign-in still work)
C. Per-network refusal only, with the cross-network counter as an alert and never a refusal
D. Progressive delay or a challenge after N failures
X. Other (please specify)

[Answer]: A

## Question 2: How are the authenticated username claims (first choice and rename) metered, so they are not an unmetered existence oracle?

Context: review-01 R-01. `PUT /v1/me/username` counts nothing, so any signed-in
account can test whether a name is taken or held at full speed. In a rename,
the claim check also runs before the window check, so a closed window still
answers `unavailable` or `change_too_soon` depending on the name. If the claims
share the typing lookup's network counters, strangers typing on a shared
carrier /24 could stop an existing user finishing the choose-username screen,
which cannot be dismissed (FR5.2).

A. A separate committed claim cascade, consumed after the format check and before the password and any lock: `un_cl_acct_hour` 10 per account, `un_cl_ip_hour` 30 per /64 and `un_cl_ip48_hr` 100 per /48, each refusing. Every claim is also counted in the product-wide `un_lk_global_hr`. In a rename, the window is checked before availability: with the window closed, only a name held for the caller may proceed, and every other target gets the same `change_too_soon`. The authenticated availability check uses the public lookup's network counters and gets no per-account counter, because the public lookup is open to the same caller anyway.
B. Count claims on the typing lookup's counters (`un_lk_*`)
C. A per-account counter only
D. No counter, relying on the password a rename needs (the first choice needs none)
X. Other (please specify)

[Answer]: A

## Question 3: What budget does the replacement username at verify draw on?

Context: review-01 R-03. The approved design counts each replacement against the
typing lookup's counters, committed before the code is read. A person on a
shared carrier /24 with a correct code and a taken name can then get a 429 and
be unable to finish sign-up. Because the count comes before the code is read,
a stranger can also use up that budget with verifies that carry no valid
code. A counter inside the verify transaction would be rolled back (the
reason the design moved it out).

A. Its own committed cascade, consumed before the code is read: `un_rp_dest_hour` 5 per destination (the verify's phone or email, keyed like `lk_number_day`) and `un_rp_ip_hour` 20 per /64, each refusing, plus the product-wide `un_lk_global_hr` count. No /48 counter: the signup ceilings already bound how many destinations one caller can hold codes for. If it is blocked, the person can still submit a new draft with a different username.
B. Keep the typing lookup's counters, and record that the replacement can be blocked
C. A committed per-draft counter, written in its own transaction
X. Other (please specify)

[Answer]: A

## Question 4: The availability lookups carry the username in a query string, which nginx's local access log records. What changes?

Context: review-01 R-09. `Dockerfile` 121-128 turned uvicorn's access log off,
and says nginx's local access log still records full request lines. The host's
nginx site (`infra/modules/app/user_data.sh.tftpl` 138-211) sets no
`access_log` or `log_format`, so nginx's default format writes each request
line, query string included. `GET ...?username=` would therefore put
usernames on the host's disk, against FR9.3. CloudFront has no access logging
configured in `infra/`. The phone already-added lookup (U2) has the same
exposure today.

A. Move both username lookups to a JSON request body: `POST /v1/accounts/username-availability` and `POST /v1/me/username-availability`. C1 is amended (U1 owns it, and neither client is built yet). No route U1 adds or changes takes a username or a login in a query string, and a test over the OpenAPI document enforces that. The phone lookup's existing exposure is recorded and left to its owner.
B. Change the nginx `log_format` to log the path without arguments (an infrastructure change that needs the host replaced, and it also fixes the phone lookup)
C. Keep GET and record the nginx log as a stated exception to FR9.3
X. Other (please specify)

[Answer]: A

## Question 5: Are the username failure counters keyed with the server secret?

Context: review-01 R-04. The approved design stores `un_fail_*` counter values
as an unkeyed SHA-256 of the username. Usernames have low entropy, so a
counter row can be reversed with a dictionary for the 48 hours it lives, and it
survives account deletion as `NOT_PERSONAL`. The hold ledger uses an HMAC
under `SHIKKHOKPLUS_OTP_HMAC_KEY` for exactly this reason. If the counters use
that key too, rotating it resets every username failure counter.

A. Key them: `'u:'` followed by the first 62 hex characters of HMAC-SHA256 under `SHIKKHOKPLUS_OTP_HMAC_KEY`, over `username-counter:v1:` and the key (plus `|` and the /64 for the per-network counter). The rotation note in `deploy/README.md` adds that rotating the key resets these counters, worth at most one more window of guesses.
B. Keep unkeyed SHA-256, and restate the `rate_limit_counter` disposition basis to say that its values can be reversed with a dictionary
C. A new, separate secret for counter keys
X. Other (please specify)

[Answer]: A
