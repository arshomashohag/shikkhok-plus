# Monitoring Design — D5 `knowing-how-it-is-going`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 adds no alert, no metric, no dashboard and no log sink.** That is four
> absences in a row, and each is a decision with a reason rather than
> something nobody got to — § 1 and § 2 give the reasons, because an
> analytics unit is precisely where a revenue alert gets proposed.
>
> **What it does add is a prohibition with no automated verifier**, and this
> document's main job is to say that plainly rather than let a table of
> green rows imply coverage: **a dues row pairs a child's name with a debt,
> and nothing mechanical stops it reaching a log line.**

## Sources

- [upstream] `nfr-design/observability-design.md` — the full design this
  implements
- [upstream] `nfr-requirements/observability-requirements.md` — NFR24.21–
  NFR24.26, NFR25.28–NFR25.31
- [upstream] this stage's `infrastructure-specification.md` § 2
- [prior] D4's infrastructure spec § 3.3 — the freshness enumeration
- [code] read 2026-10-25: `app/fees/commands.py`, `app/audit/log.py`,
  `app/errors/handler.py`, `.github/workflows/deploy.yml`

---

## 1. No alert, and the reasoning rather than the conclusion

**D5 defines no alert** [NFR25.29]. The two things that could go wrong with
an analytics figure are:

| Failure | Why no alert |
|---|---|
| The figure is **wrong** | Undetectable without a second source of truth. The ledger is the only record; an alert comparing a figure to itself detects nothing |
| The figure is **unavailable** | Already an error through the ordinary path [NFR19.51], surfaced to the caller rather than to a log |

**And the one that would be proposed**: a threshold on revenue dropping. A
teacher's earnings falling to zero is either a collection problem or a quiet
month, and **nothing in this product distinguishes them**. A threshold set
now would be invented, which `team.md` rejects in as many words.

**Verifier: none, and none is claimed.** Recorded so the absence is a
decision a reader can disagree with rather than a gap.

---

## 2. No heartbeat, and why that is right

**D5 registers no job** [NFR25.28], so there is no `job_heartbeat` row, no
staleness window and nothing for D4's freshness enumeration to read.

**That enumeration's value is unchanged by this**: it makes a unit *with* a
job unable to forget the wiring, and it makes an **absent** heartbeat
observable. D5 simply has no job — which its own file check asserts, from
the same direction.

**Verifier: a file check that D5 adds no `stamp_heartbeat` call and no cron
entry.**

---

## 3. The prohibition with no verifier

**This is the section that matters.** Three of this unit's four logging rules
are enforced by review alone [NFR24.21–NFR24.23]:

- no child's name in a log line;
- no money amount in a log line;
- no dues row, **including bare seat ids**.

**The seat-id rule is the one that looks excessive and is not.** An
`enrollment_id` is pseudonymous only while its context is absent. In a log
line a teacher quotes into a support request — *"I looked at the dues screen
at 14:05 and the figure was wrong"* — the context arrives with the quote, and
the id resolves to a child.

**The design rule is mechanical enough to review for**: a log line from this
unit carries a **count** and never a **collection**. `"dues read returned 14
rows"` is useful and permitted; the rows are not.

**One of the four is testable and is tested** [NFR24.24]: the error path is a
single known site, so a test asserts its emitted record carries no
`enrollment_id` key and no decimal-shaped value.

**No log scanner is built, and that is a decision.** One built for this unit
would be narrower than the rule it enforces, and — worse — its existence
would imply coverage of the three review-only rows. **The honest position is
that the risk is real, is highest in this unit of any so far, and is carried
by review.**

---

## 4. What an operator can do without logs

**Every figure is reproducible by re-running the read** [NFR25.30], because
nothing is stored or cached [BR1.4, BR4.2]. A support question of the form
*"this teacher says the total is wrong"* is answered by running the same read
against the same data — **with no personal data leaving the database**.

**This is why the prohibitions of § 3 cost so little.** In a product with
cached rollups, "the figure was wrong at 14:05" needs a log to investigate,
and the pressure to log the rows would be real. Here the investigation is the
read itself.

**The authentication audit log is unchanged** [NFR25.31]. Reading one's own
business figures is not an auditable event, and recording it would write a
per-teacher access pattern into an append-only store for no stated use.

---

## 5. The ZAP report

| Property | Decision | Requirement |
|---|---|---|
| Retained as a build artifact | **yes** — a blocked promotion must be triageable | NFR24.25 |
| Attached to the Play release record | **no** | NFR24.26 |
| Published anywhere | **no** — it names the host and what was scanned | NFR24.26 |

**A scan against an unreachable host must FAIL rather than report no
findings.** That is the same precondition shape as the Gitleaks shallow-clone
guard and the Docker check added earlier this session, and it is specified in
`cicd-pipeline.md` § 3 as an assertion rather than left to ZAP's own exit
behaviour.

---

## 6. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| No child name in a log [NFR24.21] | Review | **no** |
| No money amount in a log [NFR24.22] | Review | **no** |
| No dues row or seat id in a log [NFR24.23] | Review | **no** |
| The error path logs neither [NFR24.24] | A test on the emitted record | yes |
| No heartbeat, no cron [NFR25.28] | A file check | yes |
| No alert defined [NFR25.29] | **None, and none claimed** | **no** |
| Figures reproducible by re-reading [NFR25.30] | Follows from derived-not-stored | **no** |
| Audit log unchanged [NFR25.31] | A file check | yes |
| ZAP report retained [NFR24.25] | Its presence in uploaded artifacts | yes |
| ZAP report not published [NFR24.26] | Review | **no** |

**Six of ten are unautomated.** That is the highest proportion of any unit in
this record and it is the honest count: **five of the six are prohibitions**,
and a prohibition's verifier is review unless a scanner exists.

---

## Assumptions & Open Questions

- **The three review-only prohibitions are this unit's largest unverified
  risk**, and larger here than in D4 — a dues row pairs a name with a debt,
  which is more sensitive than either alone. **For the human**, if a log
  scanner is ever wanted, this is the unit that would justify it.
- **"A count and never a collection" is the reviewable form of the rule.** It
  is stated as a design rule rather than a requirement because no mechanism
  enforces it; what makes it useful is that it is checkable by eye at a diff.
- **No figure in this document was measured.** D5's code does not exist yet.
