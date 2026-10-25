# External Dependency Map

**Stage**: delivery-planning (2.9)
**Record**: 261022-remaining-slices

> Everything outside this build that can hold it up: who owns it, how long it
> takes, which Bolt it blocks, and what happens if it slips.

## Sources

- [upstream] `inception/units-generation/unit-of-work.md`
- [prior] the 2026-10-22 dependency map, four of whose seven rows have resolved

---

## Resolved, and kept so nobody re-opens them

| Dependency | Resolution |
|---|---|
| SMS gateway vendor | **BulkSMSBD**, implemented at `app/gateway/bulksmsbd.py` with a null adapter and an outbox |
| Hosting | **Deployed.** `infra/` carries the full Terraform estate with a per-environment pipeline |
| Play listing assets | Produced — icon, feature graphic, screenshots, explainer video |
| Dependency lockfiles, CVE scanning, the Android toolchain | **Installed 2026-10-22**, all gates passing. First CVE audit: no known vulnerabilities |

Still open from the gateway row and blocking nothing: OQ-3a (is there a
sandbox?) and OQ-3b (is the Bangla-body rule enforced for OTP traffic, a 3–4x
per-OTP cost multiplier if so).

---

## Open

| Dependency | Owner | Lead time | Blocks | Fallback |
|---|---|---|---|---|
| **Play Console account type** | The human | Account creation and identity verification: days to a few weeks, variable by jurisdiction. The 12-tester/14-day closed-testing window is 14 continuous days minimum and cannot start before an AAB is uploadable. | **D6** and the release | If it is the post-2023 personal type and twelve testers cannot be found, the fallback is an organisation account — a longer D-U-N-S verification path. **This is the most schedule-dangerous open item**, because the original mitigation (starting the Play clock early via a packaging Bolt) did not happen. Resolve it now, independently of any Bolt. |
| **OQ-1** — does `PaymentClaim.transaction_id` survive the claimant's deletion? | The human | A decision, not a procurement | **D6**'s generated policy, and **D3**'s payment-history schema | D3 ships the field nullable regardless, which is answer-agnostic. D6 cannot generate policy text against an undecided row. **Close before D6; ideally before D3.** |
| **OQ-5** — the external deletion route's web surface, unconfirmed against Play's expectations | The human | Minutes, by reading Play's current requirements | **D6**, release-blocking | The contract assumes FastAPI-served HTML on the existing container. A separate static host changes the path, not the semantics — cheap if found early, a release blocker at D6. |
| **OQ-2** — FR8.3's collection-rate definition | The human | Unknown | **D5** | D5 ships without the `collection_rate` field rather than with provisional arithmetic. A field is additive under `/v1/`; a wrong number in an installed client cannot be withdrawn. |
| **FCM project setup** | The human, low-friction | Hours, self-service | **D3**, which owns the adapter | Push is best-effort and never fails its caller, so D3's non-push DoD is unaffected. The real obligation is the SDK admission note: Firebase is checked against the forbidden-identifier set before it is added, and the manifest allowlist plus DEX scan are the live mechanism. |
| **Branch protection** — "Require branches to be up to date before merging" | The human | Thirty seconds | Nothing directly | Cannot be read from the repository. If it is off, the green-`main` obligation has no verifier, because the post-merge run was removed on 2026-10-19. |

---

## Not external, but behaves like one

| Item | Blocks | Note |
|---|---|---|
| ~~The Macrobenchmark harness~~ | — | **Closed 2026-10-23: not built.** PU-3.6 is discharged by a named manual check during the pilot, so nothing D4 needs lives in a later unit and the prerequisite dissolves. |

---

## Resolve now, not when the Bolt arrives

1. **The Play account type.** The full 14-day window now sits on the critical
   path to release with nothing absorbing it.
2. **OQ-5**, confirmable in minutes and a release blocker if it surfaces at D6.
3. **Branch protection**, a thirty-second settings check.

Lead times are stated as unknown where they genuinely are. No figure here is
invented to make a schedule look firmer than it is.
