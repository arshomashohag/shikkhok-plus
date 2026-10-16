**Collaborator:** aidlc-devsecops-agent

## Contribution

Remit: lint/format rules, SAST/DAST, secret and dependency scanning, supply-chain
controls. The draft is strong on testing posture and deployment; the security
tooling is where it is still a sentence rather than a practice. Two lines carry
almost all of the unspecified security work:

> Dependency and secret scanning run in CI on every push. Critical and High
> findings block the merge.

> The forbidden-identifier set is a dependency rule, not a coding rule. [...]
> Every new dependency is checked against this before it is added.

Neither names a tool, and the second names no mechanism at all. Below is what I
would put in their place.

---

### 1. Dependency and secret scanning — name the tools, change the threshold

**Tools (all free for this stack, no paid tier):**

| Concern | Tool | Why this one |
|---|---|---|
| Python dependency CVEs | `pip-audit` | Reads the resolved lockfile, queries PyPI's own advisory feed and OSV, no account, no token, runs in ~5s. |
| Gradle/Kotlin dependency CVEs | OSV-Scanner on the Gradle lockfile | OWASP Dependency-Check is the better-known answer and the wrong one here: its NVD feed download is slow, rate-limited without an API key, and famously noisy on Android transitive deps. OSV-Scanner is a single static binary against the same OSV data the Python side uses, so one findings format across both surfaces. |
| Secrets in commits and history | Gitleaks, as a pre-commit hook **and** a CI job | Pre-commit is the control that actually works; CI is the backstop for a `--no-verify`. GitHub's own push protection is free on public repos only, so do not rely on it for a private repo. |
| SBOM | Syft, one per release build, attached to the Play release record | Not a merge gate. It exists so that when a CVE lands on a shipped version you can answer "is it in the AAB on the store" in a minute instead of a day. At V1 this is cheap and it is the only artifact that makes a post-release dependency incident tractable for one person. |

**Locked dependency resolution is a precondition, not an extra.** Without a
lockfile on both surfaces the scanners are scanning a version range, not the
build. Mandate `uv.lock` (or `requirements.txt` compiled by `uv pip compile` /
`pip-tools`) for Python and Gradle dependency locking plus `dependencyVerification`
checksums for Kotlin. The checksum verification is the part that matters: it is
the only control in this project that detects a tampered or substituted
artifact in the Gradle supply chain, and it costs one generated file.

**"Critical and High block" is the wrong gate and I would replace it.** The
draft's own Deployment section already contains the better formulation — "no
open Critical or High dependency finding" as a *release* checklist item — and
then overrides it with a per-push merge block. The failure mode is specific and
predictable: a solo developer with no on-call rotation hits a Critical CVE in a
transitive Android dependency with no upstream fix available, on a Tuesday, mid-Bolt.
There is no security team to triage it and no second reviewer to approve an
exception. The gate is bypassed, and once bypassed once it is decoration.

Replace with a two-speed gate:

- **Blocking on every push, no exceptions, no severity threshold:** a Gitleaks
  finding, and a dependency-lockfile or checksum-verification failure. These are
  binary, near-zero false positive, and always actionable by the person who just
  pushed. A committed secret is the one finding where "fix it later" is wrong.
- **Non-blocking annotation on every push:** dependency CVEs, at every severity,
  posted as a PR comment.
- **Blocking at the release gate** (the Play internal-track promotion, which is
  already a checklist in the Deployment section): every Critical and High
  finding is either fixed or carries a dated, written exception. Reachability
  matters here — a High in a test-only or build-only dependency is not the same
  risk as one in the request path, and the exception note should say which.

This keeps the hard stop where it is enforceable by one person on a known
cadence, and puts the CVE feed where it informs rather than where it obstructs.
Exceptions live in a committed `.security-exceptions.md` with a required expiry
date; an expired exception fails the release gate. One file, no tooling.

**Dependabot or Renovate: weekly, grouped, not daily.** Daily individual PRs on
a two-language repo with one reviewer produce a PR backlog that gets closed
unread. Weekly grouped by ecosystem with the security-only channel left
immediate is the version that survives.

---

### 2. The forbidden-identifier set — review is not a control, and here is what is

This is the right call on importance and the wrong call on mechanism. "Every new
dependency is checked against this before it is added, enforced by review" fails
for the exact reason the risk exists: the prohibited collection is in a
*transitive* SDK that the developer never chose and never read. A reviewer
looking at `implementation("com.example:analytics:1.2")` in a Gradle diff cannot
see that it pulls an SDK that reads `Settings.Secure.ANDROID_ID`. No amount of
review discipline fixes that, and the cost of being wrong is a Families-policy
rejection after submission.

Direct answer to the brief's question: **a Gradle dependency check cannot detect
it; a merged-manifest permission check catches only a fraction; the control that
actually catches it is a static scan of the merged bytecode plus the merged
manifest, and Play's own pre-launch and Data Safety review is the last net, not
the first.** Four layers, cheapest first:

1. **Merged-manifest permission allowlist, as a Gradle task that fails the
   build.** Assert the merged manifest of the release variant contains exactly
   an approved permission set and nothing else. This catches a transitive SDK
   that declares `READ_PHONE_STATE`, `ACCESS_WIFI_STATE`, `READ_SMS`,
   `AD_ID`, or `ACCESS_FINE_LOCATION`. It is cheap, deterministic, and directly
   enforces the draft's own `NEVER request SMS read permission` rule, which is
   currently enforced by nothing. **Crucially it must also assert the absence of
   `com.google.android.gms.permission.AD_ID`** — that is the declaration Play's
   Families review looks for, and a transitive ads/analytics SDK adds it
   silently via manifest merger. It does *not* catch `AAID` read without that
   permission on older target SDKs, or `ANDROID_ID`, `Build.getSerial`, BSSID or
   SSID reads, which need no permission or a permission the app may hold anyway.

2. **A forbidden-API bytecode scan on the release AAB/APK, as a CI gate.** This
   is the layer that actually answers the question, and it is the one the draft
   is missing. Practical options, in order of effort:
   - A R8/ProGuard-independent scan: `dexdump`/`baksmali` the release DEX and
     grep the string and method-reference tables for the forbidden surface —
     `getImei`, `getSubscriberId`, `getSimSerialNumber`, `getLine1Number`,
     `Build.getSerial`, `getMacAddress`, `getBSSID`, `getSSID`,
     `AdvertisingIdClient`, `ANDROID_ID`. Method references survive minification
     because they are framework calls; obfuscation renames *your* symbols, not
     `android.telephony.TelephonyManager.getImei`. This is a 30-line script, and
     it is the highest-value security control I can name for this project per
     hour spent.
   - Lint's own `HardwareIds` check, raised to `fatal` in `lint.xml`. Free, but
     it analyses sources and may not reach into every third-party AAR, so treat
     it as a complement rather than the gate.
   - Known-tracker detection (an Exodus-Privacy-style signature list, or a
     dependency-name denylist) as a secondary signal.
   This scan must run on the **R8-minified release build**, not the debug build:
   a debug build can differ in which dependencies are present, and the release
   AAB is what ships.

3. **An SDK admission note, one paragraph per new third-party dependency.** Not
   a policy document — a committed line recording what the SDK collects and the
   vendor's own disclosure link. The point is not the document; the point is that
   the layer-1 and layer-2 gates generate a finding and this is where the answer
   is recorded so the Data Safety form can be filled from it rather than from
   memory. The Data Safety form is a release blocker in the draft already; this
   is its input.

4. **Play's pre-launch report on the internal track** is the final net. TC-18
   already puts the app there for back-stack and accessibility; it also flags
   some privacy and permission issues. Treat it as confirmation, never as the
   control, because by the time it fires the dependency is already in the build.

The strongest single recommendation in my whole contribution: **replace
"enforced in review" with layers 1 and 2, and make the bytecode scan a gate on
the release build.** Everything else here is proportionate; that one is
load-bearing.

---

### 3. Secrets handling — the progression is right, two things are missing

Environment variables in Phase 1 and Secrets Manager/SSM in Phase 2 is the
correct and honest answer at this budget. Secrets Manager at roughly USD 0.40
per secret per month for three secrets is affordable, but it buys little in
Phase 1 when there is one host and one operator. **SSM Parameter Store
`SecureString` is free and I would go there rather than Secrets Manager** unless
automatic rotation is actually wired up — paying for rotation you do not use is
the definition of a control that does not earn its place.

Missing, in order of importance:

- **A rotation procedure, which is distinct from a rotation schedule.** Do not
  mandate quarterly rotation; nobody solo does it and an unkept schedule is worse
  than none. Mandate instead that each of the three named secrets has a written,
  *exercised-once* rotation runbook. The JWT signing key is the one that needs
  design work, not just a runbook: rotating it invalidates every outstanding
  30-day refresh token and logs out every user unless the verifier accepts two
  keys during an overlap window. **Support a key id (`kid`) and two valid
  verification keys from the first commit.** Retrofitting that after an incident
  means a forced mass logout at exactly the worst moment, and it costs almost
  nothing to build now.
- **Secret-exposure paths beyond the repository.** The draft's `NEVER hardcode a
  credential` covers the repo and the image. It does not cover the three places
  these actually leak: application logs, exception tracebacks returned to a
  client, and — the one specific to this project — **the SMS gateway request/
  response log**. A gateway call carries a phone number and often the OTP itself
  in the request body. Mandate that gateway request bodies are never logged at
  any level, that the OTP never appears in any log line (the draft forbids
  plaintext OTP storage and logging — good, but the gateway client is where that
  rule will be broken by a well-meant debug statement), and that database URLs
  are redacted in connection-error output.
- **Operational access to production is genuinely undefined, and the brief is
  right that this is a gap.** No admin surface means every production operation —
  reading a stuck fee cycle, correcting a bad migration, investigating an OTP
  complaint — happens via SSH or `psql` against the live database holding
  children's names, attendance and marks. There is no audit trail of that access
  and nothing distinguishes legitimate support from a privacy incident. At this
  budget I would not build an admin surface. I would mandate three things:
  (a) production database access is via a named, non-superuser role, never the
  application's own role; (b) every interactive production database session is
  via a wrapper that logs session start, the person, and the stated reason to an
  append-only location (`psql` with a logging wrapper and `log_statement = 'mod'`
  is enough); (c) a standing rule that no production query result containing
  child-identifying data is copied into a local file, a chat, or an AI tool
  context. That third one is a real exposure path in an agent-assisted build and
  nothing currently addresses it.

---

### 4. The homemade auth surface — what to mandate, and what the seven controls miss

**The practice to mandate: a written abuse-control test suite, one adversarial
test per named control, as a release blocker on the auth slice.** R-5's
mitigation says "security review before the auth slice ships". A security review
by the person who wrote the code, who has no declared security background, is
the weakest possible form of that mitigation. Seven controls with explicit
numeric thresholds are, unusually, *perfectly testable*: each is an assertion
about behaviour at a boundary. So mandate tests, not a review:

- 4th OTP request for a number inside an hour is refused; 6th inside a day is refused.
- 11th request from an IP inside an hour is refused.
- An OTP presented at 5m01s is refused.
- An OTP that verified successfully cannot verify a second time.
- 6th verify attempt against one OTP is refused and the OTP is dead afterwards.
- The stored OTP value does not equal the transmitted one (hashing is real, not intended).
- Issue responses for a known and an unknown number are byte-identical, and
  their timing distributions are not separable.

That last one deserves a note: a timing assertion in a unit test is flaky and
will be deleted the third time it fails in CI. Do not assert a millisecond
bound. Assert the **structural** property instead — that both paths execute the
same work, e.g. that the unknown-number path performs the same hash computation
rather than returning early. Structure is testable; wall-clock is not, at this
scale.

Also mandate that **the rate-limit counters live in the datastore, not in
process memory**. A per-process dict is the classic implementation and it
silently stops working the moment there are two workers — which Phase 1 will
have, since a single Lightsail host still runs multiple Uvicorn workers. This is
a correctness bug that presents as "the limit works in testing".

**What is missing from the seven controls** — four gaps, in priority order:

1. **No refresh-token reuse-detection response.** The architecture says refresh
   tokens rotate so "theft is detectable", and then V1 has no revocation path.
   Detectable and not actable is not a control. When a rotated-away refresh token
   is presented, the correct response is to invalidate the entire token family
   for that account, forcing re-authentication. That is implementable without
   multi-device session management and closes the loop the architecture opens
   and leaves open.
2. **The cost circuit-breaker is global-only, which makes it a denial-of-service
   lever.** One attacker burning the global daily ceiling locks out every
   legitimate teacher for the rest of the day — abuse converts a financial attack
   into an availability attack. Add a per-IP-prefix and a per-hour sub-ceiling
   beneath the global daily one, so the breaker degrades rather than cliff-edges,
   and define the behaviour when it trips: what does a legitimate user see, and
   is there any path to log in at all? The draft treats this control as a
   deployment concern needing staging verification, which is right as far as it
   goes, but staging verification of an untested-by-design behaviour verifies
   that the alert fires, not that the system remains usable.
3. **Nothing rate-limits the authenticated API, only the OTP endpoints.** All
   seven controls sit in front of `/auth/*`. A valid token then has unbounded
   access to the fee, attendance and profile endpoints. With row-level security
   and lens resolution the blast radius is one account's data, which is why this
   is third and not first — but a blanket per-token request ceiling is a few
   lines in middleware and it is the difference between one compromised account
   and a scripted scrape of everything that account can reach.
4. **No authentication audit log.** See §6 — this is the same gap seen from the
   compliance side.

---

### 5. SAST/DAST — what earns its place, and what is theatre

**Earns its place:**

- **Ruff's security rules, which the draft already has for free and does not
  claim.** Ruff is chosen for format and lint; enabling its `S` (flake8-bandit)
  ruleset makes it the SAST tool. Zero additional tooling, zero additional CI
  minutes, catches hardcoded passwords, `assert` in production paths, weak
  hashing, `subprocess` with `shell=True`, and unsafe deserialization. This
  should be stated explicitly in the Code Style section, because "Ruff for format
  and check" will otherwise be configured without it.
- **Semgrep with a small set of project-specific rules, free tier.** The value
  here is not the generic OWASP ruleset — it is custom rules that encode *this
  project's* invariants, which no generic scanner knows: no `float`/`Decimal`
  arithmetic on money outside the designated module (the draft says it will "add
  an import-boundary lint check for it if it is ever violated" — write the rule
  now, it is four lines, and "if it is ever violated" means after the money bug
  shipped); no route handler without an explicit lens dependency; no
  `TelephonyManager` reference anywhere in Kotlin; no `Double`/`Float` in a
  money-carrying data class. These are the rules that make the draft's strongest
  structural decisions mechanically enforced instead of review-enforced. Semgrep
  earns its place *because* of the custom rules, not despite them.
- **mypy strict on the money and authorization modules.** The draft has this.
  It is correctly scoped and it is doing real security work on the authorization
  layer.
- **A single scripted DAST pass before the Play internal-track promotion**, not
  on every push. OWASP ZAP baseline scan against the staging host, driven from
  the committed OpenAPI 3.1 schema so it exercises real authenticated routes
  rather than crawling blind. One run, one report, reviewed by hand. The OpenAPI
  schema being committed (already in the draft) is what makes this cheap, and is
  an underrated reason that decision is correct.
- **A hand-written authorization probe suite**, which is the draft's "adversarial
  privacy boundary tests" and is already correct. Say explicitly that it covers
  the IDOR shape: teacher A requesting teacher B's batch, guardian requesting a
  non-child's enrollment, a student requesting a fee cycle not their own. This
  is the vulnerability class a scanner cannot find and the one most likely to
  exist, because it requires knowing the intended policy.

**Theatre at this scale:**

- **Continuous DAST / ZAP full active scan in CI.** Long-running, noisy against
  a FastAPI app with Pydantic validation at every boundary, and the findings on a
  typed JSON API are overwhelmingly informational header advice.
- **SonarQube or SonarCloud.** Self-hosting costs more than the entire
  infrastructure budget in compute; the free cloud tier requires a public repo.
  Ruff plus Semgrep covers the security subset for nothing.
- **A commercial SCA platform (Snyk paid tier, Mend).** The free tiers duplicate
  `pip-audit` and OSV-Scanner, and the paid tiers price above the whole budget.
- **CodeGuru Security / Amazon Inspector.** Inspector prices per-resource and
  scans an EC2/ECR estate that barely exists here; CodeGuru overlaps Ruff's `S`
  rules on Python for a per-scan fee.
- **A penetration test.** Correct to want, impossible at this budget. The honest
  substitute is the written abuse-control test suite in §4 plus the authorization
  probe suite, and recording in the RAID log that R-5 remains partially
  unmitigated because no independent assessment is affordable. Do not let a test
  suite be described as having closed R-5.
- **Container image CVE scanning as a merge gate.** Trivy on the release image is
  worth one run at the release gate for base-image CVEs; as a per-push blocking
  gate on a Debian-slim base it blocks merges on OS packages the app never calls.

---

### 6. Children's data — the practice gaps the draft does not cover

The draft handles the identifier constraints well and is silent on everything
else RC-2 and RC-3 require. Four missing practice-level controls:

1. **TC-19 is absent from both files, and it is a hard release blocker.** Two
   account-deletion paths — in-app, plus an externally accessible route usable
   without reinstalling the app — is a recorded constraint with a Play policy
   source, and it appears in neither `team-practices.md` nor the Mandated list in
   `discovered-rules.md`. The draft mandates the Data Safety form and privacy
   policy as release-blocking V1 deliverables and omits the deletion paths, which
   sit on exactly the same Play policy page and are the thing most likely to fail
   review. This is the single clearest omission I found. It needs a Mandated rule
   with `[TC-19]` as its origin, and the externally accessible route needs a
   practice note: it implies a web surface, however minimal, which the
   architecture does not currently include and the budget has not costed.
2. **No deletion semantics, which is where deletion requirements actually
   fail.** "Delete the account" is underspecified against this data model in ways
   that matter: a student's attendance and marks were written by the *teacher*
   and are the teacher's record; the same rows are the child's personal data. A
   guardian exercising a GDPR-K erasure right and a teacher's legitimate business
   record are in direct tension, and RC-5 already anticipates this by requiring
   the privacy policy to state what is retained post-deletion and why. Mandate
   that every table holding child-identifying data carries a written deletion
   disposition — hard delete, anonymize-in-place, or retain-with-stated-basis —
   decided at Domain Design and asserted by a test, and that the privacy policy
   text is generated from those dispositions rather than written independently of
   them. A privacy policy that contradicts the implementation is worse than a
   vague one.
3. **No retention policy at all.** COPPA's data-minimization expectation is that
   children's data is not held indefinitely after it stops being needed. Nothing
   in the draft says when an abandoned enrollment's attendance and marks age out,
   or how long OTP records, refresh tokens, failed-verify records and rate-limit
   counters are kept — and those last four are the easy win, because they are
   high-volume, contain phone numbers, and have an obvious short lifetime.
   Mandate a stated retention period per data class with a scheduled purge, and
   start with the auth records where the answer is uncontroversial (days, not
   months). A retention policy with one unresolved row is still far better than
   none.
4. **No audit log of access to children's data.** This is the gap behind both
   §3's undefined production access and §4's missing auth audit log. The
   required minimum, and it is small: an append-only record of authentication
   events (OTP issued, verify failed, verify succeeded, refresh rotated, refresh
   reuse detected) and of every interactive production database session. Not
   per-row access logging — that is disproportionate here and would be
   unaffordable in storage. But with zero audit logging the project cannot answer
   "was this child's data accessed improperly" at all, which is the question both
   COPPA and GDPR-K assume you can answer, and which a parent complaint will ask.
   Mandate also that the audit log itself holds no OTP, no token, and no child
   name — an audit log that leaks what it audits is a common and self-defeating
   mistake.

One further note: the draft's Testing Posture correctly makes the privacy
boundary adversarially tested. Extend that to the deletion paths once TC-19 is
in scope — a deletion test that asserts the rows are actually gone (or actually
anonymized) per their stated disposition. Deletion features are the ones most
reliably shipped broken, because nobody tests the absence of data.

---

### 7. What the interview must resolve

Security-specific, beyond the items already in the draft's Assumptions:

1. **The CI platform choice is a security decision, not only a cost one** — and
   the draft lists it as unresolved without saying so. It determines where the
   CI secrets live and what has write access to the repository. GitHub Actions
   on a private repo means GitHub holds the deploy credentials and minutes are
   metered; CodePipeline/CodeBuild keeps them in the AWS account under IAM.
   Either is defensible; this must be decided before any pipeline work, because
   every gate in this contribution is written against one of them. Ask also
   whether the repository is public or private — it changes which free tiers and
   which GitHub-native security features are available.
2. **Is the forbidden-API bytecode scan accepted as a build gate?** It is the
   one control I am asking for that costs real implementation effort (a day,
   roughly). If the answer is no, R-6's "no device identifiers anywhere" remains
   mitigated by review only, and the RAID log should say so rather than claiming
   the constraint is enforced.
3. **Merge-gate threshold:** does the user accept the two-speed model (secrets
   and lockfile integrity block every push; CVEs annotate and block at the
   release gate), or do they want the stricter per-push Critical/High block the
   draft proposes? My position is in §1, but this is their call and it is the
   kind of rule that, once in permanent memory, is either followed or quietly
   abandoned.
4. **TC-19's externally accessible deletion route: what is it?** A static page
   plus an email address, a minimal web form on the same host, or a public
   endpoint. This has architecture and budget consequences the Ideation artifacts
   do not resolve, and it is release-blocking.
5. **Retention periods per data class.** The auth records (OTP, refresh tokens,
   rate-limit counters, failed-verify records) can be answered in the interview
   in one sentence. The child academic records — attendance, marks — need the
   user's view on the teacher's-record-versus-child's-data tension, and that view
   determines what the privacy policy can say.
6. **Is there any production access other than the developer's own?** If a pilot
   teacher ever needs support that requires looking at their data, the access and
   audit controls in §3 need to exist before the pilot, not after.
7. **Does the selected SMS gateway's API expose the OTP in a loggable request
   body, and does it have a sandbox?** The draft already flags the sandbox
   question. The logging question is the security half of it and should be asked
   in the same breath when the vendor is evaluated.

---

## Positions

AGREE: Secrets never in the repository or the image, with env vars in Phase 1 and a managed store in Phase 2 — the progression is correctly proportionate to the budget and the operator count.

AGREE: Committing the generated OpenAPI 3.1 schema — it makes a contract change reviewable and is what makes a single cheap DAST pass worth running at all.

AGREE: Adversarial privacy-boundary tests at both the database and API layers, and the real-PostgreSQL integration rule — row-level security cannot be tested against SQLite, so the alternative would be an untested security control.

AGREE: Prefer conventional, well-documented Android choices given no declared Android experience — unconventional code on an unreviewable surface is itself a security risk.

AGREE: Rollback as redeploying a commit-SHA-tagged immutable image, with `latest` never deployed — this is also a supply-chain control, since it makes the deployed artifact identifiable.

AGREE: The cost circuit-breaker must be live and verified in staging before the auth slice reaches production, and non-production environments must hold sandbox gateway credentials.

OBJECT: "Dependency and secret scanning run in CI on every push. Critical and High findings block the merge" — one undifferentiated gate over two very different finding classes. Secrets and lockfile integrity should block every push; dependency CVEs should annotate on push and block at the release gate, because an unfixable transitive Critical will otherwise be bypassed and the gate discredited (§1).

OBJECT: The forbidden-identifier set enforced by dependency review — review cannot see a transitive SDK's identifier collection, which is precisely the risk. Needs a merged-manifest permission allowlist and a forbidden-API scan of the minified release bytecode as build gates (§2).

OBJECT: No scanning tools are named anywhere in the draft, so a rule that scanning happens is not yet a practice. pip-audit, OSV-Scanner, Gitleaks, Syft, Semgrep, Ruff `S` rules — all free, all specified in §1 and §5.

OBJECT: Ruff is specified for format and lint without its security ruleset — the project's SAST capability is sitting unclaimed in a tool already chosen (§5).

OBJECT: The money-module import boundary and the per-endpoint lens requirement are listed as "enforced in review", with an import-boundary lint check deferred until "if it is ever violated" — these are the draft's two strongest structural decisions and both should be Semgrep rules written now, because "if it is ever violated" means after the bug shipped (§5).

OBJECT: Dependency resolution is not locked anywhere in the draft. Without `uv.lock`/compiled requirements and Gradle dependency locking with checksum verification, the scanners scan a version range rather than the build, and nothing detects a substituted Gradle artifact (§1).

OBJECT: TC-19's two account-deletion paths appear in neither file, although sibling constraints from the same Play policy page (RC-4 Data Safety, RC-5 privacy policy) are mandated as release-blocking. This is a release blocker with an architecture and budget consequence (§6.1).

OBJECT: No data-retention practice and no deletion semantics, although COPPA and GDPR-K apply and RC-5 requires the privacy policy to state what is retained post-deletion. The auth-record retention answer is uncontroversial and can be settled in the interview (§6.2, §6.3).

OBJECT: No audit logging of authentication events or of production database access, and with no admin surface the latter is entirely undefined — the project cannot answer whether a child's data was accessed improperly (§3, §6.4).

OBJECT: The seven abuse controls are treated as complete. Four gaps: no refresh-token reuse response despite the architecture claiming theft is detectable; the global-only cost ceiling converts a financial attack into a lockout of all legitimate users; no rate limiting on the authenticated API; no auth audit log (§4).

OBJECT: R-5's mitigation of "security review before the auth slice ships" is a self-review by a developer with no declared security background. Replace with a mandated abuse-control test suite — one adversarial test per named control, all seven of which have testable numeric thresholds (§4).

OBJECT: Rate-limit counters must be mandated as datastore-backed, not in-process. A per-process counter works in testing and silently fails with multiple Uvicorn workers, which Phase 1 will have (§4).

OBJECT: JWT key rotation is not addressed. Without `kid` support and two valid verification keys from the first commit, rotating the signing key forces a mass logout of every user holding a 30-day refresh token — at exactly the moment rotation is needed (§3).
