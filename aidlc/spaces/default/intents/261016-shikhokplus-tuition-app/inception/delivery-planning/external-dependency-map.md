# External Dependency Map

**Stage**: delivery-planning (2.9)
**Phase**: Inception
**Depth**: Comprehensive
**Revision**: re-run 2026-10-22. Supersedes the 2026-10-18 map; four of its
seven rows have since resolved, and the rest are re-pointed at the deliverable
units that now carry them.

> Everything outside this build that can hold it up: who owns it, how long it
> takes, which deliverable unit it blocks, and what happens if it slips.
>
> A **deliverable unit** (D1–D6) groups one or more Bolts — one build pass over
> a piece of work, ending in something that runs — by what a person can do when
> the group ships. `bolt-plan.md` defines them.

## Sources

- [upstream] `inception/contract-design/contract-summary.md` — OQ-1..OQ-5, OQ-7
- [upstream] `inception/units-generation/unit-of-work.md`
- [team] the affirmed Deployment practice and its budget ceiling
- [code] the built state on disk, read 2026-10-22

---

## A. Resolved since the last revision

Kept rather than deleted, so a reader does not re-open a settled question.

| Dependency | Resolution |
|---|---|
| **SMS gateway vendor** (OQ-3) | **Resolved 2026-10-18: BulkSMSBD**, and now implemented — `app/gateway/bulksmsbd.py`, with a null adapter and an outbox alongside it. `contract-summary.md` §C.4 records six binding behaviours probed against the live endpoint. |
| **Hosting** | **Resolved and deployed.** `infra/` carries the full Terraform estate; the deployment pipeline builds, provisions and deploys per environment. This went further than the original Lightsail plan. |
| **FCM project setup** | Not yet needed. It blocks D3, which owns the adapter, rather than anything earlier. Self-service, hours. The real obligation is unchanged: the Firebase dependency is checked against the forbidden-identifier set *before* it is added, and the manifest allowlist and DEX scan are the mechanism. Both of those gates are **built** (`android/release-gates.gradle.kts`), so this control is live. |
| **Play Console listing assets** | Produced — icon, feature graphic, phone and tablet screenshots, and an explainer video, under `store_listing/`. |

**Still open from that row, and still unanswered:** OQ-3a (does BulkSMSBD offer a
sandbox? `team.md`'s non-production practice is not satisfiable as written
without one, though CI is unaffected because the gateway is stubbed there) and
OQ-3b (is the Bangla-body rule enforced for OTP traffic? a 3–4× per-OTP cost
multiplier if so, feeding [D-33]'s ceiling). Neither blocks a build.

---

## B. Open dependencies

| Dependency | Owner | Lead time | Blocks | Fallback if it slips |
|---|---|---|---|---|
| **Play Console account type** — a personal account created after 13 Nov 2023 requires 12 testers opted in continuously for 14 days before production access; the pilot group was described as smaller than that | The human. | Account creation and identity verification: **days to a few weeks**, variable by jurisdiction and document turnaround. Google publishes no committed SLA and none is invented here. The **12-tester/14-day window is 14 continuous days minimum**, and that clock cannot start before an AAB is uploadable. | **D6** and the release itself. The first internal-track upload is no longer gated on a packaging unit — the release gates are built and an installable APK exists — so this is now purely an account question. | If it is the post-2023 personal type and twelve testers cannot be found, the fallback is an organisation account, which is a **different and longer** verification path (D-U-N-S number, business verification). **This is now the most schedule-dangerous open item in the plan**, because the original mitigation — starting the Play clock early via a packaging Bolt at position 4 — did not happen: packaging shipped its gates without an upload. Recommend resolving the account type now, independently of any unit. |
| **OQ-1 — does `PaymentClaim.transaction_id` survive the claimant's deletion?** | The human (product and legal judgement). | Unknown; a decision, not a procurement. | **D6**'s manifest and generated policy text, and **D3**'s payment-history response schema, which must know whether the field can be null post-deletion. | D3 ships the field as nullable regardless — the answer-agnostic choice, and it costs nothing. D6 cannot generate policy text against an undecided row. **Must close before D6; ideally before D3, so the schema is not revisited.** |
| **OQ-5 — the external deletion route's web surface, unconfirmed against Play's expectations for a deletion URL** | The human (hosting and compliance confirmation). | Unknown, and cheap to confirm by reading Play's current account-deletion-URL requirements. | **D6**, which is release-blocking. | The contract assumes FastAPI-served HTML on the existing container. A separate static host would change the path, not the semantics — cheap *if discovered early*, a release blocker if discovered at D6. **Recommend confirming as soon as Play Console access exists.** |
| **OQ-2 — FR8.3's collection-rate definition, open to correction, with AC8.3.4's credit rule postdating it** | The human. | Unknown. | **D5**. | D5 sits fifth of six, which buys the maximum remaining interval. If still open when D5 arrives, ship D5 **without** the `collection_rate` field rather than with provisional arithmetic: a field is additive under the `/v1/` policy, a wrong number pinned into an installed client cannot be withdrawn. |
| **Teacher onboarding mechanism for closed testing** — no admin surface exists in V1 and none is budgeted | The human. | Unknown; depends on the mechanism. | The closed-testing pilot, not any unit. | **Materially cheaper than it was.** D1 builds account creation, so a teacher can now sign themselves up rather than being inserted by hand — which was the whole reason this row existed. What remains is only whether pilot teachers self-serve or are invited, and direct `psql` under the named-non-superuser and logged-session rule stays the fallback. The standing prohibition holds: no production query result containing child-identifying data goes into a local file, a chat, or an AI tool context. |

---

## C. New dependencies introduced by this revision

| Dependency | Owner | Blocks | Note |
|---|---|---|---|
| **The Macrobenchmark harness and low-end-device profile** | This build; not external. | **D4**'s PU-3.6 obligation, while scheduled in **D5**. | Listed here because it behaves exactly like an external dependency: a prerequisite that a blocked unit cannot satisfy for itself. It is the one genuine sequencing defect in this plan and `risk-and-sequencing-rationale.md` §D.1 names the three ways out. Not an external procurement — just work that must move. |

---

## Assumptions & Open Questions

Two items want resolving **now**, independently of the unit that blocks on them:

1. **The Play account type.** The original plan's mitigation was to start the
   Play clock six Bolts early; that did not happen, so the full 14-day window
   now sits on the critical path to release with nothing absorbing it.
2. **OQ-5**, confirmable in minutes by reading Play's current requirements, and
   a release blocker if it surfaces at D6.

Lead times are stated as **unknown** where they are genuinely unknown. No figure
here is invented to make a schedule look firmer than it is.
