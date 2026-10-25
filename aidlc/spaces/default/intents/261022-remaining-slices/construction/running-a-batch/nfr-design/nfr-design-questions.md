# NFR Design — Questions

**Stage**: nfr-design (3.3)
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

## How this stage was answered

D2's NFR requirements are seventeen derived IDs over three axes, and almost
all of them are satisfied by mechanisms that already exist. The design work is
choosing **where the new count attaches** and **what the screens must not
do** — and one of those is a navigation decision with no server-side backstop.

Each answer is settled from an upstream requirement or a direct read of the
built code, and the source is named.

---

## Q1. Where does `accepted_count` attach?

[Answer]: **A second grouped aggregate in `list_batches`, beside the existing
one.** `list_batches` already runs three bounded statements — the batches, one
grouped count over `batch_id.in_(batch_ids)`, one grouped subject fetch — and
merges them in Python.

The count of accepted seats is the same grouped shape with a decision
predicate. Two options and the second is right:

| Option | Verdict |
|---|---|
| A fourth statement, grouped the same way | Acceptable; one more bounded query |
| **The same statement as `enrollment_count`**, with a conditional aggregate | **Chosen** — one pass over the same rows yields both numbers |

A conditional aggregate (`count(*)` filtered by the decision predicate,
alongside the unfiltered `count(*)`) gives numerator and denominator from one
grouped scan, which is strictly better and no more complex to read.

[NFR20.7] [NFR20.8] [code: `app/batches/service.py:459-492`]

## Q2. Does the roster query change shape?

[Answer]: No. The two new fields are columns of the `Enrollment` rows the seat
select already reads, so there is no join and no extra statement. The
ownership check stays its own statement, as it is today.

[NFR20.10] [code: `app/batches/service.py:_owned_batch`, `list_roster`]

## Q3. What enforces "the client never counts"?

[Answer]: **The response carrying the number, plus a mapper test.** There is
no mechanism that can stop a composable summing a list — the rule is enforced
by the count being *available*, so counting is the longer path rather than the
obvious one, and by a test asserting the mapper reads the field.

Stated honestly: this is weaker than D1's structural controls. The money
boundary is a type and an import gate; this is a field and a test.

[NFR20.9] [BR1.3]

## Q4. How is the Back-after-switch obligation enforced?

[Answer]: **By making the switch a selection rather than a navigation push**,
and by a Robolectric test. This is the one D2 obligation with **no
server-side backstop**: both requests are legitimately authorized, so nothing
on the server can tell that Back took a guardian to the wrong child.

The design choice is what makes it testable: a switcher that replaces the
selected child within one screen has no back entry to return to. A switcher
that navigates to a per-child route would need explicit stack manipulation,
which is the thing that gets forgotten.

[NFR14.30] [BR4.2] [AC9.4.2]

## Q5. What stops the roster leaking a retained name?

[Answer]: **The mapper chooses the label**, so the screen never sees both. A
`displayLabel` decided server-side-of-the-mapper means the composable has no
name to render for a declined row even by accident.

The alternative — passing both name and number and letting the screen pick —
is the same shape as the layer-boundary slip D1 made and corrected.

[NFR14.28] [BR2.3] [ADR-012]

## Q6. Does D2 add any resilience pattern?

[Answer]: **No.** No new dependency, no new failure mode. The error taxonomy
maps every failure to a class with a server-provided `retryable`, and D2's
screens read that field rather than inferring from a status code.

The one thing worth naming: **a failed removal is not a transient failure**.
Both refusals are `ConflictError` and non-retryable, so the screen must not
offer a retry that cannot succeed.

[NFR14.31] [BR3.2] [team: Error handling]

## Q7. Does D2 change any logical component?

[Answer]: No component, one package. `feature/guardian` is new on the client;
the server change is two fields on `app/schemas/batches.py` and one aggregate
in `app/batches/service.py`, both inside `batches-and-enrollment`.

[components.md] [tech-stack-decisions.md]

## Assumptions & Open Questions

- **Checked, with one caveat worth stating.** PostgreSQL 16 supports
  `count(*) FILTER (WHERE ...)` and SQLAlchemy exposes it as
  `.filter()` on a function element, so the conditional aggregate in Q1 is
  expressible. But **this codebase uses no `FILTER` aggregate today**, so it
  would be a first. The design fixes the property — numerator and denominator
  from one grouped pass — and leaves the form to Code Generation: two grouped
  statements would also satisfy NFR20.7, at one more bounded query.
- **Assumed**: the roster's two new enums serialize as lowercase strings
  matching `status`.
- **Open, and D5's**: pagination. D2's server-side count is what makes it a
  later additive change; the cross-batch dues list is where it first matters.
