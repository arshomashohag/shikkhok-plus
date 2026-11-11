# UX / UI review — 2026-11-11

**Reviewer**: design agent (UI/UX). **Scope**: web PWA (`web/src`), Android Compose
(`android/src/main`), with a brief look at the admin console and public site.
**Commit**: `7547918`. **Method**: code reading plus two Playwright runs against the
Vite dev server with the API stubbed (sign-in at 320 px in `bn` and `en`), and a
static render of the attendance row using the real `tokens.css`, `app.css` and
`classes.css` at 320 px and 360 px. No backend was running. Android was read but
not built. Nothing here proposes moving a decision to the client [TC-9].

## Summary

The web client is in good shape on fundamentals. The `Sheet` is truly modal: it
makes the background inert, keeps Tab inside, closes on Escape and gives focus
back (`web/src/ui/components.tsx:303-413`). The `TopBar` moves focus to the new
screen's heading on navigation (`components.tsx:48-56`). All six icon buttons
have `aria-label`s. Reduced motion is honoured (`styles/app.css:1268`). Every text
token passes AA, and the ones I checked reach about 7:1 (recomputed below rather
than taken from the comment). Bangla digits are accepted in money and phone input
(`core/money.ts:72`, `core/format.ts:28`). I found no hard-coded user-facing
strings in web screens.

Most of what remains sits where this product's users are under the most strain:

1. **The mid-class attendance row breaks in Bangla on a small phone.** At 320 px
   the name column is 38 px wide, and a three-word Bangla name wraps to five
   lines, making the row 112 px tall. At 360 px the column is 78 px. The two
   84 px toggle buttons take the space.
2. **The Android attendance switch has no accessible name, and leaving the
   Record sheet for attendance throws away the typed topic.**
3. **Form errors fire on the first keystroke and are often not linked to their
   field**, on the money and phone forms teachers use most.
4. **Destructive actions are confirmed in one place and not in another.**
   Removing a seat is a single tap with no undo on Student detail, but needs a
   confirmation on the Students tab.
5. **The Bangla layout check has never been run.** All 51 rows read
   `not yet checked`, none read PASS, and the web PWA is not in the table. The
   project rule against an obligation with no executed verifier applies here
   (`project.md`, Forbidden).

## Findings

Severity: **High** = blocks or misleads a core task, or an accessibility failure
on a core path. **Med** = friction or partial failure on a common path. **Low** =
polish.

| ID | Sev | Surface | Title | Evidence | Recommendation | Effort |
|---|---|---|---|---|---|---|
| UX-1 | High | Web | Attendance row breaks Bangla names on small phones | `features/teacher/classes/classes.css:153-156` (2×`min-width:84px` buttons); `SessionScreen.tsx:478-511`. Measured: at 320 px the name column is **38 px**, 'মোহাম্মদ আব্দুল্লাহ আল মামুন' wraps to 5 lines and the row is 112 px tall. At 360 px the column is 78 px | Below 400 px, make the whole row the control. Tap the row to toggle, and show one 48 px status pill (icon + word) at the end, instead of two side-by-side 84 px buttons. Or put the toggle under the name. Keep `aria-pressed` semantics | M |
| UX-2 | High | Android | Attendance `Switch` has no accessible name | `feature/attendance/ui/AttendanceScreen.kt:198-210` and `feature/classcalendar/ui/ClassDayScreen.kt:196-214`: `Switch(onCheckedChange=…)` sits beside a separate `Text`, and the row is not merged. TalkBack reads "On, switch" with no student's name | `Row(Modifier.toggleable(value, role = Role.Switch, onValueChange=…))` and `Switch(onCheckedChange = null)`, the pattern already used in `core/ui/CreateForms.kt:394` and `SettingsScreen.kt:117`. This also makes the whole row the tap target | S |
| UX-3 | Med | Android | Going from Record to attendance throws away the typed topic | `feature/record/ui/RecordClassSheet.kt:134-138` "Take attendance" → `navigation/TodayRoute.kt:120-123` and `TeachingRoutes.kt:171-174` call `recorder.close()`, which sets `_sheet = null` (`RecordClassViewModel.kt:65-67`) | Keep the sheet state across the navigation, or ask first ("Save topic first?") when `typed` is not blank. The web avoids this by recording both on one form | S |
| UX-4 | Med | Android | Attendance screen gives no clear next step after saving or failing | `AttendanceScreen.kt:129-160`: `Confirmed` and non-retryable `Failed` are bare `Text`. There is no "Done" or "Back to today", and the screen has no state styling (no `Banner`), unlike `ClassDayScreen.kt:217+` | Use `Banner` with tone, and add a primary "Done" that returns to the screen the teacher came from | S |
| UX-5 | Med | Android | Two different attendance UIs for the same task | `AttendanceScreen.kt:205` (switch only, no Present/Absent word) vs `ClassDayScreen.kt:201-213` (word + switch, 48 dp row). The web uses Present/Absent segmented buttons (`SessionScreen.tsx:487-509`) | Pick one row component in `core/ui` and use it on both Android screens. Show the state as a word, not only switch position | M |
| UX-6 | Med | Web | Errors show on the first keystroke | `people/NewStudent.tsx:158-161` (`phone_invalid` once one digit is typed), `students/mappers.ts:161-168` (`phone_digit_count 1`), `money/RecordPaymentSheet.tsx:112-113`, `family/pay/PayScreen.tsx:600-601` | Validate on blur or submit, and clear the error as soon as the input becomes valid while typing ("reward early, punish late") | S |
| UX-7 | Med | Web | Field errors not linked to their inputs | `RecordPaymentSheet.tsx:103-114`, `ApprovalSheet.tsx:107-117`, `NewStudent.tsx:151-179`, `PayScreen.tsx:592-601`, `ExamForm.tsx:142,169`: `aria-invalid` is set but there is no `aria-describedby`. 28 uses of `aria-describedby` exist elsewhere, e.g. `AddStudent.tsx:107` | Move every input onto a shared `Field` (the one in `AddStudent.tsx:95-125`) so the error and help ids are wired the same way everywhere | M |
| UX-8 | Med | Web | Remove seat is one tap on Student detail but confirmed on the Students tab | `people/StudentDetail.tsx:146-152` calls `removeEnrollment` directly. `students/StudentsTab.tsx:229,301,334` open a confirm dialog for the same action | Use the same confirm sheet on Student detail, or give both an Undo snackbar | S |
| UX-9 | Med | Web | Other one-tap destructive actions | `centre/Payroll.tsx:245-252` "Remove" adjustment, no confirm or undo, and the same "Remove" label on every row; `centre/Timetable.tsx:224` archives a room in one tap | Add Undo or a confirm. Give each button a contextual name (`aria-label="Remove {label}"`) | S |
| UX-10 | Med | Web | Clicking the backdrop throws away a filled sheet | `ui/components.tsx:391-393` closes on backdrop `mousedown` whatever the sheet contains, for example a typed amount in `RecordPaymentSheet` | Add an `isDirty` prop. When the sheet is dirty, the backdrop and Escape ask "Discard?" or do nothing | S |
| UX-11 | Med | Web | Two "add student" forms that behave differently | `people/NewStudent.tsx` (route `/students/new`, `people/index.tsx:32`) has optional phone, no +880 prefix and unlinked errors. `students/AddStudent.tsx` (route `/batches/:id/students/new`, `students/index.tsx:17`) has required phone, a prefix and a linked `Field` | Merge into one form, with the batch pre-selected when opened from a batch | M |
| UX-12 | Med | Web | Back from a class goes to the batch, not where the teacher came from | `SessionScreen.tsx:132` `back = paths.batch(batchId,'classes')`, opened from Today at `Today.tsx:274,285`. `TopBar` follows a fixed path (`components.tsx:64`) | When there is in-app history, use `back={true}` (history −1), falling back to the batch path on a deep link. Mid-class, the teacher goes back to Today | S |
| UX-13 | Med | Web | Focus is lost after saving a class | `SessionScreen.tsx:134-139` bumps `generation`, and `key` (`:179`) remounts `RecordForm`, so the focused Save button is destroyed and focus falls to `<body>` | After saving, move focus to the snackbar text or the `h1`. Or do not remount the form, only reset its versions | S |
| UX-14 | Med | Web | Snackbar disappears after 6 s even when it has an action | `components.tsx:277-280` uses a fixed 6000 ms. The PWA "Update ready — Reload" uses it (`shell/AppShell.tsx:248-254`). WCAG 2.2.1 | Don't time out a snackbar that has an action (or a minimum of 10 s, paused on hover or focus). Give the update prompt a persistent banner | S |
| UX-15 | Low | Web | Snackbar covers the sticky Save button | `app.css:979-983` (fixed, `bottom: 96px`) overlaps `.action-bar` (`app.css:794-797`, `bottom: 80px` + a 56 px button) for 6 s after Save | Raise the snackbar above `.action-bar` when one is present, or put it at the top | S |
| UX-16 | Med | Web | First-run guide disappears after the first batch | `Today.tsx:65` shows the steps only while `!model.hasBatches`. Step 2 (add students) and step 3 (bKash/Nagad confirmation, which needs payment methods) are then never prompted | Give the server a `setup_steps` list (done or pending, decided on the server [TC-9]) and show the checklist until every step is done, linking to `paths.studentNew()` and Payment methods | M |
| UX-17 | Med | Both | Bangla layout check never run, and web not in the table | `docs/delivery/bangla-layout-check.md:79-139`: 51 × `not yet checked`, 0 PASS/FAIL/FIXED. No web rows. UX-1 is a concrete FAIL it would have caught | Run it for D4 attendance first. Add web rows. For web, add a Playwright check at 320 px in `bn` that flags any `.title` narrower than 96 px and any horizontal overflow | M |
| UX-18 | Low | Web | Mixed Bangla terms for "sign in" | Sign-in heading `auth_signin_headline` = "লগ ইন", button `auth_verify` = "সাইন ইন করুন" (`i18n/generated/strings.bn.json:96,102`). The bundles use "লগ ইন" 46× and "সাইন ইন" 11× | Use "লগ ইন" everywhere. Add a glossary entry | S |
| UX-19 | Low | Web | Below-target touch sizes | `.seat-toggle button` 40 px (`classes.css:154`); `.btn-small` 40 px (`app.css:757-758`, used for Today's "Record", `Today.tsx:285`); `.chip-filter` 36 px (`app.css:683-684`); stand-alone "Forgot password?" link measured at 19 px tall at 320 px | Use the `--touch` (48 px) token for these, at least on the mid-class path. Pad stand-alone links to 24 px or more (WCAG 2.5.8) | S |
| UX-20 | Low | Web | Nav landmarks named with the brand | `AppShell.tsx:183,244`: `aria-label="ShikkhokPlus"` on both `<nav>`s, not localized | Use a localized "Main navigation" label | S |
| UX-21 | Low | Web | Count `aria-label` on a plain `<span>` | `AppShell.tsx:134-142`: `aria-label` on a span with no role is generally not read out, so the screen reader hears just "3" | Put the count text in a visually hidden span inside the link | S |
| UX-22 | Low | Web | A load error that can't be retried leaves only Back | `components.tsx:232-236` renders no action when `!retryable` | Add a secondary "Go to Today" or home link | S |
| UX-23 | Low | Web | Phone has no "Verify" tab or count | `shell/nav.ts:28` marks `/verify` `desktopOnly`, and the bottom nav passes `counts={{}}` (`AppShell.tsx:245`). The Today KPI card (`Today.tsx:136`) is the only way in on a phone | Fine as decided. Make sure the Today card always shows the pending count (it does when it loads), and add the count to the "More" badge if Today fails to load | S |
| UX-24 | Low | Android | No "All present" reset | Web has `web_classes_all_present` (`SessionScreen.tsx:461-471`); there is no Android equivalent (`res/values/strings.xml`, no key) | Add a "Mark all present" text action to the shared row list from UX-5 | S |

**Recomputed contrast (WCAG formula, light theme)**: on-surface-variant on
container-high 7.27:1; verifying 7.46:1; partial 7.90:1; error on white 7.56:1;
`--outline` (field and toggle borders) on white 4.59:1, which passes 3:1 for
non-text. No contrast finding.

## Top 5 improvements, ranked

### 1. Fix the attendance row for small screens in Bangla (UX-1, UX-19) — web
Why first: this is the mid-class path [PU-3.6], on low-end phones, in the default
language. Today it shows two or three students per screen and breaks names in
the middle of a word.
**Acceptance**
- At 320×640 and 360×640 with `lang=bn` and the name 'মোহাম্মদ আব্দুল্লাহ আল মামুন',
  the name column is at least 140 px wide, and no word is broken in the middle.
  Each row is at most 72 px tall for names of up to 2 lines.
- At 360×640 with 20 students and an empty topic, 6 or more seat rows are
  visible after scrolling past the topic field.
- Every tap target in a row is at least 48×48 px (Playwright
  `getBoundingClientRect`).
- Marking one student absent and saving takes **2 taps from the session screen**
  (row, Save) and **3 from Today** (Record, row, Save). This is a Playwright test
  with `/v1/**` stubbed.
- A screen reader announces "<name>, Present/Absent, toggle button, pressed or
  not pressed", using `aria-pressed` on a control whose name includes the
  student's name.
- `document.documentElement.scrollWidth === innerWidth` (no horizontal overflow).

### 2. Unify form validation and error wiring (UX-6, UX-7, UX-11) — web
**Acceptance**
- One shared `Field` component is used by RecordPaymentSheet, ApprovalSheet,
  PayScreen amount, NewStudent/AddStudent phone fields, ExamForm and ExtraFees.
  `grep 'className="field-error"'` outside that component returns nothing in
  `features/`.
- Typing "0" into a phone field shows no error. Blurring with "017" shows
  `phone_digit_count`. Fixing it to 11 digits removes the error immediately,
  without a blur.
- Each invalid input has `aria-invalid="true"` and an `aria-describedby` that
  points at the visible error text (testing-library `toHaveAccessibleDescription`).
- On submit with errors, focus moves to the first invalid field.
- `/students/new` and `/batches/:id/students/new` render the same form. The
  batch-scoped route pre-selects the batch.

### 3. Make destructive and lossy actions consistent (UX-8, UX-9, UX-10) — web
**Acceptance**
- Removing a seat from Student detail opens the same confirm sheet as the
  Students tab. No `remove*` or `delete*` API call is reachable from a single
  click without a confirm sheet or an Undo snackbar. A test clicks each
  destructive button and asserts that no request was sent before confirming.
- `Sheet` accepts `dirty`. With a typed amount in Record payment, a backdrop
  click or Escape does not close the sheet. It asks "Discard?" (new string keys
  in both `en` and `bn`).
- Payroll "Remove" buttons have unique accessible names, including the
  adjustment label.

### 4. Android attendance: accessible rows, no lost topic, a clear finish (UX-2, UX-3, UX-4, UX-5, UX-24)
*Android may not compile in this environment. Verify with Robolectric /
Compose UI tests in CI.*
**Acceptance**
- One `AttendanceSeatRow` in `core/ui` is used by both `AttendanceScreen` and
  `ClassDayScreen`. The row is `toggleable(role = Role.Switch)`, and the
  `Switch` has `onCheckedChange = null`.
- A Compose test asserts that each seat node's merged semantics contain the
  student's name and a Present/Absent state description.
- Typing a topic, tapping "Take attendance" and coming back leaves the topic
  text unchanged (ViewModel test).
- `Confirmed` and `Failed` render a toned `Banner` and a "Done" action that pops
  back. Non-retryable failure is not a dead end.
- The Bangla layout check rows for D4 T2 are filled in with PASS, FAIL or FIXED.

### 5. Keep the user oriented after actions (UX-12, UX-13, UX-14, UX-15) — web
**Acceptance**
- Today → class → Back returns to Today. A deep link to the session → Back goes
  to the batch's Classes tab.
- After Save on a class, `document.activeElement` is the `h1` or the snackbar,
  never `<body>`.
- A snackbar with an action stays until dismissed or acted on. The PWA update
  prompt is still visible 30 s after it appears.
- The snackbar never overlaps `.action-bar`: their bounding boxes don't
  intersect at 360×640.

*Also recommended, not ranked:* turn UX-17 into a working verifier by adding the
web PWA to `bangla-layout-check.md` and a `bn`/320 px Playwright layout probe to
`npm run check`. That is how UX-1 gets caught next time instead of found by hand.
