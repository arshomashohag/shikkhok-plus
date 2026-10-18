# External Dependency Map

**Stage**: delivery-planning (2.9)
**Phase**: Inception
**Depth**: Comprehensive

> Everything outside this build that can hold it up: who owns it, how long it
> takes, which Bolt it blocks, and what happens if it slips.

## Sources

- [upstream] `inception/contract-design/contract-summary.md` — OQ-1..OQ-5, OQ-7
- [upstream] `inception/units-generation/unit-of-work.md`
- [team] the affirmed Deployment practice and its budget ceiling

---

## D. External dependencies

| Dependency | Owner | Lead time | Blocks | Fallback if it slips |
|---|---|---|---|---|
| **SMS gateway vendor selection** (OQ-3) — delivery reliability, masked-sender support, sandbox/test credentials, and whether advertised BDT 0.25–0.40 rates carry minimum commitments | The human. External to the workflow; no agent can select a vendor. | **Unknown.** Local BTRC-approved gateways in Bangladesh typically involve a commercial conversation and a KYC/business-verification step; I have no verified figure and will not invent one. Assume it is not same-day. | **B3**, which is the walking skeleton and the human skeleton checkpoint. The adapter interface is vendor-neutral and buildable now, but the per-purpose ceiling cannot be *calibrated*, and the staging sandbox path cannot be *verified*. | Build B3 against the adapter interface with a stubbed gateway — `team.md` already requires the blocking suite to run with no secret, so CI is unaffected by definition. The *skeleton checkpoint itself* is the exposure: `team.md` binds the skeleton to "an SMS arrives through the real gateway", so without a vendor the Construction Verification Command cannot be satisfied as written. **Two options and I am not choosing between them:** (a) start vendor selection now, before Construction begins, and treat it as a B1/B2-parallel activity; or (b) accept a provisionally-verified skeleton where the gateway leg is stubbed, with a recorded obligation to re-run the real verification before B4's first Play upload. Option (a) is strongly preferable and costs only a decision made early. **Flagging for the human.** |
| **Play Console account** — creation, identity verification, and the account-type question (a personal account created after 13 Nov 2023 requires 12 testers opted in continuously for 14 days before production access; the pilot group was described as smaller than that) | The human. | Account creation and identity verification: **days to a few weeks**, variable by jurisdiction and document turnaround — Google does not publish a committed SLA and I will not state one. The **12-tester/14-day closed-testing window is 14 continuous days minimum**, and that clock cannot start before an AAB is uploadable. | **B4** (first upload to the internal track) and, decisively, **B11** and the release itself. | This is the single strongest argument for B4 at position 4: it starts the Play clock roughly six Bolts earlier than a terminal U10 would. If the account type turns out to be the post-2023 personal type and 12 testers cannot be found, the fallback is an organisation account — which is a *different, longer* verification path (D-U-N-S number and business verification), so discovering this late is materially worse than discovering it now. **I recommend resolving the account-type question before Construction starts, not at B4.** |
| **Teacher onboarding mechanism for closed testing** — no admin surface exists in V1 and none is budgeted | The human. | Unknown; depends on the chosen mechanism. | The closed-testing pilot, not any Bolt. | The mechanism is almost certainly direct `psql` against production under the named-non-superuser + logged-session rule `team.md` already mandates. That is acceptable but it must be *decided and runbooked* rather than improvised on the day, because the alternative is an ad-hoc production session against children's data. Note the standing prohibition: no production query result containing child-identifying data goes into a local file, a chat, or an AI tool context. |
| **Lightsail staging + production hosts**, `ap-southeast-1` or `ap-south-1`, with storage encryption (RC-8 disqualifies any tier without it) | The human (AWS account, payment method). | **Hours.** Lightsail instance provisioning is minutes; the AWS account and payment method are the real gate, and if an account already exists this is effectively zero. | **B3** — the skeleton is bound to "running against the real Phase 1 Lightsail host." | None needed; this is the lowest-risk external dependency. Budget check: staging + production takes Phase 1 from ~USD 13 to ~USD 25/month against the USD 50 ceiling, already accepted in `team.md`. |
| **FCM project setup** — Firebase project, server credentials, Android app registration | The human, but low-friction. | **Hours.** Self-service. | **B6**, which owns the adapter. | Push is best-effort by design and never fails its caller, so B6's non-push DoD is unaffected. The real obligation here is not the setup but the **SDK admission note** [project.md]: the Firebase dependency must be checked against the forbidden-identifier set before it is added, and B4's manifest allowlist and DEX scan are the mechanism — another reason B4 precedes B6. |
| **OQ-1 — does `PaymentClaim.transaction_id` survive the claimant's deletion?** | The human (product and legal judgement). | Unknown; a decision, not a procurement. | **B11**'s manifest and generated policy text, and **B7**'s payment-history response schema, which must know whether the field can be null post-deletion. | B7 ships the field as nullable regardless, which is the answer-agnostic choice and costs nothing. But B11 cannot generate policy text against an undecided row. **Must be closed before B11 starts; ideally before B7, so the schema is not revisited.** |
| **OQ-5 — the external deletion route's web surface, unconfirmed against Play's expectations for a deletion URL** | The human (hosting and compliance confirmation). | Unknown. Confirmable by reading Play's current account-deletion-URL requirements, which is cheap. | **B11**, which is release-blocking. | The contract assumes FastAPI-served HTML on the existing container, which is the only option under the USD 50/month ceiling. A separate static host would change the path, not the semantics — so the fallback is cheap *if discovered early* and a release blocker if discovered at B11. **Recommend confirming during B4, when Play Console access first exists.** |
| **OQ-2 — FR8.3's collection-rate definition, open to correction, with AC8.3.4's credit rule postdating it** | The human. | Unknown. | **B10**. | B10 is position 10, which buys the maximum possible interval. If it is still open at B10, ship B10 without the `collection_rate` field rather than with provisional arithmetic — the field can be added additively under the `/v1/` policy, whereas a wrong number pinned into a client in the field cannot be withdrawn. |

---

## Assumptions & Open Questions

Three of these want resolving **before Construction starts**, not when the
blocking Bolt arrives:

1. **The SMS vendor**, because without one the walking-skeleton checkpoint
   cannot be satisfied as the affirmed practice words it — "an SMS arrives
   through the real gateway." Starting selection as a B1/B2-parallel activity
   costs only an early decision.
2. **The Play account type**, because if it is the post-2023 personal type and
   twelve testers cannot be found, the fallback is an organisation account with
   a longer verification path. Discovering that at B4 is materially worse than
   discovering it now.
3. **OQ-5**, confirmable cheaply by reading Play's current account-deletion-URL
   requirements — and a release blocker if it surfaces at B11.

Lead times are stated as **unknown** where they are genuinely unknown. No figure
here is invented to make a schedule look firmer than it is.
