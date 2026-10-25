# NFR Requirements — Questions

**Stage**: nfr-requirements (3.2)
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

## How this stage was answered

D2 is typed `ui`, so `produces_kinds` asks for performance, security and
tech-stack only — no scalability, reliability or observability document. That
is the right shape: D2 adds no row to any table, no job, no service, and no
alert. It adds **one response field, two screens' worth of states, and four
new screens**.

So the questions are narrow and specific, and each is answered from an
upstream criterion or a direct read of the built code.

---

## Q1. Does the new `accepted_count` cost a query per batch?

[Answer]: **It must not, and that is the requirement.** `list_batches`
already returns `enrollment_count` computed server-side, so the count is
aggregated in the same statement that lists the batches. `accepted_count` is a
second aggregate over the same rows.

The failure to avoid is a per-batch follow-up query — a teacher with twelve
batches turning one statement into thirteen. That is the N+1 shape, and the
batch list is the first screen a teacher sees after signing in.

[code: `app/batches/service.py:391`] [NFR20 of the prior record]

## Q2. Does the roster need pagination?

[Answer]: **No, and the reason is a bound rather than an omission.** A batch
is one teacher's class; the product's scale ceiling is 100 teachers and a few
thousand students [NFR6], which puts a realistic roster in the tens.

What matters is that the **count is the server's** [BR1.3] precisely so that
adding pagination later does not break it. A client-side count would be wrong
the moment the first page stopped being the whole roster — so the design is
pagination-ready without pagination being built.

[NFR6] [BR1.3]

## Q3. What is the privacy obligation on the roster?

[Answer]: **The roster is teacher-lens, so it carries no `Profile` field** —
already enforced by the schema-wide invariant that iterates every teacher-lens
response schema [D1 BR3.2]. D2 adds two fields to `RosterRowResponse` and
neither is personal data: both are decision enums.

The one D2-specific obligation is sharper: **a declined row shows the number,
not the teacher-typed name** [BR2.3]. The name is retained under the
governance basis and must not be rendered.

[D1 BR3.2] [BR2.3] [ADR-012]

## Q4. Does the guardian child route need a new control?

[Answer]: No. It resolves a `GuardianLens` and finds seats through
`guardian_account_id`, never through the child [NFR14.15]. D1's change already
means a declined guardian link grants no lens, so a declined guardian reaches
nothing — safe **because the lens stops being granted**, not because the query
filters.

What D2 adds is the **screen**, and with it one navigation obligation: Back
after a child switch must not reach the previous child's data [AC9.4.2].

[NFR14.15] [BR4.1] [BR4.2]

## Q5. Is there a new abuse surface?

[Answer]: **No new unauthenticated route.** Every D2 route requires a
session and resolves a lens. The abuse controls that matter — signup
ceilings, OTP ceilings, the byte-identical response — are D1's and untouched.

Worth stating because D1 was the unit that opened an unauthenticated surface,
and the contrast is the point: D2 adds screens over authenticated endpoints.

[D2 scope] [D1 NFR12.x]

## Q6. Does the client gain any business logic?

[Answer]: **No, and three named erosion paths say where it would.** The
layer boundary is the dominant NFR for this unit because every screen renders
a list and a count:

- counting accepted rows client-side [BR1.3];
- `if (count > 0)` to choose an empty state;
- `if (state == DECLINED)` to decide a mark [BR1.1].

D1 made the third slip and corrected it. D2 renders four times as many states.

[TC-9] [D-31] [team: Layer boundaries]

## Q7. Does the tech stack change?

[Answer]: No. Compose, the existing feature-package layout, JUnit and
Turbine, Robolectric for rendering tests. D2 adds one Kotlin package
(`feature/guardian`) and no dependency.

The one thing worth recording is the **Compose coverage measurement**
corrected at D1: screens are excluded from the JaCoCo denominator because
JaCoCo cannot instrument composables under Robolectric, and the ratchet floor
rose to 45.84 as a result. D2 adds four screens, so it is the first unit to
test whether that correction holds.

[codekb: `technology-stack.md`] [D1 code-summary]

## Q8. What must the per-screen checks cover?

[Answer]: Six rows in `docs/delivery/bangla-layout-check.md`, one per screen
[FR0.2]. The riskiest string in D2 is the count — "9 of 12 accepted" is short
in English and its Bangla form carries different digit rendering, which
`Money.format(locale)` already handles for money and nothing handles for a
plain count.

[FR0.2] [TC-15] [D-43]

## Assumptions & Open Questions

- **Assumed**: `accepted_count` is aggregated in the same statement as
  `enrollment_count` rather than added as a second query. The requirement
  below fixes the property; the SQL is Code Generation's.
- **Assumed**: the roster response stays unpaginated in V1, with the
  server-side count making pagination a later additive change rather than a
  breaking one.
- **Open, and D3's**: whether the roster shows a fee column. The response
  already carries `fee_amount`; what a declined seat shows for it is a money
  question with no ledger until D3.
