# CI/CD Pipeline — `batches-and-enrollment` (U4)

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

## Sources

- [upstream] `nfr-design/reliability-design.md` — §A.0, §A.1
- [upstream] `nfr-design/performance-design.md` — §A
- [upstream] `nfr-requirements/tech-stack-decisions.md` — A.5, A.6, B.2
- [upstream] `construction/identity-and-access/infrastructure-design/cicd-pipeline.md`
- [team] `## Deployment`, `## Testing Posture`

---

## A. What B5 adds to the backend job

| Addition | Why it cannot wait |
|---|---|
| **A second migration run, from `0001` with rows** | The from-zero run cannot see a destructive rename [NFR6.18] |
| The money `TypeDecorator` | First real money column; `team.md` specified it and B1 had no table to need it |
| The non-money allowlist | `batch.fee_due_day` matches `fee` and `due` while holding an integer |
| Query-count assertions at two roster sizes | The N+1 shape, which no existing test can see |

### A.1 The second migration run is the important one

```
pytest tests/db/test_migration_from_head.py
  1. upgrade to 0001            (the B3 head)
  2. seed a dormant enrollment  <- without this, both shapes pass
  3. upgrade to head
  4. assert the enrollment STILL POINTS AT ITS ACCOUNT
```

> **Steps 2 and 4 are the requirement**, not step 1. Verified against
> a live container: with an empty table a rename and a
> drop-and-recreate are indistinguishable, and even with a row present
> a **count** assertion passes against both. Only the surviving link
> separates them.

---

## B. The money gate changes shape here

B3 armed a schema assertion that was **vacuous** — U3 carries no
money. U4 gives it something to check, and that exposes a false
positive:

| Column | Matches | Is money | Needed |
|---|---|---|---|
| `batch.default_fee` | `fee` | yes | checked |
| `enrollment.fee_amount` | `fee`, `amount` | yes | checked |
| `batch.fee_due_day` | `fee`, `due` | **no** | **allowlist** |
| `batch.collection_number` | — | no | nothing |

> **The dangerous fix is the obvious one.** Dropping `fee` or `due`
> from the token list turns the build green while silently retiring
> the check on every genuine fee column in U7 and U8. A per-column
> allowlist keeps the tokens intact, and each entry is a reviewable
> line with a reason.
>
> This is predicted from the token list rather than observed — **no
> `Batch` table exists yet** — and becomes verifiable the moment the
> migration lands.

---

## C. The blocking suite still needs no secret

Unchanged from B3 and worth restating, because U4 is the first Unit
that could plausibly have broken it: every new test runs against the
testcontainer, the Android tests run on the JVM under Robolectric, and
a fresh clone runs the complete gate.

---

## D. What does not change

| Unchanged | Why |
|---|---|
| Gitleaks blocking every push | U4 introduces no new credential |
| The dependency-CVE two-speed policy | Room is the only new runtime dependency |
| The schema-diff gate | U4's routes change the contract; `make openapi` regenerates and the diff is read |
| The Android job | Room adds a KSP processor; the job shape is the same |

---

## E. Obligations this stage records and cannot execute

1. **Delete the skeleton seed's ROWS before deploying `0002`**, then
   the script. The migration refuses to run while they exist, so
   skipping this stops the deploy before any data is touched —
   recoverable and loud, but only if the operator knows why.
2. **`SHIKKHOKPLUS_GLOBAL_DAILY_SMS` must be set** before the first
   production deploy. Carried from B3 §F, now enforced at startup by
   `app/config.py` rather than remembered.
3. **The B3 device leg is still unverified** — no real SMS has been
   sent and the seed script has never been run against a real host.
   Recorded here because obligation 1 reads differently depending on
   whether it happened, and nothing in the record says it did.

---

## Assumptions & Open Questions

**None.** [assumption] Room's KSP processor adds build time to the
Android job but no new gate; if that job approaches the stated minute
budget, `team.md` already names splitting it to CodeBuild as the
response, and nothing here changes that calculus.
