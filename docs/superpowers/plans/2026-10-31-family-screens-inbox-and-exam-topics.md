# Family Screens, One Inbox and Exam Topics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every update lands in one bell inbox with a detail per item and an app-icon count; families get a tabbed batch screen with a Teacher tab; exams carry topics; payment rejections carry a reason; every inner screen has a back arrow.

**Architecture:** The existing `notification` table (`app/notifications/inbox.py`) becomes the single inbox: each producer fans out one row per recipient inside its own transaction, and each row points at its source (notice, exam, claim) so details load live through the reader's lens. The family batch response grows `teacher` and `exams` blocks. Android adds per-kind detail screens, a tabbed family batch screen reused by student and guardian, and a WorkManager job that polls the unread count every 15 minutes and posts one tray notification.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, pytest + testcontainers; Kotlin, Jetpack Compose, Ktor, Robolectric; new: `androidx.work:work-runtime-ktx`.

**Spec:** `docs/superpowers/specs/2026-10-31-family-screens-inbox-and-exam-topics-design.md`

## Global Constraints

- All `aidlc/spaces/default/memory/` rules apply; the ones below are the ones these tasks touch.
- Every new route resolves a lens or is listed in `LENS_EXEMPT_AUTHENTICATED` with a reason; `tests/contract/test_route_lenses.py` stays green.
- Teacher-lens responses carry no student/guardian `profile` field; family responses never carry `profile.self_name`, a phone or an address of the teacher.
- Server sends message keys, never English; every new user-facing string exists in `values/strings.xml` and `values-bn/strings.xml`; `message-keys.json` regenerated when a key is added.
- Teacher-typed text (notice body, topics, rejection reason) is shown verbatim and never translated.
- Money crosses the API as a JSON string via `app.money.wire.to_wire`.
- Inbox reads are only ever `WHERE account_id = :caller`.
- Migration is `0011`, forward-only; `tests/db/test_migration_head_pin.py` `EXPECTED_HEAD` becomes `"0011"`.
- `openapi.json` regenerated with `make openapi` under the **locked** dependencies (`pip install --require-hashes -r requirements.txt`), never the drifted local install.
- Test-first (red before green) for: inbox recipient fan-out, inbox read isolation, inbox detail authorization.
- Python line length 88 (project override), Sphinx docstrings, type hints; Ruff + mypy clean.
- Android: no business rule in the client; composables render UI state only; new dependency requires `gradle.lockfile` + `gradle/verification-metadata.xml` regenerated and an SDK admission note.
- Bound limits (builder's call, fixed here): topics ≤ 20 lines, each ≤ 120 chars; rejection reason ≤ 500 chars.

## Review Focus

1. A guardian with two children in the same batch must get two inbox items for one notice (one per child, each labelled), not one — owner: Task 3.
2. A teacher who is also a guardian in another teacher's batch must receive family items only for that batch and teacher items only for their own — owner: Task 2.
3. A notice deleted after being read must disappear from the inbox and the unread count must not go negative or stale — owner: Task 3.
4. A tray notification must not repeat for the same unread items every 15 minutes; only a rise in unread since the last check posts again — owner: Task 14.
5. Bangla teacher text (topics, reasons, notices) at maximum length must not break the detail layout — owner: Tasks 10 and 11 (render at max length in the screen test).

---

### Task 1: Schema for inbox sources, exam topics and rejection reasons

**Files:**
- Create: `migrations/versions/0011_inbox_sources_topics_reasons.py`
- Modify: `app/db/models.py` (`Notification`, `Exam`, `PaymentClaim`)
- Modify: `tests/db/test_migration_head_pin.py` (`EXPECTED_HEAD = "0011"`, revision list)
- Test: `tests/db/test_migration_0011.py`

**Interfaces:**
- Produces columns:
  - `notification.source_id UUID NULL` (the notice/exam/claim it points at; no FK, sources live in different tables)
  - `notification.child_name TEXT NULL` (seat display name, set for guardian recipients)
  - `notification.preview TEXT NULL` (first 140 chars of a notice body, or exam title)
  - index `ix_notification_source (kind, source_id)`
  - `exam.topics TEXT[] NOT NULL DEFAULT '{}'`
  - `payment_claim.rejection_reason TEXT NULL`
- `notification.kind` stays `String(32)`.

- [ ] **Step 1:** Write `test_0011_adds_columns_and_defaults_existing_exams_to_no_topics` asserting the three columns exist via `information_schema.columns`, an exam inserted before upgrade reads `topics == []`, and `app` role can `UPDATE notification`.
- [ ] **Step 2:** Run `pytest tests/db/test_migration_0011.py -v`; expect FAIL (no revision 0011).
- [ ] **Step 3:** Write the migration (`revision="0011"`, `down_revision="0010"`) and the model columns; bump `EXPECTED_HEAD`.
- [ ] **Step 4:** Run `pytest tests/db -v`; expect PASS.
- [ ] **Step 5:** Commit `feat(db): add inbox sources, exam topics and rejection reasons`.

### Task 2: Inbox core — recipients, per-item read, live detail (test-first)

**Files:**
- Modify: `app/notifications/inbox.py`
- Create: `app/notifications/recipients.py`
- Test: `tests/notifications/test_inbox_core.py`

**Interfaces:**
- Consumes: Task 1 columns.
- Produces in `app/notifications/inbox.py`:
  - new kind constants: `NOTICE = "notice"`, `EXAM_SCHEDULED = "exam_scheduled"`, `MARKS_AVAILABLE = "marks_available"`, `CLAIM_TO_VERIFY = "claim_to_verify"` (existing `FEE_REMINDER`, `PAYMENT_APPROVED`, `PAYMENT_REJECTED` kept; add `PAYMENT_PARTIAL = "payment_partial"`)
  - `deliver(..., source_id: uuid.UUID | None = None, preview: str | None = None, child_names: dict[uuid.UUID, str] | None = None)` — `child_names` maps a recipient account to the child label stored on its row
  - `InboxItem` gains `source_id`, `child_name`, `preview`
  - `mark_one_read(session, *, account_id, notification_id, now=None) -> None` (no-op for another account's id)
  - `mark_unread_for_source(session, *, kind: str, source_id: uuid.UUID) -> None` (sets `read_at = NULL`, updates `created_at` untouched)
  - `remove_for_source(session, *, kind: str, source_id: uuid.UUID) -> None`
  - `owned_item(session, *, account_id, notification_id) -> InboxItem` raising `AuthorizationError` when absent or not the caller's
- Produces in `app/notifications/recipients.py`:
  - `@dataclass(frozen=True) class Recipient: account_id: uuid.UUID; enrollment_id: uuid.UUID; child_name: str | None`
  - `family_recipients(session, *, batch_id: uuid.UUID, on: dt.date) -> list[Recipient]` — accepted student and accepted guardian of every seat whose `inactive_from` is null or ≥ `on`; guardian rows carry `child_name = seat.display_name`, student rows `None`
  - `seat_recipients(session, *, enrollment_id: uuid.UUID) -> list[Recipient]` — same rule for one seat, ignoring `inactive_from` (payments still reach a seat that has left)
  - `teacher_recipient(session, *, batch_id: uuid.UUID) -> uuid.UUID | None` — `Owner.account_id` of the batch's owner

- [ ] **Step 1: Write the failing tests** in `tests/notifications/test_inbox_core.py` (use `tests.batches.conftest.make_teacher`, `enroll`, `account_factory`):
  - `test_family_recipients_are_accepted_links_only` — seat with student accepted, guardian pending → only the student.
  - `test_guardian_of_two_children_gets_two_recipients` — one guardian on two seats → two `Recipient`s with each child's name.
  - `test_inactive_seat_is_excluded_after_inactive_from` — `inactive_from = on - 1 day` → excluded; `= on` → included.
  - `test_one_account_never_sees_or_marks_another_accounts_item` — `owned_item` on B's id as A raises `AuthorizationError`; `mark_one_read` as A leaves B's row unread.
  - `test_mark_unread_for_source_resets_read` and `test_remove_for_source_deletes_every_recipients_row`.
  - `test_teacher_recipient_is_batch_owner_account`.
- [ ] **Step 2:** Run `pytest tests/notifications/test_inbox_core.py -v`; expect FAIL (imports missing).
- [ ] **Step 3:** Implement the interfaces above. `inbox()` returns the new fields.
- [ ] **Step 4:** Run `pytest tests/notifications tests/fees/test_reminders_in_app.py -v`; expect PASS.
- [ ] **Step 5:** Commit `feat(notifications): recipients, per-item read and source tracking`.

### Task 3: Notices fan out to the inbox

**Files:**
- Modify: `app/teaching/announcements.py` (`post_announcement`, `edit_announcement`, `delete_announcement`)
- Test: `tests/teaching/test_announcement_inbox.py`

**Interfaces:**
- Consumes: `family_recipients`, `deliver`, `mark_unread_for_source`, `remove_for_source`, `NOTICE`.
- Rows: `kind=NOTICE`, `source_id=announcement.id`, `preview=body[:140]`, `batch_name=Batch.name`, `enrollment_id` per recipient.

- [ ] **Step 1:** Tests: `test_posting_a_notice_reaches_every_accepted_family_member`, `test_guardian_with_two_children_gets_one_item_per_child` (Review Focus 1), `test_editing_a_notice_marks_it_unread_again_and_updates_preview`, `test_deleting_a_read_notice_removes_it_and_unread_count_stays_correct` (Review Focus 3), `test_notice_rows_commit_with_the_notice` (a refused post writes no rows).
- [ ] **Step 2:** Run `pytest tests/teaching/test_announcement_inbox.py -v`; expect FAIL.
- [ ] **Step 3:** Call the inbox functions inside each function's existing transaction, before its commit.
- [ ] **Step 4:** Run `pytest tests/teaching -v`; expect PASS.
- [ ] **Step 5:** Commit `feat(teaching): deliver notices to the inbox`.

### Task 4: Payment items — reach the whole seat, carry the reason, tell the teacher

**Files:**
- Modify: `app/fees/verification.py` (`reject_claim` gains `reason: str | None = None`; the decision-delivery helper at ~line 465)
- Modify: `app/fees/claims.py` (`submit_claim` delivers `CLAIM_TO_VERIFY`)
- Modify: `app/schemas/fees.py` (`RejectionRequest.reason: str | None = Field(default=None, max_length=500)`)
- Modify: `app/api/fees.py` (`/claims/{claim_id}/rejection` passes `reason`)
- Test: `tests/fees/test_payment_inbox.py`

**Interfaces:**
- Decisions deliver to `seat_recipients(enrollment_id)` (was: submitter only), `source_id=claim.id`; kind `PAYMENT_APPROVED`, `PAYMENT_PARTIAL` (approved < claimed), or `PAYMENT_REJECTED`.
- A correction (`correcting=True`) calls `remove_for_source` for the claim's earlier decision kinds, then delivers the new one (one item, current outcome).
- `reject_claim` stores `rejection_reason = reason.strip() or None`.
- `submit_claim` delivers `CLAIM_TO_VERIFY` to `teacher_recipient(batch)`, `source_id=claim.id`, `amount=claimed_amount`, `child_name=seat.display_name`.

- [ ] **Step 1:** Tests: `test_rejection_reaches_student_and_accepted_guardian`, `test_rejection_reason_is_stored_verbatim_and_blank_becomes_none`, `test_partial_approval_is_its_own_kind`, `test_correction_replaces_the_earlier_item`, `test_submitting_a_claim_tells_the_batch_teacher_only`, `test_reason_over_500_chars_is_refused_by_the_api`.
- [ ] **Step 2:** Run `pytest tests/fees/test_payment_inbox.py -v`; expect FAIL.
- [ ] **Step 3:** Implement as specified.
- [ ] **Step 4:** Run `pytest tests/fees -v`; expect PASS.
- [ ] **Step 5:** Commit `feat(fees): payment items for the whole seat, rejection reasons, verify alerts`.

### Task 5: Exam topics, and the "exam scheduled" item

**Files:**
- Modify: `app/schemas/marks.py` (`ExamCreateRequest`/`ExamUpdateRequest` gain `topics: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]] = Field(default_factory=list, max_length=20)`; exam response models gain `topics: list[str]`)
- Modify: `app/marks/exams.py` (`create_exam`, `update_exam` take `topics: list[str]`; `read_exam_row`/`list_exams` return them)
- Modify: `app/api/marks.py`
- Test: `tests/marks/test_exam_topics.py`

**Interfaces:**
- `create_exam(..., topics: list[str] = ())` stores order as given; delivers `EXAM_SCHEDULED` to `family_recipients(batch_id, on=date)` with `source_id=exam.id`, `preview=title`.
- `update_exam(..., topics: list[str])` replaces topics; when date, title or topics changed, `mark_unread_for_source(EXAM_SCHEDULED, exam.id)`.

- [ ] **Step 1:** Tests: `test_topics_round_trip_in_order`, `test_no_topics_is_valid`, `test_twenty_one_topics_or_a_121_char_topic_is_refused`, `test_creating_an_exam_delivers_to_family`, `test_editing_topics_marks_the_item_unread`, `test_editing_nothing_leaves_it_read`.
- [ ] **Step 2:** Run `pytest tests/marks/test_exam_topics.py -v`; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `pytest tests/marks -v`; expect PASS.
- [ ] **Step 5:** Commit `feat(marks): exam topics and exam-scheduled inbox items`.

### Task 6: "Marks available" items

**Files:**
- Modify: `app/marks/entry.py` (`record_mark`), `app/marks/views.py` (`set_marksheet_visible`)
- Test: `tests/marks/test_marks_inbox.py`

**Interfaces:**
- `record_mark`: when the batch's `marksheet_visible` is true and this is the seat's **first** live mark for the exam, deliver `MARKS_AVAILABLE` to `seat_recipients(enrollment_id)` with `source_id=exam.id`.
- `set_marksheet_visible(visible=True)` turning false→true: deliver to every seat with a live mark on any exam of the batch that has no `MARKS_AVAILABLE` row for `(account, source_id)` yet.
- A correction of an existing mark delivers nothing.

- [ ] **Step 1:** Tests: `test_first_mark_while_visible_notifies_the_seat`, `test_mark_while_hidden_notifies_nobody`, `test_turning_visibility_on_notifies_marked_seats_once`, `test_correcting_a_mark_does_not_notify_again`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `pytest tests/marks -v`; expect PASS.
- [ ] **Step 5:** Commit `feat(marks): marks-available inbox items`.

### Task 7: Inbox API — every kind, item detail, per-item read

**Files:**
- Modify: `app/api/notifications.py`, `app/schemas/notifications.py`
- Modify: `app/contract/routes.py` (`LENS_EXEMPT_AUTHENTICATED` += the two new routes, with the same justification as the existing two)
- Modify: `openapi.json`, `message-keys.json` (if new keys)
- Test: `tests/notifications/test_inbox_api.py`

**Interfaces:**
- `NotificationResponse` gains `source_id: uuid.UUID | None`, `child_name: str | None`, `preview: str | None`; `kind` Literal = the 8 kinds.
- `GET /v1/me/notifications/{notification_id}` → `NotificationDetailResponse` = `NotificationResponse` + `available: bool` + one of:
  - `notice: {body: str, posted_at: datetime, edited_at: datetime | None}`
  - `exam: {exam_id, title, date, subject_name, total_marks, topics: list[str]}`
  - `payment: {claim_id, period, claimed: Money, approved: Money | None, outcome: Literal["approved","partial","rejected","pending"], reason: str | None}`
  - for `fee_reminder`, `marks_available`, `claim_to_verify`: no extra block (client navigates to the existing screen)
  `available=false` (and no block) when the source is gone or the caller's lens no longer reaches the seat (resolve via `readable_enrollment` for family kinds, the batch-owner lens for `claim_to_verify`).
- `POST /v1/me/notifications/{notification_id}/read` → 204; marks one.
- Opening a detail does **not** mark it read; the client calls the read route.

- [ ] **Step 1:** Tests (test-first): `test_detail_of_another_accounts_item_is_404_shaped_authorization_error`, `test_detail_after_seat_removed_is_unavailable_not_an_error`, `test_notice_detail_carries_current_body_after_edit`, `test_payment_detail_carries_reason`, `test_read_one_marks_only_that_item`, `test_every_stored_kind_is_published` (iterate the 8 constants).
- [ ] **Step 2:** Run `pytest tests/notifications/test_inbox_api.py -v`; expect FAIL.
- [ ] **Step 3:** Implement; then regenerate the contract:
  `make openapi PY=<locked-venv>/bin/python` and read the diff.
- [ ] **Step 4:** Run `pytest tests/notifications tests/contract -v`; expect PASS.
- [ ] **Step 5:** Commit `feat(notifications): inbox detail and per-item read`.

### Task 8: Family batch API — exams with topics, teacher block

**Files:**
- Modify: `app/teaching/announcements.py` (`FamilyBatchView`, `family_batch_view`)
- Modify: `app/schemas/teaching.py` (`FamilyBatchViewResponse`), `app/api/teaching.py`, `app/api/guardian.py` (`/children/{enrollment_id}/teaching` serves the same shape)
- Modify: `openapi.json`
- Test: `tests/teaching/test_family_batch_tabs.py`

**Interfaces:**
- `FamilyBatchView` gains:
  - `teacher: FamilyTeacher` = `display_name: str | None` (from `Batch.teacher_display_name`), `subjects: list[str]` (the batch's subject names, in their stored order)
  - `exams: list[FamilyExam]` = `exam_id, title, date, subject_name, total_marks, topics, state: Literal["upcoming","done"]` where `done` = `date < today` **or** the seat has a live mark; ordered upcoming soonest first, then done newest first
  - `announcements` rows gain `announcement_id` (already on `AnnouncementRow`) in the response
- `upcoming_exam` stays for compatibility.
- `GET /v1/me/enrollments/{enrollment_id}/exams/{exam_id}` and `GET /v1/children/{enrollment_id}/exams/{exam_id}` → `FamilyExam`, lens-checked through the seat, refusing an exam of another batch.

- [ ] **Step 1:** Tests: `test_teacher_block_has_display_name_and_subjects_and_no_phone_or_address` (assert the response JSON has no key containing `phone`/`address`/`self_name`), `test_blank_display_name_is_null`, `test_exams_grouped_upcoming_then_done`, `test_exam_detail_of_another_batch_is_refused`, `test_guardian_route_serves_the_same_shape`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement; regenerate `openapi.json` as in Task 7.
- [ ] **Step 4:** Run `pytest tests/teaching tests/guardians tests/privacy tests/contract -v`; expect PASS.
- [ ] **Step 5:** Commit `feat(teaching): family batch exams, topics and teacher block`.

### Task 9: Back arrows on inner screens

**Files:**
- Modify screens and their routes: `MarksheetScreen`, `ProgressScreen`, `FeeHistory` screen, `SessionsScreen`, `AttendanceScreen`, `ExamListScreen` (each takes `onBack: () -> Unit` passed to its `ScreenScaffold`/`ListScreenScaffold`); routes in `navigation/ShikkhokNavHost.kt` and `navigation/TeachingRoutes.kt` pass `{ navController.popBackStack() }`.
- Test: `android/src/test/kotlin/com/shikkhokplus/app/navigation/BackArrowTest.kt`

- [ ] **Step 1:** Robolectric test per screen: render with a recording `onBack`, click the node with content description `R.string.action_back`, assert called once.
- [ ] **Step 2:** Run `./gradlew :android:testDebugUnitTest --tests '*BackArrowTest*'`; expect FAIL (parameter missing).
- [ ] **Step 3:** Add the parameter and wire the routes.
- [ ] **Step 4:** Re-run; expect PASS.
- [ ] **Step 5:** Commit `fix(android): back arrow on every inner screen`.

### Task 10: Inbox on Android — every kind, detail screens, per-item read

**Files:**
- Modify: `core/network/InboxDto.kt`, `core/network/HttpInboxRepository.kt`, `feature/inbox/InboxUiState.kt`, `InboxMapper.kt`, `InboxViewModel.kt`, `ui/InboxScreen.kt`
- Create: `feature/inbox/InboxDetailViewModel.kt`, `feature/inbox/ui/InboxDetailScreen.kt`
- Modify: `navigation/Destination.kt` (`InboxDetail` = `"inbox/{notificationId}"`), `navigation/StudentRoutes.kt`, `res/values*/strings.xml`
- Test: `feature/inbox/InboxMapperTest.kt`, `InboxDetailViewModelTest.kt`, `InboxDetailScreenTest.kt`

**Interfaces:**
- `InboxRepository` gains `suspend fun detail(id: String): AuthResult<NotificationDetailDto>` and `suspend fun markRead(id: String): AuthResult<Unit>`.
- `InboxKind` = all 8 kinds; an unknown kind maps to null and the row is dropped (forward compatibility, D-26).
- List row shows: kind label, `childName` prefix when present ("Rahim · Physics"), `preview` or amount/period, age, bold when unread.
- Tap: `markRead(id)` then navigate:
  - `NOTICE`, `EXAM_SCHEDULED`, `PAYMENT_*` → `InboxDetail(id)`
  - `MARKS_AVAILABLE` → existing `Marksheet.of(sourceId, enrollmentId, reader)`
  - `FEE_REMINDER` → existing fee history for `enrollmentId`
  - `CLAIM_TO_VERIFY` → existing `Verify` route
- `InboxDetailScreen` renders notice body / exam fields + topics as a bulleted list / payment outcome + reason verbatim; `available=false` renders `R.string.inbox_item_unavailable`. Back arrow pops to the inbox.

- [ ] **Step 1:** Tests: mapper drops an unknown kind; mapper keeps `childName`; detail VM maps `available=false` to `Unavailable`; screen shows a 500-char Bangla reason and 20 × 120-char topics without crash (Review Focus 5); tapping a row calls `markRead` once.
- [ ] **Step 2:** Run the three test classes; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Re-run; expect PASS. Run `MessageKeyCoverageTest`.
- [ ] **Step 5:** Commit `feat(android): one inbox with a detail for every item`.

### Task 11: Family batch screen in tabs, with details and a Teacher tab

**Files:**
- Modify: `core/network/StudentDto.kt` (family view DTO gains `teacher`, `exams`), `feature/student/StudentUiState.kt`, `StudentStateMapper.kt`, `StudentBatchViewModel.kt`, `ui/StudentBatchScreen.kt`
- Create: `feature/student/ui/FamilyTabs.kt` (Classes/Exams/Notices/Teacher tab bodies), `feature/student/ui/FamilyDetailScreens.kt` (`ClassDetailScreen`, `ExamDetailScreen`, `NoticeDetailScreen`)
- Modify: `navigation/Destination.kt` (`FamilyClass`, `FamilyExam`, `FamilyNotice`, plus `ChildBatch` for guardians), `navigation/StudentRoutes.kt`, `navigation/GuardianRoutes.kt`
- Test: `feature/student/StudentStateMapperTest.kt`, `StudentScreensTest.kt`, `FamilyDetailScreensTest.kt`

**Interfaces:**
- `enum class FamilyTab { CLASSES, EXAMS, NOTICES, TEACHER }`; tab state lives in `StudentBatchViewModel` (`select(tab)`), as `BatchDetailViewModel` does.
- `StudentRepository` takes a `reader: FamilyReader` (`SELF` → `/v1/me/batches/{id}/teaching`, `GUARDIAN` → `/v1/children/{id}/teaching`) so one screen serves both; guardian header shows the child's name.
- Detail data: class and notice detail render from the already-loaded view (pass ids, look up in the VM's state); exam detail calls the Task 8 exam route. Done exams open the existing marksheet.
- Teacher tab: initials avatar from `teacher.displayName` (first letters of the first two words), generic person icon and `R.string.family_teacher_unnamed` ("Your teacher") when null, then the subject list.
- Fees row and Pay button remain in the header.

- [ ] **Step 1:** Tests: mapper groups exams by server `state` without comparing dates; Teacher tab shows "Your teacher" for a null name; each tab renders; tapping a past class / notice / upcoming exam invokes the matching navigation callback; detail screens' back arrow invokes `onBack`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement; reuse `ListScreenScaffold` and the teacher tab row pattern from `BatchDetailScreen`.
- [ ] **Step 4:** Re-run the Android suite; expect PASS.
- [ ] **Step 5:** Commit `feat(android): family batch tabs with details and a teacher tab`.

### Task 12: Topics on the teacher's exam form

**Files:**
- Modify: `feature/marks/ui/ExamCreateForm.kt` (`ExamFormValues.topics`, `onCreate` gains `topics: List<String>`), `feature/marks/MarksViewModel.kt`, `core/network/MarksDto.kt`, `core/network/HttpMarksRepository.kt`, `navigation/TeachingRoutes.kt`, strings
- Test: `feature/marks/ExamCreateFormTest.kt`

**Interfaces:**
- Topics field: one multi-line `OutlinedTextField`, one topic per line; the form sends `lines.map(String::trim).filter(String::isNotEmpty)`. Format checks only (≤ 20 lines, ≤ 120 chars per line → inline error `R.string.exam_topics_too_long`); the server has the final say.

- [ ] **Step 1:** Tests: three typed lines with a blank between are sent as three topics; editing pre-fills topics one per line; 21 lines disables submit with the error shown.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Re-run; expect PASS.
- [ ] **Step 5:** Commit `feat(android): topics on the exam form`.

### Task 13: Reason on the teacher's reject action

**Files:**
- Modify: `feature/verify/` reject confirmation UI and ViewModel, `core/network/` fees repository (`reject(claimId, correcting, reason)`), strings
- Test: `feature/verify/VerifyViewModelTest.kt`, verify screen test

**Interfaces:**
- Reject confirmation gains an optional multi-line "Reason" field (≤ 500 chars, counter shown); blank sends `null`.

- [ ] **Step 1:** Tests: typed reason is sent verbatim; blank sends null; 501 chars cannot be typed.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Re-run; expect PASS.
- [ ] **Step 5:** Commit `feat(android): optional reason when rejecting a payment`.

### Task 14: App-icon count — 15-minute check and one tray notification

**Files:**
- Modify: `gradle/libs.versions.toml`, `android/build.gradle.kts` (`implementation(libs.work.runtime.ktx)`), `android/gradle.lockfile`, `gradle/verification-metadata.xml`
- Create: `android/SDK-ADMISSION-workmanager.md` (or the project's existing admission-note location — find it first), `core/notify/UnreadCheckWorker.kt`, `core/notify/UnreadNotifier.kt`, `core/notify/UnreadSchedule.kt`
- Modify: `AndroidManifest.xml` (`POST_NOTIFICATIONS`), `MainActivity.kt` (schedule on sign-in, cancel on sign-out, clear on open, permission request after sign-in), strings
- Test: `core/notify/UnreadNotifierTest.kt`, `UnreadCheckWorkerTest.kt` (WorkManager `TestListenableWorkerBuilder`, needs `androidx.work:work-testing` as `testImplementation`)

**Interfaces:**
- `UnreadSchedule.start(context)` enqueues unique periodic work `"unread-check"`, 15 min, `NetworkType.CONNECTED`, `ExistingPeriodicWorkPolicy.KEEP`; `UnreadSchedule.stop(context)` cancels it and clears the notification.
- `UnreadCheckWorker` reads `GET /v1/me/notifications` with the stored token (no token → `Result.success()` and do nothing), then calls `UnreadNotifier.update(unread)`.
- `UnreadNotifier.update(unread: Int, lastNotified: Int): Int` — posts/updates notification id `1001` on channel `"updates"` with text `R.string.tray_updates` ("%d new updates") and `setNumber(unread)` only when `unread > lastNotified`; cancels it when `unread == 0`; returns the value to persist as `lastNotified` (stored in `SharedPreferences` `"unread"`). Text names no person, batch or amount. Tap opens `MainActivity` with extra `open=inbox`.
- Permission (API 33+) requested once after sign-in; refusal is remembered and not re-asked.

- [ ] **Step 1:** Tests: `update(3, 0)` posts with number 3; `update(3, 3)` posts nothing (Review Focus 4); `update(5, 3)` updates to 5; `update(0, 5)` cancels; worker with no token does nothing; notification text contains no batch name.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Add the dependency, regenerate lockfile and checksums (`./gradlew :android:dependencies --write-locks` and `--write-verification-metadata sha256`), write the admission note (WorkManager: AndroidX, no network of its own, no identifiers), implement.
- [ ] **Step 4:** Re-run the Android suite and `make android-quality`; expect PASS.
- [ ] **Step 5:** Commit `feat(android): unread count on the app icon via a 15-minute check`.

### Task 15: Whole-branch verification

- [ ] **Step 1:** With the locked Python environment active, run `make check`; expect every gate green (integration suite ran, not skipped).
- [ ] **Step 2:** Install the debug build on a device and walk: post a notice as teacher → it appears in the student's and guardian's bell within one check; open it → detail → back to bell; reject a payment with a reason → the family sees the reason; create an exam with topics → family Exams tab and bell show them; each inner screen's back arrow returns to its origin.
- [ ] **Step 3:** Commit any fixes; push the branch and open a PR.
