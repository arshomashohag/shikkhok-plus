# Design parity checklist — Android vs the approved design canvas

The approved design is the **ShikkhokPlus Design System** canvas
(claude.ai artifact `14c6b628-4a29-4601-adaa-64711995bf29`), mobile pages
*Sign up & log in*, *Teacher*, *Student* and *Guardian*. This file lists,
per artboard, where the Compose app differs from it, so each gap can be
closed or consciously kept.

Audited 2026-11-04 against `main` at `601c39f`. File references are
relative to `android/src/main/kotlin/com/shikkhokplus/app/`.

**How to read the boxes**

- `[ ]` — a gap to close.
- `[x]` — closed (the commit that closed it is noted).
- `[~]` — **keep the code, change the design**: the artboard conflicts
  with a project rule, or the code deviates on purpose with a recorded
  reason. These need an artboard edit, not a code change.
- `[?]` — needs a server/API addition or a product decision before the
  client can match it. Not started on the client side on purpose: a row
  that opens nothing is worse than no row.

**Out of scope:** the *Class* tab inside batch detail for every role
(`feature/classcalendar`) was changed deliberately after the design was
approved and is not audited here.

---

## Cross-cutting

- [x] **Offline with a saved copy, within the session.** Today, Dues, My
  batches, Inside a batch, the guardian home and all three More screens
  keep what this session last read when a reload cannot reach the
  server, under an "Offline · showing data from 10:42 am" banner
  (`OfflineBanner`), with what needs the server held back: Remind,
  Pay, Edit, Invitations, and every fee status, which could have been
  approved since.
- [?] **A copy that survives a restart.** The artboards' "saved copy"
  after the app is closed means children's names, fees and marks
  written to the phone's disk. That is a privacy decision (children's
  data at rest on a shared family phone [RC-1, RC-8]), not a layout
  one, so no disk cache was added; T6, T7 and G2/G3 still show an
  error card when the first read of a session fails.
- [x] **Skeleton loading.** T1, T3, S1 and S2 draw skeleton cards, as
  the artboards do, and so do the list screens with no artboard of their
  own (fee history, exams, classes, invitations, payments, My
  children). Forms, sign-in and one-off waits keep `LogoLoader`.
- [x] **Student and guardian navigation.** Students and guardians have no
  bottom bar: More opens from a profile button beside the inbox bell on
  their home (`navigation/StudentRoutes.kt` `FamilyBarActions`), pushed
  with Back. Invitations is a row inside More. Teachers keep their four
  tabs, and the lens-free person keeps Invitations · More.
- [x] **Guardian type scale.** With the guardian lens, every screen takes
  `GuardianTypography` (row titles 18/30, grey lines 14/22, title 21/34
  Bold) and `GuardianTouch` (60dp main buttons, 56dp others, 64dp rows,
  30dp chips), applied once around the navigation graph
  (`core/designsystem/Theme.kt` `GuardianScale`). Chip text is 14sp, the
  nearest design step to the board's 15sp.
- [?] **Settings that do not exist yet:** Notifications preferences, Dark
  theme, Text size, Save data, Reminder SMS language, How-to videos,
  Call/message support, Tell another teacher. No screens, storage or
  strings exist for any of them.

---

## Sign up & log in

### O1 · Create account — `feature/auth/ui/SignupScreen.kt`
- [?] Address required at sign-up: the app asks for it but does not
  require it. Requiring a child's or guardian's home address before they
  can use the app is a data-minimisation decision for the owner, not a
  layout fix.
- [?] Already-added banner should name the teacher, role and batch
  ("মাহফুজুর রহমান added this number as a student in …"); the code uses
  generic copy. Needs the server to say who added the number.
- [~] Loading uses a full-window `LogoLoader` ("Creating your account…")
  instead of "Sending code…" in the button — deliberate per the code's
  own comment.
- [~] The "We sent a code to your number" banner stays: it is the
  confirmation that the step worked. **Add it to the artboard.**

### O2 · Log in — `feature/auth/ui/AuthScreen.kt`
- [~] "Error · no account for this number" is not built, on purpose: the
  code answers every number the same way (BR2.7) and the project forbids
  revealing whether a number exists. **The artboard should drop this state.**
- [x] Malformed-number copy: "Bangladeshi mobile numbers have 11 digits,
  starting 01." (every phone field shares it).
- [~] Loading is the app-wide overlay loader, not a spinner in the
  button, by the owner's own rule for loaders (see `AuthScreen.kt`).
  **Update the artboard.**

### O3 · Enter the code — `feature/auth/ui/AuthScreen.kt`
- [~] The sent line never shows the number ("If this number has an
  account, we sent it…") — same non-disclosure rule as O2. The design's
  "…to **01712-345678**" is fine only because the person just typed it;
  decide and align.
- [~] "Change" stays on its own line: inline in the sentence it would be
  a tap target under the design system's 44px minimum. **Update the
  artboard.**
- [~] Checking uses the app-wide overlay loader ("Checking the code…"),
  by the same rule. **Update the artboard.**
- [?] Lockout note ("paused for 15 minutes"): the server reports a
  lockout as "temporarily unavailable" without its length, so the client
  cannot say 15 minutes truthfully.
- [~] "No code? … create your account first" and Retry stay: they were
  added after a teacher-added student waited on this screen with no way
  on. **Add them to the artboard.**

---

## Teacher

### T1 · Home (Today) — `feature/today/ui/TodayScreen.kt`
- [?] Schedule-change card ("Batch C moved to 7:30 pm today… notified")
  and the struck-through old time. `ClassRow` has no original-time field.
- [x] Empty/first run: "Outstanding" section with the server's total
  (৳0); step bubbles 28dp, step 1 filled primary, the rest grey
  (`feature/today/ui/TodayScreen.kt`).
- [x] Loading: skeleton for the Outstanding card.
- [x] Offline with this session's copy (see cross-cutting)
  (`feature/today/ui/TodayScreen.kt` `TAG_TODAY_OFFLINE`).
- [?] Rows marked "Recorded · not sent yet" and "can't approve while
  offline": the day's read does not say which of its classes the
  phone's queue still holds.
- [x] Recorded topic shows without a "✓ " prefix.

### T2 · Record a class — `feature/record/ui/RecordClassSheet.kt`
- [?] "Change" action in the sheet header: the board does not say what it
  changes (the class, the time, the batch), so it waits on that answer.
- [?] Two labelled suggestions ("Continue", "Next"); `RecordSheet` holds one.
- [x] Subjects as a segmented control (`RecordClassSheet.kt`).
- [~] "Take attendance" stays: it is the sheet's way to the attendance
  screen mid-class. **Add it to the artboard.**
- [~] Save stays enabled on an empty topic — blank topics are allowed
  (BR2.2). **The artboard should not grey it out.**
- [?] Loading suggestions state: the suggestion arrives with the sheet's
  own read, so there is no separate wait to draw.
- [~] "Couldn't send. Will retry on its own." with Retry now: the app's
  banner says "Saved on the phone. It sends when the connection returns."
  -- the same fact, and the queue already retries on reconnect, so a
  Retry now would only repeat what it does. **Update the artboard.**
- [x] Continuous entry: "6/20" counter and progress bar, roll numbers,
  compact "/25" rows, the "now entering" dock, the app's own keypad with
  Absent, backspace and "Next ↓" (`feature/marks/ui/MarkEntryScreen.kt`).
  Entry opens on the first seat with no mark; Next saves and moves down.
- [?] The keypad's decimal key: not drawn, because the API's mark is a
  whole number (see half marks below).
- [x] Exam in the title, "out of 25" as the subtitle
  (`feature/marks/ui/MarkEntryScreen.kt`).
- [?] "subject · batch · date" in the subtitle: the entry read carries the
  exam's date only, not its subject or batch name.
- [?] Half marks ("19.5"): the client takes `Int`. Needs the API's mark
  type confirmed before the client changes.
- [x] Empty: "No students in this batch yet".
- [?] Empty: an Add students button on it -- the entry read carries no
  batch id to open the batch's add-student form with.
- [x] Loading: skeleton rows.
- [?] Draft → review → "Publish to students & guardians", "3 to fix",
  "Max 25" row errors. There is no draft/publish model; marks save per
  field. Needs a server model.

### T4 · Payment verification — `feature/verify/ui/*`
- [x] Queue cards show TrxID and the paying account
  (`feature/verify/ui/VerifyScreen.kt`).
- [x] Inline Reject / Partial / Approve on the queue card
  (`feature/verify/ui/VerifyScreen.kt` `QueueActions`). Approve decides
  from the queue only for a payment the server says matches, with an
  unused transaction ID; Partial, Reject and anything over or reused
  open the review, where carry-forward, waive, the duplicate warning and
  the reject confirmation live.
- [?] Subtitle "· oldest 2 days": the queue read has no oldest-first
  guarantee the client may rely on, and picking the oldest would be the
  client ordering a domain list.
- [x] Partial sheet title "Approve ৳800 of ৳1,200", and "Add ৳400 to the
  next fee." on carry forward when the server's shortfall figure applies
  (`feature/verify/ui/ApprovalSheetView.kt`).
- [?] Target month and "November fee becomes ৳1,600": the review read
  carries neither the next period nor its resulting amount, and the
  client never adds money.
- [x] The approved chip says "Paid", not "Payment done".
- [~] The heading stays "Decided today": the list holds rejections too,
  so "Approved today" would mislabel them. **Rename it in the artboard.**
- [?] Empty: "Partial · ৳600 fwd" chip and times on decided rows: the
  recent-decisions read carries no carried amount.
- [x] Loading: skeleton rows (the board's button blocks are not drawn;
  the card height is what keeps the list from jumping).
- [x] Duplicate: red outline and "This ID was already used." on the
  queue card.
- [x] Duplicate: "Reject as duplicate" is the filled choice and "Approve
  anyway" the outlined one (`feature/verify/ui/PaymentReviewScreen.kt`).
- [x] Duplicate: the date it was decided, in the warning.

### T5 · Cross-batch dues — `feature/dues/ui/DuesScreen.kt`
- [x] Subtitle "৳48,600 owed · updated 2 min ago", from the phone's last
  read (`DuesScreen.kt`).
- [?] "All 7 batches": the dues read lists batches with dues only, so the
  count of all batches is not known here.
- [x] Chip colour: every late row is the red overdue chip, at any age, as
  the board draws 7, 37 and 68 days (`feature/dues/ui/DuesScreen.kt`).
- [?] Amber for a partly-paid row (the board's Nusrat): the dues read has
  no partly-paid flag, so no row is amber yet.
- [?] "Remind N late **guardians**" by SMS ("SMS in Bangla and English ·
  you approve the text first"); the app reminds students in-app. Product
  decision.
- [x] Collapsed header: the total owed stays in the bar's subtitle when
  the summary card scrolls away, which is what the collapsed board shows.
- [x] Empty keeps the "Owed to you ৳0" card, with the server's total
  (`feature/dues/ui/DuesScreen.kt`).
- [?] "paid up for October" and "November fees fall due on 10 Nov": the
  dues read carries neither the month nor the next due date.
- [x] Offline with this session's figures, Remind disabled
  (`feature/dues/ui/DuesScreen.kt` `TAG_DUES_OFFLINE`).

### T6 · Batch list — `feature/batches/ui/BatchesScreen.kt`
- [?] Fee-status chip per card ("৳7,200 late" / "৳4,800 due" / "All paid").
- [x] Schedule line ("Sat · Mon · Wed · 4:00 pm"), falling back to the
  subjects for a batch with no class days yet.
- [?] The level ("HSC 2027") and "Today moved to 7:30 pm": no level field
  and no schedule-change read exist.
- [x] "18 students · ৳1,200/mo".
- [~] "X of Y accepted" is kept under it while anyone has not accepted: a
  pending seat grants no lens, and the teacher needs to see that from the
  list. **Add it to the artboard.**
- [~] Error body "This phone has no saved copy yet…": the app keeps no
  saved copy (see offline, cross-cutting), so the sentence would be
  untrue until it does.

### T7 · Single batch — `feature/batchdetail/ui/*`
- [x] One icon in the bar: the Schedule text action is gone, and the
  schedule chip under the title opens the schedule (it reads "Schedule"
  before any class day is set, so the way in never disappears).
- [?] Header subtitle with the level ("HSC 2027"): the batch has no
  level field.
- [x] Add button hidden on Notices and on an empty roster, where "Add
  first student" is the action (`BatchDetailRoute.kt` `showsAdd`).
- [~] Declined chip: the board draws a grey fill with a **dashed**
  border, but the design system reserves the dashed outline for
  "not yet confirmed" (Verifying), and `PaymentStateTest` holds every
  other state to a non-dashed outline so the cue keeps its meaning.
  **Redraw the declined chip in the artboard** (for example grey fill,
  solid outline, a cross icon) and it can then be built.
- [~] Exams: the section stays "Marked". There is no publish step, so
  "Published" would claim one (see T3).
- [?] Exams rows: "36.7 avg of 50" needs an average from the server.
- [?] Notices: auto-sent schedule-change card, "seen by N of M families".
- [x] Notices: an inline composer (field and Send) instead of a button and
  a dialog; the draft clears once the server has the notice. It sits at
  the top of the tab rather than the bottom, so it stays in reach above
  a long list.
- [~] Edit and Remove on a notice stay: a teacher must be able to correct
  or take down what a family reads. **Add them to the artboard.**
- [x] "Save & add next" beside Add student, and "2 added so far" in the bar
  once one lands (`navigation/AddStudentRoute.kt`); the form clears only
  after the server confirms.
- [x] Batch name as the bar subtitle, with "2 added so far" after it.
- [x] "+88" prefix on both phone fields, through the shared
  `PhoneNumberField`; a malformed number is still caught while typing.
- [x] Fee as a "Batch fee · ৳1,200" toggle (`CreateForms.kt`
  `BatchFeeToggle`), read from the batch screen it was opened on; off,
  the field asks for this student's own fee. On, nothing is sent, which
  the server reads as inherit, never as zero [AC2.2.5]. A batch with no
  fee keeps the plain field.
- [~] Help lines: "New number. They'll get an SMS invite." is not added:
  nothing sends an SMS invite (invitations are accepted in the app), so
  the line would promise a message that never arrives. **Update the
  artboard.**
- [?] Number lookup: "Checking…", "Found on ShikkhokPlus", auto-fill.
  Needs a lookup endpoint (and a privacy review: it reveals that a number
  has an account, to a teacher).
- [x] Phone error "Mobile numbers have 11 digits. This one has 10." when
  a local number has the wrong count (`CreateForms.kt` `phoneError`).
- [x] Same-name hint: "Rahim is already in this batch", shown, never
  blocking, since two students can share a name.
- [~] "Open her profile" link on that hint: a teacher has no student
  profile to open (teacher-facing reads carry no profile fields,
  [TC-13, D-5]), and "her" would be the app guessing a child's gender.
  **The artboard should drop the link.**
- [x] `feature/roster/ui/AddStudentScreen.kt` was never called — removed,
  with its test.

### T9 · More — `feature/profile/ui/ProfileScreen.kt`
- [x] Title "More", not "Your profile". *(More screen redesign,
  `feature/profile/ui/ProfileScreen.kt`, `core/designsystem/MenuList.kt`)*
- [x] Profile card: avatar initial, name, "Teacher · number", tonal Edit.
- [x] Menu rows with icon, title, sub-label and chevron, grouped by
  section headers instead of a stack of fields and full-width buttons.
- [x] GETTING PAID → "Where students pay" (opens payment methods).
- [x] YOUR RECORDS → reports (opens Collections).
- [x] ACCOUNT → "Log out", "Delete account" as plain rows; version footer.
- [x] Log out is a bottom sheet: "Log out of ShikkhokPlus?", amber
  callout when work is unsent, "Stay and send them first" / "Log out
  anyway" (`feature/profile/ui/LogOutSheet.kt`). With nothing unsent it
  is a plain Log out / Cancel confirmation; the artboard draws no such
  state — add one.
- [?] "Free trial · 9 days left" card with Plans (no plan model; the app
  charges nobody — see `team.md` Way of Working).
- [?] "Fee due date and reminders" row.
- [?] "Everything is saved · Last synced" row.
- [?] APP and HELP sections (see cross-cutting settings).
- [x] "Where students pay" sub-screen title.
- [~] Its add actions stay "+ Mobile banking" and "+ Bank account": bank
  accounts are part of the 2026-11-02 payment-methods spec, which the
  board predates. **Update the artboard.**
- [x] Error · offline: banner, "Needs a connection" sub-labels, "2
  records not sent yet" row (`ProfileScreen.kt` `TAG_PROFILE_OFFLINE`,
  `TAG_PROFILE_UNSENT`).
- [~] "Switch role" is code-only but needed by people who hold more than
  one lens; kept as a row in ACCOUNT. **Add it to the artboard.**

---

## Student

### S1 · My batches — `feature/studentbatches` (`MyBatchesScreen.kt`)
- [~] Pay button stays "Send money": the later payment-methods spec
  (`docs/superpowers/specs/2026-11-02-payment-methods-and-progress-design.md`,
  F1) fixes that label for every family screen. **Update the artboard.**
- [~] Hero caption keeps the teacher's full name: a short form with
  "স্যার" would be the app guessing a teacher's gender and nickname.
  **Update the artboard, or have the server send the form to show.**
- [x] Empty: "This screen updates by itself once you're added." after the
  number.
- [x] Empty: the number on its own highlighted line.
- [x] Loading skeleton (`MyBatchesScreen.kt`).
- [?] The student's name in the bar while loading: nothing on the phone
  holds the name before the first read answers. After it, the name stays
  through a reload and offline.
- [x] Offline with this session's copy, offline banner, Send money
  disabled with "needs a connection" (`MyBatchesScreen.kt`).

### S2 · Inside a batch — `StudentBatchScreen.kt`, `FamilyTabs.kt`
- [~] One scrolling page instead of tabs: **decided 2026-11-04 to keep
  the tabs**, because flattening them removes the Classes tab and its
  calendar, which was changed on purpose. The artboard should be redrawn
  with the tabs.
- [x] Exams tab lists Results first, then Coming up, as the page does. The old strings
  (`student_result_rank`, `student_latest_notice`, `student_all_notices`,
  `student_results`) are still in `strings.xml`, unused.
- [x] Bar subtitle names the teacher.
- [?] The level ("HSC 2027") after it: the batch has no level field.
- [x] Next class as a white card (`NextClassHero` `asCard`); S1 keeps
  the blue hero.
- [?] "First class" label when none has happened: the read does not say
  whether a class has been held, and an empty topic list only says none
  was recorded.
- [x] Fee line: "November · ৳1,200", then "Due by 10 Nov".
- [~] "Pay this" and "Progress" stay under the fee card: the
  payment-methods spec puts Send money on every family fee (F1) and
  Progress on every lens (D1). **Update the artboard.**
- [?] Results with rank ("rank 5 of 19") and chevron.
- [x] Loading: skeleton cards (`StudentBatchScreen.kt`).
- [x] Offline: this session's results stay, and the fee is replaced by
  "Fee status unavailable / We don't show a payment status we can't
  confirm" (`TAG_STUDENT_FEE_UNAVAILABLE`).
- [?] The "Text only…" note: the board does not say what it refers to.

### S3 · Submit payment — `feature/pay/ui/PayScreen.kt`
- [~] One form, fee-first: **superseded by the 2026-11-02 payment-methods
  spec** (F1–F5). That spec, approved after this artboard, makes paying
  method-first from the teacher's own list (mobile banking, bank, or the
  built-in cash in hand), lets one payment cover several children in a
  batch, and accepts a payment when nothing is owed. The app follows the
  spec. **Redraw S3 from F1–F5.**
- [~] Title and close X: superseded with the rest of S3 by the payment-
  methods spec (titles follow F2–F4).
- [~] Empty: "Which fee are you paying?" list, "রসায়ন isn't listed: your
  payment is being checked": superseded with the rest of S3. The spec
  pays by method and accepts a payment when nothing is owed, so there is
  no fee list to choose from (F1–F5).
- [~] "Safe to wait… we'll keep it and resend" — payment submission is not
  an offline-queued write (only attendance and topic are, NFR5/BR3.1).
  **The artboard should drop this copy.**
- [x] Sent: title "Payment sent", chip "Verifying".
- [x] Sent: the transaction ID row, and "Until your teacher checks it, the
  fee shows as Verifying, not Paid."
- [?] Sent: "Sent 17 Oct, 3:22 pm" -- the submission's reply carries the
  date paid, not when it was sent.

### S4 · More — `feature/profile/ui/ProfileScreen.kt`
- [x] Title "More", profile card with avatar, "Student · number", Edit.
- [x] Menu rows and section headers; APP / Help absent until they exist.
- [x] Invitations as a row inside More (no longer a tab).
- [?] The row's highlight and badge count: drawn plain until the client
  knows how many invitations are pending, because a permanent highlight
  would say something is waiting when nothing is.
- [x] "Log out" as a row; delete as a plain row.
- [x] Reached from a profile button with Back, no bottom bar.
- [?] Invitation badge count, Guardian row (name · number), Payment
  history row — need a lightweight "me" summary from the server.
- [?] Invitation card: "Added 14 Oct", "<teacher> added you to <batch>",
  Classes / Fee-with-due-day / Teacher-phone grid, explanation text,
  EARLIER section; "This isn't me · Decline"; title "Invitations".
  `InvitationRow` lacks teacher, schedule, date and due day: needs them
  in the invitations read first.
- [x] Edit profile as its own screen with close X, titled "Edit profile",
  "Full name".
- [?] Mobile number "Change" with OTP to the new number — the app says the
  number cannot be changed. Needs a number-change endpoint.
- [~] "Account type" explanation ("To use ShikkhokPlus as a teacher or
  guardian, create a separate account with another number") contradicts
  the lens model: one account holds every lens its seats grant, and
  Switch role exists for exactly that [TC-11, D-2]. Not built. **The
  artboard should drop or rewrite this copy.**
- [x] Error · offline: the same More screen as T9.

---

## Guardian

### G1 · Child home & switcher — `feature/guardian/ui/GuardianHomeScreen.kt`
- [?] Combined total ("৳2,000 · September and October", "Pay ৳2,000")
  instead of one month's amount plus "N later months".
- [x] Switcher and child header pinned in a white header under the bar,
  no title (`ScreenScaffold` `pinned`); the page scrolls beneath it.
- [?] Child sub-line with class level ("HSC 2027"): no level field.
- [x] Pay goes to G3 (payments) first, where what was already paid sits
  above Send money.
- [x] Empty: "Your children appear here as soon as they're linked." after
  the number to give the teacher.
- [~] Empty bar title stays "Your students", the guardian home's title in
  every state.
- [x] Offline with this session's results, "Payments can't be shown
  right now…" in place of the payment card
  (`TAG_GUARDIAN_PAYMENTS_UNAVAILABLE`).
- [x] 30dp chips, 14sp text (the nearest design step).

### G2 · Progress — implemented as `DashboardScreen`
- [x] Title "তাসনিম's progress" for a guardian; the subtitle keeps only
  the batch (`feature/dashboard/ui/DashboardScreen.kt`).
- [?] Narrative sentence ("Marks went up in each of the last 4 tests…"),
  "Tap a point" hint, Test / Marks / Rank table: the sentence is a
  judgement about the marks the server should make and send, and rank
  is not in the dashboard read.
- [?] One-test empty state ("21/25 · Rank 3 of 20 · avg 16.4 · A progress
  line appears after the second test"): needs rank and the batch average
  for a single exam from the server.
- [x] Error copy "Couldn't load the results", with the server's reason
  under it.
- [~] Dashboard-only extras (child chips, range chips, tiles, attendance
  chart, fee strip) stay: they are the progress dashboard the
  payment-methods spec approved for all three lenses (D1, D2), which
  this artboard predates. **Redraw G2 from D1–D2.**

### G3 · Payment history & pay — `PaymentsScreen.kt`, `PayScreen.kt`
- [x] "Paid in 2026 · ৳X" is the bar subtitle (`PaymentsScreen.kt`).
- [~] The extra "Owed now ৳X" headline stays: it is the one place this
  screen says what is owed before the guardian pays, and the server
  sends it. **Add it to the artboard.**
- [~] CTA stays "Send money" (spec F1).
- [~] Pay form: superseded by the 2026-11-02 payment-methods spec, as for
  S3 (method-first, several children per payment, any amount). **Redraw
  from F1–F5.**
- [x] Guardian scale on the pay form (it follows the lens).
- [x] Loading keeps a disabled Send money in place.

### G4 · More — `feature/profile/ui/ProfileScreen.kt`
- [x] Title "More", profile card (avatar, name, "Guardian · number").
- [~] The artboard draws no Edit pill for a guardian. Kept, so a guardian
  can still correct their own name and address. **Add it to the artboard,
  or decide guardians cannot edit.**
- [x] Invitations row; "My children" row and sub-screen
  (`feature/guardian/ui/MyChildrenScreen.kt`). Tapping a child selects it
  on the home switcher. The class level ("HSC 2027") is not shown: the
  guardian read has no level field.
- [x] "Log out" as a row.
- [x] Reached from a profile button, no bottom bar.
- [?] "Is আয়ান your child?" invitation with child chip, "Yes, this is my
  child" / "No, not my child". The invitation read carries no child
  name, and sending one is a privacy decision: it would show a child's
  name to whoever holds the number a teacher typed, before they have
  confirmed they are the guardian [RC-1, D-5].
- [?] Notifications, Text size, "Call for help · Talk to a person, in Bangla".
- [x] Guardian type scale (64dp rows, 18sp titles, 21sp/700 title).
- [x] Error · offline: the same More screen as T9.

---

## Web (PWA)

The web artboards (pages *Web · …* on the same canvas, added 2026-11-04)
have no implementation yet; they are the target for the PWA, not part of
this audit. The *Delete an account* link on Web O2 points to a web
deletion screen that has no artboard yet.
