# Code Summary — `batches-and-enrollment` (U4)

**Stage**: code-generation (3.5)
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

> **26 of 28 steps built.** Steps 22-23 (the Room cache) are
> **deferred with a reason, not dropped** -- see §G. `make check` green: **553 backend tests,
> 88 Android tests**, 92.29% backend coverage against the 80% floor,
> money module still 100% branch. Ruff and mypy clean. Counts read from
> the runners rather than carried forward from an earlier commit.

## Sources

- [upstream] `code-generation/code-generation-plan.md`
- [upstream] `code-generation/unit-test-instructions.md`
- [upstream] `functional-design/rules.md`, `entities.md`
- [upstream] `nfr-design/`, `infrastructure-design/`
- [team] `## Testing Posture`, `## Code Style`
- [project] `## Forbidden`, `## Mandated`

---

## A. What this Unit changed about the system

| Change | Why it matters beyond this Unit |
|---|---|
| `enrollment` reshaped to carry **both links on one row** | The guardian's seat IS the child's seat, which is the question U3's `role` column could not answer [BR5.0] |
| **No `role` column anywhere** | U3 had one; `0002` drops it, so the shape can no longer express a stored role |
| Per-**link** erasure markers | One flag made a guardian's erasure block a student who never claimed that seat |
| The first real **money columns** | Both gates stopped being vacuous, and both had holes |
| The first **two-party** surface | Every isolation claim before this was about a mechanism, not an outcome |

---

## B. The three failure modes the plan named, and how each failed loudly

Each was verified by **building the wrong implementation**, not by
reasoning about it.

| Wrong implementation | Tests that fired |
|---|---|
| A fold that deletes guardian rows it cannot place | The guard refuses zero and two students; one folds and the link survives |
| A removal check reading the null column alone | **3 of 6** removal tests |
| A query-count fixture too small to see N+1 | 4 queries for 2 seats, **27 for 25** |

And three more the plan did not anticipate:

| Wrong implementation | Tests that fired |
|---|---|
| A roster scoped on a parameter rather than the lens | **3 of 4** isolation tests |
| Guardian resolution keyed on the child | **1 of 4** — exactly the one built for it |
| A due-date comparison for `inactive_from` | **3 of 8** period tests |

> **One injection was itself wrong.** My first attempt at the due-date
> defect passed all 8 tests, because the expression I wrote was
> equivalent to the correct rule for those inputs. A defect injection
> has to be checked against what it claims to model.

---

## C. Five defects found that no upstream artifact predicted

These are the ones worth carrying forward, because each is a **class**
rather than an instance.

### C.1 `0001`'s grant covered only the tables that existed then

`GRANT ... ON ALL TABLES` is not a standing rule. Every table `0002`
created was unreadable by the application role — and, worse, **invisible
to it in `information_schema`**, which is where the governance gates
look. The money assertion reported `enrollment.fee_amount` and silently
skipped `batch.default_fee` until the grant existed.

> **A control that quietly narrows is worse than one that fails.** Two
> new gates now assert the restricted role can read and see every live
> table.

### C.2 The money gate could not see a nullable money field

A nullable field emits `{"anyOf": [{"type": "number"}, {"type":
"null"}]}` with no top-level `type`, so a check reading `node["type"]`
saw nothing. This project's first real money column, `fee_amount`, is
**nullable by design** — null means inherit, zero is a waiver — so the
one shape the project actually uses for money was the one shape the gate
could not see. U3 carried no money, so U4 is the first Unit able to
expose it.

That fix also made the allowlist load-bearing: before it, the real app
reported nothing with *or* without the exemptions.

### C.3 No route had ever read a Bearer token

U3 shipped `verify_access_token` and three routes that did not need it —
two public, one authenticating by refresh token in the body. U4's first
authenticated lensed route found `request.state.account_id` never
populated, and every authenticated request returned 403.

### C.4 The Android suite was not in `make check`

It existed and passed, but nothing gated it, so an Android regression
would not have blocked a merge. `team.md` requires **one entrypoint**,
local and in CI, because a gate reproducible only by pushing is a gate
that gets bypassed.

### C.5 A message key could ship with no string on either side

The backend is correct when it names a key; the client is correct when
it falls back to a generic message. Together they produce an app showing
*"Something went wrong"* for a specific, actionable error — which looks
like a working error message and is therefore **never reported**.

> The backend now publishes `message-keys.json` and asserts it matches
> its own raise sites; the Android suite reads the same file. Neither
> surface can drift alone.

---

## D. Decisions taken during construction

| Decision | Why |
|---|---|
| `enrollment.batch_id` gains **no** foreign key | Every row surviving from `0001` points at a batch that cannot exist yet, so the constraint would refuse every populated database and pass only on empty ones |
| `BatchNotFound` is an `AuthorizationError` with **404** | A 403 for a real batch and 404 for an invented one is an existence oracle; a 400 would call a well-formed request malformed |
| `GuardianLens.child_enrollment_id` becomes optional | The first authenticated request has not selected a child — the selection list is what it renders |
| The Kotlin money serializer moves to the **type** | A per-field annotation works until one DTO forgets it, and a forgotten one is invisible in review because the field still renders |
| U3's write-ban is **inverted**, not deleted | U4 owns these tables, so one module is allowlisted explicitly and a test asserts the allowlist holds exactly one entry |

---

## E. What this Unit did not build

| Not built | Owner |
|---|---|
| Fee arithmetic, carry-forward, waiver | U7 — U4 ships the anchor it charges against |
| Attendance, sessions, exams, marks | U5, U6 |
| Either deletion path | U11 — U4 ships the columns erasure writes |
| An admin surface | None in V1; `Owner`'s readable field subset is stated, not enforced |
| A Retrofit client | No HTTP client is wired on Android yet — see §F |
| The Room cache | Deferred; see §G |

---

## F. Carried open items

1. **The device leg has never been run.** No HTTP client is wired on
   Android, no real SMS has been sent, and the seed script was never
   executed before being deleted. Both B3's checkpoint and this Bolt
   were verified on their test suites alone.
2. **The deploy ordering is untested against a real deployment.** The
   migration's fold guard and the grant step are correct and tested;
   the six-step ordering in `infrastructure-specification.md` §B has
   not been exercised end to end.
3. **The Android toolchain has two unresolved version signals.** The
   Gradle plugin warns it is tested to `compileSdk 35` while the
   project targets 36, and KSP cannot parse the existing sources (§G).
   Both need settling before the Room cache or any annotation
   processor can land. Recheck at packaging.
4. **`guardian_phone` edits are not audited** — a cost decision with a
   concrete revisit trigger at U7's first send to that number.

---

## G. Steps 22-23 are deferred, and the reason is a toolchain failure

The plan called for Room entities mirroring the DTOs plus a
`fetched_at` timestamp, and a test asserting no entity derives a field.
**Neither was built**, and the honest reason is worth recording rather
than quietly closing the step:

1. **KSP would not compile the existing sources.** Adding Room needs
   KSP, and with `ksp 2.0.21-1.0.25` the processor reported
   `Closing bracket expected` on **eight files this Bolt never
   touched** — all of them valid Kotlin that the Kotlin compiler
   accepts. That is a toolchain mismatch, and it sits next to the
   already-open warning that the Android Gradle plugin is tested to
   `compileSdk 35` while this project targets 36.

2. **The cache has nothing to cache yet.** There is still no HTTP
   client on Android, so a Room layer would be written against a
   repository that does not exist, tested against fixtures, and first
   exercised whenever the client lands.

> Destabilising the Android toolchain to add a cache with no data
> source, in the Bolt that just made the Android suite a merge gate,
> is the wrong trade. **The obligations survive the deferral**: the
> staleness contract is already built and tested — `RosterUiState`
> carries `fetchedAtLabel`, the screen renders it, and a Compose test
> asserts live data shows no notice. What is missing is the storage
> behind it.

Steps 24 and 25 — the screens, both language bundles, and
`fetched_at` being rendered rather than merely stored — **are** built.

---

## Assumptions & Open Questions

**None.** [assumption] The seed script's rows may never have existed in
any environment, since the device leg was never run. The migration's
fold guard makes the deploy correct either way rather than depending on
which happened.
