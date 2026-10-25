# Tech Stack Decisions — D6 `releasing-safely`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D6 `releasing-safely`
**Record**: 261022-remaining-slices

> **D6 adds no library, no service and no tool.** The generator is a script
> in a repository that already has one; the purge is a management command
> beside two that exist; the deletion paths are routes. **Everything this
> unit needs is built**, which is what a terminal `spec` unit should look
> like — if it needed new infrastructure, something earlier was deferred.
>
> The decisions worth recording are therefore **three refusals** [§ 3], and
> one choice about where generated text lives [§ 2].

> **`NFRx.y` IDs are GLOBAL.** D6's start above each base's high-water mark
> after D5. A bare `NFR17.9` or `NFR2.21` below is a **citation**.

## Sources

- [upstream] `functional-design/rules.md` — BR2.1, BR3.1, BR4.1
- [upstream] this stage's `security-requirements.md`
- [prior] `261016-.../inception/requirements-analysis/requirements.md` —
  NFR21 (no cached summary table), NFR23 (test-first for authorization)
- [team] `team.md` Code Style — conventional choices; the SDK admission note
- [code] read 2026-10-25: `scripts/release_notes.py`, `app/fees/commands.py`,
  `app/teaching/commands.py`, `Makefile`, `pyproject.toml`,
  `infra/modules/app/user_data.sh.tftpl`

---

## 1. Nothing is added

| Need | Built thing | Added |
|---|---|---|
| The policy generator | `scripts/` already holds `release_notes.py` | **nothing** |
| The purge | `app/fees/commands.py` and `app/teaching/commands.py` are the shape | **nothing** |
| Scheduling the purge | the cron entries in `user_data.sh.tftpl` | **nothing** |
| The deletion paths | FastAPI routes; both already in `PUBLIC_ROUTES` | **nothing** |
| OTP for the external route | `app/auth/otp.py`, `ceilings.py` | **nothing** |
| The manifest-driven tests | `tests/db/test_governance.py` is the pattern | **nothing** |

**NFR17.10** — D6 introduces **no third-party dependency**, so `team.md`'s
SDK admission note has nothing to record and the forbidden-identifier set is
untouched. **Verifier: the dependency lockfiles are unchanged, and the built
DEX scan and manifest allowlist are unaffected.**

**NFR17.11** — D6's new modules land under the **existing** strict mypy
islands or the global `disallow_untyped_defs`, and **add no island**. The
deletion path decides an authorization question — whether this caller owns
this account — but resolves it through `app.authz`, which is already strict.
**Verifier: `mypy app` clean, already a `make check` gate.**

---

## 2. Where generated text lives, which is the one real choice

**NFR16.6** — The policy generator writes **into the committed
`docs/legal/PRIVACY.md`** between explicit markers, and the gate regenerates
and compares [BR2.1, BR2.3].

Three options were available and the other two are recorded because each
looks reasonable:

| Option | Why not |
|---|---|
| Generate the **whole** document | Discards reviewed human prose — the contact details, the reasoning a parent actually reads, the plain-language summary. The policy would get worse to make the gate simpler |
| Generate to a **separate file** the policy includes | Markdown has no include. Play reads one URL, so something would have to assemble them, and that assembler is a second generator |
| **Markers in the committed file** | Chosen |

**The marker region is the unit of comparison, not the file** — which is
what lets a human improve the surrounding words without fighting the gate,
and is the property that makes the gate survivable rather than something
people route around.

**NFR16.7** — The generator is **deterministic**: same manifest, same bytes.
**Verifier: run it twice and compare.** A generator that emits a timestamp or
an unordered dict makes every build a diff and the gate becomes noise within
a week.

---

## 3. Three refusals

Each is the obvious addition for a unit about deletion and compliance, and
each is declined for a stated reason.

**NFR21.2 — No soft-delete flag, no `deleted_at` on the account.** The
column exists and becomes **unused** under a hard delete; this design does
not start writing to it. A soft delete would mean every query in the product
acquires an `AND deleted_at IS NULL` predicate, and the one that forgets it
serves a deleted user's data. **Verifier: no query in the deletion path
filters on `deleted_at`, and the column's stale docstring is corrected.**

**NFR21.3 — No deletion audit table.** Recording who deleted what, and
when, would mean keeping identifying data about a deletion **after** the
deletion — the exact thing being asked for.

**The fallback is weaker than an earlier draft implied, and the trade-off is
stated rather than glossed** [corrected 2026-10-25 after review]. That draft
said `auth_audit_log` "already records the OTP events that preceded it". It
does, and it survives 12 months — **but the account row is gone, so
correlating a log row back to a deleted account is possible only by phone
number, which is the identifying datum this refusal exists to avoid
retaining.** In practice there is **no usable record that a specific person
deleted their account.**

**That is accepted, and the reason is that the alternative is worse**: a
deletion audit retaining enough to be useful in a dispute is a deletion that
did not happen. What is lost is the ability to answer "did this person
delete, or were they never registered?" — a question whose answer is itself
personal data.

**Verifier: none; this is a recorded decision**, and it is named because
"log the deletion" is a reflex and the fallback sounds stronger than it is.

**NFR21.4 — No background job queue for deletion.** The deletion is
synchronous, which satisfies the policy's 30-day promise trivially. A queue
would add a dependency, a failure mode where a user believes they are
deleted and is not, and a reason for the promise to need a mechanism.
**Verifier: the deletion path commits before responding.**

---

## 4. The purge's shape

**NFR21.5** — The purge is a **management command in the app image**, run
by a cron entry, following `main_generate()`'s built shape exactly — no
required arguments, so it is also the recovery procedure a person runs by
hand. **Verifier: the command runs with no arguments; the cron entry is a
near-copy of the fee and session entries.**

**NFR21.6** — It **registers a heartbeat** under its own job name, so D4's
freshness enumeration covers it with no change to that mechanism
[D4's option B]. **Verifier: a `job_heartbeat` row appears under the purge's
name, and the freshness check reports on it without being edited.**

**This is the first job added AFTER the enumeration was written**, which is
the precise claim [corrected 2026-10-25 after review]. D3 and D4 both
register heartbeats, so the mechanism is not untested; what is new is a job
arriving *later* and being covered **with no change to the checker** — which
is the property option B was chosen for and the one D5 could not demonstrate,
having registered nothing.

---

## Assumptions & Open Questions

- **The purge's schedule is not set here.** Daily is the obvious cadence and
  the windows are 48 hours at the shortest, so daily is sufficient; the hour
  belongs with the cron entry in `infrastructure-design`, placed clear of
  the fee job's 02:00 UTC and D5's 01:00.
- **NFR16.7's determinism has no test until the generator exists.** Running
  it twice is trivial to assert and easy to omit, which is why it is a
  numbered requirement rather than a note.
- **`Account.deleted_at` stays and becomes unused** [NFR21.2]. Dropping it is
  irreversible and buys little; **its docstring — "Reserved for U11's
  deletion paths" — is corrected in `0007`'s change**, because a docstring
  describing a use that no longer exists is the claim-nothing-checks shape
  this project rejects.
- **No figure in this document was measured.** D6's code does not exist.
