# Security Design — D5 `knowing-how-it-is-going`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5's authorization is stronger than every unit before it, and the reason
> is structural rather than careful: it takes no resource id from the
> request.** D1 through D4 each validate an id a caller supplies — a batch, a
> session, an enrollment, an exam — and each therefore has a check that can be
> omitted. D5's reads take **no id at all**. The lens's `owner_id` is the only
> scoping value, so there is nothing to validate and nothing to forget.
>
> What that buys is narrow and worth stating precisely: **it removes the IDOR
> class entirely from this unit's reads** [§ 1]. What it does not remove is
> the aggregate problem — **a wrong scope leaks a number rather than a row,
> and a number has no field to inspect** [§ 2].
>
> Three designs carry this unit: the **no-id property** (§ 1), the
> **value-asserting probe** that is the only thing which can catch an
> over-wide sum (§ 2), and the **ZAP baseline** with its honestly-stated limit
> (§ 5).

## Sources

- [upstream] `nfr-requirements/security-requirements.md` — NFR14.65–NFR14.77,
  NFR10.21, NFR10.22
- [upstream] `functional-design/rules.md` — BR1.7, BR2.5, BR4.1, BR4.4
- [upstream] `functional-design/entities.md` — the `DuesRow` field notes
- [upstream] this stage's `performance-design.md` § 1 — the join that makes
  the no-id property true
- [prior] D4's `nfr-design/security-design.md` — the probe-matrix shape
- [team] `team.md` Deployment — the ZAP clause
- [code] read 2026-10-25: `app/authz/lenses.py`, `app/fees/views.py`
  (`_owned_batch`, `_refuse`), `app/contract/privacy.py`,
  `app/contract/routes.py`, `tests/privacy/test_profile_probes.py`,
  `tests/contract/test_route_lenses.py`, `app/governance/dispositions.py`

---

## 1. The no-id property, and what it removes

**Design statement: no read in this unit accepts a resource id.** Not a batch
id, not an enrollment id, not an exam id. The seat set comes from one join:

```sql
FROM enrollment e JOIN batch b ON b.id = e.batch_id
WHERE b.owner_id = :owner_id
```

**Compare what every earlier unit must do.** D3's `_owned_batch` takes a
`batch_id` from the request and refuses when `Batch.owner_id <> lens.owner_id`
— correct, and it is a check that exists because there is an input to check.
D4's `readable_enrollment` is the same shape for a seat. Each is one omitted
`and` away from an IDOR.

**D5 has no such input, so it has no such check and no such risk.** The IDOR
probes that are the centrepiece of D4's security design have **no analogue
here**, and that is stated rather than silently omitted — a reader arriving
from D4 will look for them.

**Verifier: a schema-level assertion that both operations declare an EMPTY
parameter list.** An earlier draft said "no parameter **naming a resource**",
which is weaker in the way that matters: whether a name denotes a resource is
a judgement, and a test cannot make it. **The design is stronger than that
verifier was** — these two operations take no parameters at all — so the
assertion is a plain predicate over the generated document and fails the day
someone adds `?batch_id=`, whatever they call it.

Asserting "there is no IDOR" would be the unfalsifiable form; asserting an
empty parameter list is checkable, and it is the property the design actually
has.

---

## 2. The aggregate problem, which the no-id property does not solve

**A wrong scope on a row query returns a row somebody can point at. A wrong
scope on a sum returns a number that looks right** [NFR14.66]. If the join
above lost its `owner_id` predicate, the dues list would be obviously wrong —
unfamiliar names. The earnings total would be **a larger number**, and
nothing about it announces that it spans two teachers.

**Design statement: every analytics probe asserts the figure's VALUE against
data the test seeded, never merely that a response arrived.**

| Probe | Seeds | Asserts |
|---|---|---|
| Earnings scope | Teacher A: receipts 1000. Teacher B: receipts 7000 | A's total **== 1000**, not 8000 and not "a number" |
| Dues scope | A: one owing seat. B: three owing seats | A's list length **== 1** and its one `enrollment_id` is A's |
| Trend scope | A and B with different months | A's series covers A's periods only |
| Next exam scope | B's exam sooner than A's | A sees **A's** exam, not B's |

**The last row is the one most likely to be omitted and the easiest to get
wrong**: an unscoped "soonest exam" query with `LIMIT 1` returns *somebody's*
exam, and a test asserting only "an exam came back" passes.

**Design statement: where a figure has a magnitude, teacher B is seeded so
that a leak would CHANGE teacher A's answer.** An earlier draft said "B is
seeded larger" across all four rows, which over-generalises — only two of the
four have a magnitude relation at all:

| Probe | The seeding that makes a leak visible |
|---|---|
| Earnings | **B larger.** If A dominated the sum, A's figure would barely move under a leak |
| Dues | **B has more owing seats.** A length assertion then changes under a leak |
| Trend | **Different periods**, not larger ones — a leak shows as A's series carrying a month A has no data in |
| Next exam | **B's exam SOONER.** A leak returns B's exam; if B's were later, the correct answer and the leaked one would both be A's |

**The next-exam row is the one most easily got wrong in both directions**: an
unscoped `LIMIT 1` returns *somebody's* soonest exam, so a probe where B's
exam is later passes against a leak, and a probe asserting only "an exam came
back" passes against everything.

---

## 3. A dues list is a list of people

**Design statement: a dues row carries an `enrollment_id` and the
teacher-recorded `display_name`, and no other identifying field.** No
`student_account_id`, no profile field, no phone number.

**The mechanism is the built gate, not a new one** [NFR14.69]:
`app/contract/privacy.py` iterates the generated OpenAPI document, reads each
route's lens from its dependencies, and fails `make check` on a teacher-lens
schema carrying an owner-private field. D5 adds no mechanism because the
mechanism is schema-wide by construction — which is exactly why it covers a
unit written two units after it.

**What it does not cover is stated as the honest half** [NFR14.70]: it
catches a field in a schema. It does not catch a designer deciding the dues
list should show photos, or a product decision to add a phone number so the
teacher can call. **That decision was already made against** [ADR-001] and
**review is the only control**, which this document says rather than implies.

**The declined-seat exclusion is the one predicate clause D5 shares with D4
beyond ownership** [BR1.7]. Its probe needs a **declined seat that owes
money**; a probe using pending and accepted seats cannot distinguish a
correct implementation from one missing the clause.

---

## 4. Row-level security and governance: two absences, asserted

**Design statement: D5 adds no RLS policy, because it creates no table and
therefore no column naming a reader** [NFR14.72]. The decision inherits D3's
and D4's reasoning and there is nothing new to weigh. **The probes of § 2 and
§ 3 are what enforce the boundary**; recording this as "verified by a
decision" would be the empty-promise shape.

**Design statement: the governance manifest stays at 25 and no migration
ships** [NFR10.21, NFR10.22]. **The verifier that matters here is the second
direction** of the built governance test — `test_no_disposition_names_a_table_that_does_not_exist`
— because a unit that adds nothing could still produce a stale entry by
copy-paste, and a one-directional check would miss it.

**D5's reads run as the granted non-superuser `APP_ROLE`** and the built
meta-test gates the privacy package before any probe runs [NFR14.73]. A probe
suite running as superuser reports a **pass**, which is the worst available
outcome.

---

## 5. The ZAP baseline

`team.md`: *"one scripted DAST pass before the Play internal-track
promotion: an OWASP ZAP baseline scan against the staging host, driven from
the committed OpenAPI 3.1 schema."* **Checked: no ZAP reference exists in any
workflow.** This is real work.

**Design: a job in the release workflow, before the internal-track
promotion** [NFR14.75] — not in `check.yml`. A DAST pass on every push is
slow, scans an environment that may be mid-deploy, and becomes the gate that
gets disabled.

```
# zap-api-scan.py, NOT zap-baseline.py -- corrected 2026-10-25.
# An earlier draft wrote `zap-baseline.py -f openapi`, and
# baseline has no -f option and performs no schema import at all.
# The API script is the one that reads an OpenAPI document.
zap-api-scan.py -t <the committed openapi.json> -f openapi \
                -z "-config <...>"
# High or above blocks the promotion; lower annotates [NFR14.76].
# Report retained as a build artifact [NFR24.25], not attached to
# the Play release record [NFR24.26].
```

**The two-speed threshold follows the CVE model `team.md` already
established, for the reason it already states**: a solo developer who hits an
unactionable finding mid-release with no triage path bypasses the gate once,
and after one bypass it is decoration.

### What a green ZAP run does and does not mean

**Design statement, and the most important sentence in this section: the
scan reaches only the unauthenticated surface** [NFR14.77]. It is driven from
the schema with **no token**, so what it verifies is that **every
authenticated route refuses without one** — which is real and worth checking —
and **not** that authenticated routes are free of findings.

**This is stated because a green DAST run is easy to report as "the API
passed a security scan".** For this product it means the front door is locked,
not that the rooms were searched. **No automated verifier distinguishes the
two**, and the requirement exists so the next reader does not have to.

---

## 6. What D5 does not change

- **Authentication, tokens, OTP controls** — untouched; no credential, no
  session, no token.
- **Device identifiers** — untouched. `bundletool` runs in CI and never
  ships, so the DEX scan and manifest allowlist are unaffected [NFR2.16].
- **Money representation** — untouched. The fold stays in Python precisely so
  money arithmetic stays inside `app/money/` [performance § 3].
- **`PUBLIC_ROUTES`** — unchanged at eight, with the count asserted twice.
- **The teacher / platform-administrator boundary** — D5 adds no
  administrator surface, which is worth stating because an analytics unit is
  exactly where one gets proposed.

---

## 7. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| No read accepts a resource id [§ 1] | A schema assertion over the generated document | yes |
| Every figure's **value** is scoped [NFR14.66] | Four probes asserting values, B seeded larger | yes |
| No non-teacher lens reaches these reads [NFR14.67] | Route test + a probe per route | yes |
| No `PUBLIC_ROUTES` entry [NFR14.68] | The two built count assertions | yes |
| No profile field or account id [NFR14.69] | The built `app/contract/privacy.py` gate | yes |
| …and no design decision to add one [NFR14.70] | Review | **no — the honest half** |
| A declined owing seat is absent [NFR14.71] | A probe with a declined **owing** seat | yes |
| No RLS policy needed [NFR14.72] | A recorded decision; the probes enforce it | **no** |
| Non-superuser suite [NFR14.73] | The built meta-test | yes |
| Governance at 25, both directions [NFR10.21] | The built governance pair | yes |
| No migration [NFR10.22] | A file check plus head-revision assertions | yes |
| ZAP against staging from the schema [NFR14.74] | The scan's exit status | yes |
| High blocks, lower annotates [NFR14.76] | Exit code, demonstrated once | yes |
| ZAP covers only unauthenticated surface [NFR14.77] | **None** | **no — stated so a green run is not misread** |

---

## Assumptions & Open Questions

- **§ 1's no-id property is a design choice that could be undone cheaply.**
  Adding `?batch_id=` to filter the dues list would reintroduce the IDOR
  class and the check that goes with it. The schema assertion is what makes
  that a visible decision rather than a drift.
- **§ 2's "seed B larger" rule has no mechanism.** It is a property of how the
  probes are written, enforced by review. A probe seeded the other way passes
  against a leak whenever A's figure dominates — stated so the next person
  writing one knows why the seeding is not arbitrary.
- **The ZAP severity threshold at High is this design's choice**, following
  the CVE model. No upstream artifact sets a ZAP threshold.
- **I could not execute any suite for this stage.** Every claim about a built
  gate is from reading the file, each cited by path. No claim rests on a
  measured run.
