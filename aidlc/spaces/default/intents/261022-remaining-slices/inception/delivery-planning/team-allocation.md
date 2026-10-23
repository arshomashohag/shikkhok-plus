# Team Allocation

**Stage**: delivery-planning (2.9)
**Record**: 261022-remaining-slices

> Who builds each Bolt, and who reviews it. A **Bolt** is one build pass over
> a unit, ending in something that runs.

## Sources

- [team] the affirmed Way of Working — solo build [OC-1], shallow Android
  review depth [OC-3]
- [state] Team Formation did not run under the `classic` plan

---

## There is no team to allocate

One person, who reviews everything; the agent writes most of the code [OC-1].
Stating that plainly beats inventing roles.

**Every Bolt is built by `aidlc-developer-agent` and reviewed by the human.**
No Program Board, no mob, no rotation, no hand-off.

| Bolt | Built by | Reviewed by |
|---|---|---|
| `d1-signing-up-and-joining` | aidlc-developer-agent | the human |
| `d2-running-a-batch` | aidlc-developer-agent | the human |
| `d3-collecting-fees` | aidlc-developer-agent | the human |
| `d4-teaching-and-recording` | aidlc-developer-agent | the human |
| `d5-knowing-how-it-is-going` | aidlc-developer-agent | the human |
| `d6-releasing-safely` | aidlc-developer-agent | the human |

## Where the single reviewer's attention earns most

| Bolt | What to look at |
|---|---|
| D1 | **The two query changes.** Everything else in D1 is visible on a screen; `_LENS_QUERY` and `_SUMMARY_QUERY` gaining their predicates is invisible, and it is the half that closes the exposure. The adversarial test is the guard, so check the test exists and fails without the fix. |
| D1 | **The migration.** A conditional backfill against live staging data. Read the `CASE WHEN`. |
| D2 | Lowest review risk: screens over tested endpoints. |
| D3 | The money branches — short-month clamp, carry-forward versus waive, partial approval, over-approval becoming credit. 100% branch coverage is what makes this reviewable at all. |
| D4 | The offline conflict path. Silent data loss during a live class is its failure mode, and a conflicted write presenting as failed invites a wrong retry. |
| D5 | The dues query's driving predicate — outstanding balance, not active status. The natural implementation is wrong in a way that looks right. |
| D6 | Everything. Deletion is the thing most reliably shipped broken, because nobody tests the absence of data. |

## What follows from one reviewer

The Android surface is the thinnest-reviewed part of the product [OC-3], and
**every one of these six Bolts ships screens**. The compensations are
mechanical rather than more review: conventional choices, ViewModel
state-machine tests, the serialization test per money-carrying model, the
Kotlin coverage ratchet, and checks that fail in CI.

The toolchain that makes those real — lockfiles, CVE scanning, detekt, Lint
with `HardwareIds` fatal, the coverage ratchet — was installed on 2026-10-22
and all gates pass.

## Autonomy

Construction runs autonomously. Plan Approval, summary confirmation,
verification-command selection and any failure remain human stops.
