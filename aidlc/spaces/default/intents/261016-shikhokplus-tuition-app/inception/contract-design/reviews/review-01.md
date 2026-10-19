**Collaborator:** aidlc-architecture-reviewer-agent

## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T00:56:22Z
**Iteration:** 1

### Findings

**Prior findings**

| ID | Now | Severity | Note |
|---|---|---|---|

**New findings**

| Severity | Location | Finding | Required action |
|---|---|---|---|
| Major | contract-summary.md > B.2 and B.3 | B.2 marks a 401 `ACCESS_TOKEN_EXPIRED` `retryable: false` under `AuthorizationError` (team.md: never retry), while B.3 instructs refresh-then-replay of the original request. A client author reading only one section builds the wrong behaviour. | State in B.2 that refresh-then-replay-once is the one documented exception, and define what `retryable` answers. |
| Minor | contract-summary.md > G, OQ-6 | OQ-6 is listed as open while carrying a proposed default, so it reads as a decision wearing a question's clothes. | Either decide it or drop the proposed default; leaving both makes every money response schema provisional. |
| Minor | contract-summary.md > C.1 | `SmsPurpose` has one value in V1, so NFR12.1's per-purpose budget is not exercised by any code path yet. | Add one sentence noting the design intent is verified by signature review until a second purpose exists, so nobody removes the parameter as speculative generality. |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Manual cross-reference against unit-of-work.md / unit-of-work-dependency.md | PASS | All 9 in-process edges (batches→identity, sessions→batches, exams→batches, fees→batches, payments→fees, insights→payments, insights→exams, release-packaging→identity, governance→{U3..U9}) match the reasoning stated in the dependency artifact's "Edges that are not obvious" and "Integration points" sections; none is miscategorized as in-process when the upstream artifact implies a wire boundary. |
| Manual cross-reference against decisions.md ADR-001/002/006/007 | PASS | ADR-001's owner_id rooting and enrollment_id-never-account-id rule is reflected in B.4/E.2. ADR-002's corrected ledger invariant is referenced consistently in E.1's implementation notes (matches the corrected form, not the superseded team.md form). ADR-006's refuse-on-conflict queued-write rule and the four-state model are implemented faithfully in B.8. ADR-007's "Fees owns LedgerEntry writes" is implemented as E.3's in-process contract. |
| Manual cross-reference against team.md error taxonomy table | FAIL (see Major finding) | The five classes, HTTP mappings, and server-provided-retryable rule match exactly, except the AuthorizationError/401 refresh-then-replay flow is not reconciled with team.md's literal "never retry" caller behaviour. |
| Manual check of PUBLIC_ROUTES vs team.md's allowlist description | PASS | team.md requires "exactly the OTP issue and verify endpoints, the health endpoint, and the external deletion route" — the contract's five-entry frozenset (counting GET/POST separately for one logical deletion route) matches this, and /v1/auth/refresh is correctly excluded and handled via a separate LENS_EXEMPT_AUTHENTICATED set rather than being folded into PUBLIC_ROUTES. |
| Manual check of 404-vs-403 rule for legitimate existence-disclosure cases | PASS | The rule is scoped to cross-owner existence (ADR-001's teacher-B-must-not-be-observable concern) and does not appear to suppress a case where a caller should legitimately learn a resource exists — a caller inside their own lens who can see the resource gets 200, and a caller whose lens cannot reach it (whether absent or owned by someone else) uniformly gets 403, which is the correct behavior for the IDOR boundary this protects. |
| Manual check of re-apply client_mutation_id rule (§B.8) | PASS | The artifact states explicitly and with reasoning that re-apply must use a new client_mutation_id and that reusing the old one would silently turn the re-apply into a no-op. This is clear enough that an implementer is unlikely to miss it, and it is also called out a second time under "Assumptions & Open Questions" for visibility. |

### Summary

The contract-design artifact is internally consistent with the unit DAG, the domain-design ADRs and components, the requirements NFRs it cites (NFR5.1, NFR12/12.1, NFR13, NFR16, FR11.4/11.5), and team.md's/project.md's affirmed and permanent rules, with one real gap: the AuthorizationError/401 refresh-then-replay flow in B.3 is not reconciled with team.md's literal "never retry" caller behaviour for that error class, which an implementer following only the taxonomy table could read as forbidding the refresh retry the artifact itself specifies two sections later. The in-process-vs-wire classification of all nine excluded DAG edges is correctly grounded in the upstream dependency and domain-design artifacts, the money/lens/SMS/FCM contracts match the affirmed practices precisely, and the seven open questions are genuine unresolved product/legal/measurement questions rather than decisions being avoided (OQ-6's stated "proposed default" is the only one that blurs the line, flagged as Minor). One Major and no more than two Minor findings keep this at READY.

READY
