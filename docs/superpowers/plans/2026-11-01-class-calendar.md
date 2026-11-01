# Class Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the class list with a month calendar for teachers, students and guardians; let teachers plan topics on upcoming classes and record today's topics, notes and attendance from one screen.

**Architecture:** The server computes a month view per batch (teacher) and per seat (family): every class in the month with a server-decided class state and a server-decided day state, plus topics, notes and (family) the child's own mark. The topic write gains an explicit `plan` intent and a `notes` field, both checked server-side against the class start time. Android draws a calendar from that payload and routes date taps into the existing record/attendance flows.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, pytest + testcontainers; Kotlin, Jetpack Compose, Ktor, Robolectric.

**Spec:** `docs/superpowers/specs/2026-11-01-class-calendar-design.md`

## Global Constraints

- All `aidlc/spaces/default/memory/` rules apply.
- Every new route resolves a lens; `tests/contract/test_route_lenses.py` stays green.
- Family reads go through `readable_enrollment` (app/teaching/roster.py:183); only accepted links see anything.
- Server sends message keys, not English; new keys published in `message-keys.json` + `values/strings.xml` + `values-bn/strings.xml` (Western digits in Bangla strings).
- Teacher-typed text (topics, notes) shown verbatim; notes ≤ 2000 chars, like topics.
- "Today" and start times in Bangladesh time via `app.local_time.bangladesh_now()` / `bangladesh_today()`; start = session `date` + `start_time`.
- Migration `0012`, forward-only; `tests/db/test_migration_head_pin.py` `EXPECTED_HEAD = "0012"`.
- `openapi.json` regenerated with `make openapi` under the locked dependencies; changes additive (D-26).
- Test-first for: plan-vs-covered state rules, family per-child attendance scoping, family lens refusal.
- Coverage floors only go up (backend 80% line; Kotlin `android/coverage-floor.txt`).
- Android holds no business rule: class state, day state, editability, "not enrolled then" all come from the server.
- Python line length 88, Sphinx docstrings, type hints; Ruff + mypy clean. Android: `make android-quality` green.

## Review Focus

1. A day with two classes in different states must show the server's day state (today > upcoming > not recorded > taken > cancelled) and list both classes on tap — owner: Task 3 (server precedence test) and Task 5 (tap lists both).
2. A plan queued offline before start and sent after start must be refused with `teaching.topic.class_started`, never applied as covered — owner: Task 2 (server) and Task 5 (conflict screen shown).
3. A guardian of a child who joined mid-month sees topics for every class but "Not enrolled then" for classes before the join date — owner: Task 3.
4. Picking a month outside the batch's life (before creation, after the generation horizon) must not crash: the server refuses with a validation key and the picker cannot select it — owner: Task 3 and Task 4.
5. Bangla topics/notes at 2000 chars render in the detail without breaking layout — owner: Task 6 (screen test at max length).

---

### Task 1: Session notes column

**Files:**
- Create: `migrations/versions/0012_session_notes.py`
- Modify: `app/db/models.py` (`Session.notes`), `tests/db/test_migration_head_pin.py`, any test pinning revision `"0011"`
- Test: `tests/db/test_migration_0012.py`

**Interfaces:**
- Produces: `session.notes TEXT NULL`; `Session.notes: Mapped[str | None]`.

- [ ] **Step 1:** Test `test_0012_adds_nullable_notes`: column exists, nullable, existing sessions read `None`.
- [ ] **Step 2:** Run `pytest tests/db/test_migration_0012.py`; expect FAIL.
- [ ] **Step 3:** Write migration (`revision="0011"`→`"0012"`), model field, bump head pin and revision count.
- [ ] **Step 4:** Run `pytest tests/db tests/auth`; expect PASS.
- [ ] **Step 5:** Commit `feat(db): notes on a class`.

### Task 2: Plan vs covered on the topic write (test-first)

**Files:**
- Modify: `app/teaching/submissions.py` (`write_topic`), `app/schemas/teaching.py` (`TopicWriteRequest`), `app/api/teaching.py` (`/sessions/{session_id}/topic`), `message-keys.json`, Android strings
- Test: `tests/teaching/test_topic_plan.py`

**Interfaces:**
- `TopicWriteRequest` gains `plan: bool = False` and `notes: str | None = Field(default=None, max_length=2000)`; `topic` becomes `str | None = Field(default=None, max_length=2000)` — `None` is allowed only when `plan` is true (clears the plan); otherwise 422.
- `write_topic(..., topic: str | None, plan: bool = False, notes: str | None = None, now: dt.datetime | None = None) -> TopicResult`
  - `plan=True` and `now < start` (Bangladesh): write `topic` and `notes`, bump `topic_version`, status stays `scheduled`.
  - `plan=True` and `now >= start`: raise `ConflictError(code="CLASS_STARTED", message_key="teaching.topic.class_started")` — no write.
  - `plan=False`: existing behaviour (marks `held`), plus writes `notes`.
  - Notes never change status on their own. Version, replay (`client_mutation_id`) and cancelled/inactive refusals unchanged.

- [ ] **Step 1:** Tests (test-first): `test_plan_before_start_keeps_class_scheduled`, `test_plan_after_start_is_refused_and_writes_nothing`, `test_plan_can_be_cleared_to_none_before_start`, `test_covered_write_marks_held_and_stores_notes`, `test_notes_alone_on_a_plan_do_not_mark_held`, `test_none_topic_without_plan_is_422`, `test_replayed_plan_is_idempotent`, `test_start_uses_rescheduled_date_and_time`.
- [ ] **Step 2:** Run; expect FAIL; capture output.
- [ ] **Step 3:** Implement; publish `teaching.topic.class_started` (en "This class has started. Save the topics as covered or discard the plan.", bn equivalent).
- [ ] **Step 4:** Run `pytest tests/teaching tests/contract`; `make openapi`; expect PASS.
- [ ] **Step 5:** Commit `feat(teaching): plan a class's topics before it starts`.

### Task 3: Month view for teachers and families (test-first for family scoping)

**Files:**
- Create: `app/teaching/calendar.py`
- Modify: `app/schemas/teaching.py`, `app/api/teaching.py`, `app/contract/routes.py` (only if lens wiring needs it), `openapi.json`, `message-keys.json`
- Test: `tests/teaching/test_calendar.py`

**Interfaces:**
- `ClassState = Literal["taken", "today", "upcoming", "not_recorded", "cancelled"]` — per class: `cancelled` if status cancelled; else `taken` if `held`; else `today` if date == today; else `upcoming` if date > today; else `not_recorded`.
- `DAY_PRECEDENCE: Final = ("today", "upcoming", "not_recorded", "taken", "cancelled")`; a day's `state` is the first in that order present among its classes.
- `@dataclass(frozen=True) class CalendarClass: session_id, date, start_time, end_time, subject_name, state: ClassState, topic: str | None, notes: str | None, plannable: bool` (`plannable` = server: active batch, not cancelled, now < start), `recordable: bool` (active batch, not cancelled, now >= start), `mark: Literal["present","absent","not_marked","not_enrolled"] | None` (family only; `None` for teacher).
- `@dataclass(frozen=True) class CalendarDay: date, state: ClassState, classes: list[CalendarClass]` (only days with ≥1 class).
- `@dataclass(frozen=True) class MonthView: year, month, first_month: str ("YYYY-MM"), last_month: str, days: list[CalendarDay], served_at`.
  - `first_month` = month of `Batch.created_at` (Bangladesh); `last_month` = current month + 1 (the generation horizon).
- `teacher_month(session, *, lens: TeacherLens, batch_id, year, month, now=None) -> MonthView`
- `family_month(session, *, lens: Lens, enrollment_id, year, month, now=None) -> MonthView` — the child's `mark`: `not_enrolled` when the class date is before the seat's start (`joined_on`, else `created_at` date — the rule `app/fees/generation.py` uses) or on/after `inactive_from`; else from the seat's own `Attendance` row (`present`/`absent`), else `not_marked`. Never another seat's row.
- A month outside `[first_month, last_month]` → `ValidationError(code="MONTH_OUT_OF_RANGE", message_key="teaching.calendar.month_out_of_range")`.
- Routes: `GET /v1/batches/{batch_id}/calendar?year=&month=` (teacher lens), `GET /v1/me/enrollments/{enrollment_id}/calendar?year=&month=` (student lens), `GET /v1/children/{enrollment_id}/calendar?year=&month=` (guardian lens) → `MonthViewResponse`.

- [ ] **Step 1:** Tests (test-first): `test_class_states_follow_status_and_today`, `test_day_state_uses_precedence` (two classes: taken + upcoming same day → upcoming), `test_family_sees_only_own_mark`, `test_child_who_joined_mid_month_sees_not_enrolled_before_join` (Review Focus 3), `test_left_seat_sees_not_enrolled_after_inactive_from`, `test_pending_or_declined_link_is_refused`, `test_other_batch_teacher_is_refused`, `test_month_out_of_range_is_refused` (Review Focus 4), `test_plannable_and_recordable_flip_at_start`, `test_response_has_no_phone_address_or_self_name`.
- [ ] **Step 2:** Run; expect FAIL; capture output.
- [ ] **Step 3:** Implement; publish the new key; regenerate `openapi.json`.
- [ ] **Step 4:** Run `pytest tests/teaching tests/privacy tests/contract`; expect PASS.
- [ ] **Step 5:** Commit `feat(teaching): month calendar for teachers and families`.

### Task 4: The calendar component

**Files:**
- Create: `android/.../core/ui/MonthCalendar.kt`, `android/.../core/network/CalendarDto.kt`
- Test: `android/.../core/ui/MonthCalendarTest.kt`

**Interfaces:**
- DTOs mirroring `MonthViewResponse` (unknown `state` → day dropped, D-26).
- `@Composable fun MonthCalendar(year: Int, month: Int, days: List<CalendarDayUi>, firstMonth: YearMonth, lastMonth: YearMonth, onPickMonth: (YearMonth) -> Unit, onDay: (CalendarDayUi) -> Unit, modifier: Modifier = Modifier)` — Sunday-first grid; per day renders its server `state`: taken ✓ (green tint), today (filled green), upcoming (outline + dot), not_recorded (grey), cancelled (struck); a count marker when `classes.size > 1`; header "Month YYYY ▾" opens a month+year picker limited to `[firstMonth, lastMonth]`; ‹ › arrows disabled at the ends. Labels/content descriptions from strings (en + bn).

- [ ] **Step 1:** Tests: each state renders its tag; count marker for 2 classes; picker offers no month outside range; arrows disabled at range ends; tapping a day calls `onDay` with that day.
- [ ] **Step 2:** Run `./gradlew :android:testDebugUnitTest --tests '*MonthCalendar*'`; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Re-run; expect PASS.
- [ ] **Step 5:** Commit `feat(android): a month calendar component`.

### Task 5: Teacher Classes tab as a calendar, today's class, and planning

**Files:**
- Modify: `feature/batchdetail/ui/ClassesTab.kt`, `feature/batchdetail/BatchDetailViewModel.kt` (or a new `feature/classcalendar/` package for the calendar VM + screens), `feature/record/*`, `core/queue/QueuedWrite.kt` (`plan: Boolean = false`, `notes: String? = null`), `core/network/HttpAttendanceRepository.kt` (topic body carries `plan`, `notes`, nullable `topic`), `navigation/BatchDetailRoute.kt`, `navigation/Destination.kt`, strings
- Create: `feature/classcalendar/ClassDayScreen.kt` (today/past: topics + notes + attendance + Save), `feature/classcalendar/PlanClassScreen.kt` (upcoming: topics + notes + Save; attendance "Opens on the day of the class")
- Test: `feature/classcalendar/*Test.kt`, queue/sync tests

**Interfaces:**
- Day tap: one class → open by its server flags (`recordable` → `ClassDayScreen`, `plannable` → `PlanClassScreen`, neither → read-only detail); several → a list (start time + subject) then the same routing (Review Focus 1).
- `ClassDayScreen` reuses the existing attendance write and topic write through the queue (offline + conflict screen unchanged); Save enqueues the topic write (`plan=false`, with notes) and the attendance write.
- `PlanClassScreen` enqueues a topic write with `plan=true`; a `teaching.topic.class_started` conflict shows on the existing conflict screen with "Save as covered" (re-enqueue `plan=false`) and "Discard plan" (Review Focus 2).
- The old oldest-first session list is removed from the Classes tab; month loads via `GET /v1/batches/{id}/calendar`.

- [ ] **Step 1:** Tests: VM loads the current month then a picked month; tap routing by flags; multi-class list; plan enqueues `plan=true`; class_started conflict offers both actions and each re-enqueues/discards correctly; queued write JSON round-trips `plan`/`notes`; Save on ClassDayScreen enqueues both writes.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Full Android suite + `make android-quality`; expect PASS.
- [ ] **Step 5:** Commit `feat(android): teacher class calendar with today's class and planning`.

### Task 6: Family Classes tab as a calendar

**Files:**
- Modify: `feature/student/ui/FamilyTabs.kt` (Classes tab), `feature/student/StudentBatchViewModel.kt`, `core/network/HttpStudentRepository.kt` (calendar by `FamilyReader`), `feature/student/ui/FamilyDetailScreens.kt` (class detail from the calendar payload), navigation, strings
- Test: family VM, screens, repository tests

**Interfaces:**
- `FamilyReader.SELF` → `/v1/me/enrollments/{id}/calendar`, `GUARDIAN` → `/v1/children/{id}/calendar`.
- Class detail (read-only): topics (or "planned topics" when `state == "upcoming"`), notes, and the child's `mark` label (present / absent / not marked / "Not enrolled then"). No edit controls.

- [ ] **Step 1:** Tests: both readers hit the right path; detail labels each `mark`; upcoming shows planned wording; a 2000-char Bangla topic + notes render without crash and the last line is scrollable to (Review Focus 5); no edit controls present.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Full Android suite + `make android-quality`; expect PASS.
- [ ] **Step 5:** Commit `feat(android): family class calendar`.

### Task 7: Whole-branch verification

- [ ] **Step 1:** `make check PY=<locked python>`; expect exit 0 with the integration suite run.
- [ ] **Step 2:** Device walkthrough for the owner: teacher taps today → records topics, notes, attendance offline then online; plans next week's class; plans offline, goes online after start → sees the conflict; student and guardian open November and October; a guardian of a mid-month joiner sees "Not enrolled then"; a long Bangla topic per screen (the Bangla layout verifier, manual).
- [ ] **Step 3:** Push the branch.
