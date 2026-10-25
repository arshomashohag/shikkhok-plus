# Security Requirements — D5 `knowing-how-it-is-going`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 stores nothing and therefore protects nothing new. What it does is
> aggregate**, and aggregation is its own disclosure surface: a figure
> computed across batches can reveal a batch the viewer does not reach, and a
> list of people who owe money is the most socially consequential list this
> product renders.
>
> Three things carry this unit's security weight, and none is a new
> mechanism:
>
> 1. **Every figure is scoped by the lens's `owner_id`** — the aggregate is
>    the attack surface, because a wrong scope leaks a figure rather than a
>    row, and a figure has no row-level gate to stop it.
> 2. **A dues list is a list of people**, so it is the natural place to leak
>    a student-authored name to a teacher. The built field-level gate catches
>    the schema; nothing catches a designer deciding the list should show
>    photos.
> 3. **The ZAP baseline lands here**, and D5 is the unit that owns it.

> **`NFRx.y` IDs are GLOBAL across units.** D5's new IDs start above the
> high-water mark each base reached after D4, recomputed across both records
> and the whole `aidlc/` tree. A bare `NFR14.48`, `NFR14.64` or `NFR10.18`
> below is a **citation**, never an ID defined here.

## Sources

- [upstream] `.../functional-design/rules.md` — BR1.7, BR2.5, BR4.1, BR4.4
- [upstream] `.../functional-design/entities.md` — the `DuesRow` field notes
- [upstream] `.../functional-design/functional-spec.md` §§ 5, 7, 7a
- [prior] `261016-.../inception/requirements-analysis/requirements.md` —
  NFR10, NFR11, NFR14, and the privacy boundary's three layers
- [prior] D4's `nfr-design/security-design.md` — the probe-matrix shape this
  unit follows rather than reinvents
- [team] `team.md` Deployment — *"one scripted DAST pass before the Play
  internal-track promotion: an OWASP ZAP baseline scan against the staging
  host, driven from the committed OpenAPI 3.1 schema"*
- [code] read 2026-10-25: `app/authz/lenses.py` (`TeacherLens.owner_id`),
  `app/contract/privacy.py`, `app/contract/routes.py`,
  `tests/privacy/test_profile_probes.py`, `app/governance/dispositions.py`,
  `.github/workflows/release-android.yml`, `.github/workflows/check.yml`

---

## 1. The aggregate is the attack surface

**NFR14.65** — Every figure in this unit is scoped by the **lens's
`owner_id`** and never by a batch id, enrollment id or teacher id taken from
the request. `TeacherLens` carries `owner_id` precisely so *"the lens object
handed to a handler **is** the scoping value"* [`app/authz/lenses.py:31-41`].
**Verifier: a probe per read — two teachers with disjoint batches and
different receipts each read only their own figures.**

**NFR14.66** — **An aggregate leaks differently from a row, and that is why
this requirement exists separately from NFR14.65.** A wrong scope on a row
query returns a row someone can point at; a wrong scope on a sum returns a
**number** that looks correct and discloses another teacher's revenue with no
field to inspect. **Verifier: the probe asserts the figure's VALUE, not merely
that a response came back** — teacher A's earnings must equal A's own
receipts exactly, computed in the test from A's seeded data. A probe asserting
only "a 200 with a number" passes against a figure summed across both
teachers.

**NFR14.67** — No read in this unit is reachable by a `StudentLens`,
`GuardianLens` or `InvitationLens`. The dues view, the earnings and the trend
are the teacher's business data. **Verifier: the built route-enumeration test
asserts every route resolves a lens; a probe per route asserts a non-teacher
lens is refused with the shared `NOT_AVAILABLE`.**

**NFR14.68** — D5 adds **no** entry to `PUBLIC_ROUTES`. It holds eight entries
with the count asserted at `tests/contract/test_route_lenses.py:76,104`, so an
addition fails `make check` rather than passing quietly. **Verifier: the two
built assertions, with no new mechanism.**

---

## 2. A dues list is a list of people

**NFR14.69** — No response in this unit carries an owner-private profile field
or a global account identifier. A dues row exposes an **`enrollment_id`** and
the **teacher-recorded** display name, never `student_account_id` and never a
student-authored name, photo reference or address. **Verifier: the built gate
in `app/contract/privacy.py`, which iterates the generated OpenAPI document
and reads the lens from the route — so a D5 schema violating this fails
`make check` without a per-endpoint test being remembered.**

**NFR14.70** — The gate catches the schema and **nothing catches a design
decision**. Stated plainly because this is the honest half: a roster, and now
a dues list, is the most natural place in the product to render a student's
photo beside their debt. That decision was already made against [ADR-001] and
the field-level gate is its mechanical half; **the rest is review, and there
is no automated verifier.**

**NFR14.71** — A declined seat never appears in the dues view, whatever it
owes [BR1.7]. **Verifier: a probe with a declined seat carrying an
outstanding balance, asserting its absence.** A test using only pending and
accepted seats cannot distinguish this from a query missing the clause.

---

## 3. Row-level security: the decision and why it is unchanged

**NFR14.72** — D5 adds **no** row-level security policy, because it creates
no table. The decision inherited from D3 and D4 stands unexamined only in the
sense that there is nothing new to examine: RLS exists on `profile` alone
because `profile` has a column naming its reader, and D5 introduces no table
and therefore no such column. **Verifier: the decision is recorded; what is
verified is the probe suite of § 1 and § 2, which is what actually enforces
the boundary.**

**NFR14.73** — D5's reads run as the same granted non-superuser `APP_ROLE`
and the built meta-test gates the privacy package before any probe runs
[`tests/privacy/test_rls_meta.py`]. **Verifier: the built meta-test, with no
new mechanism.** Restated rather than omitted because a probe suite running
as a superuser reports a **pass**, which is the worst available outcome, and
an absent section reads to the next person as an unconsidered gap.

---

## 4. Governance: the absence that must be asserted

**NFR10.21** — D5 creates no table, so the governance manifest stays at **25**
entries and no new disposition or retention class is written. **Verifier: the
built `tests/db/test_governance.py`, which asserts in BOTH directions — and
the second direction is the one that matters here, because a stale entry
naming a table that does not exist is exactly what a unit adding nothing could
produce by copy-paste.**

**NFR10.22** — D5 ships **no migration**. **Verifier: a file check that
`migrations/versions/` carries no new revision, plus the head-revision
assertions that are deliberately hand-updated per unit.**

---

## 5. The ZAP baseline, which this unit owns

`team.md` is specific: *"one scripted DAST pass before the Play
internal-track promotion: an OWASP ZAP baseline scan against the staging host,
driven from the committed OpenAPI 3.1 schema."*

**Checked 2026-10-25: no ZAP reference exists in any workflow.** This is real
work, not an inherited control.

**NFR14.74** — A ZAP baseline scan runs against the **staging host**, driven
from the **committed `openapi.json`**. Both prerequisites exist: staging
serves (its CloudFront 502 was resolved earlier by issuing a real origin
certificate) and the schema is committed and kept current by the schema-diff
gate. **Verifier: the scan's own exit status.**

**NFR14.75** — The scan is **not a merge gate**. It runs before the
internal-track promotion, which is where `team.md` places it. A DAST pass on
every push would be slow, would scan an environment that may be mid-deploy,
and would be the kind of gate that gets disabled. **Verifier: its placement in
the release workflow rather than in `check.yml`.**

**NFR14.76** — A ZAP finding at **High** or above blocks the promotion; lower
severities annotate. This follows the two-speed model `team.md` already
established for dependency CVEs, and for the same stated reason: a solo
developer who hits an unactionable finding mid-release with no triage path
bypasses the gate once, and after one bypass it is decoration. **Verifier: the
gate's exit code, demonstrated once against a deliberately lowered
threshold.**

**NFR14.77** — The scan's **authentication posture is stated rather than
assumed**: a baseline scan driven from the schema reaches only unauthenticated
surface unless given a token, and **D5 does not give it one**. What it
therefore verifies is that **no authenticated route answers without a
token** — which is real and is the thing most worth checking — and **not**
that authenticated routes are free of findings. **Verifier: none beyond the
scan; this requirement exists so the next reader does not mistake a green ZAP
run for coverage of the authenticated surface.**

---

## 6. What D5 does not change

Stated so a reader does not look for a decision made elsewhere:

- **Authentication, tokens and OTP abuse controls** [NFR12, NFR13] —
  untouched. D5 adds no credential, no session, no token.
- **Device identifiers** [NFR11] — untouched. D5 adds no SDK and no new
  Android dependency beyond `bundletool` in CI, which never ships in the app.
- **Money representation** [NFR9] — untouched. D5 adds no arithmetic to
  `app/money/` [BR4.3], and the built import-boundary checks already fail
  `make check` on raw `decimal` outside that package.
- **Encryption at rest** [NFR10] — untouched. D5 adds no tier and no store.
- **The teacher / platform-administrator boundary** [TC-14] — D5 adds no
  administrator surface. Worth stating here because an analytics unit is
  exactly where one would be proposed.

---

## 7. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| Every figure scoped by `owner_id` [NFR14.65] | A probe per read, two teachers | yes |
| The figure's **value** is right, not merely present [NFR14.66] | Equality against seeded data | yes |
| No non-teacher lens reaches these reads [NFR14.67] | Route test + a probe per route | yes |
| No `PUBLIC_ROUTES` entry [NFR14.68] | The two built count assertions | yes |
| No profile field or account id [NFR14.69] | The built `app/contract/privacy.py` gate | yes |
| …and no design decision to show one [NFR14.70] | Review | **no — stated as the honest half** |
| A declined seat is absent [NFR14.71] | A probe with a declined owing seat | yes |
| No RLS policy needed [NFR14.72] | Recorded; the probes enforce the boundary | **no — a recorded decision** |
| The suite is non-superuser [NFR14.73] | The built meta-test | yes |
| Governance stays at 25, both directions [NFR10.21] | The built governance pair | yes |
| No migration [NFR10.22] | A file check plus head-revision assertions | yes |
| ZAP runs against staging from the schema [NFR14.74] | The scan's exit status | yes |
| ZAP is not a merge gate [NFR14.75] | Its placement in the release workflow | yes |
| High blocks, lower annotates [NFR14.76] | Exit code, demonstrated once | yes |
| ZAP covers only unauthenticated surface [NFR14.77] | **None** | **no — stated so a green run is not misread** |

---

## Assumptions & Open Questions

- **No threat model document exists for this product.** Searched both
  records' `inception/` trees and `docs/`. These requirements derive from the
  stated constraints and the built gates, which is the same basis D1 through
  D4 used.
- **NFR14.77's limit is the one most likely to be misread.** A green ZAP
  baseline is easy to report as "the API passed a security scan". It means
  the unauthenticated surface passed, which for this product is mostly the
  assertion that authenticated routes refuse without a token.
- **The ZAP severity threshold at High is this document's choice**, following
  the two-speed CVE model `team.md` established. No upstream artifact sets a
  ZAP threshold.
- **I could not execute any test suite for this stage.** Every claim about a
  built gate is from reading the file, and each is cited by path. No claim
  here rests on a measured run.
