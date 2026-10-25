# Observability Design — D5 `knowing-how-it-is-going`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5's observability design is mostly a design for NOT logging**, and that
> is a real design rather than an absence. A dues row pairs a child's name
> with a debt, and the obvious diagnostic for "this teacher says the figure
> is wrong" is to log the rows that produced it.
>
> **Three of the four prohibitions have no automated verifier** [§ 1], which
> is stated rather than implied. The one that does get a test is the error
> path, because its shape is known in advance.
>
> **D5 registers no job, so the freshness mechanism every previous unit built
> on has nothing to stamp** — and § 2 explains why that is the correct
> outcome of D4's enumeration decision rather than a gap it left.

## Sources

- [upstream] `nfr-requirements/observability-requirements.md` — NFR24.21–
  NFR24.26, NFR25.28–NFR25.31
- [upstream] `functional-design/rules.md` — BR1.1, BR1.4, BR4.2
- [upstream] this stage's `security-design.md` § 5 — the ZAP job
- [prior] D4's infrastructure spec § 3.3 — the freshness enumeration
- [code] read 2026-10-25: `app/fees/commands.py` (heartbeat and freshness),
  `app/audit/log.py`, `app/errors/handler.py`

---

## 1. The design for not logging

| Prohibition | Why it is reachable here | Verifier |
|---|---|---|
| No child's name [NFR24.21] | A dues row carries one per seat | **review only** |
| No money amount [NFR24.22] | Every figure this unit produces | **review only** |
| No dues row, even seat ids [NFR24.23] | The natural "why is this figure wrong" diagnostic | **review only** |
| The error path [NFR24.24] | Its shape is known in advance | **a test** |

**Design statement: a log line from this unit carries a count and never a
collection.** `"dues read returned 14 rows"` is permitted and useful;
`"dues read returned [...]"` is the prohibition. The distinction is
mechanical enough to review for, which is the most this unit gets.

**Why seat ids are prohibited too** [NFR24.23], since they are not names: an
`enrollment_id` plus a timestamp, in a log a teacher quotes into a support
request, is a re-identification path — the teacher knows which seat they were
looking at. The id is only pseudonymous while the context is absent, and a
log line supplies the context.

**Design statement: the error path logs the correlation id and the error
code, and never the figure, the seat set or any row** [NFR24.24]. **Verifier:
a test asserting the emitted record carries no `enrollment_id` key and no
decimal-shaped value.** This is the one of the four that is testable because
the error path is a single known site; the other three are "every call site
anyone adds", which is what makes them review-only.

**No log scanner is built**, and that is a decision: one built for this unit
would be narrower than the rule it enforces and would imply coverage of the
three review-only rows. The honest position is that **the risk is real,
highest here of any unit, and carried by review**.

---

## 2. No job, and why that is the right answer

D4 chose option B for the freshness check — enumerate every registered
`job_heartbeat` row — partly on the argument that **later units would get
coverage for free**. D5 is the first test of that argument and the answer is
a little surprising: **D5 registers no job, so it gets coverage of nothing,
and that is correct** [NFR25.28].

**Design statement: D5 writes no heartbeat, adds no cron entry and changes
the freshness check not at all.** The enumeration's value was never "every
unit gets an alert" — it was "a unit that *does* register a job cannot
forget to wire it in". A unit with no job needs no wiring.

**Verifier: a file check that D5 adds no `stamp_heartbeat` call and no cron
entry** [NFR2.20].

---

## 3. The alert that is deliberately not defined

**Design statement: D5 defines no alert** [NFR25.29].

An analytics unit is exactly where a threshold alert on a revenue figure gets
proposed, so the reasoning is recorded rather than left as silence:

- **A wrong figure is undetectable without a second source of truth.** There
  is none — the ledger is the only record, and an alert comparing a figure to
  itself detects nothing.
- **An unavailable figure is already an error**, surfaced through the
  ordinary error path [NFR19.51].
- **A figure that drops to zero** could be a collection problem or a quiet
  month, and nothing in this product distinguishes them. **A threshold set
  now would be invented**, which `team.md` rejects.

---

## 4. What an operator can answer without logs

**Design statement: every figure is reproducible by re-running the read**
[NFR25.30], because nothing is stored or cached [BR1.4, BR4.2]. There is no
materialised value that can diverge from its source and no point-in-time
state to reconstruct.

**This is why the logging prohibitions cost so little.** In a product with
cached rollups, "the figure was wrong at 14:05" needs a log to investigate.
Here it needs the same read, run again — and a support question is answerable
with no personal data leaving the database.

**The authentication audit log is unchanged** [NFR25.31]. Reading one's own
business figures is not an auditable event, and recording it would write a
per-teacher access pattern into an append-only store for no stated use.

---

## 5. The ZAP report

**Retained as a build artifact of the release run** [NFR24.25]: without it a
blocked promotion names a severity and nothing a person can triage.

**Not attached to the Play release record and not published** [NFR24.26]: it
describes the staging host's surface, which is infrastructure detail rather
than release documentation, and publishing a DAST report tells a reader where
the host is and what was scanned.

---

## 6. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| No child name in a log [NFR24.21] | Review | **no** |
| No money amount in a log [NFR24.22] | Review | **no** |
| No dues row or seat id in a log [NFR24.23] | Review | **no** |
| The error path logs neither [NFR24.24] | A test on the emitted record | yes |
| No heartbeat, no cron [NFR25.28] | A file check | yes |
| No alert defined [NFR25.29] | **None, and none claimed** | **no — a recorded decision** |
| Figures reproducible by re-reading [NFR25.30] | Follows from derived-not-stored; nothing built | **no** |
| Audit log unchanged [NFR25.31] | A file check | yes |
| ZAP report retained [NFR24.25] | Its presence in uploaded artifacts | yes |
| ZAP report not published [NFR24.26] | Review | **no** |

**Six of ten are not automated**, which is high for this record and is the
honest count. Five of the six are prohibitions — statements that something
does not happen — and a prohibition's verifier is review unless a scanner
exists.

---

## Assumptions & Open Questions

- **The three review-only prohibitions are this unit's largest unverified
  risk**, and it is larger here than in D4: a dues row pairs a name with a
  debt, which is more sensitive than either alone.
- **§ 2's observation is milder than an earlier draft made it**, corrected
  after review. That draft called D4's option-B argument "true but vacuous"
  for a unit with no job, which understates what enumeration bought: it also
  makes an **absent** heartbeat observable, and that is the same mechanism —
  read from the other direction — as D5's own file check for the absence of a
  `stamp_heartbeat` call. So D5 is not evidence the argument oversold itself;
  it is a unit where the free coverage happens to cover nothing, which is the
  correct outcome rather than a gap. **Not a learnings-gate item.**
- **No figure here was measured.** D5's code does not exist yet.
