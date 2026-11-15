# Functional Design Questions — usernames-backend (U1)

Intent `261113-unique-usernames`. Only questions that need judgement are asked
here. Everything the requirements, ADR-001 to ADR-012, contracts C1 and C3, and
the accepted review points already settle is carried into the artifacts
without a question, and each corner of the corner checklist that has a sensible
default is written as a rule or an assumption rather than asked. The person
directed: "don't wait for my approval. Go with your recommendations." Each
answer below is the recommended option, listed as A, and was left to the agent.

## Question 1: Where is the sign-up replacement attempt counted, so a rollback cannot undo it? (Domain Design review R-09, Contract Design review R-03)

Context: ADR-011 rolls the whole verify transaction back when the draft's
username was taken meanwhile, so the code stays usable. The draft's
`username_replacements` counter lives inside that transaction, so every
increment is rolled back with it and the cap of 3 never binds. A correct code
could then try an unlimited number of names for its five-minute life, outside
every lookup ceiling. In `app/auth/ceilings.py`, the committing cascade
(`_consume`) commits each increment before checking it, independently of the
caller's later work.

A. Count every verify that carries a replacement username against the availability lookup's own ceilings (per /64, per /48, and the alert-only global count), consumed and committed at the start of the verify route, before the code is read. A refusal is HTTP 429 `auth.lookup.too_many`, `retryable: false`, and consumes no code attempt. Drop the per-draft cap: the `pending_signup.username_replacements` column and the `account.username.retry_limit` key are removed from C1 and C3 before either is built. The bound is then exactly the bound on the public lookup, which already answers the same question for anyone
B. Keep the cap of 3 as a committed counter: a new rate-limit scope keyed on the draft's contact, consumed by the committing cascade before the verify transaction, refusing the fourth replacement with `account.username.retry_limit`; also count against the lookup ceilings
C. Keep the cap of 3 only, as a committed counter (B without the lookup ceilings)
D. Refuse every replacement after the first and make the person start the draft again
X. Other (please specify)

[Answer]: A

## Question 2: May an account reclaim more than once inside one rename window? (Domain Design review R-10, Contract Design review R-04)

Context: ADR-012 exempts a reclaim from the 30-day rename limit and leaves
`username_changed_at` where it was. A reclaim also holds the name being given
up for this same account, so the next rename back is a reclaim too, and the two
names could alternate without limit inside the window. The contract's
`next_change_at` is "null when no limit applies", which says nothing after a
reclaim.

A. Only the first reclaim inside a rename window is exempt. The account records when it last reclaimed (`username_reclaimed_at`); a reclaim is exempt only while that value is absent or earlier than `username_changed_at`. A second reclaim in the same window is an ordinary rename and is refused as `account.username.change_too_soon`. After a reclaim, `next_change_at` is the unchanged `username_changed_at` plus 30 days
B. A reclaim moves `username_changed_at` to now, so it restarts the limit (this makes "undo my rename" cost another 30 days)
C. A reclaim is allowed once per hold, recorded on the hold row (the hold on the name given up is a new row, so the alternation survives)
D. No reclaim exemption at all (contradicts FR7.3 and ADR-012)
X. Other (please specify)

[Answer]: A

## Question 3: What is a change that alters only the letter case of the current username (`rahim_m` to `Rahim_M`)?

Context: uniqueness, sign-in and holds use the lowercase key, so the key does
not change. Treating it as an ordinary rename would start the 30-day limit and
place a hold on a key the account still holds.

A. A case-only change is allowed at any time after the password is confirmed. It is exempt from the rename limit, places no hold, does not move `username_changed_at` or `username_reclaimed_at`, and is audited as a username change. Sending exactly the stored text is a successful no-op with no audit row
B. A case-only change is an ordinary rename, subject to the limit, with no hold
C. A case-only change is refused as `account.username.unavailable`
X. Other (please specify)

[Answer]: A

## Question 4: What happens when a signed-in account that has a username but no password asks to rename?

Context: a session is normally issued by a password, but accounts that signed
in before passwords existed can still hold a session with no password (`POST
/v1/me/password` lets them set a first one with no current password). Contract
C1 says a rename or reclaim needs the password.

A. The rename is refused with `account.username.password_required` until a password is set; `GET /v1/me` already reports `has_password: false`, so the client routes the person to set one first. Choosing the FIRST username needs no password, as C1 says
B. Skip the password confirmation for an account without a password, as `change_password` does for its first password
C. Require a code sent to a verified contact instead
X. Other (please specify)

[Answer]: A

## Question 5: Which network prefix does the per-username-and-network failure ceiling (`un_fail_net_hour`) key on?

Context: ADR-007 counts username sign-in failures per username and network
prefix (10 an hour) and per username across networks (30 an hour), so an
attacker on one network cannot lock out the owner on another. The sign-in route
already computes two prefixes: the caller's /64 (IPv4 /24) and its /48 (IPv4
/24). Many subscribers of one mobile carrier share an IPv6 /48 and an IPv4 /24.

A. The /64 (IPv4 /24), the narrower prefix the route already passes as `ip_prefix`. An attacker spreading across /64s inside one /48 is still bounded by the existing shared per-/48 failure ceiling and by the 30-per-hour cross-network ceiling
B. The /48 (IPv4 /24): coarser, so a carrier-sharing owner is more likely to share the attacker's counter
C. Both, as two scopes (a seventh new scope name within 16 characters)
X. Other (please specify)

[Answer]: A
