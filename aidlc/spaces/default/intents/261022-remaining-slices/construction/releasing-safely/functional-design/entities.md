# Entities — D6 `releasing-safely`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D6 `releasing-safely`
**Record**: 261022-remaining-slices

> **D6 creates no table and ships one migration, and that migration exists
> because of a defect rather than a feature.** `Enrollment.student_account_id`
> is `ondelete="CASCADE"` while `guardian_account_id` is `ondelete="SET NULL"`
> — so under the deletion this unit builds, **a student deleting their account
> would destroy the teacher's attendance, marks and settled fee history for
> that seat**, while a guardian doing the same would not. § 2 is that finding.
>
> **The rest of this unit is about making existing declarations enforceable.**
> Three things are written down and checked by nothing:
>
> | Written | Enforced by |
> |---|---|
> | 25 dispositions in `dispositions.py` | the governance test — **yes** |
> | 7 finite retention windows | **nothing. `RetentionClass` is referenced only by its own definition** |
> | "The policy is generated from the schema" | **nothing. No generator exists** |
>
> D6 is the unit that turns the second and third into mechanisms.

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` — D6's scope
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.6,
  US1.7, US10.1
- [prior] `261016-.../inception/user-stories/stories.md` — AC1.6.1–AC1.6.3,
  AC1.7.1–AC1.7.2, AC10.1.1–AC10.1.7
- [prior] ADR-012 — a declined seat keeps the teacher-typed name
- [human] 2026-10-25 — **hard-delete the account row**, honouring the
  published policy; **migration `0007` makes THREE links `SET NULL`**; and
  **a teacher owning any batch cannot delete their account**
- [code] read 2026-10-25: `app/db/models.py` (`Account`, `Enrollment`, the
  six tables cascading from `enrollment`), `app/governance/dispositions.py`,
  `app/contract/routes.py`, `docs/legal/PRIVACY.md`, `docs/legal/README.md`,
  `scripts/`, `Makefile`

---

## 1. Tables, and the one schema change

| Table | D6 does |
|---|---|
| `account` | **hard-deletes the row** [human, 2026-10-25] |
| `profile` | hard-deletes — self-authored, owner-private |
| `otp_request`, `refresh_token`, `verify_attempt` | hard-deletes |
| `enrollment` | **keeps the row, clears the links** — § 2 |
| attendance, marks, fee entries, ledger | **keeps, retained with basis** |
| `auth_audit_log` | keeps 12 months; holds no name or code |

**One migration, `0007`, and it alters THREE constraints** [§ 2], two of
which must also become nullable. It drops them by their **real** names,
which are not the names the model implies. No new table,
no new column — `Account.deleted_at` already exists, its docstring reading
*"Reserved for U11's deletion paths"*, and U11 maps forward to this unit.

**`dispositions.py` stays at 25 entries**, but **`account`'s disposition
changes from `ANONYMIZE_IN_PLACE` to `HARD_DELETE`** to match the decision and
the published policy. That is a content change to an existing row, not a new
one.

---

## 2. The cascade defect, which is this unit's reason for a migration

### What is built

```
Enrollment.student_account_id   -> account.id   ondelete="CASCADE"
Enrollment.guardian_account_id  -> account.id   ondelete="SET NULL"
```

**Two columns on one table, referencing the same parent, with opposite delete
behaviours and no comment explaining why.**

### What it means under a hard delete

| Who deletes | Today's behaviour | Policy and AC1.6.2 require |
|---|---|---|
| A guardian | link nulled, **enrollment survives** | survives ✓ |
| A **student** | **the enrollment row is deleted** | survives ✗ |

**And the blast radius is not one row.** Six tables cascade from
`enrollment` — `fee_cycle`, `payment_claim`, ledger entries, attendance,
marks and attendance submissions. A student's deletion would remove, in one
statement, **the teacher's entire record of that seat**: every mark, every
attendance mark, and a settled fee ledger.

That contradicts **AC1.6.2** ("the teacher-authored enrollment, attendance,
marks and fee records remain") and contradicts the published policy, which
tells a user in as many words that those entries are kept.

### A second cascade, found by asking whether anything else re-links

**`payment_claim.submitted_by_account_id` is also `CASCADE`** — and
`nullable=False` — so even after the enrollment link is fixed, a student
deleting their account **still deletes their payment claims**: the record of
a payment they submitted, with its transaction id and channel.

**The ledger survives**, which bounds the damage and is worth stating:
`ledger_entry.created_by_account_id` is `SET NULL`, and its link to
`payment_claim` is `SET NULL` too. So **balances and the fee history are
intact**; what disappears is the claim row and its evidence.

**The same asymmetry appears inside one table**:
`verified_by_account_id` on the same row is `SET NULL`. So a teacher's
deletion unlinks the verification and keeps the claim, while a student's
deletes it outright.

**Included in `0007`** [human, 2026-10-25]: `submitted_by_account_id` becomes
nullable and `SET NULL`, consistent with `verified_by_account_id` beside it.

### The enumeration, which is the only honest way to do this

**Two cascades were found by reading pairs; the third was found by
enumerating.** Every `account.id` reference, with its `ondelete`, its
nullability and **its table's disposition** — because the contradiction is
exactly *a `CASCADE` against a `RETAIN_WITH_BASIS` table*:

| Table | Column | ondelete | NOT NULL | Disposition | |
|---|---|---|---|---|---|
| `enrollment` | `student_account_id` | CASCADE | no | RETAIN_WITH_BASIS | **contradicts** |
| `payment_claim` | `submitted_by_account_id` | CASCADE | **yes** | RETAIN_WITH_BASIS | **contradicts** |
| `queued_submission` | `submitted_by_account_id` | CASCADE | **yes** | RETAIN_WITH_BASIS | **contradicts** |
| `profile` | `account_id` | CASCADE | yes | HARD_DELETE | correct |
| `refresh_token` | `account_id` | CASCADE | yes | HARD_DELETE | correct |
| `owner` | `account_id` | CASCADE | yes | HARD_DELETE | correct — but § 2a |
| `hidden_batch_preference` | `account_id` | CASCADE | yes | HARD_DELETE | correct |
| `reminder_event` | `sent_by_account_id` | CASCADE | yes | HARD_DELETE | correct |
| seven others | — | SET NULL | no | RETAIN_WITH_BASIS | correct |

**Fifteen references: eight CASCADE, seven SET NULL.** The rule falls out of
the table rather than being asserted over it:

> **A `CASCADE` to `account.id` is wrong exactly when its table's disposition
> is `RETAIN_WITH_BASIS`** — the manifest already says the row must survive
> account deletion, and a cascade deletes it.

**Two of the three contradicting columns are `NOT NULL`**, so `0007` must
make them nullable as well as altering the constraint — not a one-line
`ondelete` flip.

**`queued_submission` is the third and it is reachable only by a teacher**:
its basis says *"the account it names is the TEACHER who submitted, never the
student"*. § 2a is why that now cannot happen.

**This enumeration is the mechanism, not just the finding** [BR1.3]: the
deletion test derives the same table from `DISPOSITIONS` and the live
constraints, so **a future `CASCADE` added against a `RETAIN_WITH_BASIS`
table fails without anyone editing the test.**

---

## 2a. Teacher deletion, which nothing had considered

**The largest cascade in the product, and it runs through `owner`**:

```
account --CASCADE--> owner --CASCADE--> batch --> enrollment --> six tables
```

Every row on that path is `NOT NULL` and `CASCADE`. **A teacher deleting
their own account would erase every student's attendance, marks and settled
fee ledger across every batch they ever ran** — records belonging to children
who never consented to that deletion, and it is reachable today through
BR3.2's unauthenticated route, which takes only a phone number.

**Each link is individually defensible**, which is why nothing caught it. An
`owner` row exists only for its account; a `batch` exists only for its owner.
**The chain is what is wrong**, and no single `ondelete` is the culprit.

**The decision** [human, 2026-10-25]: **a teacher with any batch cannot
delete their account.** The route refuses and names what is blocking, so the
teacher deactivates or hands over their batches first. **The cascade becomes
unreachable rather than correct**, which is the stronger property — it does
not depend on six constraints all staying right.

**This makes the published policy wrong and `0007` does not fix that.**
`PRIVACY.md` currently says a teacher's deletion means *"their students'
records are deleted with the class"*. Under this decision that never happens,
because the deletion is refused first. **BR2.1's generator is what corrects
it**, which is the second time in this unit that generating the policy would
have caught a statement the code contradicts.

### `0007` must drop constraints by their REAL names

**The constraint names in the database are not the names the model
implies**, and a migration written against the model would **fail on a
migrated database while passing against a metadata-created one** — the worst
shape of divergence, because tests that build from metadata would stay green.

| Constraint | Model implies | **Actually named** |
|---|---|---|
| enrollment → account (student) | `fk_enrollment_student_account_id_account` | **`fk_enrollment_account_id_account`** |
| enrollment → account (guardian) | `fk_enrollment_guardian_account_id_account` | **`fk_enrollment_guardian_account`** |
| payment_claim → account | convention | convention — created by `0005` |
| queued_submission → account | convention | convention — created by `0006` |

**How the drift happened, and it is instructive**: `0001` created the student
FK as `fk_enrollment_account_id_account`, named for the column as it then was
(`account_id`). `0002:132` renamed the **column** to `student_account_id`
with `alter_column(new_column_name=...)` — **which renames the column and not
the constraint.** The guardian FK was hand-named in `0002:363` and never
matched the convention at all.

**Nothing guards this.** `app/db/base.py` declares the naming convention and
its docstring says it exists to prevent exactly this divergence;
`tests/db/test_migration_runs.py` asserts only the *absence* of
`fk_enrollment_batch`, and **nothing compares the migrated constraint set
against the model's.** `0007` therefore names the real names explicitly, and
a comment records why they look wrong.

---

### The fix, and why it is a migration rather than code

**Migration `0007` alters `student_account_id` and
`payment_claim.submitted_by_account_id` to `ondelete="SET NULL"`**, making
each symmetric with the column beside it [human, 2026-10-25].

**The alternative was to null the column in the deletion path before deleting
the account**, which works and was declined. The reason is the one this
project keeps arriving at: **a rule enforced by remembering is enforced
once.** The destructive default would stay one forgotten line away, and any
*other* path that deletes an account row — a repair script, a future admin
tool, a test fixture — would still cascade. **The constraint makes the
database enforce AC1.6.2.**

> **Neither `ondelete` is wrong in isolation**, which is why this survived
> four units. A cascade is right for a row that exists only for its parent.
> The pair is wrong *together*, because it makes one user action mean two
> different things depending on which role the account holds — and a
> per-column default is invisible at the row level, so reading the model
> found it where reading the deletion code would not have.

---

## 3. What deletion does, table by table

This is the deletion specification, and it is **transcribed from
`dispositions.py` rather than invented here** — with the one change § 1
names.

```yaml
deletion:

  - table: account
    action: HARD_DELETE          # changed from ANONYMIZE_IN_PLACE
    note: >
      The published policy promises "Deleted permanently, within 30
      days: Your phone number" and the human chose to honour it
      [2026-10-25]. **The basis the manifest carried for anonymising
      names a real hazard and it does not disappear**: the phone
      number is the permanent key, so freeing it means a future signup
      with that number could meet a stranger's records. § 4 is how
      this unit closes that, because the decision creates the
      obligation.

  - table: profile
    action: HARD_DELETE
    note: Self-authored and owner-private. Nobody else has a claim.

  - table: [otp_request, refresh_token, verify_attempt]
    action: HARD_DELETE
    note: Credentials and their attempts. No basis for keeping them.

  - table: enrollment
    action: RETAIN, links cleared
    note: >
      The row survives with `student_account_id` and
      `guardian_account_id` nulled -- by the CONSTRAINT after `0007`,
      not by the deletion code [§ 2]. **`display_name` is
      teacher-authored and SURVIVES** [ADR-012], which is the
      disclosure the policy must state and a test must assert it
      states.

  - table: [attendance, mark, fee_cycle, ledger_entry, payment_claim]
    action: RETAIN_WITH_BASIS
    note: >
      Simultaneously the child's personal data and the teacher's
      record of a class they ran and were paid for. Erasing them
      rewrites an attendance history and a settled ledger.

  - table: auth_audit_log
    action: RETAIN 12 months
    note: Holds no name, no code, no token. Already true.
```

---

## 4. The reuse hazard the decision creates

**Hard-deleting `account` frees the phone number**, and the manifest's own
basis says why that matters: a different person could later sign up with that
number.

**After `0007` the hazard is bounded rather than eliminated**, and the bound
is worth stating precisely:

- Every `account.id` reference is **nulled or cascaded**, so a new account
  with the same number gets a **new `id`** and inherits **no link** to the old
  one. A stranger cannot reach the deleted user's records by signing up.
- What survives is the **teacher-typed `display_name` and `guardian_phone`**
  on the enrollment — teacher-authored data the policy already discloses.

**So the hazard the basis named is a linkage hazard, and nulling the links
closes it.** `0007` is therefore not only AC1.6.2's enforcement; it is also
what makes the hard delete safe. **Two obligations, one constraint** — stated
because a later reader may see `0007` as serving only one and weaken it.

**One residual, stated rather than solved**: `guardian_phone` on the
enrollment is a phone number the teacher typed, and it survives. If the
guardian whose number it is deletes their account, that string remains. It is
teacher-authored under ADR-012, the policy discloses it, and **this design
does not change it** — but it is the sharpest edge of the disclosure and
`rules.md` names the test that asserts the policy says so.

---

## 5. Entities this unit reads and does not write

| Thing | Read for |
|---|---|
| `DISPOSITIONS` | the generated policy text, and the deletion itself |
| `RETENTION` | the chunked purge's windows |
| `PUBLIC_ROUTES` | the two deletion routes are **already allowlisted** |

**`PUBLIC_ROUTES` is not touched.** It holds eight entries, two of them
`("GET", "/account-deletion")` and `("POST", "/account-deletion")`, declared
in D1 with a comment reading *"pre-declared D6 scope"*. **D6 lands handlers
against entries that already exist**, so the count assertion continues to
pass with no change.

---

## 6. What D6 does not create

| Thing | Why |
|---|---|
| Any new table | Every mechanism reads existing rows |
| Any new column | `Account.deleted_at` already exists, reserved for this unit |
| A `PUBLIC_ROUTES` entry | Both deletion routes were pre-declared |
| A new disposition kind | Three exist and cover every case |
| A new retention class | Five exist; D6 **enforces** them for the first time |

---

## Assumptions & Open Questions

- **`Account.deleted_at` exists and this design does not use it for the
  account row**, because that row is now hard-deleted. The column was
  reserved for a soft delete the decision superseded. **Whether to drop it in
  `0007` or leave it is `rules.md`'s to settle**; leaving an unused column is
  the smaller change and the project's rule about comments stating claims
  applies to its docstring either way.
- **`RetentionClass` is referenced only by its own definition.** Seven tables
  carry finite windows — three at 7 days, two at 12 months, one at 48 hours,
  one until-expiry-plus-30 — and **nothing deletes anything today**. The
  chunked purge is the first enforcement, which makes it new behaviour rather
  than a scheduled version of something existing.
- **No policy generator exists**, although `docs/legal/README.md` is headed
  "The policy is generated from the schema, not written beside it". The
  existing `PRIVACY.md` was hand-written against the schema and verified by a
  five-row manual table. **D6 builds the generator**, and the policy it
  produces must be compared against the existing text rather than silently
  replacing it — the current wording was reviewed by a human and the
  generator's first output has not been.
- **The 30-day promise is a policy claim with no mechanism.** `PRIVACY.md`
  says "Deleted permanently, within 30 days". A synchronous deletion satisfies
  it trivially; a queued one needs the purge to run. `rules.md` states which
  this unit builds.
