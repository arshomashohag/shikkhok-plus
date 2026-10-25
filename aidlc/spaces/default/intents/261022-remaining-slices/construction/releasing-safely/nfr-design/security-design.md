# Security Design — D6 `releasing-safely`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D6 `releasing-safely`
**Record**: 261022-remaining-slices

> **Every earlier unit's security design protects data. D6's protects its
> destruction**, and that inverts the usual shape: the dangerous operation is
> the *intended* one, the attacker's goal is to make it succeed rather than to
> read something, and the route that offers it is **public by regulatory
> requirement** rather than by oversight.
>
> Four designs carry this unit, and each attaches to a mechanism that is
> already built rather than inventing one:
>
> | Design | Attaches to | Why it is not optional |
> |---|---|---|
> | **Purpose-scoped codes** [§ 1] | `app/auth/otp.py` | As built, a sign-in code **would** confirm a deletion |
> | **A third ceiling cascade** [§ 2] | `app/auth/ceilings.py` | The two built cascades bind neither a botnet nor a victim lock-out |
> | **Constraint-level cascade assertion** [§ 3] | `pg_constraint` | `0007` fixes three edges; nothing stops a fourth being added |
> | **Refusal before destruction** [§ 4] | `app/authz/` | Seven retained tables are reachable only through `owner -> batch` |
>
> **Four facts were read out of the built code and the migration history
> before designing**, and each changed the design rather than confirming it
> [§ 6]. The fourth would have produced a **vacuous pass**.

## Sources

- [upstream] `nfr-requirements/security-requirements.md` — NFR14.78–NFR14.102
- [upstream] `nfr-requirements/tech-stack-decisions.md` — NFR21.2–NFR21.6
- [upstream] `functional-design/rules.md` — BR1.1–BR1.6, BR3.1–BR3.3
- [upstream] `functional-design/functional-spec.md` §§ 2, 2a, 5
- [prior] D5's `nfr-design/security-design.md` — the collected-obligations shape
- [prior] ADR-012; AC1.6.1–AC1.6.3, AC10.1.1–AC10.1.7
- [human] 2026-10-25 — hard delete; `0007`'s three columns; a teacher owning a
  batch cannot delete; the deletion-specific global sub-ceiling
- [code] read 2026-10-25: `app/auth/ceilings.py`, `app/auth/otp.py`,
  `app/api/auth.py` (`ip_prefix_of`), `app/db/models.py` (`RateLimitCounter`,
  `OtpRequest`), `app/governance/dispositions.py`, `app/contract/routes.py`

---

## 1. Purpose-scoped codes, and the shadowing problem a filter creates

**NFR14.98 says a deletion code is its own purpose. This is how**, and the
design is larger than "add a `WHERE` clause" because of a property of the
built query.

### What is built, verified by reading it

```python
OTP_PURPOSE: Final = "otp"              # app/auth/otp.py:60
```

`issue()` takes **no purpose argument** and writes that module constant.
`verify()` selects:

```sql
SELECT id, otp_hash, expires_at, consumed_at FROM otp_request
 WHERE phone = :phone ORDER BY issued_at DESC LIMIT 1 FOR UPDATE
```

**No purpose predicate.** So a code issued to sign in would confirm a
deletion, which is the whole of the finding.

### The design

1. **`issue()` takes an explicit `purpose`, with no default.** The absent
   default is the design, not an oversight: `OTP_PURPOSE`'s own docstring
   records that a default *"would let a second consumer arrive without anyone
   choosing its ceiling"*. D6 is that second consumer. A required argument
   makes the third consumer choose too.
2. **`verify()` takes the purpose and filters on it.**
3. **The column needs no migration.** `otp_request.purpose` is `String(32)`
   (`app/db/models.py:335`); `deletion` is eight characters.

### The shadowing problem, which is the part worth designing

`verify()` returns the **latest row for the phone**. Add a purpose filter
naively and the ordering changes meaning in a way that is easy to get wrong
in *either* direction:

| Ordering | Consequence |
|---|---|
| Latest row for the phone, **then** check its purpose | A sign-in code issued after a deletion code **shadows** it; the user's valid deletion code is refused with no explanation |
| **Latest row for the phone AND that purpose** | Correct. Each purpose has its own most-recent code |

**The second is the design**: the predicate goes in the `WHERE`, beside
`phone`, not in a check after the row is fetched.

**This matters because the orders are plausible in real use.** A person
requests a deletion code, is unsure, signs in to look at their data first,
then returns to the deletion page with the code they were sent. A
fetch-then-check implementation refuses them, and refuses them with
`_refused()` — which is deliberately contentless, so they are told nothing.
They would retry, spending ceiling budget, and conclude the feature is broken.

**Verifier**: issue a deletion code, then issue a sign-in code for the same
number, then present the deletion code at the deletion route and **assert it
is accepted**. A test that issues only one code passes against the shadowing
defect.

### The single-use rule carries over unchanged

`verify()` sets `consumed_at` inside the same transaction as the check that
read it, under `FOR UPDATE`. NFR14.81's replay requirement needs **no new
mechanism** — it needs the deletion path to call `verify()` rather than
reimplement it. That is stated because reimplementing it is the obvious
shortcut for a route that lives in a different module.

---

## 2. A third ceiling cascade

**NFR14.100 and NFR14.102 together are one mechanism**, and the built module
already shows its exact shape.

### The precedent, read rather than assumed

`app/auth/ceilings.py` holds **two** cascades over one `_consume()`
implementation. The docstring on `ScopeKind` states the principle D6 inherits:

> *"The signup members are separate counters, not extra conditions on the OTP
> ones... A signup refusal never consumes an OTP allowance, and the reverse."*

### The design

**`check_and_consume_deletion()`, a third cascade over the same
`_consume()`.** One implementation, three cascades — because, as the built
docstring says, *"the order-and-accounting rule is the control, and a second
copy of it is how the two stop agreeing"*.

Four new `ScopeKind` members:

| Member | Value | Scope | Limit |
|---|---|---|---|
| `DEL_NUMBER_HOURLY` | `del_number_hour` | the number | 3 |
| `DEL_NUMBER_DAILY` | `del_number_day` | the number | 5 |
| `DEL_IP_HOURLY` | `del_ip_hour` | the /24 prefix | 10 |
| `DEL_GLOBAL_DAILY` | `del_global_day` | the global sentinel | **50** |

**The values are constrained by the column and this was computed, not
eyeballed.** `rate_limit_counter.scope_kind` is `String(16)`
(`app/db/models.py:447`), and the built comment records that
`signup_number_day` — seventeen characters — *"PostgreSQL refuses outright"*.
Measured: `del_number_hour` is 15, `del_number_day` 14, `del_ip_hour` 11,
`del_global_day` 14. **The obvious prefixes do not fit**: `deletion_number_day`
is 19 and `delete_number_day` is 17. The `del_` prefix is the design, and the
reason is recorded here so the next reader does not "improve" it.

### Why the per-IP scope is not the control here, verified rather than assumed

`ip_prefix_of` (`app/api/auth.py:74`) is:

```python
return ".".join(host.split(".")[:3]) if "." in host else host
```

**Two properties follow, and both weaken the per-IP bound for this attack:**

1. **A /24 prefix**, deliberately — so one mobile NAT does not produce a
   per-user counter, and so the counter is not itself a record of who called
   from where. Good for its purpose; it means an attacker spanning prefixes
   never accumulates toward `PER_IP_HOURLY`.
2. **An IPv6 address contains no `.`, so the whole address is the scope
   value.** Each IPv6 caller therefore gets its *own* counter — a bound of 10
   per address rather than per /24, and an IPv6 allocation is vastly larger
   than a /24's worth of addresses.

**Neither is a defect to fix here**, and this is deliberate: narrowing the
prefix would re-introduce the per-user counter the comment rejects, and
IPv6 prefix handling is a change to a function three built routes depend on,
in the last unit before release.

**What follows is that `DEL_GLOBAL_DAILY` is the load-bearing control and
the per-IP scope is depth**, which is the opposite of how a reader would
naturally rank them. It is recorded so the sub-ceiling is not later traded
away as redundant with a per-IP limit that does not bind this attack.

### Why signup's no-global decision does not transfer

`_signup_scopes` deliberately has **no global scope**, and its stated reason is
that signup's cost passes through the OTP cascade's global ceiling immediately
afterwards, so a second global counter *"would bound the same spend twice at
two thresholds"*.

**That reasoning does not hold for deletion, and the difference is the
attack.** Deletion's hazard is not that it spends twice — it is that it spends
**the same budget sign-in needs**. NFR14.102's sub-ceiling exists precisely to
stop one consumer exhausting another's, which is the opposite of the condition
under which signup declined a global scope. Recording this is the point: a
reader who patterns off signup would omit the global scope and reopen the
finding.

### The new counters fall under an existing retention window

`rate_limit_counter` carries `RetentionClass.HOURS_48` in the manifest
(derived from `DISPOSITIONS` on 2026-10-25, not quoted), so the purge
[§ 5a's sibling obligation] deletes the four `del_*` scopes' rows on the same
schedule as the other six. **No new retention entry is needed**, and that is
worth asserting rather than assuming: a new counter kind whose rows were
never purged would accumulate one row per number per day indefinitely, and
nothing in the ceiling path would notice.

**The purge's window is longer than every ceiling window it serves** — 48
hours against a daily maximum — so a counter is never deleted while it is
still being enforced against. That ordering is the correctness property; the
specific 48 hours is the manifest's existing choice, which D6 does not change.

### The accounting, unchanged and inherited

Narrowest-first, with the refusing scope's own increment released so a refusal
consumes nothing. **D6 writes no new `_consume()`**, so it cannot get this
wrong — which is the argument for the third cascade over a bespoke limiter.

**`fire_ceiling_alert` fires on `DEL_GLOBAL_DAILY`** as it does on
`GLOBAL_DAILY`, and for a sharper reason: the deletion budget being drained is
**not** ordinary use. Sign-in's global ceiling tripping might be a busy day.
Fifty deletion codes in a day is an attack, and it is the only one of the
seven scopes whose breach has no innocent explanation.

### What the verifiers must assert

**All three assert that something still WORKS**, which is the half a refusal
test misses:

| Requirement | Verifier |
|---|---|
| NFR14.100 | Exhaust `del_number_day` for a number, then **assert a sign-in code still issues for that same number** |
| NFR14.102 | Drain `del_global_day`, then **assert a sign-in code still issues** |
| Both | A test asserting only that the deletion route refuses **passes against the shared-counter defect** |

---

## 3. The cascade assertion, at the constraint level

**NFR14.83 and NFR14.99 are one test**, and it is the strongest thing this
unit builds.

### Why a code-level check would not do

`0007` changes three `ondelete` values. A test that asserts *those three columns*
is a test of the migration, and it passes forever afterwards while a fourth
contradicting constraint is added in some later unit. The property worth
asserting is not "these two are right" but **"no contradiction exists"**,
which is a statement about the live schema.

### The query, run against the live schema on 2026-10-25

Depth-one reachability was the first draft and the reviewer was right that it
is insufficient. The transitive form finds **eleven** `RETAIN_WITH_BASIS`
tables reachable from `account` by cascade, **seven of them only through
`owner -> batch`** — a chain `0007` does not touch at all.

**That number settles a design question rather than decorating one.** It is
why BR1.6's refusal [§ 4] is **load-bearing**: without it, `0007` alone leaves
a teacher's deletion destroying seven kinds of retained record.

**The path column is the diagnostic.** A failure that says only "a
contradiction exists" sends the next reader to `models.py` to work out which
of fifteen foreign keys it means. The recursive query carries the path, so the
failure names the chain.

### Two facts about `0007` that this assertion must survive

**Carried forward from the functional design because each defeats the
assertion in a different way**, and neither is visible from the requirements.

**1. Two of the three contradicting columns are `NOT NULL`.** The three are
`enrollment.student_account_id` (nullable), `payment_claim.submitted_by_account_id`
and `queued_submission.submitted_by_account_id` (both `NOT NULL`). A `0007` that flips
`ondelete` alone **fails at migration time** — `SET NULL` on a `NOT NULL`
column is not a constraint PostgreSQL will accept. The migration must make
them nullable as well.

**This is a security fact and not a schema detail**: a migration that fails
is the *good* outcome. The hazard is the reverse ordering — making the column
nullable in one change and deferring the `ondelete` flip — which leaves the
cascade in place while the schema *looks* prepared. **§ 3's test is what
catches that**, because it asserts the `confdeltype`, not the nullability.

**2. The constraint names in the database are not the names the model
implies**, and this is the sharper one:

| Constraint | Model implies | Actually named |
|---|---|---|
| enrollment → account (student) | `fk_enrollment_student_account_id_account` | **`fk_enrollment_account_id_account`** |
| enrollment → account (guardian) | `fk_enrollment_guardian_account_id_account` | **`fk_enrollment_guardian_account`** |

**Verified in the migration sources, not carried from the functional
design**: `0001:201` creates `name="fk_enrollment_account_id_account"`, named
for the column as it then was (`account_id`); `0002:132` is
`op.alter_column("enrollment", "account_id", new_column_name="student_account_id")`,
which renames the **column** and not the constraint; `0002:363` hand-names the
guardian FK `fk_enrollment_guardian_account`, which never matched the
convention at all.

**The failure mode is a vacuous pass, which is this project's recurring
one.** A migration written against the model's implied names **fails on a
migrated database and passes against a metadata-created one** — so a test
suite that builds its schema from metadata stays green while production
cannot migrate. `0007` names the real names explicitly.

**This is why § 3's query reads `pg_constraint` rather than the ORM
metadata.** The two disagree today, demonstrably, on two constraints; a
metadata-sourced assertion would be asserting against the document rather
than against the database. That is the design reason for the choice, stated
rather than left as a preference.

### `0007` must move a deliberately pinned head

`tests/db/test_no_d5_migration.py` pins `EXPECTED_REVISIONS = 6` and
`EXPECTED_HEAD = "0006"`, with a docstring explaining that **either alone is
defeatable** — a replaced revision keeps the count and moves the head, a new
branch moves neither.

**So D6 adding `0007` will fail that test, and that is the test working.**
Verified: six files in `migrations/versions/`, and the test asserts
`len(found) == EXPECTED_REVISIONS` and `head.name.startswith(EXPECTED_HEAD)`.
`0007` trips **both**. Its third assertion is scoped to `app/analytics/` —
D5's package — so D6 does not touch it.

**But that test is not the whole blast radius, and an earlier draft of this
section said it was** [corrected 2026-10-25 after review]. A grep for the
pinned literal finds **four**, and the fourth is the one that matters:

| Location | What it pins |
|---|---|
| `tests/db/test_no_d5_migration.py:29` | `EXPECTED_HEAD`, plus the revision **count** |
| `tests/db/test_migration_from_head.py:142` | `assert revision == "0006"` after upgrade |
| `tests/db/test_migration_runs.py:121` | `assert revision == "0006"` |
| **`tests/auth/test_endpoints.py:194`** | **`body["migration_revision"] == "0006"`** |

**The fourth is not a migration test at all.** It asserts what `/health`
reports — and `team.md`'s Deployment practice makes the post-deploy smoke set
*"a health endpoint reporting database connectivity and applied migration
revision"*. So the literal is the deploy-time check's expected value, not a
schema detail, and leaving it stale would mean the smoke check asserts an
old revision against a freshly migrated host.

**`tests/db/test_migration_rollback_is_total.py:117` asserts `"0001"` and is
correctly NOT in this list** — it is the failed-migration path, which `0007`
does not move. Naming the exception matters as much as naming the list,
because a blanket find-and-replace of `"0006"` would be right and a blanket
one of "the revision literal" would not.

**Why the incomplete version was wrong in a way worth recording**: naming one
test made the change look like a one-line pin update, so the other three
would surface as confusing CI failures mid-build — which is exactly the
pressure under which a constant gets edited to make a test pass rather than
updated with intent.
The design requirement is that the pin is updated **as part of `0007`'s
change**, not discovered as a surprise failure and patched afterwards: the
file is D5's assertion that D5 ships no migration, so D6 moving it is a
deliberate statement that D6 does, and the comment it carries should say so.

**It is named here rather than left to the build** because the alternative —
hitting it mid-build and editing a constant to make a test pass — is exactly
what `project.md` forbids: never weaken a defined check to make a step pass.
Updating a pin with intent and weakening a gate under pressure produce the
same diff, and only the sequence tells them apart.

### The fixture exists

`tests/db/test_governance.py`'s `restricted_session` already executes raw
`pg_tables` and `information_schema.columns` reads. A `pg_constraint` query
needs **no new fixture and no new privilege** — confirmed by the reviewer
independently. `confdeltype` is `c` for CASCADE and `n` for SET NULL.

**This test runs as the restricted role like every other** [project rule], and
that is not incidental here: a superuser-run schema test would still read
`pg_constraint` correctly, so this is the one privacy-suite member where the
restricted role buys nothing extra. It stays restricted anyway, because an
exception is a thing to remember.

### The restricted role does NOT narrow this gate, and that was measured

**The governance suite records a near-miss worth taking seriously here**: an
ungranted table is invisible to the restricted role in `information_schema`,
so *"every gate above silently stops covering it"* — the money assertion
skipped `batch.default_fee` entirely until the grant was added, and the
comment concludes **a control that quietly narrows is worse than one that
fails.**

**§ 3's query runs as that same role, so the obvious fear is that it inherits
the same narrowing.** It does not, and this was **measured against a real
PostgreSQL 16** on 2026-10-25 rather than reasoned about: two child tables
were created with `ON DELETE CASCADE`, `SELECT` granted on one only, and both
catalogs queried as the restricted role.

| Catalog | Sees the granted child | Sees the **ungranted** child |
|---|---|---|
| `information_schema.tables` | yes | **no** |
| `pg_constraint` | yes | **yes** |

**`pg_constraint` is a system catalog and is not permission-filtered by
table grant**, where `information_schema`'s views are. So a `RETAIN_WITH_BASIS`
table whose grant was forgotten — the exact mistake that already happened once
on this project — **still has its cascade checked**.

**This is a property of the catalog choice, not of care**, which is why it is
recorded: a future reader "simplifying" § 3 to read
`information_schema.referential_constraints` would reintroduce the narrowing
silently, and the test would keep passing.

---

## 4. Refusal before destruction

**BR1.6 / NFR14.84**: a teacher owning any batch cannot delete their account.

### Why this is a refusal rather than a cascade fix

The seven tables of § 3 reachable only through `owner -> batch` are **other
people's records** — students' attendance, marks, ledger rows — that happen to
hang off a teacher's batch. Nulling that chain is not available: a batch with
no owner is not a batch, and the rows beneath it lose the scoping value every
lens resolves through.

**So the design refuses the deletion instead of weakening the schema**, and
the refusal is what makes the retained records safe rather than a second
`0007`.

### The refusal must be a precondition, not a cleanup

Checked **before** anything is destroyed, in the same transaction, because a
deletion that removes half an account and then refuses is worse than either
outcome. **Verifier: a teacher with one batch attempts deletion; assert the
refusal AND assert the account row still exists** — the second half is what
catches a partial.

### What it tells the teacher

The refusal is **not** contentless, and this is the one place in this unit
where that is right. Enumeration resistance protects a number's existence from
a stranger; here the caller has already proven ownership of the number. A
contentless refusal would tell a teacher their deletion "failed" with no route
forward, and they would conclude the feature is broken rather than that they
must first hand over or close their batches.

**It carries a `message_key`** like every other error [built contract], so the
Bangla string is a translation rather than a server-sent English sentence.

---

## 5. What D6 asserts rather than builds

Five invariants are already enforced. D6's job is to run them **against the
final schema**, which is the first time they have been run against a schema
nobody will add to.

| Invariant | Built mechanism | NFR |
|---|---|---|
| Refusals disclose nothing | the error-contract test | NFR14.91 |
| No profile field to a teacher | `app/contract/privacy.py` | NFR14.92 |
| Every route names a lens | the route-enumeration test | NFR14.93 |
| No trusted lens hint | built in D1 | NFR14.94 |
| Governance complete, **both directions** | the governance pair | NFR14.95 |

**The second direction of the governance test matters most here**: a
disposition naming a table that no longer exists is exactly what a long
sequence of units produces, and D6 is the last chance to notice.

---

## 5a. The generated policy is a security artifact

**NFR14.88–14.90, NFR16.6, NFR16.7 and NFR14.101 are here rather than in a
documentation section**, because the privacy policy is the document a
regulator reads and a false statement in it is a compliance failure, not a
typo.

### The threat is drift, and it is the one this unit already met

§ 1 of the functional design found **three documents answering one question
three ways** — `dispositions.py` said anonymize, `README.md` said hard delete,
`PRIVACY.md` said deleted permanently. That is not hypothetical drift; it is
the drift this unit was handed. **The generator plus the drift gate is what
would have caught it** [NFR14.88], and that is the argument for the gate
stated as evidence rather than as principle.

### The design

| Requirement | Mechanism |
|---|---|
| NFR16.6 | Generated text lives **between markers** in the committed `PRIVACY.md`; the **marker region is the unit of comparison**, so human prose around it stays editable |
| NFR14.88 | Regenerate-and-compare in `make check`, the same shape as the built OpenAPI schema-diff gate |
| NFR16.7 | **Deterministic**: same manifest, same bytes. A generator emitting a timestamp makes every build a diff and the gate becomes noise within a week |
| NFR14.89 | The **ADR-012 disclosure** asserted against the *generated* output — that a teacher-typed name survives deletion |
| NFR14.101 | The manifest's **basis** corrected, not only its disposition |

### NFR14.101 is the subtle one and deserves its own sentence

The generator reads the **basis** field. NFR14.89 asserts a disclosure is
**present**; nothing asserts it is **true**. So the `account` entry's basis —
which currently argues for anonymization, the disposition the human overruled
— would be faithfully published as the reasoning for a hard delete.

**A generated document is only as true as the field it reads.** Correcting
the disposition without the basis produces a policy that is mechanically
consistent and substantively wrong, which is worse than the three-way
disagreement it replaced: that one was at least visible.

### NFR14.90 is the one partly-automated obligation in this unit

Nothing mechanically prevents a **factual claim being written outside the
generated region** — a human could add a sentence to the prose saying data is
deleted when the manifest says retained, and the drift gate would not see it.

**Removing the rival hand-written table shrinks the surface; it does not close
it.** This is named rather than rounded up, and it is the reason § 7's "every
obligation is automated" claim is scoped to the *security* obligations and
excludes this one.

### NFR17.10 and NFR17.11, which are refusals

**NFR17.10** — D6 adds no third-party dependency, so the forbidden-identifier
set is untouched and the SDK admission note has nothing to record.
**NFR17.11** — the deletion path decides an authorization question but
resolves it through `app.authz`, which is already a strict island, so no new
island is added. **Verifier for both: the lockfiles and the mypy config are
unchanged**, which is a real assertion rather than an absence of one.

---

## 6. Four things the built code changed about this design

Recorded because each was read rather than assumed, and each would have been
wrong the other way:

1. **`scope_kind` is `String(16)`.** The natural `deletion_` prefix does not
   fit and PostgreSQL refuses it at the first call. Measured, not estimated.
2. **`verify()` orders by `issued_at DESC LIMIT 1` with no purpose
   predicate.** That is both the vulnerability (§ 1) and the reason a naive
   filter creates a shadowing bug.
3. **`_signup_scopes` has no global scope, with a stated reason that does not
   transfer.** Patterning off it would reopen NFR14.102.

4. **Two constraint names in the database differ from the model's**, because
   `0002` renamed a column with `alter_column`, which does not rename its
   constraint. This is the reason § 3 reads `pg_constraint` rather than ORM
   metadata, and it upgrades that choice from a preference to a design
   requirement.

**None of these is visible from the requirements**, which is the argument for
reading the module — and the migration history — before designing against it.

**The fourth is the one that would have produced a vacuous pass**, which is
this project's recurring failure mode: a metadata-built test suite staying
green while the real database cannot migrate.

---

## 7. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| A sign-in code cannot confirm a deletion [NFR14.98] | Issue for sign-in, present at deletion, assert refusal | yes |
| **A later sign-in code does not shadow a deletion code** [§ 1] | Issue deletion, then sign-in, assert the deletion code is **accepted** | yes |
| A consumed code cannot be replayed [NFR14.81] | Present it twice | yes |
| Deletion's number counter is its own [NFR14.100] | Exhaust it, assert **sign-in still issues** | yes |
| Deletion's global sub-ceiling is its own [NFR14.102] | Drain it, assert **sign-in still issues** | yes |
| The scope values fit the column [§ 2] | Any ceiling test exercises the insert | yes |
| The `del_*` counters are purged [§ 2] | The purge's manifest-driven test covers `rate_limit_counter` without a new entry | yes |
| **No contradicting CASCADE exists, transitively** [NFR14.83, NFR14.99] | **The recursive `pg_constraint` query** | yes |
| The assertion reads the **database**, not the metadata [§ 3] | The query targets `pg_constraint`; the two provably disagree on two constraint names today | yes |
| `0007` runs on a **migrated** database, not only a metadata-built one [§ 3] | The migration test chain applies `0007` from head | yes |
| **All four** pinned revision literals move [§ 3] | The four named locations, including `/health`'s smoke value | yes |
| The assertion is **not narrowed** by the restricted role [§ 3] | Measured: `pg_constraint` is not grant-filtered; `information_schema` is | yes |
| A teacher with batches cannot delete [NFR14.84] | A probe, **plus asserting the account survives** | yes |
| Enumeration-resistant responses [NFR14.79] | Equality over two responses | yes |
| The five built invariants [NFR14.91–95] | Existing gates, unchanged | yes |

| **No factual claim outside the generated region** [NFR14.90] | **Review, plus removing the rival table** | **partly** |

**Every obligation above is automated except the last**, and the exception is
the one that is about prose rather than state. The rest — deletion, ceilings,
constraints — are all assertable because each is a question about what the
system *is*, and that is a property of the subject rather than of effort.

**NFR14.90 is the single partly-automated row**, carried here from § 5a rather
than quietly dropped: nothing mechanically stops a human sentence in the
hand-written prose contradicting the manifest.

**Three of them assert that something still works after an attack**, and those
are the three that a refusal-only test passes against. They are marked in bold
above for that reason, not for importance.

---

## Assumptions & Open Questions

- **The deletion sub-ceiling is 50 of 500** [human, 2026-10-25]. Like
  `GLOBAL_DAILY` it is **a value, not a decision**: the mechanism is what this
  unit builds and tests, and the production number is set at deployment.
- **`del_global_day` alerting on breach is this design's addition**, not a
  stated requirement. It follows `GLOBAL_DAILY`'s precedent and the reasoning
  is in § 2; if the operator finds it noisy, the finding would be that
  deletion traffic is higher than expected, which is itself worth knowing.
- **The purpose filter's shadowing property has no upstream requirement.** It
  was found by reading `verify()`, and § 1 is where it is recorded. It is a
  numbered obligation in § 7 rather than a note, because it is exactly the
  kind of thing a correct-looking implementation gets wrong.
- **No figure in § 2 was measured against a running ceiling**; the limits are
  design values. **The string lengths in § 2 WERE computed**, and the
  distinction is deliberate.
- **I could not execute any suite for this stage**: D6's code does not exist.
  Every claim about built code here was read from the source on 2026-10-25,
  and every claim about the live schema was produced by the § 3 query, which
  was run.
