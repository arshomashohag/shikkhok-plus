# Phase Check — Ideation → Inception

**Date**: 2026-10-17
**Checked by**: approval-handoff (1.7), Step 4
**Verdict**: **PASS with recorded gaps**

Verifies Intent → Scope → Intent Backlog consistency, and that every scope item
has feasibility backing.

---

## 1. Intent → Scope consistency

Does every capability in the scope document trace to the intent statement or a
confirmed answer?

| Scope area | Traces to | Status |
|---|---|---|
| Teacher surface — batches, enrollment, fee override, multiple enrollment, inactive-from-date, edit details, sessions, exams, announcements, payment verification, partial disposition | Initial description §6 | OK |
| Teacher surface — attendance | [intent: Q5] | OK |
| Teacher surface — cross-batch dues screen | Initial description §6, reaffirmed [scope: Q6] | OK |
| Teacher surface — analytics dashboard | [intent: Q12], [scope: Q4] | OK — content undefined, see §5 |
| Student surface — batch list, next class, topics, exam dates, announcements, marksheet, own fee status | Initial description §7 | OK |
| Student and guardian — the three writes | Initial description §5, §9 | OK |
| Guardian surface — child selection, per-child batches, progress over time, payment outlook | Initial description §8 | OK |
| Cross-cutting — phone OTP auth | Initial description §3, provider at [feasibility: Q5] | OK |
| Cross-cutting — role switching | Initial description §3 | OK |
| Cross-cutting — push notifications | [intent: Q12], [scope: Q3] | OK — event set incomplete, see §5 |
| Cross-cutting — Bangla and English | Initial description §11, [intent: Q13] | OK |
| Cross-cutting — account deletion, Data Safety, privacy policy, accessibility | Initial description §11 | OK |

**No orphan scope items.** Every capability traces to the initial description or
a confirmed answer.

**No dropped intent items.** Each capability named in the initial description
§6–§9 appears in the scope document, with one correction made during this phase:
account deletion, the Data Safety form and the privacy policy were omitted from
the first draft of the intent statement and restored after the reviewer found
them. Recorded here because it was a real near-miss.

---

## 2. Scope → Intent Backlog consistency

Does every in-scope capability appear as a proto-Unit line item, and does every
backlog item trace back to scope?

| Scope area | Backlog coverage | Status |
|---|---|---|
| Authentication and identity | PU-1.1 – PU-1.13 | OK |
| Batches and enrollment | PU-2.1 – PU-2.14 | OK |
| Schedule, sessions, attendance | PU-3.1 – PU-3.10 | OK |
| Exams and marksheets | PU-4.1 – PU-4.7 | OK |
| Fee cycles | PU-5.1 – PU-5.9 | OK |
| Payment submission and verification | PU-6.1 – PU-6.10 | OK |
| Cross-batch dues screen | PU-7.1 – PU-7.3 | OK |
| Cross-cutting (push, analytics, localization, accessibility, APK, build, compliance) | PU-8.1 – PU-8.10 | OK |

**No orphan backlog items.** Every proto-Unit line traces to a scope capability.

**Count**: 8 proto-Units, approximately 70 line items, each carrying a source
tag.

---

## 3. Scope → Feasibility backing

Does every scope item have feasibility backing, and does any scope item
contradict a constraint?

| Scope item | Feasibility backing | Status |
|---|---|---|
| Phone OTP auth | Provider decision and cost analysis, `feasibility-assessment.md` §3 | OK |
| Attendance requiring connectivity | Assessed as low engineering risk; product risk R-7 accepted | OK |
| Money ledger | Representation settled [feasibility: Q8]; medium risk with mandatory tests | OK |
| Fee-cycle generation | Idempotency mechanism specified, `architecture-proposal.md` §8d | OK |
| Cross-batch dues query | Named as the reason PostgreSQL was chosen over DynamoDB | OK |
| Privacy boundary | Three-layer mechanism specified, `architecture-proposal.md` §8f | OK |
| Org-owned batches (deferred) | `Owner` indirection specified, `architecture-proposal.md` §8b | OK |
| PWA (deferred) | Server-side rules plus generated OpenAPI, `architecture-proposal.md` §8a | OK |
| Android client | Architecture specified; **R-2 medium-high risk** from the review gap | OK — risk recorded |
| Push notifications | FCM permissibility verified [firebase-privacy]; cost not assessed | **GAP** — see §5 |
| Analytics dashboard | No feasibility assessment possible | **GAP** — see §5 |
| Bangla and English | Constraint TC-15; no specific feasibility concern | OK |
| Play compliance deliverables | Target API, deletion and Families requirements verified against official documentation | OK |
| Subscription state (deferred) | Absorb-without-rework obligation recorded; no mechanism specified | **GAP** — see §5 |
| Admin surface (deferred) | Visibility bound specified [intent: Q20]; no mechanism | OK — out of V1 entirely |

**No scope item contradicts a constraint.** Checked each of the 20 technical, 7
organisational and 8 regulatory constraints against the scope document.

---

## 4. Contradiction check across phases

| Potential contradiction | Resolution |
|---|---|
| Attendance in V1 as a "primary mid-class path" versus cached-reads-only | Raised and resolved [intent: Q18] — attendance stays, connectivity required, risk accepted |
| 13+ Play declaration versus under-13 students logging in | Raised and resolved [intent: Q17] — mixed audience declared |
| Platform admin APIs in V1 versus no admin surface | Raised and resolved [intent: Q16 → Q20] — removed entirely |
| `FeeCycle` as described in §10 versus the teacher-adjustable anchor | Raised and resolved [intent: Q19] — anchor plus ledger, calendar months retained |
| One-month timeline versus full-scope Must Have | Raised and resolved [scope: Q7] — timeline is the variable |
| `shikhokplus` versus `shikkhok-plus` spelling | Raised and resolved [intent: Q3] — `com.shikkhokplus.app` |
| Push notifications in V1 versus the no-device-identifier constraint | Raised and resolved [Q1] — FCM verified permissible |

**No unresolved contradictions carry into Inception.**

---

## 5. Gaps recorded

Three gaps, none blocking, each with an owner.

| Gap | Detail | Owner |
|---|---|---|
| **Analytics dashboard has no content** | A Must Have that specifies nothing cannot be sized, built or tested. Excluded from the 8–12 week estimate for that reason. | Requirements Analysis (2.3) |
| **Push notification event set incomplete** | Two event types named (fee reminders, new marks); class cancellation, payment approval, announcements and exam scheduling are all plausible and unspecified. | Requirements Analysis (2.3) |
| **Subscription absorb-without-rework has no mechanism** | Unlike org-owned batches (`Owner` indirection) and the PWA (server-side rules plus generated OpenAPI), the deferred subscription has an obligation recorded but no structural mechanism specified. | Domain Design (2.6) |

That third gap is the one worth noting: of the six deferred capabilities
claiming absorb-without-rework, only two have concrete mechanisms. The reviewer
raised this at intent capture as an accumulating-risk concern and it remains
substantially open.

---

## 6. Coverage summary

| Check | Result |
|---|---|
| Intent → Scope | 100% — no orphan scope items, no dropped intent items |
| Scope → Backlog | 100% — no orphan backlog items |
| Scope → Feasibility backing | 12 of 15 fully backed; 3 gaps recorded with owners |
| Constraint contradictions | None |
| Cross-phase contradictions | None unresolved; 7 raised and resolved during Ideation |
| Open questions | 8 entering Inception: 4 with owning stages, 3 without, 1 resolved in this stage |

---

## 7. Human approval

- [ ] Reviewed and approved

**Verdict: PASS with recorded gaps.** Ideation is internally consistent and
traceable. The three gaps are documentation gaps with named owners in early
Inception stages, not inconsistencies, and none blocks design work.

---

## Assumptions & Open Questions

- This check verifies internal consistency and traceability. It does not verify
  that the decisions are correct — only that they are coherent with each other
  and sourced. [assumption]
- The "no scope item contradicts a constraint" finding was established by
  reading each constraint against the scope document, not by an automated
  check. [assumption]
- Coverage percentages count artifact line items, not implementation
  completeness; nothing has been built. [assumption]

## Sources

- All Ideation artifacts under `../ideation/`.
- [firebase-privacy] https://firebase.google.com/support/privacy — retrieved
  2026-10-17.
