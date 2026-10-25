## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-25T08:05:41Z
**Iteration:** 1

### What I verified by reading the code

Every built-code claim I sampled held, and two of them I reproduced
independently rather than confirming.

**NFR14.83 is implementable, and I derived its three rows separately.**
Before reading the SQL the document now carries, I walked
`app/db/models.py` for every `ForeignKey("account.id", ondelete="CASCADE")`
and cross-joined the owning tables against `DISPOSITIONS`. Eight tables hold
a direct cascade to `account.id` — `profile`, `refresh_token`, `owner`,
`enrollment`, `hidden_batch_preference`, `payment_claim`, `reminder_event`,
`queued_submission` — and exactly three of those are `RETAIN_WITH_BASIS`:
`enrollment`, `payment_claim`, `queued_submission`. That is the same triple
the document names, reached from the ORM rather than from `pg_constraint`,
which is the stronger form of agreement. The `restricted_session` fixture in
`tests/db/test_governance.py` already executes raw `pg_tables` and
`information_schema.columns` reads, so a `pg_constraint` query needs no new
fixture and no new privilege. The requirement is implementable as specified.

**Counts.** `DISPOSITIONS` holds exactly 25 entries; 18 carry
`RetentionClass.LIFE_OF_ACCOUNT`; the split is 14 `RETAIN_WITH_BASIS`, 10
`HARD_DELETE`, 1 `ANONYMIZE_IN_PLACE`. `PUBLIC_ROUTES` holds exactly eight
tuples including both `/account-deletion` entries, and the comment's
"Exactly eight" is now asserted. `scripts/` holds `release_notes.py` and
nothing else. `Account.deleted_at` exists at `app/db/models.py:275` with the
docstring "Reserved for U11's deletion paths" and no writer. `job_heartbeat`
is a real table with a real upsert in `app/fees/commands.py`. All as stated.

**NFR14.98 closes the cross-purpose hole I raised, and closes it correctly.**
I had found that `issue()` writes the module constant `OTP_PURPOSE = "otp"`
with no purpose argument and that `verify()` selects the latest
`otp_request` for a phone with no `purpose` predicate, so a sign-in code
would have confirmed a deletion. NFR14.98 requires an explicit purpose on
issue, a filter on verify, and a deletion-specific purpose with its own
ceiling, and its verifier — present a sign-in code to the deletion
confirmation and assert refusal — is the test that distinguishes a filtered
lookup from an unfiltered one. Nothing further is needed on that point; what
remains are the two scope questions in the findings below.

**What I could not do:** no suite was executed. Like the lead, I read files.
I did not re-run the lead's `pg_constraint` query; my agreement with its
three rows comes from the independent ORM derivation above, which is
stronger evidence than re-running the same statement would have been.

### Findings

**Prior findings**

| ID | Now | Severity | Note |
|---|---|---|---|

**New findings**

| Severity | Location | Finding | Required action |
|---|---|---|---|
| Major | aidlc/spaces/default/intents/261022-remaining-slices/construction/releasing-safely/nfr-requirements/security-requirements.md > NFR14.83 | NFR14.83 is scoped to foreign keys pointing directly at `account.id`, and its SQL filters on `confrelid = 'account'::regclass`. The unit's own preamble names a fourth hazard the rule therefore does not cover: `owner` is `HARD_DELETE` and cascades to `batch`, which is `RETAIN_WITH_BASIS`, and from `batch` onward to `batch_subject`, `schedule_slot`, `session`, `exam` and `enrollment` — all `RETAIN_WITH_BASIS`. After `0007` fixes the three direct rows, this requirement returns zero while a teacher deletion still destroys retained records transitively. NFR14.84 blocks that path behaviourally, but the schema-level rule the unit calls its strongest mechanism does not see it | Extend NFR14.83 to the transitive closure: walk cascade edges from `account` through every intermediate table rather than stopping at depth one, and assert no `RETAIN_WITH_BASIS` table is reachable by an all-CASCADE path. Alternatively state explicitly that NFR14.83 is depth-one only and that the chain is covered solely by NFR14.84's behavioural block |
| Major | aidlc/spaces/default/intents/261022-remaining-slices/construction/releasing-safely/nfr-requirements/security-requirements.md > § 1, NFR14.98 and NFR14.80 | NFR14.98 correctly gives deletion its own purpose and its own ceiling, but it does not say whether deletion's number-scoped counter is *separate from* sign-in's or *shared with* it, and the answer decides whether a stranger can lock a victim out of their own account. `app/auth/ceilings.py` counts `PER_NUMBER_HOURLY = 3` / `PER_NUMBER_DAILY = 5` against the phone number, not the requester. If deletion reuses `ScopeKind.NUMBER_*`, an attacker posting a victim's number five times exhausts that victim's sign-in allowance for the day from an unauthenticated route. Signup already faced this and chose distinct `ScopeKind` members so "a signup refusal never consumes an OTP allowance and the reverse" | State in NFR14.98 that deletion's ceiling uses its own distinct `ScopeKind` members, following signup's precedent, so a deletion request cannot consume a sign-in allowance. Add a verifier asserting that exhausting the deletion ceiling for a number leaves that number still able to request a sign-in code |
| Major | aidlc/spaces/default/intents/261022-remaining-slices/construction/releasing-safely/nfr-requirements/security-requirements.md > § 1, NFR14.80 | Against a distributed attacker the per-number and per-IP ceilings do not bind, and the one that does bind has a side effect no requirement names. `ip_prefix_of` (`app/api/auth.py:74`) reduces the caller to a /24 prefix, so a botnet spanning prefixes never meets `PER_IP_HOURLY = 10`; per-number limits do not bind either, because the attack uses many numbers once each rather than one number many times. The only ceiling left is `GLOBAL_DAILY` (500, env-tunable) — and because it is global, an attacker who drains it denies **sign-in to every legitimate user** for the rest of the day, from a public route, while `fire_ceiling_alert` fires after the budget is already spent. NFR14.80's "the built ceilings, extended to this route" reads as sufficient and is not | Record this residual risk explicitly rather than leaving it implied by NFR14.80. State the accepted position — that the global ceiling is the only distributed-abuse bound, that reaching it degrades sign-in product-wide, and that the alert is detective rather than preventive — and add whichever mitigation the human chooses: a proof-of-work or CAPTCHA on the public deletion page, a deletion-specific global sub-ceiling that cannot consume the sign-in budget, or an explicit decision to accept it for closed testing |
| Minor | aidlc/spaces/default/intents/261022-remaining-slices/construction/releasing-safely/nfr-requirements/security-requirements.md > § 1 | An abandoned deletion attempt leaves residue that no requirement describes, and one piece of it outlives the account. An unverified attempt writes an `otp_request` row carrying the phone number (`HARD_DELETE`, `DAYS_7`) and increments `rate_limit_counter` rows (`HARD_DELETE`, `HOURS_48`), neither of which is reachable by the deletion path if the user never verifies. More pointedly, a *completed* deletion that removes the account leaves the attacker-or-user's `otp_request` rows holding that phone number for up to seven days after the account is gone — so NFR14.86's "the number is gone" is true of `account` and not of the database. The purge resolves it within the stated window, but the requirement as written claims more than the schema delivers at the moment of deletion | Either extend NFR14.86 to assert the number is absent from `otp_request` and every other phone-carrying table immediately after deletion, or state that the guarantee is "gone from `account` at once, gone everywhere within the retention window" and reconcile that with the policy's "within 30 days" promise |
| Minor | aidlc/spaces/default/intents/261022-remaining-slices/construction/releasing-safely/nfr-requirements/tech-stack-decisions.md > § 3, NFR21.3 | The refusal of a deletion audit table leaves no record whatsoever that a deletion occurred, and the stated fallback is inaccurate in one direction. `auth_audit_log` records OTP issue, verify-failure and verify-success events, so it shows a code was verified for a number — but after the deletion the number itself is gone from `account`, and the log's own disposition is `RETAIN_WITH_BASIS` at 12 months, so correlating a surviving log row to a deleted account is possible only by phone number, which is the identifying datum the refusal exists to avoid retaining. The reasoning is sound and the conclusion is defensible, but for a dispute ("you deleted my account and I never asked") there is currently nothing non-identifying to point at | Either record a minimal non-identifying fact — a salted or hashed number plus a timestamp and the route used, with its own disposition and retention entry — or state in the refusal that no record of a completed deletion survives and that a dispute is answerable only from the pre-deletion `auth_audit_log` rows, so the trade-off is on the page rather than implied |
| Minor | aidlc/spaces/default/intents/261022-remaining-slices/construction/releasing-safely/nfr-requirements/security-requirements.md > NFR14.86 and § 4 | The manifest and the published policy currently disagree with the human decision in a way these requirements do not name. `app/governance/dispositions.py` gives `account` `Disposition.ANONYMIZE_IN_PLACE` with a basis arguing a hard delete "would free the number for reuse"; `docs/legal/README.md:57` says `account` is "hard delete"; `docs/legal/PRIVACY.md:179` refers to "anonymised entries". The human decision for this unit is hard-delete. NFR14.86 asserts the number is gone, which is the consequence of the change, but no requirement states that the `account` manifest entry and its basis text must themselves change — and NFR14.88's generator reads that basis to produce the policy, so a stale basis generates a policy sentence contradicting the behaviour the tests assert | Add a requirement that `DISPOSITIONS["account"]` moves to `HARD_DELETE` with a rewritten basis, since the generated policy text is derived from that field and NFR14.89's generated-output assertion cannot catch a basis that is merely wrong rather than missing |
| Minor | aidlc/spaces/default/intents/261022-remaining-slices/construction/releasing-safely/nfr-requirements/tech-stack-decisions.md > § 4, NFR21.6 | NFR21.6's claim that the purge "is the first real test of D4's option-B enumeration decision" is fair and I verified its basis — `job_heartbeat` is built, `app/fees/commands.py` holds the upsert and the enumeration query at line 237, and D4's own requirements record that D5 registered no job. One qualifier is missing: D3's fee job and D4's session job already register heartbeats, so the mechanism has live producers. What is untested is specifically that a job added by a *later* unit is covered without editing the enumeration | Narrow the sentence to what is actually first — the first job registered after the enumeration was written — rather than the first test of the mechanism |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| none listed in dispatch | n/a | Verification was by direct reads of `app/db/models.py`, `app/governance/dispositions.py`, `app/contract/routes.py`, `app/auth/otp.py`, `app/auth/ceilings.py`, `tests/db/test_governance.py`, `docs/legal/README.md` and `docs/legal/PRIVACY.md` |
| independent cascade derivation | 3 rows, matching | `enrollment`, `payment_claim`, `queued_submission` derived from the ORM, agreeing with the document's `pg_constraint` query |
| disposition and retention counts | 25 / 18 / 8, all matching | Stated counts for dispositions, `LIFE_OF_ACCOUNT` entries and `PUBLIC_ROUTES` are correct |

### Summary

The requirements are specific, verifier-bearing and grounded in code that I
re-derived rather than took on trust — NFR14.83 is implementable exactly as
written and finds exactly the three cascades claimed, and NFR14.98 closes
the cross-purpose hole completely. The concerns worth the human's attention
before approving are all about residual scope: NFR14.83 stops at depth one
while the unit's own fourth hazard is transitive; NFR14.98 gives deletion
its own ceiling without saying it must be a *separate counter* from
sign-in's, which is what decides whether a stranger can lock a victim out;
and against a distributed attacker only the global ceiling binds, so
draining it degrades sign-in for every user — a residual risk the unit
should record as accepted rather than leave implied.

---

## Resolution - 2026-10-25

Every finding was closed in `security-requirements.md`,
`tech-stack-decisions.md` or `traceability.json`. Three needed a human
decision; one needed a query RUN against the live schema rather than a claim.

| Finding | Closed by |
|---|---|
| **Major** - reachability is depth-one and misses the `owner -> batch` chain | **NFR14.99.** The recursive query was written and RUN against the live schema: **eleven** `RETAIN_WITH_BASIS` tables are reachable, **seven only through `owner -> batch`**, which `0007` does not touch. This settles that BR1.6's refusal is **load-bearing**, not belt-and-braces |
| **Major** - deletion would reuse the sign-in ceiling scopes | **NFR14.100**, with its ambiguity closed: it is a new **counter**, not a new limit on a shared one, so five posts of a victim's number cannot lock them out of signing in. The verifier asserts a sign-in code **still issues** |
| **Major** - neither per-IP nor per-number binds a global DoS | **NFR14.102** [human, 2026-10-25]: a deletion-specific **global** sub-ceiling, 50 carved out of 500. `ip_prefix_of` reduces a caller to a /24 so spanning prefixes never meets `PER_IP_HOURLY`, and many-numbers-once-each never meets a per-number limit - leaving `GLOBAL_DAILY` the only bound, and draining it denies **sign-in to everyone** for the day |
| **Minor** - the manifest's *basis* would stay wrong after the disposition is fixed | **NFR14.101.** The generator reads the basis field; NFR14.89 asserts a disclosure is *present*, not that it is *true*. A generated document is only as true as the field it reads |
| **Minor** - `otp_request` holds the number for 7 days after deletion | **NFR14.86 corrected.** The honest claim is gone from `account` **at once**, gone everywhere **within its retention window** - seven days, inside the policy's thirty. The verifier now ties NFR14.86 to the purge rather than leaving each to assume the other |
| **Minor** - NFR21.3's fallback and NFR21.6's "first job" were both overclaims | Both corrected in `tech-stack-decisions.md`: there is **no usable record** that a specific person deleted (correlating `auth_audit_log` needs the phone number), and D3/D4 already register heartbeats - the real claim is *first job added **after** the enumeration was written* |

**The collected table in section 7 was extended to cover all five
review-added ids**, which it did not, and `traceability.json`'s note now
**derives** its status counts from the rows instead of stating them.
