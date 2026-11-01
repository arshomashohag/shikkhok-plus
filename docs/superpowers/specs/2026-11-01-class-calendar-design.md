# Class calendar — design

Date: 2026-11-01
Status: draft for approval
Mockup: `.superpowers/brainstorm/57086-1793508567/content/teacher-calendar.html`
(approved by the owner as drawn)

## Why

1. Students and guardians only ever see classes that already happened.
   The family batch screen lists past sessions (`date < today`) plus a
   "next class" line, so on 1 November every class they can see is in
   October, while the teacher sees November too. This is a display gap,
   not missing data: the nightly job already creates every class for the
   current and next month (`app/teaching/generation.py`, cron
   `app.teaching.commands generate`).
2. The teacher's class list runs oldest first, so the class that matters
   today is at the bottom.
3. A teacher can't plan a future class's topics: writing a topic today
   also marks the class taken (`write_topic` sets `status="held"`).

The owner's picture: on a busy afternoon the teacher opens a batch, taps
today, writes what was covered and takes attendance; when they have a
minute, they set the topics of upcoming classes.

Success: anyone opening a batch sees this month at a glance — what was
taught, what's coming, today — and can open any date to its details;
the teacher can plan ahead and record today in a few taps.

## Goals

- A month calendar replaces the class list, for teachers, students and
  guardians.
- Any month/year can be picked to see older (or the next) month.
- Tapping a date opens that class: topics, notes, attendance.
- Teachers record today's topics, notes and attendance from today's date.
- Teachers set and edit planned topics on upcoming classes, until the
  class starts.
- Students and guardians see the same calendar, read-only.

## Non-goals

- Changing how classes are generated, the weekly schedule editor, or
  cancelling/moving a class (those flows exist and stay).
- Notifications for planned topics.
- Showing families other children's attendance.

## Anti-goals

- The client deciding what a date's state is (taken, upcoming,
  not recorded, cancelled) — the server sends it.
- A family member seeing another child's attendance, or anything a
  student or guardian wrote reaching a teacher.
- Losing the existing offline attendance queue and conflict handling.

## Constraints

All of `aidlc/spaces/default/memory/` applies. The ones that bite:

- Every new route names its lens; families read through the existing
  family lens rules (`readable_enrollment`).
- Server sends message keys, not English; Bangla and English strings for
  everything new; teacher-typed text (topics, notes) shown verbatim.
- Migration `0012`, forward-only.
- `openapi.json` regenerated under the locked dependencies.
- Test-first where a wrong answer is an authorization error (family
  reads of attendance; per-child scoping).
- Coverage floors only go up (backend 80% line, Kotlin floor in
  `android/coverage-floor.txt`).
- Dates and "today" in Bangladesh time (`app.local_time`).

## The parts, as decided

### Calendar (teacher, student, guardian)

- Lives in the batch's Classes tab (teacher batch screen, and the family
  batch screen's Classes tab built in the previous change).
- A month grid, Sunday first, with a header showing "November 2026 ▾"
  and previous/next arrows. Tapping the header opens a month + year
  picker.
- Each date with a class shows its state, decided by the server:
  - **taken** — green tick (the class is `held`);
  - **today** — filled green;
  - **upcoming** — outlined with a dot;
  - **not recorded** — grey: a past `scheduled` class nobody recorded
    (the teacher can still record it);
  - **cancelled** — struck through.
- A day with more than one class (a batch may have several weekday slots
  at different start times, `refuse_duplicate_slots` only rejects the
  same start time) shows a small count marker; tapping it lists the
  classes by start time and subject to pick one.
- The month shown on open is the current month.

### A class's detail (teacher)

- **Today, or any past date:** topics covered, optional notes, and the
  attendance sheet (Present / Absent per student), then Save. This reuses
  the existing record-class flow (`RecordClassViewModel`, the offline
  queue, attendance version and conflict screen); the calendar is a new
  way in. Saving topics or attendance marks the class taken, as today.
- **Upcoming date (before the class's start time):** planned topics and
  notes, editable; attendance shows "Opens on the day of the class".
  Saving a plan does NOT mark the class taken.
- **From the class's start time** the topics field is "topics covered".

### A class's detail (student, guardian)

- Read-only. A taken date shows topics covered, notes, and this child's
  own present/absent mark. An upcoming date shows the planned topics and
  notes. No edit controls.
- A guardian sees it per child, as the batch screen already does.
- A child who joined after a class does not see attendance for it.

### Topics and notes

- One topics field per class, as now. Before start it is the plan; from
  start it is what was covered. No separate planned-topics column.
- New optional `notes` text on each class, teacher-written, shown
  verbatim to families.
- Planned-topic edits are allowed until the class's start date-time
  (Bangladesh time); after that, edits follow the existing topic rules
  (and mark it taken).

### Rules settled after review (Claude's calls)

- **Start time** = the class's stored `date` + `start_time`, in
  Bangladesh time (`app.local_time`). A rescheduled class uses its new
  date and time.
- **Plan vs covered is an explicit intent, checked by the server.** The
  client sends whether a write is a plan. A plan write is accepted only
  before start; a plan that reaches the server after start (e.g. queued
  offline at 3:50, sent at 4:10 for a 4:00 class) is refused with a
  conflict and a message key, and the app shows it on the existing
  conflict screen so the teacher can save it as covered or drop it. The
  server never silently turns a plan into a covered write.
- **What marks a class taken:** saving covered topics (including an
  explicitly blank topic, as today) or attendance, at or after start.
  Plans and notes never mark it taken.
- **Clearing a plan:** a teacher can clear planned topics back to empty
  (NULL) before start.
- **Notes travel with topics:** one write carries topics + notes,
  queued offline and versioned by the existing `topic_version`, so the
  single Save works offline. Notes up to 2000 characters, like topics.
- **Day cell state, decided by the server per day** with this order:
  today > upcoming > not recorded > taken > cancelled (a day shows its
  most actionable class); the count marker shows when there is more
  than one class.
- **Editing the past:** unchanged from today — a teacher may record or
  correct any past class of an active batch. Inactive batches show the
  calendar read-only (server says `BATCH_INACTIVE`, as now). Cancelled
  classes open read-only for everyone, families included.
- **Joined after / left:** families see a class's topics for every class
  in the month, but their child's attendance only for classes on or
  after the seat started (the same `joined_on`, else `created_at`, rule
  fee generation uses) and before `inactive_from`. Outside that window
  the mark reads "Not enrolled then". Only accepted links see anything,
  as the family lens already enforces.
- **Subjects:** a seat belongs to the whole batch, so families see every
  class of the batch, all subjects.

### Old list

The teacher's oldest-first session list is replaced by the calendar.

## Left to the builder

- API shape: a month endpoint per batch (teacher) and per seat (family)
  returning each class's date, start/end time, subject, server-decided
  state, topics, notes, and (family) the child's own mark — or extending
  existing endpoints. Any month the batch existed may be asked for.
- How "planned" topic writes are separated from "covered" writes in
  `write_topic` (e.g. a flag, or the server deciding from the class's
  start time).
- Bounds for notes length (topics already allow 2000 chars).
- The month/year picker's range (no earlier than the batch's creation,
  no later than the generation horizon).
- Visual details beyond the mockup, following the existing design
  system.

## Calls Claude made (owner to confirm while reading)

- One topics field that is the plan before start and the record after.
- Notes is a new optional field, visible to families.
- Past unrecorded classes show grey "not recorded" and stay recordable.
- Cancelled classes show struck through.
- Families see only their own child's attendance, and nothing from
  before the child joined.
- The calendar opens on the current month.
