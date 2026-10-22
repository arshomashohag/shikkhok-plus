# User Stories — Plan and Questions

**Stage**: user-stories (2.4)
**Phase**: Inception
**Record**: 261022-remaining-slices

## Sources

- [upstream] `inception/requirements-analysis/requirements.md` — this record's
  32 requirements, of which FR1a is the acceptance model
- [prior] `261016-shikhokplus-tuition-app/inception/user-stories/stories.md` —
  45 stories, 2026-10-17, traced and gated
- [prior] the same record's `personas.md` — P1 Rafiq (teacher), P2 Tanvir
  (student), P3 Shireen (guardian), P4 the platform owner
- [upstream] `codekb/shikkhok-plus/` — the scan of the built code

---

## The plan

**Personas: unchanged, not restated.** P1–P4 are defined in the prior record
and nothing in the re-cut adds or alters one. `personas.md` in this record is a
pointer to them plus the one thing acceptance changes: Tanvir and Shireen now
have a decision to make that they did not have before, and that decision is the
first thing either of them does in the product.

**Story numbering continues; it does not restart.** The prior record uses
US1.1–US1.9 for identity. New stories here begin at **US1.10**. Existing IDs
are never reused or renumbered — four built Units reference them.

**Breakdown: by workflow**, not by feature or persona. The acceptance model is
a single workflow crossing three personas (a teacher adds, a person decides, a
ledger responds), and cutting it by persona would scatter one state machine
across three places.

**Priority: all Must Have.** Every new story is part of D1, which is the unit
that makes the app usable at all. There is nothing to defer.

**Scope: around eight new stories**, plus explicit supersession of six criteria
across four existing stories.

---

## Q1. How should the contradicted stories and criteria be handled?

Requirements Analysis recorded supersessions in this record and left the prior
gated artifact intact [Q1 there]. The same question arises here, with one
difference: acceptance criteria are what someone writes a test against, so a
stale criterion is more dangerous than a stale requirement.

- A. **Same treatment as the requirements.** New stories and criteria in this
  record, each naming what it supersedes and why; the prior record keeps its
  2026-10-17 text as the historical statement.
- B. Edit the prior record's `stories.md`, so there is one file.
- C. Write the new stories only, and leave the contradicted criteria for
  whoever next reads them to notice.
- X. Other (please specify)

[Answer]: A. Same treatment as the requirements. New stories and
criteria in this record, each naming what it supersedes and why; the prior
record keeps its 2026-10-17 text as the historical statement. The prior
`stories.md` is a gated artifact and overwriting it would destroy the evidence
of what changed and when.

## Q2. US1.2's premise is inverted. Replace it, or supersede it?

US1.2 reads "Student or guardian claims a dormant record… **without anyone
inviting me**". Under acceptance, the invitation is the mechanism. The story's
title, its narrative and three of its four criteria are now wrong.

- A. **Supersede the whole story** with a new one (US1.10) describing the
  accept-or-decline decision, and mark US1.2 superseded in this record.
  AC1.2.2 and AC1.2.3 — which lenses are offered — carry forward amended.
- B. Keep US1.2 and amend only its criteria, so the story ID stays stable for
  anything that references it.
- X. Other (please specify)

[Answer]: B. Keep US1.2 and amend its criteria, so the ID stays
stable for anything that references it.

**With one extension the conductor flagged and applied:** the story's TITLE and
NARRATIVE are amended too, not only its criteria. "Claims a dormant record" and
"without anyone inviting me" describe the superseded model, so leaving them
while amending the criteria beneath them would leave the story contradicting
itself — which is worse than either consistent alternative. The ID, which is
what the answer protects, is unchanged.

## Q3. Who is the operator story for?

The prior record has US1.8 "The code cannot be abused", written for **the
operator** persona (P4) rather than for a teacher or student. Signup now needs
its own abuse controls [FR1.7d], separate from the OTP ceilings.

- A. **A new operator story** (numbered US1.16 in the artifact), matching US1.8's shape: signup's
  per-number and per-IP ceilings, and the assertion that `POST /v1/auth/otp`
  stays byte-identical for known and unknown numbers after signup exists.
- B. Extend US1.8's criteria rather than adding a story.
- X. Other (please specify)

[Answer]: A. A new operator story, written as US1.16 in the artifact (the question's draft said US1.11, which the signup story took), matching US1.8's shape:
signup's own per-number and per-IP ceilings, and the assertion that
`POST /v1/auth/otp` stays byte-identical for known and unknown numbers after
signup exists. A new story rather than extra criteria on US1.8, because signup
abuse and OTP abuse are different surfaces with different controls, and the
reason signup needs its own is that its response is deliberately informative
where OTP's is deliberately not.

## Q4. Does the voided-ledger behaviour belong in a story, or only in D3?

Declining stops fee generation and voids accrued cycles as an append-only
reversal [FR1.9f.1–f.3]. The fee system is D3; acceptance is D1.

- A. **A story in D1, with criteria asserting the ledger outcome.** The rule is
  part of what declining means, and D1 is where declining is built — even
  though the cycles it voids are generated by D3 machinery.
- B. Defer it to D3's stories, where the ledger lives.
- C. A story in D1 for the stop-generation half, and D3 for the voiding half.
- X. Other (please specify)

[Answer]: A. A story in D1, with criteria asserting the ledger
outcome. The rule is part of what declining MEANS, and D1 is where declining is
built — even though the cycles it voids are generated by D3's machinery. The
alternative risks D1 shipping a decline that silently does nothing to the money,
which is the exposure the rule exists to close.

## Q5. How much should the stories say about the invitation lens?

[FR1.9d.1] requires a distinct invitation lens rather than a special case in
the resolver. That is a design decision, and stories are not the place for
design — but it is also an authorization boundary, which is exactly what a
criterion should pin.

- A. **Assert the behaviour, not the mechanism.** Criteria state what a pending
  person can and cannot reach; how the lens is built belongs to Functional
  Design.
- B. Name the invitation lens in the criteria, so the design decision is
  visible to whoever writes the test.
- X. Other (please specify)

[Answer]: A. Assert the behaviour, not the mechanism. The criteria
state what a pending person can and cannot reach; how the lens is built belongs
to Functional Design. The requirement [FR1.9d.1] already records the invitation
lens as the chosen mechanism, so the decision is not lost by keeping it out of
the stories.
