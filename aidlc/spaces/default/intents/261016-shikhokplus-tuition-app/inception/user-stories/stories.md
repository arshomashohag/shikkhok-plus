# User Stories — ShikhokPlus V1

**Stage**: user-stories (2.4)
**Phase**: Inception
**Date**: 2026-10-17

Grouped by proto-Unit, in dependency order. **One story per actor** [Q2], so a
teacher action and its student- or guardian-side consequence are separate
stories. **Every story is Must Have** [Q1], per the Scope Definition decision
that V1 carries no lower tier; the real sequencing decision belongs to Delivery
Planning.

`US{group}.{seq}` and `AC{group}.{seq}.{n}` are permanent traceability keys.

---

## US1 — Authentication and identity (PU-1)

### US1.1 — Teacher signs in

As **a teacher**, I want to sign in with my phone number and a code, so that I
reach my batches without remembering a password.

- **AC1.1.1** — Given I enter a valid Bangladeshi phone number, When I request a code, Then an SMS arrives and the screen tells me a code was sent to that number. [FR1.2]
- **AC1.1.2** — Given I received a code, When I enter it within 5 minutes, Then I am signed in and my teacher lens is active. [FR1.2] [NFR13]
- **AC1.1.3** — Given I enter a code more than 5 minutes after it was sent, When I submit it, Then it is refused as expired and I am offered a new one. [NFR12]
- **AC1.1.4** — Given I enter the wrong code 5 times, When I try a 6th, Then the code is dead and I must request a new one. [NFR12]
- **AC1.1.5** — Given the SMS never arrives, When the cooldown expires, Then a resend is offered and the message says delivery failed rather than that my code was wrong. [FR1.13]
- **AC1.1.6** — Given I type my number, Then it is never read from the SIM, and the app holds no SMS read permission. [FR1.2] [NFR11]

*INVEST*: Independent (nothing precedes it), Testable (every criterion is
mechanical). This story plus US1.2 is the walking skeleton.

### US1.2 — Student or guardian claims a dormant record

As **a student or guardian**, I want to sign in with the number my teacher
recorded, so that I can see what was recorded about me without anyone inviting
me.

- **AC1.2.1** — Given a teacher recorded my number and I have never signed in, When I sign in for the first time, Then my account activates and the batches recorded against my number appear. [FR1.8]
- **AC1.2.2** — Given my number appears as a student on one enrollment and as a guardian on another, When I sign in, Then both lenses are offered. [FR1.4] [FR1.6]
- **AC1.2.3** — Given my number appears only as a student, When I sign in, Then no guardian lens is offered. [FR1.4]
- **AC1.2.4** — Given I am signed in, When I switch lens, Then the view changes without re-authenticating. [FR1.5]

### US1.8 — The code cannot be abused

As **the operator**, I want the OTP path bounded against abuse, so that a
malicious caller cannot exhaust the SMS budget or brute-force a code.

- **AC1.8.1** — Given one number has requested 3 codes within an hour, When a 4th is requested, Then it is refused; and given 5 within a day, a 6th is refused. [NFR12]
- **AC1.8.2** — Given one IP has requested 10 codes within an hour, When an 11th is requested, Then it is refused. [NFR12]
- **AC1.8.3** — Given the rate-limit counters, Then they are datastore-backed rather than per-process, because a per-process counter passes every test and silently stops working with two workers, which Phase 1 has. [NFR12] [team: Walking Skeleton]
- **AC1.8.4** — Given the global daily SMS ceiling is reached, Then further sends are refused and an alert fires. [NFR12]
- **AC1.8.5** — Given the ceiling or a sub-ceiling trips, When a legitimate user requests a code, Then they are told the service is temporarily unavailable rather than that their number is invalid, and the message does not reveal the limit. [NFR12] [team: degraded mode]
- **AC1.8.6** — Given a code was issued, Then the stored value differs from the transmitted one, and no log line at any level contains the code. [NFR12] [project: NEVER store or log an OTP in plaintext]
- **AC1.8.7** — Given a request for a number that has an account and one that does not, Then the two responses are byte-identical and the unknown-number path performs the same hashing work rather than returning early. [NFR12] [desc §12f]

*Why this is its own story*: five of the seven abuse controls are
user-observable and two were already criteria of US1.1, so the line was an
omission rather than a principle. Per-SMS billing makes this a direct budget
exposure, and it sits inside the walking skeleton by the affirmed practices.

### US1.9 — Role is resolved per request, never stored

As **the system**, I want each request's lens derived from current data, so
that a change in what someone owns takes effect immediately and no stale role
survives.

- **AC1.9.1** — Given a request, Then the lens is computed from owned batches and enrollments at that moment; no role is read from the account record and none is cached across requests. [FR1.3] [project rule]
- **AC1.9.2** — Given an account that owned no batches and then creates one, When its next request arrives, Then the teacher lens is available without re-authenticating. [FR1.3]
- **AC1.9.3** — Given an account whose last enrollment is removed, When its next request arrives, Then the student lens is no longer available. [FR1.3]
- **AC1.9.4** — Given lens resolution within one request, Then memoising it for that request is permitted; caching it across requests is not. [FR1.3] [team: request-scoped memoization]

*Why this needs a story*: a cached role is indistinguishable from a computed
one on every happy path. Only AC1.9.2 and AC1.9.3 — where ownership changes
mid-session — can tell them apart, and this is the single most-mandated rule in
the project.

### US1.3 — Teacher creates a record for a number that never signs in

As **a teacher**, I want a mistyped number to simply stay unclaimed, so that a
typo costs me nothing and nobody else receives my student's data.

- **AC1.3.1** — Given I enrolled a number nobody owns, When nobody ever signs in with it, Then the enrollment stays dormant indefinitely and I continue to use it normally for attendance, marks and fees. [FR1.8] [FR1.9]
- **AC1.3.2** — Given a dormant enrollment, Then no notification, invitation or reminder is ever sent to that number. [FR1.7]
- **AC1.3.3** — Given a dormant enrollment, When I view the roster, Then it is **not** marked there, because dormant is the normal state early in a batch's life and decorating most rows would flag normality as a problem. [FR1.8] [Q7.3]
- **AC1.3.4** — Given I open an enrollment's detail, Then it states whether that person has ever signed in, and offers a path to correct the phone number. [Q7.3]
- **AC1.3.5** — Given a batch, Then it shows how many enrollments have been claimed out of the total — for example "9 of 12 have signed in" — so I can see the scale without per-row clutter. [Q7.3]
- **AC1.3.6** — Given an enrollment, Then **never claimed** is distinguishable from **claimed and then deleted**, because the first may be a mistyped number and the second is a person who left. [FR1.8] [FR11.1]

*Why AC1.3.4 and AC1.3.5 exist.* AC1.3.2 guarantees no notification ever
reaches a dormant number, so a teacher who mistyped a guardian's number
believed that guardian was receiving updates while the guardian never knew they
were enrolled — mutually invisible. The roster stays undecorated because
dormant is normal; the information lives where a teacher looks when they
suspect something, plus one batch-level count.

### US1.4 — Teacher enrolls a number that already owns batches

As **a teacher**, I want to be warned when I enroll a number belonging to
another teacher, so that I do not silently add a colleague as my student.

- **AC1.4.1** — Given I enter a number that owns at least one batch, When I confirm the enrollment, Then I am warned that the number belongs to an existing teacher before it is created. [FR1.11]
- **AC1.4.2** — Given the warning, When I proceed, Then the enrollment is created and that account gains a student lens alongside its teacher lens. [FR1.10] [FR1.6]

### US1.5 — Any user edits their own profile

As **any signed-in user**, I want a private profile only I can see, so that my
own name and photo are mine regardless of what a teacher typed.

- **AC1.5.1** — Given I open my profile, Then I can set a self-entered name and photo. [FR1.12]
- **AC1.5.2** — Given I save a profile name, When any teacher views any roster containing me, Then they see the display name they typed, unchanged. [FR1.12] [FR2.4]
- **AC1.5.3** — Given I am on the profile screen, Then helper text states that this does not change what teachers see. [FR1.12]

### US1.6 — Any user deletes their account in-app

As **any signed-in user**, I want to delete my account from inside the app, so
that I can leave without contacting anyone.

- **AC1.6.1** — Given I request deletion and confirm, Then my account and private profile are removed per each table's recorded disposition. [FR1.14] [FR11.1]
- **AC1.6.2** — Given I was a student or guardian, When my account is deleted, Then the teacher-authored enrollment, attendance, marks and fee records remain and the enrollment reverts to dormant. [FR11.1]
- **AC1.6.3** — Given I already deleted my account, When a second deletion request arrives, Then it succeeds without error and changes nothing further. [FR11.3]

### US1.7 — Anyone deletes an account from the web

As **a person who no longer has the app installed**, I want to request deletion
from a web page, so that uninstalling does not trap my data.

- **AC1.7.1** — Given I open the external deletion route without the app installed, When I verify ownership of my number, Then deletion proceeds identically to the in-app path. [FR1.15]
- **AC1.7.2** — Given the route, Then it is reachable without authenticating through the app and names the app and developer. [FR1.15]

---

## US2 — Batches and enrollment (PU-2)

### US2.1 — Teacher creates a batch

As **a teacher**, I want to set up a batch with its subjects, fee and schedule,
so that everything else attaches to it.

- **AC2.1.1** — Given I create a batch, Then I set a name, one or more subjects, a default monthly fee, a fee due day and weekly schedule slots. [FR2.1]
- **AC2.1.2** — Given I set a fee due day of 29, 30 or 31, When a month lacks that day, Then the due date clamps to that month's last day. [FR5.2]
- **AC2.1.3** — Given a created batch, Then its ownership is recorded through an owner entity rather than directly against my account. [FR2.2]

### US2.2 — Teacher enrolls a student

As **a teacher**, I want to add a student by phone number with an optional
guardian number, so that both can see what I record.

- **AC2.2.1** — Given I enroll a student, Then I supply a phone number, an optional guardian phone number and a display name I type. [FR2.3]
- **AC2.2.2** — Given I typed a display name, Then it belongs to this enrollment and not to the person's account. [FR2.4]
- **AC2.2.3** — Given the same student is in two of my batches, Then they are enrolled twice and each enrollment carries its own display name and fee. [FR2.9]
- **AC2.2.4** — Given a number already has an account from another teacher, When I enroll it, Then the enrollment attaches to that existing account. [FR1.10]
- **AC2.2.5** — Given I set a per-enrollment fee, Then it overrides the batch default; absent one, the batch default applies. [FR2.8]

### US2.3 — Teacher corrects a misspelled name

As **a teacher**, I want to fix a student's display name, so that the marksheet
does not show it wrong.

- **AC2.3.1** — Given an enrollment, When I edit the display name, Then every roster, marksheet and dues view I see reflects it immediately. [FR2.5]
- **AC2.3.2** — Given I change a display name, Then the student's own private profile is unaffected. [FR2.5] [FR1.12]

### US2.4 — Teacher marks a student inactive from a date

As **a teacher**, I want to mark a student inactive from a date, so that future
fees stop while what they already owe remains.

- **AC2.4.1** — Given I mark a student inactive from a date, Then no fee cycle generates for any period beginning **strictly after** that date, while the period **containing** the date still generates. [FR2.11] [FR5.3] [Q7.1]
- **AC2.4.2** — Given existing unpaid cycles, When I mark them inactive, Then those dues stand unchanged. [FR2.11]
- **AC2.4.3** — Given the same student is active in another of my batches, When I mark them inactive here, Then the other enrollment is unaffected. [FR2.11]
- **AC2.4.4** — Given the inactive date falls inside a period, Then that period's cycle stands in full — whether it was generated before I marked them inactive or generates afterwards — and I may adjust it through the charge-adjustment path. The outcome does not depend on whether the daily job had already run. [FR5.6] [Q7.1]
- **AC2.4.5** — Given a student I mark inactive from the 1st of a period, Then that period still charges in full unless I adjust it. [FR5.6] [Q7.1]

### US2.5 — Teacher removes a mistaken enrollment

As **a teacher**, I want to delete an enrollment I created by mistake, so that a
typo does not sit on my roster forever.

- **AC2.5.1** — Given an enrollment that is dormant and has no attendance, marks or fee history, When I remove it, Then it is deleted. [FR2.12]
- **AC2.5.2** — Given an enrollment with any attendance, marks or fee history, When I attempt removal, Then it is refused and marking inactive is offered instead. [FR2.12]

### US2.6 — Student sees their batches

As **a student**, I want a list of my batches, so that everything about each one
is in one place.

- **AC2.6.1** — Given I am signed in as a student, Then I see every batch where my number is the recorded student. [FR2.9]
- **AC2.6.2** — Given a batch is inactive, Then it is read-only and collapsed by default, with all history still reachable. [FR8-intent]
- **AC2.6.3** — Given an inactive batch, When I hide it, Then it disappears from my list only, not from the guardian's or the teacher's. [FR2.13]

### US2.7 — Guardian selects which child to view

As **a guardian with more than one child**, I want to choose a child, so that I
see one child's records at a time.

- **AC2.7.1** — Given two or more children are reachable from my number, When I sign in, Then I am asked which child to view. [FR2.15]
- **AC2.7.2** — Given exactly one child is reachable, When I sign in, Then I go straight to that child's batches with no selection step. [FR2.15]
- **AC2.7.3** — Given the selection list, Then each child shows their display name and the teacher who recorded them. [FR2.16]
- **AC2.7.4** — Given a selected child, When I switch to another, Then the view changes without re-authenticating. [FR2.17]

### US2.8 — Guardian sees only the batches their number reaches

As **a guardian**, I want to see the batches recorded against the number I
signed in with, so that what I see matches what a teacher recorded.

- **AC2.8.1** — Given teacher A recorded my number PN1 and teacher B recorded PN2 for the same child, When I sign in with PN1, Then I see teacher A's batch only. [FR2.7] [FR2.18]
- **AC2.8.2** — Given that situation, When I sign in with PN1, Then the child appears once, not twice. [FR2.18]
- **AC2.8.3** — Given any batch in my view, Then it shows which teacher it belongs to, so attribution does not depend on reaching the child-selection list. [FR2.16]
- **AC2.8.4** — Given my batch list, Then a persistent statement says the view is keyed to the number I signed in with, showing that number partially masked. [A3]
- **AC2.8.5** — Given exactly one child is reachable and the selection list is therefore skipped, Then AC2.8.3 and AC2.8.4 still apply. This is the case the explanation is most needed in and the one the selection list cannot reach. [FR2.15] [A3]
- **AC2.8.6** — Given zero children are reachable from my number, Then an empty state says so and explains that a teacher must record this number, rather than showing a blank list. [FR2.14]

*Why AC2.8.5 exists*: FR2.16 put the recording teacher in the child-selection
list, and FR2.15 skips that list when only one child is reachable. So the single
explanatory signal in the specification was invisible in precisely the worst
case — one child, two teachers, one visible batch. A guardian there sees one
batch, no explanation, and concludes the app lost her data.

*AC2.8.6 is the guardian-side face of the mistyped number*: FR2.15 covered one
child and two-or-more, never zero.

**A3 remains an assumption, narrowed.** The guardian now has attribution and a
statement of what the view is keyed to. What is still assumed is that she infers
"the other teacher recorded a different number" rather than "data is missing".
The structural fix — letting an account verify a second number and union the
batches — is deferred, and is compatible with the lens model unchanged.

---

## US3 — Schedule, sessions and attendance (PU-3)

### US3.0 — Sessions exist to be recorded against

As **a teacher**, I want the classes implied by my weekly schedule to exist as
sessions, so that there is something to record attendance against.

Added after the review: US3.1 opens a session, and nothing created one. The
schedule slots from US2.1 are a weekly recurrence rule, not instances.

- **AC3.0.1** — Given a batch with weekly schedule slots, Then a session exists for each occurrence, identified by its date and start time. [FR3.1] [FR3.2]
- **AC3.0.2** — Given I change a batch's schedule slots, Then existing past sessions are unaffected and future occurrences follow the new slots. [FR3.1]
- **AC3.0.3** — Given a date with no scheduled slot, When I hold a class anyway, Then I can create an ad-hoc session for it. [FR3.2]

*Whether sessions are materialised rows or computed from the recurrence rule is
a schema decision for Domain Design, not a story decision. What the story
fixes is that they must be addressable either way, because attendance and
topics attach to them.*

### US3.1 — Teacher records a session mid-class

As **a teacher**, I want to record the topic and mark attendance during class,
so that I do it once rather than reconstructing it later.

- **AC3.1.1** — Given a scheduled session, When I open it, Then I record the subject and the topic covered. [FR3.2]
- **AC3.1.2** — Given the session roster, When I mark each student present or absent, Then attendance is recorded per enrollment. [FR3.5]
- **AC3.1.3** — Given I have no connectivity, When I submit the roster, Then it is **queued on the device** and shown as saved-on-phone-not-yet-sent, never as confirmed, and it syncs automatically when connectivity returns with no action from me. [FR3.6] [NFR5] [NFR5.1] [mockups: Q11.2]
- **AC3.1.9** — Given a queued write, When I close and reopen the app, Then the queue survives and still shows as not yet sent. [NFR5.1]
- **AC3.1.10** — Given a queued write, Then it is visually distinct from both a confirmed write and a failed one — three states, not two. [NFR5.1] [AC9.2.2]
- **AC3.1.4** — Given the roster opens, Then every student defaults to present and I mark only the exceptions. [FR3.5]
- **AC3.1.5** — Given I have marked the roster, When I submit, Then the whole roster is written in **one atomic operation** — never one write per student. A per-student write leaves attendance half-saved after a mid-roster connection drop, and a retry cannot reconcile that on screen. [FR3.5] [FR3.6]
- **AC3.1.6** — Given I submit, Then the confirmation names the present and absent counts, so a mis-tap is visible before it is committed. [FR3.5]
- **AC3.1.7** — Given a session whose attendance I already recorded, When I reopen it, Then I can correct it, and the correction is visible per FR9.2. [FR3.5] [FR9.2]
- **AC3.1.8** — Given no speed requirement applies [Q14.3], Then **no criterion here constrains elapsed time**, and the properties that stand in its place are AC3.1.4's default-present and AC3.1.5's single atomic write. Nothing in V1 measures how long marking takes. [FR3.5] [Q14.3]

*AC3.1.4 and AC3.1.5 are the design answer to a requirement that was dropped.*
You removed the speed obligation [Q14.3], so nothing measures mid-class speed.
These two make it structurally fast instead: default-present turns twelve taps
into one or two, and one atomic write means a dropped connection loses nothing
rather than half a roster. AC3.1.8 records the absence so a developer neither
invents a latency budget nor reads the gap as licence.

### US3.2 — Teacher reschedules or cancels a session

As **a teacher**, I want to move or cancel a class, so that the schedule matches
reality.

- **AC3.2.1** — Given a scheduled session, When I reschedule it, Then its date and time change and students and guardians see the new time. [FR3.4]
- **AC3.2.2** — Given a scheduled session, When I cancel it, Then its status is cancelled and no attendance can be recorded against it. [FR3.3] [FR3.4]

### US3.3 — Teacher posts an announcement

As **a teacher**, I want to post a note to a batch, so that I tell everyone once
instead of messaging individually.

- **AC3.3.1** — Given a batch, When I post an announcement, Then every student and guardian in that batch sees it. [FR3.8]
- **AC3.3.2** — Given my announcement, When I edit it, Then it shows as edited. [FR3.9]
- **AC3.3.3** — Given my announcement, When I delete it, Then it disappears from student and guardian views. [FR3.9]
- **AC3.3.4** — Given any announcement, Then it never expires automatically. [FR3.9]

### US3.4 — Student sees the next class and what was covered

As **a student**, I want to see when the next class is and what we have covered,
so that I know where I stand.

- **AC3.4.1** — Given a batch, Then I see the next scheduled class date and time. [FR3.7]
- **AC3.4.2** — Given past sessions, Then I see the topics covered in each. [FR3.7]
- **AC3.4.3** — Given no connectivity, When I open a batch I have viewed before, Then the last fetched schedule and topics are shown with their age indicated. [NFR4]

### US3.5 — Guardian sees attendance and progress

As **a guardian**, I want to see whether my child actually attended, so that I
know what my money bought.

- **AC3.5.1** — Given my child's batch, Then I see their attendance per session. [FR3.7] [desc §1]
- **AC3.5.2** — Given past sessions, Then I see the topics covered, so I can see teaching is progressing. [FR3.7]

---

## US4 — Exams and marksheets (PU-4)

### US4.1 — Teacher creates an exam and enters marks

As **a teacher**, I want to record an exam and its marks, so that students and
guardians see results without me reading them out.

- **AC4.1.1** — Given a batch and subject, When I create an exam, Then I set a title, date and total marks. [FR4.1]
- **AC4.1.2** — Given an exam, When I enter marks, Then I record one result per enrollment. [FR4.2]
- **AC4.1.3** — Given a student who did not sit the exam, When I record their result, Then I mark them Absent, which is distinct from a mark of zero. [FR4.3]
- **AC4.1.4** — Given I have not finished marking, Then unmarked results show as not yet entered rather than as absent or zero. [FR4.3]
- **AC4.1.5** — Given a student enrolled after the exam date, Then their result shows as not applicable rather than absent. [FR4.3]

### US4.2 — Teacher controls marksheet visibility

As **a teacher**, I want to turn the shared marksheet off for a batch, so that I
can match what the families of that batch expect.

- **AC4.2.1** — Given a new batch, Then marksheet visibility defaults to on. [FR4.6]
- **AC4.2.2** — Given I turn it off, When a student or guardian opens the batch, Then no marksheet is shown at all. [FR4.6]

### US4.3 — Student sees their own and peers' marks

As **a student**, I want to see my mark alongside the rest of the batch, so that
I know where I stand.

- **AC4.3.1** — Given a past exam with visibility on, Then I see my own mark, named. [FR4.5]
- **AC4.3.2** — Given the same exam, Then I see my **rank**, the batch **average**, the **highest mark**, and a **banded distribution** — not a list of other students' individual marks. [FR4.5] [design: deanonymisation by inference]
- **AC4.3.3** — Given fewer than 3 results fall in a band, Then that band merges with its neighbour, so a band never identifies one student. [FR4.5]
- **AC4.3.4** — Given fewer than 5 results are marked for the exam, Then no comparison is shown at all — only my own mark. [FR4.5]
- **AC4.3.5** — Given marking is incomplete, Then no rank or average is shown, because a rank that drifts from 2nd to 7th as marks arrive reads as the app changing my result. [FR4.3] [FR4.5]
- **AC4.3.6** — Given students marked Absent, Then they are excluded from the average, the rank and the distribution. [FR4.3] [FR4.5]
- **AC4.3.7** — Given I am in two batches, Then each marksheet shows only that batch's results, never across batches. [FR4.4]

*Why this replaces a row list.* FR4.5 says other rows are anonymised. In a
batch of 8 to 20 students who sit together and discuss their marks, twelve
unattributed numbers are deanonymised by inference within a day — so
"anonymised" would over-claim for a product under a Families declaration. Rank,
average and bands give the standing the brief wants motivating [desc §10]
without publishing a list that can be matched up. It also fits [TC-9] better:
a rank and a band are decisions the server makes, where a row list invites the
client to sort.

**This is a change to how FR4.5 is satisfied, not to FR4.5.** Raised at the
gate.

### US4.4 — Guardian sees their child's progress over time

As **a guardian**, I want to see my child's marks across exams, so that I can
tell whether they are improving.

- **AC4.4.1** — Given my child has sat two or more exams, Then I see their results in date order. [FR4.7]
- **AC4.4.2** — Given an exam where my child was absent, Then it shows as Absent rather than as a zero that would distort the trend. [FR4.3] [FR4.7]

---

## US5 — Fee cycles (PU-5)

### US5.1 — Fee cycles generate monthly

As **a teacher**, I want fees to appear each month without my doing anything, so
that collection is a review rather than a data-entry task.

- **AC5.1.1** — Given an active enrollment, When a new period begins, Then a fee cycle generates with the enrollment's fee as its charged amount. [FR5.3] [FR5.1]
- **AC5.1.2** — Given N generation runs for the same period overlapping **concurrently**, Then exactly one cycle row exists per `(enrollment, period)` and the ledger's charged total equals one period's charge. A sequential two-run test does not satisfy this criterion: an application-level "has this already run" guard passes sequentially and fails with two workers, which Phase 1 has. [FR5.4] [project: ALWAYS test fee-cycle generation idempotency with overlapping concurrent generations]
- **AC5.1.3** — Given generation was missed yesterday, When it runs today, Then the missing cycle appears and no duplicate is created for periods already generated. The across-days case is tested separately from AC5.1.2, because concurrency alone does not exercise it. [FR5.5]
- **AC5.1.6** — Given a cycle already exists for an `(enrollment, period)`, When generation encounters it, Then the conflict is the **success path** and not an error: generation completes without raising. [FR5.4] [team: error handling]
- **AC5.1.4** — Given an enrollment inactive from before the period, Then no cycle generates. [FR5.3]
*AC5.1.5 was removed from this story and promoted to System-wide invariants
below: money-as-a-string is a system-wide property enforced mechanically in CI,
and attaching it to one story implies the other money stories are unbound.*

### US5.2 — Teacher adjusts what a student owes

As **a teacher**, I want to change what a student actually owes, so that the
amount matches what I agreed with them.

- **AC5.2.1** — Given a fee cycle, When I adjust the charged amount, Then the balance recalculates and the ledger records charged, received, carried forward and forgiven separately. [FR5.1]
- **AC5.2.2** — Given I adjust an amount, Then the previous value and that I changed it are visible to me and to that student and guardian. [FR9.1] [FR9.2]

### US5.3 — Student sees their fee status

As **a student**, I want to see what I owe, so that I can tell my guardian
accurately.

- **AC5.3.1** — Given my enrollment, Then I see the current period's amount and whether it is paid, partly paid or unpaid. [FR5.8]
- **AC5.3.2** — Given past periods, Then I see each one's status and amount. [FR5.8]

### US5.4 — Guardian sees what is due and when

As **a guardian**, I want to know the next payment date and amount, so that I am
not surprised.

- **AC5.4.1** — Given my child's enrollment, Then I see the next due date and amount. [FR5.8]
- **AC5.4.2** — Given past cycles, Then I see each one's payment status. [FR5.8]

---

## US6 — Payment submission and verification (PU-6)

### US6.1 — Guardian submits a payment

As **a guardian**, I want to record that I paid, so that the teacher knows
without my telephoning.

- **AC6.1.1** — Given I paid out of band, When I submit, Then I select a batch, enter a transaction ID and an amount. [FR6.1]
- **AC6.1.2** — Given the batch selector, Then each option shows the child's name alongside the batch name. [FR6.3]
- **AC6.1.3** — Given I submit, Then a confirmation names both the child and the batch before it is recorded. [FR6.3]
- **AC6.1.4** — Given my amount is less than the balance, Then it is accepted as a partial payment. [FR6.4]
- **AC6.1.5** — Given my submission, Then it resolves to the enrollment's open fee cycle. Where no open cycle exists, the submission is refused with a stated reason rather than creating one. Where more than one unpaid cycle exists, it applies to the oldest. [FR6.2]
- **AC6.1.6** — Given I enter zero or a negative amount, Then the submission is refused before it is recorded. [FR6.4] [money boundary]
- **AC6.1.7** — Given I enter an amount exceeding the outstanding balance, Then the submission is accepted and recorded as claimed — the teacher decides at verification what to approve. Over-claiming is not blocked at submission, because money may genuinely have been overpaid out of band. [FR6.4] [money boundary]

### US6.2 — Student submits a payment

As **a student**, I want to submit a payment with the same form my guardian
uses, so that either of us can do it.

- **AC6.2.1** — Given I am a student, When I submit a payment, Then the form and its behaviour are identical to the guardian's. [FR6.1]

### US6.3 — Teacher verifies a claimed payment

As **a teacher**, I want to approve or reject what a guardian says they paid, so
that my records reflect money I actually received.

- **AC6.3.1** — Given pending submissions, Then I see them listed per batch. [FR6.5]
- **AC6.3.2** — Given a submission, When I approve it in full, Then the claimed amount is recorded as received. [FR6.6]
- **AC6.3.3** — Given a submission, When I approve a lesser amount, Then I choose whether the shortfall carries forward or is waived. **The shortfall is `charged − approved`, not `claimed − approved`** — what remains owed is measured against what was charged, because a guardian's claim is an assertion and the charge is the obligation. Where claim and charge differ, only the charge matters to the balance. [FR6.6] [FR6.8]
- **AC6.3.7** — Given I approve an amount exceeding what was charged, Then it is accepted and the excess is recorded as a **credit** on the ledger, never as a negative outstanding balance. Outstanding never goes below zero. [FR5.9] [FR6.6] [Q7.2]
- **AC6.3.8** — Given a credit exists on an enrollment, When the next cycle generates, Then the credit is applied against it automatically and the remaining credit, if any, carries on. [FR5.9] [Q7.2]
- **AC6.3.4** — Given a submission, When I reject it, Then nothing is recorded as received and the submitter sees the rejection. [FR6.6] [FR6.9]
- **AC6.3.5** — Given any verification, Then who approved it and when is recorded. [FR6.7]
- **AC6.3.6** — Given I approved wrongly, When I correct it, Then the previous decision and that I changed it are visible to me and to that student and guardian. [FR9.2] [FR9.3]

### US6.4 — Guardian sees what happened to their payment

As **a guardian**, I want to see whether my payment was accepted, so that a
dispute has a shared record.

- **AC6.4.1** — Given I submitted a payment, Then I see its status: pending, approved in full, approved in part, or rejected. [FR6.9]
- **AC6.4.2** — Given an approval for less than I claimed, Then I see the approved amount and whether the remainder carried forward or was waived. [FR6.9] [FR6.8]
- **AC6.4.3** — Given the teacher later corrected a verification, Then I see the correction and that it was changed. [FR9.2]

---

## US7 — Cross-batch dues (PU-7)

### US7.1 — Teacher sees everyone who owes money

As **a teacher**, I want one screen showing everyone who owes me money across
all my batches, so that month-end collection stops being reconstruction work.

- **AC7.1.1** — Given outstanding balances across several batches, When I open the dues view, Then I see every person who owes, with the amount and the batch. [FR7.1]
- **AC7.1.2** — Given a student marked inactive who still owes money, Then they appear in the dues view. [FR7.2]
- **AC7.1.3** — Given a student who is active and owes nothing, Then they do not appear. [FR7.2]
- **AC7.1.4** — Given the dues view, Then it is reachable from top-level navigation in one action and renders current data on open with no generate step. [FR7.3]
- **AC7.1.5** — Given nobody owes anything, Then a defined empty state is shown. [FR7.3]

---

## US8 — Teacher analytics (PU-8)

Split into four after the review. The original single story bundled four views
that share no code: a sum over verified payments, a multi-month series, a ratio
with its own denominator rules, and a cross-batch exam query. Criterion count
was the wrong sizing signal — the right one is how many data surfaces a story
first forces into existence, and this was four.

### US8.1 — Teacher sees this month's earnings

As **a teacher**, I want the total I actually received this month, so that I
know what the month produced.

- **AC8.1.1** — Given verified payments this month, Then I see the total received across all batches. [FR8.1]
- **AC8.1.2** — Given no verified payments this month, Then zero is shown as a value, not as an empty state — zero earned is a fact, not an absence of data. [FR8.1]

*Depends on US6*: only a verified payment counts as received.

### US8.2 — Teacher sees earnings over time

As **a teacher**, I want the trend across months, so that I can see whether
this is growing.

- **AC8.2.1** — Given two or more months of history, Then I see the received total per month in date order. [FR8.2]
- **AC8.2.2** — Given fewer than two months of history, Then no trend is shown, because a single point is not a trend. [FR8.2]

### US8.3 — Teacher sees the collection rate

As **a teacher**, I want to know what proportion of what I charged I actually
collected, so that I can tell a collection problem from a pricing one.

- **AC8.3.1** — Given a period, Then I see the collection rate: received in that period divided by charged in that period, as a percentage. [FR8.3]
- **AC8.3.2** — Given carried-forward amounts from earlier periods, Then they are excluded from both the numerator and the denominator, so the figure measures this period's collection rather than cumulative debt. [FR8.3]
- **AC8.3.3** — Given waived amounts, Then they are excluded from the denominator — a waiver is not an uncollected debt. [FR8.3]
- **AC8.3.4** — Given a credit applied from an earlier overpayment, Then it counts as received in the period whose charge it settles, not in the period it arrived. [FR8.3] [FR5.9]
- **AC8.3.5** — Given a period where nothing was charged, Then the rate shows as not applicable rather than zero or a division error. [FR8.3]

*AC8.3.4 is new*: the credit concept added at Q7.2 creates a question the
original collection-rate definition did not face.

### US8.4 — Teacher sees the next exam

As **a teacher**, I want the soonest upcoming exam at a glance, so that I know
what is coming without opening each batch.

- **AC8.4.1** — Given a future exam exists in any of my batches, Then I see the soonest one with its title, batch, subject, date and whole days remaining. [FR8.4]
- **AC8.4.2** — Given no future exam exists, Then an empty state says so. [FR8.4]
- **AC8.4.3** — Given two exams on the same date, Then one is shown with a deterministic tiebreaker rather than arbitrarily. [FR8.4]

*Depends on US4 only*, not on US5 or US6 — this is why the bundled story's
dependency was wrong.

---

## US9 — Notifications (PU-8, cross-cutting)

### US9.1 — Guardian is told when something needs attention

As **a guardian**, I want to be told when a fee is due or marks are published,
so that I do not have to keep opening the app.

- **AC9.1.1** — Given a fee cycle becomes due, Then I receive a notification. [FR10.1]
- **AC9.1.2** — Given my child's marks are entered, Then I receive a notification. [FR10.1]
- **AC9.1.3** — Given notification delivery fails, Then the operation that triggered it still succeeds. [FR10.2]
- **AC9.1.4** — Given notifications, Then no advertising or device identifier is transmitted. [NFR11]

---

### US9.2 — Any write that fails does not lose what I typed

As **any user**, I want a failed write to keep my input and tell me what
happened, so that no connectivity problem costs me my work.

Added after the mob round: there are 14 write stories across this backlog and
one documented failure path between them, under a rule that forbids offline
writes entirely [NFR5]. One cross-cutting story rather than a criterion on each.

- **AC9.2.1** — Given I have entered data and the write fails, Then everything I typed is preserved and the screen stays where it was. [NFR5] [corner: unsaved input]
- **AC9.2.2** — Given a write fails, Then the value is not painted as saved — an unconfirmed write never renders as a confirmed one. For the mid-class path, which queues [NFR5], there are **three** states and not two: confirmed, queued, and failed. Queued is never shown as confirmed. [NFR5] [NFR5.1] [TC-9]
- **AC9.2.3** — Given a failure, Then I can tell a connectivity failure from a server rejection, because the server supplies whether it is retryable rather than the client inferring it from a status code. [team: error taxonomy] [TC-9]
- **AC9.2.4** — Given I submit twice — by double-tap or by retrying after an unclear outcome — Then only one record is created. [corner: double submit]
- **AC9.2.5** — Given the dues view or any list fails to load, Then an error state is shown and **not** the empty state, because an empty dues view tells a teacher nobody owes him money. [FR7.3]

### US9.3 — The app works in Bangla, not just translated into it

As **a Bangla-first user**, I want the app to behave correctly in Bangla, so
that numerals, dates and ordering are not quietly wrong.

- **AC9.3.1** — Given any number **the app itself produces** — money, marks, dates and times, transaction IDs, phone numbers, counts — Then it renders in Latin numerals regardless of locale. [NFR3] [mockups: Q11.3]
- **AC9.3.4** — Given text **a person typed**, Then it is stored and displayed exactly as typed, including Bengali digits inside it. The app never normalises a user's prose. [NFR3] [mockups: Q11.3]
- **AC9.3.5** — Given a numeric field, Then Bengali digits are accepted on input and normalised to Latin before storage — a guardian typing ১২৫৪০০ into an amount field gets 125400. [NFR3] [mockups: Q11.3]
- **AC9.3.6** — Given a transaction ID, Then it is upper-cased with spaces removed on entry, and rendered in a monospaced face whose zero is distinguishable from O, because bKash and Nagad codes mix 0/O and 1/I/l. [NFR3] [mockups: design system]
- **AC9.3.2** — Given any list of people, Then ordering is collated server-side for the active locale rather than by byte order. [NFR3] [TC-9]
- **AC9.3.3** — Given the longest Bangla string on each screen, Then the layout holds without truncation or overflow. The named screens are the roster, the marksheet, the dues view, OTP entry, and every empty and error state — explanatory strings are the longest in the product and the least likely to be screenshotted. [NFR3] [project rule] |

*Why this bends the no-NFR-stories decision* [Q4]: these are not NFR
restatements. Each is a behaviour that is wrong in a specific, testable way if
unstated, and localization is the one NFR where "deferred to NFR Requirements"
risks the work being done untestably in the meantime.

### US9.4 — Status is never carried by colour alone

As **any user**, I want every status readable without relying on colour, so
that the app works for colour-blind users and in bright sunlight.

Added after the review. Accessibility is otherwise correctly deferred to
Refined Mockups and NFR Requirements, but three cases are story-level because
they are about *what information is present*, not how it looks.

- **AC9.4.1** — Given a fee status (paid, partial, unpaid) or an attendance mark (present, absent), Then the status is conveyed by text or an icon and never by colour alone. The server already sends a status enum [FR5.8], so the text is arriving — the story requires showing it. [NFR15] [TC-9]
- **AC9.4.2** — Given I switch lens or switch child, When I press Back, Then I do not land in the other lens's or other child's data. [FR1.5] [FR2.17] [NFR14]
- **AC9.4.3** — Given I confirm account deletion, Then the confirmation names what is deleted and what the teacher's records retain, per the per-table dispositions. [FR1.14] [FR11.1] [RC-5]

*AC9.4.2 is a privacy boundary case wearing navigation clothing*: the back
stack holding a previous lens's screen is a leak, not a usability defect.
*AC9.4.3 is an [RC-5] compliance exposure*: the privacy policy must state what
is retained after deletion, and a confirmation that does not say so contradicts
it at the moment it matters most.

---

## System-wide invariants

These hold across every story and are enforced mechanically in CI rather than
asserted per story. Attaching them to one story would imply the others are
unbound, which is the opposite of what they mean.

| Invariant | Enforcement | Source |
|---|---|---|
| Every money value crosses the API as a JSON string, never a number — asserted on both sides, with the client rejecting a number loudly rather than coercing it | Contract test on the generated schema, plus a client decode test | [FR5.7] [NFR9] [project rule] |
| No `TelephonyManager` phone-number read anywhere; the number is always typed | Semgrep rule plus the DEX scan on the release build | [FR1.2] [NFR11] [project rule] |
| No advertising or device identifier transmitted anywhere | Merged-manifest allowlist plus DEX scan, both failing build gates | [NFR11] [team: two build gates] |
| Money arithmetic exists only inside the money module | Import-boundary check from the first commit | [project rule] |
| Every route resolves a lens except the explicit allowlist | Route-enumeration test, asserted at collection time | [FR1.3] [AC10.1.7] |
| Bangla and English string bundles are both present from the first screen | Per-screen check; no hardcoded user-facing strings | [NFR3] [project rule] |

---

## US10 — The privacy boundary, adversarially (cross-cutting)

Added after the mob round. Every other story tests authorization from the
actor's **own** view — what they see. None tested what happens when someone
asks for data that is not theirs, which is the vulnerability class a scanner
cannot find because finding it requires knowing the intended policy. The
affirmed practices mandate exactly these probes; the story is where the policy
they probe is stated.

### US10.1 — The system refuses a request for someone else's data

As **the system**, I want every request for data outside the requester's lens
refused, so that the privacy boundary holds against a crafted request and not
only against the UI.

- **AC10.1.1** — Given teacher A is signed in, When A requests teacher B's batch by its identifier, Then the request is refused as an `AuthorizationError`. [NFR14] [desc §12f] [team: error taxonomy]
- **AC10.1.2** — Given a guardian signed in, When they request an enrollment for a child that is not theirs, Then the request is refused as an `AuthorizationError`. [NFR14] [team: error taxonomy]
- **AC10.1.3** — Given a student signed in, When they request a fee cycle that is not their own, Then the request is refused as an `AuthorizationError`. [NFR14] [team: error taxonomy]
- **AC10.1.4** — Given any such refusal, Then it carries `retryable: false` and the response does not disclose whether the requested resource exists. A refusal that is retryable, or that distinguishes "not yours" from "does not exist", defeats the purpose. [NFR12-enumeration] [desc §12f] [team: error taxonomy]
- **AC10.1.5** — Given any teacher-lens response schema, Then it contains no owner-private profile field. Asserted across the whole generated schema rather than per endpoint, so an endpoint added later is covered. [FR9.4] [NFR14] [team: schema-wide invariant]
- **AC10.1.6** — Given a client sends a lens hint, When the hint claims a lens the account's data does not support, Then the server ignores it and resolves the lens from owned batches and enrollments. [FR1.3] [project: never trust a client-supplied lens hint]
- **AC10.1.7** — Given every route in the application, Then each resolves a lens, except an explicit allowlist containing only OTP issue, OTP verify, health, and the external deletion route. [FR1.3] [team: route-enumeration test]
- **AC10.1.8** — Given one account holding both a teacher lens and a guardian lens, When it switches lens inside a single session, Then no data resolved under one lens is served under the other. [FR1.6] [NFR14]

*AC10.1.8 is the one a cache-by-resource-id implementation breaks silently*:
the obvious optimisation caches a batch by its id, and the same account holding
two lenses then reads it under whichever lens asked first.

---

## Dependencies

```
US1 (auth, identity, dormant records, deletion)
 └─> US2 (batches, enrollment, guardian child selection)
      ├─> US3 (sessions, attendance, announcements)  ─┐
      ├─> US4 (exams, marksheets)                     │ independent
      └─> US5 (fee cycles)                           ─┘ of each other
           └─> US6 (payment submission, verification)
                └─> US7 (cross-batch dues)
US8.1's earnings, collection rate and trend need **verified payments from
US6**, not merely generated cycles from US5 — received and waived amounts only
exist once a teacher has approved something. Its next-exam view needs only US4.
US9.1 fires on both a fee cycle (US5) and entered marks (US4), so it depends on
both. US9.2 and US9.3 span every write and every screen respectively.

Corrected after the review: the earlier line said US8 depended on US5 and US9
on US4, which understated both.
```

US1.1 plus US1.2 is the walking skeleton [team: Walking Skeleton].

---

## INVEST notes

| Criterion | How these stories meet it |
|---|---|
| **Independent** | Grouped by slice, so each group is deliverable once its predecessor exists. One-story-per-actor [Q2] means a teacher story does not require its student-side story to ship together. |
| **Negotiable** | Criteria state behaviour, not implementation. No story names a screen layout or an endpoint. |
| **Valuable** | Every story names a persona and a benefit. US1.3's value is to the teacher (a typo costs nothing), which is why it reads oddly as a user goal. |
| **Estimable** | Each story's criteria are countable and mechanical. US8.1 is the largest and may need splitting — flagged for the mob. |
| **Small** | Most are 3–6 criteria. US1.1 (6) and US8.1 (6) are the largest; US5.1 at 5 carries the most risk per criterion. |
| **Testable** | Every criterion is Given/When/Then with an observable outcome. Three criteria deliberately assert an **absence** (AC1.3.3, AC3.1.4, AC5.1.5) because an unstated absence gets implemented as its opposite. |

---

## Assumptions & Open Questions

- ~~AC6.3.7 introduces a credit concept the data model does not have.~~
  **Resolved at Q7.2**: the ledger gains a fifth quantity, a credit, and
  `requirements.md` was amended — FR5.1 now records five quantities rather than
  four, and FR5.9 states the overpayment rule. Domain Design inherits a ledger
  with a credit field rather than discovering the need for one.
- ~~AC1.3.3's roster decoration is arguable.~~ **Resolved at Q7.3**: the roster
  stays undecorated, and claim status moves to the enrollment detail with a
  number-correction path, plus a batch-level signed-in count [AC1.3.4,
  AC1.3.5]. The mutual-invisibility problem — neither teacher nor guardian
  learns a number was mistyped — is addressed where a teacher actually looks.
- ~~The `inactive_from` generation contradiction.~~ **Resolved at Q7.1**:
  the period containing `inactive_from` always generates and stands in full.
  FR5.3 was amended, since the contradiction was in the requirement rather than
  only in the story.
- **US8.1 may be too large**, carrying six criteria across four distinct views
  (monthly total, trend, collection rate, next exam). It is one story because
  the dashboard is one screen; it may need splitting for estimability.
  [assumption]
- **No story covers concurrent edits** [FR11.4]. Last-write-wins with
  correction history is specified, but writing it as a story would require
  describing a race the teacher cannot observe. Covered by the requirement, not
  a story. [assumption]
- **No story covers the teacher-deletion cascade** [FR11.2], because its
  behaviour is not yet decided — it is an open Domain Design question. US1.6
  covers the student and guardian case only. [assumption]
- **No stories for the 17 NFRs** [Q4]. All are Deferred to NFR Requirements in
  traceability. Three NFRs do appear inside criteria where they are
  user-visible (NFR4 in AC3.4.3, NFR5 in AC3.1.3, NFR13 in AC1.1.2), which is
  coverage of the behaviour rather than of the requirement. [assumption]
- **Every story is Must Have** [Q1], so the priority field carries no
  discriminating information. Recorded as instructed; Delivery Planning owns
  sequencing. [assumption]
- **US9.1's event set is incomplete.** Fee due and marks entered are specified;
  class cancellation, payment approval and announcements are plausible and
  unspecified. Owned by Functional Design. [assumption]

## Sources

- [desc] Initial description, §1–§11.
- [Q1], [Q2], [Q3], [Q4], [Q6] Confirmed answers in `user-stories-questions.md`.
- [FR*], [NFR*], [A3] `inception/requirements-analysis/requirements.md`.
- [Q14.3] the dropped mid-class speed requirement, `requirements-analysis-questions.md`.
- [team: *] `aidlc/spaces/default/memory/team.md`, affirmed practices.
