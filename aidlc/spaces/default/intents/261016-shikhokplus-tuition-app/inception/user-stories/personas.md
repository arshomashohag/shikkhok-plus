# Personas — ShikhokPlus

**Stage**: user-stories (2.4)
**Phase**: Inception
**Date**: 2026-10-17

Four personas. Three have V1 stories; the platform owner is recorded for
completeness and has no V1 surface [intent: Q20].

---

## P1 — Rafiq, the private tuition teacher

**Priority**: Primary. The paying customer and the only author of teaching
records.

| | |
|---|---|
| **Role** | Teaches several batches, often multiple subjects per batch, from home or a rented room [desc §1] |
| **Tech comfort** | Moderate. Uses WhatsApp and Messenger daily. Has never used a purpose-built app for this and keeps records in a paper notebook or Excel [desc §1] [Q5] |
| **Device** | Own Android phone, not shared. Mobile data is cheap and plentiful [Q6.2] |
| **Frequency** | Daily during term — several times a day, once per class |

**Goals**

1. Stop losing track of who paid and who did not, across every batch at once.
2. Keep the guardian informed without answering the same question by phone
   twenty times a month.
3. Spend no more time on records than the notebook already costs him.

**Pain points**

1. Month-end collection is reconstruction work: he reads back through a
   notebook to work out who owes what [desc §1].
2. Guardians ask about progress and he has nothing to show them but memory
   [desc §1].
3. A student who leaves owing money disappears from his attention, because the
   notebook is organised by batch and the departed student is no longer in one
   [desc §6, FR7.2].

**What makes him abandon the app**

Anything slower than paper, mid-class. His brief says more than a few seconds
per class to mark attendance and he stops using it [desc §11]. There is no
V1 requirement enforcing that [Q14.3], so this persona's defining risk is
undetected until he tells us.

---

## P2 — Tanvir, the student

**Priority**: Secondary. Subject of the records, read-only except three writes.

| | |
|---|---|
| **Role** | Secondary-school student in one or more of Rafiq's batches [desc §7] |
| **Age** | 11–18. Under-13s are present and do log in, which drives the mixed-audience Play declaration [intent: Q17] [Q5] |
| **Tech comfort** | Native. More fluent with a phone than either the teacher or the guardian |
| **Device** | Own phone, not shared with the guardian [Q6.2] |
| **Frequency** | Weekly or less — spikes after an exam |

**Goals**

1. Know when the next class is and what was covered.
2. See how he did in the last exam, and how that compares.
3. Not be the messenger between his teacher and his guardian about money.

**Pain points**

1. No record of what was taught except his own notes.
2. Exam results arrive verbally and are forgotten.

**What he writes** — exactly three things: a payment submission, hiding an
inactive batch from his own list, and his own private profile [desc §5]. The
profile is invisible to the teacher and the app says so explicitly [desc §4,
FR1.12].

**Design consequence of his age**: under-13s logging in is why no device or
advertising identifier may be transmitted anywhere [NFR11], and why the
marksheet anonymises other students' marks [FR4.5].

---

## P3 — Shireen, the guardian

**Priority**: Secondary by access, **decisive commercially**. Funds the tuition
and her satisfaction is the stated renewal driver [desc §1].

| | |
|---|---|
| **Role** | Parent or guardian paying for one or more children's tuition [desc §8] |
| **Tech comfort** | Lower than the teacher's. Comfortable with messaging apps, less so with anything requiring setup [Q5] |
| **Primary motivation** | **Fee transparency over academic detail** [Q5-D, confirmed Q6.1]. She wants to know what is owed, what was paid, and that classes actually happened. Marks matter, but they are not what makes her open the app. This ordering decides which of her stories are load-bearing: US5.4 and US6.4 before US4.4. |
| **Device** | Own phone, not shared with her child [Q6.2] |
| **Frequency** | Monthly around the fee date, plus after exams |

**Goals**

1. Know her money is buying actual attendance and actual teaching [desc §1].
2. Know what is owed and when, without asking.
3. See whether her child is improving.

**Pain points**

1. Currently sees nothing at all — no attendance, no syllabus progress, no
   marks, no fee history [desc §1]. This is the gap the product exists to close.
2. Has to ask her child, who is not a reliable narrator about marks.

**The model complication she lives with**: her visibility is keyed to the phone
number the teacher recorded [FR2.7]. If two teachers recorded different numbers
for the same child, each number reaches only its own teacher's batches
[FR2.18].

The explanation she gets, after the specialist round: every batch names its
teacher [AC2.8.3], a persistent statement says the view is keyed to the number
she signed in with [AC2.8.4], and both apply even when the child-selection list
is skipped [AC2.8.5] — which was the case the original design missed, and the
one where the confusion is worst. A3 remains an assumption, narrowed: she now
has attribution and a statement of scope, and what is still assumed is that she
infers "the other teacher recorded a different number" rather than "my data is
missing".

---

## P4 — The platform owner

**Priority**: Operator. **No V1 surface** — neither interface nor APIs
[intent: Q20]. Recorded so the stories are not missing an actor by accident.

| | |
|---|---|
| **Role** | Operates the business: onboards teachers, oversees subscriptions |
| **V1 access** | None. Teachers are onboarded manually, by a mechanism still undefined [feasibility: I-6] |
| **Eventual visibility** | Subscriber information only — teacher name, plan, payment status. Never any student or guardian data [intent: Q20] [NFR-project rule] |

**Why no stories**: with subscription deferred, there is nothing to activate
programmatically during closed testing, so the APIs have nothing to do. When
this persona gains a surface, its visibility bound is already decided.

---

## Persona relationships

```
P1 Rafiq (teacher) ──writes──> batches, enrollments, sessions,
     │                          attendance, exams, marks, fee cycles,
     │                          verifications, announcements
     │
     ├──reads──> P2's and P3's payment submissions (claims only)
     │
     └──NEVER reads──> P2's or P3's private profile [FR9.4, NFR14]

P2 Tanvir (student) ──reads──> own batches, own marks, anonymised peer marks,
     │                          own fee status
     └──writes──> payment submission, hide batch, own profile

P3 Shireen (guardian) ──reads──> child's batches (scoped by recorded number),
     │                            child's marks and progress, fee outlook
     └──writes──> payment submission, hide batch, own profile

P4 platform owner ──> no V1 surface
```

**The asymmetry is the product.** P1 authors almost everything and sees none of
P2's or P3's private writes. P2 and P3 see most of what P1 authors about them
and write almost nothing. That is deliberate and structurally enforced, not a
permissions convenience [desc §4] [desc §12f].

One account may hold more than one of these lenses simultaneously — being both
a student and a guardian is normal [desc §3, FR1.6] — so these are roles a
person occupies, not accounts.

---

## Assumptions & Open Questions

- Persona names are illustrative, chosen as common Bangladeshi names so stories
  read naturally. No real person is described. [assumption]
- P1's tech comfort, P2's age range and P3's tech comfort were confirmed [Q6.1];
  the device picture was corrected to own-phones-with-decent-data [Q6.2].
  Frequency-of-use figures are inferred from the described workflow, not
  measured. [assumption]
- P3 is described as the mother in the illustrative name, but a guardian may be
  any adult — father, grandparent, older sibling, or an unrelated funder. No
  requirement assumes a relationship type. [assumption]
- P2's age range drives the Families declaration, so if students are in fact
  mostly 16+ the compliance posture could relax. The brief says
  secondary-school, which spans the under-13 line, so the strict reading
  stands. [intent: Q17] [assumption]
- No persona was written for a teacher's assistant or a second teacher sharing a
  batch, because V1 has no multi-teacher batches. Coaching centres are the
  deferred capability that introduces them. [desc §2] [assumption]

## Sources

- [desc] Initial description, §1–§12.
- [Q5], [Q6.1], [Q6.2] Confirmed answers in `user-stories-questions.md`.
- [FR*], [NFR*], [A3] `inception/requirements-analysis/requirements.md`.
- [intent: Q17], [intent: Q20] `ideation/intent-capture/`.
- [feasibility: I-6] `ideation/feasibility/raid-log.md`.
- [Q14.3] the dropped mid-class speed requirement, `requirements-analysis-questions.md`.
