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

- [ ] **Offline with a saved copy.** No screen has the "Offline · showing
  data from 10:42 am" state; a failed load always replaces the content
  with an error card (T1, T5, T6, T7 fees, S1, S2, G1, G2, G3, and all
  three More screens).
- [ ] **Skeleton loading.** Most screens show `LogoLoader`; the
  artboards draw skeleton cards (T1, T3, S1, S2).
- [ ] **Student and guardian navigation.** The artboards draw no bottom
  bar for student and guardian: More opens from a profile button with
  Back. *Partly closed:* Invitations is now a row inside More and no
  longer a tab, so the bars are My batches · More and Children · More
  (`navigation/ShikkhokNavHost.kt` `routesFor` / `tabsFor`). Still open:
  replacing the bar with a profile button. The lens-free person keeps
  Invitations as their home tab (`homeFor(null)`), since it is the only
  place they can act.
- [ ] **Guardian type scale.** Guardian artboards use larger type and
  targets (64dp rows, 18sp row titles, 60/56dp buttons, 30dp chips with
  15sp text). The app uses the same scale for every lens.
- [?] **Settings that do not exist yet:** Notifications preferences, Dark
  theme, Text size, Save data, Reminder SMS language, How-to videos,
  Call/message support, Tell another teacher. No screens, storage or
  strings exist for any of them.

---

## Sign up & log in

### O1 · Create account — `feature/auth/ui/SignupScreen.kt`
- [ ] Address is "Address (optional)" and not required; the design labels
  it "Address" and has an "Add your address" error state.
- [?] Already-added banner should name the teacher, role and batch
  ("মাহফুজুর রহমান added this number as a student in …"); the code uses
  generic copy. Needs the server to say who added the number.
- [~] Loading uses a full-window `LogoLoader` ("Creating your account…")
  instead of "Sending code…" in the button — deliberate per the code's
  own comment.
- [ ] Code-only "We sent a code to your number" banner is not in the design.

### O2 · Log in — `feature/auth/ui/AuthScreen.kt`
- [~] "Error · no account for this number" is not built, on purpose: the
  code answers every number the same way (BR2.7) and the project forbids
  revealing whether a number exists. **The artboard should drop this state.**
- [ ] Malformed-number copy: design says "Bangladeshi mobile numbers have
  11 digits, starting 01."
- [ ] Loading is the overlay loader, not a spinner in the button.

### O3 · Enter the code — `feature/auth/ui/AuthScreen.kt`
- [~] The sent line never shows the number ("If this number has an
  account, we sent it…") — same non-disclosure rule as O2. The design's
  "…to **01712-345678**" is fine only because the person just typed it;
  decide and align.
- [~] "Change" stays on its own line: inline in the sentence it would be
  a tap target under the design system's 44px minimum. **Update the
  artboard.**
- [ ] Checking should be an in-place "Checking the code…" label, not the
  overlay loader.
- [ ] Lockout note ("paused for 15 minutes") has no specific copy.
- [ ] Code-only extras not in the design: "No code? … create your account
  first" hint, Retry button.

---

## Teacher

### T1 · Home (Today) — `feature/today/ui/TodayScreen.kt`
- [?] Schedule-change card ("Batch C moved to 7:30 pm today… notified")
  and the struck-through old time. `ClassRow` has no original-time field.
- [x] Empty/first run: "Outstanding" section with the server's total
  (৳0); step bubbles 28dp, step 1 filled primary, the rest grey
  (`feature/today/ui/TodayScreen.kt`).
- [ ] Loading: skeleton for the Outstanding card.
- [ ] Offline with cache (see cross-cutting), including rows marked
  "Recorded · not sent yet" and "can't approve while offline".
- [x] Recorded topic shows without a "✓ " prefix.

### T2 · Record a class — `feature/record/ui/RecordClassSheet.kt`
- [ ] "Change" action in the sheet header.
- [?] Two labelled suggestions ("Continue", "Next"); `RecordSheet` holds one.
- [ ] Subjects as a segmented control, not FilterChips.
- [ ] "Take attendance" link is code-only.
- [~] Save stays enabled on an empty topic — blank topics are allowed
  (BR2.2). **The artboard should not grey it out.**
- [ ] Loading suggestions state.
- [ ] "Couldn't send. Will retry on its own." snackbar with **Retry now**
  (the app shows a banner with OK).

### T3 · Marks entry — `feature/marks/ui/MarkEntryScreen.kt`
- [ ] Continuous entry: "6/20" counter and progress bar, roll numbers,
  compact "/25" rows, the "now entering" dock, keypad with Absent and
  "Next ↓".
- [x] Exam in the title, "out of 25" as the subtitle
  (`feature/marks/ui/MarkEntryScreen.kt`).
- [?] "subject · batch · date" in the subtitle: the entry read carries the
  exam's date only, not its subject or batch name.
- [?] Half marks ("19.5"): the client takes `Int`. Needs the API's mark
  type confirmed before the client changes.
- [x] Empty: "No students in this batch yet".
- [ ] Empty: an Add students button on it.
- [ ] Loading: skeleton rows.
- [?] Draft → review → "Publish to students & guardians", "3 to fix",
  "Max 25" row errors. There is no draft/publish model; marks save per
  field. Needs a server model.

### T4 · Payment verification — `feature/verify/ui/*`
- [x] Queue cards show TrxID and the paying account
  (`feature/verify/ui/VerifyScreen.kt`).
- [ ] Inline Reject / Partial / Approve on the queue card. Partial needs
  the approval sheet, so this is a layout change to the decision flow,
  not a button row.
- [ ] Subtitle "· oldest 2 days".
- [x] Partial sheet title "Approve ৳800 of ৳1,200", and "Add ৳400 to the
  next fee." on carry forward when the server's shortfall figure applies
  (`feature/verify/ui/ApprovalSheetView.kt`).
- [?] Target month and "November fee becomes ৳1,600": the review read
  carries neither the next period nor its resulting amount, and the
  client never adds money.
- [x] The approved chip says "Paid", not "Payment done".
- [~] The heading stays "Decided today": the list holds rejections too,
  so "Approved today" would mislabel them. **Rename it in the artboard.**
- [ ] Empty: "Partial · ৳600 fwd"
  chip, time on rows, "can be undone for 24 hours", "…and on Today".
- [ ] Loading: card skeletons with button blocks.
- [x] Duplicate: red outline and "This ID was already used." on the
  queue card.
- [x] Duplicate: "Reject as duplicate" is the filled choice and "Approve
  anyway" the outlined one (`feature/verify/ui/PaymentReviewScreen.kt`).
- [ ] Duplicate: the date in the warning.

### T5 · Cross-batch dues — `feature/dues/ui/DuesScreen.kt`
- [ ] Subtitle "All 7 batches · updated 2 min ago".
- [x] Chip colour: every late row is the red overdue chip, at any age, as
  the board draws 7, 37 and 68 days (`feature/dues/ui/DuesScreen.kt`).
- [?] Amber for a partly-paid row (the board's Nusrat): the dues read has
  no partly-paid flag, so no row is amber yet.
- [?] "Remind N late **guardians**" by SMS ("SMS in Bangla and English ·
  you approve the text first"); the app reminds students in-app. Product
  decision.
- [ ] Collapsing header when scrolled.
- [x] Empty keeps the "Owed to you ৳0" card, with the server's total
  (`feature/dues/ui/DuesScreen.kt`).
- [?] "paid up for October" and "November fees fall due on 10 Nov": the
  dues read carries neither the month nor the next due date.
- [ ] Offline with cache, disabled Remind.

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
- [ ] Error body "This phone has no saved copy yet…".

### T7 · Single batch — `feature/batchdetail/ui/*`
- [ ] Header subtitle has the level ("HSC 2027"); one icon, no extra
  "Schedule" text action.
- [ ] FAB hidden on empty Students (only "Add first student") and on Notices.
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
- [ ] Notices: inline bottom composer instead of FAB + dialog; no
  Edit/Remove in the design.

### T8 · Add student — `core/ui/CreateForms.kt` `StudentAddForm`
- [x] "Save & add next" beside Add student, and "2 added so far" in the bar
  once one lands (`navigation/AddStudentRoute.kt`); the form clears only
  after the server confirms.
- [ ] Batch name as the bar subtitle.
- [x] "+88" prefix on both phone fields, through the shared
  `PhoneNumberField`; a malformed number is still caught while typing.
- [ ] Fee as a "Batch fee · ৳1,200" toggle, not a free-text field.
- [ ] Help lines: "New number. They'll get an SMS invite.", name auto-fill
  sentence, guardian "Lets a parent see marks…".
- [?] Number lookup: "Checking…", "Found on ShikkhokPlus", auto-fill.
  Needs a lookup endpoint (and a privacy review: it reveals that a number
  has an account, to a teacher).
- [ ] Phone error "This one has 10" (digit count).
- [ ] Inline duplicate-name card with "Open her profile".
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
- [ ] "Where students pay" sub-screen: title, single "Add a number ·
  bKash, Nagad or Rocket" row, "Shown first" marker, FEES section.
- [ ] Error · offline: banner, "Needs a connection" sub-labels, "2
  records not sent yet" row.
- [~] "Switch role" is code-only but needed by people who hold more than
  one lens; kept as a row in ACCOUNT. **Add it to the artboard.**

---

## Student

### S1 · My batches — `feature/studentbatches` (`MyBatchesScreen.kt`)
- [~] Pay button stays "Send money": the later payment-methods spec
  (`docs/superpowers/specs/2026-11-02-payment-methods-and-progress-design.md`,
  F1) fixes that label for every family screen. **Update the artboard.**
- [ ] Hero caption uses the short teacher name ("মাহফুজ স্যার").
- [ ] Empty: number on its own highlighted line; "This screen updates by
  itself once you're added."
- [ ] Loading skeleton with the name in the bar.
- [ ] Error with saved copy, offline banner, disabled "Pay a fee · needs
  connection".

### S2 · Inside a batch — `StudentBatchScreen.kt`, `FamilyTabs.kt`
- [~] One scrolling page instead of tabs: **decided 2026-11-04 to keep
  the tabs**, because flattening them removes the Classes tab and its
  calendar, which was changed on purpose. The artboard should be redrawn
  with the tabs.
- [x] Exams tab lists Results first, then Coming up, as the page does. The old strings
  (`student_result_rank`, `student_latest_notice`, `student_all_notices`,
  `student_results`) are still in `strings.xml`, unused.
- [ ] Bar subtitle "teacher · HSC 2027".
- [ ] Next class as a white card; "First class" label when none has happened.
- [ ] Fee sub-line "November due 10 Nov"; no extra "Send money"/"Progress"
  on the card.
- [?] Results with rank ("rank 5 of 19") and chevron.
- [ ] Loading/Error: saved results, "Fee status unavailable / We don't
  show a payment status we can't confirm", "Text only…" note.

### S3 · Submit payment — `feature/pay/ui/PayScreen.kt`
- [~] One form, fee-first: **superseded by the 2026-11-02 payment-methods
  spec** (F1–F5). That spec, approved after this artboard, makes paying
  method-first from the teacher's own list (mobile banking, bank, or the
  built-in cash in hand), lets one payment cover several children in a
  batch, and accepts a payment when nothing is owed. The app follows the
  spec. **Redraw S3 from F1–F5.**
- [~] Title and close X: superseded with the rest of S3 by the payment-
  methods spec (titles follow F2–F4).
- [ ] Empty: "Which fee are you paying?" list, "রসায়ন isn't listed: your
  payment is being checked".
- [~] "Safe to wait… we'll keep it and resend" — payment submission is not
  an offline-queued write (only attendance and topic are, NFR5/BR3.1).
  **The artboard should drop this copy.**
- [x] Sent: title "Payment sent", chip "Verifying".
- [ ] Sent: bKash ID row, "Sent 17 Oct, 3:22 pm", "Until then the fee
  shows as Verifying, not Paid".

### S4 · More — `feature/profile/ui/ProfileScreen.kt`
- [x] Title "More", profile card with avatar, "Student · number", Edit.
- [x] Menu rows and section headers; APP / Help absent until they exist.
- [x] Invitations as a row inside More (no longer a tab).
- [?] The row's highlight and badge count: drawn plain until the client
  knows how many invitations are pending, because a permanent highlight
  would say something is waiting when nothing is.
- [x] "Log out" as a row; delete as a plain row.
- [ ] Reached from a profile button with Back, no bottom bar (see
  cross-cutting navigation).
- [?] Invitation badge count, Guardian row (name · number), Payment
  history row — need a lightweight "me" summary from the server.
- [ ] Invitation card: "Added 14 Oct", "<teacher> added you to <batch>",
  Classes / Fee-with-due-day / Teacher-phone grid, explanation text,
  EARLIER section; "This isn't me · Decline"; title "Invitations".
  `InvitationRow` lacks teacher, schedule, date and due day.
- [x] Edit profile as its own screen with close X, titled "Edit profile",
  "Full name".
- [?] Mobile number "Change" with OTP to the new number — the app says the
  number cannot be changed. Needs a number-change endpoint.
- [~] "Account type" explanation ("To use ShikkhokPlus as a teacher or
  guardian, create a separate account with another number") contradicts
  the lens model: one account holds every lens its seats grant, and
  Switch role exists for exactly that [TC-11, D-2]. Not built. **The
  artboard should drop or rewrite this copy.**
- [ ] Error · offline.

---

## Guardian

### G1 · Child home & switcher — `feature/guardian/ui/GuardianHomeScreen.kt`
- [?] Combined total ("৳2,000 · September and October", "Pay ৳2,000")
  instead of one month's amount plus "N later months".
- [ ] Switcher and child header pinned in a white header, no title.
- [ ] Child sub-line with class level ("HSC 2027").
- [ ] Pay goes to G3 (payments), not straight to the pay form.
- [ ] Empty: bar "ShikkhokPlus", "Your children appear here as soon as
  they're linked."
- [ ] Error with saved results, "Payments can't be shown right now…".
- [ ] 30dp / 15sp chips.

### G2 · Progress — implemented as `DashboardScreen`
- [x] Title "তাসনিম's progress" for a guardian; the subtitle keeps only
  the batch (`feature/dashboard/ui/DashboardScreen.kt`).
- [ ] Narrative sentence ("Marks went up in each of the last 4 tests…"),
  "Tap a point" hint, Test / Marks / Rank table.
- [ ] One-test empty state ("21/25 · Rank 3 of 20 · avg 16.4 · A progress
  line appears after the second test").
- [ ] Error copy "Couldn't load the results…".
- [ ] Dashboard-only extras (child chips, range chips, tiles, attendance
  chart, fee strip) are not in the design — decide which stay.

### G3 · Payment history & pay — `PaymentsScreen.kt`, `PayScreen.kt`
- [x] "Paid in 2026 · ৳X" is the bar subtitle (`PaymentsScreen.kt`).
- [ ] No extra "Owed now ৳X" headline: kept for now, since it is the one
  place this screen says what is owed before the guardian pays.
- [~] CTA stays "Send money" (spec F1).
- [~] Pay form: superseded by the 2026-11-02 payment-methods spec, as for
  S3 (method-first, several children per payment, any amount). **Redraw
  from F1–F5.**
- [ ] Guardian scale on the pay form.
- [ ] Loading keeps a disabled "Pay · waiting for connection".

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
- [ ] Reached from a profile button (see cross-cutting navigation).
- [ ] "Is আয়ান your child?" invitation with child chip, "Yes, this is my
  child" / "No, not my child".
- [?] Notifications, Text size, "Call for help · Talk to a person, in Bangla".
- [ ] Guardian type scale (64dp rows, 18sp titles, 21sp/700 title).
- [ ] Error · offline.

---

## Web (PWA)

The web artboards (pages *Web · …* on the same canvas, added 2026-11-04)
have no implementation yet; they are the target for the PWA, not part of
this audit. The *Delete an account* link on Web O2 points to a web
deletion screen that has no artboard yet.
