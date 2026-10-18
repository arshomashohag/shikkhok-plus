# Business Rules — `identity-and-access` (U3)

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **the walking skeleton**

## Sources

- [stage] `functional-design-questions.md` — Q1 through Q7
- [upstream] `inception/user-stories/stories.md` — US1.1, US1.2, US1.5,
  US1.8, US1.9 and their acceptance criteria
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — the
  six stories this Unit owns: US1.1, US1.2, US1.5, US1.8, US1.9
- [upstream] `inception/contract-design/contract-summary.md` — §B.3 the auth
  endpoints, §B.4 the lens contract, §C the SMS gateway and §C.4 BulkSMSBD
- [upstream] `inception/domain-design/decisions.md` — ADR-001, D-2, D-33
- [upstream] `construction/api-contract/functional-design/rules.md` — BR4.4,
  the obligation this Unit inherits
- [team] `## Walking Skeleton`, `## Testing Posture`, `## Code Style`
- [project] `## Forbidden` / `## Mandated`

---

## Part A — Source of truth

```yaml
rules:

  # ---- BR1.x - The lens is computed, never stored ----

  - id: BR1.1
    statement: >
      The lens is computed from owned batches and enrollments on every
      request. No role is read from the account record, and none is cached
      across requests.
    category: authorization
    applies_to: Every authenticated request
    trigger: Any request carrying an access token
    logic: >
      IF a request is authenticated
      THEN query Owner and Enrollment for this account AT THAT MOMENT
      AND derive the available lenses from what those queries return
      ELSE no lens is available.
    violation_behaviour: >
      A role column on Account, a module-level dict, an lru_cache, or a
      cache key outliving the request. None of these fails a happy-path
      test, which is why the rule is mechanical rather than reviewed.
    rationale: >
      **A cached lens is indistinguishable from a computed one on every
      happy path.** Only a mid-session ownership change tells them apart,
      which is exactly what BR1.2 and BR1.3 describe.

      This is the single most-mandated rule in the project, and the pressure
      against it is real: lens resolution runs on every request, making it
      the hottest query in the system on a 2 GB instance. The argument for
      caching it will arrive with plausible numbers attached. The rule is
      a mechanism so it survives that conversation.
    source: [AC1.9.1, FR1.3, TC-11, D-2, project.md Mandated]

  - id: BR1.2
    statement: >
      An account that owned no batches and then creates one has the teacher
      lens available on its NEXT request, with no re-authentication.
    category: authorization
    applies_to: Lens resolution
    trigger: Ownership gained mid-session
    logic: >
      IF an Owner row now exists for this account
      THEN the next request offers the teacher lens
      ELSE it does not.
    violation_behaviour: >
      A cache keyed on the account returns the pre-creation answer. This is
      one of exactly two tests that catch it.
    rationale: >
      Named as its own rule rather than left as a test, because its only
      purpose is to fail against the caching implementation. A reader who
      does not know that will delete it as redundant with BR1.1.
    source: [AC1.9.2]

  - id: BR1.3
    statement: >
      An account whose last enrollment is removed no longer has the student
      lens on its NEXT request.
    category: authorization
    applies_to: Lens resolution
    trigger: Ownership lost mid-session
    logic: >
      IF no Enrollment row remains for this account
      THEN the student lens is no longer offered.
    violation_behaviour: >
      A cache serves a lens the data no longer supports — which is an
      authorization decision made on stale state.
    rationale: >
      The mirror of BR1.2, and the more dangerous direction: BR1.2 withholds
      access someone should have, this one GRANTS access someone should not.
    source: [AC1.9.3]

  - id: BR1.4
    statement: >
      Memoizing the resolved lens within one request is permitted. Caching
      it across requests is not. The memo lives on the request object.
    category: constraint
    applies_to: Lens resolution
    trigger: A second lens lookup inside one request
    logic: >
      IF the lens was already resolved for THIS request
      THEN reuse it
      ELSE query again.
    violation_behaviour: >
      Any storage outliving the request. A test asserts two requests from
      one account each hit the database.
    rationale: >
      The distinction needs a mechanism rather than a convention, because
      "request-scoped" is a property of WHERE the value lives. On
      request.state it is garbage-collected with the request; in a module
      dict it is not, and the difference is invisible at the call site.
    source: [AC1.9.4, team.md: request-scoped memoization]

  # ---- BR2.x - The seven OTP abuse controls ----

  - id: BR2.1
    statement: >
      Rate-limit counters are datastore-backed, never per-process.
    category: constraint
    applies_to: All three counter scopes
    trigger: Any OTP issue request
    logic: >
      IF a limit is checked
      THEN it reads and increments a row under a unique constraint on
      (scope_kind, scope_value, window_start)
      ELSE the count is per-worker and therefore wrong.
    violation_behaviour: >
      A per-process dictionary. The test exercises the limit through two
      independent sessions, which a shared-nothing counter cannot survive.
    rationale: >
      **This is a correctness requirement, not hardening.** The obvious
      implementation passes every naive test and silently stops working the
      moment there are two workers — which Phase 1 has, because one
      Lightsail host runs several Uvicorn workers. It presents as "the limit
      works in testing", which is the worst way for a budget control to
      fail.
    source: [AC1.8.3, NFR12, team.md Walking Skeleton]

  - id: BR2.2
    statement: >
      Per-number: a 4th code within an hour is refused; a 6th within a day
      is refused. Per-IP-prefix: an 11th within an hour is refused.
    category: constraint
    applies_to: The OTP issue path
    trigger: An issue request
    logic: >
      IF the per-number hourly count >= 3
      OR the per-number daily count >= 5
      OR the per-IP-prefix hourly count >= 10
      THEN refuse before calling the gateway.
    violation_behaviour: >
      Checking after the call spends the money the limit exists to protect.
    rationale: >
      The ceiling is checked BEFORE the gateway call, never after. A breach
      is a ConflictError (409), never a TransientError: retrying into a cost
      ceiling is exactly wrong, and 429 carries a retry-after convention
      that invites it.
    source: [AC1.8.1, AC1.8.2, NFR12, D-33]

  - id: BR2.3
    statement: >
      A code expires 5 minutes after issue, verifies at most once, and dies
      after 5 failed attempts.
    category: constraint
    applies_to: The OTP verify path
    trigger: A verify request
    logic: >
      IF now > expires_at OR consumed_at IS NOT NULL OR attempts >= 5
      THEN refuse
      ELSE compare the hash, and on success set consumed_at IN THE SAME
      TRANSACTION as the check that read it.
    violation_behaviour: >
      Setting consumed_at in a later transaction lets a concurrent second
      verify slip between the check and the write.
    rationale: >
      Three controls in one rule because they share a transaction boundary.
      Each needs an ADVERSARIAL test: verifying twice must fail; the 6th
      attempt must fail AND the code must be dead afterwards, so a correct
      7th also fails. An implementation that counts without invalidating
      passes the confirmatory half of that.
    source: [AC1.1.3, AC1.1.4, NFR12]

  - id: BR2.4
    statement: >
      The stored OTP value is a hash and never the transmitted code. No log
      line at any level contains the code.
    category: constraint
    applies_to: Storage and logging
    trigger: Issuing a code
    logic: >
      IF a code is issued
      THEN store its hash
      AND log only (purpose, outcome, correlation_id).
    violation_behaviour: >
      Plaintext storage, or a gateway request body in a log — that call
      carries the phone number and the code together.
    rationale: >
      The test READS THE STORED COLUMN and asserts it differs from what was
      sent. Asserting that a correct code verifies is satisfied by storing
      it in plaintext, so the confirmatory test certifies nothing.
    source: [AC1.8.6, project.md: NEVER store or log an OTP in plaintext]

  - id: BR2.5
    statement: >
      A global daily SMS ceiling refuses further sends and fires an alert.
      Per-number and per-IP-prefix sub-ceilings sit beneath it.
    category: constraint
    applies_to: The OTP issue path
    trigger: Any send
    logic: >
      Check the NARROWEST ceiling first and the global one LAST -
      per-number hourly, then per-number daily, then per-IP-prefix hourly,
      then global daily. Increment a scope's counter only when that scope's
      check passes, so a refused request never consumes a wider budget.
    violation_behaviour: >
      Checking global first, which an earlier draft of this rule specified
      and the functional spec repeated. That order lets one attacker's
      requests consume the GLOBAL daily counter before their own per-number
      limit ever trips - so the attacker is stopped eventually, but only
      after spending everyone else's allowance. The sub-ceilings exist
      precisely to prevent that, and checking them last defeats them.
    rationale: >
      The breaker must DEGRADE rather than cliff-edge, which is what the
      sub-ceilings buy: an attacker burning one number's allowance does not
      exhaust everyone else's. **That property requires narrowest-first
      evaluation**, and an earlier version of this rule argued for it in
      prose while specifying the opposite in its logic - caught at review.

      Order and accounting are one decision, not two. A narrowest-first
      check that still increments the global counter on a refused request
      has the same defect in a quieter form.
    source: [AC1.8.4, D-33, team.md Walking Skeleton]

  - id: BR2.6
    statement: >
      When a ceiling trips, the user is told the service is temporarily
      unavailable. The message does not reveal the limit, and never implies
      their number is invalid.
    category: policy
    applies_to: The degraded path
    trigger: Any ceiling breach
    logic: >
      IF a ceiling refused the send
      THEN return a temporary-unavailability message_key
      ELSE the ordinary path.
    violation_behaviour: >
      "Invalid number" tells a legitimate teacher their account is broken
      and tells an attacker which numbers exist. Revealing the limit tells
      an attacker exactly how to pace a drain.
    rationale: >
      Degradation is user-visible, so what the user sees is a rule rather
      than an implementation detail.
    source: [AC1.8.5, NFR12, team.md: degraded mode]

  - id: BR2.7
    statement: >
      Issue responses for a known and an unknown number are BYTE-IDENTICAL,
      and the unknown-number path performs the same hashing work rather
      than returning early.
    category: authorization
    applies_to: The OTP issue path
    trigger: An issue request for any number
    logic: >
      IF the number has no account
      THEN compute the hash that would have been stored, discard it, consume
      budget identically, and return the same response
      ELSE the ordinary path.
    violation_behaviour: >
      An early return makes the unknown path measurably cheaper, so the
      response body matching is not enough.
    rationale: >
      **This is NFR14.4, deferred to this Unit by U2's BR4.4**, and it is
      asserted STRUCTURALLY — that the hash function was called on both
      paths — never as a wall-clock bound. A millisecond assertion is flaky
      and gets deleted the third time CI fails on it.

      **The hash is the SMALLER asymmetry, and an earlier version of this
      rule discussed only that one** - caught at review. The known-number
      branch performs a transactional INSERT of an OtpRequest row; the
      unknown branch performs none. A database write involves lock
      acquisition and a WAL flush, which is a far larger and more reliable
      timing signal than a hash computation. A test asserting only that
      hashing is symmetric would leave the louder channel wide open while
      reading as though the oracle were closed.

      So the requirement is the WRITE, not just the hash: **the unknown
      branch performs an equivalent write and rolls it back**, inside the
      same transaction shape the known branch uses. That is checkable -
      assert both branches issue the same statements - and it closes the
      asymmetry that actually dominates.

      **What remains unclosed, stated so the test is not read as stronger
      than it is**: equivalent work is not constant time. A patient attacker
      with a very large sample could still find residual variance. Closing
      that needs a fixed response deadline - returning only after a wall
      clock elapses regardless of path - which is implementable but
      disproportionate here, and would itself become a latency floor on
      every OTP request.
    source: [AC1.8.7, NFR14.4, BR4.4, desc §12f]

  # ---- BR3.x - The privacy boundary ----

  - id: BR3.1
    statement: >
      What a person writes about themselves lives in Profile, written only
      by its owner. What a teacher types lives in Enrollment, written only
      by the teacher.
    category: authorization
    applies_to: Both name columns
    trigger: Any roster read
    logic: >
      IF a teacher reads a roster
      THEN the query reads Enrollment.display_name
      AND never reaches Profile.
    violation_behaviour: >
      A join to Profile in a teacher-facing query. Structurally visible in
      review, unlike a forgotten filter.
    rationale: >
      "Which name does a teacher see" is answered by WHICH TABLE THE QUERY
      READS, not by a filter someone remembers to apply. That is what makes
      the boundary structural rather than procedural.
    source: [AC1.5.2, TC-13, D-5, D-7]

  - id: BR3.2
    statement: >
      Profile carries row-level security with a policy keyed on the
      session's account id.
    category: authorization
    applies_to: Profile
    trigger: Any query against Profile
    logic: >
      IF a session reads Profile
      THEN it sees only rows whose account_id matches its own
      ELSE the policy denies.
    violation_behaviour: >
      RLS absent, disabled, or bypassed by connecting as a superuser.
    rationale: >
      The second of the three layers. U2 shipped the third (teacher-facing
      schemas carry no profile fields); this Unit adds the table split
      (BR3.1) and the policy.
    source: [NFR14, TC-13, team.md Testing Posture]

  - id: BR3.3
    statement: >
      Database tests connect as a RESTRICTED NON-SUPERUSER role, and a
      meta-test asserts that before the privacy suite runs.
    category: constraint
    applies_to: The integration suite
    trigger: Any privacy-boundary test
    logic: >
      IF current_user is a superuser
      OR row_security is off
      OR no policy exists on Profile
      THEN fail before running the suite.
    violation_behaviour: >
      The default testcontainers connection is `postgres`, a superuser.
    rationale: >
      **PostgreSQL documents that superusers and table owners bypass RLS
      entirely.** A privacy suite run as superuser passes identically
      whether the policy is correct, broken, or absent — so the strongest
      test obligation in the project would certify nothing. The meta-test is
      what makes every other privacy test mean something.
    source: [project.md NEVER, pg-rls, Q9, TC-13]

  # ---- BR4.x - Tokens ----

  - id: BR4.1
    statement: >
      A refresh rotates: the presented token is invalidated and a new pair
      is issued. Presenting a rotated-out token invalidates THE WHOLE
      FAMILY.
    category: authorization
    applies_to: The refresh path
    trigger: Any refresh request
    logic: >
      IF the presented token has rotated_at set
      THEN invalidate every token sharing its family_id and refuse
      ELSE rotate it and issue a new pair in the same family.
    violation_behaviour: >
      Invalidating only the presented token leaves the thief's token
      working, which inverts the control.
    rationale: >
      **Reuse detection degrades silently into non-rotating tokens, because
      the happy path is identical either way.** The difference appears only
      when an old token is presented again — which is exactly the stolen-
      token case the mechanism exists for. Tested as a STATE MACHINE over
      five transitions, not as a happy path.
    source: [US1.8, NFR13, team.md Testing Posture]

  - id: BR4.2
    statement: >
      Refresh tokens are stored hashed. Access tokens expire in 15 minutes
      and expiry is enforced server-side.
    category: constraint
    applies_to: Token storage and validation
    trigger: Issuing or validating a token
    logic: >
      IF a refresh token is stored
      THEN store its hash
      AND reject an access token past its expiry.
    violation_behaviour: >
      A leaked table yielding live sessions; or expiry trusted from a
      client-supplied claim without server-side comparison.
    rationale: >
      Asserted by reading the column, as with the OTP hash, and by a test
      that a 15-minute-expired token is refused.
    source: [NFR13, team.md Testing Posture]

  - id: BR4.3
    statement: >
      JWTs carry a `kid` header and the verifier accepts two valid keys.
    category: constraint
    applies_to: Token signing and verification
    trigger: Any token operation
    logic: >
      IF a token is signed
      THEN it names its key id
      AND verification accepts either of two configured keys.
    violation_behaviour: >
      A single-key verifier. Rotating the signing key then force-logs-out
      every holder of a 30-day refresh token, at exactly the moment rotation
      is needed.
    rationale: >
      Costs almost nothing now and is a mass-logout incident to retrofit
      later, which is why team.md pulls it into the skeleton.
    source: [team.md Walking Skeleton, NFR13]

  # ---- BR5.x - The gateway ----

  - id: BR5.1
    statement: >
      Success is response_code == 202 and nothing else. A non-2xx HTTP
      status means a transport problem, never an application rejection.
    category: constraint
    applies_to: The BulkSMSBD adapter
    trigger: Any send
    logic: >
      IF response_code == 202
      THEN SENT
      ELSE map the code to the taxonomy; an unrecognised code is FatalError.
    violation_behaviour: >
      raise_for_status() as a success check. BulkSMSBD returns HTTP 200
      with the error in the body — verified against the live endpoint.
    rationale: >
      The field is `response_code`, not `code`. Named explicitly because
      the most-installed Python client for this gateway parses `code` and
      mocks {'code': 202} in its tests, so its tests pass against a fiction.
    source: [contract-summary §C.4.1]

  - id: BR5.2
    statement: >
      The scheme is https and is enforced in code, not configuration.
    category: constraint
    applies_to: The adapter's construction
    trigger: Adapter instantiation
    logic: >
      IF urlparse(base_url).scheme != "https"
      THEN raise.
    violation_behaviour: >
      Plain HTTP serves the same API with no redirect and no HSTS —
      verified — so a misconfigured http:// ships the phone number AND the
      OTP in cleartext and SUCCEEDS SILENTLY. Nothing fails, warns or logs.
    rationale: >
      Under RC-1/RC-2/RC-3 that is a privacy failure on children's-adjacent
      data. Per team.md's "where a rule is important, it is mechanical", the
      scheme is not a configuration value and no TLS-verification toggle is
      exposed.
    source: [contract-summary §C.4.2, RC-1, RC-2, RC-3]

  - id: BR5.3
    statement: >
      A send is attempted exactly once. There is no automatic retry at any
      layer. A timeout or an ambiguous response is UNKNOWN, never FAILED.
    category: policy
    applies_to: The adapter
    trigger: Any send outcome
    logic: >
      IF the call times out OR returns code 1005
      THEN record UNKNOWN and consume budget
      ELSE map the outcome.
    violation_behaviour: >
      Automatic retry double-charges and double-messages. There is no
      idempotency key and no message id to deduplicate against.
    rationale: >
      The gateway offers NO delivery report and no message id, verified
      against nine probed endpoint names. So 202 means "submitted" and
      nothing more, permanently — which makes the UNKNOWN state mandatory
      rather than cautious. The user-facing path for every non-SENT outcome
      is "request a new code", presented as a delivery failure and never as
      an incorrect code.
    source: [contract-summary §C.3, §C.4.5, AC1.1.5]

  - id: BR5.4
    statement: >
      Every non-production environment runs a null adapter, selected by
      explicit configuration, with the null adapter as the default.
    category: constraint
    applies_to: Adapter selection
    trigger: Application startup
    logic: >
      IF the environment explicitly names the real adapter
      THEN construct it
      ELSE construct the null adapter.
    violation_behaviour: >
      Defaulting to the real adapter means a missing or misspelt setting
      spends real money and messages a real person.
    rationale: >
      BulkSMSBD has no sandbox, so team.md's "non-production holds test
      credentials" cannot hold as written — the mechanism it names does not
      exist. The property it protects is preserved by a different mechanism,
      and the default fails SAFE, toward not sending.
    source: [contract-summary §C.4.6 / OQ-3a]

  - id: BR5.5
    statement: >
      The OTP message body is English GSM-7 and the rendered template,
      including the SMS Retriever app hash, is asserted to fit one segment.
    category: constraint
    applies_to: The OTP template
    trigger: Build time
    logic: >
      IF the rendered template exceeds 160 GSM-7 characters
      THEN fail the build.
    violation_behaviour: >
      Silently doubling the per-OTP cost with no error and no signal.
    rationale: >
      Code 1012 does not apply to OTP traffic, so the body stays English at
      160 characters per segment rather than 70. The app hash consumes 12 of
      them, which is easy to forget until the invoice arrives.
    source: [contract-summary §C.4.6 / OQ-3b, §C.4.7, TC-5]

  # ---- BR6.x - Boundaries this Unit must not cross ----

  - id: BR6.1
    statement: >
      U3 creates Owner and Enrollment EMPTY and never writes them.
    category: constraint
    applies_to: This Unit's migration and queries
    trigger: Any write
    logic: >
      IF a statement writes Owner or Enrollment
      THEN it does not belong in this Unit.
    violation_behaviour: >
      Asserted by a test over this Unit's own SQL and ORM usage.
    rationale: >
      Empty is not absent: a query against a table that does not exist
      fails, so lens resolution needs both to exist. Table shape only — not
      an ownership transfer and not a dependency on U4, which owns their
      behaviour and extends their columns.
    source: [unit-of-work.md U3, units-generation learning]

  - id: BR6.3
    statement: >
      B3's verification needs an Owner row and an Enrollment row that no U3
      code may create. They are inserted by a COMMITTED SEED SCRIPT, run
      manually against staging as a verification precondition, and never by
      application code.
    category: constraint
    applies_to: The skeleton verification only
    trigger: Preparing the B3 checkpoint
    logic: >
      IF the skeleton must demonstrate a teacher lens
      THEN a seed script inserts one Owner row and one Enrollment row
      AND that script lives beside the migration, is committed, and is
      never imported by application code
      ELSE no lens resolves and the verification cannot run.
    violation_behaviour: >
      An INSERT inside U3 to make the demo work. That is the ownership
      transfer BR6.1 forbids, and it would arrive disguised as a fixture.
    rationale: >
      **The empty-shell rule solved the schema question and left the data
      question open, and the two are not the same.** A recorded learning
      from Units Generation already says a Unit claiming to run standalone
      must answer the schema question explicitly rather than infer it from
      data-emptiness. The same reasoning applies one level up: B3's own
      confidence hypothesis requires an account that OWNS ONE BATCH and is
      enrolled as a guardian, and U3 can create neither.

      Without this rule the skeleton can prove the OTP path and the absence
      of a lens, and nothing else — an account with no Owner and no
      Enrollment row resolves to no lens at all, so the single most
      structurally unusual decision in the system goes undemonstrated at
      the one checkpoint built to demonstrate it.

      A seed script rather than application code, because the alternative
      is an INSERT inside U3 that would then need removing at B5. The
      script is throwaway by intent and its removal is a B5 obligation.
    source: [bolt-plan B3 confidence hypothesis, BR6.1, units-generation learning]

  - id: BR6.2
    statement: >
      No log line carries a phone number, an OTP, a token or a child name.
      Every error log carries the correlation id.
    category: constraint
    applies_to: Every log statement in this Unit
    trigger: Any logging call
    logic: >
      IF a log line is emitted
      THEN it carries the correlation id and none of the four forbidden
      values.
    violation_behaviour: >
      Gateway request bodies logged at any level — that call carries the
      phone number and often the code itself.
    rationale: >
      Phone numbers are children's-adjacent personal data under RC-1/RC-2/
      RC-3, so this is a compliance rule rather than hygiene. The audit log
      holds no OTP, no token and no child name: an audit log that leaks what
      it audits is a common and self-defeating mistake.
    source: [team.md Deployment, RC-1, RC-2, RC-3]
```

---

## Part B — Rules summary

| Rule | Category | What it fixes |
|---|---|---|
| **BR1.1** | authorization | The lens is computed, never stored or cached |
| **BR1.2** | authorization | Ownership gained mid-session takes effect next request |
| **BR1.3** | authorization | Ownership lost mid-session takes effect next request |
| **BR1.4** | constraint | Memoization on the request object, nowhere else |
| **BR2.1** | constraint | Counters in the datastore, not in a process |
| **BR2.2** | constraint | Per-number and per-IP limits, checked before the call |
| **BR2.3** | constraint | Expiry, single-use and the attempt ceiling |
| **BR2.4** | constraint | Hashed storage; the code never reaches a log |
| **BR2.5** | constraint | Global ceiling with sub-ceilings beneath it |
| **BR2.6** | policy | Degraded mode says unavailable, not invalid |
| **BR2.7** | authorization | Byte-identical responses; same hashing work |
| **BR3.1** | authorization | Two name columns, two writers, two tables |
| **BR3.2** | authorization | Row-level security on Profile |
| **BR3.3** | constraint | The suite connects as a non-superuser |
| **BR4.1** | authorization | Reuse invalidates the family, not one token |
| **BR4.2** | constraint | Hashed refresh tokens; enforced expiry |
| **BR4.3** | constraint | JWT `kid` and two valid keys |
| **BR5.1** | constraint | 202 is the only success signal |
| **BR5.2** | constraint | HTTPS enforced in code |
| **BR5.3** | policy | One attempt; timeout is UNKNOWN |
| **BR5.4** | constraint | Null adapter by default outside production |
| **BR5.5** | constraint | One-segment OTP template, app hash included |
| **BR6.1** | constraint | Owner and Enrollment created empty, never written |
| **BR6.2** | constraint | No phone, OTP, token or child name in any log |
| **BR6.3** | constraint | A committed seed script supplies the rows the skeleton must demonstrate |

---

## Assumptions & Open Questions

**None.** [assumption] All three BulkSMSBD questions closed before this
stage and their answers are binding here as BR5.1 through BR5.5.
