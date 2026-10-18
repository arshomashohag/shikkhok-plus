# Team Allocation

**Stage**: delivery-planning (2.9)
**Phase**: Inception
**Depth**: Comprehensive

## Sources

- [team] the affirmed Way of Working: "We work **solo**: the agent writes most
  of the code and the user reviews all of it" [OC-1]
- [upstream] `ideation/feasibility/` — no mobs to staff [feasibility: Q1]
- [upstream] the Bolt plan

---

## There is no team to allocate

This is a solo build. One person holds every role — product owner, architect,
reviewer, release manager — and the agent writes most of the code. Inventing a
staffing table here would describe a project that does not exist, so this
artifact records the allocation that is real: **every Bolt, one builder, one
reviewer, the same two parties throughout.**

| Bolt | Builder | Reviewer | Gate |
|---|---|---|---|
| B1 `money-core` | agent | the user | human checkpoint |
| B2 `api-contract` | agent | the user | human checkpoint |
| B3 `identity-and-access` | agent | the user | **skeleton checkpoint** — human, and separate |
| B4 `release-packaging` | agent | the user | human checkpoint |
| B5 `batches-and-enrollment` | agent | the user | human checkpoint |
| B6 `fee-cycles-and-ledger` | agent | the user | human checkpoint |
| B7 `payment-claims-and-verification` | agent | the user | human checkpoint — the last gated one |
| B8 `sessions-and-attendance` | agent | the user | automatic |
| B9 `exams-and-marksheets` | agent | the user | automatic |
| B10 `teacher-insights` | agent | the user | automatic |
| B11 `privacy-and-governance` | agent | the user | automatic — **re-gating recommended**, see the Bolt plan |

## What follows from solo, and is already built into the plan

The staffing constraint is not a footnote here; it shaped several decisions in
earlier stages and they are collected in one place because they are the real
content of this artifact.

- **No Bolt runs concurrently with another.** Construction Execution is serial
  because there is no second worker, not because the DAG forbids it. The
  parallelisable sets recorded at Units Generation describe *reorderability*,
  not simultaneity — they mean a Bolt can be moved without a merge hazard, which
  is useful when an external dependency slips.
- **Review is the only quality gate that sees intent**, and it is one stretched
  reviewer. That is why the plan leans on mechanical gates: the money boundary
  is a type and an import check, the lens is a data dependency and a
  route-enumeration test, the forbidden-identifier set is a manifest allowlist
  and a bytecode scan. Each of those arrives in the Bolt that establishes it, so
  review is the backstop rather than the mechanism.
- **Android depth is the declared weak spot** [OC-3], and five Bolts carry
  Compose work. The plan's compensation is conventional choices, tests an
  unfamiliar reviewer can read, and CI failures rather than review findings —
  not more review.
- **Review latency is a real schedule term and is not in any estimate.** Seven
  Bolts are human checkpoints held by one person who also holds every other
  role. Wall-clock exceeds build time by however long each checkpoint waits.

## Assumptions & Open Questions

- **The teacher-onboarding mechanism for closed testing has no owner and no
  surface.** No admin UI is budgeted, so onboarding pilot teachers almost
  certainly means direct `psql` against production under the affirmed
  named-non-superuser-with-logged-session rule. That is acceptable, but it must
  be decided and runbooked rather than improvised on the day — the alternative
  is an ad-hoc production session against children's data. The standing
  prohibition applies: no production query result containing child-identifying
  data goes into a local file, a chat, or an AI tool context.
