# Coaching centres — design

Date: 2026-11-06
Status: draft for approval (all product decisions recorded). Staff,
payroll, extra fees and expenses are designed in
`2026-11-06-fees-expenses-and-staff-design.md`.

## Why

Today one teacher runs their own batches. A coaching centre is different:
several teachers teach many batches with hundreds of students, a batch can
meet more than once a day, most days have classes, and one or more managers
build the timetable and decide which teacher takes each class.

Success: a centre's managers can run the whole centre from the app, a
teacher hired by a centre sees and does only what their own classes need,
and a teacher who tutors privately keeps working exactly as today — with the
same account.

## Owner decisions, 2026-11-06

| # | Decision |
|---|---|
| D1 | One person can be a solo tutor **and** teach at one or more centres, with one account. |
| D2 | A solo tutor keeps full control of their own batches. At a centre, a teacher sees **only their own classes** in the schedule, and can **update the class topic, take attendance and enter marks — nothing else** (later extended by D15: they also see their own pay). They never see another teacher's classes. |
| D3 | Marks are entered and published by the subject's teacher **and** by a manager. A manager has **every read and write permission** in the centre. |
| D4 | **Only a manager** assigns, reassigns or swaps the teacher of a class. |
| D5 | A class can have a **room**, chosen when the class is created. Optional. |
| D6 | Centres will be the paid tier eventually. **For now everything is free**; nothing about billing is built. |

## What the codebase already gives us

- Batches, students and payment methods hang off `owner`, not off an
  account (`app/db/models.py`: `Owner`, `Student`, `Batch`,
  `PaymentMethod`). The feasibility architecture (§8b) planned exactly this
  so a centre is a new kind of owner and no batch, enrollment, fee cycle or
  ledger row migrates.
- Every write already records the **person**, not the owner:
  `Attendance.recorded_by_account_id`, `Mark.recorded_by_account_id`,
  `PaymentClaim.verified_by_account_id`, `Announcement.posted_by_account_id`.
- Lenses are recomputed per request with no cache (`app/authz/resolve.py`),
  so revoking a centre teacher takes effect on their next request.
- Classes are materialised `session` rows, so a teacher and a room can be
  attached to one occurrence.
- Seat acceptance (ADR-014) is the pattern staff invitations reuse: naming
  a phone number never grants access; accepting does.

## What does not fit today

1. **One owner per account, one person per owner.** `owner` has only
   `id` and `account_id`; `_LENS_QUERY` and `_SUMMARY_QUERY` pick one owner
   with `LIMIT 1`. A tutor who also teaches at a centre would silently get
   one workspace (breaks D1).
2. **The teacher lens is all-or-nothing.** `TeacherLens(owner_id)` scopes
   about 40 queries as `Batch.owner_id == lens.owner_id` across 56 teacher
   routes. That is a manager's power, not a centre teacher's (breaks D2).
3. **No record of who teaches a class.** `schedule_slot` and `session` have
   no teacher and no room; "the teacher" is free text on
   `batch.teacher_display_name`. Nothing prevents double-booking (breaks
   D4, D5).
4. **Flows that assume one human behind an owner.**
   `teacher_recipient()` (`app/notifications/recipients.py`) notifies
   `owner.account_id`; account deletion (`app/governance/deletion.py`)
   retires every batch of every owner the account holds — a centre
   teacher deleting their account would retire the centre's batches.

## Design

### 1. Workspaces and membership

```
owner         + kind  ('teacher' | 'organisation')   -- no default [ADR-013 habit]
              + name  (centre name; NULL for a solo tutor)

owner_member  id, owner_id, account_id NULL, invited_phone, display_name,
              role      ('manager' | 'teacher'),
              decision  ('pending' | 'accepted' | 'declined'),
              relink_blocked_at, revoked_at, created_at
              UNIQUE (owner_id, account_id) WHERE account_id IS NOT NULL
```

- Migration backfills one `manager` membership, `accepted`, for every
  existing owner (`kind = 'teacher'`). After that, **membership is the only
  source of workspace access** and solo tutors go through the same path as
  centres — no special case.
- A `kind = 'teacher'` owner has exactly one member; invitations are only
  possible on an `organisation`. A centre always keeps at least one accepted
  manager — enforced in the transaction that revokes or demotes, and tested.
- **Sign-up offers a fourth account type, Coaching** (owner decision
  2026-11-06). Choosing it asks for the centre's name and, in the same
  transaction as the account, creates an `organisation` owner and an
  accepted `manager` membership for the person signing up. Like the other
  three types it only picks the home screen; it is not stored as a role.
- Staff are invited by phone and gain nothing until they accept, exactly as
  a seat does. Revoking sets `revoked_at`; the next request has no lens.
- Rooms: `room(id, owner_id, name, archived_at)`, managed by managers.

### 2. Two lenses, one of them new

| Lens | Who | Reaches |
|---|---|---|
| `TeacherLens(owner_id, member_id)` — **unchanged meaning** | a solo tutor; a centre **manager** | everything in that owner, as today (D2 solo half, D3) |
| `ClassTeacherLens(owner_id, member_id)` — **new** | a centre **teacher** | only sessions where `session.teacher_member_id = member_id`, and exams where `exam.examiner_member_id = member_id` |

Why this split: the 56 existing routes keep `TeacherLens` and keep their
`Batch.owner_id == lens.owner_id` scoping untouched. Only **resolution**
changes (membership with role `manager` instead of `owner.account_id`).
The narrow lens is added only to the handful of classroom routes D2 lists,
whose dependency becomes `TeacherLens | ClassTeacherLens`. A centre teacher
therefore cannot reach any route that was not deliberately opened to them,
which is the fail-closed default.

The route-enumeration gate extends with one assertion: every route
accepting `ClassTeacherLens` is in an explicit allowlist, so opening a route
to centre teachers is a visible diff, never an accident.

**Which workspace a request acts on:**

- Resource routes (`/v1/batches/{id}/…`, `/v1/sessions/{id}/…`,
  `/v1/exams/{id}/…`) derive the owner **from the resource** and check the
  caller's membership in it. No contract change.
- Collection routes (batch list, students, dues, today, payment methods)
  take an `owner_id` query parameter, validated against memberships — the
  same pattern as the guardian's `child_enrollment_id`, so no client hint is
  trusted. For compatibility with the shipped Android build [D-26] the
  parameter may be omitted while the account has exactly one workspace.
- `/v1/me` lists workspaces (`owner_id`, name, kind, role); the lens picker
  becomes a workspace switcher.

Lens resolution stays one statement [NFR6.1]: it returns the set of
accepted, unrevoked memberships instead of `LIMIT 1`.

### 3. What a centre teacher can do (D2), as routes and schemas

| Capability | Route shape | Scope predicate |
|---|---|---|
| My schedule (today, calendar) | new `GET /v1/me/classes?from&to` across all workspaces | `teacher_member_id` in my memberships |
| Class detail + roster | `GET /v1/sessions/{id}` | assigned to me |
| Take attendance (including the offline queue) | existing attendance write | assigned to me **at replay time** |
| Update topic and notes | existing topic write | assigned to me |
| Exams I examine, enter and publish marks | existing marks routes | `examiner_member_id = me` |
| My pay, read-only (added by D15 in the fees design) | new `GET /v1/me/pay?owner_id` | `staff.member_id = me` |

Privacy is enforced by **schema**, not by filtering: the class-teacher
roster is a separate response type carrying `enrollment_id` and the
teacher-typed `display_name` only — no phone numbers, no guardian, no fee
status. The existing OpenAPI-wide invariant test is extended: no
`ClassTeacherLens` response schema may contain a phone, guardian, fee or
profile field. Profile data stays invisible to managers too — "every
permission" (D3) does not override the `NEVER expose anything a student or
guardian writes to any teacher` rule, which is structural (RLS on
`profile`).

Offline writes: a queued attendance composed before a manager reassigned
the class is **refused at replay** with a new error code
(`class_reassigned`), never applied. The refusal needs a new
`message_key` in both string bundles; that is no extra release, because a
centre teacher exists only from the release that ships their screens.

A centre teacher does not see fees, dues, payment methods, students
outside their roster, notices, batch settings, or any class not assigned to
them — including other classes of the same batch.

### 4. Assignment, swaps and rooms (D4, D5)

```
schedule_slot  + teacher_member_id NULL, + room_id NULL, + batch_subject_id NULL
session        + teacher_member_id NULL, + room_id NULL,
               + assignment_source ('slot' | 'override')
exam           + examiner_member_id NULL
```

- Generation copies the slot's teacher and room into each new session.
- A manager can override one session (substitute) or swap the teachers of
  two sessions. Both are manager-only `TeacherLens` routes (D4).
- **Rule amendment (BR1.2):** reassigning a slot's teacher or room now
  updates *future, not-yet-held, non-overridden* sessions. Held, cancelled
  and overridden sessions are untouched. Today's rule — schedule changes
  never touch generated sessions — still holds for times and weekdays.
- **Double-booking is refused by the database**, not by application code:

  ```sql
  CREATE EXTENSION IF NOT EXISTS btree_gist;
  ALTER TABLE session ADD CONSTRAINT ex_session_teacher_overlap
    EXCLUDE USING gist (
      teacher_member_id WITH =,
      tsrange(date + start_time, date + coalesce(end_time, start_time + interval '1 minute')) WITH &&
    ) WHERE (status <> 'cancelled' AND teacher_member_id IS NOT NULL)
    DEFERRABLE INITIALLY IMMEDIATE;
  -- the same shape for room_id
  ```

  `DEFERRABLE` is required for swaps: exchanging the teachers of two
  overlapping classes passes through a transient double-booking, so the
  swap runs `SET CONSTRAINTS … DEFERRED` inside one transaction.
  `btree_gist` is supported on RDS PostgreSQL 16.
- A violation maps to a `ConflictError` naming the clashing class, which the
  manager can read in full.
- `exam.examiner_member_id` defaults at creation to the teacher of that
  batch-subject's slots when there is exactly one, otherwise the manager
  picks.
- Families see the teacher assigned to each class (name only, via the
  existing no-phone teacher schema) instead of `batch.teacher_display_name`,
  which remains for solo tutors.

### 5. Everything else that changes

- **Notifications:** payment and submission notices go to every accepted
  manager of the owner; class-level notices (a refused offline replay) go
  to the assigned teacher.
- **Account deletion:** for each membership, a centre teacher's or
  manager's deletion revokes the membership and clears its `account_id`,
  keeping the manager-typed `display_name` as the record of who taught
  (disposition to be confirmed at Domain Design; the manifest completeness
  test forces the decision). Only a `kind = 'teacher'` owner retires its
  batches as today. Closing a centre is a separate manager action.
- **Data Safety / privacy policy:** staff accounts now see children's names
  and attendance. The policy text is generated from dispositions, so the new
  tables flow into it; the Data Safety answers are rechecked before release.
- **Clients:** managers get a timetable across batches, teachers and rooms
  — on the web desktop layout first, where the grid fits. Centre teachers
  get "My classes" (today plus calendar), the class screen
  (attendance, topic) and "My exams" on Android and web. The nav set
  (`web/src/shell/nav.ts`, `ShikkhokNavHost.kt`) gains a centre-teacher
  tab set.
- **Billing (D6):** nothing is built. The owner row is where a plan will
  attach, and the two lenses give exactly two enforcement points when it
  does.
- **Capacity:** a centre with 30 batches and two classes a day is about
  3,600 session rows per two-month horizon and a few hundred enrollments —
  well within the current t4g.small and RDS micro and the USD 50/month
  ceiling. The open risk is PU-3.6 (mid-class attendance speed) on a
  100-plus roster on a low-end phone; its manual pilot check must include a
  centre-sized roster.

## Delivery order

Each step ships on its own and leaves solo tutors unchanged.

1. **Foundations — no visible change.** `owner.kind`/`name`,
   `owner_member` with backfill, resolution over memberships, the
   `owner_id` parameter on collection routes, deletion and notification
   routing through membership. All authorization; test-first under the
   team's predicate.
2. **Centres and managers.** Create a centre, invite managers and teachers
   with acceptance, rooms. Managers use today's teacher screens
   centre-wide; workspace switcher.
3. **Scheduling.** Teacher and room on slots and sessions, generation
   copying them, override and swap, the two exclusion constraints, the
   BR1.2 amendment, the manager timetable on web.
4. **Centre teachers.** `ClassTeacherLens`, `/v1/me/classes`, names-only
   roster, attendance/topic/marks under assignment, examiner on exams,
   replay refusal, the centre-teacher tab set on both clients.

Out of scope: teacher salaries/payroll (new money-module arithmetic, its
own intent), multi-branch centres, billing.

## Decided 2026-11-06 (the proposed defaults, accepted)

1. **Exams at a centre:** a manager creates the exam and names the
   examiner; the examiner enters and publishes its marks.
2. **Clashes with a tutor's private schedule:** checked within one centre
   only. A centre learns nothing about a tutor's private batches.
3. **After reassignment:** a reassigned class moves entirely to the new
   teacher, past attendance view included. A revoked teacher loses
   everything at once.
