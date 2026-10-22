# Requirements Analysis — Questions

**Stage**: requirements-analysis (2.3)
**Phase**: Inception
**Depth**: Standard
**Record**: 261022-remaining-slices

## Sources

- [desc] the authoritative project description for this record — the six
  remaining deliverable units D1–D6
- [upstream] `codekb/shikkhok-plus/` — the scan of the built code, 2026-10-22
- [upstream] `inception/practices-discovery/team-practices.md`
- [prior] `261016-shikhokplus-tuition-app/inception/requirements-analysis/requirements.md`
  — the product's full requirements, written 2026-10-17
- [prior] `261016-shikhokplus-tuition-app/inception/delivery-planning/bolt-plan.md`
  — the approved re-cut, 2026-10-22

---

## How this stage is scoped

The product's requirements are **already written, traced and gated**: 102
entries with no gaps, covering every capability D1–D6 will build. This stage
does not re-derive them and does not renumber them — the `FR{n}.{m}` IDs are
permanent traceability keys that four built Units already reference.

What this stage exists for is narrower and real: **four requirements now
contradict decisions taken after they were written.** The requirements say one
thing and the approved plan says another, and a contradiction left standing
means the next reader follows whichever file they opened.

The affected requirements, read from the prior record:

| ID | What it says today | What contradicts it |
|---|---|---|
| **FR1.7** | "Only a teacher creates a student record. **There is no self-registration, no join request and no invite acceptance.**" | D1 adds account creation AND seat acceptance. Every clause of this requirement is now false. |
| **FR1.9** | "A mistyped number produces a permanently dormant record. **This is correct behaviour, not an error state**, and the system never attempts recovery." | The acceptance decision of 2026-10-22 treats a mistyped number as the exposure to close: a stranger silently gains a guardian lens over a child. |
| **FR1.4** | "At login, only the lenses that have data are offered." | Still true, but `GET /v1/me` now implements it, and acceptance adds a condition: a lens is offered only once the seat is **accepted**. |
| **FR1.8** | "A created record is dormant until that number first authenticates." | Authenticating is no longer sufficient. A seat is dormant → pending → accepted, and the lens arrives at acceptance rather than at first sign-in. |

Three further items need confirming rather than deciding, and are below.

---

## Q1. How should the contradicted requirements be handled?

FR1.7 and FR1.9 state the opposite of what was decided on 2026-10-22. Both are
referenced by built code and by the prior record's traceability.

- A. **Amend in place, in this record, with the supersession recorded.** Write
  the corrected requirements here as `FR1.7a` / `FR1.9a`, each naming the
  requirement it supersedes and why. The prior record stays as the historical
  statement; this record carries the current one.
- B. Edit the prior record's `requirements.md` directly, so there is one file.
- C. Leave both and rely on the delivery plan to override them in practice.
- X. Other (please specify)

[Answer]: A. Amend in place, in this record, with the supersession
recorded. The corrected requirements are written here as `FR1.7a` and `FR1.9a`,
each naming the requirement it supersedes and why. The prior record keeps its
2026-10-17 statement as the historical record; this record carries the current
one. Editing the prior record directly was declined: it is a gated artifact and
overwriting it would destroy the evidence of what changed and when.

## Q2. What exactly does acceptance gate?

The decision records that a seat grants no student or guardian lens until
accepted, and that the teacher's side never blocks. The boundary worth stating
as a requirement is what a **pending** person can see of their own seat.

- A. **Nothing but the invitation.** A pending seat shows only that a teacher
  added this number, with accept and decline. No batch content, no dues, no
  attendance until accepted.
- B. The invitation plus read-only visibility of what they would be accepting
  (batch name, subject, the fee amount), so the decision is informed.
- C. Everything a student normally sees, with writes blocked until acceptance.
- X. Other (please specify)

[Answer]: B. The invitation plus read-only visibility of what they
would be accepting — batch name, subject and the fee amount — so the decision is
informed. A person asked to accept a financial obligation on behalf of a child
should be able to see what the obligation is before agreeing. This is narrower
than a student view: no attendance, no marks, no other enrollments, and no
writes.

## Q3. What happens to a seat that is never accepted?

A teacher adds a number, the person never opens the app or never accepts. The
seat accrues fee cycles from creation [FR5], because the teacher's side does
not block.

- A. **It stays pending indefinitely, and the roster shows that.** No expiry.
  The teacher sees the pending state and can correct the number or mark the
  enrollment inactive. This is the current assumption in the plan.
- B. It expires after a stated period and the enrollment becomes inactive
  automatically.
- C. It stays pending, and fee generation is suspended for an unaccepted seat
  until it is accepted.
- X. Other (please specify)

[Answer]: A. It stays pending indefinitely and the roster shows
that. No expiry. The teacher sees the pending state, and can correct the number
or mark the enrollment inactive. Fee cycles continue to generate, because the
teacher's side never blocks on acceptance and the debt is real whether or not
anyone opened the app.

## Q4. Does declining need to tell the teacher anything?

Declining is durable and survives re-adding. The teacher typed that number for
a reason, and a decline is information they do not otherwise get.

- A. **The roster shows declined, distinctly from pending.** The teacher learns
  the number was wrong, or that the person refused, and acts accordingly. No
  notification.
- B. Declined looks identical to pending on the roster. The teacher is told
  nothing, so a declining person is not exposed to them.
- C. Declined shows on the roster and the teacher is notified when it happens.
- X. Other (please specify)

[Answer]: A. The roster shows declined, distinctly from pending,
with no notification. This is what makes a mistyped digit visible: without it, a
wrong number and a refusal and an unopened app all look identical. No
notification, because a decline is not urgent and the roster is where the
teacher already looks.

## Q5. Are the three toolchain gaps requirements of this work, or already discharged?

Practices Discovery assigned lockfiles, CVE scanning and the Android quality
toolchain to "before D1", and that work was completed on 2026-10-22 ahead of
this stage — all gates pass. The question is whether they should also appear
here as requirements.

- A. **No. They are done, and recording a completed control as a requirement of
  future work would misdescribe the state.** The practice file records the
  assignment and the commit records the delivery; `requirements.md` notes them
  as satisfied preconditions rather than as requirements.
- B. Yes, record them as requirements of this work with their status marked
  satisfied, so the traceability chain shows them explicitly.
- X. Other (please specify)

[Answer]: A. No. They are done — completed 2026-10-22 ahead of
this stage, with all gates passing — and recording a completed control as a
requirement of future work would misdescribe the state. They are listed under
Constraints as satisfied preconditions; the practice file records the
assignment and the commit records the delivery.

## Q6. Anything the six units should cover that the prior requirements miss?

The prior requirements were written before the re-cut, so they describe
capabilities rather than user-visible slices. The re-cut's own standard is that
a unit is not done until the thing can be done on a phone.

- A. **No additions. The capability requirements are complete**, and what the
  re-cut adds is a delivery standard rather than new requirements — recorded
  here as an acceptance condition applying to all six units.
- B. Add a per-unit requirement that each unit's named artboards are matched,
  so "done on a phone" has an explicit verifier per screen.
- C. There is something missing — I will say what.
- X. Other (please specify)

[Answer]: B. Add a per-unit requirement that each unit's named
artboards are matched, so "done on a phone" has an explicit verifier per screen
rather than being a judgement call at the checkpoint. This is FR0.2 below.
