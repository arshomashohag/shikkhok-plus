# Business Rules — usernames-backend (U1)

Intent `261113-unique-usernames`, unit U1. Source of truth for this unit's
decision logic. `test_first: true` marks a rule that meets the team's
test-first predicate (team.md, Testing Posture): the correct output is knowable
from the requirement before the code exists, and a wrong answer is an
authorization error (who may sign in, who may take a name, who may see it).
Those tests are written first. The other rules are test-after, written from
the rule and never from the implementation.

**Amended at Code Generation** by `nfr-requirements/security-requirements.md`
§ Amendments (items 1 to 6) and by the code-generation plan's one added
decision: in Family D the across-networks count refuses a network only once
that network has failed the name 3 times (not 1). The amended rules say so
in their own logic; BR2.6, BR3.1 to BR3.5, BR4.5 to BR4.7, BR6.1 and BR10.1
changed.

HTTP statuses follow the built taxonomy handler (`app/errors/handler.py`):
`ValidationError` renders 400, `ConflictError` 409 (or 429 for a lookup
ceiling), and a request the schema itself rejects (a missing required field,
an over-long field) is FastAPI's 422. `retryable` is read from the class and
is false for all three.

Groups: BR1 what a username is; BR2 sign-up; BR3 availability; BR4 sign-in;
BR5 `username_required` and the first choice; BR6 rename and reclaim; BR7 the
hold ledger; BR8 privacy; BR9 recovery and deletion stay phone-or-email; BR10
concurrency.

```yaml
rules:
  # ---------------------------------------------------------------- BR1
  - id: BR1.1
    statement: Leading and trailing whitespace is removed before a username is judged; whitespace inside it is an invalid character.
    category: validation
    applies_to: [UsernameCandidate]
    trigger: Any username input - sign-up, the replacement at verify, first choice, rename, either availability lookup
    logic: >
      Remove leading and trailing whitespace. The result is the candidate's
      text. IF any whitespace remains inside it THEN the candidate is refused as
      invalid_character (BR1.6). The sign-in field is trimmed too but is not
      judged by this group (BR4.2).
    violation: account.username.invalid_character (ValidationError, 400, code USERNAME_INVALID); the request is otherwise untouched.
    source: [FR1.4]
    test_first: false

  - id: BR1.2
    statement: A username uses only Latin letters, digits, underscore and dot.
    category: validation
    applies_to: [UsernameCandidate]
    trigger: As BR1.1
    logic: IF any character of the text is outside a-z, A-Z, 0-9, "_" and "." (Bangla script, "@", "-", spaces, any other code point) THEN refuse as invalid_character.
    violation: account.username.invalid_character (400, USERNAME_INVALID).
    source: [FR1.1]
    test_first: false

  - id: BR1.3
    statement: A username is 3 to 20 characters long, inclusive.
    category: validation
    applies_to: [UsernameCandidate]
    trigger: As BR1.1
    logic: >
      Count characters of the trimmed text (all are single-byte once BR1.2
      holds). IF fewer than 3 THEN too_short (an empty or whitespace-only input
      is too_short). IF more than 20 THEN too_long. 3 and 20 are accepted.
      Input longer than 64 characters never reaches this rule: the request
      schema refuses it with 422.
    violation: account.username.too_short or account.username.too_long (400, USERNAME_INVALID).
    source: [FR1.1]
    test_first: false

  - id: BR1.4
    statement: A username starts with a Latin letter.
    category: validation
    applies_to: [UsernameCandidate]
    trigger: As BR1.1
    logic: IF the first character is a digit, "_" or "." THEN refuse. This is what makes a username never parse as a phone number (A3).
    violation: account.username.must_start_with_letter (400, USERNAME_INVALID).
    source: [FR1.2]
    test_first: false

  - id: BR1.5
    statement: A username does not end with a dot and never has two dots in a row.
    category: validation
    applies_to: [UsernameCandidate]
    trigger: As BR1.1
    logic: IF the last character is "." OR the text contains ".." THEN refuse.
    violation: account.username.bad_dot (400, USERNAME_INVALID).
    source: [FR1.2]
    test_first: false

  - id: BR1.6
    statement: Every refusal names exactly one broken rule, chosen by a fixed precedence, as a message_key, and never echoes the input.
    category: validation
    applies_to: [UsernameCandidate, every username refusal]
    trigger: A candidate fails one or more of BR1.1-BR1.5 or BR1.8
    logic: >
      Check in this order and stop at the first failure: invalid_character
      (BR1.1, BR1.2), too_short then too_long (BR1.3), must_start_with_letter
      (BR1.4), bad_dot (BR1.5), reserved (BR1.8). So "01712345678" is
      must_start_with_letter, "_rahim" must_start_with_letter, "rahim." and
      "ra..him" bad_dot, "রহিম" invalid_character, "Admin" reserved, "ab"
      too_short. The refusal carries the key only; the client keeps the typed
      text itself (FR1.6). Taken and held are not format refusals: they are
      account.username.unavailable (BR3.1, BR10.2), and there is no separate
      "held" key on any surface (ADR-007 amends FR1.6).
    violation: The one key above.
    source: [FR1.6, FR1]
    test_first: false

  - id: BR1.7
    statement: Uniqueness, sign-in and holds use the username's lowercase key; the display keeps the person's casing.
    category: constraint
    applies_to: [Account.username, Account.username_key, UsernameHold.key_digest]
    trigger: A username is stored, compared, looked up or held
    logic: >
      key = lowercase(text). Two candidates with equal keys are the same
      username: "Rahim_01" and "rahim_01" cannot both exist. The account stores
      text as username and key as username_key. Every comparison - uniqueness,
      the reserved list, holds, sign-in - uses the key.
    violation: A second account claiming an existing key is refused as account.username.unavailable (BR6.9).
    source: [FR1.3]
    test_first: true

  - id: BR1.8
    statement: Reserved names are refused at every claim, compared by key, from one server-side list.
    category: policy
    applies_to: [UsernameCandidate]
    trigger: Sign-up, the replacement at verify, first choice, rename; either availability lookup answers "reserved"
    logic: >
      IF the key exactly equals a member of the one reserved list (at least
      admin, administrator, support, help, shikkhokplus, shikkhok, system, root,
      staff, teacher, official) THEN refuse. Exact key match only: "admin_1" is
      not reserved. The list lives in the Usernames module and nowhere else.
    violation: account.username.reserved (400, USERNAME_INVALID); on the lookups, status "reserved".
    source: [FR1.5]
    test_first: false

  - id: BR1.9
    statement: The database backstops the username's shape and its key.
    category: constraint
    applies_to: [Account]
    trigger: Any write to the account's username columns
    logic: >
      The account row is refused by the database IF exactly one of username and
      username_key is null, OR username_key differs from lower(username), OR
      username_key lacks the FR1 shape, OR username_key duplicates another
      row's. The equality check alone would pass when either side is null, so
      the both-or-neither condition is written out. These are backstops; the
      application refuses first with the keyed refusals above.
    violation: A database refusal on the uniqueness backstop is mapped to account.username.unavailable (BR10.2); any other backstop firing is a defect and surfaces as a server error.
    source: [FR1.3, FR1.1]
    test_first: false

  # ---------------------------------------------------------------- BR2
  - id: BR2.1
    statement: Sign-up requires a username, judged by BR1 before the draft is saved.
    category: validation
    applies_to: [SignupRequest, PendingSignup.username]
    trigger: POST /v1/accounts
    logic: >
      The request schema requires username (missing is 422; C1). After the
      existing signup ceilings are consumed, the candidate is judged by BR1 and
      then by availability (BR2.2). Only a valid, available candidate's text is
      stored in the draft, beside the exactly-one contact and the profile
      fields, and only then is the code issued.
    violation: A BR1 refusal is 400 with its key; nothing is saved and no code is sent.
    source: [FR2.1, FR2]
    test_first: false

  - id: BR2.2
    statement: The username is checked for availability when the draft is submitted, and the answer never depends on the contact.
    category: authorization
    applies_to: [POST /v1/accounts]
    trigger: A valid candidate in a sign-up request
    logic: >
      IF the key is on an account, OR under a live hold (whoever released it -
      the person is not signed in, so no hold is theirs), THEN refuse before
      the draft is saved and before any code is issued. The check reads only
      the username key: it runs identically whether or not the phone or email
      already has an account or a draft, so a username outcome reveals nothing
      about a contact (FR2.4). It is not counted against the availability
      ceilings: the signup ceilings, consumed first, are tighter.
    violation: account.username.unavailable (ConflictError, 409, code USERNAME_UNAVAILABLE). This adds a 409 to C1's POST /v1/accounts, which lists only 201 and 422.
    source: [FR2.2, FR2.4]
    test_first: true

  - id: BR2.3
    statement: A draft never reserves its username; whichever draft completes verification first takes it.
    category: policy
    applies_to: [PendingSignup.username]
    trigger: Two drafts name the same key; any availability check
    logic: >
      Availability (BR2.2, BR3.1, BR3.2, BR6.9) reads accounts and holds only,
      never drafts. Two live drafts may carry the same key. The first verify to
      create its account claims the key under the username advisory key
      (BR10.1); the second meets BR2.4.
    violation: None for the draft; the later verify is refused by BR2.4.
    source: [FR2.3]
    test_first: true

  - id: BR2.4
    statement: A username taken between draft and verification rolls the whole verify back, leaving the code usable and the draft untouched.
    category: constraint
    applies_to: [complete_signup, create_account_rows, the verify transaction]
    trigger: A correct, live code completes a bound draft whose username can no longer be claimed
    logic: >
      Inside the verify transaction, account creation takes the username
      advisory key with the contact keys (BR10.1) and judges the claim (BR6.9:
      not on another account, not under a live hold, not reserved, still of
      FR1 shape). IF the claim fails for any reason THEN raise a conflict and
      write nothing more. The route commits nothing on a 4xx, so the code's
      consumed mark, its successful attempt row, any draft update and every
      account row are discarded together [C-07]: the code is unspent, its
      attempt count unchanged, the draft as it was. No failed-verify ceiling is
      counted, because the code was right.
    violation: account.username.unavailable (409, USERNAME_UNAVAILABLE, retryable false). "Not retryable" means do not resend the same request; the remedy is a different request carrying a replacement username (BR2.5).
    source: [FR2.2]
    test_first: true

  - id: BR2.5
    statement: A verify may carry a replacement username, which replaces the draft's inside the same transaction; holding the draft's live, correct code is the authorization.
    category: authorization
    applies_to: [VerifyRequest.username, PendingSignup.username]
    trigger: POST /v1/auth/verify with username present
    logic: >
      The replacement is judged by BR1 first, before any counter or code is
      touched; a refusal there is 400 and consumes nothing. Then BR2.6 counts
      it. Then the code is verified as usual. IF the code is right AND no
      account holds the destination AND a live draft is bound to this code THEN
      the draft's username is set to the replacement's text inside the verify
      transaction and account creation proceeds with it (BR2.4 judges it like
      any claim). IF the destination already has an account, or no draft is
      bound, THEN the replacement is ignored and the verify answers exactly as
      it would without it. A wrong, expired or spent code is refused as today
      and counted as an ordinary verify failure.
    violation: BR1 refusals (400); BR2.6 (429); the existing code refusals; BR2.4 (409) if the replacement is unavailable too.
    source: [FR2.2]
    test_first: true

  - id: BR2.6
    statement: Each replacement attempt is counted against the replacement ceilings (Family C), committed before the verify reads the code, so no rollback can undo the count.
    category: policy
    applies_to: [POST /v1/auth/verify, RateLimitCounter un_rp_*, un_lk_global_hr]
    trigger: A verify request carrying a valid replacement username
    logic: >
      Amended by security-requirements.md NFR2.3 (Amendment 1). After the
      existing failed-verify ceiling check and the BR1 judgement, and BEFORE
      the code row is read or locked, consume one unit of un_rp_dest_hour
      (the verify's destination counter key: the phone, or "e:" and the
      email's hash; limit 5) and un_rp_ip_hour (caller's /64; limit 20)
      through the committing cascade, then count un_lk_global_hr
      (alert-only). At that point the session holds no other uncommitted
      work, so the cascade's commit commits only the counters. The verify
      transaction that follows can roll back without touching them. A
      correct code can therefore try at most 5 names an hour for its
      destination, fewer than the public lookup allows, and typing lookups
      never spend this budget. There is no per-draft cap and no
      username_replacements column (Q1); a verify with no replacement
      consumes nothing here. Residual, stated plainly (NFR2.3): the count
      precedes the code check, so a stranger can spend a destination's 5;
      the person can still submit a new draft with another username.
    violation: auth.lookup.too_many (ConflictError status 429, code TEMPORARILY_UNAVAILABLE, retryable false, no retry-after hint). Nothing else happens - the code is not read, no attempt is recorded, and the code still works without a replacement or after the window turns.
    source: [FR2.2, FR3.2]
    test_first: true

  - id: BR2.7
    statement: A draft saved before this change creates an account with no username.
    category: policy
    applies_to: [PendingSignup.username]
    trigger: A verify completes a draft whose username is null
    logic: >
      IF the bound draft has no username AND no replacement was sent THEN the
      account is created without one, no USERNAME_SET event is written, and
      username_required is true for it (BR5.1). A replacement sent with such a
      verify is used like any other (BR2.5).
    violation: None.
    source: [FR2.1, FR5.1]
    test_first: false

  - id: BR2.8
    statement: Creating an account with a username records USERNAME_SET by account id only.
    category: policy
    applies_to: [AuthAuditLog]
    trigger: Account creation with a username commits
    logic: Write USERNAME_SET with the new account id and the request's correlation id, in the same transaction as the account, after ACCOUNT_CREATED. The row carries no username, contact or code.
    violation: None (an audit write failure fails the transaction like any other write).
    source: [FR2.1, FR9.3]
    test_first: false

  - id: BR2.9
    statement: The sign-up response stays identical whether or not the contact already has an account.
    category: authorization
    applies_to: [POST /v1/accounts]
    trigger: Any sign-up that passes BR2.1 and BR2.2
    logic: >
      Every username decision (BR2.1, BR2.2) is taken before, and
      independently of, anything that reads the contact. After them the route
      does exactly what it does today for every contact - save the draft,
      issue the code, answer 201 with a fresh draft id - so a known and an
      unknown contact still receive the same body and the same work (the
      existing anti-enumeration guarantee of the sign-up route).
    violation: None.
    source: [FR2.4]
    test_first: true

  # ---------------------------------------------------------------- BR3
  - id: BR3.1
    statement: The public availability lookup answers only available, unavailable, invalid or reserved, and a held name is unavailable.
    category: authorization
    applies_to: [POST /v1/accounts/username-availability, UsernameAvailabilityResponse]
    trigger: An unauthenticated lookup (a POST with the candidate in a JSON body, NFR3.5)
    logic: >
      After BR3.3's ceilings: IF the candidate fails BR1.1-BR1.5 THEN
      "invalid" with that rule's message_key; ELSE IF BR1.8 THEN "reserved";
      ELSE IF the key is on any account OR under any live hold THEN
      "unavailable"; ELSE "available". The response has exactly two fields,
      status and message_key (message_key only for invalid). It never carries
      an account id, the stored casing, a hold expiry, or any other datum, and
      a held name is indistinguishable from a taken one (ADR-007 amends FR3.1).
    violation: None (an answer, not a refusal).
    source: [FR3.1, FR3]
    test_first: true

  - id: BR3.2
    statement: The authenticated availability check differs from the public one only for names the caller itself holds.
    category: authorization
    applies_to: [POST /v1/me/username-availability]
    trigger: A signed-in lookup, used in Settings (a POST with a body, NFR3.5)
    logic: >
      As BR3.1, except: IF the key is under a live hold whose releasing account
      is the caller THEN "available" (a rename would take it back, BR6.4 or
      BR6.6); IF the key is the caller's own current key THEN "available" (a
      rename to it is a case-only change or a no-op, BR6.7). It does not say
      whether the rename limit would allow the change: the rename's own answer
      does that.
    violation: None.
    source: [FR3.1, FR7.3]
    test_first: true

  - id: BR3.3
    statement: Both availability lookups are bounded by their own ceilings, counted before anything is read.
    category: policy
    applies_to: [POST /v1/accounts/username-availability, POST /v1/me/username-availability]
    trigger: Every lookup request that passes schema validation
    logic: >
      Amended by security-requirements.md NFR2.1 (Amendment 1): Family A of
      four. Consume un_lk_ip_hour (/64, limit 30) and un_lk_ip48_hour (/48,
      limit 100) through the committing cascade, narrowest first, refusing
      at the first breach with nothing consumed; then count un_lk_global_hr
      product-wide (SHIKKHOKPLUS_GLOBAL_HOURLY_USERNAME_LOOKUPS, default
      1000), alerting once on the request that fills it and never refusing.
      Counted for every candidate, valid or not, before the candidate is
      judged, so the refusal cannot depend on the answer. These counters are
      the availability lookups' own and never the already-added lookup's
      (lk_*). Claims (Family B: un_cl_acct_hour 10, un_cl_ip_hour 30,
      un_cl_ip48_hr 100, consumed by PUT /v1/me/username after the format
      check and before the password, NFR1.6) and sign-up replacements
      (Family C, BR2.6) have their own scopes; no family reads another's
      rows. All three count in un_lk_global_hr.
    violation: auth.lookup.too_many (429, TEMPORARILY_UNAVAILABLE, retryable false).
    source: [FR3.2]
    test_first: false

  - id: BR3.4
    statement: A lookup ceiling never blocks the form; the check at creation or rename is the authoritative one.
    category: policy
    applies_to: [the availability lookups, POST /v1/accounts, PUT /v1/me/username]
    trigger: A lookup is refused by BR3.3, or answers from a state that changes before submission
    logic: >
      Amended by security-requirements.md NFR2.2 and NFR2.3 (Amendment 2).
      No sign-up or rename reads the lookup counters (Family A). A person
      refused by the lookup can still submit; the submission is judged by
      BR2.2, BR2.4 or BR6.9 at that moment, and an "available" answer that
      has gone stale is refused there. A claim refusal (Family B) and a
      replacement refusal (Family C) do refuse that submission, by design:
      the claimer tries again in the next window; the person replacing a
      name can submit a new draft.
    violation: None.
    source: [FR3.2]
    test_first: false

  - id: BR3.5
    statement: The public lookup joins the public-route allowlist, and the two new authenticated routes join the lens-exempt set, each with its reason and the counts that check them.
    category: authorization
    applies_to: [PUBLIC_ROUTES, LENS_EXEMPT_AUTHENTICATED]
    trigger: The routes are registered
    logic: >
      Amended by security-requirements.md NFR3.5 (Amendment 5): both lookups
      are POST with a body. ("POST", "/v1/accounts/username-availability") is
      added to PUBLIC_ROUTES with a justification comment; the comment's
      stated count moves from fourteen to fifteen, and every assertion of
      that count moves with it in the same change. ("POST",
      "/v1/me/username-availability") and ("PUT", "/v1/me/username") are
      added to LENS_EXEMPT_AUTHENTICATED, each on GET /v1/me's reasoning:
      they act on the authenticated account alone and read nothing another
      account owns beyond a yes or no.
    violation: The route-enumeration gate fails CI for an unlisted route; a count assertion fails CI for a stale count.
    source: [FR3.3]
    test_first: true

  # ---------------------------------------------------------------- BR4
  - id: BR4.1
    statement: A password sign-in names exactly one of login, phone and email.
    category: validation
    applies_to: [PasswordSignInRequest]
    trigger: POST /v1/auth/password
    logic: >
      IF none, or more than one, of login, phone and email is present THEN the
      schema refuses the request. phone and email keep their existing meaning
      and validation unchanged (FR4.6); login is what the person typed, at most
      254 characters.
    violation: 422 from the schema, before any ceiling or lookup.
    source: [FR4.1, FR4.6]
    test_first: false

  - id: BR4.2
    statement: The server classifies the login field as email, phone or username, in that order.
    category: calculation
    applies_to: [LoginSubject]
    trigger: A sign-in carrying login
    logic: >
      Trim it. IF it contains "@" THEN it is an email, canonicalised as the
      email field is (an address that fails that rule is refused as
      email.invalid, exactly as the email field refuses it today). ELSE IF it
      parses as a Bangladeshi mobile number in any accepted spelling THEN it is
      that phone, canonicalised. ELSE it is a username, and its value is the
      lowercase form. A username subject is NOT judged against FR1: a malformed
      one is simply a key no account has, and is refused like any unknown name
      (BR4.4). The three kinds are disjoint because a username starts with a
      letter and contains no "@" (ADR-003). A mistyped number falls through to
      a username lookup and gets the uniform refusal.
    violation: email.invalid (400) for a malformed address only; otherwise none.
    source: [FR4.1]
    test_first: false

  - id: BR4.3
    statement: Phone and email sign-in keep working, permanently, for every account.
    category: policy
    applies_to: [POST /v1/auth/password]
    trigger: A sign-in by phone or email, through the existing fields or through login
    logic: >
      A phone or email subject follows today's path unchanged: the account is
      found by that contact, counted under pw_fail_id_hour on its existing
      counter key, refused by the existing uniform refusal. Whether the account
      has a username makes no difference.
    violation: None.
    source: [FR4.2, FR4.6]
    test_first: true

  - id: BR4.4
    statement: An unknown username, an account with no password and a wrong password are refused identically.
    category: authorization
    applies_to: [POST /v1/auth/password]
    trigger: A username sign-in that does not match
    logic: >
      Find the account whose username_key equals the subject. IF none, OR it
      has no password, THEN perform the same no-op password work as today
      (one scrypt evaluation); ELSE verify the password. Every one of the three
      failures then counts the same failure scopes (BR4.5), writes
      PASSWORD_SIGN_IN_FAILED (account id null when none was found, as today),
      commits, and refuses with one response. The response body, status, and
      the statements executed are the same in all three cases, and the same as
      a phone or email failure.
    violation: auth.password.wrong (ValidationError, 400, code PASSWORD_NOT_VALID).
    source: [FR4.3, FR4]
    test_first: true

  - id: BR4.5
    statement: Username sign-in failures are counted per username and network, per network, and per username across networks (Family D), on keyed values that cannot collide with any other counter.
    category: policy
    applies_to: [RateLimitCounter un_fail_net_hour, un_fail_ip_hour, un_fail_ip48_hr, un_fail_hour]
    trigger: Every username sign-in, before the lookup and after a failure
    logic: >
      Amended by security-requirements.md NFR2.4 and NFR3.3 (Amendments 3 and
      6), with the code-generation plan's three-failure rule. Before the
      account is looked up, peek (read, never increment), in this order,
      refusing at the first match: un_fail_net_hour >= 10; un_fail_ip_hour
      (any username from this /64) >= 20; un_fail_ip48_hr (this /48) >= 60;
      un_fail_hour >= 20 AND this network's un_fail_net_hour >= 3. On a
      failure (BR4.4), increment all four and the existing alert-only
      pwf_global_hour, each committed. Values are keyed: un_fail_hour is
      'u:' + the first 62 hex of HMAC-SHA256 under SHIKKHOKPLUS_OTP_HMAC_KEY
      over "username-counter:v1:" + key; un_fail_net_hour the same over
      "username-counter:v1:" + key + "|" + /64. A username subject never
      reads or writes pw_fail_id_hour, vf_ip_hour, vf_ip48_hour or
      vf_global_hour, so a username key and a phone or email key never share
      a counter and username failures never refuse a code verify; a 'u:'
      value cannot equal a phone, an 'e:' email value or an 'acct:' value.
      Counted identically for unknown and known usernames.
    violation: BR4.6.
    source: [FR4.4, FR4]
    test_first: true

  - id: BR4.6
    statement: A full username failure ceiling refuses in sign-in's words and checks nothing.
    category: policy
    applies_to: [CeilingBreach]
    trigger: BR4.5's peek finds a full scope
    logic: >
      Refuse before any lookup or password work, write
      PASSWORD_CEILING_BREACHED with no account id, commit. All four Family D
      scopes answer the same key as pw_fail_id_hour; the ceiling refusal maps
      them by a literal key, so a new scope cannot fall through to the OTP
      refusal text (NFR2.6).
    violation: auth.password.too_many_attempts (ConflictError, 409, code TEMPORARILY_UNAVAILABLE).
    source: [FR4.4]
    test_first: true

  - id: BR4.7
    statement: A stranger cannot lock the owner out of username sign-in from another network, and never out of phone, email or code sign-in.
    category: authorization
    applies_to: [POST /v1/auth/password]
    trigger: An attacker fills un_fail_net_hour or un_fail_hour for a known username
    logic: >
      Amended by security-requirements.md NFR2.4 (Amendment 3) and the
      code-generation plan's three-failure rule. A further attempt from a
      network N that has failed the name 10 times is refused (BR4.6). A
      stranger who fills un_fail_hour (20, all networks) from their own
      networks cannot refuse the owner's username sign-in from any network
      on which that name has failed fewer than 3 times this window, so an
      owner who mistyped once or twice on their own network still signs in.
      A stranger sharing the owner's /64 (on IPv4 the /24) can refuse
      username sign-in from that network for the rest of the window, by 10
      failures on that name or 20 on any names; that residual is stated, not
      removed. No username counter ever refuses a sign-in by the same
      account's phone or email (BR4.3) or a code verify, which do not read
      them.
    violation: None.
    source: [FR4.4]
    test_first: true

  - id: BR4.8
    statement: A successful username sign-in continues exactly as a phone or email sign-in does.
    category: policy
    applies_to: [POST /v1/auth/password]
    trigger: The password matches
    logic: >
      Transparent rehash, PASSWORD_SIGN_IN_SUCCEEDED, then IF the account has a
      confirmed authenticator THEN the existing MFA challenge ELSE the token
      pair - the same response shapes as today. Password setup, the second step
      and refresh are not touched. The success response carries no username
      and no username_required; the client reads username_required from GET
      /v1/me (C1 narrows FR5.1 to that route).
    violation: None.
    source: [FR4.5]
    test_first: false

  # ---------------------------------------------------------------- BR5
  - id: BR5.1
    statement: username_required is computed by the server and is true exactly while the account has no username.
    category: calculation
    applies_to: [MeResponse.username_required]
    trigger: Every response built from MeResponse (GET /v1/me, PATCH /v1/me, the contact routes that return MeResponse)
    logic: username_required = (username IS NULL). Never stored, never cached across requests, never read from the client. MeResponse also carries username (the stored casing, or null).
    violation: None.
    source: [FR5.1, FR5]
    test_first: true

  - id: BR5.2
    statement: The server refuses no other request because the account has no username.
    category: policy
    applies_to: [every route]
    trigger: An account with no username calls any route
    logic: No route reads username_required or username as a precondition. The flag is the decision; the clients enforce the choose-username screen (A5, ADR-008).
    violation: None.
    source: [FR5.3]
    test_first: false

  - id: BR5.3
    statement: Choosing the first username needs no password, is exempt from the rename limit, places no hold and does not start the limit.
    category: authorization
    applies_to: [PUT /v1/me/username]
    trigger: The signed-in account has no username
    logic: >
      Judge by BR1 and BR6.9. IF valid and claimable THEN set username and
      username_key, leave username_changed_at and username_reclaimed_at null,
      place no hold, write USERNAME_SET, and answer the stored username with
      next_change_at null. Any password sent is ignored. A sign-up username is
      a first choice too: the first ordinary rename after it is allowed at
      once (FR7.2's limit counts renames, not first choices).
    violation: BR1 refusals (400); account.username.unavailable (409).
    source: [FR5.4, FR5]
    test_first: true

  # ---------------------------------------------------------------- BR6
  - id: BR6.1
    statement: A rename, a reclaim and a case-only change need the account's password, confirmed before anything is locked or written.
    category: authorization
    applies_to: [PUT /v1/me/username, UsernameChangeRequest.password]
    trigger: The signed-in account already has a username
    logic: >
      Amended by security-requirements.md NFR1.6 (Amendment 4): the claim
      cascade (Family B) is consumed first, after the BR1 format check and
      before this password check. Then: IF the account has no password THEN
      refuse with password_required (Q4; the client reads has_password from
      GET /v1/me and routes to setting one). ELSE IF the request carries no
      password THEN refuse with password_required. ELSE check it under the
      existing current-password ceilings (pw_fail_id_hour on 'acct:'+id,
      plus the shared per-prefix scopes): a full ceiling refuses, a wrong
      password counts a failure, commits it, and refuses. Only a confirmed
      password proceeds to the unit of work, which takes the account key,
      re-reads the row, then takes the username keys (NFR4.2), and judges
      the window BEFORE availability (NFR1.6).
    violation: account.username.password_required (ValidationError, 400, code USERNAME_PASSWORD_REQUIRED, new key); auth.password.current_wrong (400, PASSWORD_NOT_VALID); auth.password.too_many_attempts (409).
    source: [FR7.1]
    test_first: true

  - id: BR6.2
    statement: An ordinary rename is allowed at most once every 30 days.
    category: policy
    applies_to: [Account.username_changed_at]
    trigger: A rename that is not a first choice, a case-only change, or an exempt reclaim
    logic: >
      The window is open IF username_changed_at is null OR now is at or after
      username_changed_at + 30 days (exact duration, UTC instants). IF open
      THEN proceed (BR6.3). ELSE refuse, carrying next_change_at =
      username_changed_at + 30 days in the error details as an ISO 8601 UTC
      string with seconds and a "Z" suffix (details are string-valued). So a
      rename on day 0 refuses a rename on day 20 and allows one on day 30.
    violation: account.username.change_too_soon (ConflictError, 409, code USERNAME_CHANGE_TOO_SOON, details.next_change_at).
    source: [FR7.2]
    test_first: true

  - id: BR6.3
    statement: An ordinary rename moves the name, holds the old one for this account, and starts a new window.
    category: constraint
    applies_to: [Account, UsernameHold]
    trigger: BR6.2 allows the rename and BR6.9 allows the claim
    logic: >
      In one transaction: set username and username_key to the new candidate;
      set username_changed_at = now; place (upsert) a hold on the old key with
      held_until = now + 30 days and releasing_account_id = this account;
      delete any hold row on the new key's digest (it is either expired or this
      account's own); write USERNAME_CHANGED. Answer the new username and
      next_change_at = now + 30 days. username_reclaimed_at is left as it is:
      being earlier than the new username_changed_at, it already reads as
      unused for the new window.
    violation: None beyond BR6.2 and BR6.9.
    source: [FR7.1, FR7.2, FR7.3]
    test_first: true

  - id: BR6.4
    statement: The first reclaim inside a rename window is exempt from the limit and does not move the window.
    category: authorization
    applies_to: [Account.username_reclaimed_at, UsernameHold]
    trigger: A rename whose target key is under a live hold releasing to this account, while the window is closed
    logic: >
      IF the window is closed (BR6.2) AND the target is held live for this
      account AND (username_reclaimed_at is null OR username_reclaimed_at <
      username_changed_at) THEN it is an exempt reclaim: in one transaction set
      username and username_key to the target; delete the target's hold row;
      place (upsert) a hold on the key being given up, for this account, 30
      days from now; set username_reclaimed_at = now; leave
      username_changed_at unchanged; write USERNAME_CHANGED. Answer the
      username and next_change_at = username_changed_at + 30 days (unchanged,
      never null after a reclaim).
    violation: None (see BR6.5 for the refused case).
    source: [FR7.3, FR7.2]
    test_first: true

  - id: BR6.5
    statement: A second reclaim inside the same window is an ordinary rename and is refused by the limit.
    category: authorization
    applies_to: [PUT /v1/me/username]
    trigger: A reclaim while the window is closed and username_reclaimed_at is at or after username_changed_at
    logic: >
      The exemption is spent for this window, so the request is judged as an
      ordinary rename by BR6.2 and refused. The two names therefore cannot
      alternate: rename A to B on day 0, reclaim A on day 3, and a move back to
      B (held for this account since day 3) is refused until day 30. (R-10)
    violation: account.username.change_too_soon (409) with next_change_at = username_changed_at + 30 days.
    source: [FR7.2, FR7.3]
    test_first: true

  - id: BR6.6
    statement: Taking back an own-held name while the window is open is an ordinary rename and does not spend the reclaim exemption.
    category: policy
    applies_to: [PUT /v1/me/username]
    trigger: A rename to a name held live for this account, while the window is open
    logic: Judged and applied exactly as BR6.3 (the target's hold row is deleted as part of it); username_reclaimed_at is not set.
    violation: None.
    source: [FR7.3]
    test_first: true

  - id: BR6.7
    statement: A change of letter case only is not a rename.
    category: policy
    applies_to: [PUT /v1/me/username]
    trigger: The new candidate's key equals the account's current key
    logic: >
      After BR6.1's password confirmation: IF the text equals the stored text
      exactly THEN answer success with no write and no audit row (a no-op). ELSE
      update username only, write USERNAME_CHANGED, place no hold, and move
      neither username_changed_at nor username_reclaimed_at; it is allowed at
      any time (Q3). The answer's next_change_at is whatever BR6.2 would report
      (null while the window is open).
    violation: None beyond BR1 and BR6.1.
    source: [FR7.1, FR1.3]
    test_first: false

  - id: BR6.8
    statement: Changing the username signs nobody out.
    category: policy
    applies_to: [PUT /v1/me/username]
    trigger: Any successful first choice, rename, reclaim or case-only change
    logic: No token family is revoked and no session is ended. Other devices read the new username from GET /v1/me on their next refresh.
    violation: None.
    source: [FR7.5]
    test_first: false

  - id: BR6.9
    statement: One claim rule decides whether an account may take a key, at sign-up completion, first choice and rename.
    category: authorization
    applies_to: [AccountDirectory claim]
    trigger: Any write that gives an account a username key
    logic: >
      Under the key's advisory lock (BR10.1), the claim is allowed only IF the
      candidate passes BR1 (shape and reserved list), AND no OTHER account has
      the key, AND there is no live hold on the key's digest, or the live hold's
      releasing account is the claiming account. A hold whose releasing account
      is null (deletion, or a renamed-away account since erased) blocks
      everyone. An expired hold blocks nobody, purged or not, and a successful
      claim deletes any hold row on that digest.
    violation: account.username.unavailable (409, USERNAME_UNAVAILABLE) - one key for taken and held alike.
    source: [FR7.3, FR1.3, FR2.2]
    test_first: true

  # ---------------------------------------------------------------- BR7
  - id: BR7.1
    statement: A hold stores a keyed digest of the key and never the username text.
    category: constraint
    applies_to: [UsernameHold.key_digest]
    trigger: A hold is placed, checked or cleared
    logic: >
      digest = lowercase hex HMAC-SHA256, keyed by SHIKKHOKPLUS_OTP_HMAC_KEY
      (read from the environment, never the database), over the bytes of
      "username-hold:v1:" followed by the key. Every hold read and write goes
      through this one function. No hold row, log line or error carries the
      key or the text.
    violation: None (a missing key fails at start-up, as the OTP path already does).
    source: [FR7.4, FR10.2]
    test_first: true

  - id: BR7.2
    statement: A hold lasts 30 days from the latest release and is live until that instant, exclusive.
    category: calculation
    applies_to: [UsernameHold.held_until]
    trigger: A release; any hold check
    logic: held_until = release instant + 30 days. Live IF now < held_until. At held_until and after, the name is free (FR7.3 acceptance - deleted today, available on day 31).
    violation: None.
    source: [FR7.3]
    test_first: true

  - id: BR7.3
    statement: One row per digest; a later release of the same name replaces the earlier one.
    category: constraint
    applies_to: [UsernameHold]
    trigger: A release of a key whose digest already has a row
    logic: Upsert on key_digest - held_until and releasing_account_id take the new release's values; created_at keeps the first. Live or expired, the latest release wins.
    violation: None.
    source: [FR7.3]
    test_first: false

  - id: BR7.4
    statement: A rename hold names the releasing account; a deletion hold names none; erasing an account clears its name from every hold it left.
    category: constraint
    applies_to: [UsernameHold.releasing_account_id]
    trigger: A hold is placed by a rename or reclaim, or by account deletion; an account is erased
    logic: >
      Rename and reclaim set releasing_account_id to the account. Deletion
      sets it null. When an account row is deleted, the database sets the
      column to null on every hold that named it, so those holds go on blocking
      everyone until they expire and nobody can reclaim them.
    violation: None.
    source: [FR7.3, FR7.4]
    test_first: true

  - id: BR7.5
    statement: Deleting an account starts a 30-day digest-only hold on its username, inside the deletion's one transaction.
    category: policy
    applies_to: [delete_account, UsernameHold]
    trigger: Either deletion path deletes an account that has a username
    logic: >
      After the account key and the re-read under it, take the username key
      with the contact keys (BR10.1). Before the account row is deleted, upsert
      a hold on the key's digest with held_until = now + 30 days and
      releasing_account_id null. It commits with the rest of the deletion, or
      not at all. An account with no username leaves no hold.
    violation: None.
    source: [FR10.2, FR7.4, FR10]
    test_first: true

  - id: BR7.6
    statement: Expired holds are purged by the existing retention purge, on their own expiry.
    category: policy
    applies_to: [UsernameHold, the retention purge]
    trigger: The scheduled daily retention purge
    logic: >
      username_hold carries a new finite retention class whose age column is
      held_until and whose window is zero: rows whose held_until is strictly
      earlier than the purge's moment are deleted, in the purge's chunks, and
      the job's heartbeat is stamped as today. No new job is added. Purge is an
      optimisation: availability already ignores expired rows (BR6.9).
    violation: None (a failed purge leaves rows that read as free; the heartbeat alert covers a dead job).
    source: [FR10.2, FR7.3]
    test_first: false

  - id: BR7.7
    statement: The deletion disposition, the generated privacy policy and the key's rotation note all name the hold.
    category: policy
    applies_to: [DISPOSITIONS, the privacy policy, deploy/README.md]
    trigger: The hold table is added
    logic: >
      username_hold gets a disposition entry (retained with basis, until its
      expiry) whose basis states what it stores (a keyed digest of the
      lowercase name, an expiry, and while the account exists the releasing
      account), why (so nobody can take a just-released name and impersonate
      its owner for 30 days), and that it is purged at expiry. The account
      entry's basis adds that the username is removed with the account. The
      policy is regenerated from them. The operational note for
      SHIKKHOKPLUS_OTP_HMAC_KEY says that rotating it releases every live
      username hold early.
    violation: The governance and policy-generation gates fail CI for an undeclared table or a stale policy.
    source: [FR10.2]
    test_first: false

  # ---------------------------------------------------------------- BR8
  - id: BR8.1
    statement: The username is served only to its owner, on two named schemas, on routes that act only on the owner.
    category: authorization
    applies_to: [MeResponse.username, UsernameChangeResponse.username]
    trigger: Any response
    logic: >
      Only MeResponse.username and UsernameChangeResponse.username carry it,
      and only on routes in LENS_EXEMPT_AUTHENTICATED (the /v1/me family),
      read from the authenticated account id. No teacher, guardian, student,
      membership, class-teacher, examiner, centre or platform-administrator
      response carries any account's username or username_key, and no response
      anywhere carries username_key. The sign-in success response and the
      availability responses carry neither.
    violation: BR8.2's gate fails CI.
    source: [FR9.1, FR9]
    test_first: true

  - id: BR8.2
    statement: The privacy gates enforce BR8.1 mechanically, on every route, not only teacher-facing ones.
    category: authorization
    applies_to: [OWNER_PRIVATE_FIELDS, OWN_ACCOUNT_FIELDS, a new account-private check, FORBIDDEN_TOKENS]
    trigger: CI
    logic: >
      username and username_key join OWNER_PRIVATE_FIELDS, which the existing
      gate walks on teacher-facing routes only. Because that leaves guardian,
      student, membership and other lenses unchecked, a second walk - shaped
      like the staff-field check, over EVERY route's response schema - fails on
      any field named username or username_key unless the (schema, field) pair
      is in OWN_ACCOUNT_FIELDS AND the route is in LENS_EXEMPT_AUTHENTICATED.
      OWN_ACCOUNT_FIELDS gains ("MeResponse", "username") and
      ("UsernameChangeResponse", "username") only. "username" joins the admin
      contract's FORBIDDEN_TOKENS, matched as a substring like the others.
    violation: CI fails, naming the route, schema and field.
    source: [FR9.2, FR9.1]
    test_first: true

  - id: BR8.3
    statement: A membership test fails if an account username column exists outside the gate's sets.
    category: authorization
    applies_to: [Account columns, the gate's sets]
    trigger: CI
    logic: >
      The test names account.username and account.username_key, and also
      selects every account column whose name contains "username" (except the
      two timestamps, which are named as exempt), and fails unless each is in
      OWNER_PRIVATE_FIELDS and in the account-private walk's field set, and
      "username" is in FORBIDDEN_TOKENS. A column added under an unrelated name
      would escape the pattern, which is why the two are also named (ADR-010).
    violation: CI fails.
    source: [FR9.2]
    test_first: true

  - id: BR8.4
    statement: No log line, audit row, notification, message or error carries a username.
    category: policy
    applies_to: [logging, AuthAuditLog, error details, RateLimitCounter, notifications, SMS, email]
    trigger: Any username path
    logic: >
      Audit rows carry the account id only (USERNAME_SET, USERNAME_CHANGED,
      and the existing sign-in events). Error envelopes carry a message_key and,
      for change_too_soon, a timestamp - never the candidate, the stored name or
      the key. Log lines on these paths carry the correlation id and an outcome,
      never the subject; a username sign-in logs no more than a phone sign-in.
      Counter values are hashes ('u:'...). No notification, SMS or email is sent
      by any username path.
    violation: A test drives each path and asserts the absence; review is the backstop.
    source: [FR9.3]
    test_first: true

  # ---------------------------------------------------------------- BR9
  - id: BR9.1
    statement: Forgotten-password recovery and both deletion paths still take a phone or an email only.
    category: authorization
    applies_to: [POST /v1/auth/otp, POST /v1/auth/verify, GET and POST /account-deletion, DELETE /v1/me]
    trigger: A recovery or deletion request
    logic: >
      These request schemas keep the exactly-one phone-or-email fields and
      gain no login field. A username typed into the email field is refused as
      email.invalid and into the phone field as the phone refusal, exactly as
      any non-contact is today. The code still goes only to a verified contact.
    violation: The existing format refusals.
    source: [FR10.1, FR10]
    test_first: false

  # ---------------------------------------------------------------- BR10
  - id: BR10.1
    statement: Every claim and release takes the username advisory keys, last in the one lock order, in a single call with the path's other keys.
    category: constraint
    applies_to: [app/db/advisory.py, create_account_rows, rename, delete_account]
    trigger: Any write that claims or releases a username key
    logic: >
      A new namespace "username" is appended to the lock order (student,
      account, contact, username), with a helper naming "username:<key>".
      Account creation takes its contact keys and the username key in one call.
      First choice and rename take the account key, re-read the row FOR
      UPDATE, then take the new key and the old key (from that locked
      re-read) in a second call (reliability-requirements.md NFR4.2, R-06).
      Deletion takes the account key, then (after its re-read) the contact keys
      and the username key in one call. Because every path takes username keys
      last and the helper sorts within a call, no two paths can wait on each
      other in a cycle; the keys are what make the account check and the hold
      check one decision, so a release committing between them cannot let a
      held name through.
    violation: None (an ordering defect would show as a deadlock; see BR10.3).
    source: [FR2.2, FR7.3]
    test_first: true

  - id: BR10.2
    statement: A uniqueness violation on the key is reported as the name being unavailable, never as a server error.
    category: constraint
    applies_to: [create_account_rows, rename]
    trigger: The database refuses a duplicate username_key
    logic: Classify the integrity error by its constraint name; the username-key uniqueness constraint maps to account.username.unavailable (409). Any other integrity error keeps its existing handling.
    violation: account.username.unavailable (409).
    source: [FR1.3, FR2.2]
    test_first: false

  - id: BR10.3
    statement: Rename runs as one re-runnable unit of work; the verify transaction does not.
    category: constraint
    applies_to: [PUT /v1/me/username, POST /v1/auth/verify]
    trigger: A serialization failure or deadlock
    logic: >
      The rename's unit (locks, re-read, claim, writes, commit) runs under the
      existing bounded retry, because it sends nothing before its commit. The
      password confirmation commits its own failures and runs before the unit,
      outside the retry. The verify path is not wrapped: it already commits
      code refusals part-way, so it cannot be re-run from its first statement;
      its keys are advisory and ordered, so a cycle is not expected there.
    violation: After the retries, error.temporarily_unavailable (TransientError, 503, retryable true).
    source: []
    test_first: false
```

## Rules summary

| ID | Rule (short) | Category | Test-first |
|---|---|---|---|
| BR1.1 | Trim; inner whitespace invalid | validation | no |
| BR1.2 | Latin letters, digits, `_`, `.` only | validation | no |
| BR1.3 | 3 to 20 characters | validation | no |
| BR1.4 | Starts with a letter | validation | no |
| BR1.5 | No trailing dot, no `..` | validation | no |
| BR1.6 | One refusal key, fixed precedence, no echo | validation | no |
| BR1.7 | Lowercase key for uniqueness, sign-in, holds | constraint | yes |
| BR1.8 | Reserved list by exact key, one place | policy | no |
| BR1.9 | Database backstop incl. both-or-neither | constraint | no |
| BR2.1 | Sign-up requires a username | validation | no |
| BR2.2 | Draft-time availability, independent of contact | authorization | yes |
| BR2.3 | Drafts never reserve | policy | yes |
| BR2.4 | Taken at verify rolls everything back | constraint | yes |
| BR2.5 | Replacement at verify, authorised by the code | authorization | yes |
| BR2.6 | Replacements counted on committed Family C ceilings (R-09, NFR2.3) | policy | yes |
| BR2.7 | Pre-deploy draft creates no username | policy | no |
| BR2.8 | USERNAME_SET by account id | policy | no |
| BR2.9 | Sign-up response stays contact-independent | authorization | yes |
| BR3.1 | Public lookup: four answers, held reads unavailable | authorization | yes |
| BR3.2 | Authenticated lookup: own holds read available | authorization | yes |
| BR3.3 | Family A lookup ceilings before reading | policy | no |
| BR3.4 | A lookup ceiling never blocks the form; claim and replacement ceilings refuse | policy | no |
| BR3.5 | Allowlists and counts updated | authorization | yes |
| BR4.1 | Exactly one of login, phone, email | validation | no |
| BR4.2 | Classify email, phone, username | calculation | no |
| BR4.3 | Phone and email sign-in permanent | policy | yes |
| BR4.4 | Uniform refusal | authorization | yes |
| BR4.5 | Family D: per name and /64, per /64, per /48, per name across networks; keyed values | policy | yes |
| BR4.6 | Ceiling refusal in sign-in's words | policy | yes |
| BR4.7 | No cross-network lockout of a network with fewer than 3 failures | authorization | yes |
| BR4.8 | Success continues as today | policy | no |
| BR5.1 | `username_required` = no username | calculation | yes |
| BR5.2 | No route refused for lacking one | policy | no |
| BR5.3 | First choice: no password, no limit, no hold | authorization | yes |
| BR6.1 | Password confirmed for rename (Q4) | authorization | yes |
| BR6.2 | Rename limit 30 days, `next_change_at` ISO | policy | yes |
| BR6.3 | Ordinary rename effects | constraint | yes |
| BR6.4 | First reclaim in a window exempt (R-10) | authorization | yes |
| BR6.5 | Second reclaim refused (R-10) | authorization | yes |
| BR6.6 | Own-held while window open is ordinary | policy | yes |
| BR6.7 | Case-only change is not a rename (Q3) | policy | no |
| BR6.8 | Nobody signed out | policy | no |
| BR6.9 | The one claim rule | authorization | yes |
| BR7.1 | Keyed digest, never text | constraint | yes |
| BR7.2 | 30 days, live until exclusive | calculation | yes |
| BR7.3 | Upsert, latest release wins | constraint | no |
| BR7.4 | Releasing account, set-null on erasure | constraint | yes |
| BR7.5 | Deletion hold in the deletion transaction | policy | yes |
| BR7.6 | Purge by the existing retention job | policy | no |
| BR7.7 | Disposition, policy, rotation note | policy | no |
| BR8.1 | Owner-only, two schemas, `/v1/me` routes | authorization | yes |
| BR8.2 | Every-route account-private gate | authorization | yes |
| BR8.3 | Column membership test | authorization | yes |
| BR8.4 | No username in logs, audit, errors, messages | policy | yes |
| BR9.1 | Recovery and deletion stay phone-or-email | authorization | no |
| BR10.1 | Username advisory keys, last in order | constraint | yes |
| BR10.2 | Duplicate key maps to unavailable | constraint | no |
| BR10.3 | Rename re-runnable; verify not | constraint | no |
