# Requirements — ShikhokPlus V1

**Stage**: requirements-analysis (2.3)
**Phase**: Inception
**Date**: 2026-10-17

`FR{n}` and `NFR{n}` IDs are permanent traceability keys. Downstream stages
preserve them exactly rather than renumbering or replacing them with prose.

---

## Intent analysis

The goal is not "an app for tuition teachers". It is to make a teacher's own
records legible to the guardian who pays for them, without letting that
legibility cost the teacher anything. [desc]

Three goals follow, in priority order:

1. **Replace the notebook without slowing the class down.** A teacher's current
   system is fast because it is paper. Anything slower gets abandoned mid-term,
   taking the records with it. [desc §11]
2. **Give the guardian what they currently cannot get at all** — attendance,
   topics covered, marks over time, and what is owed. Guardian satisfaction is
   the stated renewal driver, so this is the commercial engine. [desc]
3. **Make month-end collection tractable.** The cross-batch dues view is the
   single feature a teacher would pay for, because it answers a question paper
   cannot: who owes me money right now, across everything I teach. [desc §6]

The structural goal underneath all three: the same records serve three parties
with asymmetric rights, and the asymmetry must hold by construction rather than
by discipline. [desc §4] [desc §12f]

---

## Functional requirements

### FR1 — Identity and authentication

| ID | Requirement | Source |
|---|---|---|
| FR1.1 | The phone number is the account identifier. One number is one account permanently; there is no second identifier and no account merging. | [desc §3] |
| FR1.2 | Authentication is phone number plus a one-time code delivered by SMS. There is no password, no email and no social login. | [desc §3] [feasibility: Q5] |
| FR1.3 | The account has no role field. Teacher, student and guardian are lenses resolved per request from owned batches and enrollments. | [desc §3] [desc §12c] |
| FR1.4 | At login, only the lenses that have data are offered. An account owning no batches is never offered a teacher lens. | [desc §3] |
| FR1.5 | An in-app lens switcher changes the active lens without re-authentication. | [desc §3] |
| FR1.6 | One account may hold two or more lenses simultaneously; being both a student and a guardian is normal and must work. | [desc §3] |
| FR1.7 | Only a teacher creates a student record. There is no self-registration, no join request and no invite acceptance. | [desc §3] |
| FR1.8 | A created record is dormant until that number first authenticates. A dormant record is fully functional for the teacher and invisible to anyone else. | [desc §3] |
| FR1.9 | A mistyped number produces a permanently dormant record. This is correct behaviour, not an error state, and the system never attempts recovery. | [desc §3] |
| FR1.10 | When a teacher enters a number that already has an account, the enrollment attaches to that existing account. Students carry their batches across teachers. | [desc §3] |
| FR1.11 | A teacher may enter a number that already owns batches. The system warns that the number belongs to an existing teacher and requires confirmation before proceeding. | [Q7] |
| FR1.12 | The account owns a private profile — self-entered name and photo — visible only to its owner, with helper text stating it does not change what teachers see. | [desc §4] |
| FR1.13 | When OTP delivery fails, the failure is presented as a delivery failure and not as an incorrect code. A resend becomes available once the cooldown expires, with rate limits still applying. | [Q12] |
| FR1.14 | In-app account deletion removes the account and its data per each table's written disposition. | [desc §11] [TC-19] |
| FR1.15 | An externally accessible deletion route performs the same deletion without requiring the app to be installed. | [desc §11] [TC-19] |

### FR2 — Batches and enrollment

| ID | Requirement | Source |
|---|---|---|
| FR2.1 | A teacher creates a batch with a name, subjects taught, a default monthly fee, a fee due day and weekly schedule slots. | [desc §6] |
| FR2.2 | Batch ownership is indirected through an owner entity, so a batch can later be owned by an organisation without migrating the batch. | [desc §12b] |
| FR2.3 | A teacher enrolls a student by phone number, an optional guardian phone number and a teacher-typed display name. | [desc §6] |
| FR2.4 | The display name belongs to the enrollment, not the account. The same person may legitimately appear under different names in different batches. | [desc §4] |
| FR2.5 | A teacher may edit any enrollment detail they typed, including the display name. | [desc §6] |
| FR2.6 | The guardian number is captured per enrollment. Two teachers holding different guardian numbers for one student is valid and neither is wrong. | [desc §10] |
| FR2.7 | A guardian sees exactly the enrollments recorded against the number they authenticated with. Where two teachers recorded different numbers for one child, each number reaches only its own teacher's batches. | [Q6] |
| FR2.8 | A per-enrollment fee override replaces the batch default. Absent an override, the batch default applies. | [desc §6] [desc §10] |
| FR2.9 | A student taking two batches is enrolled twice. All state is batch-level; nothing aggregates across batches except the teacher's dues view (FR7). | [desc §6] |
| FR2.10 | A teacher marks a student inactive **from a date**, not by a flag. | [desc §6] |
| FR2.11 | Marking inactive stops fee cycles for periods beginning after that date, leaves all existing dues standing, and leaves the student active in every other batch. | [desc §6] |
| FR2.12 | A teacher may remove an enrollment only while it is dormant and carries no attendance, marks or fee history. Otherwise marking inactive is the only exit. | [Q5] |
| FR2.13 | A student or guardian may hide an inactive batch from their own list. Hiding affects only that viewer. | [desc §5] |
| FR2.14 | The guardian app resolves the set of children reachable from the authenticated number — every distinct student account appearing on an enrollment where that number is the recorded guardian. | [desc §8] [Q6] |
| FR2.15 | Where exactly one child is reachable, the guardian app opens directly on that child's batch list with no selection step. Where two or more are reachable, it opens on child selection. | [Q15.1] |
| FR2.16 | The child-selection list shows each child's display name and the teacher who recorded them, so a guardian can tell which teacher's records they are about to view. | [Q15.2] |
| FR2.17 | A guardian may switch the selected child at any point without re-authenticating. | [desc §8] [desc §3] |
| FR2.18 | Where one child is reachable under two different guardian numbers recorded by different teachers, each number's login shows that child with only its own teacher's batches. The child appears once per login, not twice. | [Q6] [FR2.7] |
| FR2.19 | When a teacher enters a phone number on the add-student form, the system looks up existing enrollments **owned by that same teacher** and offers the teacher-authored display name and guardian number from the most recent such enrollment as editable defaults, stating which batch they came from. The lookup never reaches enrollments owned by another teacher and never returns self-authored profile data. A number enrolled only with another teacher is indistinguishable from a number enrolled nowhere — asserted as a **structural** property, not a wall-clock bound: the lookup performs the same owner-scoped query work regardless of whether an out-of-scope enrollment exists, and never short-circuits on a global existence check. This follows the precedent the team already set for OTP enumeration resistance, where a timing assertion was explicitly rejected as flaky. | [design: T8] [FR2.4] [FR2.6] [mockups: Q12.2] [team: Walking Skeleton] |

### FR3 — Schedule, sessions and attendance

| ID | Requirement | Source |
|---|---|---|
| FR3.1 | A batch carries weekly recurring schedule slots with a weekday, start time and end time. | [desc §6] [desc §10] |
| FR3.2 | A session records its date, start time, subject and the topic covered. | [desc §6] |
| FR3.3 | A session is scheduled, held or cancelled. | [desc §10] |
| FR3.4 | A teacher may reschedule or cancel a session. | [desc §6] |
| FR3.5 | Attendance is recorded per session per enrollment. **No speed requirement applies** — §11's mid-class speed statement was dropped as a requirement and carries no acceptance criterion or verifier, so nothing here constrains how long marking a batch may take. See Out of scope. | [Q5-intent] [Q14.3] |
| FR3.6 | Attendance and topic-log writes **queue locally when connectivity is absent** and sync automatically on reconnect. The teacher is told the entry is saved on the phone and not yet sent, and it is never rendered as confirmed until it syncs. This reverses the earlier connectivity-required rule for the mid-class path only, and partly restores the protection lost when the mid-class speed requirement was dropped: a queued write cannot fail mid-class. | [mockups: Q11.2] [NFR5] [NFR5.1] |
| FR3.7 | Students and guardians see the next class date and time, the topics covered to date, and attendance. | [desc §7] [desc §1] |
| FR3.8 | A teacher posts announcements per batch. | [desc §6] |
| FR3.9 | A teacher may edit or delete an announcement they posted. An edited announcement shows that it was edited; a deleted one disappears from student and guardian views. Announcements do not expire automatically. | [FR3.8] [gap: announcement lifecycle] |

### FR4 — Exams and marksheets

| ID | Requirement | Source |
|---|---|---|
| FR4.1 | A teacher creates an exam per batch and subject, with a title, date and total marks. | [desc §6] [desc §10] |
| FR4.2 | A teacher enters a mark per enrollment per exam. | [desc §6] |
| FR4.3 | A result distinguishes four states: a numeric mark, **Absent**, **not yet entered**, and **joined after the exam**. A zero is a numeric mark and never conflated with absence. | [Q9] |
| FR4.4 | The batch marksheet shows every enrollment's result for each past exam, scoped strictly to that batch and never across batches. | [desc §7] |
| FR4.5 | The viewer's own row is named. Every other row shows its result without an attached identity. | [Q10] [Q14.2] |
| FR4.6 | A per-batch visibility toggle, defaulting on, controls whether the marksheet is shown at all. | [desc §10] |
| FR4.7 | A guardian sees their child's results across exams over time. | [desc §8] |

### FR5 — Fee cycles

| ID | Requirement | Source |
|---|---|---|
| FR5.1 | The fee amount is a teacher-adjustable anchor, not a fixed amount due. The ledger records what was charged, received, carried forward, forgiven, **and credited** — five quantities, not four. The credit field was added to hold an overpayment [FR5.9], since without it an excess payment has nowhere to go but a negative outstanding balance, which the ledger invariant forbids. Carry-forward is recorded two-sided — relieving the originating period and charging the receiving one — so a carried debt is never counted in both [ADR-002]. | [intent: Q19] [US-Q7.2] [ADR-002] |
| FR5.2 | Fee periods are calendar months with a due day, clamped to the last day of months that lack it. | [intent: Q19] |
| FR5.3 | Cycles generate monthly for enrollments whose `inactive_from` is unset, or falls **on or after the first day of the period**. So the period *containing* `inactive_from` always generates; only periods beginning strictly after it do not. | [desc §10] [US-Q7.1] |
| FR5.4 | Generation is idempotent by database constraint on `(enrollment, period)`. Running it twice produces identical state. | [desc §12d] |
| FR5.5 | Generation runs daily so a missed day self-heals without producing duplicates. | [architecture §8d] |
| FR5.6 | Where a student goes inactive mid-period, that period's cycle stands in full — whether it was generated before the teacher marked them inactive or generates afterwards. The teacher adjusts it through the charge-adjustment path if they choose. A student leaving on the 1st still owes the full month unless the teacher adjusts it. | [Q3] [US-Q7.1] |
| FR5.9 | An approved payment exceeding what was charged for a cycle is accepted, and the excess is recorded as a **credit** carried to the next cycle. Outstanding never goes negative. Money received as credit counts as money received for reconciliation purposes: cash in is receipts **plus** credit grants, which is what keeps the ledger identity balanced on an overpayment [ADR-002]. | [US-Q7.2] [team: ledger invariant] [ADR-002] |
| FR5.7 | Money is fixed-point decimal in BDT throughout, crossing the API as a string. | [feasibility: Q8] [TC-7] |
| FR5.8 | Students see their own fee status and history. Guardians see the next payment date and amount, and the status of every past cycle. | [desc §7] [desc §8] |

### FR6 — Payment submission and verification

| ID | Requirement | Source |
|---|---|---|
| FR6.1 | Students and guardians submit a payment using one identical form: batch, transaction ID, amount. | [desc §9] |
| FR6.2 | The selected batch resolves to the enrollment, which resolves to the open fee cycle. | [desc §9] |
| FR6.3 | The form shows the child's name alongside the batch name, and submission shows a confirmation naming both. | [Q13] |
| FR6.4 | Partial amounts are accepted. | [desc §9] |
| FR6.5 | A teacher sees pending verifications per batch. | [desc §6] |
| FR6.6 | A teacher approves in full, approves a lesser amount than claimed, or rejects. | [desc §6] |
| FR6.7 | Every verification records who approved it and when. | [desc §6] |
| FR6.8 | On approving less than claimed, the teacher chooses to carry the remainder forward or waive it. | [desc §6] |
| FR6.9 | Students and guardians see their payment history including each submission's outcome. | [desc §8] |
| FR6.10 | No payment gateway. Money moves out of band; the system records the claim and the verification only. | [desc §9] |
| FR6.11 | A payment claim records the channel used. The channel set is **server-supplied data, not a client-side list**, so adding one is a data change rather than an app release — an installed Android app cannot be forced to update. V1 values: bKash, Nagad, Rocket, cash. | [design: S3] [desc §9] [NFR16] [mockups: Q12.3] |
| FR6.12 | A teacher records a **collection number** — the mobile-money number guardians send to — as a batch-level or teacher-level field, explicitly **separate from their login number**, since a teacher may collect on a different account from the one they sign in with. It is optional: where unset, the payment form omits step 1 and tells the student or guardian to ask the teacher how to pay. | [design: S3] [mockups: Q13.1] |
| FR6.13 | The collection number is **the one teacher-authored field deliberately exposed to students and guardians**, because the payment flow cannot work without it. Its disclosure is intentional and bounded: it is shown only to students and guardians enrolled in that teacher's batches, never in any listing or search, and the teacher is told at entry that it will be visible to them. | [FR6.12] [desc §4] [mockups: Q13.1] |

### FR7 — Cross-batch dues

| ID | Requirement | Source |
|---|---|---|
| FR7.1 | A teacher sees everyone who owes money right now, across all their batches, with amounts. | [desc §6] |
| FR7.2 | The view is driven by outstanding balance, **not** by active status. A student who left owing money still appears. | [desc §6] |
| FR7.3 | The dues view is reachable from the teacher's top-level navigation in one action, renders current data on open without a generate or run step, and shows a defined empty state when nobody owes anything. | [desc §6] [Q6-scope] |

### FR8 — Teacher analytics

| ID | Requirement | Source |
|---|---|---|
| FR8.1 | The monthly earnings total, derived from the ledger: what was actually received this month across all batches. | [Q1] |
| FR8.2 | An earnings trend across months. | [Q1] |
| FR8.3 | The collection rate for a period: total received in that period divided by total charged in that period, expressed as a percentage. Carried-forward amounts from earlier periods are excluded from both the numerator and the denominator, so the figure measures that period's collection rather than cumulative debt. Waived amounts are excluded from the denominator. Where nothing was charged, the rate is shown as not applicable rather than as zero or as a division error. | [Q1] [FR8.3-def] |
| FR8.4 | The soonest future exam across all the teacher's batches, showing its title, batch, subject, date and the whole days remaining until it. When no future exam exists, a defined empty state. | [Q1] |

### FR9 — Corrections and history

| ID | Requirement | Source |
|---|---|---|
| FR9.1 | A correction overwrites the current value rather than appending a reversing entry. | [Q4] |
| FR9.2 | The previous value and the identity of whoever changed it are retained and **visible to both the teacher and the affected student or guardian**. Correction history is never hidden from either party. | [Q4] [Q14.1] |
| FR9.3 | FR9.1 and FR9.2 apply to exactly three record types, all teacher-authored: exam marks, fee-cycle amounts, and payment verifications. | [Q4] [Q14.1] |
| FR9.4 | The correction-history mechanism applies **only** to teacher-authored records. It is never extended to student- or guardian-authored content — a submitted payment claim, a hidden-batch preference, or a private profile — because exposing a student's or guardian's edit history to a teacher would breach the privacy boundary. | [desc §4] [project: NEVER expose anything a student or guardian writes to any teacher] |

### FR10 — Notifications

| ID | Requirement | Source |
|---|---|---|
| FR10.1 | Push notifications for fee reminders and newly entered marks. | [intent: Q12] [scope: Q3] |
| FR10.2 | Notification delivery never fails the operation that triggered it. | [team: error handling] |
| FR10.3 | A reminder is recorded as an **event**, not a flag: `(enrollment, period, channel, sent_at, sent_by, outcome)`. The teacher-facing "reminded 3 days ago" / "Never reminded" state is derived as the latest event per `(enrollment, period)`. A boolean or a `last_reminded_at` column cannot express channel, a failed send, or a second reminder, so it would force a migration when a second channel arrives. | [design: T5] [mockups: Q12.1] |
| FR10.4 | The V1 fee-reminder push [FR10.1] writes a reminder event [FR10.3]. This exercises the table in V1 and makes the "Not reminded" filter implementable against real data without any SMS capability. | [mockups: Q12.1] |

### FR11 — Account deletion effects and concurrency

| ID | Requirement | Source |
|---|---|---|
| FR11.1 | A **student's or guardian's** account deletion removes their own account and private profile. It does not remove the teacher-authored enrollment, attendance, marks or fee records, which are the teacher's business record. The enrollment reverts to dormant and the display name the teacher typed is retained. | [FR1.14] [desc §4] |
| FR11.2 | A **teacher's** account deletion is governed by the disposition decided at Domain Design. It is **not specified here** because it destroys records belonging to other people: a teacher's batches carry every enrolled student's attendance, marks and fee history, and those students and guardians have no say in the teacher's deletion request. See Open questions. | [FR1.14] [TC-19] [gap: teacher deletion cascade] |
| FR11.3 | Deletion is idempotent: a second deletion request for an already-deleted account succeeds without error and without further effect. | [FR1.14] [FR1.15] |
| FR11.4 | Concurrency is split by write path. An **interactive** write (the teacher is online and the request is sent immediately) keeps last-write-wins on a per-field basis, with the correction history (FR9.2) recording each change with its actor and time; no cross-device locking or conflict prompt applies. A **queued** write (FR3.6, the mid-class offline path) carries the version it was composed against and is **refused and reported** when the underlying record changed in the interim; it is never merged and never silently applied. | [gap: concurrent edits] [ADR-006] |
| FR11.5 | A refused queued write surfaces to the teacher as a conflict (NFR5.1), showing what they recorded offline against what the record now says, and offering to re-apply or discard. Their offline entry is preserved until they choose. | [ADR-006] [NFR5.1] |

---

## Non-functional requirements

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR1 | Android target and compile SDK | API 36 (Android 16) | [TC-1] |
| NFR2 | Supported device floor | `minSdk` 24 (Android 7.0), 2 GB RAM. Release AAB download size at or below 15 MB, measured from the Play Console's reported download size for the `arm64-v8a` split and asserted at the release gate. | [desc §11] [NFR2-note] |
| NFR3 | Languages | Bangla and English from the first screen, device-locale driven falling back to English; no hardcoded user-facing strings; layouts survive longer Bangla text | [desc §11] [intent: Q13] |
| NFR4 | Offline reads | Rosters, schedules, topics, exams and fee status readable from cache without connectivity, with staleness shown | [intent: Q6] |
| NFR5 | Offline writes | **Permitted for the mid-class path only** — the topic log and attendance [FR3.2, FR3.5] queue locally and sync when connectivity returns. Every other write requires connectivity and fails with an explicit retry prompt that preserves what was typed. | [intent: Q18] [TC-8] [mockups: Q11.2] |
| NFR5.1 | Queue semantics | A queued write has **four** states, all distinct: queued (shown as queued, never rendered as saved), confirmed, failed (the send did not succeed and retry is appropriate) and **conflicted** (the send succeeded in reaching the server, which refused it because the record changed underneath — retry as-is is wrong, FR11.4). The queue survives app restart. Sync is automatic on reconnect with no user action; resolving a conflict is not, because it needs the teacher's decision. | [mockups: Q11.2] [ADR-006] |
| NFR6 | Scale ceiling | 100 teachers, a few thousand students | [feasibility: Q9] |
| NFR7 | Infrastructure cost | Under USD 50/month | [feasibility: Q3] |
| NFR8 | Data residency | None required; nearest region for latency | [feasibility: Q7] |
| NFR9 | Money representation | Fixed-point decimal, BDT only, JSON string in transit, never float | [feasibility: Q8] [TC-7] |
| NFR10 | Children's data at rest | Encrypted | [RC-8] |
| NFR11 | Device identifiers | None transmitted anywhere; no ads SDK; no `TelephonyManager` number read | [intent: Q17] [TC-3] [TC-4] |
| NFR12 | OTP abuse controls | Per-number 3/hour and 5/day; per-IP 10/hour; 5-minute single-use OTP; 5 verify attempts; hashed storage; enumeration-resistant responses; global daily SMS ceiling with per-number and per-IP sub-ceilings | [architecture §7] [team: Walking Skeleton] |
| NFR12.1 | SMS budget is **per purpose**, not global-only | The gateway adapter takes a `purpose` parameter and each purpose carries its own daily ceiling and alert. V1 has one purpose (`otp`). This exists now because a second, teacher-triggered consumer later would otherwise make one ceiling arbitrate between an abuse burst and a legitimate bulk action — and a shared ceiling either lets reminders exhaust the OTP budget and lock teachers out of login, or throttles reminders unpredictably. Retrofitting means re-reasoning about the one control protecting the project's wallet, after a second consumer is live. | [mockups: Q12.1] [R-4] [NFR12] |
| NFR13 | Token lifetimes | 15-minute access token; 30-day rotating refresh token with reuse detection and family invalidation | [architecture §7] |
| NFR14 | Privacy boundary enforcement | Structural in three layers: separate tables by writer, row-level security, teacher-facing schemas without profile fields | [desc §12f] |
| NFR15 | Accessibility and navigation | Accessibility basics and correct back-stack behaviour | [desc §11] |
| NFR16 | API versioning | `/v1/` additive; an installed client handles unknown fields rather than failing to parse | [D-26] |
| NFR17 | Backend test coverage | 80% line coverage; branch coverage on the authorization layer; 100% branch on the money module | [team: Testing Posture] |

**Deliberately absent**: there is no mid-class speed requirement. See the
Out-of-scope section.

---

## Constraints

Carried from `ideation/feasibility/constraint-register.md` — 20 technical, 7
organisational and 8 regulatory constraints, unchanged by this stage. The ones
that shaped requirements above:

- **TC-19** — two account-deletion paths, one of which needs a web surface the
  approved architecture does not yet include. [FR1.14, FR1.15]
- **TC-8 / D-9** — **superseded in part.** The constraint as recorded at
  feasibility forbade offline writes outright. The design review at Refined
  Mockups reversed that for the mid-class path only [mockups: Q11.2]: topic log
  and attendance queue locally and sync [NFR5, NFR5.1, FR3.6]. Every other write
  still requires connectivity, so TC-8 holds everywhere except those two.
- **TC-7 / D-20** — money as a type with a single arithmetic module.
- **TC-11 / D-2** — role computed per request, never stored or cached.
- **RC-1** — the mixed-audience Families declaration, which is why FR4.5
  anonymises and NFR11 exists.

---

## Assumptions

- **A1** — Teachers will accept that a mid-period departure leaves a full
  period's fee standing, adjusting it manually when they choose. [FR5.6] This
  is the likeliest source of a real fee dispute, and FR5.6 resolves it in the
  teacher's favour by default. [Q3] [assumption]
- **A2** — Anonymised marks preserve enough of the peer-comparison effect the
  brief describes to remain motivating. The brief says named marks are what make
  it motivating, so this trade is a judgment the pilot should test. [FR4.5]
  [Q14.2] [assumption]
- **A3** — Guardians will understand that a different phone number reaches a
  different teacher's batches, and will not read a missing batch as data loss.
  [FR2.7] **Partly addressed**: [FR2.16] names the recording teacher against
  each child, so a guardian can see whose records they are viewing. What remains
  assumed is that a guardian seeing only one of their child's two teachers
  infers "the other teacher recorded a different number" rather than "the app
  lost my data". No requirement states that explanation anywhere. [Q6] [Q15.2]
  [assumption]
- **A4** — Overwriting a payment verification while keeping visible history is
  sufficient for dispute resolution. An append-only trail would be stronger;
  visible history was judged sufficient. [FR9.2] [Q14.1] [assumption]
- **A5** — The analytics figures (FR8.1–FR8.3) derive entirely from the ledger
  and need no separate aggregation store at this scale. [NFR6] [assumption]
- **A6** — ~~"Collection rate" means received divided by charged...~~
  **Promoted to a requirement.** The reviewer was right that this was a product
  definition invented by this artifact rather than an assumption: the answer
  naming "collection rate" never specified the formula, and labelling an
  invented definition as an assumption hides a decision instead of recording it.
  The formula now states denominator, carried-forward and waiver handling, and
  the no-charge case explicitly at [FR8.3]. It remains open to correction, but
  as a requirement someone can disagree with rather than an assumption nobody
  reads. [FR8.3]
- **A7** — Push notification delivery is best-effort. No requirement states a
  delivery guarantee or a retry policy. [FR10.1] [assumption]
- **A8** — NFR2's numbers are the agent's choice, not the user's. `minSdk` 24
  and 2 GB RAM are the conventional low-end Android floor for a 2026 release in
  this market, and 15 MB is a figure a Compose app with no media assets can
  reasonably hold. The brief said "low-end devices" and "small APK" without
  numbers; these make the constraint verifiable, and they are the right kind of
  thing to correct at this gate if they are wrong. [NFR2] [assumption]
- **A9** — FR11.4's last-write-wins rule for *interactive* writes assumes a
  teacher editing the same batch on two devices simultaneously is rare enough
  not to warrant locking. One teacher, one class at a time makes this likely,
  but it is unverified. The assumption no longer covers the queued path, where
  the delay between composing and sending makes a conflict plausible rather
  than rare, which is why that path refuses instead. [FR11.4] [ADR-006]
  [assumption]

---

## Out of scope

Excluded by the brief, by decision, or by consequence — see
`ideation/scope-definition/scope-document.md` for the full boundary. Items this
stage removed or declined to add:

- **The mid-class speed requirement.** §11 states that a teacher needing more
  than a few seconds per class will abandon the app. That statement is
  **deliberately not a requirement** in V1: it carries no numeric target, no
  acceptance criterion and no verifier, and becomes design guidance only.
  [Q11] [Q14.3]
- **Automatic proration** on mid-period exit. [FR5.6] chose manual adjustment.
  [Q3]
- **Append-only payment verification.** [FR9.1] chose overwrite with visible
  history. [Q14.1]
- **Named marks on the shared marksheet**, which §10 specified and [FR4.5]
  overrides. [Q14.2]
- **Enrollment removal after history exists.** [FR2.12] permits it only while
  dormant. [Q5]
- **Student performance trends in the analytics dashboard.** Offered and not
  selected; guardians still see per-child progress via [FR4.7]. [Q1]
- **Numeric success-metric targets.** All three measures stay directional for
  V1. [Q2]
- Offline writes, payment gateway integration, PDF export, private messaging,
  multi-device session management, subscription state, the admin surface,
  coaching centres, the tutor marketplace, batch messaging and the PWA.

---

## Open questions

Owned by named later stages:

| Question | Owner |
|---|---|
| The teacher-vs-teacher privacy boundary. One account enrolled with several teachers could leak across that edge under read-time lens resolution. | Domain Design (2.6) |
| `FeeCycle` redesign to the anchor-plus-ledger model, superseding §10. | Domain Design (2.6) |
| Deletion disposition per table — hard delete, anonymise in place, or retain with stated basis. Blocks the privacy policy, which is generated from it. | Domain Design (2.6) |
| Retention period for child academic records. The teacher's-record versus child's-data tension is unresolved. | Domain Design (2.6) |
| A mechanism for the subscription capability to be absorbed without rework. | Domain Design (2.6) |
| **What a teacher's account deletion does to their batches, and to every enrolled student's attendance, marks and fee history.** [FR11.2] A teacher deleting their account destroys records belonging to people who were not asked. The symmetric student case is settled at [FR11.1]; this one is not, and it is the harder half because the data subject and the record owner are different people. | Domain Design (2.6) |
| How a guardian learns that another number reaches other batches (A3). | Refined Mockups (2.5) |
| The exact notification event set beyond fee reminders and new marks. | Functional Design (3.1) |

Unowned, external to the workflow:

| Question | Blocks |
|---|---|
| SMS gateway vendor, with delivery reliability and sandbox credentials verified. | FR1.2 implementation |
| Play Console account type — personal accounts created after 13 Nov 2023 need 12 testers for 14 continuous days. | The release plan |
| Teacher onboarding mechanism during closed testing; no admin surface exists. | Closed testing |
| The web surface TC-19's external deletion route requires, which is uncosted. | FR1.15 |

---

## Assumptions & Open Questions

Both sections above are substantive. In summary: 7 assumptions (A1–A7), 7
workflow-owned open questions and 4 external ones.

Two accepted risks worth restating, because neither is resolved and both were
deliberate:

- **§11's abandonment risk has no detection mechanism.** Dropping the speed
  requirement means nothing in V1 will reveal a too-slow attendance path before
  a pilot teacher abandons the app and says so. [Q14.3] [assumption]
- **Wrong-child payment is visible, not prevented.** [FR6.3] shows the child's
  name and confirms it, but a guardian moving quickly can still submit against
  the wrong child; the teacher catches it at verification. The stronger option —
  select the child first, making a wrong-child payment unreachable — was offered
  and not taken. [Q13] [assumption]

---

## Sources

- [desc] Initial description, §1–§13.
- [Q1]–[Q14] Confirmed answers in `requirements-analysis-questions.md`.
- [intent: Q*] `ideation/intent-capture/intent-capture-questions.md`.
- [feasibility: Q*], [architecture §*], [TC-*], [OC-*], [RC-*], [D-*]
  `ideation/feasibility/`.
- [scope: Q*] `ideation/scope-definition/scope-definition-questions.md`.
- [team: *] `aidlc/spaces/default/memory/team.md`, affirmed practices.
