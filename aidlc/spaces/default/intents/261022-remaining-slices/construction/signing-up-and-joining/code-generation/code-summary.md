# Code Summary — D1 `signing-up-and-joining`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices
**Date**: 2026-10-23

## What this unit closes

Before D1, **naming an account on an enrollment link was the grant**. A
teacher who mistyped one digit of a guardian's number handed a stranger a
guardian lens over a child's attendance and marks the moment that stranger
signed in. D1 makes acceptance the grant: a link carries a decision, and only
`accepted` resolves a lens.

The whole unit is that sentence plus the consequences of it being true.

## Sources

- [upstream] `functional-design/` — 26 rules BR1.1–BR7.2, 6 workflows, the migration as § 5
- [upstream] `nfr-design/` and `nfr-requirements/` — the lens hierarchy, the ceiling cascade, the three privacy layers
- [upstream] `inception/user-stories/stories.md` — the acceptance criteria in `traceability.json`
- [code] `app/`, `android/`, `migrations/`, `tests/`, read and modified 2026-10-23

---

## Verification

`make check` — **exit 0**, with Docker reachable, so the integration suite
genuinely ran rather than skipping silently.

| Gate | Result |
|---|---|
| `ruff format --check` | 153 files already formatted |
| `ruff check` | All checks passed |
| `mypy app` | Success: no issues found in 71 source files |
| Backend suite | **700 passed** (615 before D1; 85 new) |
| Backend line coverage | **91.37%** against the 80% floor |
| Money module branch coverage | **100.00%**, `fail_under = 100` |
| **Authorization layer branch coverage** | **100%** (145 statements, 20 branches, 0 missed) |
| Android unit tests | pass; 3 new test files |
| Kotlin quality gates | spotless, detekt, lint, ratchet — all pass |
| Kotlin line coverage | **35.26%**, up from 30.95%; floor raised to match |
| OpenAPI schema diff | committed schema matches generated |

The authorization figure is the one the practice asks for: `team.md` measures
that layer as **branch** coverage because lens resolution is pure branching
and line coverage on it is close to meaningless. It is 100% with no
exclusions.

### Phase A failed before Phase B, as required

The four test-first files were written against the pre-D1 tree and **run
red**, in two stages:

1. **Against the merged schema** — all 9 collectible tests failed with
   `TypeError: 'student_decision' is an invalid keyword argument for
   Enrollment`. Honest, but weak: it proves a column is absent, not that a
   predicate is wrong.
2. **After the migration landed and before the predicates changed** — the
   decisive run. 8 of 9 failed on the *logic*: `available_lenses` granted a
   student and a guardian lens to an account named only on `pending` links,
   `lens_summary` counted them, `remove_enrollment` refused to remove a
   mistyped seat whose stranger had signed up, and the roster showed it as
   claimed. `test_an_accepted_seat_is_still_refused` passed at that point,
   correctly — it is the positive control that stops a predicate refusing
   everything from passing the file.

That second run is the evidence the plan asked for. Both are reported because
the first alone would overstate what it showed.

---

## What was built

### The three things the brief named as most likely to be got wrong

**1. Both granting queries carry the predicate.** `_LENS_QUERY`
(`app/authz/resolve.py`) and `_SUMMARY_QUERY` (`app/authz/summary.py`) each
gained `decision = 'accepted'` on their student and guardian branches. They
are separate statements in separate modules reading the same columns, and
neither reads the other, so changing one alone is a silent half-fix with two
symmetrical failures. `tests/authz/test_acceptance_predicate.py` asserts both
in one file for that reason.

**2. Signing up is not accepting.** `app/accounts/service.py` links a new
account to seats a teacher already recorded and writes **no decision**. It is
an absence, so `tests/accounts/test_lookup.py:test_signing_up_leaves_an_existing_seat_pending`
asserts the link *was* made and both columns are still `pending` — without the
first half the test would pass against an implementation that never linked
anything, which is a different product rather than a safer one.

**3. The migration backfills conditionally.** `0004_acceptance_and_address.py`
adds both columns nullable with **no `server_default` at any point**,
backfills `accepted` where the link names an account and `pending` otherwise,
then sets `NOT NULL`. A plain `DEFAULT 'pending'` would have withdrawn a
working lens from every student already signed in. `tests/db/test_migration_0004.py`
stages at **`0003`** — the revision a staging deploy actually upgrades from,
and the first at which a dormant seat is expressible at all — and asserts both
backfill directions plus the absence of the default against
`information_schema`.

**Plus the two merged readers.** `remove_enrollment` and the roster's
`is_dormant` both read `student_account_id` as "claimed". Both now call one
shared `_nobody_accepted(record)` helper, which returns true only when
**neither** link has accepted. One function rather than two copies, because
two copies of a predicate that must agree is how they stop agreeing.

### Everything else

| Area | What landed |
|---|---|
| Schema | `0004`: two per-link decision columns (native enum, three values), `profile.address` |
| Authorization | `InvitationLens` as a fourth lens type; `app/authz/invitations.py` resolving it by its **own statement** returning a set |
| Signup | `app/accounts/service.py` — one transaction for account, profile and a conditional `Owner` |
| Abuse control | Two new `ScopeKind` members and a second cascade builder sharing one `_consume` implementation |
| Audit | `ACCOUNT_CREATED` and `SIGNUP_CEILING_BREACHED` as **named members**, no free-form field |
| API | `POST /v1/accounts`, the lookup, and four invitation routes |
| Privacy | `address` enrolled in `OWNER_PRIVATE_FIELDS`; 7 new adversarial probes |
| Android | `AcceptanceState`/`SignupRole`, 5 DTOs, signup and invitation state machines with their mappers, profile edit states |
| Strings | 43 new entries in **both** bundles, 96 each |

---

## Decisions made during implementation

These are choices the plan left open or that the code forced. Each is recorded
with what it cost.

### 1. Signup sets the row-level-security context to the account it just created

**The plan did not anticipate this and the first implementation failed on it.**
The `profile` policy's `WITH CHECK` requires the inserted `account_id` to equal
the transaction's bound account, and the request middleware binds the
*authenticated* account. Signup has none — the account being written was
created by this very transaction and nobody has verified a code for it yet — so
every signup was refused by the policy.

The policy was behaving correctly. `create_account` now calls
`set_account_context(session, account.id)` between the `Account` flush and the
`Profile` insert, which is what the policy *means* (a person may write their
own profile) rather than an exemption from it. The alternatives — writing the
row as the table owner, or adding a policy branch for an unbound session —
would each have weakened the one mechanism standing between a teacher and a
child's home address, and weakened it for every future writer rather than for
this one. The setting is transaction-local, so it is discarded at the commit
and cannot leak to the next request on a pooled connection.

### 2. The signup scope names are abbreviated

`signup_number_day` is 17 characters and `rate_limit_counter.scope_kind` is
`String(16)`. The first signup failed with a driver truncation error rather
than a ceiling decision. The names are now `su_number_day` and `su_ip_hour`,
and `tests/accounts/test_ceilings.py:test_every_scope_kind_fits_its_column`
asserts **every** member fits, reading the limit from the column's own declared
length rather than from a literal 16. Widening the column would have been a
migration against a table two cascades write concurrently, to buy one character
of readability.

### 3. The signup cascade has no global scope

Signup's cost to the project is the OTP it triggers, and that send passes
through the OTP cascade's own global daily ceiling immediately afterwards. A
second global counter would bound the same spend twice at two thresholds, so
the tighter one would silently become the real limit and the looser would read
as a control while governing nothing.

### 4. A separate `message_key` for a signup ceiling breach

Both cascades answer the same `TEMPORARILY_UNAVAILABLE` code, so a client
switches on one value. The key differs because a signup refusal shown on the
signup screen saying "we could not send your code" describes a step that never
happened. Written as two literal `message_key=` sites rather than a conditional
expression, because the key scanner matches that literal form — a key assembled
in an expression is invisible to it, and the published list would silently stop
covering it.

### 5. `app.accounts.*` added as a fourth mypy strict island

`team.md` names three. This is a deliberate addition: `app.accounts` creates
identities and is the only package permitted to write the decision columns, so
the two things it decides are "does this person exist" and "has this person
agreed". `disallow_any_explicit` is set, as on `app.authz.*`. Named in the same
commit as the package, because the drift this project recorded on 2026-10-22
was a deferral with a stated trigger and nothing watching for it.

### 6. Three allowlists and three stated counts moved

Each is a reviewable line by design, and each was moved deliberately:

- `PUBLIC_ROUTES` 6 → **8**, with the docstring count and both assertions
  updated. D1's two are the product's first unauthenticated *write* and its
  first deliberate disclosure.
- `LENS_EXEMPT_AUTHENTICATED` 2 → **3**. `GET /v1/invitations` reports which
  invitation lenses exist, on exactly `GET /v1/me`'s reasoning. The four
  per-seat routes each resolve an `InvitationLens`.
- `WRITE_PERMITTED` 2 → **4**. `app/api/accounts.py` was deliberately **not**
  added: it was checked against the gate and writes nothing, and listing a
  module that needs no exemption is how an allowlist stops describing what it
  permits.

### 7. Two stale user-facing strings corrected

`enrollment_remove_claimed` said "this student has signed in" and
`roster_status_dormant` said "hasn't signed in yet". D1 makes both false —
the predicate now reads the decision — so both were corrected in both bundles.
The `AuthAuditLog` docstrings claiming "five events" were corrected the same
way, since the project forbids a comment stating a count that nothing checks.

---

## Deviations from the plan

| Step | What differed | Why |
|---|---|---|
| 8 | Migration tests stage at `0003`, not `0001` | `0001` makes `enrollment.account_id` NOT NULL, so a dormant seat is not expressible there. Staging at `0001` would force the dormant case to be arranged through the post-migration schema, which is arranging the answer. `0003` is also the revision a deploy actually upgrades from. |
| 20 | The `PUBLIC_ROUTES` comment correction was already done | It was corrected on 2026-10-22 before D1 started. The count was moved 6 → 8 instead. |
| 24–26 | Compose composables not written; state machines, mappers and strings are | See **Gaps** below. |
| 32 | `app.authz.*` strict was already configured | Landed before D1 as the practice assigned. `app.accounts.*` was added instead. |

Four tests outside D1's own files were updated, each because D1 changed what
they assert about rather than because they were in the way: the two head-revision
literals, the health endpoint's revision, the `AuthEvent` vocabulary set, and
`Profile`'s exact column set. The last one gained a companion test deriving
`OWNER_PRIVATE_FIELDS` membership from `Profile`'s columns, so the next column
added fails the suite rather than slipping past it.

---

## Gaps — things this unit did not finish

### 1. The Compose screens — closed after the build

**This was reported as the largest gap and has since been closed.** The first
pass landed everything *beneath* the screens — state machines, pure mappers,
DTOs, both string bundles — and no `@Composable`. Against this unit's own
standard that was not a deliverable unit: [FR0.1] says a unit whose endpoints
work but whose screens do not exist is **not done**, and D1 exists precisely
because two earlier Bolts shipped working endpoints with two unstyled forms.

Now written, with Robolectric rendering tests for each:

| Screen | File | Tests |
|---|---|---|
| `O1` signup, 5 states | `feature/auth/ui/SignupScreen.kt` | 8 |
| `O4` invitations, 7 states | `feature/invitations/ui/InvitationsScreen.kt` | 9 |
| `O5` profile, edit half | `feature/profile/ui/ProfileScreen.kt` | 7 |

Each composable takes a UI state and callbacks and renders with **no
conditional depending on a domain value**, which is the practice for this
surface. The tests assert the rules that are only observable in the rendering
— the ones a mapper test cannot see because they are about what the screen
does *not* show:

- the already-added notice names **neither teacher nor batch** [BR2.3];
- the role is **locked, not hidden** [BR4.5];
- the two decline sheets say **opposite things about the fee** [BR5.2] — the
  guardian sheet asserts "fees are unchanged" and asserts the student wording
  is absent, which is the defect that pair exists to prevent;
- a declined seat **keeps its accept action** [BR5.4];
- the profile edit offers **no deletion control** — that is D6's [TC-19].

**A measurement defect surfaced while closing this**, and it is worth more
than the screens. Every Compose screen in the project measured 0 covered
lines, `AuthScreenKt` included, despite `AuthScreenTest` passing: JaCoCo
instruments the class, Robolectric drives composition through Compose's
runtime, and the screen's own bytecode records no hits. 573 of 1769 lines —
a third of the denominator — were permanently unreachable, so the Kotlin
figure tracked **how many screens existed** rather than what was verified.
That is exactly what `coverage.gradle.kts`'s own comment says its exclusions
exist to prevent; the exclusions simply did not reach the composables.

Fixed by completing the exclusion rather than lowering the floor. **The floor
rose, 35.26 → 45.84**, because removing unmeasurable lines from the
denominator tightens the ratchet rather than loosening it.

### 2. The Bangla layout check has five open rows

`docs/delivery/bangla-layout-check.md` now carries a D1 row for each of
`O1`, `O4`, both decline sheets and `O5`, each naming the exact string the
check must use. **All five are open.** The verifier the team chose is a manual
check on a device in Bangla locale, and nothing automated discharges it — the
sentence this project requires to be written rather than implied.

D1's new strings are now the four longest in the whole bundle.
`decline_guardian_body` at 125 characters is the longest string in the app and
sits in a bottom sheet, the tightest vertical space in the product. That is the
first row to check.

**The screens now exist, so the check is performable** — it was blocked on
gap 1 and is not any more. It still needs a person with a device in Bangla
locale, and nothing automated discharges it.

### 3. The student link is attached only through the guardian number

`_link_existing_seats` attaches a new account to seats recording its number as
`guardian_phone`. A **student** seat carries no typed-number column of its own —
a teacher creating one records a display name and, optionally, a guardian
contact — so there is nothing to match a student link against at signup. A
student whose teacher added them reaches their seat when the roster's number is
corrected, which is D2's screen.

This is a real limit on W2's step 5 and the design does not name a column that
would close it. Recorded so it is a decision rather than a later discovery.

### 4. No profile write endpoint

`ProfileUiState` models the edit half of `O5`, and no `PATCH /v1/profile`
exists. US1.5's AC1.5.1 is therefore `PARTIAL` in `traceability.json`. The
privacy obligations around the column — the owner-private field set, the
row-level-security policy, the schema-wide invariant — are all in force and
tested; what is missing is the route that writes it.

---

## What remains out of scope, unchanged from the plan

| Not built | Owner |
|---|---|
| Any money consequence of declining | **D3** [US1.14] — no ledger table exists |
| The roster screen showing split states | **D2** [AC1.10.7] |
| Account deletion, either path | **D6** [TC-19] — `PUBLIC_ROUTES` allowlists both, no handler |
| Staging enablement, pre-migration backup | **The human** |

## Assumptions & Open Questions

- **Assumed**: the decision columns are a native PostgreSQL enum rather than a
  check-constrained string. The design left this to code generation; a native
  type makes widening the set a visible migration rather than an edit to a
  constraint nobody reads.
- **Assumed**: signup's ceiling *values* (3 per number per day, 10 per IP per
  hour). The rules fixed that the counters are separate, narrowest-first and
  datastore-backed, not the integers. The per-number figure is deliberately
  tighter than the OTP path's, because a person signs up for a number once.
- **Open, and the human's**: whether `O4` is reachable from the lens switcher.
  The invitation lens is deliberately not one of the three a person chooses
  between, so the switcher is the wrong home for it. The mockups record this as
  open and D1's routes are agnostic to the answer.
