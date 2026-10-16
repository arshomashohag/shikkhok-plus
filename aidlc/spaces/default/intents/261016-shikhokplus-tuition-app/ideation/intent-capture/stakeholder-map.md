# Stakeholder Map — ShikhokPlus

**Stage**: intent-capture (1.1)
**Phase**: Ideation
**Date**: 2026-10-17

---

## Key Stakeholders and Their Interests

| Stakeholder | Role | Primary Interest | Access in V1 | Source |
|---|---|---|---|---|
| Private tuition teacher | Paying customer and sole author of teaching records | Replace paper notebooks and Excel; collect month-end fees reliably; see everyone who owes money across all batches at once | Full read/write on own batches | [desc] |
| Guardian | Funds the tuition; commercially decisive | See what they are paying for — attendance, topics covered, marks over time, next payment date and amount, and the status of every past fee cycle | Read-only, plus submit a payment, hide an inactive batch, edit own profile | [desc] |
| Student | Subject of the records; may be under 13 | See own batches, next class, topics covered, exam marksheets and own fee status | Read-only, plus the same three writes as the guardian | [desc] [Q17] |
| Platform owner | Operates the business | Onboard teachers; oversee subscriptions and payment status; collect subscriptions out-of-band | No surface in V1 — neither interface nor APIs. Teachers onboarded manually. When the surface arrives, visibility is bounded to subscriber information only (teacher name, plan, payment status), never student or guardian data | [Q1] [Q20] |
| Pilot teachers | Early adopters whose feedback shapes priority | A tool that works mid-class in a real classroom, on a low-end phone and patchy data | Same as teacher | [Q10] |
| Google Play | Distribution gatekeeper | Policy compliance, particularly children's data and account deletion | Not a user; a release precondition | [Q17] [desc] |

A single phone number may hold more than one of the student and guardian roles
at once; roles are lenses resolved at read time from owned batches and
enrollments, not stored fields. [desc]

---

## Decision-Makers vs. Influencers

### Decision-makers

| Who | Authority | Source |
|---|---|---|
| Project owner (the user) | Decides scope and priority | [Q10] |

### Influencers

| Who | Influence | Source |
|---|---|---|
| Pilot teachers | A small group whose feedback influences priority, without scope authority. Group size not quantified. | [Q10] [assumption] |
| Guardians | Influence indirectly and strongly: guardian satisfaction is the stated driver of teacher subscription renewal, so guardian needs shape product priority even though guardians hold no decision rights. | [desc] |
| Google Play policy | Constrains rather than influences: the mixed-audience-including-children declaration imposes non-negotiable technical constraints on identity handling and third-party SDKs. | [Q17] |

No co-founder, business partner, investor or external stakeholder with scope
authority or reporting expectations was identified. [Q10]

---

## Communication Requirements

| Audience | Requirement | Cadence | Source |
|---|---|---|---|
| Pilot teachers | Informal updates; no formal written artifacts required | Not specified | [Q11] |
| Investors or external partners | None — no such stakeholder exists for this initiative | Not applicable | [Q10] [Q11] |

No reporting cadence or stakeholder-facing artifact obligation applies, so later
stages produce technical artifacts only. [Q11]

### In-product communication to stakeholders

Distinct from project reporting, these are product features serving the
stakeholders above.

| Channel | Direction | Status in V1 | Source |
|---|---|---|---|
| Batch announcements | Teacher to all batch members | In scope (in the agreed data model) | [desc] |
| Push notifications | System to students and guardians | In scope | [Q12] |
| Batch messaging / group chat | Between batch members | Excluded from V1; architecture must absorb it later | [desc] |
| Teacher-to-single-student private messaging | Teacher to one student | Excluded from V1 | [Q12] |

---

## Assumptions & Open Questions

- The pilot teacher group size was described only as "a small group" and is not
  quantified, so the feedback loop's weight on priority cannot be sized.
  [Q10] [assumption]
- The platform-owner persona has no V1 surface, so it exercises no access in V1.
  Its eventual visibility is already bounded to subscriber information only, so
  the question that was open at artifact generation is now closed; what remains
  is ensuring the design can honour that bound when the surface is built.
  [Q20] [assumption]
- Guardian influence is inferred to be strong from the stated link between
  guardian satisfaction and subscription renewal, but no mechanism exists in V1
  for guardians to report dissatisfaction in-product, so that influence reaches
  the project only indirectly through the teacher or the pilot group.
  [desc] [assumption]
- Whether pilot teachers are a defined cohort with an onboarding or feedback
  process, or simply the first organic users, was not established.
  [Q10] [assumption]

---

## Sources

- [desc] Initial description: the authoritative project description recorded at
  workflow creation.
- [Q1], [Q10], [Q11], [Q12], [Q17], [Q20] — confirmed answers in
  `intent-capture-questions.md`. (Q16's answer was superseded by Q20.)
