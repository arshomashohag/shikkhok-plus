# Intent Capture & Framing — Clarifying Questions

**Stage**: intent-capture
**Phase**: Ideation
**Depth**: Comprehensive

## Sources

- [desc] Initial description: "Build ShikhokPlus: a native Android app plus backend for private tuition management in Bangladesh. Teachers manage batches, students, schedules, topic logs, exams/marksheets, and month-end fee collection; students and guardians get read-only visibility plus payment submission. Phone number is the account; role (teacher/student/guardian) is a lens resolved at read time, not a field. Strict privacy boundary: nothing a student or guardian writes is ever visible to a teacher. V1 excludes coaching centres, tutor marketplace, batch messaging, and PWA, but the architecture must absorb them without rework. Includes cross-batch dues screen, fee cycles with carry-forward/waiver, teacher payment verification, Bangla+English localization, and Google Play readiness (Data Safety, children's data policy, account deletion)."
- [scope] Workflow-selected scope: `classic`.

---

## Q1. Who pays for ShikhokPlus, and what happens when they stop?

The description says serving the guardian well is what makes the teacher's
subscription renew, which implies teachers pay a recurring fee. That single
fact drives the whole commercial model: whether we need subscription state in
V1, what a lapsed teacher's students can still see, and whether billing is in
scope at all.

- A. Teacher pays a recurring subscription; billing is OUT of V1 scope (manual/offline collection, no in-app purchase, no subscription state in the data model)
- B. Teacher pays a recurring subscription; subscription STATE is in V1 (we track active/lapsed and gate features) but payment collection is manual
- C. Teacher pays via Google Play Billing in-app subscription in V1
- D. Free for V1 — no monetisation at all; we are proving the product first
- E. Guardians or students pay, not teachers
- X. Other (please specify)

[Answer]: A - we need to build the admin dashboard for the platform owner so that we can manage users and payment. Right now we will have the necessary APIs to onboard the teachers for the platform admin.

---

## Q2. What is the Google Play "target audience" declaration for this app?

This is the most expensive question in this batch to get wrong, and it is a
declaration we must make in Play Console before release. I verified Google's
current policy: for any app whose declared target audience includes children,
"device phone number must not be requested from TelephonyManager" — absolute,
no exceptions — and child-or-unknown-age users must not have advertising or
device identifiers transmitted at all. Your students are typically minors and
the phone number IS the account. Note the distinction that matters: asking a
user to TYPE their number is always fine; READING it off the SIM is what the
policy forbids. Play may independently verify the declaration, so an
optimistic answer here is the kind of wrong that gets a release pulled.

- A. Adults only (18+) — app is marketed to and used by teachers; students/guardians are the teacher's contacts. Declare adult audience, enforce an 18+ gate on who can log in
- B. Mixed audience including children — students are minors and log in themselves. Accept Families policy obligations: no AAID/device identifiers, certified ads SDKs only, COPPA/GDPR-K compliance
- C. Teens 13+ and adults, excluding under-13 — students are secondary-school age
- D. Not yet decided — treat as an open risk, design to the strictest reading (no device identifiers anywhere, no ads SDK) and settle before release
- X. Other (please specify)

[Answer]: C. For secondary school students, the guardian will use the APP as guardian. But there shouldn't be any restriction on APP to install it in any devices

---

## Q3. What is the authoritative spelling, and therefore the permanent package name?

Your brief says use "ShikhokPlus" consistently and never invent variant
spellings — but §11 suggests `com.shikhokplus.app` while this repository is
already named `shikkhok-plus` (double-k). Those are two different spellings
already in play. The package name is permanent once published and cannot be
changed, so this needs settling before the first commit of the Android module,
not after.

- A. `com.shikhokplus.app` — matches §11; rename the repo to `shikhokplus` for consistency
- B. `com.shikkhokplus.app` — matches the existing repo spelling `shikkhok-plus`
- C. A domain-backed namespace you own (specify the reversed domain, e.g. `com.yourdomain.shikhokplus`) — safest if you own or will own a domain
- D. Something else entirely — the Latin romanisation is unsettled, pick a neutral namespace
- X. Other (please specify)

[Answer]:B

---

## Q4. What does success look like in numbers, within what timeframe?

Ideation artifacts require measurable success metrics — "improved performance"
or "teachers like it" cannot be verified. I need the actual target so later
stages can trace requirements to it.

- A. Teacher retention: N teachers still active after 3 months (specify N)
- B. Guardian engagement: % of guardians who open the app at least monthly (specify %)
- C. Fee collection improvement: reduction in overdue balances vs. paper baseline (specify %)
- D. Adoption volume: N teachers onboarded in the first 6 months (specify N)
- E. Multiple of the above — specify which and the numbers
- X. Other (please specify)

[Answer]: E - A, B, C

---

## Q5. Is attendance in or out of V1?

Your §1 says guardians currently see "no attendance" and §11 warns that "a
teacher who needs more than a few seconds per class to mark attendance will
abandon the app" — both imply attendance exists. But §2's IN list and the §10
data model have no attendance entity at all: `Session` records subject and
topic, not who showed up. This is a real gap, not a wording slip, and it
changes the schema and the mid-class UX.

- A. Attendance IS in V1 — add a per-session, per-enrollment attendance record; mid-class marking is a primary UX path
- B. Attendance is OUT of V1 — §1 and §11 were loose wording; `Session` topic logging is all V1 does. Guardians see topics, not presence
- C. Attendance is out of V1 but the schema must absorb it later without migration pain
- D. Not yet decided — flag as an open question and settle at requirements
- X. Other (please specify)

[Answer]: A

---

## Q6. What exactly is the teacher's offline guarantee mid-class?

§11 asks for "graceful offline for everything a teacher does mid-class". Full
offline write with sync and conflict resolution is a large engineering
commitment that affects the data model, the API and the Android architecture;
cached-reads-only is far cheaper. I need the real boundary, because retrofitting
offline writes later is a rewrite rather than an addition.

- A. Cached reads only — rosters and schedules readable offline; all writes require connectivity and fail with a clear retry prompt
- B. Offline writes for the mid-class path only (topic log, and attendance if in scope), queued and synced on reconnect; everything else online
- C. Full offline-first — every teacher write queues locally and syncs, with conflict resolution
- D. Online-only with aggressive caching and good error states; offline is a V2 concern
- X. Other (please specify)

[Answer]: A

---

## Q7. How are the fee-cycle money rules settled where the spec is silent?

Your §10 gives `balance = amount_due + carry_in − adjustment − amount_paid` and
monthly generation, but money bugs live in the corners the formula does not
cover. These are the ones I would otherwise have to assume, and each has real
dispute potential. (Select all that apply, or pick X and tell me your rules.)

- A. Mid-month joiners are prorated by day; mid-month leavers likewise
- B. No proration — a student enrolled any time in a period owes the full period fee
- C. Overpayment creates a negative balance that carries forward as credit
- D. Overpayment is refused at submission (claimed amount cannot exceed balance)
- E. A fee override (`Enrollment.fee_amount`) applies only to future cycles, never retroactively to generated ones
- X. Other (please specify)

[Answer]: A - a fee amount is just a anchor. Teacher decides what he actually gets and allowed. It may vary by students as well. Teacher may receive full fee, partial or over (as a tip). He will decide whether he owes something in next month as well as carry over from current month or he can mark is as paid though it's partial. Just add the amount in ledger for final reporting of earnings.

---

## Q8. What is the authoritative timezone and period boundary for fee cycles?

A "month" and a "due day" are ambiguous without a timezone, and fee disputes
are exactly where that ambiguity bites. Bangladesh is UTC+6 with no daylight
saving, which simplifies this — but the rule still has to be written down.

- A. Asia/Dhaka (UTC+6) for all period and due-date arithmetic; store instants in UTC, compute day boundaries in Asia/Dhaka
- B. Server UTC throughout; display converted to local
- C. Per-teacher configurable timezone (needed only if teachers abroad are expected)
- D. Not yet decided
- X. Other (please specify)

[Answer]: It is also flexible. Let teacher set the start of the batch and set the pay cycle. It's default to 30 days. So, due date will be at the 30th day after batch start. And next due date is at 60th and so on. It's just to notify students/guardian about the dates. 

---

## Q9. What happens to a fee due day that does not exist in a given month?

`Batch.fee_due_day` is a day-of-month. A teacher who sets 31 has no 31st in
February. This is a classic corner that produces wrong due dates silently.

- A. Clamp to the last day of the month (31 → 28/29 Feb)
- B. Restrict the input to 1–28 at entry time so the case cannot arise
- C. Roll forward into the next month (31 Jan → 3 Mar in a non-leap year)
- D. Not yet decided
- X. Other (please specify)

[Answer]: Normally batches starts at the start of the month and due dates are last of the month. Count the days, not my month day. Rule is, 30 days counts a month. Whenever the batch starts.

---

## Q10. Who are the stakeholders beyond the three app personas, and who decides scope?

Ideation requires a stakeholder map with decision-makers distinguished from
influencers. I know about teachers, students and guardians from the
description. I do not know whether anyone else has a say.

- A. You alone decide scope and priority; teachers/students/guardians are users, not deciders
- B. You decide, with a small group of pilot teachers whose feedback influences priority (specify roughly how many)
- C. There is a co-founder or business partner who shares scope authority
- D. There is an investor or external stakeholder with reporting expectations
- E. Multiple of the above — specify
- X. Other (please specify)

[Answer]: B

---

## Q11. Is there a reporting cadence or communication requirement I should produce artifacts for?

This determines whether later stages generate stakeholder-facing summaries or
only technical artifacts.

- A. None — this is solo work, no external reporting
- B. Informal updates to pilot teachers; no formal artifacts needed
- C. Periodic written progress summaries for an investor or partner (specify cadence)
- D. Not yet defined
- X. Other (please specify)

[Answer]: B

---

## Q12. What should this first version deliberately NOT do, beyond the four exclusions already named?

Your §2 already excludes coaching centres, the tutor marketplace, batch
messaging and the PWA. Scope creep in a V1 like this usually arrives through
features that feel small individually. Naming them as out-of-scope now is
cheaper than arguing about them later. (Select all that apply.)

- A. No push notifications (fee reminders, class reminders, new-marks alerts)
- B. No report-card or marksheet PDF export or sharing
- C. No teacher-to-single-student private messaging or one-way announcements beyond the batch `Announcement` entity already in the model
- D. No analytics dashboard for teachers (trends, income over time, student performance charts)
- E. No multi-device session management or session revocation for a logged-in account
- X. Other (please specify — or "none of these, they are all in")

[Answer]: B, C, E

---

## Q13. What is the launch geography and language default?

§11 requires Bangla and English from the start. What I do not know is which is
the default on first launch, and whether anything outside Bangladesh is a
consideration — it affects phone-number handling (country code assumptions) and
the Play listing.

- A. Bangladesh only; Bangla is the default language, English available in settings
- B. Bangladesh only; follow the device locale, falling back to Bangla
- C. Bangladesh only; follow the device locale, falling back to English
- D. Bangladesh primary but expect Bangladeshi diaspora users abroad — do not hardcode the +880 country code
- X. Other (please specify)

[Answer]: C

---

## Q14. Where should DECISIONS.md and DEFERRED.md live, and who writes them?

Your §13.5 asks for these two running files. No workflow stage produces them,
so without an explicit decision they would quietly not happen. I want them
recorded as a standing deliverable with an owner and a location.

- A. Repository root (`DECISIONS.md`, `DEFERRED.md`); I maintain them, appending at every approval gate
- B. Inside the workflow record directory alongside the stage artifacts; I maintain them
- C. Repository root, but as a lightweight index that links to the per-stage artifacts rather than duplicating their content
- D. Repository root; I append to them only when you explicitly ask
- X. Other (please specify)

[Answer]: X- Ignore these

---

## Q15. Is there an existing document, prototype, or prior attempt I should read?

The brief is unusually detailed, which sometimes means it was distilled from
something longer, or that a previous build exists.

- A. No — the brief is everything; nothing else exists
- B. Yes, a document exists (specify the path or filename and I will read it)
- C. A previous prototype or partial build exists elsewhere (specify where)
- D. Competitor or reference apps worth examining (name them)
- X. Other (please specify)

[Answer]: A

---

## Q16. Admin surface scope in V1 (follow-up to Q1)

Q1's answer added an admin dashboard for the platform owner (manage users and
payments, onboard teachers). That is a fourth persona with write access and a
web surface; neither was in the V1 scope, and §4's privacy boundary does not
describe what a platform admin may see. Asked to establish what V1 ships.

- A. APIs only in V1 — admin-capable endpoints and the authorization model allowing a platform-owner role, but no web UI in V1
- B. APIs plus a minimal server-rendered admin web page in V1
- C. Full admin dashboard in V1
- D. Defer entirely to V2 — no admin surface and no admin APIs
- X. Other (please specify)

[Answer]: A. APIs only in V1 — SUPERSEDED by Q20. The user subsequently removed the
platform admin APIs from V1 as well, reasoning that with subscription deferred
there is nothing for them to activate programmatically during closed testing.
See Q20 for the operative answer.

---

## Q17. Play target-audience declaration, resolved (follow-up to Q2)

Q2 selected "Teens 13+ and adults, excluding under-13" while also stating that
guardians act for secondary-school students and the app should install on any
device. Those conflict: if under-13 students log in, a 13+ declaration is a
misdeclaration, and Play may verify independently. The user then specified the
mechanism: if the teacher enters both the student's and the guardian's phone
number, both can log in, irrespective of the student being under 13. That
mechanism decides the declaration.

- A. Students never log in; guardians only — declare adults-only (18+)
- B. Declare mixed audience including children — accept Families obligations
- C. Keep 13+ and enforce it with an age gate at login
- D. Design to the strictest reading, settle the declaration before release
- X. Other (please specify)

[Answer]: B. Declare mixed audience including children. Login behaviour is as the
user specified: teacher enters student phone and optional guardian phone, and
both can log in regardless of the student's age. Accepted consequences: no
advertising or device identifiers (AAID, SIM serial, build serial, BSSID, MAC,
SSID, IMEI, IMSI) transmitted anywhere; no ads SDK; no device phone-number read
via TelephonyManager (numbers are always typed, never auto-filled from the SIM);
COPPA and GDPR-K compliance; Families data-practices declarations in Play
Console.

---

## Q18. Resolving the attendance/offline conflict (follow-up to Q5 and Q6)

Q5 put attendance in V1 as a primary mid-class path; Q6 chose cached-reads-only
with no offline writes. Marking attendance is a write, so on patchy classroom
data it would fail exactly when it is being used — the abandonment scenario §11
warns about. Asked which constraint gives way.

- A. Offline writes for the mid-class path only (attendance, topic log), queued and synced
- B. Keep cached-reads-only; attendance stays in V1 but requires connectivity
- C. Keep cached-reads-only; drop attendance to V2
- D. Full offline-first for all teacher writes
- X. Other (please specify)

[Answer]: B. Keep cached-reads-only; attendance needs connectivity. Attendance
remains in V1 as a primary mid-class path, but marking it requires a live
connection and fails with a clear retry prompt. The §11 abandonment risk is
accepted and recorded as a known risk rather than designed away in V1.

---

## Q19. Fee model: elapsed-day cycles vs the agreed §10 schema (follow-up to Q7, Q8, Q9)

Q7–Q9 described a fee model that departs from §10: fee as a teacher-adjustable
anchor rather than a fixed amount due, with the teacher deciding what is
actually charged, received, carried forward or forgiven; and cycles counted in
elapsed days from batch start (30 days treated as a month) rather than calendar
months with a `fee_due_day`. §10 said "implement this, flag anything you'd
change", so this was put back to the user rather than assumed.

- A. Yes — redesign fully to the elapsed-day ledger model
- B. Yes to the anchor-and-ledger model, but keep calendar months as the period
- C. No — keep §10 exactly as written
- D. Model both and choose at domain design
- X. Other (please specify)

[Answer]: B. Adopt the teacher-adjustable fee anchor and the ledger of what was
actually charged, received, carried forward or forgiven, but keep calendar-month
periods with a due day (clamped for short months). Month-end collection stays
aligned with how guardians think about "this month's fee". The elapsed-day
cycle from Q8/Q9 is not adopted for V1.

---

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

- Commercial model: teacher pays a recurring subscription, collected manually;
  no billing or subscription state in the V1 data model. Platform-owner admin
  capability ships as APIs only in V1 (teacher onboarding, user and payment
  management), no web UI.
- Play target audience: mixed audience including children. Teacher enters the
  student's phone and optionally the guardian's; both can log in regardless of
  the student's age. Accepted constraints: no advertising or device identifiers
  transmitted anywhere, no ads SDK, no TelephonyManager phone-number read
  (numbers always typed), COPPA and GDPR-K compliance, Families declarations in
  Play Console.
- Package name: `com.shikkhokplus.app`, matching the existing repo spelling.
  User-facing strings remain "ShikhokPlus", so product name and namespace differ
  by one k — deliberate.
- Success metrics: teacher retention after 3 months, guardian monthly-open rate,
  and reduction in overdue balances versus the paper baseline. Numeric targets
  not yet supplied.
- Attendance: in V1 as a primary mid-class path, per-session and per-enrollment.
- Offline: cached reads only. Rosters and schedules readable offline; all writes
  including attendance require a live connection and fail with a clear retry
  prompt. The §11 abandonment risk is accepted.
- Fee model: fee is a teacher-adjustable anchor, not a fixed amount due. The
  teacher decides what is actually charged, received, carried forward or
  forgiven, recorded in a ledger for earnings reporting. Calendar-month periods
  with a due day (clamped for short months) retained; elapsed-day cycle not
  adopted for V1. This revises §10's FeeCycle.
- Stakeholders: the user decides scope and priority; a small group of pilot
  teachers influences it. Informal updates to them, no formal reporting
  artifacts.
- Out of V1, beyond the four already excluded: marksheet PDF export or sharing,
  teacher-to-student private messaging beyond batch announcements, and
  multi-device session management or revocation. Push notifications and a
  teacher analytics dashboard remain in scope.
- Localization: Bangladesh only; follow the device locale, falling back to
  English.
- DECISIONS.md and DEFERRED.md: withdrawn at the user's instruction; not
  deliverables.
- Prior material: none; the brief is everything.

[Answer]: Looks correct

---

## Assumption Confirmation

Both artifacts carry `## Assumptions & Open Questions` entries. These are
recorded as assumptions, not facts; accepting them does not make them true.

From `intent-statement.md`:

1. Numeric targets for all three success metrics are unset; the measures are
   confirmed but the thresholds are not.
2. The §11 abandonment risk from connectivity-required attendance marking is
   accepted rather than mitigated in V1.
3. What a platform administrator may see is unspecified; the admin APIs add a
   fourth principal with write access, so the privacy boundary needs an explicit
   admin clause at Domain Design.
4. The confirmed fee model supersedes the agreed `FeeCycle` shape in the initial
   description; that entity will be revised at Domain Design.
5. Push notifications remain in V1 while messaging and PDF export are excluded;
   notifications carry server-side delivery infrastructure the excluded features
   do not.
6. Pilot teacher group size is not quantified.
7. Subscription state is absent from the V1 data model, so the application
   cannot distinguish an active teacher from a lapsed one and cannot gate
   features on subscription status.
8. Whether a guardian may have children under more than one teacher
   simultaneously is implied by per-enrollment guardian capture but not
   explicitly confirmed.

From `stakeholder-map.md`:

9. Pilot teacher group size is not quantified, so the feedback loop's weight on
   priority cannot be sized.
10. What an administrator may see of any party's private data is unspecified.
11. Guardian influence is inferred to be strong from the renewal link, but V1
    gives guardians no in-product mechanism to report dissatisfaction, so that
    influence reaches the project only indirectly.
12. Whether pilot teachers are a defined cohort with an onboarding or feedback
    process, or simply the first organic users, was not established.

Options:

- A. Accept assumptions
- B. Convert to follow-up questions

[Answer]: A. Accept assumptions — accepted for the remaining assumptions, after
assumptions 3, 7, 10 and the admin-scope part of 5 were resolved directly by the
user's reply rather than accepted. Those resolutions are recorded as Q20 below,
and the artifacts were revised accordingly before acceptance.

---

## Q20. Admin visibility, subscription timing, and admin API scope (follow-up to Q16 and assumptions 3, 7, 10)

At the assumption confirmation gate the user resolved three open assumptions
directly instead of selecting accept or convert. Recorded here as the operative
answers.

**Q20.1 — What may a platform administrator see?**

- A. Subscriber (teacher) information only: name, subscription plan, payment status. Never any student or guardian data.
- B. All data, as the platform operator
- C. Teacher data plus aggregate, non-identifying student counts
- X. Other (please specify)

[Answer]: A. Subscriber information only — name, subscription plan, payment
status and similar. Explicitly not any student's or guardian's data. This
completes the privacy boundary: the initial description bars teachers from
seeing student and guardian writes, and this bars the administrator from seeing
student and guardian data at all.

**Q20.2 — Is subscription state in V1?**

- A. Deferred — out of V1, but the data model and app design must absorb it later without rework
- B. In V1 as state only, no billing
- C. In V1 with Google Play Billing
- X. Other (please specify)

[Answer]: A. Deferred. Skipped for the closed testing period, but needed later,
so it must be kept in mind when designing the application and the data models.
It joins coaching centres, the marketplace, batch messaging and the PWA as a
named future capability the architecture must absorb without rework.

**Q20.3 — Do the platform admin APIs ship in V1?**

- A. No — removed from V1 entirely
- B. Yes, APIs only (the earlier Q16 answer)
- C. Yes, APIs plus a minimal web UI
- X. Other (please specify)

[Answer]: A. No. With subscription deferred there is no need to activate a
teacher's subscription programmatically, so the admin APIs have nothing to do
during closed testing. This supersedes Q16. Teachers are onboarded manually for
V1, and the platform-owner persona has no V1 surface at all.

---
