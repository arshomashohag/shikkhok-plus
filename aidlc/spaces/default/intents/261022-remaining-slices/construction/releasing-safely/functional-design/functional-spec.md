# Functional Specification — D6 `releasing-safely`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D6 `releasing-safely`
**Record**: 261022-remaining-slices

> **D6 is terminal and release-blocking, and its work is almost entirely
> about absences**: a row that must be gone, a policy claim with no
> generator, a retention class nothing enforces, a cascade nobody noticed.
> **Absences are what no test asserts unless someone writes it deliberately**,
> which is why `team.md` says deletion features are the ones most reliably
> shipped broken.
>
> **Four things were found by reading the built code before designing**, and
> each changed what this unit must do:
>
> | Found | Consequence |
> |---|---|
> | Three documents disagree about the phone number [§ 1] | A human decision, taken |
> | **A student's deletion cascades the enrollment away** [§ 2] | Migration `0007`, **three columns** |
> | **A teacher's deletion erases every student's history** [§ 2a] | Deletion refused while batches exist |
> | "The policy is generated" — **no generator exists** [§ 3] | D6 builds it |
> | `RetentionClass` is referenced only by itself [§ 4] | The purge is new behaviour |

## Sources

- [upstream] this stage's `entities.md` and `rules.md` — 18 rules
- [upstream] `inception/units-generation/unit-of-work.md` — D6's scope
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.6,
  US1.7, US10.1
- [prior] `261016-.../inception/user-stories/stories.md` — the AC rows
- [prior] ADR-003, ADR-004, ADR-009, **ADR-012**
- [human] 2026-10-25 — hard-delete the account; `0007` makes **three** links
  `SET NULL`; **a teacher owning any batch cannot delete their account**
- [code] read 2026-10-25: `app/db/models.py`, `app/governance/dispositions.py`,
  `app/contract/routes.py`, `app/auth/`, `docs/legal/PRIVACY.md`,
  `docs/legal/README.md`, `scripts/`, `Makefile`

---

## 1. The conflict this unit inherited, and the decision

Three documents answered the same question three ways:

| Source | What happens to the phone number |
|---|---|
| `app/governance/dispositions.py` | **`ANONYMIZE_IN_PLACE`** — "a hard delete would free the number for reuse by a different person while enrollments still reference the account" |
| `docs/legal/README.md` | **"hard delete"** |
| `docs/legal/PRIVACY.md` | **"Deleted permanently, within 30 days: Your phone number"** |

**The policy is what a regulator reads**, and the human chose it
[2026-10-25]: **hard-delete the account row.** `dispositions.py` is updated to
match rather than left to disagree [BR1.1].

**That decision creates an obligation rather than removing one.** The basis
the manifest carried names a real hazard, and § 2's migration is what closes
it — a point worth holding onto, because `0007` reads at first like a fix for
one thing and serves two.

---

## 2. The cascade defect

### What is built

```
Enrollment.student_account_id   -> account.id   ondelete="CASCADE"
Enrollment.guardian_account_id  -> account.id   ondelete="SET NULL"
```

**Verified by reading the model**: six foreign keys point at
`enrollment.id`, **all six `CASCADE`** — `fee_cycle`, `payment_claim`,
ledger entries, attendance, marks, attendance submissions.

### What it means

| Who deletes | Today | AC1.6.2 and the policy require |
|---|---|---|
| A guardian | link nulled, enrollment survives | survives ✓ |
| A **student** | **enrollment deleted, and six tables with it** | survives ✗ |

A student's deletion would remove the teacher's **entire record of that
seat** — every mark, every attendance mark, a settled fee ledger — in one
statement. **The policy tells the user those entries are kept.**

### The fix

**Migration `0007` makes `student_account_id` `SET NULL`** [human,
2026-10-25], symmetric with the guardian column.

**And a second column, found by asking whether anything else re-links.**
`payment_claim.submitted_by_account_id` is also `CASCADE`, so a student's
deletion would still destroy their payment claims -- the record of a payment
they submitted, with its transaction id. The ledger survives
(`created_by_account_id` and the claim link are both `SET NULL`), so balances
are intact; the claim row and its evidence are not. **`0007` carries both
changes** [human, 2026-10-25].

**All fifteen `account.id` references were checked** -- eight `CASCADE`,
seven `SET NULL`. After these two, the remaining six cascades are correct,
and the test that distinguishes them is worth stating: **a cascade is right
when the row exists only for the account being deleted, and wrong when the
row is someone else's record that merely names it.** `reminder_event` and
`queued_submission` cascade correctly because they are teacher-authored --
they die with the teacher's account, not a student's.

**The code-only alternative was declined**, and the reason generalises: a
rule enforced by remembering is enforced once. Nulling the column in the
deletion path leaves the destructive default one forgotten line away, and any
*other* path that deletes an account — a repair script, an admin tool, a
fixture — still cascades.

**Neither `ondelete` is wrong alone**, which is how this survived four units
and two reviews. A cascade is right for a row that exists only for its
parent. **The pair is wrong together**, because one user action means two
different things depending on which role the account holds — and a per-column
default is invisible at the row level.

---

## 3. The policy, and the claim that had no mechanism

`docs/legal/README.md` is headed:

> **The policy is generated from the schema, not written beside it**

**No generator exists.** Checked across `app/`, `scripts/` (which holds only
`release_notes.py`), `tests/` and the `Makefile`: nothing references
`PRIVACY.md`. The current text was hand-written *against* the schema and
verified by a five-row table of manual checks — careful work, and not what
the heading claims.

**This is the project's own standing rule, on its most sensitive document**:
where a comment states a fact, the fact is a claim, and either something
asserts it or the claim comes out.

**D6 builds the generator** [BR2.1], and three properties make it worth more
than the sentence it replaces:

1. **The factual table is generated; the prose is not.** The contact address,
   the reasoning a parent reads, the plain-language summary are human-written
   and stay. **What is generated is which data is deleted, which is kept, and
   for how long** — the part that can silently stop matching the code.
2. **The disclosure is asserted** [BR2.2]: that a teacher-typed name survives
   deletion [ADR-012]. A person who declined a seat still appears in a
   teacher's record under a name they did not choose, and a policy omitting
   that is a false statement to a regulator about children's data.
3. **Drift fails `make check`** [BR2.3], the same shape as the built OpenAPI
   schema-diff gate — and for the same reason: a committed artifact derived
   from code must be regenerated in the change that alters its source.

**The three-way conflict of § 1 is what this gate would have caught**, which
is the argument for it stated as evidence rather than principle.

---

## 4. Retention, enforced for the first time

**`RetentionClass` is referenced only by its own definition** — checked
across `app/` and `tests/`. Seven tables carry finite windows:

| Window | Tables |
|---|---|
| 7 days | 3 |
| 12 months | 2 |
| 48 hours | 1 |
| until expiry + 30 days | 1 |
| **life of account** | **18** |

**Nothing deletes anything today.** So the purge is **new behaviour**, not a
scheduled version of something existing — and the two rules that matter are
about not doing too much:

- **BR4.2**: `LIFE_OF_ACCOUNT` is never purged. Eighteen of twenty-five
  tables, including every attendance, mark and ledger row. **The dangerous
  implementation is the natural one** — iterate all tables, apply a default
  window to those without an explicit one — and it would delete the product's
  entire history on first run.
- **BR4.1**: idempotent and chunked. **The honest failure of a retention job
  is not deleting too much; it is dying halfway and being re-run.** An
  unchunked `DELETE` over a year of `otp_request` rows locks the table on the
  single small instance this product runs on.

---

## 5. The two deletion paths

```
In-app:    Settings -> Delete account -> confirm by signing in
External:  GET  /account-deletion   (the page, no session)
           POST /account-deletion   (after OTP ownership proof)
```

**Both already exist in `PUBLIC_ROUTES`**, declared in D1 with the comment
*"pre-declared D6 scope"*. **D6 lands handlers against entries that exist**,
so the asserted count of eight is unchanged [BR3.2].

**Both paths call one deletion function** [BR3.1], and the test compares the
surviving row sets rather than asserting each against a hand-written
expectation — because the route that drifts is the external one, used less,
tested less, and the one Play requires.

**The external route consumes the OTP ceilings** [BR3.3]. An unauthenticated
public endpoint that issues SMS without them is a way to spend the project's
entire messaging budget from a script — the exact attack the ceilings exist
for, through a door added later.

---

## 6. What D6 asserts rather than builds

D6 is typed `spec`, and this is what that means: most of US10.1 is already
enforced by mechanisms built in earlier units.

| Invariant | Mechanism | D6's job |
|---|---|---|
| Refusals disclose nothing [AC10.1.1–4] | the built error-contract test | run it against the final schema |
| No profile field to a teacher [AC10.1.5] | `app/contract/privacy.py` | the same |
| Every route names a lens [AC10.1.7] | the route-enumeration test | the same |
| No trusted lens hint [AC10.1.6] | built in D1 | the same |
| Governance complete [BR5.4] | the governance pair | the same, in **both** directions |

**Stating these as rules rather than omitting them is what makes "the
invariants hold against the final schema" a checked claim.** The second
direction of the governance test matters most at the end of a project: a
disposition naming a table that no longer exists is what a long sequence of
units produces.

---

## 7. Definition of done

- `make check` green, including the **new** policy-drift gate [BR2.3].
- **Deletion asserted as absence**, enumerated from `DISPOSITIONS` [BR1.3] —
  a table added later with no deletion handling fails the test **without the
  test being edited**.
- **BR1.2 asserted for BOTH roles.** A test using only a guardian passes
  against the defect.
- `0007` applied; `student_account_id` is `SET NULL`.
- The generated policy contains ADR-012's disclosure [BR2.2].
- The purge demonstrated **idempotent** (a second run deletes zero) and
  **bounded** (a batch size, not "all matching rows").
- `PUBLIC_ROUTES` still **8**; `dispositions.py` still **25**.
- Data Safety form content and Play declarations written against the
  **generated** policy.

---

## 8. What D6 does not do

No new table. No new column — `Account.deleted_at` already exists and becomes
unused. No `PUBLIC_ROUTES` entry. No new disposition kind or retention class.
No new error class. No change to any earlier unit's behaviour except the one
constraint `0007` alters.

---

## Assumptions & Open Questions

- **`Account.deleted_at` becomes unused** under a hard delete, and its
  docstring — *"Reserved for U11's deletion paths"* — becomes wrong. The
  column stays (dropping it is irreversible and buys little); **the docstring
  is corrected in `0007`'s change**.
- **The generated region of the policy is marked, and the test compares only
  that region.** Generating the whole document would discard reviewed human
  prose. Where the markers go is implementation; **that there are markers is
  the rule**.
- **The generator's first output must be compared against the existing text
  rather than replacing it silently.** The current wording was reviewed by a
  human; the generator's has not been, and a diff is how a person checks that
  nothing true was lost.
- **`guardian_phone` on the enrollment survives deletion.** It is a phone
  number the teacher typed, covered by ADR-012 and disclosed by the policy —
  **the sharpest edge of the disclosure**, and BR2.2's test is what keeps it
  stated.
- **The 30-day promise is satisfied by a synchronous delete**, which this
  design builds. A queued deletion would give that promise a mechanism it
  does not currently have.
- **Every count here was read from the code on 2026-10-25**: 25 dispositions,
  8 public routes, **6 foreign keys to `enrollment.id`, all CASCADE**, 7
  finite retention windows, 18 `LIFE_OF_ACCOUNT`. None was measured by
  running anything, because D6's code does not exist.
