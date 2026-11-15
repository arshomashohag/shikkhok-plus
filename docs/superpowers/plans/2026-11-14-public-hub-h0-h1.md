# Public Hub H0 (Guardrails) and H1 (Listings) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install the privacy guardrails every public hub page will depend on (H0). Then let tutors and centre managers author, publish and unpublish an opt-in hub profile and per-batch listings, with reporting and admin suspension (H1). No public page ships in this plan; that is H2.

**Architecture:**
- **H0** adds four mechanical controls before any public route exists:
  - a restricted `shikkhok_hub_reader` database role;
  - a public-facing audience in the privacy gate, walking a registry of public view models;
  - a `PUBLIC_CACHEABLE_ROUTES` no-auth gate plus an import gate on `app/hub/public`;
  - a canary-probe harness.
- **H1** adds a new `app/hub/listings` module over three new tables (`bd_area`, `owner_listing`, `batch_listing`) and a `app/moderation` module over `hub_report` and `hub_moderation_event`.
- Listings are a separate resource beside batches. `POST/PATCH /v1/batches` keep their contract, and deactivating a batch hides its listing.

**Tech Stack:**
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, pytest + testcontainers.
- Android: Kotlin, Jetpack Compose, kotlinx.serialization, JUnit + Turbine.
- Web: React + TypeScript + Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-14-public-hub-design.md` (approved 2026-11-14). Detail behind it: `docs/reviews/2026-11-14-public-hub/REPORT.md` §6–§8.

**Deviations from the spec, decided here:**
- **Migration numbers shift by one.** H0's role migration takes `0034`, so `bd_area` is `0035` and listings are `0036`. H2–H4 renumber when written.
- **Centre-teacher name consent resolves a new `CentreMemberLens`** instead of being lens-exempt. A lens is how this codebase scopes "my own membership" (compare `MembershipLens`), and it keeps the route-enumeration gate meaningful.
- **"Preview as public" moves to H2.** It renders the real public page, which does not exist yet. The H1 editors show a plain summary card instead.

## Global Constraints

- Every new route resolves a lens or is listed in an allowlist with a written reason. `PUBLIC_ROUTES` stays at **14** in this plan; H2 raises it to 18.
- No `float`, and no `Decimal` outside `app/money/**`. JSON money is a string, and Kotlin uses the `Money` value class.
- Integration tests run as the restricted role (`restricted_session` / `api_client`), never as superuser.
- Python:
  - Sphinx docstrings on every module, class and function (`:param`, `:return`, `:raises`);
  - type hints everywhere;
  - Ruff line length 88;
  - imports at top.
- Every new error has a stable `code` and a `message_key`, is added to `message-keys.json`, and has a string in `android/src/main/res/values/strings.xml`, `values-bn/strings.xml` and the web bundles. `MessageKeyCoverageTest` and `tests/contract/test_message_keys.py` must stay green.
- Every new table gets a `DISPOSITIONS` entry (`app/governance/dispositions.py`) and, when `HARD_DELETE`, a `HARD_DELETE_SCOPES` entry (`app/governance/deletion.py`) in the same task. Then regenerate `docs/legal/PRIVACY.md` with `python3 -m scripts.generate_privacy_policy`.
- After any API change, run `make openapi` and commit `openapi.json`.
- Each new migration moves `EXPECTED_REVISIONS` and `EXPECTED_HEAD` in `tests/db/test_migration_head_pin.py` and extends that file's comment trail.
- A comment that states a count must be asserted by a test, or the number comes out (project rule).
- Spec values, verbatim:
  - listing statuses `draft | published | hidden | suspended` (default `draft`);
  - slug `^[a-z0-9-]{3,60}$`;
  - admissions `open | waitlist | closed`;
  - modes `in_person | home_visit | online`;
  - report reasons `personal_info | child_safety | abusive | fake | misleading | other`;
  - report targets `listing | media | review | reply`;
  - report statuses `open | upheld | dismissed`;
  - limits: reports **10/day/account**, listing updates **50/day/owner**;
  - centre teacher fallback label **"Centre faculty"**;
  - badge "Runs classes on ShikkhokPlus" = **≥ 5 accepted enrollments and attendance recorded in the last 30 days**;
  - consent text version `2026-11-14`.
- Commits are conventional-commit shaped and end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Gate: `make test` for backend tasks, `make web` for web tasks and `make android` for Android tasks, with `make check` green before the final task's commit.

## Review Focus

1. **A solo tutor never published.** Their name, area and batches appear in no hub response except their own editor, and no draft becomes public by any path. (Task 8, `test_never_published_owner_is_draft_everywhere`.)
2. **A centre teacher who has not consented.** Their name appears in no batch listing response; the response says "Centre faculty". (Task 10, `test_unconsented_member_is_centre_faculty`.)
3. **A batch is deactivated while its listing is published.** The listing becomes `hidden` in the same transaction and stays hidden when the batch is reactivated. (Task 9, `test_deactivating_batch_hides_listing_and_reactivation_does_not_republish`.)
4. **A rival account files a child-safety report on a competitor's listing.** The listing stays `published` until an admin suspends it. (Task 11, `test_report_never_changes_listing_status`.)
5. **A solo tutor deletes their account.** No `owner_listing` or `batch_listing` row survives. A centre manager deleting theirs leaves the centre's listing standing. (Task 7, `test_solo_owner_deletion_removes_listing_centre_survives_manager`.)

---

## H0 — Guardrails

### Task 1: `shikkhok_hub_reader` role and its meta-test

**Files:**
- Create: `migrations/versions/0034_hub_reader_role.py`
- Modify: `app/db/roles.py`
- Create: `app/hub/__init__.py`, `app/hub/public/__init__.py`, `app/hub/public/db.py`
- Modify: `tests/db/test_migration_head_pin.py`
- Test: `tests/privacy/test_hub_reader_meta.py`

**Interfaces:**
- Produces:
  - `app.db.roles.HUB_READER_ROLE: Final = "shikkhok_hub_reader"`
  - `app.hub.public.db.as_hub_reader(session: Session) -> None`, which runs `SET LOCAL ROLE shikkhok_hub_reader` inside the caller's transaction.

- [ ] **Step 1: Write the failing tests** in `tests/privacy/test_hub_reader_meta.py`. The `test_hub_` name sorts after `test_rls_meta.py` and before the hub probes.
  - `test_hub_reader_is_not_superuser_and_cannot_bypass_rls`: `SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = 'shikkhok_hub_reader'` returns `(False, False, False)`.
  - `test_app_role_may_become_hub_reader`: on `restricted_session`, `as_hub_reader(session)` then `SELECT current_user` gives `"shikkhok_hub_reader"`.
  - `test_hub_reader_cannot_read_private_tables` (parametrised over `profile`, `enrollment`, `payment_method`, `account`, `student`, `batch`): after `as_hub_reader`, `SELECT 1 FROM <table> LIMIT 1` raises `sqlalchemy.exc.ProgrammingError` whose `orig` is `psycopg.errors.InsufficientPrivilege`.
- [ ] **Step 2: Run** `pytest tests/privacy/test_hub_reader_meta.py -v`. Expected: FAIL (role does not exist).
- [ ] **Step 3: Implement.**
  - **Migration** (`revision = "0034"`, `down_revision = "0033"`):
    - `CREATE ROLE shikkhok_hub_reader NOLOGIN NOSUPERUSER NOBYPASSRLS`, guarded by `IF NOT EXISTS` in a `DO` block;
    - `GRANT shikkhok_hub_reader TO shikkhok_app`;
    - `GRANT USAGE ON SCHEMA public TO shikkhok_hub_reader`;
    - no table grants.
    - Downgrade: `REVOKE`, then `DROP ROLE`.
  - Add `HUB_READER_ROLE` to `app/db/roles.py`.
  - Write `as_hub_reader`.
  - Move the head pin to 33 → **34**, head `"0034"`.
- [ ] **Step 4: Run** `pytest tests/privacy tests/db -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(db): shikkhok_hub_reader role for public hub reads (0034)`.

### Task 2: Public-facing audience in the privacy gate

**Files:**
- Create: `app/hub/public/registry.py`
- Modify: `app/contract/privacy.py`
- Create: `tests/contract/fixtures/public_leak_app.py`
- Test: `tests/contract/test_public_privacy.py`

**Interfaces:**
- Produces:
  - `app.hub.public.registry.PUBLIC_VIEW_MODELS: tuple[type[BaseModel], ...]`, empty in H0 and appended to by H2;
  - `register_view(model: type[BaseModel]) -> type[BaseModel]`, a decorator that appends and returns the model;
  - `app.contract.privacy.PUBLIC_FORBIDDEN_FIELDS: Final[frozenset[str]]`;
  - `app.contract.privacy.public_field_leaks(app: FastAPI, view_models: Iterable[type[BaseModel]]) -> list[tuple[str, str, str]]`, returning `(origin, component, field)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_public_forbidden_set_is_the_spec_union`: `PUBLIC_FORBIDDEN_FIELDS` equals `OWNER_PRIVATE_FIELDS | FORBIDDEN_ACCOUNT_ID_FIELDS | STAFF_PRIVATE_FIELDS | {"phone", "student_phone", "guardian_phone", "invited_phone", "collection_number", "display_name", "enrollment_id", "student_id", "self_name"}`.
  - `test_real_app_has_no_public_leaks`: `public_field_leaks(create_app(), PUBLIC_VIEW_MODELS) == []`.
  - `test_fixture_view_model_leak_is_caught`: a planted `BaseModel` with a nested model holding `display_name` is reported as `("view:<ModelName>", "<NestedName>", "display_name")`.
  - `test_fixture_public_route_leak_is_caught`: the fixture app in `public_leak_app.py` registers `GET /health` (a `PUBLIC_ROUTES` member) with a `response_model` carrying `collection_number`, and is reported.
- [ ] **Step 2: Run** `pytest tests/contract/test_public_privacy.py -v`. Expected: FAIL (names undefined).
- [ ] **Step 3: Implement.**
  - `public_field_leaks` walks two sources:
    - the JSON schema of every route in `PUBLIC_ROUTES` that has a `response_model`, via `_api_routes`;
    - `model.model_json_schema(ref_template="#/$defs/{model}")` of every view model.
  - It reuses `_walk` with a classifier over `PUBLIC_FORBIDDEN_FIELDS`, plus a `$defs` lookup for view models.
- [ ] **Step 4: Run** `pytest tests/contract -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(contract): public-facing privacy audience and view-model registry`.

### Task 3: Cacheable-route no-auth gate and the `app/hub/public` import gate

**Files:**
- Modify: `app/contract/routes.py`
- Modify: `tests/gates/test_import_gates.py`
- Create: `tests/gates/fixtures/hub_public_bad_import/` (one module importing `app.db.models`)
- Test: `tests/contract/test_public_cacheable.py`

**Interfaces:**
- Produces:
  - `app.contract.routes.PUBLIC_CACHEABLE_ROUTES: frozenset[tuple[str, str]] = frozenset()`, asserted to be a subset of `PUBLIC_ROUTES`;
  - `authenticated_cacheable_routes(app: FastAPI, cacheable: frozenset[tuple[str, str]] = PUBLIC_CACHEABLE_ROUTES) -> list[tuple[str, str]]`;
  - `HUB_PUBLIC_IMPORT_ALLOWLIST: Final[frozenset[str]] = frozenset({"app.hub.public", "app.db.roles", "app.money", "app.api.html", "app.errors"})`, in the test module.

- [ ] **Step 1: Write the failing tests:**
  - `test_cacheable_set_is_subset_of_public`.
  - `test_cacheable_routes_are_get_only`: every entry's method is `"GET"`.
  - `test_real_app_has_no_authenticated_cacheable_route`: `authenticated_cacheable_routes(create_app()) == []`.
  - `test_fixture_cacheable_route_with_auth_is_caught`: a fixture app routes `GET /health` through `Depends(authenticated_account)`, and `authenticated_cacheable_routes(fixture, cacheable={("GET", "/health")})` returns it. Give the function an optional `cacheable` parameter defaulting to `PUBLIC_CACHEABLE_ROUTES`.
  - In `test_import_gates.py`: `test_hub_public_imports_only_its_allowlist` (real tree: passes) and `test_hub_public_import_gate_fires_on_fixture` (the fixture importing `app.db.models` fails).
- [ ] **Step 2: Run** `pytest tests/contract/test_public_cacheable.py tests/gates/test_import_gates.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `authenticated_cacheable_routes`. It walks `route.dependant` recursively and flags any node whose `call` is `authenticated_account`, `token_subject`, or any callable whose return annotation resolves to a `Lens` (`resolve_lens_type`). The import gate parses `app/hub/public/**/*.py` with `ast` and fails on any `app.`-prefixed import whose module is not equal to, or a submodule of, an allowlist entry.
- [ ] **Step 4: Run** `make gates`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(gates): no-auth gate for cacheable public routes and hub.public import gate`.

### Task 4: Canary probe harness

**Files:**
- Create: `tests/privacy/canary.py`
- Test: `tests/privacy/test_hub_canary.py`

**Interfaces:**
- Produces:
  - `tests.privacy.canary.CanaryWorld`, a frozen dataclass holding `strings: frozenset[str]` and `owner_id: UUID`;
  - `seed_canaries(session: Session) -> CanaryWorld`, which seeds one solo owner with unique `uuid4().hex`-derived strings in `profile.self_name`, `account.phone`, `batch.collection_number`, `enrollment.display_name`, `enrollment.guardian_phone`, `student.display_name`, plus the enrollment id itself;
  - `rendered_public_bodies(client: TestClient, paths: Iterable[str]) -> dict[str, str]`.

- [ ] **Step 1: Write the tests:**
  - `test_no_canary_on_any_cacheable_public_page`: it walks every `PUBLIC_CACHEABLE_ROUTES` path, resolving `{locale}` to both `en` and `bn` and `{owner_slug}` / `{batch_slug}` from the seeded world once H2 adds them. It asserts no canary string appears in any body, and asserts it walked `len(PUBLIC_CACHEABLE_ROUTES) * 2` bodies, the stated count.
  - `test_canary_probe_fires_on_planted_page`: a fixture app whose `GET /hub/en` echoes the seeded `collection_number` is caught.
- [ ] **Step 2: Run** `pytest tests/privacy/test_hub_canary.py -v`. Expected: the fixture test FAILs until the harness exists.
- [ ] **Step 3: Implement** the harness. H2 extends the path resolver; leave the slug resolution as a function `_resolve(path: str, world: CanaryWorld) -> list[str]` that raises `NotImplementedError` for an unknown placeholder, so a new public route cannot be silently skipped.
- [ ] **Step 4: Run** `pytest tests/privacy -v`. Expected: PASS.
- [ ] **Step 5: Commit** `test(privacy): canary probe harness for public hub pages`.

### Task 5: Rule amendments (owner-approved wording)

**Files:**
- Modify: `aidlc/spaces/default/memory/project.md` (`## Forbidden` and `## Mandated`)

**This task is a human-reviewed text change, not code.** The owner approved the wording on 2026-11-14 (spec D3 and D4). AI-DLC's learnings ritual is not available in this environment, so the owner must look at this exact diff before merge.

- [ ] **Step 1: Replace the D-5 line** (`NEVER expose anything a student or guardian writes to any teacher. [TC-13] [D-5]`) with the amended text from `REPORT.md` §8. Keep the tags and append `(amended 2026-11-14, public hub)`.
- [ ] **Step 2: Replace the D-6 line** in the same way, with `REPORT.md` §8's wording.
- [ ] **Step 3: Append under `## Forbidden`:**
  - `NEVER put a student's name, photo, marks, attendance or enrollment date on any public surface. [hub spec §8] (affirmed 2026-11-14)`
  - `NEVER render a public page from anything but a registered public view model read through shikkhok_hub_reader. [hub spec §8] (affirmed 2026-11-14)`
  - `NEVER list an owner, batch or centre member without that person's recorded consent. [hub spec D1] (affirmed 2026-11-14)`
- [ ] **Step 4: Append under `## Mandated`:**
  - `ALWAYS pre-moderate hub images and reviews before they are public. [hub spec D7] (affirmed 2026-11-14)`
- [ ] **Step 5: Commit** `docs(rules): amend D-5 and D-6 for the public hub (owner-approved)`. Flag the commit in the PR description for the owner's review.

---

## H1 — Listings

### Task 6: `bd_area` vocabulary (0035)

**Files:**
- Create: `app/hub/listings/__init__.py`, `app/hub/listings/data/bd_area.csv`, `migrations/versions/0035_bd_area.py`
- Modify: `app/db/models.py` (add `BdArea`), `app/governance/dispositions.py`, `tests/db/test_migration_head_pin.py`
- Test: `tests/db/test_migration_0035.py`

**Interfaces:**
- Produces:
  - `BdArea(code: str PK VARCHAR(8), kind: str, parent_code: str | None, name_en: str, name_bn: str)`;
  - enum `bd_area_kind` = `division | district | upazila`, where `upazila` is the Bangladesh Bureau of Statistics level-3 "Upazila/Thana", including metropolitan thanas such as Mirpur.

**Data source:** the BBS geocode list (divisions, districts, upazilas/thanas, with official English and Bangla names). Commit it as CSV with header `code,kind,parent_code,name_en,name_bn`. Do not invent names: any row not traceable to BBS is left out.

- [ ] **Step 1: Write the failing tests:**
  - `test_0035_seeds_8_divisions_and_64_districts`.
  - `test_every_district_parent_is_a_division_and_every_upazila_parent_is_a_district`.
  - `test_upazila_count_is_at_least_490`.
  - `test_names_are_nonblank_in_both_languages`.
  - `test_hub_reader_can_select_bd_area`: under `as_hub_reader`, `SELECT count(*) FROM bd_area` works.
- [ ] **Step 2: Run** `pytest tests/db/test_migration_0035.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - The migration creates the table and enum and loads the CSV with `op.bulk_insert`, reading from the CSV path.
  - It runs `GRANT SELECT ON bd_area TO shikkhok_hub_reader, shikkhok_app`.
  - Add a disposition: `NOT_PERSONAL`, `LIFE_OF_ACCOUNT`, with basis "A fixed list of Bangladesh's divisions, districts and upazilas; about no person."
  - Move the head pin to 35.
- [ ] **Step 4: Run** `pytest tests/db -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): Bangladesh area vocabulary (0035)`.

### Task 7: Listing, report and moderation tables (0036)

**Files:**
- Create: `migrations/versions/0036_hub_listings.py`
- Modify:
  - `app/db/models.py`: add `OwnerListing`, `BatchListing`, `HubReport`, `HubModerationEvent`; add `OwnerMember.public_name_consent_at`;
  - `app/governance/dispositions.py`, `app/governance/deletion.py`, `docs/legal/PRIVACY.md` (regenerated);
  - `tests/db/test_migration_head_pin.py`.
- Test: `tests/db/test_migration_0036.py`, `tests/governance/test_hub_deletion.py`

**Interfaces:**
- Produces (columns per spec §3, plus):
  - `OwnerListing.slug: str | None`, with CHECK `status = 'draft' OR slug IS NOT NULL` and UNIQUE where not null;
  - `OwnerListing.district_code` / `upazila_code` FK `bd_area.code`;
  - `OwnerListing.street_address` allowed only when `owner.kind = 'organisation'`, enforced by trigger function `hub_street_address_centre_only()`;
  - `BatchListing.show_fee` / `show_schedule` NOT NULL with no server default;
  - `BatchListing.owner_id`, kept equal to `batch.owner_id` by trigger `hub_batch_listing_owner_matches()`;
  - `HubReport(id, target_kind, target_id, reporter_account_id FK account CASCADE, reason, note VARCHAR(500) NULL, status, created_at, decided_at, decided_by_account_id FK SET NULL)`, UNIQUE `(target_kind, target_id, reporter_account_id)`;
  - `HubModerationEvent(id, event, target_kind, target_id, actor_admin_account_id FK SET NULL, decision_code, correlation_id, at)`, append-only with no free text;
  - `OwnerMember.public_name_consent_at: datetime | None`;
  - enums `hub_listing_status`, `hub_admissions`, `hub_teaching_mode`, `hub_report_reason`, `hub_report_target`, `hub_report_status`, `hub_moderation_event_kind` (`report_filed | report_upheld | report_dismissed | listing_suspended | listing_unsuspended`).
- No grants to `shikkhok_hub_reader` yet; H2's views get them.

- [ ] **Step 1: Write the failing tests:**
  - `test_draft_without_slug_inserts_published_without_slug_fails`.
  - `test_slug_check_rejects_uppercase_and_short`.
  - `test_solo_owner_listing_refuses_street_address` (trigger raises).
  - `test_batch_listing_owner_must_match_batch_owner`.
  - `test_show_fee_has_no_default`: an INSERT omitting it raises `NotNullViolation`.
  - `test_moderation_event_is_append_only`, following `tests/db/test_append_only.py`: `UPDATE` and `DELETE` are refused for the app role.
  - In `tests/governance/test_hub_deletion.py`, `test_solo_owner_deletion_removes_listing_centre_survives_manager` (Review Focus 5) and `test_reporter_deletion_removes_their_reports`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** the migration, models, append-only trigger (copy the `0015` pattern), and dispositions:

  | Table | Disposition | Retention |
  |---|---|---|
  | `owner_listing` | `HARD_DELETE` for a solo owner | `LIFE_OF_ACCOUNT` |
  | `batch_listing` | `HARD_DELETE` | `LIFE_OF_ACCOUNT` |
  | `hub_report` | `HARD_DELETE`, `ACCOUNT_COLUMN` `reporter_account_id` | `LIFE_OF_ACCOUNT` |
  | `hub_moderation_event` | `NOT_PERSONAL` | `MONTHS_12` |

  The two listing tables use `VIA_CASCADE` if `delete_account` deletes a solo `owner` row; otherwise add an explicit owner-scoped delete in `delete_account`. Read `app/governance/deletion.py` first. The Review Focus 5 test decides which is correct.

  Grants match `0022`'s grants on `owner_member`. Regenerate `PRIVACY.md`. Move the head pin to 36.
- [ ] **Step 4: Run** `pytest tests/db tests/governance -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): listing, report and moderation tables (0036)`.

### Task 8: Owner listing service (test-first)

**Files:**
- Create: `app/hub/listings/consent.py`, `app/hub/listings/owner.py`, `app/hub/listings/checklist.py`, `app/hub/listings/badge.py`
- Test: `tests/hub/__init__.py`, `tests/hub/test_owner_listing.py`, `tests/hub/test_badge.py`

**Interfaces:**
- Consumes: `TeacherLens(account_id, owner_id)`, `OwnerListing`, `BdArea`.
- Produces:
  - `consent.HUB_CONSENT_VERSION: Final = "2026-11-14"`.
  - `owner.get_or_draft(session, lens: TeacherLens) -> OwnerListing`. It inserts a `draft` on first call, with `public_name` prefilled from `owner.name` for a centre, or else from the first non-blank `batch.teacher_display_name` by `created_at`. It never reads `profile`.
  - `owner.update(session, lens, changes: OwnerListingUpdate) -> OwnerListing`.
  - `owner.publish(session, lens, consent_version: str, now: dt.datetime) -> OwnerListing`.
  - `owner.unpublish(session, lens, now) -> OwnerListing`, which sets `hidden`.
  - `owner.slug_available(session, slug: str, lens: TeacherLens) -> bool`.
  - `checklist.owner_checklist(listing: OwnerListing) -> list[ChecklistItem]`. `ChecklistItem` is a frozen dataclass of `key: str, done: bool`, with keys `public_name`, `slug`, `area`, `headline`, `bio`, `contact_or_none`.
  - `checklist.owner_publishable(items) -> bool`.
  - `badge.runs_classes(session, owner_id: UUID, today: dt.date) -> bool`.

- [ ] **Step 1: Write the failing tests:**
  - `test_get_or_draft_creates_one_draft_and_is_idempotent`.
  - `test_draft_name_prefill_never_reads_profile`: seed `profile.self_name = "PRIVATE-X"` and no batch display name, then assert `public_name == ""` and `"PRIVATE-X"` is absent.
  - `test_publish_refuses_wrong_consent_version` (`ValidationError`, code `HUB_CONSENT_OUTDATED`).
  - `test_publish_refuses_incomplete` (`HUB_LISTING_INCOMPLETE`, with `details["missing"]` a comma-joined list of checklist keys).
  - `test_publish_records_consent_version_time_and_account`.
  - `test_suspended_listing_cannot_be_published_or_edited` (`ConflictError`, `HUB_LISTING_SUSPENDED`).
  - `test_unpublish_sets_hidden_and_republish_is_allowed`.
  - `test_slug_taken_by_other_owner_is_conflict` (`HUB_SLUG_TAKEN`).
  - `test_upazila_must_belong_to_district` (`ValidationError`, `HUB_AREA_MISMATCH`).
  - `test_never_published_owner_is_draft_everywhere` (Review Focus 1). It asserts that no code path in `app/hub/listings` sets `published` except `publish`, by calling every other public function on a draft and re-reading the status.
  - Badge tests:
    - `test_badge_needs_five_accepted_and_recent_attendance`;
    - `test_badge_false_with_four_accepted`;
    - `test_badge_false_when_last_attendance_31_days_ago`.
- [ ] **Step 2: Run** `pytest tests/hub -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the functions above. An owner-text field may not contain a phone number outside `public_contact_phone`: reuse the phone-pattern normaliser in `app/accounts/phone.py` and raise `HUB_TEXT_CONTAINS_CONTACT`.
- [ ] **Step 4: Run** `pytest tests/hub -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): owner listing drafts, consent and publishing`.

### Task 9: Batch listing service (test-first)

**Files:**
- Create: `app/hub/listings/batches.py`
- Modify: `app/batches/service.py` (`update_batch`, around line 1054)
- Test: `tests/hub/test_batch_listing.py`

**Interfaces:**
- Consumes: Task 8's `get_or_draft` and checklist pattern.
- Produces:
  - `batches.list_for_owner(session, lens) -> list[BatchListingView]`. It covers every active batch of the owner. `BatchListingView` carries `batch_id`, `batch_name`, `subjects: list[str]` (from `batch_subject`), `listing: BatchListing | None` and `checklist`.
  - `batches.upsert(session, lens, batch_id, changes: BatchListingUpdate) -> BatchListing`.
  - `batches.publish(session, lens, batch_id, now) -> BatchListing`.
  - `batches.unpublish(session, lens, batch_id, now) -> BatchListing`.
  - `batches.hide_for_inactive_batch(session, batch_id: UUID) -> None`, called by `update_batch` in the same transaction.

- [ ] **Step 1: Write the failing tests:**
  - `test_publish_requires_owner_listing_published` (`HUB_OWNER_NOT_PUBLISHED`).
  - `test_publish_requires_description_class_level_subject_and_both_flags`.
  - `test_upsert_without_show_fee_is_validation_error`.
  - `test_other_owners_batch_is_not_available`: 403, code matching the existing `_owned_batch` refusal.
  - `test_inactive_batch_cannot_be_published`.
  - `test_deactivating_batch_hides_listing_and_reactivation_does_not_republish` (Review Focus 3).
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.** In `update_batch`, when `changes.active is False`, call `hide_for_inactive_batch` before `session.commit()`.
- [ ] **Step 4: Run** `pytest tests/hub tests/batches -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): batch listings, hidden when their batch is retired`.

### Task 10: Listing API, centre member consent, errors and contract

**Files:**
- Create: `app/schemas/hub.py`, `app/api/hub.py`
- Modify:
  - `app/authz/lenses.py`, `app/api/deps.py` (`CentreMemberLens`, `centre_member_lens`);
  - `app/api/centres.py` (consent route);
  - `app/main.py` (register `hub_router`);
  - `app/auth/ceilings.py` (`HUB_LISTING_OWNER_DAILY`);
  - `message-keys.json`, `openapi.json`.
- Test: `tests/hub/test_hub_api.py`, `tests/privacy/test_hub_listing_probes.py`

**Interfaces:**
- Consumes: Tasks 8–9.
- Produces these routes (all `TeacherLens` unless noted):
  - `GET /v1/hub/listing` → `OwnerListingResponse`, with fields per spec §3 plus `status`, `checklist: list[ChecklistItemWire]`, `publishable: bool`, `runs_classes: bool`, `consent_version_current: str`;
  - `PUT /v1/hub/listing` (`OwnerListingUpdate`) → `OwnerListingResponse`;
  - `POST /v1/hub/listing/publish` (`PublishRequest{consent_version: str}`) → `OwnerListingResponse`;
  - `POST /v1/hub/listing/unpublish` → `OwnerListingResponse`;
  - `GET /v1/hub/slugs/{slug}` → `SlugAvailability{slug, available}`;
  - `GET /v1/hub/batch-listings` → `list[BatchListingResponse]`;
  - `PUT /v1/batches/{batch_id}/listing` (`BatchListingUpdate`) → `BatchListingResponse`;
  - `POST /v1/batches/{batch_id}/listing/publish` → `BatchListingResponse`;
  - `POST /v1/batches/{batch_id}/listing/unpublish` → `BatchListingResponse`;
  - `PUT /v1/centres/{centre_id}/members/me/public-name-consent` (`CentreMemberLens`, body `{consent: bool}`) → 204;
  - `GET /v1/hub/areas?parent=<code>` → `list[AreaOption{code, kind, name_en, name_bn}]` (`TeacherLens`).
- `CentreMemberLens(account_id, owner_id, member_id)` is granted only for an accepted, unrevoked `owner_member` of `centre_id` held by this account.
- `BatchListingResponse.teacher_names: list[str]`: assigned members' `display_name` only where `public_name_consent_at` is set, otherwise `["Centre faculty"]`. The field is named `teacher_names`, not `display_name`, so it passes the public audience in H2.
- `BatchListingResponse.fee: Money | None` is filled only when `show_fee`.
- New codes: `HUB_SLUG_TAKEN`, `HUB_LISTING_INCOMPLETE`, `HUB_LISTING_SUSPENDED`, `HUB_CONSENT_OUTDATED`, `HUB_AREA_MISMATCH`, `HUB_OWNER_NOT_PUBLISHED`, `HUB_TEXT_CONTAINS_CONTACT`, `HUB_WRITE_CEILING`. Their message keys are `hub.<snake>`. `HUB_WRITE_CEILING` is a `ConflictError`.

- [ ] **Step 1: Write the failing tests** in `test_hub_api.py`:
  - one happy-path test per route;
  - `test_class_teacher_cannot_edit_centre_listing` (403);
  - `test_manager_can_edit_centre_listing_with_workspace_header`;
  - `test_listing_update_ceiling_is_50_per_day` (the 51st PUT gives 409 `HUB_WRITE_CEILING`);
  - `test_fee_is_a_json_string_only_when_shown`;
  - `test_unconsented_member_is_centre_faculty` (Review Focus 2);
  - `test_consent_route_refuses_pending_or_revoked_member`.

  In `test_hub_listing_probes.py`:
  - `test_teacher_a_cannot_read_or_write_teacher_b_listing`;
  - `test_no_hub_schema_contains_collection_number_or_phone`, which walks every `/v1/hub` and `/v1/batches/{batch_id}/listing*` response schema against `PUBLIC_FORBIDDEN_FIELDS`. `public_contact_phone` is the owner's opt-in field and is deliberately not in that set.
- [ ] **Step 2: Run** `pytest tests/hub tests/privacy -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the routes, schemas, lens and ceiling scope. Then run `make openapi` and update `message-keys.json`. The route gate needs no allowlist change: every route resolves a lens.
- [ ] **Step 4: Run** `make test`. Expected: PASS, including `test_route_lenses.py`, `test_privacy_schema.py`, `test_message_keys.py` and `test_schema_diff.py`.
- [ ] **Step 5: Commit** `feat(api): hub listing editor routes and centre member name consent`.

### Task 11: Reports, admin queue and suspension

**Files:**
- Create: `app/moderation/__init__.py`, `app/moderation/reports.py`, `app/moderation/suspension.py`, `app/schemas/moderation.py`
- Modify:
  - `app/api/hub.py` (report route);
  - `app/api/admin.py` (three routes);
  - `app/contract/routes.py` (`LENS_EXEMPT_AUTHENTICATED` +1 with reason, `PLATFORM_ADMIN_ROUTES` +3);
  - `app/auth/ceilings.py` (`HUB_REPORT_ACCOUNT_DAILY`);
  - `app/notifications/inbox.py` (kind `HUB_LISTING_SUSPENDED = "hub_listing_suspended"`, not in `LEGACY_KINDS`);
  - `message-keys.json`, `openapi.json`.
- Test: `tests/moderation/__init__.py`, `tests/moderation/test_reports.py`, `tests/moderation/test_suspension.py`

**Interfaces:**
- Produces:
  - `reports.file(session, account_id: UUID, target_kind: str, target_id: UUID, reason: str, note: str | None, now) -> None`;
  - `reports.queue(session, kind: Literal["report","listing"]) -> list[QueueItem]`, oldest first, with `waited_hours: int`;
  - `reports.decide(session, admin: PlatformAdminLens, report_id: UUID, decision: Literal["upheld","dismissed"], now) -> None`;
  - `suspension.set(session, admin, owner_id: UUID, suspended: bool, reason_code: str, now) -> None`. Suspending sets the owner listing to `suspended` and every published batch listing to `hidden`. It delivers `HUB_LISTING_SUSPENDED` to the owner's managing accounts (solo: `owner.account_id`; centre: accepted managers) with `batch_name=listing.public_name`, and writes a `hub_moderation_event`.
  - Routes:
    - `POST /v1/hub/reports`: lens-exempt authenticated, body `{target_kind, target_id, reason, note?}`, returns 202;
    - `GET /v1/admin/hub/queue?kind=report|listing`;
    - `POST /v1/admin/hub/reports/{report_id}/decision`;
    - `PUT /v1/admin/hub/owners/{owner_id}/suspension` (`{suspended: bool, reason_code}`).
  - The admin queue item for a report shows the target's text and the reason. It shows the reporter only as `reporter_ref`, the opaque label from `app/help/identity.py`, and never their phone or name.
  - New codes: `REPORT_ALREADY_FILED` (409), `REPORT_TARGET_NOT_FOUND` (404-equivalent `AuthorizationError`, identical for a missing target and a draft target).

- [ ] **Step 1: Write the failing tests:**
  - `test_report_never_changes_listing_status` (Review Focus 4).
  - `test_report_on_draft_or_missing_listing_is_identical_refusal`.
  - `test_second_report_same_target_is_conflict`.
  - `test_eleventh_report_in_a_day_is_ceiling`.
  - `test_report_note_with_phone_number_is_refused` (`HUB_TEXT_CONTAINS_CONTACT`).
  - `test_admin_queue_has_no_reporter_phone_or_name`, an OpenAPI schema walk plus a response probe.
  - `test_suspension_hides_batches_notifies_managers_and_logs_event`.
  - `test_unsuspend_returns_owner_listing_to_hidden_not_published`.
  - `test_non_admin_cannot_reach_admin_hub_routes`.
- [ ] **Step 2: Run** `pytest tests/moderation -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Update the comments above both allowlists with the new counts and reasons. `test_admin_contract.py`'s `walked == len(PLATFORM_ADMIN_ROUTES)` now walks 10.
- [ ] **Step 4: Run** `make test`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(moderation): hub reports, admin queue and listing suspension`.

### Task 12: Web — listing editor and admin moderation screens

**Files:**
- Create:
  - `web/src/features/teacher/hub/Listing.tsx`, `BatchListings.tsx`, `PublishSheet.tsx`, `hub.mappers.ts`, `hub.test.tsx`;
  - `web/src/admin/hub/Queue.tsx`, `Queue.test.tsx`.
- Modify: `web/src/api/endpoints.ts`, `web/src/api/schema.d.ts` (`npm run gen`), the teacher "More" navigation, the admin navigation, and the web string bundles (EN and BN) for every new key and label. Render `hub_listing_suspended` in the inbox.

**Interfaces:**
- Consumes: Task 10–11 routes.
- Produces: routes `/ui/more/hub` and `/ui/more/hub/batches`; admin route `/hub`.

- [ ] **Step 1: Write the failing tests** in `hub.test.tsx`:
  - `renders checklist from server and disables Publish until publishable`;
  - `publish sheet sends consent_version from the response`;
  - `shows suspended banner and read-only fields when status is suspended`;
  - `batch row shows Centre faculty from teacher_names`;
  - `fee is shown via the server money string, never parsed to a number`;
  - `a failed save shows retry and keeps the form` (TC-8).

  In `Queue.test.tsx`: `lists reports oldest first and suspends an owner after confirm`.
- [ ] **Step 2: Run** `cd web && npm test -- hub Queue`. Expected: FAIL.
- [ ] **Step 3: Implement** with the existing `claude_design/` components and tokens. Long Bangla titles wrap and are never truncated.
- [ ] **Step 4: Run** `make web`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(web): hub listing editor and admin hub queue`.

### Task 13: Android — listing editor

**Files:**
- Create: `android/src/main/kotlin/com/shikkhokplus/app/feature/hublisting/` (`HubListingScreen.kt`, `HubListingViewModel.kt`, `BatchListingsScreen.kt`, `HubApi.kt`, `HubModels.kt`)
- Modify:
  - the navigation graph and "More" menu;
  - `values/strings.xml`, `values-bn/strings.xml`;
  - the inbox renderer for `hub_listing_suspended`;
  - the client's announced notification kinds.
- Test: `android/src/test/kotlin/com/shikkhokplus/app/feature/hublisting/HubListingViewModelTest.kt`, `HubModelsSerializationTest.kt`

**Interfaces:**
- Consumes: Task 10 routes.
- Produces: `HubListingUiState` with `Loading | Editing(listing, checklist, publishable) | Suspended | Error(retryable)`, mapped from the response by `fun OwnerListingResponse.toUiState(): HubListingUiState`.

- [ ] **Step 1: Write the failing tests:**
  - `loading_then_editing_maps_checklist`;
  - `suspended_status_maps_to_read_only_state`;
  - `failed_save_exposes_retry_and_keeps_input`;
  - `publish_sends_server_consent_version`;
  - `fee_decodes_from_string_and_fails_loudly_on_json_number` (the serialization test).
- [ ] **Step 2: Run** `./gradlew testDebugUnitTest --tests '*hublisting*'`. Expected: FAIL.
- [ ] **Step 3: Implement** with Compose. The screen renders only server decisions (checklist, publishable, teacher names). Fields have Bangla and English tabs, as spec §4 of the design analysis describes.
- [ ] **Step 4: Run** `make android`. Expected: PASS, including detekt, ktlint, lint and the coverage ratchet.
- [ ] **Step 5: Commit** `feat(android): hub listing editor`.

### Task 14: Close-out

**Files:**
- Modify: `docs/legal/PRIVACY.md` (regenerated, if not already current), `CHANGELOG.md`.

- [ ] **Step 1: Run** `python3 -m scripts.generate_privacy_policy`, then `pytest tests/governance/test_policy_generation.py -v`. Expected: PASS.
- [ ] **Step 2: Add a `CHANGELOG.md` entry:** "Hub listings (not yet public): owners can prepare and publish a hub profile and batch listings; reports and admin suspension."
- [ ] **Step 3: Run** `make check`. Expected: every target green.
- [ ] **Step 4: Commit** `docs: changelog and privacy policy for hub listings`.
