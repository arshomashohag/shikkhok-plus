# Public Hub H4 (Verified-Guardian Reviews) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Release 3 of the hub, verified-guardian reviews, behind a server-side switch that is off by default:
- a guardian with a real, accepted, attended seat rates a published batch and may add text;
- the platform admin moderates every review and every owner reply before it is public;
- reviews are published in a weekly batch and appear on a batch page only once it holds 3 published reviews;
- the owner replies once per review and may report, but never hide or delete;
- the author edits within 30 days and deletes at any time, totally;
- a child-safety or personal-information report hides a review or reply at once.

**Architecture:**
- **Eligibility.** One SQL statement in `app/reviews/eligibility.py` assesses an account against a batch. It grants a `ReviewerLens`, a `Lens` subtype resolved per batch from the path, as `InvitationLens` is. The tests are written first.
- **Lifecycle and moderation.** Review lifecycle, replies and rating arithmetic live in `app/reviews`. Moderation lives in `app/moderation/reviews.py`, behind the existing admin gate.
- **Two new views.** `hub_public_review` and `hub_public_rating` apply the k-threshold *inside the view*. Public pages read them as `shikkhok_hub_reader`. The teacher API reads the same two views as the application role, so no teacher code path touches the `review` base table.
- **The switch.** `SHIKKHOKPLUS_HUB_REVIEWS` gates every write and every display. It never gates a deletion.

**Tech Stack:**
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, Jinja2, pytest + testcontainers.
- Infra: Terraform (one SSM parameter, the `/hub/*` query allowlist) and CloudFront Functions JS 2.0.
- Clients: web React/TS; Android Kotlin/Compose.

**Spec:** `docs/superpowers/specs/2026-11-14-public-hub-design.md`. Read in particular:
- §6 Reviews, plus the H4 parts of §1, §3 (`review`, `review_reply`, `hub_report`), §4, §7, §8, §9 ("Pull reviews") and §10;
- owner decisions D2, D3, D8 and D9.

The detail behind §6 is in `docs/reviews/2026-11-14-public-hub/team/technical-design.md`:
- §2.1 (`review`, `review_reply`);
- §2.4 eligibility;
- §2.5 "Reviews must not become a D-5 channel";
- §4.1 review routes;
- §4.4 schemas;
- §5.3 privacy tests.

Where it and the spec disagree, the spec wins.

**Built on H3** (`docs/superpowers/plans/2026-11-18-public-hub-h3.md`, on this branch):
- **Public pages:** `render.page` with the view registry, and the canary harness (`tests/privacy/canary.py`).
- **Takedowns:** the `cdn_invalidation` outbox, with `invalidation.owner_paths`.
- **Moderation:** `app/moderation/reports.py`, with `file`, `queue` and `decide`, plus `HOLD_REASONS`, and the media hold/settle pattern in `app/moderation/media.py`.
- **Report kinds:** `review` and `reply` are already in `HUB_REPORT_TARGET_VALUES`.
- **Clients:** the web `HubReport` screen and the Android App Link.
- **Rulings R1–R13:** see `.superpowers/sdd/2026-11-18-public-hub-h3/progress.md`.

**Owner gates that this plan does not discharge (human steps, recorded in Task 13's runbook):**
- **D9:** reviews are switched on only after the day-90 bar in spec §9 is met.
- **D8:** the local legal review of the review policy precedes switching on.
- **D6:** the updated Data Safety form and Families declaration are published before switching on.

The switch is how the code waits for all three.

## Calls made in this plan

These are not owner decisions; correct any before execution.

1. **The switch.**
   - **Setting:** env `SHIKKHOKPLUS_HUB_REVIEWS`. It is on only for the exact value `on`, so any other value, or none, is off and the switch fails closed.
   - **Source:** Terraform creates SSM `/shikkhokplus/shikkhokplus-<env>/hub-reviews` with value `off` and `ignore_changes = [value]`. A person flips it, and the next deploy writes it into the runtime env.
   - **Routes:** every route is always registered, so the route, privacy and OpenAPI gates see one fixed surface in every environment. Gated routes answer a documented disabled response.
   - **Why:** D9 and D8 make reviews conditional on evidence that does not exist yet, so the code must ship dark.
2. **Two statuses the spec's §3 list lacks:**
   - `approved` means a moderator approved the review and it waits for the weekly publication.
   - `held` means a report took it down pending a decision. This is H3 deviation 2, applied to reviews.

   Review statuses are `pending, approved, published, rejected, removed, held`. Reply statuses are `pending, published, rejected, removed, held`.
3. **Replies are pre-moderated.** The spec is silent on this. A reply is the one owner-written text addressed to a specific family's review, so it is the likeliest place for a child's name to appear (Forbidden: no student name on a public surface). A reply publishes on approval, with no weekly batch, because its timing points at no seat.
4. **Weekly publication.** A daily job publishes every `approved` review whose `approved_at` is before the most recent **Friday 00:00 Asia/Dhaka**. The spec says "weekly"; Friday is the Bangladeshi weekend. Running daily makes the job self-healing (a missed run publishes on the next one) under the default 48-hour freshness threshold.
5. **The k-threshold is enforced in the views, not in Python.**
   - `hub_public_review` holds no row for a batch with fewer than 3 published reviews.
   - `hub_public_rating` gives the count always, and gives the average and distribution only at 3 or more.

   So no caller, teacher API included, can read below-threshold text.
6. **The teacher reads through the views as the application role.** The migration grants `SELECT` on the two views to `shikkhok_app` as well as to the hub reader. The app role already reads the base tables, so the grant adds no reach, and it avoids a `SET LOCAL ROLE` inside a write transaction. A source gate asserts that `app/reviews/owner.py` never names the `review` base table.
7. **The author's lens survives losing eligibility.**
   - **Grant:** `ReviewerLens` is granted when the account is a member (spec conditions 1–3), *or* when it authored a review of the batch. Otherwise "delete at any time" would break the moment a seat was declined or a listing unpublished.
   - **Writing:** creating a review needs full eligibility. An edit needs membership plus the 30-day window.
8. **The edit window** runs 30 days from the first `submitted_at`. It is not reset by edits.
9. **`client_mutation_id` is dropped** from the spec's PUT body. PUT replaces the review, so a replay with identical rating and body is a no-op that consumes no allowance and does not re-moderate.
10. **No review pagination; the newest 50 are shown.**
    - The technical design's `?rpage=` would widen the verbatim six-key edge allowlist and the invalidation shapes for a list that numbers in the tens.
    - Order is `published_month DESC, id`. Ids are random, so order within a month says nothing about submission order.
11. **Sort by rating ships as one new query key, `sort`, with the value `rating`.** The edge allowlist becomes seven keys.
    - The score is the spec's Bayesian score (prior 3.5, weight 5), at owner level, over batches that meet the threshold only.
    - When the switch is off, `sort` is ignored and not offered.
12. **Owner-card rating** aggregates only batches that meet the threshold, and is absent when none does. Folding a below-threshold batch into an owner average would leak its rating through the ordering.
13. **No `aggregateRating` in the JSON-LD.** Review-snippet policy questions are out of scope for V1.
14. **The admin's author reference is a new, domain-separated hash** (`shikkhokplus/hub-review-author/v1:`), not `requester_ref`. A shared reference would let the admin join a review to that account's help tickets, where a teacher-guardian's name is shown (D4: never with a name).
15. **Deletion is total for content.**
    - Deleting a review (by its author, by account deletion, or with a solo owner's listing) also deletes its reply and every `hub_report` row targeting the review or the reply.
    - `hub_moderation_event` rows stay. They are ids and closed codes, `NOT_PERSONAL`, kept 12 months.
16. **Notifications are limited to:**
    - **`hub_review_outcome`**, to the author, when their review is published, rejected or removed;
    - **`hub_reviews_published`**, to the owner, when a weekly run published reviews on a batch that is at or above the threshold.

    These are not built: "you are now eligible" (it needs a daily scan; the reviewable list serves it) and reply notifications. Neither is in spec §6.
17. **The "Pull reviews" measure** (spec §9) is three admin-overview figures over a trailing 91 days:
    - `hub_reviews_public` (published, held or removed);
    - `hub_reviews_reported` (distinct ones with a report in the window);
    - `hub_reviews_pull_bar`, which is true when `reported * 100 > public * 5`.

    All are computed in SQL.
18. **Inactive beyond 180 days** answers `REVIEW_NOT_YET_ELIGIBLE` with the message key `hub.review.window_closed`, following technical design §2.4: the seat was real. One code covers three message keys, so the client renders the reason without interpreting a detail.
19. **Migration numbers:**
    - `0045` adds the tables and views.
    - `0046` adds the moderation event labels, which need an autocommit block, as `0044` did.

## Global Constraints

- **The switch (verbatim):**
  - **Setting:** `SHIKKHOKPLUS_HUB_REVIEWS`, read at each call by `app.hub.public.settings.reviews_enabled() -> bool`. It is true only for the exact string `on`; unset, `ON`, `true`, `1` and ` on` are all off.
  - **Disabled response:** HTTP 404, `AuthorizationError(code="HUB_REVIEWS_OFF", message_key="hub.review.off", status=404)`. Every gated route documents it in its OpenAPI `responses`.
  - **The off behaviour:**

  | Surface | When off |
  |---|---|
  | `PUT …/my-review`, `GET /v1/hub/reviews`, `PUT …/reply`, admin review detail and decision, `GET /v1/admin/hub/queue?kind=review` | `HUB_REVIEWS_OFF` |
  | `GET /v1/hub/reviewable` | 200, listing only batches the caller already reviewed |
  | `GET …/my-review` | 200, with `can_write = false` |
  | `DELETE …/my-review`, `DELETE …/reply`, account deletion | Work unchanged. **The switch never gates a deletion.** |
  | Public pages | No review section, no rating on any card, no review or reply report link; `sort` ignored and not rendered |
  | `POST /v1/hub/reports` with `target_kind` `review` or `reply` | The existing identical `REPORT_TARGET_NOT_FOUND` |
  | Weekly publication job | Publishes nothing and sends nothing; still stamps its heartbeat |

  - **Ordering:** the switch dependency runs before the lens is resolved, so an off switch answers `HUB_REVIEWS_OFF` and never `NOT_AVAILABLE`.
- **Eligibility (verbatim from spec §6).** `today` is `bangladesh_today()`. Conditions 1–3 define membership; failing any one answers `NOT_AVAILABLE` (403), identical for a non-member and a nonexistent batch:
  1. `enrollment.guardian_account_id = :account` and `guardian_decision = 'accepted'`. V1 is guardian-only; a student link never qualifies.
  2. `guardian_relink_blocked_at IS NULL`.
  3. The batch is public: `batch_listing.status = 'published'`, `batch.active`, and `owner_listing.status = 'published'`.

  Conditions 4–6 apply to a member:
  4. **Tenure:** `COALESCE(joined_on, (created_at AT TIME ZONE 'Asia/Dhaka')::date) <= today - 30`. Day 30 qualifies; day 29 does not.
  5. **Attendance:** at least 4 distinct `session` rows of that batch, with `status <> 'cancelled'`, that have an `attendance` row for this enrollment with `present = true`.
  6. **Recency:** `inactive_from IS NULL` or `inactive_from >= today - 180`. 180 days qualifies; 181 does not.

  A member failing 4–6 gets 409 `REVIEW_NOT_YET_ELIGIBLE`, with one message key per reason:
  - `hub.review.not_yet_eligible`, with `details={"eligible_from": ISO date}`, when tenure alone is unmet;
  - `hub.review.needs_attendance`, when attendance is unmet;
  - `hub.review.window_closed`, when recency is unmet.

  Several enrollments of one guardian in one batch (siblings) count as one: the account is eligible if any enrollment is, and the evidence is the eligible enrollment with the earliest join date.
- **Tenure bucket**, frozen at first submit, measured from the evidence enrollment's join date `j`:
  - `lt_6m` when `j + 6 months > today`;
  - `6_12m` when `j + 12 months > today`;
  - `gt_1y` otherwise.
- **Content:**
  - **Rating:** an integer 1–5.
  - **Review body:** optional; after `strip()`, at most 1000 characters. An empty body is stored as NULL.
  - **Reply body:** 1–1000 characters after `strip()`; one reply per review.
  - **Contact refusal:** text is refused with 400 `REVIEW_CONTAINS_CONTACT` (`hub.review.contains_contact`, `details={"field": …}`) when either:
    - `app.accounts.phone.contains_phone` finds a number (it already normalises Bangla digits and separators);
    - `app.reviews.content.contains_url` matches `(?i)\b(?:https?://|www\.)` or a host `\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|info|biz|bd|io|me|co|app|link|xyz|online|site|page)\b`.
- **Display (verbatim):**
  - **Threshold:** `REVIEW_THRESHOLD = 3`.
  - **Labels:**
    - EN: "Verified guardian · enrolled under 6 months" / "Verified guardian · enrolled 6–12 months" / "Verified guardian · enrolled over 1 year".
    - BN: "যাচাইকৃত অভিভাবক · 6 মাসের কম সময় ধরে ভর্তি" / "যাচাইকৃত অভিভাবক · 6–12 মাস ধরে ভর্তি" / "যাচাইকৃত অভিভাবক · 1 বছরের বেশি সময় ধরে ভর্তি".
  - **What is never shown:** a name, an initial, a class or a day.
  - **Dates:** month and year only, e.g. "Nov 2026" / "নভেম্বর 2026" (Latin digits).
  - **Volume:** at most 50 reviews on a page, newest month first.
- **Arithmetic, all in SQL, with no float and no Python `decimal`:**
  - **Average:** `average_tenths = round(10 * sum(rating)::numeric / count(*))::int`, so 43 means 4.3.
  - **Bayesian score:** `score_milli = round((17500 + 1000 * sum)::numeric / (5 + count))::int`; an owner with no qualifying reviews scores 3500.
  - **Display:** tenths are rendered as `f"{t // 10}.{t % 10}"`.
- **Edit window:** 30 days from `submitted_at`. After it, 409 `REVIEW_EDIT_CLOSED` (`hub.review.edit_closed`). An edit returns the review to `pending` and clears `approved_at` and `published_month`.
- **Ceilings:**
  - **Review writes:** `ScopeKind.HUB_REVIEW_DAILY = "hub_review_day"`, `HUB_REVIEW_ACCOUNT_DAILY = 5`. A breach is 409 `HUB_REVIEW_CEILING` (`hub.review.ceiling`). Only a PUT that changes something consumes one.
  - **Replies:** consume the existing `HUB_LISTING_OWNER_DAILY`. A reply on a suspended owner listing is refused with `HUB_LISTING_SUSPENDED` (H3 R8).
- **New error codes:**

  | Code | Status | Class | Message key(s) |
  |---|---|---|---|
  | `HUB_REVIEWS_OFF` | 404 | `AuthorizationError` | `hub.review.off` |
  | `REVIEW_NOT_YET_ELIGIBLE` | 409 | `ConflictError` | `hub.review.not_yet_eligible`, `hub.review.needs_attendance`, `hub.review.window_closed` |
  | `REVIEW_CONTAINS_CONTACT` | 400 | `ValidationError` | `hub.review.contains_contact` |
  | `REVIEW_EDIT_CLOSED` | 409 | `ConflictError` | `hub.review.edit_closed` |
  | `HUB_REVIEW_CEILING` | 409 | `CeilingBreach` | `hub.review.ceiling` |
  | `REVIEW_NOT_FOUND` | 404 | `AuthorizationError` | `hub.review.not_found` |
  | `REVIEW_ALREADY_DECIDED` | 409 | `ConflictError` | `hub.review.already_decided` |
  | `REVIEW_CODE_INVALID` | 400 | `ValidationError` | `hub.review.code_invalid` |

  A non-member reuses the registered `NOT_AVAILABLE` (403, `authz.lens.not_available`).
- **Route counts:**
  - `PUBLIC_ROUTES` stays **19**, and `PUBLIC_CACHEABLE_ROUTES` stays the same **4**.
  - `LENS_EXEMPT_AUTHENTICATED` gains exactly `("GET", "/v1/hub/reviewable")`.
  - A new asserted `REVIEWER_ROUTES` holds exactly the three `/v1/hub/batches/{batch_id}/my-review` methods.
  - Three new `TeacherLens` routes.
  - `PLATFORM_ADMIN_ROUTES` goes 12 → **14**.
- **Public data sources:** public handlers read only these seven views, under `as_hub_reader`:
  - `hub_public_owner`, `hub_public_batch`, `hub_public_teacher_name`, `hub_public_area`, `hub_public_media`;
  - `hub_public_review` and `hub_public_rating` (new).

  The hub reader cannot `SELECT` `review` or `review_reply`. `app.reviews` is never imported by `app/hub/public/**`; the existing allowlist gate enforces it.
- **Never in any response, page or admin view:**
  - `author_account_id`, `account_id` or `enrollment_id`;
  - `submitted_at`, `approved_at`, `edited_at`, `decided_at`;
  - `display_name`, or any phone.

  The admin sees `author_ref` (Call 14) and `author_role` only.
- **Moderation timetable (D7) is human:** 48 h for reviews and replies, 24 h for child-safety. The queue orders oldest first and shows `waited_hours`; nothing automates the deadline.
- **Carried from H3:**
  - **Backend gate:** every task runs `python -m ruff check app tests`, `python -m ruff format --check app tests`, `python -m mypy app` and its pytest directories, plus `tests/contract` whenever a migration, `DISPOSITIONS`, a route or a schema changes.
  - **Restricted role:** integration tests connect as the restricted non-superuser role (`restricted_session`).
  - **Test-first:** every authorization-predicate case is written first: eligibility, lens grants, teacher scoping, view visibility, the k-threshold.
  - **Migrations:** head pins move in all four files: `tests/db/test_migration_head_pin.py`, `test_migration_from_head.py`, `test_migration_runs.py` and `tests/auth/test_endpoints.py`.
  - **Generated files are regenerated, never hand-edited:**
    - `openapi.json` via `make openapi`;
    - `web/src/api/schema.d.ts` via `cd web && npm run gen:api`;
    - `web/src/i18n/generated/*` via `cd web && node scripts/sync-strings.mjs`;
    - `docs/legal/PRIVACY.md` via `python3 -m scripts.generate_privacy_policy`.
  - **Strings:** new strings start in Android `values/` and `values-bn/`, plus `message-keys.json` and `MessageKeys.kt`. Public-page strings go in `app/hub/public/messages.py`. Copy is EN and BN, with Latin digits.
  - **Android routes:** every new Android action is wired through its navigation route and proven by a route-level test.
  - **Edge functions:** the CloudFront Functions JS 2.0 runtime has no `Array.from`, no `for…of` and no spread; use `indexOf` and index loops.
  - **Counts:** a comment that states a count is asserted by a test.
  - **Bangla layout:** every new screen gets a row in `docs/delivery/bangla-layout-check.md`, a human check.
  - **Commits:** conventional, ending with the `Co-Authored-By` trailer.

## Review Focus

1. **A guardian with two children in one batch**, one eligible and one not:
   - one review is allowed, with the eligible seat as evidence;
   - two devices submitting a first review at once leave exactly one row.

   Tests: Task 3 `test_siblings_one_eligible_grants_with_that_enrollment`; Task 4 `test_concurrent_first_writes_make_one_review`.
2. **A batch drops from 3 published reviews to 2** (one removed, held, edited back to pending, or deleted):
   - text, average and distribution vanish from the batch page, the owner card, the teacher API and the sort score;
   - an invalidation is enqueued in the same transaction.

   Tests: Task 2 `test_threshold_is_enforced_by_the_views`; Task 9 `test_drop_below_threshold_hides_everything_public`; Task 5 `test_teacher_sees_nothing_below_threshold`.
3. **Contact smuggled into text**, which must be refused:
   - Bangla digits `০১৭১২৩৪৫৬৭৮`, `017 1234 5678`, `+880-17…`;
   - `www.example.com`, `example.com.bd/x`, `fb.com/page`.

   Ordinary text must pass: "Class 10, 2024 batch, GPA 4.5", "Tk 1500 a month", "4.30 pm".

   Test: Task 4 `test_contact_refusal_cases` (parametrised, both ways).
4. **An author deletes a review that is held, pending, reported and replied to:**
   - the row, its reply and every report on either are gone;
   - an invalidation is enqueued if it was visible;
   - the admin queue no longer lists it;
   - all of this also works with the switch off.

   Test: Task 4 `test_delete_is_total`.
5. **The switch is turned off with published reviews in the database:**
   - no public page shows a review, rating, report link or sort choice;
   - the teacher API answers `HUB_REVIEWS_OFF`;
   - the author can still read and delete;
   - the job publishes nothing.

   Tests: Task 9 `test_switch_off_hides_reviews_on_every_public_page`; Task 6 `test_gated_routes_answer_reviews_off_and_deletes_still_work`; Task 8 `test_off_publishes_nothing_but_stamps_heartbeat`.

---

### Task 1: The reviews switch

**Files:**
- Create: `app/reviews/__init__.py`, `app/reviews/switch.py`
- Modify:
  - `app/hub/public/settings.py`: `HUB_REVIEWS_ENV = "SHIKKHOKPLUS_HUB_REVIEWS"` and `reviews_enabled()`.
  - `message-keys.json`, `android/src/main/res/values{,-bn}/strings.xml` and `android/.../feature/auth/MessageKeys.kt`: add `hub.review.off`. Then run `cd web && node scripts/sync-strings.mjs`.
  - `docker-compose.yml`: `SHIKKHOKPLUS_HUB_REVIEWS: ${SHIKKHOKPLUS_HUB_REVIEWS:-off}`.
  - `deploy/docker-compose.staging.yml`: `SHIKKHOKPLUS_HUB_REVIEWS: ${SHIKKHOKPLUS_HUB_REVIEWS:-off}`.
  - `infra/modules/app/deployment_state.tf`: `aws_ssm_parameter.hub_reviews`, named `/shikkhokplus/shikkhokplus-${var.environment}/hub-reviews`, type `String`, value `"off"`, `lifecycle { ignore_changes = [value] }`.
  - `.github/workflows/deploy.yml`:
    - read `HUB_REVIEWS=$(ses_param hub-reviews)`;
    - stop the release unless the value matches `^(on|off)$`, with the same "Nothing has been recorded or rolled" wording;
    - `echo "SHIKKHOKPLUS_HUB_REVIEWS=${HUB_REVIEWS}"` into `runtime.env`.
  - `infra/README.md`: a "Switching reviews on" runbook (Task 13 completes the checklist).
- Test: `tests/reviews/__init__.py`, `tests/reviews/conftest.py`, `tests/reviews/test_switch.py`, `tests/gates/test_hub_reviews_switch_infra.py`

**Interfaces:**
- Produces:
  - `app.hub.public.settings.reviews_enabled() -> bool`.
  - `app.reviews.switch.reviews_off() -> AuthorizationError` (the verbatim disabled response).
  - `app.reviews.switch.require_reviews_on() -> None`, a FastAPI dependency that raises `reviews_off()` when off.
  - `app.reviews.switch.REVIEWS_OFF_RESPONSES: dict[int | str, dict[str, Any]]`: the 404 `ErrorEnvelope` entry, described "Reviews are switched off (HUB_REVIEWS_OFF)". Every gated route merges it into `responses=`.
  - The pytest fixture `reviews_on` in `tests/reviews/conftest.py` (monkeypatch setenv `on`). It is also re-exported for `tests/hub`, `tests/moderation` and `tests/privacy` through their conftests.

- [ ] **Step 1: Write the failing tests:**
  - `test_off_when_unset`.
  - `test_on_only_for_exact_value`, parametrised `on` → True; `ON`, `On`, `true`, `1`, ` on`, `on `, `yes` and the empty string → False.
  - `test_read_at_each_call` (set, unset, set again within one process).
  - `test_require_reviews_on_raises_documented_error` (code, status 404, message key).
  - `test_message_key_published` (it is in `message-keys.json` and both Android bundles).
  - Gates:
    - `test_ssm_switch_parameter_defaults_off_and_ignores_value`;
    - `test_deploy_validates_switch_value_and_writes_it`;
    - `test_both_compose_files_forward_switch_defaulting_off`.
- [ ] **Step 2: Run** `pytest tests/reviews/test_switch.py tests/gates/test_hub_reviews_switch_infra.py tests/gates/test_compose_forwards_runtime_env.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Run `terraform fmt -check -recursive infra`, then `validate` through the scratch provider mirror.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/reviews tests/gates tests/contract`) and `cd web && npm run check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(reviews): server-side reviews switch, off by default`.

### Task 2: Review data, the two public views and dispositions (0045)

**Files:**
- Create: `migrations/versions/0045_hub_reviews.py`
- Modify:
  - `app/db/models.py`: `Review`, `ReviewReply`, `HUB_REVIEW_STATUS_VALUES`, `HUB_REPLY_STATUS_VALUES`, `HUB_REVIEW_AUTHOR_ROLE_VALUES`, `HUB_REVIEW_TENURE_VALUES`.
  - `app/governance/dispositions.py`, `app/governance/deletion.py` (`HARD_DELETE_SCOPES`) and the head pins.
  - `tests/privacy/test_hub_public_views.py`: rename to `test_hub_reader_reads_only_the_seven_views`, and extend the private-column check.
  - `tests/privacy/test_hub_reader_meta.py`: add `review` and `review_reply` to the refused list.
- Test: `tests/db/test_migration_0045.py`, `tests/privacy/test_hub_public_review_view.py`

**Interfaces:**
- Produces:
  - **`review`:**
    - **Keys and links:** `id UUID PK`; `batch_id FK batch_listing(batch_id) ON DELETE CASCADE`; `author_account_id FK account ON DELETE CASCADE`; `enrollment_id FK enrollment ON DELETE SET NULL NULL`.
    - **Content:** `author_role hub_review_author_role NOT NULL` (with CHECK `= 'guardian'` in V1); `rating SMALLINT CHECK 1..5`; `body TEXT NULL CHECK char_length <= 1000`.
    - **State:** `status hub_review_status NOT NULL DEFAULT 'pending'`; `tenure_bucket hub_review_tenure NOT NULL`; `rejection_code VARCHAR(32) NULL`.
    - **Times:** `submitted_at`, `edited_at NULL`, `approved_at NULL`, `published_month DATE NULL`, `decided_at NULL`, `decided_by_account_id FK account SET NULL`.
    - **Constraints:**
      - UNIQUE `uq_review_batch_author (batch_id, author_account_id)`;
      - CHECK `(status = 'published' OR status = 'held') = (published_month IS NOT NULL)`;
      - CHECK `published_month IS NULL OR extract(day FROM published_month) = 1`;
      - CHECK `status NOT IN ('rejected','removed') OR rejection_code IS NOT NULL`;
      - CHECK `(status = 'approved') = (approved_at IS NOT NULL)`;
      - a partial index `(batch_id) WHERE status = 'published'`.
  - **`review_reply`:**
    - **Columns:** `review_id PK FK review ON DELETE CASCADE`; `body TEXT NOT NULL CHECK 1..1000`; `status hub_reply_status NOT NULL DEFAULT 'pending'`; `written_by_account_id FK account SET NULL`; `created_at`, `edited_at NULL`, `published_month DATE NULL`, `decided_at NULL`, `decided_by_account_id FK account SET NULL`, `rejection_code VARCHAR(32) NULL`.
    - **Constraint:** the same published-month and rejection CHECKs as `review`.
  - **`hub_public_rating`** (`security_barrier`): one row per batch visible in `hub_public_batch` with at least one published review.
    - **Columns:** `batch_id`, `review_count int`, and three that are NULL below 3: `average_tenths int`, `rating_sum int` and `distribution int[]` (five counts, 1★ to 5★).
  - **`hub_public_review`** (`security_barrier`): published reviews joined to `hub_public_rating` with `review_count >= 3`.
    - **Columns:** `id`, `batch_id`, `rating`, `body`, `tenure_bucket`, `author_role`, `published_month`, `reply_body` and `reply_month`. The two reply columns are filled only when the reply's status is `published`.
  - **Grants:** both views get `SELECT` to `shikkhok_hub_reader` and to `shikkhok_app` (Call 6). `shikkhok_app` also gets CRUD on both tables.
  - **Dispositions:**
    - `review`: `HARD_DELETE`, `LIFE_OF_ACCOUNT`, scope `ACCOUNT_COLUMN` on `author_account_id`. The basis says it is also deleted with the teacher's listing.
    - `review_reply`: `HARD_DELETE`, `LIFE_OF_ACCOUNT`, `VIA_CASCADE`. A centre's reply survives a manager's deletion with `written_by_account_id` cleared.

- [ ] **Step 1: Write the failing tests (test-first: view visibility is the authorization boundary).**
  - `test_0045_creates_tables_enums_and_views` (enum labels exact, in order).
  - `test_published_month_iff_published_or_held`, `test_rejection_needs_code`, `test_one_review_per_author_per_batch`.
  - `test_threshold_is_enforced_by_the_views` (Review Focus 2). With 2 published reviews:
    - `hub_public_review` has no row for the batch;
    - `hub_public_rating` has `review_count = 2` and NULL average and distribution.

    At 3 published, all appear. Pending, approved, held, rejected and removed reviews count toward nothing.
  - `test_views_hide_reviews_of_invisible_batches`, parametrised over owner draft, batch draft or hidden, inactive batch and suspended owner.
  - `test_unpublished_reply_is_not_exposed`.
  - `test_average_tenths_cases`, parametrised: `[5,4,4]→43`, `[5,4,4,4]→43` (half-up), `[1,2,2]→17`, `[5,5,5]→50`, `[1,1,1]→10`, `[4,4,5,5]→45`; the distribution of `[5,4,4]` is `[0,0,0,2,1]`.
  - `test_review_views_never_depend_on_identity_columns`. Via `pg_depend`, no dependency on `review.author_account_id`, `review.enrollment_id`, `review.submitted_at`, `review.edited_at`, `review.approved_at`, `review.decided_by_account_id` or `review_reply.written_by_account_id`.
  - `test_hub_reader_reads_only_the_seven_views` and `test_hub_reader_cannot_read_private_tables[review|review_reply]`.
  - `test_review_dispositions`.
- [ ] **Step 2: Run** `pytest tests/db/test_migration_0045.py tests/privacy -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - The migration uses 0043's `CREATE VIEW … WITH (security_barrier)` and grant pattern, with `REVIEW_THRESHOLD = 3` as a module constant interpolated into both views.
  - The downgrade refuses while any `review` row exists.
  - Add the models, dispositions and scopes, and move the head pins.
  - Then run `python3 -m scripts.generate_privacy_policy`.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/db tests/privacy tests/governance tests/contract`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(reviews): review tables and threshold-enforcing public views (0045)`.

### Task 3: Eligibility and the ReviewerLens (test-first)

**Files:**
- Create: `app/reviews/eligibility.py`, `app/reviews/lens.py`
- Modify:
  - `app/api/deps.py`: `reviewer_lens`.
  - `tests/named_tests.toml`: one entry per boundary test below, each with its criterion and the rule `spec §6`.
- Test: `tests/reviews/test_eligibility.py`, `tests/reviews/test_reviewer_lens.py`

**Interfaces:**
- Produces:
  - `Standing = Literal["eligible", "not_yet", "closed", "author_only"]` and `Tenure = Literal["lt_6m", "6_12m", "gt_1y"]`.
  - **`Assessment`** (a frozen dataclass): `batch_id`, `batch_title: str` (`batch_listing.public_title`, never `batch.name`), `owner_public_name: str`, `enrollment_id: UUID | None`, `review_id: UUID | None`, `standing: Standing`, `waiting_on: Literal["tenure", "attendance"] | None`, `eligible_from: date | None` (set only when tenure alone is unmet), `tenure: Tenure | None`.
  - **`ELIGIBILITY_QUERY`:** **one statement** with `:account_id`, `:today` and `:batch_id`, where a NULL batch means all batches.
    - It computes the six conditions per enrollment, then one row per batch: the eligible enrollment with the earliest join date first, else the earliest.
    - It UNIONs batches where the account has a review but is not a member (`author_only`).
  - `assess(session, account_id, batch_id, today) -> Assessment | None` returns None for a non-member with no review.
  - `reviewable(session, account_id, today, *, open_only: bool) -> list[Assessment]`:
    - **Rows:** standings `eligible`, `not_yet` and every row with a `review_id`, ordered by `batch_title`. `closed` rows without a review are omitted.
    - **Switch off:** `open_only=False` restricts the list to rows with `review_id`.
  - **`ReviewerLens(Lens)`** in `app/reviews/lens.py`: `batch_id: UUID` and `assessment: Assessment`.
  - **`app.api.deps.reviewer_lens(batch_id, session, account_id) -> ReviewerLens`:**
    - not memoised;
    - raises `AuthorizationError(code=NOT_AVAILABLE, message_key="authz.lens.not_available")` when `assess` returns None.

- [ ] **Step 1: Write the failing tests, before any implementation** (team predicate: a wrong answer is an authorization error). Each builds its world through `tests/hub/support.py` helpers, as the restricted role:
  - Tenure:
    - `test_day_29_not_yet_with_eligible_from` (`eligible_from = joined + 30`);
    - `test_day_30_eligible`;
    - `test_joined_on_null_uses_created_at_in_dhaka` (a `created_at` of 20:00 UTC counts as the next Dhaka day).
  - Attendance:
    - `test_three_attended_not_yet_attendance`;
    - `test_four_attended_eligible`;
    - `test_absent_and_cancelled_sessions_do_not_count`;
    - `test_attendance_in_another_batch_does_not_count`.
  - Recency:
    - `test_inactive_180_days_eligible`;
    - `test_inactive_181_days_closed`.
  - Membership:
    - `test_pending_declined_or_blocked_guardian_is_not_member` (three cases → None);
    - `test_student_link_is_not_member`;
    - `test_invisible_batch_is_not_member`, parametrised over batch draft, hidden, suspended owner, owner draft and inactive batch.
  - Several seats and authors:
    - `test_siblings_one_eligible_grants_with_that_enrollment` (Review Focus 1);
    - `test_author_keeps_lens_after_losing_membership` (`author_only`).
  - Tenure buckets:
    - `test_tenure_buckets_at_boundaries` (`today = j + 6 months - 1 day → lt_6m`, `today = j + 6 months → 6_12m`, `today = j + 12 months - 1 day → 6_12m`, `today = j + 12 months → gt_1y`).
  - The list and the lens:
    - `test_reviewable_lists_open_and_reviewed_omits_closed`;
    - `test_reviewable_off_lists_only_reviewed`;
    - `test_reviewer_lens_refusal_is_identical_for_nonmember_and_missing_batch` (the same status and body bytes).
- [ ] **Step 2: Run** `pytest tests/reviews/test_eligibility.py tests/reviews/test_reviewer_lens.py -q`. Expected: FAIL. Keep the RED output for the reviewer.
- [ ] **Step 3: Implement** the statement in SQL. No Python loop may decide eligibility.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/reviews tests/contract`, and `pytest tests/test_named_test_manifest.py`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(reviews): one-statement eligibility and the ReviewerLens`.

### Task 4: Author lifecycle — write, edit, delete, contact refusal

**Files:**
- Create:
  - `app/reviews/content.py`;
  - `app/reviews/authoring.py`;
  - `app/reviews/forget.py`;
  - `app/reviews/identity.py` (`review_author_ref`, used by Task 7).
- Modify: `app/auth/ceilings.py` (`HUB_REVIEW_DAILY`, `HUB_REVIEW_ACCOUNT_DAILY`, `check_and_consume_hub_review`, and the breach mapping), `message-keys.json` plus both Android bundles plus `MessageKeys.kt` (every Task-4 key), then run sync-strings.
- Test: `tests/reviews/test_content.py`, `tests/reviews/test_authoring.py`, `tests/reviews/test_forget.py`

**Interfaces:**
- Consumes: `ReviewerLens` and `Assessment` (Task 3); `invalidation.owner_paths` and `invalidation.enqueue`.
- Produces:
  - **`content`:** `contains_url(text: str) -> bool` and `refuse_contact(field: str, text: str | None) -> None`.
  - **`MyReview`** (a frozen dataclass): `rating`, `body`, `status`, `rejection_code`, `tenure`, `published_month: date | None`, `reply_body: str | None` (published replies only), `submitted_at`.
  - **`MyReviewState`:** `assessment`, `can_write: bool`, `edit_until: date | None`, `review: MyReview | None`.
    - **`can_write`:** the switch is on, and either there is no review and the standing is `eligible`, or there is a review, the standing is not `author_only`, and today is on or before `edit_until`.
  - `authoring.state(session, lens, today) -> MyReviewState`.
  - **`authoring.write(session, lens, *, rating: int, body: str | None, now) -> MyReviewState`:**
    1. `refuse_contact("body", body)`.
    2. Refuse by standing, using the eligibility codes, or `REVIEW_EDIT_CLOSED` for an `author_only` edit or one after `edit_until`.
    3. An identical rating and body is a no-op that returns the state.
    4. `check_and_consume_hub_review`.
    5. **Create:** `INSERT … ON CONFLICT (batch_id, author_account_id) DO NOTHING`. When the insert lost a race, the call continues as an edit of the winner's row.
    6. **Edit:** status `pending`, `edited_at = now`, with `approved_at`, `published_month`, `rejection_code`, `decided_*` cleared. If the review was `published`, the owner paths are enqueued for invalidation.
  - `authoring.delete(session, lens, now) -> None`: calls `forget.forget(session, [review_id], now)` and commits. It refuses nothing on a missing review: the outcome is a 204 either way, as an idempotent DELETE.
  - **`forget.forget(session, review_ids: list[UUID], now) -> None`:**
    1. Read which reviews are visible in `hub_public_review` and their owner slugs.
    2. Delete `hub_report` rows where `target_kind IN ('review','reply') AND target_id = ANY(:ids)`.
    3. Delete the reviews (the reply cascades).
    4. Enqueue `owner_paths` for every review that was visible.

    It commits nothing. Tasks 4 and 10 call it.
  - `identity.review_author_ref(account_id: UUID) -> str`: 10 upper-case hex characters of SHA-256 over `b"shikkhokplus/hub-review-author/v1:" + id.bytes`.

- [ ] **Step 1: Write the failing tests:**
  - `test_contact_refusal_cases` (Review Focus 3, every case in it, both directions).
  - `test_create_requires_eligible`, parametrised over `not_yet` (each key) and `closed`.
  - `test_create_freezes_tenure_and_evidence_enrollment`.
  - `test_edit_returns_published_review_to_pending_and_invalidates`.
  - `test_edit_after_30_days_closed`.
  - `test_author_only_cannot_edit_but_can_read_and_delete`.
  - `test_identical_put_is_a_noop_and_consumes_nothing`.
  - `test_sixth_write_in_a_day_hits_ceiling`.
  - `test_concurrent_first_writes_make_one_review` (Review Focus 1: two sessions, a Barrier, one row, both calls succeed).
  - `test_delete_is_total` (Review Focus 4: held, pending and published variants, with a reply and reports by two accounts on both the review and the reply; afterwards, nothing referencing the id remains except `hub_moderation_event`).
  - `test_delete_works_with_switch_off`.
  - `test_body_over_1000_after_strip_refused` and `test_blank_body_stored_as_null`.
  - `test_author_ref_is_not_the_help_requester_ref`.
- [ ] **Step 2: Run** `pytest tests/reviews -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the gate (backend set, plus `tests/reviews tests/auth tests/contract`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(reviews): author write, edit window and total delete`.

### Task 5: Teacher reviews and replies (read through the views)

**Files:**
- Create: `app/reviews/owner.py`
- Test: `tests/reviews/test_owner_reviews.py`, `tests/gates/test_teacher_reviews_read_views.py`

**Interfaces:**
- Consumes: `hub_public_review` and `hub_public_rating` as the app role (Task 2); `forget`-style invalidation (Task 4).
- Produces:
  - **`OwnerBatchRating`:** `batch_id`, `batch_title`, `review_count`, `average_tenths: int | None`, `distribution: list[int] | None`. It covers every published batch of the lens's owner, including those with 0 reviews.
  - **`OwnerReview`:** `id`, `batch_id`, `rating`, `body`, `tenure`, `published_month`, `reply_body` (published), `reply_month`, `my_reply_status: str | None`, `my_reply_body: str | None`, `my_reply_rejection_code: str | None`. The `my_reply_*` fields come from `review_reply` keyed by `review_id`, for reviews already in the view.
  - `owner_reviews(session, lens: TeacherLens) -> tuple[list[OwnerBatchRating], list[OwnerReview]]`. Review content is read only from `hub_public_review WHERE batch_id = ANY(:owned)`, where `:owned` is the lens's owner's `batch_listing.batch_id` values.
  - **`put_reply(session, lens, review_id, body, now) -> OwnerReview`:**
    - the review must be in `hub_public_review` and in an owned batch, else `REVIEW_NOT_FOUND`;
    - a suspended owner listing is refused with `refuse_suspended`;
    - `refuse_contact("body", body)`, then consume `HUB_LISTING_OWNER_DAILY`;
    - the reply is upserted to `pending` with `written_by_account_id = lens.account_id`;
    - replacing a published reply enqueues `owner_paths`;
    - an identical body is a no-op.
  - `delete_reply(session, lens, review_id, now) -> None`: hard-delete, and invalidate if the reply was published. An absent reply is still a 204.

- [ ] **Step 1: Write the failing tests (test-first: owner scoping is an authorization predicate):**
  - `test_teacher_sees_only_published_above_threshold` (pending, approved and held reviews are absent).
  - `test_teacher_sees_nothing_below_threshold` (Review Focus 2; the batch rating row still shows `review_count`).
  - `test_other_owner_cannot_list_or_reply`: teacher B's `put_reply` on A's review gets `REVIEW_NOT_FOUND`, identical to a random id.
  - `test_centre_manager_reply_records_writer` (survival of a manager's deletion is Task 10's test).
  - `test_reply_contact_refused` and `test_reply_on_suspended_listing_refused`.
  - `test_replacing_published_reply_returns_it_to_pending_and_invalidates`.
  - `test_delete_reply_idempotent`.
  - Gate `test_owner_module_never_reads_review_base_table`: the source of `app/reviews/owner.py` matches no `\bFROM\s+review\b`, `\bJOIN\s+review\b` or `\bReview\b` import. It reads `hub_public_review`, `hub_public_rating`, `batch_listing` and `review_reply` only.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the gate (backend set, plus `tests/reviews tests/gates`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(reviews): teacher reads reviews through the public views and replies`.

### Task 6: Review API routes

**Files:**
- Create: `app/schemas/reviews.py`, `app/api/hub_reviews.py`
- Modify:
  - `app/main.py`: include the router (it registers itself in `app.state.included_routers` like the others).
  - `app/contract/routes.py`:
    - `LENS_EXEMPT_AUTHENTICATED` gains `("GET", "/v1/hub/reviewable")`, with a reasoning comment on the `/v1/invitations` pattern;
    - `REVIEWER_ROUTES` (3);
    - `reviewer_routes(app) -> set[tuple[str, str]]`.
  - `app/contract/privacy.py`: `REVIEW_FORBIDDEN_FIELDS = PUBLIC_FORBIDDEN_FIELDS | {"author_account_id", "submitted_at", "approved_at", "edited_at", "decided_at", "joined_on"}` and `review_field_leaks(app) -> list[tuple[str, str, str]]`. The function walks the responses of `REVIEWER_ROUTES`, the three teacher review routes and `/v1/hub/reviewable`.
  - `openapi.json` and `web/src/api/schema.d.ts`, both generated.
- Test: `tests/reviews/test_review_routes.py`, `tests/contract/test_reviewer_contract.py`, `tests/contract/test_review_privacy.py`

**Interfaces:**
- **Routes:**
  - `GET /v1/hub/reviewable` (lens-exempt, authenticated) → `list[ReviewableBatch{batch_id, batch_title, owner_public_name, state: Literal["eligible","not_yet","reviewed"], eligible_from: date | None}]`. Not switch-gated (see the off table).
  - `GET /v1/hub/batches/{batch_id}/my-review` (ReviewerLens) → `MyReviewResponse{standing, waiting_on, eligible_from, can_write, edit_until, review: MyReviewBody | None}`. `MyReviewBody` holds rating, body, status, rejection_code, tenure, published_month as `"YYYY-MM"` and reply_body.
  - `PUT /v1/hub/batches/{batch_id}/my-review` (ReviewerLens, switch-gated) takes `ReviewWrite{rating: int = Field(ge=1, le=5), body: str | None = Field(default=None, max_length=1000)}` → `MyReviewResponse`.
  - `DELETE /v1/hub/batches/{batch_id}/my-review` (ReviewerLens) → 204.
  - `GET /v1/hub/reviews` (TeacherLens, switch-gated) → `OwnerReviewsResponse{batches: list[OwnerBatchRatingWire], reviews: list[OwnerReviewWire]}`.
  - `PUT /v1/hub/reviews/{review_id}/reply` (TeacherLens, switch-gated) takes `ReplyWrite{body: str = Field(min_length=1, max_length=1000)}` → `OwnerReviewWire`.
  - `DELETE /v1/hub/reviews/{review_id}/reply` (TeacherLens) → 204.
- **Wire rules:**
  - Every gated route lists `dependencies=[Depends(require_reviews_on)]` **in the decorator**, so it runs before the lens.
  - Every write route rolls back the session on any non-taxonomy exception (H3 Task 5 carry).
  - Each route's `responses=` documents its error codes from the Global Constraints table.

- [ ] **Step 1: Write the failing tests:**
  - `test_reviewer_routes_resolve_reviewer_lens` (`reviewer_routes(app) == REVIEWER_ROUTES`, both directions) and `test_lens_exempt_count_and_reviewable_entry`.
  - `test_gated_routes_answer_reviews_off_and_deletes_still_work` (Review Focus 5: every gated route answers 404 `HUB_REVIEWS_OFF` with switch off, even for a non-member; both DELETEs, `GET my-review` and `GET reviewable` behave as the off table says).
  - `test_off_response_documented_in_openapi` (each gated route's 404 entry is present).
  - `test_end_to_end_create_edit_delete` (with `reviews_on`).
  - `test_error_envelopes_for_new_codes` (status, code and message_key for each row of the table).
  - `test_teacher_routes_refuse_class_teacher_and_guardian`.
  - `test_no_review_response_carries_identity_fields` (`review_field_leaks(app) == []`), plus a fixture model carrying `author_account_id` that the gate catches (non-vacuous).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Then run `make openapi` and `cd web && npm run gen:api`.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/reviews tests/contract tests/privacy tests/gates`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(api): reviewer, teacher review and reply routes`.

### Task 7: Moderation — admin queue, decisions, report holds, pull-gate figures (0046)

**Files:**
- Create: `migrations/versions/0046_review_moderation_events.py`, `app/moderation/reviews.py`, `web/src/admin/hub/ReviewRow.tsx`
- Modify:
  - `app/db/models.py` (`HUB_MODERATION_EVENT_VALUES`) and the head pins.
  - `app/moderation/vocab.py`: `REVIEW_REJECTION_CODES = ("identifiable_child", "personal_info", "abusive", "off_topic", "other")` and `ReviewRejectionCode`.
  - `app/moderation/reports.py`:
    - `_reportable` accepts `review` and `reply` through `reviews.is_public`;
    - `file` holds on `HOLD_REASONS`;
    - `decide` calls `reviews.settle_report`;
    - `queue` accepts `kind="review"`;
    - `_targets` describes review and reply targets;
    - `QueueItem` gains `author_ref` and `author_role`.
  - `app/api/admin.py`:
    - the queue `kind` Literal adds `review`, and `kind=review` raises `reviews_off()` when off;
    - `GET /v1/admin/hub/reviews/{review_id}?target=review|reply`;
    - `POST /v1/admin/hub/reviews/{review_id}/decision`;
    - both new routes are switch-gated, and the overview gains three figures.
  - `app/admin/overview.py`, `app/schemas/admin.py` and `app/schemas/moderation.py`.
  - `app/contract/routes.py`: `PLATFORM_ADMIN_ROUTES` +2, the comment says fourteen, and `tests/contract/test_admin_contract.py` asserts 14.
  - The `POST /v1/hub/reports` comment in `routes.py`: it now mentions the review/reply hold.
  - `web/src/admin/hub/Queue.tsx` and its test, `web/src/admin/screens/Overview.tsx`, and the admin strings.
- Test: `tests/moderation/test_review_moderation.py`, `tests/db/test_migration_0046.py`, `tests/admin/test_overview_reviews.py`

**Interfaces:**
- **Migration 0046:** adds the labels `review_approved`, `review_rejected`, `review_held`, `review_restored`, `review_removed`, `review_published`, `reply_approved`, `reply_rejected`, `reply_held`, `reply_restored` and `reply_removed`. It uses 0044's autocommit `ADD VALUE IF NOT EXISTS`, restores the lock timeout, and its downgrade refuses while any label is used.
- **`reviews.is_public(session, target_kind: Literal["review","reply"], target_id) -> bool`:** false when the switch is off. A review counts when it is in `hub_public_review`; a reply counts when its row there has `reply_body IS NOT NULL`.
- **`reviews.hold(session, target_kind, target_id, *, reason, now, correlation_id) -> None`:** `published → held`, enqueues `owner_paths`, and records the event with no actor. It runs in the report's transaction.
- **`reviews.decide(session, lens, target_kind, target_id, *, approve: bool, code: str | None, now, correlation_id) -> str`:**

  | Target | From | Approve | Reject (code from `REVIEW_REJECTION_CODES`) |
  |---|---|---|---|
  | review | `pending` | `approved`, `approved_at = now` | `rejected` |
  | review | `held` | `published`, event `review_restored` | `removed`, with invalidation |
  | reply | `pending` | `published`, `published_month` = the Dhaka month of `now` | `rejected` |
  | reply | `held` | `published`, event `reply_restored` | `removed`, with invalidation |

  - `held` keeps `published_month`; `removed` and `rejected` clear it (the 0045 CHECK).
  - Any other status raises `REVIEW_ALREADY_DECIDED`.
  - A code on approval, or a missing or unknown code on rejection, raises `REVIEW_CODE_INVALID`.
  - An absent target raises `admin_not_found()`.
  - Rows are locked `FOR UPDATE`.
- **`reviews.settle_report(…)`** mirrors `media.settle_report`:
  - **Upheld:** a published or held target becomes `removed`, with `REPORT_REJECTION_CODES` mapping (else `other`), and is invalidated.
  - **Dismissed:** a held target is restored to `published` unless another open holding report remains.
- **`reviews.waiting(session) -> list[WaitingReview]`:** pending and held reviews and replies, oldest first by `submitted_at`, `created_at` or hold time.
- **`reviews.detail(session, target_kind, target_id) -> ReviewDetail`:**
  - **Fields:** `target_kind`, `review_id`, `rating`, `body`, `tenure`, `author_role`, `author_ref`, `status`, `batch_title`, `owner_public_name`, `reply_body`, `open_reports`, `waited_hours`.
  - **Never:** an account id, enrollment, `display_name` or phone.
- **Admin routes:** `AdminHubReviewDecisionRequest{target: Literal["review","reply"], decision: Literal["approve","reject"], code: ReviewRejectionCode | None}` → `AdminHubReviewDecided{review_id, target, status}`.
- **Overview figures:** `hub_reviews_public: int`, `hub_reviews_reported: int` and `hub_reviews_pull_bar: bool`, over a trailing 91 days (Call 17).
- **Web admin:**
  - a Reviews tab lists pending and held items, each showing the author reference, role, tenure, rating, body and, for a reply, the reply;
  - the checklist line reads "No child named or identifiable; no contact details" / BN twin;
  - approve, or reject with a code;
  - the Overview shows the three figures, with "Pull-reviews bar crossed" / BN twin when it is true.

- [ ] **Step 1: Write the failing tests:**
  - `test_pending_review_approves_to_approved_not_published`.
  - `test_reject_requires_code_and_records_event`.
  - `test_reply_approval_publishes_immediately`.
  - `test_child_safety_report_holds_review_in_same_transaction`: roll the report back and the review is still published; commit it, and the review is held with an invalidation row.
  - `test_reply_report_holds_reply_only`.
  - `test_upheld_report_removes_and_dismissed_restores_unless_another_hold`.
  - `test_reports_on_reviews_refused_when_switch_off` (`REPORT_TARGET_NOT_FOUND`).
  - `test_report_on_below_threshold_review_refused` (it is not public).
  - `test_admin_detail_carries_author_ref_and_no_identity`.
  - `test_queue_review_kind_off_answers_reviews_off`.
  - `test_decision_on_published_is_conflict`.
  - `test_pull_bar_figures` (cases: 0 public → false; 20 public with 1 reported → false; 20 with 2 → true).
  - `test_0046_adds_labels`.
  - Web: `reviews tab approves and rejects with code`, `reply items show the review they answer`, `overview shows pull bar`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Then run `make openapi` and `cd web && npm run gen:api`.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/moderation tests/reviews tests/admin tests/db tests/contract`) and `cd web && npm run check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(moderation): review and reply moderation, report holds and the pull-reviews figures`.

### Task 8: Weekly publication job and notifications

**Files:**
- Create: `app/reviews/publication.py`, `app/reviews/commands.py`
- Modify:
  - `app/db/models.py`: `HUB_REVIEW_PUBLISH_JOB = "hub_review_publication"` in `EXPECTED_JOBS`, with a docstring comment.
  - `infra/modules/app/user_data.sh.tftpl`: a cron entry `10 21 * * *` (03:10 Dhaka) running `docker compose run --rm api python -m app.reviews.commands publish`, logging to `/var/log/shikkhokplus-hub-review-publication.log`, on the fee-generation pattern.
  - `app/notifications/inbox.py`: `HUB_REVIEW_OUTCOME = "hub_review_outcome"` and `HUB_REVIEWS_PUBLISHED = "hub_reviews_published"`, neither legacy.
  - `app/schemas/notifications.py` (the `kind` Literal) and `app/api/notifications.py` (the kind maps).
  - `app/moderation/reviews.py`: `decide` and `settle_report` deliver `hub_review_outcome` on a review's rejection or removal.
- Test: `tests/reviews/test_publication.py`, `tests/gates/test_scheduled_jobs.py` (unchanged; it must pass with the new job)

**Interfaces:**
- `publication.week_start(now: dt.datetime) -> dt.datetime`: the most recent Friday 00:00 Asia/Dhaka at or before `now`, as an aware UTC datetime.
- **`publication.publish_due(session, now) -> int`:**
  - **Switch off:** returns 0 and changes nothing.
  - **Otherwise:**
    1. `UPDATE review SET status='published', published_month = date_trunc('month', <now in Dhaka>)::date, approved_at = NULL WHERE status='approved' AND approved_at < :week_start RETURNING id, batch_id, author_account_id`.
    2. One `review_published` event per row.
    3. Deliver `hub_review_outcome` (preview `published`, `source_id` the batch id, `batch_name` the batch's `public_title`) to each author.
    4. For each batch whose `hub_public_rating.review_count >= 3` after the update, deliver `hub_reviews_published` (preview: the number published on that batch in this run, Latin digits; `source_id` the owner id) to `managing_accounts(session, owner)`.

    Nothing is invalidated, because additions ride the 10-minute TTL (H3 ruling).
- `commands.main(["publish"])` opens a session, runs `publish_due`, commits, and stamps `HUB_REVIEW_PUBLISH_JOB` on every completed run, including when the switch is off.
- **Outcome previews:** `published`, `rejected` or `removed`. A rejection never carries the moderator's code to the inbox; the code is in the author's `my-review`.

- [ ] **Step 1: Write the failing tests:**
  - `test_week_start_is_friday_midnight_dhaka` (cases: Thursday 23:59 Dhaka → the previous Friday; Friday 00:00 → itself; 18:00 UTC Thursday, which is Friday 00:00 Dhaka → itself).
  - `test_approved_before_boundary_published_after_not`.
  - `test_published_month_is_dhaka_month` (a run at 2026-12-31T18:30Z publishes with month 2027-01-01).
  - `test_overlapping_runs_publish_and_notify_once` (two sessions with a Barrier).
  - `test_owner_notified_only_at_or_above_threshold`.
  - `test_rejection_and_removal_notify_author_without_code`.
  - `test_off_publishes_nothing_but_stamps_heartbeat` (Review Focus 5).
  - `test_scheduled_jobs` (gate) passes.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Then run `make openapi` and `cd web && npm run gen:api`, because the notification kind Literal changed.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/reviews tests/notifications tests/gates tests/contract`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(reviews): weekly publication job and review notifications`.

### Task 9: Reviews and ratings on public pages; sort by rating

**Files:**
- Modify:
  - `app/hub/public/views.py`:
    - add `RatingSummary{state: Literal["below_threshold","shown"], count: int, average_tenths: int | None, average_display: str | None, distribution: list[int] | None}`;
    - add `HubReply{body, month_display}` and `HubReview{review_id: UUID, rating, body: str | None, author_label: str, month_display: str, reply: HubReply | None}`, with `HubReview` registered;
    - `HubBatchCard.rating: RatingSummary | None`, `HubBatchPage.reviews: list[HubReview]`, `HubOwnerCard.rating: RatingSummary | None`, and `HubSearchPage.sort: Literal["relevance","rating"]` plus `offers_sort: bool`.
  - `app/hub/public/queries.py`:
    - read `hub_public_rating` and `hub_public_review` only when `reviews_enabled()`;
    - the owner aggregate covers qualifying batches only (Call 12);
    - `search(..., sort: str | None)` orders by `score_milli DESC` and then the existing order when `sort == "rating"` and the switch is on.
  - `app/hub/public/routes.py`: `QUERY_KEYS` gains `sort`, read only for search.
  - `app/hub/public/messages.py`: the three labels, the twelve month names in EN and BN, `reviews_heading`, `reviews_count`, `reviews_below_threshold`, `rating_out_of`, `reply_heading`, `report_review`, `report_reply`, `sort_label`, `sort_relevance`, `sort_rating`, `reviews_most_recent`.
  - Templates: create `templates/_reviews.html` and `_rating.html`, and include them from `batch.html`, `owner.html` and `search.html`. Use `<meter>` for the distribution, with no inline style.
  - `static/hub.css`.
  - `app/hub/listings/preview.py`: the owner's preview shows the same review section from the same views.
  - `infra/modules/site/functions/hub-query.js` (`ALLOWED` and `LOWERCASED` gain `sort`; JS 2.0 subset only), its test, and `infra/modules/site/main.tf` (`hub_query_strings` gains `"sort"`).
  - `tests/privacy/canary.py`: the canary world gains:
    - a batch with exactly 2 published canary-bodied reviews;
    - a batch with 3 published reviews (one with a published reply and one with a pending canary reply);
    - pending, approved, held and rejected reviews with canary bodies;
    - each author's `enrollment.display_name` and guardian phone as canaries.
- Test: `tests/hub/test_public_reviews.py`, `tests/privacy/test_hub_canary.py` (new probes; the walked-body count is unchanged), `tests/gates/test_hub_query_keys_agree.py`, `infra/modules/site/functions/hub-query.test.mjs`

**Interfaces:**
- **Consumes:** the two views (Task 2) and the switch (Task 1).
- **Batch page:** reviews are capped at 50, ordered `published_month DESC, id`.
  - **Report links:** `kind=review&id={review_id}` and, for a reply, `kind=reply&id={review_id}`.
  - **Text:** `average_display` is `"4.3"`, built by integer ops. The heading reads "4.3 out of 5 · 7 reviews" / BN twin.
  - **Below threshold:** "2 reviews so far. Ratings appear once a class has 3." / "এখন পর্যন্ত 2টি রিভিউ। কোনো ক্লাসে 3টি রিভিউ হলে রেটিং দেখা যাবে।"
- **Search form:** offers the `sort` select only when the switch is on.

- [ ] **Step 1: Write the failing tests:**
  - `test_batch_page_shows_reviews_only_at_threshold` (2 → count line only; 3 → full section).
  - `test_drop_below_threshold_hides_everything_public` (Review Focus 2: batch page, owner card and search order).
  - `test_label_month_and_order` (no day, no name; the EN and BN month strings are exact).
  - `test_review_and_reply_report_links`.
  - `test_owner_card_rating_uses_only_qualifying_batches`.
  - `test_sort_by_rating_orders_by_bayesian_score` (owners at `[5,5,5]`, `[5,4,4]` and none → scores 4063, 3813, 3500, in that order).
  - `test_switch_off_hides_reviews_on_every_public_page` (Review Focus 5: no `class="reviews"`, no `rating`, no `kind=review` link and no sort select in either locale; `?sort=rating` returns the relevance order).
  - `test_page_csp_unchanged_and_no_inline_style`.
  - `test_canary_review_text_of_unpublished_or_below_threshold_never_public`, and `test_canary_published_review_does_appear` (non-vacuous).
  - `test_edge_and_origin_query_keys_agree` (`hub-query.js` `ALLOWED` == Terraform `hub_query_strings` == `QUERY_KEYS`).
  - JS: `sort passes and is lowercased; utm_source still 400`.
- [ ] **Step 2: Run** `pytest tests/hub tests/privacy -q && make infra-functions`. Expected: FAIL.
- [ ] **Step 3: Implement.** Run `terraform fmt -check -recursive infra`.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/hub tests/privacy tests/contract tests/gates`), then `make infra-functions` and `cd site && npm test`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): reviews and ratings on public pages, sort by rating`.

### Task 10: Deletion and takedown wiring

**Files:**
- Modify:
  - `app/governance/deletion.py`, in `delete_account`, before the generic hard-delete loop, on the `_enqueue_solo_media` pattern:
    - `_forget_authored_reviews`: reads the account's review ids `FOR UPDATE`, then `forget.forget(...)`;
    - `_forget_solo_owner_reviews`: the reviews of every batch listing of the account's solo owners, before `_delete_solo_owner_rows`.
  - `app/governance/dispositions.py` basis text, if the tests show it is needed; then run `python3 -m scripts.generate_privacy_policy`.
- Test: `tests/governance/test_review_deletion.py`

**Interfaces:**
- Consumes: `forget.forget` (Task 4). Each step enqueues invalidations only for reviews that were visible.

- [ ] **Step 1: Write the failing tests:**
  - `test_guardian_account_deletion_removes_reviews_replies_and_reports_on_them`.
  - `test_guardian_deletion_removes_reports_they_filed` (the existing `hub_report` scope, re-asserted with review targets).
  - `test_solo_owner_deletion_removes_their_batches_reviews_and_reports_on_them`.
  - `test_centre_reviews_and_replies_survive_manager_deletion_with_writer_cleared`.
  - `test_visible_review_deletion_enqueues_invalidation`.
  - `test_moderation_events_survive_as_bare_ids`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the gate (backend set, plus `tests/governance tests/reviews tests/privacy tests/contract`), then regenerate the privacy policy and confirm `git diff --stat docs/legal/PRIVACY.md` shows the review rows. Expected: PASS.
- [ ] **Step 5: Commit** `feat(governance): reviews go totally with their author or listing`.

### Task 11: Web — guardian reviews, teacher reviews inbox, report and inbox kinds

**Files:**
- Create:
  - `web/src/features/family/reviews/{api.ts, mappers.ts, MyReviews.tsx, ReviewEditor.tsx, reviews.test.tsx}`;
  - `web/src/features/teacher/hub/Reviews.tsx` and `Reviews.test.tsx`.
- Modify:
  - `web/src/App.tsx`: routes `/reviews` and `/reviews/:batchId`.
  - `web/src/features/guardian/GuardianHome.tsx`: a "Reviews" entry, rendered only when `GET /v1/hub/reviewable` returns a non-empty list.
  - `web/src/features/teacher/hub/index.tsx`: a Reviews tab, rendered only when `GET /v1/hub/reviews` succeeds; `HUB_REVIEWS_OFF` renders no tab and no error.
  - `web/src/features/common/HubReport.tsx`: `Kind` gains `review | reply`.
  - `web/src/features/account/area/mappers.ts`: the two notification kinds, announced and titled, with taps opening `/reviews/:batchId` (author) or the teacher Reviews tab (owner).
  - Android `values{,-bn}/strings.xml` for every new `web_*` key, then `cd web && node scripts/sync-strings.mjs`.
  - `docs/delivery/bangla-layout-check.md`: rows for MyReviews, ReviewEditor and Teacher Reviews, marked to check.

**Interfaces:**
- **Editor:**
  - 1–5 star radio buttons, with labels;
  - an optional body with a 1000-character counter;
  - "Your review is checked before it appears, and only once this class has 3 reviews. It never shows your name." / BN twin.
  - **Reading a review:** shows its status (Awaiting review / Approved, appears Friday / Published / Not published: {reason}). The reason comes from the `rejection_code` labels.
  - **Writing:** `can_write` decides whether the form is editable; `edit_until` shows "You can edit until {date}". The client computes no eligibility.
  - **Delete:** behind a confirmation reading "This removes your review completely."
- **`not_yet`:** renders the server's message key, with `eligible_from` when present.
- **Teacher Reviews:**
  - per-batch rating rows from `batches`;
  - review cards with a reply box (1000 counter);
  - the reply status, with "Awaiting review";
  - delete reply;
  - "Report" navigating to `/hub-report?kind=review&id=…`.

- [ ] **Step 1: Write the failing tests:**
  - `entry hidden when reviewable empty or reviews off`;
  - `editor submits and shows awaiting review`;
  - `not yet eligible shows server reason and date`;
  - `edit closed shows read-only with delete`;
  - `delete confirms then calls DELETE`;
  - `contact error shows server message`;
  - `teacher tab hidden on HUB_REVIEWS_OFF`;
  - `teacher replies and sees awaiting review`;
  - `report link prefills review kind`;
  - `inbox renders both review kinds`.
- [ ] **Step 2: Run** `cd web && npm run check`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `cd web && npm run check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(web): guardian reviews and the teacher reviews inbox`.

### Task 12: Android — guardian reviews, teacher reviews, report and inbox kinds

**Files:**
- Create: `android/src/main/kotlin/com/shikkhokplus/app/feature/hubreviews/`:
  - `HubReviewsApi.kt` (`HttpHubReviewsApi`) and `HubReviewsModels.kt`;
  - `MyReviewsViewModel.kt`, `ReviewEditorViewModel.kt` and `OwnerReviewsViewModel.kt`;
  - `ui/{MyReviewsScreen.kt, ReviewEditorScreen.kt, OwnerReviewsScreen.kt}`;
  - their tests.
- Modify:
  - `navigation/Destination.kt`: `HubMyReviews` (`hub/reviews/mine`), `HubReviewEditor` (`hub/reviews/{batchId}`) and `HubOwnerReviews` (`hub/listing/reviews`).
  - `navigation/HubRoutes.kt`: every action wired.
  - `GuardianHomeScreen.kt`: a "Reviews" row, shown only when the reviewable list is non-empty.
  - `HubListingScreen.kt`: a "Reviews" row, shown only when `GET /v1/hub/reviews` succeeded.
  - `HubReportViewModel.kt`: `ReportKind.REVIEW("review")` and `REPLY("reply")`.
  - `InboxMapper.kt` and `InboxScreen.kt`: the two kinds, announced, with taps navigating to the editor or the owner reviews.
  - `values/` and `values-bn/` strings.
  - `docs/delivery/bangla-layout-check.md`: rows for the three screens.

**Interfaces:**
- Behaviour mirrors Task 11 exactly.
- **ViewModel states:** `Loading`, `Ready`, `Saving`, `Error(retryable)` and `Off`. `Off` is reached from `HUB_REVIEWS_OFF` and renders nothing.
- **Failed writes:** a failed write keeps the typed text and offers retry (TC-8).
- **Rating serialisation:** the rating is an `Int`. No float appears anywhere, and `average_tenths` is not used on Android.

- [ ] **Step 1: Write the failing tests:**
  - ViewModels:
    - `submit success`;
    - `not yet eligible renders reason and date`;
    - `edit closed is read only`;
    - `delete confirmed`;
    - `contact refused keeps text`;
    - `network failure keeps text and offers retry`;
    - `off hides entry`.
  - `HubReviewsRouteTest`: drives the real routes with MockEngine. It asserts that the guardian-home row opens MyReviews → the editor, that submit, edit and delete call the API, that the teacher row opens owner reviews, and that reply, delete reply and Report navigate to `HubReport` with `kind=review`.
  - `InboxRouteTest` additions for both kinds; `HubReportRouteTest` accepts `review` and `reply`.
- [ ] **Step 2: Run** `make android`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make android && make android-quality`, then `cd web && node scripts/sync-strings.mjs --check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(android): guardian reviews and the teacher reviews screen`.

### Task 13: Deploy, smoke, release deliverables and the switch runbook

**Files:**
- Modify:
  - `deploy/smoke.py --hub`: also `GET {site}/hub/en?sort=rating` returns 200, which proves the edge allowlist carries `sort`.
  - `docs/legal/README.md`, the Data Safety delta: reviews are written by guardians, shown publicly after moderation with no name, deletable at any time, and deleted with the account. The Families user-content declaration note covers pre-moderation and in-app reporting.
  - `docs/legal/PRIVACY.md` (regenerated).
  - Site copy, EN and BN twins: the "Private by design" paragraph says reviews come only from verified guardians, are checked before they appear, and never show a name.
  - `infra/README.md`, the "Switching reviews on" runbook. Each step is a human check, in order:
    1. the D9 day-90 bar in spec §9 is met;
    2. the D8 legal review is recorded;
    3. the D6 Data Safety and Families declarations are published;
    4. `aws ssm put-parameter --overwrite --name /shikkhokplus/shikkhokplus-<env>/hub-reviews --value on`;
    5. dispatch a deploy;
    6. check that a seeded batch page in staging shows the reviews section.

    Switching off is the same with `off`.
- Test: `tests/gates/test_deploy_workflow.py` (`test_hub_smoke_checks_sort_key`), `tests/gates/test_hub_reviews_switch_infra.py` (`test_runbook_lists_d8_d9_d6_before_flip`), `site/test/build.test.mjs` (both twins)

- [ ] **Step 1: Write the failing tests.**
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make check` once, the full gate. Expected: every target green.
- [ ] **Step 5: Commit** `feat(deploy): smoke the sort key and ship review release deliverables`.
