# Logical Components — D5 `knowing-how-it-is-going`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 adds one backend package, one router and two Android features, and
> nothing else.** No table, no migration, no money arithmetic, no job, no
> client dependency.
>
> The one structural decision worth the name is **where the folds live**:
> `app/analytics/` holds pure functions over ledger entries already in hand,
> so the money-shaped logic is testable without a database and the I/O is
> somewhere else. That mirrors why `app/marks/marksheet.py` was split out in
> D4, and for the same reason.

## Sources

- [upstream] `nfr-requirements/tech-stack-decisions.md` — NFR2.15–NFR2.21,
  NFR17.9, NFR18.9, NFR18.10
- [upstream] `functional-design/entities.md` — the four read models
- [upstream] this stage's `performance-design.md` §§ 1, 3
- [code] read 2026-10-25: `app/fees/`, `app/marks/`, `app/teaching/`,
  `app/api/`, `android/src/main/kotlin/com/shikkhokplus/app/feature/`,
  `pyproject.toml`

---

## 1. Backend

```
app/analytics/
  __init__.py
  seats.py       # the owned-seat set: ONE join, no resource id  [security § 1]
  dues.py        # DuesRow assembly; the per_cycle minimum       [BR1.1-BR1.7]
  earnings.py    # the period fold and the trend                [BR2.1-BR2.6]
  upcoming.py    # the next exam, one statement with LIMIT 1     [BR3.1-BR3.4]

app/api/analytics.py   # two routes, teacher lens on both
app/schemas/analytics.py
```

**Which modules may touch a session is the design decision here**, because
the constant-statement property depends on it:

| Module | Session | What it does |
|---|---|---|
| `seats.py` | **yes** | The one owned-seat join, and the one ledger select |
| `upcoming.py` | **yes** | One exam select with `LIMIT 1` |
| `earnings.py` | **no** | Pure fold: entries in, period totals out |
| `dues.py` | **no** | Pure assembly: seats + entries in, `DuesRow[]` out |

**`dues.py` taking no session is the load-bearing row**, and an earlier draft
left it ambiguous. It is where the per-seat loop lives, so it is the one
place a query could be added per row [NFR20.32] — a module that cannot reach
a session **cannot** make that mistake, which turns the N+1 obligation from a
rule into a structural property.

**`earnings.py` holding no I/O** gives the same property the money module and
`app/marks/marksheet.py` have: the double-count test [reliability § 1.1]
needs no database, so the arithmetic is testable at unit speed.

**The join that makes the no-id property true exists once**, in `seats.py`.
Both reads call it, so a later change adding a `batch_id` filter has one
place to be noticed rather than two.

**No new strict mypy island** [NFR17.9]. `app/analytics/` decides no
authorization question: it receives a resolved `TeacherLens` and scopes by
its `owner_id`. The lens resolution is `app.authz`'s, already strict. The
global `disallow_untyped_defs` covers the rest.

**Why not extend `app/fees/`.** The dues view is money-shaped and the
temptation is real. But `app/fees/` owns *writing* fee cycles, claims and
verifications; D5 writes nothing and reads across batches rather than within
one. Adding a read-only cross-batch module there would make the package's
boundary "things to do with money" rather than "the fee lifecycle", and the
strict island on `app.fees.*` would then cover code that decides nothing.

---

## 2. The two routes

| Route | Lens | Returns |
|---|---|---|
| `GET /v1/me/dues` | Teacher | `DuesRow[]`, possibly empty [BR1.5] |
| `GET /v1/me/overview` | Teacher | earnings, trend?, next exam? |

**Neither takes a path or query parameter.** That is the no-id property made
concrete, and the schema assertion of `security-design.md` § 1 is what keeps
it true.

**The `/me/` prefix does not imply it, and that is worth stating because it
reads as if it does.** Checked against the four built `/me/*` routes:
`GET /v1/me/fees` carries a `StudentLens` **and takes an `enrollment_id`
query parameter**; `/me/batches/{enrollment_id}/teaching` and
`/me/enrollments/{enrollment_id}/exams/{exam_id}/marksheet` take path ids.
**The prefix means "scoped to the caller", not "takes no id".** D5's no-id
property is this unit's own, so the schema assertion is load-bearing rather
than a restatement of a convention — a later `/v1/me/dues?batch_id=` would
be perfectly conventional and would reintroduce the class § 1 removes.

**Three blocks in one response rather than three routes**, because they are
one screen and two of the three share the ledger read [performance § 2]. Three
routes would be three seat-set queries for one screen.

**`/v1/me/` rather than `/v1/teacher/`**, following the built `/v1/me`
precedent: the lens decides what "me" means, and a path segment naming a role
would be a second place that knows.

---

## 3. Android

```
feature/dues/      StateMapper, UiState, ui/DuesScreen.kt
feature/overview/  StateMapper, UiState, ViewModel, ui/OverviewScreen.kt
core/network/      AnalyticsDto.kt
```

Matching the built `feature/roster/` convention exactly [NFR18.9]. **No new
dependency** — no charting library [NFR2.17], so the trend renders with
existing Compose primitives or as a list.

**The mapper decides every rendering question**, including the three
absences: whether to show the trend block at all, whether the next-exam block
is a figure or an empty state. **A composable never compares a domain value**
— `if (outstanding > 0)` on the client would be the dues membership rule,
reimplemented where nothing tests it.

Both screens get a row in `docs/delivery/bangla-layout-check.md` [NFR18.10].
**The earnings figure is the string to check hardest**: a money amount in
Bangla numerals under a long Bangla label, on the screen a teacher opens
most.

---

## 4. CI

One new step in `release-android.yml` — the download-size gate [performance
§ 5] — and one new job, the ZAP baseline [security § 5]. **`bundletool` is
pinned and checksum-verified** [NFR2.21], installed in the step that uses it.

**Nothing changes in `check.yml`.** The size gate and the DAST pass both
measure a nearly-finished app, which is why they belong at release rather
than on every push.

---

## 5. What is reused unchanged

| Need | Built thing |
|---|---|
| Money arithmetic | `app/money/` — `derive()`, `Money` |
| Authorization | `TeacherLens`, the route-enumeration gate |
| Privacy enforcement | `app/contract/privacy.py` |
| Error taxonomy | the closed five-class hierarchy |
| Session scope | `app/api/deps.py`'s request-scoped session |
| Test harness | pytest, testcontainers, real PostgreSQL 16 |

---

## Assumptions & Open Questions

- **The package name `app/analytics/` is this design's choice.** No upstream
  artifact names it. `app/insights/` and `app/reporting/` were considered;
  "analytics" matches the vocabulary of FR8's requirements.
- **Two routes rather than one** is also this design's choice. One combined
  route would share the seat-set query between dues and overview, but the two
  are different screens with different refresh patterns and a combined
  response would make the dues list a sub-object of a thing called "overview".
- **`/v1/me/dues` and `/v1/me/overview` are proposed paths.** Nothing
  upstream fixes them.
- **No figure here was measured.** D5's code does not exist yet.
