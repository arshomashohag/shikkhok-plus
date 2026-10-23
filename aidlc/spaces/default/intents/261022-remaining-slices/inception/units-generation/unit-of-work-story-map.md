# Unit / Story Map

**Stage**: units-generation (2.7)
**Phase**: Inception
**Record**: 261022-remaining-slices

> Which unit implements which story. Order *within* a unit is noted; order
> *between* units is Delivery Planning's decision.

## Sources

- [upstream] `inception/user-stories/stories.md`
- [upstream] `inception/units-generation/unit-of-work.md` and
  `unit-of-work-dependency.md`
- [prior] `261016-shikhokplus-tuition-app/inception/user-stories/stories.md`
  — the 45 stories the four merged units delivered

---

## Unit identity

| Unit ID | Name | Directory |
|---|---|---|
| D1 | `signing-up-and-joining` | `d1-signing-up-and-joining` |
| D2 | `running-a-batch` | `d2-running-a-batch` |
| D3 | `collecting-fees` | `d3-collecting-fees` |
| D4 | `teaching-and-recording` | `d4-teaching-and-recording` |
| D5 | `knowing-how-it-is-going` | `d5-knowing-how-it-is-going` |
| D6 | `releasing-safely` | `d6-releasing-safely` |

---

## Story to Unit

| Story | Unit ID | Unit | Directory | Note |
|---|---|---|---|---|
| US1.2 | D1 | signing-up-and-joining | d1-signing-up-and-joining | Amended: the lenses offered depend on acceptance, not on signing in |
| US1.5 | D1 | signing-up-and-joining | d1-signing-up-and-joining | Profile edit, the `O5` screen |
| US1.10 | D1 | signing-up-and-joining | d1-signing-up-and-joining | Accepting or declining a seat |
| US1.11 | D1 | signing-up-and-joining | d1-signing-up-and-joining | Signing up without a teacher — the root capability |
| US1.12 | D1 | signing-up-and-joining | d1-signing-up-and-joining | Signing up on a number a teacher already added |
| US1.13 | D1 | signing-up-and-joining | d1-signing-up-and-joining | Changing my mind after declining |
| US1.16 | D1 | signing-up-and-joining | d1-signing-up-and-joining | Signup's own abuse ceilings |
| US1.3 | D2 | running-a-batch | d2-running-a-batch | Amended: the roster shows a seat's state |
| US1.15 | D2 | running-a-batch | d2-running-a-batch | A seat nobody accepts |
| US2.5 | D2 | running-a-batch | d2-running-a-batch | Amended: a seat nobody accepted can still be removed |
| US2.1 | D2 | running-a-batch | d2-running-a-batch | Create a batch |
| US2.2 | D2 | running-a-batch | d2-running-a-batch | Add a student by phone number |
| US2.3 | D2 | running-a-batch | d2-running-a-batch | The roster |
| US2.4 | D2 | running-a-batch | d2-running-a-batch | Batch settings and schedule |
| US2.6 | D2 | running-a-batch | d2-running-a-batch | Guardian child home and switcher — settles OQ-7 |
| US1.14 | D3 | collecting-fees | d3-collecting-fees | Declining stops the money. **Wholly D3** — see below |
| US5.1 | D3 | collecting-fees | d3-collecting-fees | Fee cycle generation |
| US5.2 | D3 | collecting-fees | d3-collecting-fees | Carry-forward, two-sided |
| US5.3 | D3 | collecting-fees | d3-collecting-fees | Waiver |
| US5.4 | D3 | collecting-fees | d3-collecting-fees | The daily self-healing job |
| US5.5 | D3 | collecting-fees | d3-collecting-fees | Credit grant and apply |
| US5.6 | D3 | collecting-fees | d3-collecting-fees | The server-computed fee status enum |
| US5.7 | D3 | collecting-fees | d3-collecting-fees | Student and guardian fee views |
| US6.1 | D3 | collecting-fees | d3-collecting-fees | Submit a payment claim |
| US6.2 | D3 | collecting-fees | d3-collecting-fees | The pending-verification list |
| US6.3 | D3 | collecting-fees | d3-collecting-fees | Teacher verifies a claimed payment |
| US6.4 | D3 | collecting-fees | d3-collecting-fees | Guardian sees what happened to their payment |
| US3.1 | D4 | teaching-and-recording | d4-teaching-and-recording | Sessions from weekly recurrence |
| US3.2 | D4 | teaching-and-recording | d4-teaching-and-recording | Record a class — the mid-class path |
| US3.3 | D4 | teaching-and-recording | d4-teaching-and-recording | The topic log |
| US3.4 | D4 | teaching-and-recording | d4-teaching-and-recording | Reschedule and cancel |
| US3.5 | D4 | teaching-and-recording | d4-teaching-and-recording | Announcements |
| US3.6 | D4 | teaching-and-recording | d4-teaching-and-recording | Attendance visible to student and guardian |
| US4.1 | D4 | teaching-and-recording | d4-teaching-and-recording | Exam creation |
| US4.2 | D4 | teaching-and-recording | d4-teaching-and-recording | Mark entry with the four result states |
| US4.3 | D4 | teaching-and-recording | d4-teaching-and-recording | Correction history via `superseded_by_id` |
| US4.4 | D4 | teaching-and-recording | d4-teaching-and-recording | The anonymised batch marksheet |
| US4.5 | D4 | teaching-and-recording | d4-teaching-and-recording | The `marksheet_visible` toggle |
| US4.6 | D4 | teaching-and-recording | d4-teaching-and-recording | Exam dates |
| US4.7 | D4 | teaching-and-recording | d4-teaching-and-recording | Guardian progress over time |
| US7.1 | D5 | knowing-how-it-is-going | d5-knowing-how-it-is-going | Cross-batch dues, driven by balance not status |
| US8.1 | D5 | knowing-how-it-is-going | d5-knowing-how-it-is-going | This month's earnings |
| US8.2 | D5 | knowing-how-it-is-going | d5-knowing-how-it-is-going | Earnings over time |
| US8.3 | D5 | knowing-how-it-is-going | d5-knowing-how-it-is-going | Collection rate — ships without the field while OQ-2 is open |
| US8.4 | D5 | knowing-how-it-is-going | d5-knowing-how-it-is-going | The next upcoming exam |
| US1.6 | D6 | releasing-safely | d6-releasing-safely | Amended: deletion does not clear a decline |
| US1.7 | D6 | releasing-safely | d6-releasing-safely | The external deletion route |
| US10.1 | D6 | releasing-safely | d6-releasing-safely | The system refuses a request for someone else's data |
| US1.8 | D1 | signing-up-and-joining | d1-signing-up-and-joining | **Already delivered** by the merged identity-and-access unit. Listed against D1 because D1 extends the same abuse-control surface with signup's own ceilings (US1.16), and the OTP controls must still hold afterwards — the byte-identical assertion is part of D1's tests |
| US1.17 | D1 | signing-up-and-joining | d1-signing-up-and-joining | **Withdrawn** at the User Stories review as a delivery standard rather than a story. Listed against D1 because D1 is the first unit the obligation binds: its four screens each need a row in docs/delivery/bangla-layout-check.md before the unit completes [FR0.2] |

---

## US1.14 belongs wholly to D3

The first draft of this file split it, giving D1 "[AC1.14.2a]'s minimum: the
ability to append a reversal entry against a cycle".

**Checked: no ledger table exists.** There is no `LedgerEntry` and no
`FeeCycle` in `app/db/models.py` or in any of the three migrations, because D3
creates both. D1 had nothing to write a reversal to, so the "minimum ledger
mechanism" was a deliverable with no target.

D1 owns the **decision-column transition** — a decline sets
`student_decision = 'declined'` — and nothing more about money. Every money
consequence is D3's: AC1.14.1 and AC1.14.1a (whether generation stops, by
link), AC1.14.2 (the reversal entry), AC1.14.3 (an un-decline does not
resurrect voided cycles), and AC1.14.4 (a pending seat keeps generating).

**AC1.14.2a is unsatisfiable as written, and that is the honest reading.** It
exists to answer "can D1 ship a decline that does nothing to the money?" The
answer is yes and it is correct, because in D1 there is no money. The exposure
it guards — a decline leaving a silent debt — cannot occur before D3, and D3's
own criteria close it. **D3's Definition of Done inherits AC1.14.1 through
AC1.14.4 in full.**

---

## Stories deliberately not mapped

| Story | Why |
|---|---|
| **US1.17** | Withdrawn at the User Stories review: a delivery standard wearing a story's clothes. [FR0.2] carries the obligation and `docs/delivery/bangla-layout-check.md` is its verifier. |
| **US1.8** | Not a story of this record. It is the prior record's OTP abuse-control story, cited in US1.16's INVEST note to explain why signup's ceilings are a separate story. Delivered by the merged `identity-and-access`. |
| **US9.1–US9.4** | Cross-cutting: notification, failed-write recovery, Bangla, colour-independence. They are standing per-unit obligations with named verifiers in `unit-of-work.md`. |

Mapping a cross-cutting story to one unit makes it that unit's problem and
nobody else's, which is exactly how the Bangla obligation went three Bolts
without a verifier.

---

## Coverage

Every story of this record maps to a unit, or is listed above with the reason
it does not. No story is unmapped by omission.
