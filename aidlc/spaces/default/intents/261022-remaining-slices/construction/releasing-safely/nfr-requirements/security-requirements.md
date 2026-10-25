# Security Requirements — D6 `releasing-safely`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D6 `releasing-safely`
**Record**: 261022-remaining-slices

> **D6 is the only unit whose central feature destroys data, and the only one
> with an unauthenticated route that does it.** Those two facts set the whole
> security shape: the dangerous operation is the *intended* one, and the
> attack surface is a phone number typed into a public page.
>
> **Three hazards are specific to this unit**, and each is already visible in
> the built code rather than hypothetical:
>
> 1. **Deletion as a weapon** — `POST /account-deletion` is public and keyed
>    on a phone number. Without ownership proof it deletes anyone's account
>    given a number that is not secret.
> 2. **Deletion as collateral** — the functional design found three
>    `CASCADE`s that destroy *retained* records, and a fourth chain where a
>    teacher's deletion erases every student's history [BR1.6].
> 3. **A public SMS endpoint** — issuing codes without the built ceilings is
>    a way to spend the project's entire messaging budget from a script.

> **`NFRx.y` IDs are GLOBAL.** D6's start above each base's high-water mark
> after D5, recomputed across the whole `aidlc/` tree. A bare `NFR14.77`,
> `NFR12.11` or `NFR10.22` below is a **citation**, never defined here.

## Sources

- [upstream] `functional-design/rules.md` — BR1.1–BR1.6, BR2.1–BR2.3,
  BR3.1–BR3.3, BR4.1–BR4.3, BR5.1–BR5.4
- [upstream] `functional-design/entities.md` §§ 2, 2a — the enumeration and
  the teacher chain
- [prior] `261016-.../inception/requirements-analysis/requirements.md` —
  NFR10, NFR11, NFR12, NFR14
- [prior] AC1.6.1–AC1.6.3, AC1.7.1–AC1.7.2, AC10.1.1–AC10.1.7, ADR-012
- [human] 2026-10-25 — hard-delete the account; `0007`'s three columns; a
  teacher owning any batch cannot delete
- [code] read 2026-10-25: `app/db/models.py`, `app/governance/dispositions.py`,
  `app/contract/routes.py`, `app/auth/ceilings.py`, `app/auth/otp.py`,
  `tests/db/test_governance.py`, `docs/legal/PRIVACY.md`

---

## 1. The public deletion route

**NFR14.78** — `POST /account-deletion` deletes nothing until ownership of
the number is proven by the **same OTP mechanism the app uses**. **Verifier:
a probe posting a valid number with no verified code, asserting zero rows
change.**

**NFR14.79** — The route's responses are **enumeration-resistant**: the
response to a number with no account is byte-identical to one with an
account, before verification. **Verifier: an equality assertion over the two
responses**, not two independent "is a 200" checks.

**This is the same oracle rule the OTP path already follows**, and it matters
more here: a deletion page that distinguishes "no such account" from "code
sent" is a free account-existence lookup for any phone number, on a public
URL a regulator requires to exist.

**NFR14.80** — The route consumes the **built** per-number, per-IP and
global SMS ceilings [NFR12, NFR12.1]. **Verifier: the built ceiling tests,
extended to this route** — not a new mechanism.

**An unauthenticated public endpoint that issues SMS without them is a way
to spend the project's entire messaging budget from a script**, and it would
be a door added in the last unit to a control built in the first.

**NFR14.100** — **Deletion gets its OWN ceiling scopes, not the sign-in
budget.** Added 2026-10-25 after review, and the reason is an attack the
shared budget makes free: `PER_NUMBER_HOURLY = 3` and
`PER_NUMBER_DAILY = 5` count **per number, not per requester**, so an
attacker with a list of numbers can spend each victim's daily allowance
from the public deletion page and **lock every one of them out of signing
in for the day** — without ever deleting anything.

**The precedent is built and this follows it.** Signup has
`ScopeKind.SIGNUP_NUMBER_DAILY` and `SIGNUP_IP_HOURLY` with
`SIGNUP_PER_NUMBER_DAILY = 3`, separate from the sign-in scopes **for
exactly this reason** [NFR12.1]. Deletion is the third consumer and has not
been given one.

**Verifier: exhaust the deletion scope for a number, then assert a SIGN-IN
code still issues for that same number** — the assertion that distinguishes
separate scopes from a shared counter. A test that only checks the deletion
route refuses passes against the shared budget.

**The number-scoped counter is separate, and this is the half that needed
saying** [clarified 2026-10-25 after review]. "Its own ceiling" is ambiguous
between a new *limit* on a shared counter and a new *counter*. It is a new
counter: deletion gets its own `ScopeKind` members, so **posting a victim's
number five times exhausts the deletion allowance and leaves their sign-in
allowance untouched.** Sharing `ScopeKind.NUMBER_*` would make the public
route a targeted lock-out — five posts and the victim cannot sign in for a
day. `check_and_consume_signup`'s docstring already states the principle:
*"a signup refusal never consumes an OTP allowance and the reverse."*

**NFR14.102 — deletion gets its own GLOBAL sub-ceiling, because the other
two do not bind a botnet.** Added 2026-10-25 after review, and the gap is
real rather than theoretical:

- `ip_prefix_of` reduces a caller to a **/24 prefix**, so an attacker
  spanning prefixes never meets `PER_IP_HOURLY = 10`.
- The attack is **many numbers once each**, so per-number limits never
  trigger either.

**That leaves `GLOBAL_DAILY = 500` as the only bound — and it is global**, so
draining it from an unauthenticated page **denies sign-in to every
legitimate user for the rest of the day**, with `fire_ceiling_alert` firing
only once the budget is already spent.

**NFR14.102**: deletion carries a **global daily sub-ceiling carved out of
the 500** (50), so exhausting the deletion route refuses further deletions
and leaves sign-in working [human, 2026-10-25]. **Verifier: drain the
deletion sub-ceiling, then assert a sign-in code still issues.**

**This follows the pattern NFR12.1 already set** rather than inventing one:
each purpose carries its own ceiling precisely so one consumer cannot
exhaust another's budget. D6 is the third consumer and the first that is
unauthenticated.

**NFR14.81** — A deletion **confirmation** code is single-use and expires on
the same terms as a sign-in code, and **cannot be replayed** to delete a
second time. **Verifier: present a consumed code, assert refusal and zero
further change.**

### NFR14.98 — a deletion code is its own purpose, and today it would not be

**Added 2026-10-25 after reading `app/auth/otp.py` rather than assuming the
mechanism could simply be reused.** Two facts make this a requirement rather
than a detail:

- **`issue()` takes no `purpose` argument.** It writes the module constant
  `OTP_PURPOSE = "otp"`, whose own docstring says a DEFAULT *"would let a
  second consumer arrive without anyone choosing its ceiling, which is the
  one control protecting the project's wallet."* **D6 is that second
  consumer**, and NFR12.1 already requires each purpose to carry its own
  ceiling.
- **`verify()` does not filter on purpose.** It selects the latest
  `otp_request` for the phone, full stop.

**So as built, a code issued for SIGN-IN would confirm a DELETION.** A
user who requested a login code, then visited the public deletion page,
could have their account destroyed by a code they believed was for signing
in — and an attacker who obtains any code by any means gets both powers from
one credential.

**NFR14.98**: `issue()` takes an explicit purpose, `verify()` filters on it,
and a deletion carries its own purpose value with its own ceiling [NFR12.1].
**Verifier: issue a code with the sign-in purpose, present it to the deletion
confirmation, assert refusal** — the test that distinguishes a filtered
lookup from an unfiltered one.

**This is the clearest instance in the unit of the project's own rule**: the
constant was written with a comment explaining exactly what would go wrong
when a second consumer arrived, and D6 is the unit where it arrives.

---

## 2. Deletion as collateral: what must survive

**NFR14.82** — No deletion removes a row whose disposition is
`RETAIN_WITH_BASIS`. **Verifier: the manifest-driven test of BR1.3, which
derives its table list from `DISPOSITIONS` rather than a literal** — so a
table added later with a contradicting cascade fails **without the test
being edited**.

**NFR14.83** — **No `CASCADE` to `account.id` exists against a table whose
disposition is `RETAIN_WITH_BASIS`.** This is the rule the functional
design's enumeration produced, and it is stated as a requirement because it
is checkable directly against the live schema rather than only through
behaviour.

**Verifier: a test that reads the live foreign-key constraints and the
manifest and asserts the intersection is empty.** That is strictly stronger
than testing a deletion, because it fails on a *newly added* contradicting
constraint before anyone deletes anything.

**The query was written and run against the live schema rather than
specified in the abstract** [2026-10-25], because a requirement whose
verifier might not be implementable is a requirement with no verifier:

```sql
SELECT c.conrelid::regclass::text AS tbl, a.attname AS col, c.confdeltype
  FROM pg_constraint c
  JOIN unnest(c.conkey) WITH ORDINALITY k(attnum, ord) ON true
  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
 WHERE c.contype = 'f' AND c.confrelid = 'account'::regclass
```

`confdeltype` is `c` for CASCADE and `n` for SET NULL. Run against the
migrated database through the existing `restricted_session` fixture, it
returns **15 foreign keys** and the intersection with `RETAIN_WITH_BASIS`
is exactly:

```
('enrollment',        'student_account_id')
('payment_claim',     'submitted_by_account_id')
('queued_submission', 'submitted_by_account_id')
```

**Three rows — the same three `0007` alters**, arrived at independently of
the enumeration that found them. The test is implementable, reads through
the restricted role like every other governance test, and **this run is its
own first evidence**: today it fails with three rows, and after `0007` it
must return none.

### NFR14.99 — and depth-one is not enough

**Corrected 2026-10-25 after review.** The query above filters
`confrelid = 'account'`, so it is **depth-one only** — and the chain this
unit's own § 2a describes is transitive. `owner` is `HARD_DELETE`, so it
*passes* NFR14.83 while everything hanging off it is `RETAIN_WITH_BASIS`.
**After `0007` the depth-one rule returns zero while a teacher's deletion
still destroys retained records.**

**NFR14.99**: the reachability is computed **transitively**, following
`CASCADE` edges from `account` to any depth. Written and run against the
live schema:

```sql
WITH RECURSIVE reach(tbl, path) AS (
  SELECT child, ARRAY['account', child] FROM fk WHERE parent='account' AND d='c'
  UNION ALL
  SELECT f.child, r.path || f.child FROM fk f JOIN reach r ON f.parent = r.tbl
   WHERE f.d='c' AND NOT f.child = ANY(r.path)
) SELECT DISTINCT tbl, path FROM reach
```

**It finds eleven distinct `RETAIN_WITH_BASIS` tables**, not three:

```
batch           via account -> owner -> batch
batch_subject   via account -> owner -> batch -> batch_subject
schedule_slot   via account -> owner -> batch -> schedule_slot
session         via account -> owner -> batch -> session
exam            via account -> owner -> batch -> exam
mark            via account -> owner -> batch -> exam -> mark
attendance      via account -> owner -> batch -> session -> attendance
enrollment      via account -> enrollment
fee_cycle       via account -> enrollment -> fee_cycle
ledger_entry    via account -> enrollment -> ledger_entry
payment_claim   via account -> payment_claim
```

**Seven of those are reachable only through `owner → batch`, which `0007`
does not touch.** That settles a question the design left implicit: **BR1.6's
refusal is load-bearing rather than belt-and-braces.** `0007` alone would
leave a teacher's deletion destroying seven kinds of retained record.

**Verifier: the recursive query, asserting the result set is empty for any
account that CAN be deleted.** Because a teacher owning batches cannot be
deleted at all [NFR14.84], the assertion is scoped to deletable accounts —
and the **path column is the diagnostic**, naming the chain rather than only
the table, so a failure says where the cascade runs.

**NFR14.84** — A teacher owning any batch **cannot delete their account**
[BR1.6]. **Verifier: a probe with one batch asserting refusal, and asserting
every row on the `owner → batch → enrollment` chain still exists.**

**The chain is `account → owner → batch → enrollment → six tables`, every
hop `NOT NULL` and `CASCADE`.** Each link is individually correct, which is
why nothing caught it for four units; the requirement makes the chain
**unreachable** rather than trusting six constraints to stay right.

---

## 3. What a deletion must prove it removed

**NFR14.85** — The deletion test asserts the **absence** of rows per table,
not the success of the call. **Verifier: for every `HARD_DELETE` table, zero
rows remain for that account; for every `RETAIN_WITH_BASIS` table, the rows
remain.**

**`team.md`: deletion features are the ones most reliably shipped broken,
because nobody tests the absence of data.** Every test anyone writes by
instinct asserts what is *there*.

**NFR14.86** — The phone number is **gone**, asserted by querying for it
rather than by querying the account id. **Verifier: after deletion, a lookup
by the original number finds nothing.**

**This is the one assertion the published policy's promise reduces to** —
*"Deleted permanently, within 30 days: Your phone number"* — and an id-keyed
assertion passes against a row whose id changed but whose number remains.

**But the number is not gone from the DATABASE at the moment of deletion,
and the requirement must say so** [corrected 2026-10-25 after review]. An
`otp_request` row carries the phone number and has a **7-day** retention; a
completed deletion leaves those rows behind for up to a week. `account` is
clean immediately; the database is not.

**The honest form, and it reconciles with the 30-day promise rather than
contradicting it**: the number is **gone from `account` at once, and gone
everywhere within its retention window** — seven days, comfortably inside
the thirty the policy states. **Verifier: assert `account` holds no such
number immediately, AND that the purge removes the `otp_request` rows
carrying it.** The second half is what ties NFR14.86 to the purge rather
than leaving each to assume the other.

**NFR14.87** — A second deletion request **succeeds and changes nothing**
[BR1.4]. **Verifier: delete, delete again, assert success and unchanged row
counts.** Implemented as an idempotent `DELETE` rather than
look-up-then-delete, which is a race between two requests.

---

## 4. The policy as a security artifact

**NFR14.88** — The policy's factual claims are **generated** from the
manifest, and drift fails `make check` [BR2.1, BR2.3]. **Verifier: the
regenerate-and-compare gate, the same shape as the built OpenAPI
schema-diff.**

**This is a security requirement rather than a documentation one**: the
policy is a statement to a regulator about children's data, and this unit
began by finding **three documents giving three different answers** to what
deletion does to a phone number.

**NFR14.89** — The generated text states that a **teacher-typed name
survives deletion** [ADR-012]. **Verifier: assert the disclosure against the
GENERATED output**, so the test fails if the generator stops emitting it —
not against the committed file, which would pass on a stale copy.

**NFR14.90** — **No factual claim about data handling lives outside the
generated region.** `docs/legal/README.md` currently carries a rival
per-table disposition list contradicting the manifest. **Verifier: the
generator owns that table too, or it is removed and the README points at the
policy.** A generator that owns one document does not stop a second
document contradicting the code.

**NFR14.101** — **The `account` entry's `disposition` AND its `basis` are
both corrected**, and the basis is the half nothing else catches. Added
2026-10-25 after review.

The manifest today reads `ANONYMIZE_IN_PLACE` with a basis *arguing against*
hard delete: *"a hard delete would free the number for reuse by a different
person while enrollments still reference the account."* The human chose hard
delete [2026-10-25], and **`0007` is what makes that argument obsolete** —
after it, no enrollment references a deleted account.

**NFR14.88's generator reads the `basis` field to produce policy text, and
NFR14.89 asserts a disclosure is PRESENT.** Neither catches a basis that is
merely **wrong**. So without this requirement the generated policy would
faithfully publish an argument the schema no longer supports — a generated
document is only as true as the field it reads.

**Verifier: the generated policy text contains no claim that the phone
number is retained**, asserted against the generated output. That is the
checkable form; "the basis is correct" is not.

---

## 5. The invariants D6 asserts against the final schema

D6 is typed `spec`. These are **built** and the obligation is to run them
once more, over the completed product.

| Invariant | Mechanism | ID |
|---|---|---|
| Refusals disclose nothing | the built error-contract test | **NFR14.91** |
| No profile field to a teacher | `app/contract/privacy.py` | **NFR14.92** |
| Every route resolves a lens | the route-enumeration test | **NFR14.93** |
| No trusted lens hint | built in D1 | **NFR14.94** |
| Governance complete, both directions | `tests/db/test_governance.py` | **NFR14.95** |

**NFR14.93's `PUBLIC_ROUTES` stays at eight.** Both `/account-deletion`
entries were pre-declared in D1; **D6 lands handlers against entries that
already exist** and adds none.

**NFR14.95's second direction is the one that matters at the end of a
project**: a disposition naming a table that no longer exists is what a long
sequence of units produces, and a one-directional check misses it.

---

## 6. The purge as an attack surface

**NFR14.96** — The purge deletes **nothing** whose retention class is
`LIFE_OF_ACCOUNT` — 18 of 25 tables, including every attendance, mark and
ledger row. **Verifier: a fixture aged two years in a `LIFE_OF_ACCOUNT`
table survives a purge.**

**The dangerous implementation is the natural one**: iterate all tables,
apply a default window to those without an explicit one. That would delete
the product's entire history on its first run.

**NFR14.97** — The purge runs with the same restricted non-superuser
`APP_ROLE` as everything else, and **is not an administrative path**.
**Verifier: the built meta-test, unchanged.** Stated because a maintenance
job is exactly where a broader role gets used for convenience.

---

## 7. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| Ownership proven before deletion [NFR14.78] | A probe with no verified code | yes |
| Enumeration-resistant responses [NFR14.79] | Equality over two responses | yes |
| Ceilings apply to the public route [NFR14.80] | The built ceiling tests, extended | yes |
| A consumed code cannot be replayed [NFR14.81] | A replay probe | yes |
| Nothing `RETAIN_WITH_BASIS` is removed [NFR14.82] | The manifest-driven test | yes |
| **No contradicting CASCADE exists** [NFR14.83] | **A live-constraint-vs-manifest test** | yes |
| A teacher with batches cannot delete [NFR14.84] | A probe plus a chain assertion | yes |
| Absence asserted per table [NFR14.85] | The same manifest-driven test | yes |
| The number is gone [NFR14.86] | A lookup by number, not by id | yes |
| Idempotent deletion [NFR14.87] | Delete twice | yes |
| Policy drift fails the build [NFR14.88] | Regenerate and compare | yes |
| The ADR-012 disclosure is present [NFR14.89] | Asserted on generated output | yes |
| No facts outside the generated region [NFR14.90] | **Review, plus removing the rival table** | **partly** |
| The five built invariants [NFR14.91–95] | Existing gates, unchanged | yes |
| `LIFE_OF_ACCOUNT` never purged [NFR14.96] | An aged fixture | yes |
| The purge uses `APP_ROLE` [NFR14.97] | The built meta-test | yes |
| A sign-in code cannot confirm a deletion [NFR14.98] | Issue for sign-in, present at deletion, assert refusal | yes |
| **Reachability is transitive, not depth-one** [NFR14.99] | **The recursive query over live constraints** | yes |
| Deletion's number counter is its own [NFR14.100] | Exhaust deletion, assert sign-in still issues | yes |
| The manifest **basis** is corrected too [NFR14.101] | Asserted on the generated text, not the enum | yes |
| Deletion has its own GLOBAL sub-ceiling [NFR14.102] | Drain it, assert sign-in still issues | yes |

**Every row added after review is automated**, which is worth stating because
the three that matter most — NFR14.99, NFR14.100 and NFR14.102 — each assert
that something **still works** after an attack, and an assertion that a route
merely *refuses* passes against the defect in all three.

**One row is only partly automated**, and it is named rather than rounded up:
nothing mechanically prevents a factual claim being written outside the
generated region. Removing the rival table shrinks the surface; it does not
close it.

---

## Assumptions & Open Questions

- **NFR14.83 is the strongest requirement in this unit and it is new.** No
  earlier unit asserts a property of the *schema's constraints* against the
  manifest. It is cheap — both sides are already readable — and it is what
  makes the three cascades found here the last three rather than the first
  three.
- **The 30-day promise is satisfied by a synchronous delete.** If deletion
  ever becomes queued, the promise acquires a mechanism it does not have.
- **`guardian_phone` on the enrollment survives deletion** — a phone number
  the teacher typed, covered by ADR-012 and disclosed by the policy. It is
  the sharpest edge of the disclosure and NFR14.89's test keeps it stated.
- **No threat model document exists for this product.** Searched both
  records' `inception/` trees and `docs/`. These requirements derive from the
  stated constraints and the built gates, which is the basis D1–D5 used.
- **I could not execute any suite for this stage.** Every claim about a built
  gate is from reading the file, each cited by path.
