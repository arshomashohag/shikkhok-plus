# Family screens, one inbox, and exam topics — design

Date: 2026-10-31
Status: draft for approval

## Why

The owner walked through the app end to end before anyone uses it and
found five gaps that make it feel unfinished:

1. Inner screens with no back arrow, so a person cannot get back to
   where they came from.
2. The bell only shows fee reminders. Notices, payment outcomes and exam
   news never reach it, and nothing tells a person something new arrived
   while the app is closed.
3. A student's (and guardian's) batch page stacks everything — classes,
   notices, the next exam — on one long screen, while the teacher gets
   tidy tabs. Nothing on it opens to a detail.
4. Students and guardians see nothing about the teacher.
5. A teacher cannot say what an exam covers.

Success: a student, guardian or teacher can find every update in one
place, open any item to its full detail, always get back with a back
arrow, and see on the app icon that something new is waiting.

## Goals

- One inbox per person under the bell, holding every kind of update.
- Every inbox item opens a detail screen.
- An unread count on the app icon while the app is closed.
- The family (student and guardian) batch screen split into tabs, each
  item opening its detail.
- A Teacher tab for families.
- Topics on exams, written by the teacher, read by families.
- A back arrow on every non-home screen.

## Non-goals

- Instant push. Decided: a 15-minute background check now. Firebase push
  is a possible later upgrade and is **not** added here.
- Replies, comments or read receipts visible to teachers.
- Changing what a teacher's own screens show, except exam topics and
  the optional rejection reason.
- Teacher photos.
- Notification settings or per-kind muting.

## Anti-goals (would make this a failure even if it "works")

- Any new SDK that sends a device or advertising identifier
  (`project.md` NEVER rules). This design adds no SDK.
- The client deciding anything a server should: what is unread, who an
  item is for, whether an exam is upcoming or done (`project.md`
  ALWAYS keep business rules server-side).
- A teacher seeing anything a student or guardian wrote.
- One person seeing another person's inbox.
- A family member seeing a teacher's phone number or address.

## Constraints

Everything in `aidlc/spaces/default/memory/` applies. The ones that bite
here:

- Per-request lens authorization; every new route names its lens, and
  the route-enumeration gate must stay green.
- Teacher-lens responses carry no student or guardian profile fields.
- Message keys, not English, from the server; Bangla and English strings
  for every new piece of text.
- The committed `openapi.json` is regenerated with `make openapi` under
  the **locked** dependencies (see the 2026-10-31 FastAPI drift: install
  `requirements.txt`, not `pip install -e`).
- Migrations forward-only and backward-compatible; `0011` is next.
- Test-first where a wrong answer is an authorization error: inbox
  fan-out recipients and inbox read isolation meet that predicate.
- Android: no new dependency without regenerating the Gradle lockfile and
  checksums. WorkManager is the one new library this design needs
  (`androidx.work:work-runtime-ktx`); it sends no identifier and needs an
  SDK admission note.

## The parts, as decided

### 1. Back arrows

Every screen that is not a home tab gets a back arrow that pops to where
it was opened from. Known missing today: Marksheet, Progress, Fee
history, Sessions, Attendance, Exams. Home tabs (Today, Batches, Dues,
My batches, Guardian home, Profile, sign-in) stay without one. A detail
opened from the bell returns to the bell; one opened from a batch tab
returns to that tab.

### 2. The inbox ("bell")

**What lands in it** (decided):

| Kind | Who gets it | Detail shows |
|---|---|---|
| Notice posted | every accepted student and guardian of the batch | full text, batch, date |
| Notice edited | the same people; updates the existing item, marks it unread | same |
| Notice deleted | removes the item | — |
| Payment claim approved / partly approved / rejected | the student and guardians of that seat | amount claimed, amount approved, period, outcome, reason if rejected |
| New payment to verify | the batch's teacher | who claimed (student name only), amount, period; opens the existing verification screen |
| Fee reminder | as today | as today |
| Exam scheduled | every accepted student and guardian of the batch | title, date, subject, total, topics |
| Marks available | the student and guardians of the seat | opens that exam's marksheet |

- One list per person, newest first, unread items bold.
- Opening an item marks it read; a "Mark all read" action exists.
- A guardian's items are labelled with the child's name.
- The server stores each item as a row per recipient in the existing
  `notification` table (`app/notifications/inbox.py`), extended with
  what the detail screens need. Items for one account are only ever read
  `WHERE account_id = :caller`, as today.
- The bell shows the unread count, read from the server.

**Items point to their source; details load live** (Claude's call). An
inbox row records what it is about (kind, batch, seat, the notice /
exam / claim id) and a short summary for the list. The detail screen
loads the current source through the reader's lens. Consequences:

- An exam whose date or topics change, or a payment decision that is
  corrected (`correcting=True`), shows the current version when opened;
  the change also marks the item unread again. No duplicate item.
- **Access lost means detail lost.** If the reader's seat is removed, a
  guardian declines or is unlinked, the item stays in the list (so the
  history is not silently rewritten) but its detail answers "no longer
  available" — the lens decides, not the inbox row. This is the
  authorization rule tested first.
- Fan-out goes to seats active on the item's date: a seat past its
  `inactive_from` gets no new notices or exams. Payment items still go
  to that seat's student and guardians while dues are open.
- Someone who accepts a seat later gets new items only; past notices and
  exams are on the batch's tabs, not back-filled into the inbox.

**Detail screens**: one per kind, each with a back arrow. A notice or
exam detail renders the server's text. A payment item opens its detail; the
teacher's "new payment to verify" opens the existing verification flow.

### 3. Count on the app icon

Decided: a **15-minute background check**, no Firebase.

- WorkManager periodic work, 15 minutes (Android's floor; Doze may
  delay it further, and that is accepted).
- It runs only while signed in, asks the server for the unread count and
  the newest unread items, and if there is anything **new since the last
  check** posts or updates ONE tray notification ("3 new updates"), with
  `setNumber(unreadCount)` so launchers that show numbers show the
  count. Tapping it opens the bell list.
- When the app is opened, or everything is read, the tray notification
  is cleared.
- Android 13+: the app asks once for notification permission, after
  sign-in, not at first launch. If refused, the bell still works in-app.
- Sign-out cancels the work and clears the notification.
- The tray notification text names no child, teacher or amount: the
  lock screen is visible to anyone holding the phone.

### 4. Family batch screen

Header: batch name, subject, next class, and the existing fees row / Pay
button. Tabs: **Classes · Exams · Notices · Teacher**.

- **Classes**: upcoming (from the schedule) then past, with topic and
  this student's attendance. A past class opens its detail: date, time,
  topic covered, attendance.
- **Exams**: "Coming up" and "Done", grouped by the server. Coming up
  opens an exam detail (date, subject, total, topics); done opens the
  existing marksheet.
- **Notices**: newest first with a preview; opens the full notice.
- **Teacher**: see 5.

Guardians get the same screen per child, with the child's name in the
header, and see exactly what the student sees.

### 5. Teacher tab

Shows the teacher's **name, an initials avatar and the subjects they
teach in this batch**. **No phone number, no address.** (Claude's call
as the safer default for a children's app; the owner may ask for the
phone later.)

- **No photo** (decided). Nothing uploads or serves one today; photos
  are a separate later feature (upload, storage cost, image library, and
  a change to the owner-only `profile` policy).
- **The name is `Batch.teacher_display_name`**, the one name families
  may be shown. `profile.self_name` is owner-private and is not read.
  When the display name is blank, the tab says "Your teacher" and the
  avatar shows a generic person icon instead of initials.
- Initials and avatar colour are presentation of the server's name, not
  a decision; the server sends the name, the app draws it.

### 5a. Rejection reason

Decided: **free text typed by the teacher.**

- The teacher's reject action gains an optional "Reason" text field
  (bounded length, builder's choice of limit). This is the one change
  to the teacher's verification screen.
- Stored on the claim decision; a correction that rejects again may
  carry a new reason, and the current one is what the detail shows.
- Families see it exactly as typed, in whatever language. It is the
  teacher's own writing, so it crosses no privacy boundary; it is not a
  message key and is not translated.
- No reason given: the detail says "Rejected" only.

### 6. Exam topics

- A teacher adds topics when creating or editing an exam: a list of
  short lines, one per topic.
- Stored as an ordered list on the exam (new column or child table,
  builder's choice), bounded in count and length.
- Shown in the exam detail to families, in the "exam scheduled" inbox
  item, and on the teacher's exam form when editing.
- Optional: an exam with no topics is valid.

## Left to the builder

- Exact schema for inbox extensions and topics, and the migration.
- Whether notice fan-out happens in the request transaction (preferred,
  so a notice and its inbox rows commit together) or after.
- API shape of the new family batch endpoint(s); splitting the current
  one-bundle response is allowed.
- Limits: topic count and length, inbox page size and retention.
- Visual design: follow the existing design-system components and the
  teacher batch screen's tab pattern. No new design board exists; where
  one is needed, mirror T7.

## Calls Claude made (owner to confirm while reading)

- No phone or address on the Teacher tab; a blank display name reads
  "Your teacher".
- Editing a notice marks its inbox item unread again.
- The tray notification is generic and names nobody.
- Notification permission is asked after sign-in, not at first launch.
- "Marks available" fires when a seat's mark is recorded while the
  batch's marksheets are visible, and for every marked seat when the
  teacher turns marksheet visibility on.
- Inbox items point to their source and load details live; changes mark
  the item unread; lost access shows "no longer available"; inactive
  seats get no new notices or exams; no back-fill for late acceptance.
