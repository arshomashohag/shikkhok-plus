# Observability Requirements — D5 `knowing-how-it-is-going`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 runs no job, so it has no freshness to alert on — and that removes
> the mechanism every previous unit's observability rested on.** D3's and
> D4's requirements were built around `job_heartbeat` and the
> absence-of-success alert. D5 has nothing to stamp.
>
> What replaces it is narrower and mostly prohibitive: **a dues list is a
> list of named people and their debts, and it must never reach a log
> line.** This is the unit where the logging prohibitions carry the most
> weight and have the fewest automated verifiers, and § 1 says so rather
> than implying coverage.

> **`NFRx.y` IDs are GLOBAL.** D5's new IDs start above each base's
> high-water mark after D4. A bare `NFR24.13` or `NFR25.23` below is a
> **citation**, never an ID defined here.

## Sources

- [upstream] `.../functional-design/rules.md` — BR1.1, BR2.1, BR4.4
- [upstream] `.../functional-design/entities.md` — the `DuesRow` fields
- [prior] D4's `nfr-requirements/observability-requirements.md` — NFR24.13–
  NFR24.17's prohibitions, NFR25.x's alerting model
- [prior] D4's infrastructure spec § 3.3 — the freshness enumeration this
  unit does not extend
- [team] `team.md` Deployment — the logging prohibitions
- [code] read 2026-10-25: `app/fees/commands.py` (the heartbeat and freshness
  mechanism D5 does not use), `app/audit/log.py`, `app/auth/ceilings.py`

---

## 1. What must never reach a log line

**NFR24.21** — **No child's name reaches a log line in this unit.** The dues
read handles a teacher-recorded display name per row, and the obvious
diagnostic — logging the rows returned when a teacher reports a wrong figure
— writes a list of named children into the host's stdout. **Verifier: review
of D5's call sites. NOTHING AUTOMATED CHECKS THIS**, which is the same honest
half D4 recorded for NFR24.13, and it carries more weight here because a dues
row pairs a name with a debt.

**NFR24.22** — **No money amount reaches a log line.** Not an outstanding
balance, not an earnings total, not a trend point. **Verifier: review. No
automated scanner exists.**

**NFR24.23** — **No dues row reaches a log line, even in aggregate.** Logging
"returned 14 rows" is permitted; logging the rows is not, and neither is
logging the seat ids, because an enrollment id plus a timestamp in a log the
teacher's own support request quotes is a re-identification path. **Verifier:
review.**

**NFR24.24** — An error raised during an analytics read logs the request or
correlation id and the error code, and **never the figure being computed, the
seat set, or any row**. **Verifier: a test asserting the error path's log
record carries no `enrollment_id` and no amount** — this is the one of the
four that gets a test, following D4's pattern where the conflict path was
testable because its shape was known.

---

## 2. No job, and therefore no freshness

**NFR25.28** — D5 registers **no** job, writes **no** `job_heartbeat` row,
and extends the freshness check **not at all**. The enumeration D4 built
reads every registered row, so D5 adding none means D5 adds nothing to that
alert — which is the correct outcome and is stated because D4's option-B
decision was argued on the grounds that later units would get coverage for
free. **Here the free coverage is of nothing, and that is right.**
**Verifier: a file check that D5 adds no `stamp_heartbeat` call.**

**NFR25.29** — D5 defines **no new alert**. The two conditions worth alerting
on in an analytics unit — a figure that is wrong, and a figure that is
unavailable — are respectively undetectable without a second source of truth,
and already covered by the ordinary error path. **Verifier: none, and none is
claimed.** Stated so the absence is a decision rather than an oversight,
because an analytics unit is exactly where someone would add a threshold
alert on a revenue figure, and a threshold set now would be invented.

---

## 3. What an operator can answer

**NFR25.30** — A support question of the form *"this teacher says their
earnings total is wrong"* is answerable **without logs**, by re-running the
same read against the same data. The figures are derived rather than stored
[BR1.4, BR4.2], so there is no cached value to diverge from its source and
no point-in-time state to reconstruct. **Verifier: this follows from the
derived-not-stored design; nothing additional is built, and the requirement
records why no audit trail is added.**

**NFR25.31** — The existing append-only authentication audit log is
**unchanged**. D5 adds no auditable event: reading one's own business figures
is not an action worth recording, and recording it would write a per-teacher
access pattern into an append-only store for no stated use. **Verifier: a
file check that D5 adds no audit-log call.**

---

## 4. The ZAP baseline's output

**NFR24.25** — The ZAP baseline's report is retained as a build artifact of
the release run [security § 5]. **Verifier: its presence in the workflow's
uploaded artifacts.** Without retention a blocked promotion names a severity
and nothing a person can read to triage it.

**NFR24.26** — The ZAP report is **not** attached to the Play release record
and is not published. It describes the staging host's surface, which is
infrastructure detail rather than release documentation. **Verifier:
review.**

---

## Assumptions & Open Questions

- **Three of the four logging prohibitions have no automated verifier**
  [NFR24.21–NFR24.23], and that is stated rather than implied. The project
  has no log scanner, and building one for this unit alone would be a
  mechanism narrower than the rule it enforces. **The risk is real and is
  highest here**, because a dues row is a name paired with a debt.
- **NFR25.29 declines to set a revenue threshold alert.** The question was
  asked: a teacher's earnings dropping to zero could be a collection problem
  or a quiet month, and nothing in this product distinguishes them. A
  threshold set now would be invented, which is the shape `team.md` rejects.
- **No figure in this document was measured.** D5's code does not exist yet.
