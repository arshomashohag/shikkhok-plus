# User Stories — account creation and seat acceptance

**Stage**: user-stories (2.4)
**Phase**: Inception
**Record**: 261022-remaining-slices

> **The product's 45 stories are not restated here.** They live at
> `261016-shikhokplus-tuition-app/inception/user-stories/stories.md`, are
> traced to requirements, and their `US{n}.{m}` and `AC{n}.{m}.{seq}` IDs are
> permanent keys that four built Units reference.
>
> This file carries what changed: eight new stories for the work no story
> covered, and the amendments to four existing stories whose criteria the
> acceptance model contradicts. New IDs continue the existing numbering from
> **US1.10**; nothing is renumbered.

## Sources

- [upstream] `inception/requirements-analysis/requirements.md` — FR0, FR1a
- [prior] the 45 stories and four personas of 2026-10-17
- [Q1]–[Q5] in `user-stories-questions.md`

**Personas**: P1 Rafiq (teacher), P2 Tanvir (student), P3 Shireen (guardian),
P4 the platform owner. Defined in the prior record; `personas.md` here records
only what acceptance changes about them.

**Priority**: every story below is **Must Have**. All are part of D1, the unit
that makes the app usable by someone who has never used it.

---

## Part A — Amendments to existing stories

Each amendment names the criterion it supersedes. The prior record keeps its
2026-10-17 text as the historical statement [Q1].

### US1.2 — amended: Student or guardian accepts a seat a teacher created

**Title and narrative amended, ID unchanged** [Q2]. The prior story read
*"Student or guardian claims a dormant record… so that I can see what was
recorded about me **without anyone inviting me**"*. Every clause of that is now
inverted: the invitation is the mechanism, and signing in claims nothing. The
title and narrative are amended alongside the criteria, because a story whose
heading contradicts its own criteria is worse than either consistent
alternative. The ID is stable, which is what matters for anything referencing
it.

As **a student or guardian**, I want to decide whether a seat a teacher created
for my number is really mine, so that nobody is enrolled in my name without my
agreement and nobody sees my records by typing a wrong digit.

| Criterion | Statement | Supersedes |
|---|---|---|
| **AC1.2.1a** | Given a teacher recorded my number and I sign in, When I reach my home screen, Then the seat appears as an invitation I may accept or decline, and **no lens for that seat is active until I accept**. | **AC1.2.1** — "my account activates and the batches recorded against my number appear" |
| **AC1.2.2a** | Given my number appears as a student on one **accepted** seat and as a guardian on another **accepted** seat, When I sign in, Then both lenses are offered. | **AC1.2.2** — same, without the acceptance condition |
| **AC1.2.3a** | Given my number appears only on seats I have not accepted, When I sign in, Then **no** student or guardian lens is offered, only the invitations. | **AC1.2.3** — "appears only as a student… no guardian lens is offered" |
| AC1.2.4 | Unchanged: given I am signed in, When I switch lens, Then the view changes without re-authenticating. | — |

[FR1.9a] [FR1.4a] [FR1.8a]

### US1.3 — amended: the roster shows a seat's state

| Criterion | Statement | Supersedes |
|---|---|---|
| **AC1.3.2a** | Given a seat I created, Then the person named **is shown the invitation when they sign in**. No SMS, push or other outbound notification is sent to that number for this purpose. | **AC1.3.2** — "no notification, invitation or reminder is ever sent to that number" |
| **AC1.3.3a** | Given a seat on my roster, When I view the roster, Then **declined** is marked per row, and **pending** is shown as a batch-level count ("9 of 12 accepted") rather than a per-row mark. | **AC1.3.3** — "it is not marked there, because dormant is the normal state… decorating most rows would flag normality as a problem" |
| **AC1.3.4a** | Given I open a seat's detail, Then it states that seat's state — pending, accepted or declined — and offers a path to correct the phone number. | **AC1.3.4** — "states whether that person has ever signed in" |
| **AC1.3.5a** | Given a batch, Then it shows how many seats have been **accepted** out of the total, so I can see the scale without per-row clutter. | **AC1.3.5** — "how many enrollments have been claimed… '9 of 12 have signed in'" |
| **AC1.3.6a** | Given a seat, Then **never accepted** is distinguishable from **accepted and then deleted**, because the first may be a mistyped number and the second is a person who left. | **AC1.3.6** — "never claimed is distinguishable from claimed and then deleted" |

**Dormant collapses into pending** [human, this stage]. Once signup exists, a
seat a teacher creates is pending from creation; signing in is no longer the
event that changes its state. Dormant survives only as the state a seat returns
to when an accepted person deletes their account [AC1.6.2a], so the three
criteria above — all written in sign-in terms — are superseded rather than
amended.

AC1.3.4, AC1.3.5 and AC1.3.6 were **not** in this stage's original assessment,
which named six contradicted criteria. The review found three more. The
assessment's count was wrong.

**On clutter.** The superseded AC1.3.3 refused to mark the roster because
"dormant is the normal state early in a batch's life and decorating most rows
would flag normality as a problem". That reasoning survives the collapse and is
honoured rather than discarded: pending is now the common early state, so
marking every pending row would reproduce exactly the clutter it guarded
against. Pending therefore keeps AC1.3.5's batch-level count, and only
**declined** — which is not normality and is the signal that a number may be
wrong — is marked per row. [FR1.9h]

### US2.5 — amended: a seat nobody accepted can still be removed

| Criterion | Statement | Supersedes |
|---|---|---|
| **AC2.5.1a** | Given a seat that **no link has accepted** — pending or declined — and which therefore has no claimed history, When I remove it, Then it is deleted. | **AC2.5.1** — "Given an enrollment that is **dormant** and has no attendance, marks or fee history, When I remove it, Then it is deleted" |

**Found at review, and it is the one that mattered most.** Once dormant
collapses into pending, a criterion permitting removal only while *dormant*
forbids removal of every seat a teacher creates — which is the primary recovery
path from a mistyped number, the exact exposure acceptance exists to close.
AC1.15.2 offers the teacher that path and AC2.5.1 took it away, and neither
this stage's amendments nor [FR1.9i] had reached it.

The underlying rule is unchanged and [ADR-003] is intact: a teacher cannot make
an accepted person's records go away. What changes is only the name of the
state that means "nobody has claimed this". A declined seat is removable for the
same reason a pending one is — nobody accepted it, so nothing is destroyed —
and removal does not defeat [FR1.9c], because re-adding the number creates a
fresh seat the person is free to decline again. [FR2.12] [FR1.9i]

### US1.6 — amended: deletion does not clear a decline

| Criterion | Statement | Supersedes |
|---|---|---|
| **AC1.6.2a** | Given I was a student or guardian, When my account is deleted, Then the teacher-authored enrollment, attendance, marks and fee records remain, and the seat reverts to dormant **unless I had declined it, in which case it stays declined**. | **AC1.6.2** — "the enrollment reverts to dormant", unconditionally |

Found at review of this record's requirements. Unconditional reversion makes
deletion a way to clear a decline: delete, and the next teacher re-add
re-prompts a person who refused. [FR11.1a]

---

## Part B — New stories

### US1.10 — Accepting or declining a seat

As **a student or guardian** (P2, P3), I want to see what I am being asked to
join before I agree, so that I can accept my own enrollment confidently and
refuse one that is not mine.

- **AC1.10.1** — Given a seat is pending for my number, When I open it, Then I see the batch name, the subject and the fee amount, and nothing else about that batch. [FR1.9d]
- **AC1.10.2** — Given a pending seat, Then I can reach no attendance, no marks, no other enrollment, and no write action for it. [FR1.9d]
- **AC1.10.3** — Given a pending seat, When I accept, Then the matching lens becomes available and the seat's full history from creation is visible to me, including any dues accrued before I accepted. [FR1.9g]
- **AC1.10.4** — Given a pending seat, When I decline, Then no lens is granted and the seat does not appear among my enrollments. [FR1.9a]
- **AC1.10.5** — Given a seat where I am recorded as both the student and the guardian, When I accept, Then both lenses become available for it and the seat appears once, not twice. [FR1.16]
- **AC1.10.6** — Given a seat whose student and guardian are **different people**, When one of them accepts and the other declines, Then each decision affects only that person's own lens: the accepter gets theirs, the decliner gets none, and neither decision changes the other's. [FR1.9b]
- **AC1.10.7** — Given the same seat, Then the teacher's roster shows the seat once, with each link's state shown separately rather than collapsed into one. [FR1.9b] [FR1.9h]

*INVEST*: Independent of the rest of D1 once signup exists; Testable — every
criterion is a reachability assertion. This is the story that closes the
unconsented-guardian exposure.

### US1.11 — Signing up without a teacher

As **a person with no account** (P1, P2, P3), I want to create my own account,
so that I can use the product without waiting for someone else to add me.

- **AC1.11.1** — Given I have no account, When I supply a role, name, mobile number and address, Then an account is created, and an `Owner` row is created **only** if I chose Teacher. [FR1.7a]
- **AC1.11.2** — Given I chose Teacher, When I sign in, Then a teacher lens is available and I reach my own empty batch list. [FR1.7a] [FR1.4a]
- **AC1.11.3** — Given I chose Student or Guardian, When I sign in and hold no accepted seat, Then no student or guardian lens is offered. [FR1.7a] [FR1.9a]
- **AC1.11.4** — Given I complete the form, Then the account is created **before** the code is sent, and the submit action names the number the code will go to. [FR1.7c]
- **AC1.11.5** — Given I claim a role, Then nothing verifies the claim. [FR1.7b]

*INVEST*: Independent — nothing precedes it, and nothing else in D1 can be
demonstrated without it.

### US1.12 — Signing up on a number a teacher already added

As **a student or guardian whose teacher added me** (P2, P3), I want the signup
form to already know who I am, so that I do not retype what my teacher
recorded or pick the wrong role.

- **AC1.12.1** — Given my number has a seat a teacher created, When the signup form renders, Then my name is pre-filled from the teacher's entry and marked as correctable, and the role is locked to the one the seat carries. [FR1.7f]
- **AC1.12.2** — Given the same, Then the form tells me a teacher has added this number and **does not name the teacher or the batch**. [FR1.7f]
- **AC1.12.3** — Given I complete signup on such a number, Then the seat is **still pending**: signing up does not accept it. [FR1.9a]
- **AC1.12.4** — Given my number already has an account, When I try to sign up, Then I am told the number already has an account and directed to log in. [O1 state 5]

*INVEST*: Testable; AC1.12.2 is the criterion that keeps the lookup from
becoming an oracle for who teaches whom.

### US1.13 — Changing my mind after declining

As **a student or guardian who declined by mistake** (P2, P3), I want to be
able to accept after all, so that a mis-tap does not permanently lock me out of
my own records.

- **AC1.13.1** — Given I declined a seat, When I view my invitations, Then the declined seat is still listed with an accept action available to me. [FR1.9c.1]
- **AC1.13.2** — Given I declined a seat, When I accept it later, Then the lens becomes available exactly as if I had accepted first time. [FR1.9c.1]
- **AC1.13.3** — Given I declined a seat, Then **no action available to the teacher** clears or reverses that decline. [FR1.9c.2]
- **AC1.13.4** — Given I declined a seat and the teacher adds my number to that batch again, Then I am **not** re-prompted. [FR1.9c]

*INVEST*: Small and Testable. AC1.13.3 and AC1.13.4 together are the pair that
makes the durability protect the right person: durable against the teacher,
reversible by me.

### US1.14 — Declining stops the money

As **a person who declined a seat** (P2, P3), I want declining to stop the fees
that seat was accruing, so that refusing an enrollment that is not mine does
not leave a debt in my name.

- **AC1.14.1** — Given a pending seat that has been generating fee cycles, When **the student link** declines, Then no further cycle is generated for that seat. [FR1.9f.1]
- **AC1.14.1a** — Given the same seat, When **the guardian link** declines, Then fee generation is **unaffected**: the student owes the fee, and a guardian's refusal to oversee the enrollment does not cancel the student's obligation. Only the guardian's own lens is withdrawn. [FR1.9b] [FR1.9f.1]
- **AC1.14.2** — Given the same, Then the cycles already accrued are voided, recorded as a **reversal** in the ledger rather than by deleting rows. [FR1.9f.2] [ADR-002]
- **AC1.14.2a** — Given D1 ships before D3's fee machinery, Then D1 carries the **minimum ledger needed to satisfy AC1.14.2**: the ability to append a reversal entry against a cycle. D1 does not carry fee generation, carry-forward, credit or payment verification, all of which remain D3. | *This is the resolution of the ordering question, stated as a criterion rather than flagged beside one: a developer reading AC1.14.2 alone could not tell whether D1 is done.* [FR1.9f.2]
- **AC1.14.3** — Given I later accept under [AC1.13.2], Then the voided cycles are **not** resurrected and generation resumes from the acceptance date. [FR1.9f.3]
- **AC1.14.4** — Given a seat is pending and not declined, Then fee cycles continue to generate from its creation. [FR1.9f]

*INVEST*: Valuable — this is the story that keeps the mistyped-number exposure
from reappearing on the ledger after acceptance closed it on the lens. Built in
D1 though the machinery is D3's, because it is part of what declining means
[Q4].

### US1.15 — A seat nobody accepts

As **a teacher** (P1), I want to see that a seat has not been accepted, so that
I can tell a wrong number from a student who has not opened the app.

- **AC1.15.1** — Given a seat nobody accepts, Then it stays pending indefinitely, with no expiry and no automatic deactivation. [FR1.9e]
- **AC1.15.2** — Given a pending seat, When I view the roster, Then I can see it is pending and can correct the number or mark the enrollment inactive. [FR1.9h]
- **AC1.15.3** — Given a declined seat, When I view the roster, Then I see it as declined, distinctly from pending. [FR1.9h]
- **AC1.15.4** — Given a seat is declined, Then I receive no notification. [FR1.9h]

*INVEST*: Testable. AC1.15.3 is what makes a mistyped digit discoverable at all.

### US1.16 — Signup cannot be abused

As **the platform owner** (P4), I want signup bounded independently of the OTP
path, so that an informative response cannot be used to enumerate numbers or
exhaust the SMS budget.

- **AC1.16.1** — Given signup requests from one number, When the per-number ceiling is exceeded, Then further requests are refused. [FR1.7d]
- **AC1.16.2** — Given signup requests from one IP, When the per-IP ceiling is exceeded, Then further requests are refused. [FR1.7d]
- **AC1.16.3** — Given signup exists, When `POST /v1/auth/otp` is called for a known and for an unknown number, Then the two responses remain **byte-identical**. [FR1.7e] [BR2.7]
- **AC1.16.4** — Given the already-added lookup, When it is called for any number, Then its response names neither a teacher nor a batch. [FR1.7f]

*INVEST*: Independent of the UI stories; Testable adversarially. A separate
story from US1.8 rather than extra criteria on it, because signup and OTP have
opposite disclosure properties by design and conflating their controls is how
one inherits the other's assumptions [Q3].

### US1.17 — withdrawn

**Drafted and removed at review** [human, this stage]. It said every screen
must have a row in `docs/delivery/bangla-layout-check.md` before its unit
completes — which is true, and is not a user story. Its personas did not want
it, its criteria were about a committed file, and one of them defined
done-ness. FR0.1 was already marked `N/A` in traceability for being a delivery
standard rather than a behaviour; FR0.2 is the same kind of thing and is now
marked the same way.

The obligation is not weakened by removing the story. It lives in [FR0.2] and
in the committed check file, which already treats a missing row as an
incomplete unit.

## Dependencies

```
US1.11 (signup)
  └─> US1.12 (signup on an added number)
  └─> US1.10 (accept or decline)
        ├─> US1.13 (change my mind)
        ├─> US1.14 (declining stops the money)
        └─> US1.15 (a seat nobody accepts)

US1.16 (abuse controls)  — independent, built alongside US1.11
US1.17 (per-screen check) — applies to every unit, no dependency
```

US1.11 precedes everything: nothing else in D1 can be demonstrated until an
account can exist. US1.14 depends on D3's ledger machinery existing in some
form, which is recorded as a known ordering question rather than hidden.

## Assumptions & Open Questions

- **Settled at review**: US1.14's ledger ordering. The first draft flagged it
  as open beside AC1.14.2; the review was right that a gap sitting *inside* a
  criterion leaves a developer unable to tell whether D1 is done. It is now
  AC1.14.2a — D1 carries the minimum ledger to append a reversal, and nothing
  more of D3's machinery.
- **Assumed**: a teacher correcting a mistyped number creates a fresh seat
  rather than editing the old one in place. [AC2.5.1a] permits removing the
  unaccepted seat and [AC1.3.4a] offers a correction path; which of the two the
  UI uses is a Functional Design choice, and both end in the right place.
- **Open**: whether a guardian who declines should be able to tell the teacher
  *why* — a wrong number versus an unwillingness to oversee. [AC1.15.4] sends
  no notification and [AC1.3.3a] shows declined on the roster, so the teacher
  learns the fact but not the reason. Deliberate for V1; worth revisiting if
  teachers report chasing declines they cannot interpret.
