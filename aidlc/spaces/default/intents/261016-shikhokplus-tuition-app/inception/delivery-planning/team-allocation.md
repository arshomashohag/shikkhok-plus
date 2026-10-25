# Team Allocation

**Stage**: delivery-planning (2.9)
**Phase**: Inception
**Depth**: Comprehensive
**Revision**: re-run 2026-10-22.

> Who builds each deliverable unit, and who reviews it.
>
> A **deliverable unit** (D1–D6) groups one or more Bolts — one build pass over
> a piece of work, ending in something that runs — by what a person can do when
> the group ships. `bolt-plan.md` defines them.

## Sources

- [upstream] the re-cut Bolt plan
- [team] the affirmed Way of Working — solo build [OC-1], review depth on the
  Android surface [OC-3]
- [state] Team Formation (1.5) was SKIP under the `classic` plan

---

## A. There is no team to allocate

Team Formation did not run, because this is a solo build: one person, who
reviews everything, with the agent writing most of the code [OC-1]. Stating that
plainly is more useful than inventing roles that do not exist.

**Every deliverable unit is built by `aidlc-developer-agent` and reviewed by the
human.** There is no Program Board, no mob composition, no rotation, and no
hand-off between teams. The mob-programming and team-topology practices in the
knowledge base do not apply here and are not forced onto this project.

| Unit | Built by | Reviewed by |
|---|---|---|
| D1 `signing-up-and-joining` | aidlc-developer-agent | the human |
| D2 `running-a-batch` | aidlc-developer-agent | the human |
| D3 `collecting-fees` | aidlc-developer-agent | the human |
| D4 `teaching-and-recording` | aidlc-developer-agent | the human |
| D5 `knowing-how-it-is-going` | aidlc-developer-agent | the human |
| D6 `releasing-safely` | aidlc-developer-agent | the human |

## B. What follows from one reviewer

Two consequences the team practice already accepts deliberately, restated here
because this revision makes both sharper.

**Review is the only quality gate that sees intent.** Tests and linters catch
what they are told to catch; the review catches whether the thing is the right
thing. That is why this project puts its important rules in mechanisms rather
than in review: the money boundary is a type and an import check, the lens is a
data dependency and a route-enumeration test, the forbidden-identifier set is a
manifest allowlist and a bytecode scan, the privacy boundary is a restricted
database role. Review remains the backstop and is not the mechanism.

**The Android surface is the thinnest-reviewed part of the product** [OC-3], and
**this revision increases its share of the work substantially.** The original
plan had four remaining Bolts that were backend-only; under the re-cut, all six
deliverable units ship screens, because a unit is no longer done until the thing
can be done on a phone. The compensations are unchanged and now carry more
weight:

- conventional, well-documented Android choices over clever ones, with project
  constraints outranking the sample where they conflict;
- tests an unfamiliar reviewer can read — ViewModel state-machine tests for
  loading, success, error and the explicit retry path; a serialization test per
  money-carrying model proving loud failure on a JSON number;
- the Kotlin coverage no-regression ratchet, which gives the trend teeth without
  anyone inventing a target they cannot justify;
- checks that fail in CI rather than in review.

## C. Autonomy

**Construction runs autonomously from here** [Q8]. The affirmed practice gated
"through the payment slice, then autonomous", and the slice that anchored it —
the platform subscription — no longer exists. The fee system remains in full but
no longer marks a gating boundary.

Human stops that remain regardless: Plan Approval, summary confirmation,
verification-command selection, and any failure. The walking skeleton was built
and human-checkpointed at B3, so that ceremony does not recur.

## D. Review expertise per unit

Not a staffing plan — a note on where the single reviewer's attention is worth
most, given that the mechanisms carry the rest.

| Unit | Where review attention earns most |
|---|---|
| D1 | The acceptance state machine. Pending, accepted and declined interact with the lens resolver, and a mistake grants a lens that should not exist. The durable-decline path is the one most likely to be got subtly wrong. |
| D2 | Screens over already-tested endpoints. Lowest review risk in the plan. |
| D3 | The fee arithmetic, and specifically the branches: the short-month clamp, carry-forward versus waive, partial approval, over-approval becoming credit. 100% branch coverage on the money module is what makes this reviewable at all. |
| D4 | The offline conflict path. The failure mode is silent data loss during a live class, and a conflicted write presenting as failed would invite a wrong retry. |
| D5 | The cross-batch dues query's driving predicate — outstanding balance, not active status. The natural implementation is wrong in a way that looks right. |
| D6 | Everything. Deletion features are the ones most reliably shipped broken, because nobody tests the absence of data, and this unit runs autonomously at the end of the plan. |
