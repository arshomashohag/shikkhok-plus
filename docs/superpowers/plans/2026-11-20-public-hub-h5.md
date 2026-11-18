# Public Hub H5 (Join Requests Through the App) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the optional hub unit H5, join requests through the app (`listing_enquiry`), behind a server-side switch that is off by default:
- an owner turns join requests on for their published listing, separately from publishing it;
- a signed-in guardian sends a request to join from a public page, about the owner or one of its batches;
- the guardian's phone number (or email address) reaches the owner only when the guardian ticks "share" on that request;
- the owner answers with one closed outcome, and can start the existing add-student form prefilled from the request;
- the guardian sees their requests, and withdraws any of them at any time, totally.

**Architecture:**
- **One table, one view.** Migration `0047` adds `listing_enquiry` and `owner_listing.accepts_enquiries`, and a new view `hub_public_enquirable` that names the published owners accepting requests. Public pages read that view as the hub reader, only to decide whether to print an "Ask to join" link.
- **A private channel, not a public surface.** Enquiries live in `app/hub/enquiries`. No public view, no administrator route and no report kind ever reads `listing_enquiry`. The owner reads it through `TeacherLens`; the guardian reads their own rows, scoped by account id in SQL.
- **Consent is a column, contact is read live.** `share_contact` has no default. The owner's response carries the guardian's verified phone (else email) from `account`, read at request time, only while `share_contact` is true and the row exists.
- **Acceptance is untouched.** The add-student form prefilled from a request creates a seat through the existing `create_student`, so the seat starts `pending` and the guardian still accepts it through invitations. H5 adds no acceptance transition, and a test-first test proves it.
- **The switch.** `SHIKKHOKPLUS_HUB_ENQUIRIES` gates every send, every owner read and the public link. It never gates a withdrawal, an account deletion or the purge.

**Tech Stack:**
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, Jinja2, pytest + testcontainers.
- Infra: Terraform (one SSM parameter); no CloudFront change (the link goes to the web app, not `/hub/*`).
- Clients: web React/TS; Android Kotlin/Compose.

**Spec:** `docs/superpowers/specs/2026-11-14-public-hub-design.md`. H5 is §1 "Optional: H5 Join requests through the app" and §3 `listing_enquiry optional (H5)`; it also touches §4 (public pages), §7 (API), §8 (privacy controls), §9 (no traffic counting) and §10 (the App Link pattern). The detail behind it, where the spec is silent:
- `docs/reviews/2026-11-14-public-hub/REPORT.md` §7.6 (four routes), the §8 abuse table ("Enquiries: 5 per day per account, 1 open per owner") and the H5 row of the delivery table ("Consented contact sharing. Lead inbox; accepting a lead pre-fills the add-student flow. Phone never shared without consent; rate limits");
- `team/product-requirements.md` HUB-FR-41 ("a signed-in adult account … the requester's name, the class, and a message of up to 300 characters … shares the requester's phone only after they consent explicitly. Accepting a lead pre-fills the existing add-student flow");
- `team/technical-design.md` §2.1 `listing_enquiry` (`share_contact BOOL (no default)`, `status (open, closed)`).

Where they and the spec disagree, the spec wins; where they disagree with each other, the call is recorded below.

**Built on H4** (`docs/superpowers/plans/2026-11-19-public-hub-h4.md` and its rulings in `.superpowers/sdd/2026-11-19-public-hub-h4/progress.md`). H4 is built before this plan starts, so these exist:
- **Switch pattern:** `app.hub.public.settings.reviews_enabled()`, `app/reviews/switch.py`, the `reviews_on` fixture in root `tests/conftest.py` (F3), the SSM parameter at `/shikkhokplus/${var.name_prefix}/hub-reviews` (F1), its `ses_param hub-reviews` read and `^(on|off)$` validation in `deploy.yml`, and `"hub-reviews": "off"` in `_RECORD_PARAMS` of `tests/gates/test_deploy_workflow.py` (F2).
- **Content check:** `app.reviews.content.contains_url(text: str) -> bool`.
- **Ceilings:** the non-committing consume pattern (`consume_hub_review_in_transaction`, F5).
- **Grants:** the app role reading public views (H4 Call 6).
- **Head:** Alembic head is `0046`. This plan adds `0047` only.
- **Message keys:** each task publishes the keys it raises, in the literal `message_key="…"` form (F4).

**Owner gates that this plan does not discharge (human steps, recorded in Task 10's runbook):**
- **Rule amendment.** `project.md` Forbidden reads "NEVER expose anything a student or guardian writes to any teacher, except a hub review its author explicitly submitted for public display". A join request is written by a guardian *to* a teacher, so the rule as worded forbids H5. It must be amended through the learnings ritual (as D3 amended it for reviews) before the switch is turned on. Proposed wording is in Task 10.
- **D6:** the Data Safety form and the Families declaration describe join requests before the switch is turned on.

The switch is how the code waits for both.

## Calls made in this plan

These are not owner decisions; correct any before execution.

1. **The switch.**
   - **Setting:** env `SHIKKHOKPLUS_HUB_ENQUIRIES`, on only for the exact value `on`; any other value, or none, is off.
   - **Source:** Terraform creates SSM `/shikkhokplus/${var.name_prefix}/hub-enquiries` with value `off` and `ignore_changes = [value]`. A person flips it, and the next deploy writes it into the runtime env.
   - **Routes:** every route is always registered, so the route, privacy and OpenAPI gates see one fixed surface. Gated routes answer a documented disabled response.
   - **Why:** the rule amendment above does not exist yet, so the code must ship dark.
2. **Guardians only, by declaration.** The spec has no age signal (D2 defers student reviews "behind an age signal"), and FR-41 says "a signed-in adult account". A request carries `declares_adult_guardian: Literal[True]` ("I am the student's parent or guardian, and 18 or older"). The declaration is required, not stored: every row is a guardian's request by construction. There is no student enquirer in V1.
3. **The owner opts in, separately from publishing.** `owner_listing.accepts_enquiries BOOLEAN NOT NULL DEFAULT false`. D1 made being listed opt-in; being messaged by strangers is a second thing an owner agrees to. Existing listings are unaffected.
4. **What an enquiry reveals to the owner, and when.** The owner's managers see, from the moment it is sent:
   - the student's name and class level as the guardian typed them for this request (`student_name`, `class_level`);
   - the optional message;
   - the batch it is about, by the batch's `public_title`;
   - when it was received.

   They see the guardian's contact only while `share_contact` is true: the account's verified `phone`, else its verified `email`, never both. It is read live from `account`, so a changed number shows the new one, and a withdrawn request shows nothing.

   They never see the account id, a profile field (`self_name`, address), the username, whether the guardian holds seats anywhere, or any other request.
5. **Contact travels only through the consent box.** `student_name` and `message` are refused with the existing `HUB_TEXT_CONTAINS_CONTACT` (`hub.text_contains_contact`, `details={"field": …}`) when they hold a phone number (`refuse_phone_in`) or a URL (`app.reviews.content.contains_url`). Otherwise a guardian who unticked "share" could still type the number, and the column would not mean what it says.
6. **No moderation, no administrator view, no report kind.** An enquiry is a private message to one owner, never published, so the pre-moderation rule (images and reviews) does not reach it. D4 lets an administrator see only content submitted *for publication*, so no admin route reads `listing_enquiry`. `hub_report_target` gains no label.
   - **The owner's protection** is: close a request, turn requests off, and the limits in Call 9. There is no block list in V1.
7. **The owner answers with a closed outcome, not text.** `POST …/close` takes `outcome`:
   - `added`: "You are being added. Accept the invitation when it arrives." Allowed only when `share_contact` is true, since without a contact the owner cannot seat anyone.
   - `not_now`: "The teacher cannot take this request now."
   - `call_us`: "Please call the teacher." Allowed only while the owner listing has a `public_contact_phone`; the guardian's view shows that published number.

   Any other combination answers 400 `ENQUIRY_OUTCOME_INVALID`. The guardian gets one inbox item. Owner free text to a family would be a new unmoderated channel and is not built.
8. **Accepting a lead pre-fills, nothing more.** The owner taps "Add as student". The client opens the existing add-student form with `?enquiry=<id>`; the form reads `GET /v1/hub/enquiries/{id}` and fills:
   - `display_name` from `student_name`;
   - `guardian_phone` or `guardian_email` from the shared contact;
   - the batch, from `batch_id`.

   After `POST /v1/students` succeeds, the client calls close with `added`. The seat starts `pending` as every new seat does ([ADR-013]: naming a number is never consent), and the guardian accepts through `/v1/invitations`. No server code path links an enquiry to a seat.
9. **Limits.**
   - **Daily:** `ScopeKind.HUB_ENQUIRY_DAILY = "hub_enquiry_day"`, `HUB_ENQUIRY_ACCOUNT_DAILY = 5`, consumed non-committingly. A refused send counts nothing.
   - **One open per owner:** a partial unique index `(owner_id, enquirer_account_id) WHERE status = 'open'` and `INSERT … ON CONFLICT DO NOTHING`, never a check-then-insert. To ask again before the owner answers, the guardian withdraws first.
   - **No cooldown** after a `not_now`; the daily cap bounds a resend loop.
10. **Lengths.** `message` is 1–300 characters after `strip()`, else NULL (FR-41; the technical design's 1000 was written for reviews). `student_name` is 1–80 after `strip()`.
11. **Retention: 90 days from sending, through the existing purge.**
    - A new `RetentionClass.DAYS_90`, with the age column `created_at`, so `app/governance/commands.py` purges `listing_enquiry` with no new job.
    - An unanswered request simply ages out; there is no expiry job.
    - A lead nobody acted on in three months is not worth keeping a child's name for.
12. **Deletion is total.** Withdrawal, the guardian's account deletion and a solo owner's account deletion each delete the rows *and* every inbox item whose `source_id` is the enquiry (both kinds, both parties).
    - A centre's requests survive a manager's deletion.
    - The 90-day purge deletes rows only; the inbox items it leaves carry a public title and an outcome code, nothing the guardian typed.
13. **Seven routes, not the REPORT's four.**
    - **Kept:** the four (send, list-mine, owner list, close).
    - **Added:**
      - `GET …/enquiry-target`, so the consent box can name who receives the number (informed consent needs the name);
      - `DELETE /v1/me/hub/enquiries/{id}`, because "delete at any time" needs a route;
      - `GET /v1/hub/enquiries/{id}`, which the prefilled add-student form reads (no phone number in a URL).
14. **The public link** is `{web_app_url}/ui/hub-enquiry?owner=<owner slug>` on an owner page and `…&batch=<batch id>` on a batch page (the batch id is already public as the report id).
    - **When shown:** only when the switch is on and the owner is in `hub_public_enquirable`. A batch page also needs `admissions <> 'closed'`.
    - **Android:** the App Link intent filter gains the path.
    - **Caching:** turning requests on or off rides the 10-minute TTL with no invalidation. A stale link leads to a form whose send is refused with `ENQUIRY_TARGET_NOT_FOUND`; no private data is involved (H3 ruling: additions ride the TTL).
15. **A new view rather than a changed one.** `hub_public_enquirable (owner_id, slug)` reads `hub_public_owner` joined to `owner_listing.accepts_enquiries`. Altering `hub_public_owner` would need `CREATE OR REPLACE` under two dependent views, and its downgrade cannot drop the column.
16. **The app role reads public views (H4 Call 6).**
    - **Grants:** `0047` grants `SELECT` on `hub_public_owner`, `hub_public_batch` and `hub_public_enquirable` to `shikkhok_app`.
    - **Use:** target checks and the guardian's view of a `call_us` number then use the same predicates the public pages use, with no `SET LOCAL ROLE` in a write transaction.
    - **Reach:** the app role already reads the base tables, so nothing new is reachable.
17. **Inbox kinds.** Neither is in `LEGACY_KINDS`, and neither preview carries anything the guardian typed or shared.
    - **`hub_enquiry_received`** goes to `managing_accounts(owner)`, with `batch_name` the batch's `public_title` (else the listing's `public_name`), `source_id` the enquiry id, and `preview` None. Closing marks every manager's copy read.
    - **`hub_enquiry_answered`** goes to the guardian, with the same `batch_name`, `preview` the outcome code, and `source_id` the enquiry id.
18. **No demand measure.** Spec §9 counts no visitor traffic. Enquiry counts are not added to the admin overview.

## Global Constraints

- **The switch (verbatim):**
  - **Setting:** `SHIKKHOKPLUS_HUB_ENQUIRIES`, read at each call by `app.hub.public.settings.enquiries_enabled() -> bool`. It is true only for the exact string `on`; unset, `ON`, `true`, `1` and ` on` are all off.
  - **Disabled response:** HTTP 404, `AuthorizationError(code="HUB_ENQUIRIES_OFF", message_key="hub.enquiry.off", status=404)`. Every gated route documents it in its OpenAPI `responses`.
  - **The off behaviour:**

  | Surface | When off |
  |---|---|
  | `GET …/enquiry-target`, `POST …/enquiries`, `GET /v1/hub/enquiries`, `GET /v1/hub/enquiries/{id}`, `POST …/close` | `HUB_ENQUIRIES_OFF` |
  | `GET /v1/me/hub/enquiries` | 200, the caller's own requests, so they can withdraw them |
  | `DELETE /v1/me/hub/enquiries/{id}`, account deletion, the retention purge | Work unchanged. **The switch never gates a deletion.** |
  | Public pages and the owner's preview | No "Ask to join" link |
  | `GET /v1/hub/listing` | `enquiries_offered = false`; `accepts_enquiries` is still stored by `PUT` |

  - **Ordering:** the switch dependency is listed in each gated route's decorator, so it runs before any lens, target or ownership check.
- **Who may send.** All of these, or one identical 404 `ENQUIRY_TARGET_NOT_FOUND` (`hub.enquiry.target_not_found`), which is also the answer for a slug that never existed:
  - the owner slug is in `hub_public_enquirable`;
  - a `batch_id`, if given, is a row of `hub_public_batch` with that `owner_slug` and `admissions <> 'closed'`;
  - the caller is not in `managing_accounts(owner)`.
- **Request body:** `EnquiryWrite{student_name: str, class_level: ClassLevel, message: str | None, batch_id: UUID | None, share_contact: bool, declares_adult_guardian: Literal[True]}`.
  - `share_contact` has no default, so omitting it is a 422.
  - `ClassLevel` is `app.schemas.hub.ClassLevel`.
  - The lengths are in Call 10, and contact refusal is in Call 5.
- **Contact predicate (test-first).** An owner-side response carries `guardian_phone` = `account.phone` and `guardian_email` = NULL when the account has a phone. It carries `guardian_email` = `account.email` only when the phone is NULL. Both are NULL unless `share_contact` is true.
- **New error codes:**

  | Code | Status | Class | Message key |
  |---|---|---|---|
  | `HUB_ENQUIRIES_OFF` | 404 | `AuthorizationError` | `hub.enquiry.off` |
  | `ENQUIRY_TARGET_NOT_FOUND` | 404 | `AuthorizationError` | `hub.enquiry.target_not_found` |
  | `ENQUIRY_ALREADY_OPEN` | 409 | `ConflictError` | `hub.enquiry.already_open` |
  | `HUB_ENQUIRY_CEILING` | 409 | `CeilingBreach` | `hub.enquiry.ceiling` |
  | `ENQUIRY_NOT_FOUND` | 404 | `AuthorizationError` | `hub.enquiry.not_found` |
  | `ENQUIRY_ALREADY_CLOSED` | 409 | `ConflictError` | `hub.enquiry.already_closed` |
  | `ENQUIRY_OUTCOME_INVALID` | 400 | `ValidationError` | `hub.enquiry.outcome_invalid` |

  Contact in text reuses the registered `HUB_TEXT_CONTAINS_CONTACT`.
- **Route counts:**
  - `PUBLIC_ROUTES` stays **19**, and `PUBLIC_CACHEABLE_ROUTES` stays **4**.
  - `LENS_EXEMPT_AUTHENTICATED` gains exactly four entries:
    - `("GET", "/v1/hub/owners/{owner_slug}/enquiry-target")`;
    - `("POST", "/v1/hub/owners/{owner_slug}/enquiries")`;
    - `("GET", "/v1/me/hub/enquiries")`;
    - `("DELETE", "/v1/me/hub/enquiries/{enquiry_id}")`.
  - There are three new `TeacherLens` routes: `GET /v1/hub/enquiries`, `GET /v1/hub/enquiries/{enquiry_id}` and `POST /v1/hub/enquiries/{enquiry_id}/close`.
  - `PLATFORM_ADMIN_ROUTES` stays **14**.
- **Public data sources:** public handlers read only these eight views, under `as_hub_reader`:
  - H3's five;
  - H4's `hub_public_review` and `hub_public_rating`;
  - `hub_public_enquirable` (new).

  The hub reader cannot `SELECT` `listing_enquiry`. `app/hub/public/**` never imports `app.hub.enquiries`; the existing allowlist gate enforces it.
- **Never in any enquiry response, page, inbox preview or log line:**
  - `enquirer_account_id` or any account id;
  - `self_name`, `username`, an address field;
  - the guardian's contact, except as the contact predicate allows on owner-side responses.

  `student_name`, `message` and the contact are never logged at any level.
- **Carried from H3/H4:**
  - **Backend gate:** every task runs `python -m ruff check app tests`, `python -m ruff format --check app tests`, `python -m mypy app` and its pytest directories, plus `tests/contract` whenever a migration, `DISPOSITIONS`, a route or a schema changes.
  - **Restricted role:** integration tests connect as `restricted_session`.
  - **Test-first:** every authorization-predicate case is written first: who may send, owner scoping, the contact predicate, the guardian's own-row scoping, and the seat staying `pending`.
  - **Migrations:** head pins move in all four files: `tests/db/test_migration_head_pin.py`, `test_migration_from_head.py`, `test_migration_runs.py` and `tests/auth/test_endpoints.py`.
  - **Generated files are regenerated, never hand-edited:** `openapi.json` via `make openapi`; `web/src/api/schema.d.ts` via `cd web && npm run gen:api`; `web/src/i18n/generated/*` via `cd web && node scripts/sync-strings.mjs`; `docs/legal/PRIVACY.md` via `python3 -m scripts.generate_privacy_policy`.
  - **Strings:** new strings start in Android `values/` and `values-bn/`, plus `message-keys.json` and `android/src/main/kotlin/com/shikkhokplus/app/feature/auth/MessageKeys.kt`. Public-page strings go in `app/hub/public/messages.py`. Copy is EN and BN, with Latin digits. Bangla wording is a human check.
  - **Android routes:** every new Android action is wired through its navigation route and proven by a route-level test.
  - **Counts:** a comment that states a count is asserted by a test.
  - **Bangla layout:** every new screen gets a row in `docs/delivery/bangla-layout-check.md`.
  - **Commits:** conventional, ending with the `Co-Authored-By` trailer.

## Review Focus

1. **The guardian unticks "share" and still types their number**, as `০১৭১২৩৪৫৬৭৮` in the message, `017 1234 5678` in the student name, or `wa.me/8801712345678`.
   - Each is refused, and nothing is stored or counted.
   - Ordinary text passes: "Class 8, wants Physics and Maths", "can come after 4.30 pm".

   Test: Task 3 `test_contact_in_text_refused_both_ways` (parametrised).
2. **The listing changes between page render and send.** The owner unpublishes, is suspended, turns requests off, or closes the batch's admissions. Other bad targets: a `batch_id` of another owner, and the caller being the owner's own manager.
   - Each answers the same `ENQUIRY_TARGET_NOT_FOUND` status and body bytes as a slug that never existed.

   Test: Task 3 `test_unenquirable_targets_answer_identically`.
3. **Two devices send the first request at once.**
   - Exactly one open row exists afterwards.
   - The other call gets `ENQUIRY_ALREADY_OPEN`.
   - The daily counter moved once.

   Test: Task 3 `test_concurrent_sends_make_one_open_enquiry`.
4. **The guardian withdraws a request the owner has already received and answered.**
   - The row, the owners' `hub_enquiry_received` items and the guardian's `hub_enquiry_answered` item are gone.
   - The owner's `GET /v1/hub/enquiries/{id}` answers `ENQUIRY_NOT_FOUND`.
   - All of this also works with the switch off.

   Test: Task 3 `test_withdraw_is_total`; Task 5 `test_gated_routes_answer_enquiries_off_and_withdraw_still_works`.
5. **The owner adds the student from a request.** The new seat links to the guardian's account with `guardian_decision = 'pending'`; the guardian holds an invitation lens and no guardian lens until they accept.

   Test: Task 4 `test_student_added_from_enquiry_starts_pending`.

---

### Task 1: The enquiries switch

**Files:**
- Create: `app/hub/enquiries/__init__.py`, `app/hub/enquiries/switch.py`
- Modify:
  - `app/hub/public/settings.py`: `HUB_ENQUIRIES_ENV = "SHIKKHOKPLUS_HUB_ENQUIRIES"` and `enquiries_enabled()`.
  - `message-keys.json`, both Android bundles and `MessageKeys.kt`: add `hub.enquiry.off`. Then run `cd web && node scripts/sync-strings.mjs`.
  - `docker-compose.yml` and `deploy/docker-compose.staging.yml`: `SHIKKHOKPLUS_HUB_ENQUIRIES: ${SHIKKHOKPLUS_HUB_ENQUIRIES:-off}`.
  - `infra/modules/app/deployment_state.tf`: `aws_ssm_parameter.hub_enquiries`, named `/shikkhokplus/${var.name_prefix}/hub-enquiries`, type `String`, value `"off"`, `lifecycle { ignore_changes = [value] }`.
  - `.github/workflows/deploy.yml`, beside H4's `hub-reviews` read:
    - `HUB_ENQUIRIES=$(ses_param hub-enquiries)`;
    - stop unless the value matches `^(on|off)$`, with the same "Nothing has been recorded or rolled" wording;
    - `echo "SHIKKHOKPLUS_HUB_ENQUIRIES=${HUB_ENQUIRIES}"` into `runtime.env`.
  - `tests/gates/test_deploy_workflow.py`: `_RECORD_PARAMS` gains `"hub-enquiries": "off"`.
  - `deploy/README.md`: an env-table row.
  - `infra/README.md`: a "Switching join requests on" runbook stub (Task 10 completes it).
  - `tests/conftest.py`: the `enquiries_on` fixture (monkeypatch setenv `on`), beside `reviews_on`.
- Test: `tests/enquiries/__init__.py`, `tests/enquiries/test_switch.py`, `tests/gates/test_hub_enquiries_switch_infra.py`

**Interfaces:**
- Produces:
  - `app.hub.public.settings.enquiries_enabled() -> bool`.
  - `app.hub.enquiries.switch.enquiries_off() -> AuthorizationError` (the verbatim disabled response).
  - `app.hub.enquiries.switch.require_enquiries_on() -> None`, a FastAPI dependency.
  - `app.hub.enquiries.switch.ENQUIRIES_OFF_RESPONSES: dict[int | str, dict[str, Any]]`: the 404 `ErrorEnvelope` entry, described "Join requests are switched off (HUB_ENQUIRIES_OFF)".
  - The root fixture `enquiries_on`.

- [ ] **Step 1: Write the failing tests:**
  - `test_off_when_unset`.
  - `test_on_only_for_exact_value`, parametrised `on` → True; `ON`, `On`, `true`, `1`, ` on`, `on `, `yes` and `""` → False.
  - `test_read_at_each_call`.
  - `test_require_enquiries_on_raises_documented_error` (code, status 404, message key).
  - `test_message_key_published`.
  - `test_switches_are_independent`: reviews on with enquiries off, and the reverse.
  - Gates:
    - `test_ssm_switch_parameter_defaults_off_and_ignores_value`;
    - `test_deploy_validates_switch_value_and_writes_it`;
    - `test_both_compose_files_forward_switch_defaulting_off`.
- [ ] **Step 2: Run** `pytest tests/enquiries/test_switch.py tests/gates/test_hub_enquiries_switch_infra.py tests/gates/test_compose_forwards_runtime_env.py tests/gates/test_deploy_workflow.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** on the H4 Task 1 pattern. Run `terraform fmt -check -recursive infra`, then `validate` through the scratch provider mirror.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/enquiries tests/gates tests/contract`) and `cd web && npm run check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(enquiries): server-side join-request switch, off by default`.

### Task 2: Enquiry data, the enquirable view, dispositions and retention (0047)

**Files:**
- Create: `migrations/versions/0047_listing_enquiry.py`
- Modify:
  - `app/db/models.py`:
    - `ListingEnquiry`, `HUB_ENQUIRY_STATUS_VALUES = ("open", "closed")` and `HUB_ENQUIRY_OUTCOME_VALUES = ("added", "not_now", "call_us")`;
    - `OwnerListing.accepts_enquiries`.
  - `app/governance/dispositions.py`: `RetentionClass.DAYS_90 = "90_days"` and the `listing_enquiry` entry.
  - `app/governance/commands.py`: `_CLASS_AGE[DAYS_90] = timedelta(days=90)` and `_AGE_COLUMN["listing_enquiry"] = "created_at"`.
  - `scripts/generate_privacy_policy.py`: `_RETENTION_TEXT[DAYS_90] = "90 days"`.
  - `app/governance/deletion.py`: `HARD_DELETE_SCOPES["listing_enquiry"]`.
  - The four head pins.
  - `tests/privacy/test_hub_public_views.py`: `test_hub_reader_reads_only_the_eight_views`.
  - `tests/privacy/test_hub_reader_meta.py`: `listing_enquiry` joins the refused list.
- Test: `tests/db/test_migration_0047.py`, `tests/privacy/test_hub_public_enquirable_view.py`, `tests/governance/test_enquiry_retention.py`

**Interfaces:**
- Produces:
  - **`owner_listing.accepts_enquiries`:** `BOOLEAN NOT NULL DEFAULT false`.
  - **`listing_enquiry`:**
    - **Keys and links:**
      - `id UUID PK DEFAULT gen_random_uuid()`;
      - `owner_id FK owner ON DELETE CASCADE NOT NULL`;
      - `batch_id FK batch_listing(batch_id) ON DELETE SET NULL NULL`;
      - `enquirer_account_id FK account ON DELETE CASCADE NOT NULL`.
    - **Content:**
      - `student_name TEXT NOT NULL`, CHECK `char_length(btrim(student_name)) BETWEEN 1 AND 80`;
      - `class_level VARCHAR(20) NOT NULL`, CHECK `IN HUB_CLASS_LEVELS`;
      - `message TEXT NULL`, CHECK `message IS NULL OR char_length(message) BETWEEN 1 AND 300`;
      - `share_contact BOOLEAN NOT NULL`, with **no default**.
    - **State:**
      - `status hub_enquiry_status NOT NULL DEFAULT 'open'`;
      - `outcome hub_enquiry_outcome NULL`;
      - `created_at timestamptz NOT NULL`;
      - `closed_at timestamptz NULL`.
    - **Constraints:**
      - CHECK `(status = 'closed') = (outcome IS NOT NULL)`;
      - CHECK `(status = 'closed') = (closed_at IS NOT NULL)`;
      - CHECK `outcome IS DISTINCT FROM 'added' OR share_contact`.
    - **Indexes:**
      - partial UNIQUE `uq_listing_enquiry_open (owner_id, enquirer_account_id) WHERE status = 'open'`;
      - `ix_listing_enquiry_owner_created (owner_id, created_at)`;
      - `ix_listing_enquiry_enquirer (enquirer_account_id)`.
  - **`hub_public_enquirable`** (`security_barrier`): `SELECT o.owner_id, o.slug FROM hub_public_owner o JOIN owner_listing l ON l.owner_id = o.owner_id WHERE l.accepts_enquiries`.
  - **Grants:**
    - `shikkhok_app`: CRUD on `listing_enquiry`, and `SELECT` on `hub_public_owner`, `hub_public_batch` and `hub_public_enquirable` (Call 16);
    - `shikkhok_hub_reader`: `SELECT` on `hub_public_enquirable` only.
  - **Disposition:** `listing_enquiry`: `HARD_DELETE`, `DAYS_90`, with the basis:

    > A request to join that a signed-in guardian sent to a teacher or centre: the student's name and class as they typed them, an optional message, and whether they chose to share their phone number or email address, which is read from their account only while the request exists and only if they chose. Seen only by the people who run that listing; never public, never shown to platform administrators. It goes when the guardian withdraws it or deletes their account, when a solo teacher deletes theirs, and 90 days after it was sent in any case.

  - **Scope:** `HARD_DELETE_SCOPES["listing_enquiry"] = _Target(scope=ACCOUNT_COLUMN, column="enquirer_account_id", note=…)`. The note says the solo-owner side and the inbox items are removed first by `app.hub.enquiries.forget` (Task 7).

- [ ] **Step 1: Write the failing tests (test-first: view visibility decides who may be messaged):**
  - `test_0047_creates_table_enums_view_and_column` (enum labels exact and in order; `accepts_enquiries` defaults false on existing rows).
  - `test_share_contact_has_no_default` (an insert omitting it raises).
  - `test_closed_needs_outcome_and_time`, `test_added_needs_shared_contact`, `test_one_open_per_owner_and_account` (a second open row raises; a closed one beside it does not).
  - `test_enquirable_view_lists_only_published_accepting_owners`, parametrised over draft, hidden, suspended and `accepts_enquiries = false` → absent.
  - `test_enquirable_view_never_depends_on_private_columns`: via `pg_depend`, the view depends on no column but `owner_listing.accepts_enquiries` and `owner_listing.owner_id`, apart from what it reads through `hub_public_owner`.
  - `test_hub_reader_reads_only_the_eight_views` and `test_hub_reader_cannot_read_private_tables[listing_enquiry]`.
  - `test_app_role_can_select_the_three_public_views`.
  - `test_enquiry_disposition_and_retention`: the entry exists, `RETENTION["listing_enquiry"] is DAYS_90`, and `WINDOWS["listing_enquiry"].keep_for == timedelta(days=90)`.
  - `test_enquiries_purged_after_90_days`: rows at 89 and 91 days, open and closed; `purge_expired` removes only the 91-day rows.
  - `test_downgrade_refuses_while_enquiries_exist`.
- [ ] **Step 2: Run** `pytest tests/db/test_migration_0047.py tests/privacy tests/governance -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - The migration follows 0043's `CREATE VIEW … WITH (security_barrier)` and grant pattern.
  - The downgrade refuses while any `listing_enquiry` row exists, then drops the view, the table, both enums and the column.
  - Add the model, then move the head pins.
  - Run `python3 -m scripts.generate_privacy_policy`.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/db tests/privacy tests/governance tests/contract`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(enquiries): listing_enquiry, the enquirable view and 90-day retention (0047)`.

### Task 3: Sending, reading and withdrawing — the guardian's side (test-first)

**Files:**
- Create: `app/hub/enquiries/target.py`, `app/hub/enquiries/sending.py`, `app/hub/enquiries/forget.py`
- Modify:
  - `app/auth/ceilings.py`: `HUB_ENQUIRY_ACCOUNT_DAILY = 5`, `ScopeKind.HUB_ENQUIRY_DAILY = "hub_enquiry_day"`, `consume_hub_enquiry_in_transaction`, and the `CeilingBreach` mapping to `HUB_ENQUIRY_CEILING` / `hub.enquiry.ceiling`.
  - `app/notifications/inbox.py`: `HUB_ENQUIRY_RECEIVED = "hub_enquiry_received"` and `HUB_ENQUIRY_ANSWERED = "hub_enquiry_answered"`. Neither is legacy.
  - `message-keys.json`, both Android bundles and `MessageKeys.kt`: `hub.enquiry.target_not_found`, `hub.enquiry.already_open`, `hub.enquiry.ceiling`. Then run sync-strings.
  - `tests/named_tests.toml`: one entry per boundary test marked † below, with its criterion and the rule `H5 Global Constraints`.
- Test: `tests/enquiries/support.py`, `tests/enquiries/test_target.py`, `tests/enquiries/test_sending.py`, `tests/enquiries/test_forget.py`

**Interfaces:**
- Consumes: `managing_accounts` and `refuse_phone_in` from `app.hub.listings.shared`; `app.reviews.content.contains_url`; `inbox.deliver` and `inbox.remove_for_source`.
- Produces:
  - **`tests/enquiries/support.py`:** `enquirable_owner(session, *, centre: bool = False, accepts: bool = True, admissions: str = "open") -> EnquirableWorld`.
    - `EnquirableWorld` is a frozen dataclass with `lens: TeacherLens`, `owner_slug: str`, `batch_id: UUID`, `batch_title: str` and `manager_ids: list[UUID]`.
    - It builds a published owner listing and one published batch, using `tests/hub/support.py` helpers.
    - `guardian(session, *, phone: str | None = "01712345678", email: str | None = None) -> UUID` makes a verified account.
  - **`target.Target`** (a frozen dataclass): `owner_id`, `owner_slug`, `owner_public_name`, `batch_id: UUID | None`, `batch_title: str | None`.
  - **`target.resolve(session, account_id, owner_slug, batch_id) -> Target`:** applies the Global Constraints "who may send" through `hub_public_enquirable` and `hub_public_batch`. It raises the one `ENQUIRY_TARGET_NOT_FOUND`, built by `target.not_found()`.
  - **`sending.EnquiryTarget`:** `owner_public_name`, `batch_title`, `contact_kind: Literal["phone","email"]` (from the caller's account), `already_open: bool`.
  - `sending.describe(session, account_id, owner_slug, batch_id) -> EnquiryTarget`.
  - **`sending.MyEnquiry`** (a frozen dataclass): `id`, `owner_public_name`, `batch_title`, `student_name`, `class_level`, `message`, `share_contact`, `status`, `outcome`, `sent_on: date` (Dhaka), `owner_contact_phone: str | None`.
    - `owner_contact_phone` is the listing's published `public_contact_phone`, read from `hub_public_owner`, set only when `outcome == "call_us"`.
  - **`sending.send(session, account_id, owner_slug, *, student_name, class_level, message, batch_id, share_contact, now) -> MyEnquiry`:**
    1. Strip; empty `message` → None.
    2. `refuse_phone_in([("student_name", …), ("message", …)])`, then the same `HUB_TEXT_CONTAINS_CONTACT` for `contains_url` on either.
    3. `target.resolve`.
    4. `CeilingChecker(session).consume_hub_enquiry_in_transaction(account_id, now)`.
    5. `INSERT … ON CONFLICT (owner_id, enquirer_account_id) WHERE status = 'open' DO NOTHING RETURNING id`. No row → `ENQUIRY_ALREADY_OPEN`, raised so the caller's rollback un-counts the ceiling.
    6. `deliver(kind=HUB_ENQUIRY_RECEIVED, account_ids=managing_accounts(owner), batch_name=batch_title or owner_public_name, source_id=id, preview=None)`.
    7. Commit.
  - `sending.mine(session, account_id) -> list[MyEnquiry]`: the caller's rows only, newest first, at most 50.
  - `sending.withdraw(session, account_id, enquiry_id) -> None`: `forget.forget(session, [ids owned by the caller])`, then commit. A foreign or missing id changes nothing and is not an error (an idempotent DELETE).
  - **`forget.forget(session, enquiry_ids: list[UUID]) -> None`:** for each kind in `(HUB_ENQUIRY_RECEIVED, HUB_ENQUIRY_ANSWERED)`, `remove_for_source` per id; then `DELETE FROM listing_enquiry WHERE id = ANY(:ids)`. It commits nothing.

- [ ] **Step 1: Write the failing tests, before any implementation** (a wrong answer here messages a stranger or leaks a number). Each test runs as the restricted role.
  - † `test_unenquirable_targets_answer_identically` (Review Focus 2). The cases, each compared to a never-existing slug by status and body bytes:
    - owner draft, hidden or suspended;
    - `accepts_enquiries` false;
    - the batch is closed;
    - the batch belongs to another owner;
    - the batch is unpublished;
    - the caller is a centre manager of the owner;
    - the caller is a solo owner's own account.
  - `test_waitlist_batch_accepts`.
  - † `test_contact_in_text_refused_both_ways` (Review Focus 1, parametrised: refused and passing cases; a refusal leaves no row and no counter row).
  - `test_send_stores_typed_fields_and_notifies_every_manager` (centre with two managers; `preview` is None and `batch_name` is the batch's `public_title`).
  - † `test_concurrent_sends_make_one_open_enquiry` (Review Focus 3: two sessions, a Barrier).
  - `test_send_after_close_opens_a_new_one`.
  - `test_sixth_send_in_a_day_hits_ceiling` and `test_refused_send_consumes_nothing`.
  - `test_describe_names_target_and_contact_kind` (phone-only → `phone`; email-only → `email`; `already_open` true after a send).
  - † `test_mine_lists_only_own_rows` (two guardians, two owners).
  - `test_call_us_shows_published_number_and_hides_it_after_unpublish`.
  - † `test_withdraw_is_total` (Review Focus 4: an answered request; afterwards no `listing_enquiry` row and no `notification` row with that `source_id` remains, for either party).
  - `test_withdraw_foreign_or_missing_id_changes_nothing` (another guardian's row survives).
- [ ] **Step 2: Run** `pytest tests/enquiries -q`. Expected: FAIL. Keep the RED output for the reviewer.
- [ ] **Step 3: Implement.** No Python loop decides who may send; `resolve` is one SQL statement.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/enquiries tests/auth tests/notifications tests/contract`, and `pytest tests/test_named_test_manifest.py`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(enquiries): guardians send, read and withdraw join requests`.

### Task 4: The owner's inbox — list, read, close (test-first)

**Files:**
- Create: `app/hub/enquiries/owner.py`
- Modify:
  - `message-keys.json`, both bundles and `MessageKeys.kt`: `hub.enquiry.not_found`, `hub.enquiry.already_closed`, `hub.enquiry.outcome_invalid`. Then run sync-strings.
  - `tests/named_tests.toml`: entries for the † tests.
- Test: `tests/enquiries/test_owner.py`, `tests/enquiries/test_add_from_enquiry.py`, `tests/gates/test_enquiries_imports.py`

**Interfaces:**
- Consumes: `forget`, the inbox kinds and `support` (Task 3); `inbox.mark_read_for_source`.
- Produces:
  - **`owner.OwnerEnquiry`** (a frozen dataclass): `id`, `batch_id: UUID | None`, `batch_title: str | None`, `student_name`, `class_level`, `message`, `status`, `outcome`, `received_at: datetime`, `guardian_phone: str | None`, `guardian_email: str | None`, `outcomes_allowed: list[str]`.
    - The contact fields follow the contact predicate, computed in the SELECT with a `CASE WHEN e.share_contact` over a join to `account`.
    - `outcomes_allowed` is empty for a closed request; otherwise `not_now`, plus `added` when `share_contact`, plus `call_us` when the owner listing has a `public_contact_phone`. The clients render actions from it and decide nothing.
  - **`owner.list_for(session, lens: TeacherLens) -> list[OwnerEnquiry]`:** `WHERE e.owner_id = :lens_owner`, open first, then `created_at DESC`, at most 100.
  - **`owner.get(session, lens, enquiry_id) -> OwnerEnquiry`:** the same statement with the id. A missing or foreign id raises the one `ENQUIRY_NOT_FOUND` (404).
  - **`owner.close(session, lens, enquiry_id, outcome: Literal["added","not_now","call_us"], now) -> OwnerEnquiry`:**
    1. Lock the row `FOR UPDATE` where `id` and `owner_id = lens.owner_id`. None → `ENQUIRY_NOT_FOUND`; `status = 'closed'` → `ENQUIRY_ALREADY_CLOSED`.
    2. `added` without `share_contact`, or `call_us` while the owner listing's `public_contact_phone` is NULL → `ENQUIRY_OUTCOME_INVALID`.
    3. Set `status`, `outcome` and `closed_at`.
    4. Deliver `HUB_ENQUIRY_ANSWERED` to the enquirer (preview: the outcome).
    5. `mark_read_for_source(kind=HUB_ENQUIRY_RECEIVED, source_id=id, now=now)`.
    6. Commit.

    A suspended listing does not block closing.
  - **Gate `test_enquiries_package_imports_nothing_private`:** `app/hub/enquiries/**` imports nothing from `app.students`, `app.fees`, `app.marks`, `app.guardians`, `app.authz.invitations` or `app.accounts.decisions`. This is the mechanical form of "no server path links an enquiry to a seat".

- [ ] **Step 1: Write the failing tests first** (owner scoping and the contact predicate are authorization predicates):
  - † `test_contact_shared_only_with_consent`. The table:

    | Account contacts | `share_contact` | `guardian_phone` | `guardian_email` |
    |---|---|---|---|
    | phone + email | false | None | None |
    | phone + email | true | the phone | None |
    | email only | true | None | the email |

    Asserted on `list_for` and on `get`. The guardian's inbox items and the owner's `preview` never contain the contact.
  - `test_contact_is_read_live` (the guardian's verified number changes, and the owner sees the new one).
  - † `test_other_owner_cannot_list_read_or_close`: teacher B's `get` and `close` on A's id answer the same bytes as a random id; B's `list_for` excludes it.
  - `test_centre_managers_share_one_inbox` (both managers list it; a centre teacher-role member has no `TeacherLens` route access, which Task 5 covers).
  - `test_close_outcomes` (each outcome; the guardian gets `hub_enquiry_answered` with the outcome as preview; every manager's received item is marked read).
  - `test_added_without_contact_and_call_us_without_public_phone_invalid`, and `test_outcomes_allowed_matches_close_rules` (for every combination, an outcome is listed exactly when `close` accepts it).
  - `test_second_close_is_already_closed`.
  - † `test_student_added_from_enquiry_starts_pending` (Review Focus 5, the acceptance predicate):
    1. A guardian sends with `share_contact`.
    2. The owner's `get` gives the prefill values.
    3. `app.students.service.create_student(lens=…, display_name=student_name, guardian_phone=guardian_phone, seats=[SeatRequest(batch_id)])`.
    4. `owner.close(…, "added")`.

    Then:
    - the new seat has `guardian_account_id` equal to the guardian and `guardian_decision == "pending"`;
    - `available_invitations(session, guardian)` lists it;
    - `available_lenses(session, guardian)` holds no `GuardianLens` until `accept_seat`.
  - † `test_enquiry_changes_no_seat` (sending, closing with each outcome, and withdrawing leave every `enrollment` row byte-identical).
  - The import gate.
- [ ] **Step 2: Run** `pytest tests/enquiries tests/gates/test_enquiries_imports.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the gate (backend set, plus `tests/enquiries tests/gates tests/students tests/notifications`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(enquiries): the owner's join-request inbox and closed outcomes`.

### Task 5: Enquiry API routes, contract and notification kinds

**Files:**
- Create: `app/schemas/enquiries.py`, `app/api/hub_enquiries.py`
- Modify:
  - `app/main.py`: include the router (it registers in `app.state.included_routers`).
  - `app/contract/routes.py`: the four `LENS_EXEMPT_AUTHENTICATED` entries, each with a reasoning comment on the `/v1/hub/reports` pattern:
    - the two `/v1/hub/owners/{owner_slug}/…` routes act as the authenticated account, reach only a published owner that chose to accept requests, and answer every other target identically;
    - the two `/v1/me/hub/enquiries` routes are scoped by account id in SQL.
  - `tests/contract/test_route_lenses.py`: the exact-set assertion.
  - `app/contract/privacy.py`:
    - `ENQUIRY_FORBIDDEN_FIELDS = OWNER_PRIVATE_FIELDS | FORBIDDEN_ACCOUNT_ID_FIELDS | {"enquirer_account_id", "self_name", "phone", "email", "student_phone", "display_name"}`;
    - `ENQUIRY_ROUTES` (the seven);
    - `enquiry_field_leaks(app) -> list[tuple[str, str, str]]`, which walks every 2xx response of `ENQUIRY_ROUTES`.
  - `app/schemas/notifications.py`: the `kind` Literal gains both kinds. `app/api/notifications.py`: the kind maps.
  - `openapi.json` and `web/src/api/schema.d.ts`, both generated.
- Test: `tests/enquiries/test_enquiry_routes.py`, `tests/contract/test_enquiry_privacy.py`, `tests/privacy/test_enquiry_probes.py`

**Interfaces:**
- **Routes:**
  - `GET /v1/hub/owners/{owner_slug}/enquiry-target?batch_id=` (exempt, gated) → `EnquiryTargetResponse{owner_public_name, batch_title, contact_kind, already_open}`.
  - `POST /v1/hub/owners/{owner_slug}/enquiries` (exempt, gated, 201) takes `EnquiryWrite`:
    - `student_name: str = Field(min_length=1, max_length=80)`;
    - `class_level: ClassLevel`;
    - `message: str | None = Field(default=None, max_length=300)`;
    - `batch_id: UUID | None = None`;
    - `share_contact: bool` (required);
    - `declares_adult_guardian: Literal[True]`.

    Both strings use `StringConstraints(strip_whitespace=True, …)` (H4 F14). It returns `MyEnquiryWire`.
  - `GET /v1/me/hub/enquiries` (exempt, not gated) → `list[MyEnquiryWire{id, owner_public_name, batch_title, student_name, class_level, message, share_contact, status, outcome, sent_on, owner_contact_phone}]`.
  - `DELETE /v1/me/hub/enquiries/{enquiry_id}` (exempt, not gated) → 204.
  - `GET /v1/hub/enquiries` (TeacherLens, gated) → `list[OwnerEnquiryWire]`, with the `OwnerEnquiry` fields.
  - `GET /v1/hub/enquiries/{enquiry_id}` (TeacherLens, gated) → `OwnerEnquiryWire`.
  - `POST /v1/hub/enquiries/{enquiry_id}/close` (TeacherLens, gated) takes `EnquiryClose{outcome: Literal["added","not_now","call_us"]}` → `OwnerEnquiryWire`.
- **Wire rules:**
  - Gated routes list `dependencies=[Depends(require_enquiries_on)]` in the decorator.
  - Every write route rolls back the session on any non-taxonomy exception (H3 Task 5 carry).
  - Each route's `responses=` documents its codes from the Global Constraints table.
  - The correlation id is never paired with an enquiry field in a log line.

- [ ] **Step 1: Write the failing tests:**
  - `test_lens_exempt_set_exact` (the four entries) and `test_teacher_enquiry_routes_resolve_teacher_lens`.
  - `test_gated_routes_answer_enquiries_off_and_withdraw_still_works` (Review Focus 4):
    - with the switch off, every gated route answers 404 `HUB_ENQUIRIES_OFF` to an authenticated caller, before any target or ownership check (a foreign enquiry id gets the same answer as an owned one);
    - `GET /v1/me/hub/enquiries` lists and `DELETE` removes.
  - `test_off_response_documented_in_openapi`.
  - `test_end_to_end_send_answer_withdraw` (with `enquiries_on`).
  - `test_missing_share_contact_or_false_declaration_is_422`.
  - `test_error_envelopes_for_new_codes`: status, code and message_key for each row of the table.
  - `test_teacher_routes_refuse_centre_teacher_student_and_guardian_lenses`.
  - Probes (`tests/privacy/test_enquiry_probes.py`):
    - teacher B reading or closing A's enquiry gets the same body as a random id;
    - guardian B deleting A's id leaves A's row;
    - no admin route returns any `listing_enquiry` column, and `PLATFORM_ADMIN_ROUTES` still counts 14.
  - `test_no_enquiry_response_carries_identity_fields` (`enquiry_field_leaks(app) == []`), plus a fixture route returning `enquirer_account_id` that the gate catches (non-vacuous).
  - `test_inbox_renders_both_kinds_for_announcing_clients_only`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Then run `make openapi` and `cd web && npm run gen:api`.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/enquiries tests/contract tests/privacy tests/notifications tests/gates`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(api): join-request routes for guardians and owners`.

### Task 6: Owner opt-in and the "Ask to join" link on public pages

**Files:**
- Modify:
  - `app/hub/listings/owner.py`: `OwnerListingUpdate.accepts_enquiries: bool | None = None`, written by `update`.
  - `app/schemas/hub.py`:
    - `OwnerListingUpdateRequest.accepts_enquiries: bool | None = None`;
    - `OwnerListingResponse.accepts_enquiries: bool` and `enquiries_offered: bool` (= `enquiries_enabled()`).
  - `app/api/hub.py`: `_owner_response` fills both.
  - `app/hub/public/views.py`: `HubOwnerPage.enquiry_open: bool` and `HubBatchPage.enquiry_open: bool`, both registered models already.
  - `app/hub/public/queries.py`:
    - `owner_page` and `batch_page` read `hub_public_enquirable` only when `enquiries_enabled()`;
    - `HubBatchPage.enquiry_open` also needs the batch's `admissions <> 'closed'`.
  - `app/hub/public/render.py`: `_enquiry_href(owner_slug: str, batch_id: uuid.UUID | None) -> str` returns `f"{web_app_url()}/ui/hub-enquiry?{urlencode(…)}"`, and `_Meta.enquiry_href: str | None` is set when the view's `enquiry_open`.
  - `app/hub/listings/preview.py`: the owner's preview sets `enquiry_open` from its own row (`accepts_enquiries` and the switch).
  - `app/hub/public/messages.py`: `enquiry_link` "Ask to join" / "ভর্তির অনুরোধ পাঠান", and `enquiry_link_batch` "Ask to join this class" / "এই ক্লাসে ভর্তির অনুরোধ পাঠান".
  - `owner.html` and `batch.html`: one `<p><a href="{{ meta.enquiry_href }}">…</a></p>` above the report link, when set.
  - `tests/privacy/canary.py`: the canary world's solo owner accepts enquiries and holds one enquiry from a canary account, with:
    - `share_contact` true;
    - the account's phone and email as canaries;
    - a canary `student_name` and `message`.
  - `openapi.json` and `schema.d.ts`, both generated.
- Test: `tests/hub/test_public_enquiry_link.py`, `tests/hub/test_owner_listing.py` (new cases), `tests/privacy/test_hub_canary.py` (new probes; the walked-body count is unchanged)

**Interfaces:**
- **Consumes:** the view (Task 2) and the switch (Task 1). `app/hub/public` imports only `app.hub.public.settings` for the switch, never `app.hub.enquiries`.

- [ ] **Step 1: Write the failing tests:**
  - `test_listing_toggle_round_trips_and_reports_offered` (`enquiries_offered` follows the switch; the PUT consumes one listing edit like any other).
  - `test_link_shown_only_when_switch_on_and_owner_accepts` (both locales, owner and batch pages; the href's exact query).
  - `test_batch_link_hidden_when_admissions_closed_owner_link_kept`.
  - `test_switch_off_removes_link_on_every_page` (no `/ui/hub-enquiry` anywhere in search, owner, batch or sitemap, in either locale, with an accepting owner in the database).
  - `test_preview_shows_link_from_own_row`.
  - `test_page_csp_unchanged_and_no_inline_style`.
  - `test_canary_enquiry_never_public` (under `enquiries_on` and `reviews_on`), and `test_canary_link_does_appear` (non-vacuous).
- [ ] **Step 2: Run** `pytest tests/hub tests/privacy -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Then run `make openapi` and `cd web && npm run gen:api`.
- [ ] **Step 4: Run** the gate (backend set, plus `tests/hub tests/privacy tests/contract tests/gates`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): owners opt in to join requests; public pages link to the form`.

### Task 7: Deletion wiring

**Files:**
- Modify:
  - `app/hub/enquiries/forget.py`: `for_account(session, account_id) -> int` collects:
    - the ids where `enquirer_account_id = :account`;
    - the ids where `owner_id IN (SELECT id FROM owner WHERE account_id = :account AND kind = 'teacher')`.

    It locks them `FOR UPDATE`, calls `forget`, and returns the count.
  - `app/governance/deletion.py`: in `delete_account`, call `forget.for_account` before the generic `ACCOUNT_COLUMN` loop (which then finds nothing for this table), and add its count to `rows_deleted["listing_enquiry"]` after the loop, so the loop's assignment does not overwrite it.
  - `app/governance/dispositions.py` basis text, if the tests show it is needed; then run `python3 -m scripts.generate_privacy_policy`.
- Test: `tests/governance/test_enquiry_deletion.py`

**Interfaces:**
- Consumes: `forget.forget` (Task 3).

- [ ] **Step 1: Write the failing tests:**
  - `test_guardian_deletion_removes_their_enquiries_and_owner_inbox_items`.
  - `test_solo_owner_deletion_removes_received_enquiries_and_guardian_inbox_items`.
  - `test_centre_enquiries_survive_manager_deletion` (the other manager still lists them).
  - `test_deletion_works_with_switch_off`.
  - `test_external_deletion_path_also_forgets` (the `/account-deletion` code path reaches the same `delete_account`).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the gate (backend set, plus `tests/governance tests/enquiries tests/privacy tests/contract`). Then regenerate the privacy policy and confirm `git diff --stat docs/legal/PRIVACY.md` shows the `listing_enquiry` row. Expected: PASS.
- [ ] **Step 5: Commit** `feat(governance): join requests go totally with either party`.

### Task 8: Web — request form, my requests, owner inbox, prefilled add-student

**Files:**
- Create:
  - `web/src/features/common/HubEnquiry.tsx` and `HubEnquiry.test.tsx`;
  - `web/src/features/account/MyEnquiries.tsx` and `MyEnquiries.test.tsx`;
  - `web/src/features/teacher/hub/Enquiries.tsx` and `Enquiries.test.tsx`;
  - `web/src/features/teacher/hub/enquiries.api.ts`.
- Modify:
  - `web/src/App.tsx`:
    - generalise `SignInThenReport` to `SignInThenReturn`, used by both `/hub-report` and `/hub-enquiry` while signed out;
    - add `/hub-enquiry` and `/hub-enquiries` for every lens.
  - `web/src/features/account/More.tsx`: a "My join requests" row, rendered only when `GET /v1/me/hub/enquiries` returns a non-empty list.
  - `web/src/features/teacher/hub/index.tsx` and `paths.ts`: `/more/hub/enquiries` and `/more/hub/enquiries/:enquiryId`.
  - `web/src/features/teacher/hub/Listing.tsx`:
    - a "Receive join requests" switch, rendered only when `enquiries_offered`;
    - a "Join requests" row, rendered only when `GET /v1/hub/enquiries` succeeds (`HUB_ENQUIRIES_OFF` renders no row and no error).
  - `web/src/features/teacher/paths.ts`: `studentNew(batchId?, enquiryId?)` adds `enquiry=<id>`.
  - `web/src/features/teacher/people/NewStudent.tsx`: with `?enquiry=`, it reads `GET /v1/hub/enquiries/{id}` and fills the name, the guardian phone or email, and the batch. After a successful save, it calls close with `added`; a failed close shows a retry and keeps the saved student.
  - `web/src/features/account/area/mappers.ts`: the two kinds, announced and titled.
    - **Owner tap:** opens `/more/hub/enquiries/:id`.
    - **Guardian tap:** opens `/hub-enquiries`.
  - Android `values{,-bn}/strings.xml` for every new `web_*` key, then run `cd web && node scripts/sync-strings.mjs`.
  - `docs/delivery/bangla-layout-check.md`: rows for HubEnquiry, MyEnquiries, Enquiries and EnquiryDetail.

**Interfaces:**
- **The form** (`/hub-enquiry?owner=&batch=`):
  - **Header:** reads `enquiry-target`, then shows "To {owner_public_name}" and the batch title.
  - **Fields:**
    - student name;
    - class level (from the `ClassLevel` labels the listing editor already has);
    - message, with a 300 counter;
    - the share box, labelled by `contact_kind`: "Share my phone number with {owner}" / "{owner}-কে আমার ফোন নম্বর দেখাতে দিন", or the email twin. It is unticked and must be touched; a submit with it untouched is blocked client-side as a required choice.
    - help text: "If you don't share it, the teacher sees your request but cannot call you. You can withdraw it at any time." / BN twin;
    - the declaration checkbox: "I am the student's parent or guardian, and 18 or older." / "আমি শিক্ষার্থীর মা-বাবা বা অভিভাবক, এবং আমার বয়স 18 বা তার বেশি।"
  - **Already open:** `already_open` renders "You already have a request with this teacher" with a link to `/hub-enquiries`.
  - **Errors:** every refusal renders the server's message key.
- **My requests:** status and outcome copy from the outcome code; for `call_us`, a `tel:` link to `owner_contact_phone`; "Withdraw" behind a confirmation reading "This deletes your request completely."
- **Owner inbox:**
  - **The list:** open first.
  - **The detail:** student name, class, message, batch, received date, and the shared contact as `tel:` / `mailto:` when present, else "Not shared".
  - **Actions:**
    - "Add as student" (only when `outcomes_allowed` holds `added`) → `paths.studentNew(batchId, id)`;
    - "Not now";
    - "Ask them to call" (only when `outcomes_allowed` holds `call_us`).
  - The client computes no eligibility: every refused action renders the server's message key.

- [ ] **Step 1: Write the failing tests:**
  - `signed-out enquiry link signs in then returns`;
  - `form names the target and requires the share choice and declaration`;
  - `already open shows link to my requests`;
  - `contact refusal shows server message`;
  - `my requests withdraw confirms then calls DELETE`;
  - `call_us shows owner number`;
  - `owner inbox hidden on HUB_ENQUIRIES_OFF`;
  - `owner detail shows contact only when shared`;
  - `add as student prefills and closes with added after save`;
  - `close failure after save keeps student and offers retry`;
  - `listing toggle hidden when not offered`;
  - `inbox renders both enquiry kinds`.
- [ ] **Step 2: Run** `cd web && npm run check`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `cd web && npm run check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(web): join requests for guardians and owners`.

### Task 9: Android — request form, my requests, owner inbox, prefilled add-student

**Files:**
- Create: `android/src/main/kotlin/com/shikkhokplus/app/feature/hubenquiry/`:
  - `HubEnquiryApi.kt` (`HttpHubEnquiryApi`) and `HubEnquiryModels.kt`;
  - `EnquiryFormViewModel.kt`, `MyEnquiriesViewModel.kt` and `OwnerEnquiriesViewModel.kt`;
  - `ui/{EnquiryFormScreen.kt, MyEnquiriesScreen.kt, OwnerEnquiriesScreen.kt, OwnerEnquiryDetailScreen.kt}`;
  - their tests.
- Modify:
  - `AndroidManifest.xml`: the App Link intent filter gains `<data android:path="/ui/hub-enquiry" />`, and its comment names both paths.
  - `navigation/Destination.kt`: `HubEnquiryForm` (`hub/enquiry?owner={owner}&batch={batch}`), `HubMyEnquiries` (`hub/enquiries/mine`), `HubOwnerEnquiries` (`hub/listing/enquiries`) and `HubOwnerEnquiry` (`hub/listing/enquiries/{enquiryId}`). `NewStudent` gains `ARG_ENQUIRY` (`students-add?batch={batchId}&enquiry={enquiryId}`).
  - `navigation/HubRoutes.kt`: every action wired, plus the link effect parsing `/ui/hub-enquiry` beside `/ui/hub-report`.
  - `navigation/TeacherStudentsRoutes.kt` and `feature/students/ui/AddStudentForm.kt`: prefill from `GET /v1/hub/enquiries/{id}`, then close with `added` after the save.
  - `HubListingScreen.kt` and `HubListingViewModel.kt`: the switch row (only when `enquiriesOffered`) and the "Join requests" row (only when the list call succeeded).
  - The More/account screen: "My join requests", only when the list is non-empty.
  - `InboxMapper.kt` and `InboxScreen.kt`: the two kinds, announced, with taps navigating as on web.
  - `values/` and `values-bn/` strings.
  - `docs/delivery/bangla-layout-check.md`: rows for the four screens.

**Interfaces:**
- Behaviour mirrors Task 8 exactly.
- **ViewModel states:** `Loading`, `Ready`, `Sending`, `Error(retryable)` and `Off`. `Off` comes from `HUB_ENQUIRIES_OFF` and renders nothing.
- **Failed writes:** a failed write keeps the typed text and offers retry (TC-8). `shareContact` is a nullable `Boolean?` in form state, so "not chosen" cannot be sent.

- [ ] **Step 1: Write the failing tests:**
  - ViewModels:
    - `send success`;
    - `share choice required`;
    - `already open`;
    - `contact refused keeps text`;
    - `network failure keeps text and offers retry`;
    - `withdraw confirmed`;
    - `owner contact shown only when shared`;
    - `off hides entry`.
  - `HubEnquiryRouteTest`, driving the real routes with MockEngine:
    - an App Link to `/ui/hub-enquiry?owner=x&batch=y` opens the form, and send calls the API;
    - the More row opens my requests, and withdraw calls `DELETE`;
    - the teacher row opens the inbox → detail → "Add as student" opens `NewStudent` with the enquiry prefilled → save → close `added`.
  - `HubReportRouteTest` still passes with the wider intent filter; `InboxRouteTest` additions cover both kinds.
- [ ] **Step 2: Run** `make android`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make android && make android-quality`, then `cd web && node scripts/sync-strings.mjs --check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(android): join requests for guardians and owners`.

### Task 10: Release deliverables and the switch runbook

**Files:**
- Modify:
  - `docs/legal/README.md`: a "Data Safety: what join requests change" section.
    - **Collected:** the student's name and class as typed, an optional message, and (only by choice per request) the phone number or email address already on the account.
    - **Shared:** with the one teacher or centre the guardian chose, at their direction.
    - **Never:** public, or shown to platform administrators.
    - **Deleted:** on withdrawal, on account deletion, and after 90 days.

    The Families note says requests come only from accounts declaring they are a parent or guardian aged 18 or older, and that no message reaches a child account from a teacher through this feature.
  - `docs/legal/PRIVACY.md` (regenerated).
  - `infra/README.md`, the "Switching join requests on" runbook. Each step is a human check, in order:
    1. The `project.md` Forbidden rule is amended through the learnings ritual. Proposed text:

       > NEVER expose anything a student or guardian writes to any teacher, except a hub review its author explicitly submitted for public display, and a join request a guardian explicitly sent to that owner, which only that owner's managers see, never with the guardian's contact unless they chose to share it on that request.

       Together with the existing review clauses.
    2. The D6 Data Safety and Families declarations are published.
    3. `aws ssm put-parameter --overwrite --name /shikkhokplus/shikkhokplus-<env>/hub-enquiries --value on`.
    4. Dispatch a deploy.
    5. In staging, a seeded owner with requests on shows "Ask to join", and a test guardian's request reaches the owner's inbox.

    Switching off is the same with `off`; open requests stay readable and withdrawable by their guardians and are purged at 90 days.
- Test:
  - `tests/gates/test_hub_enquiries_switch_infra.py`: `test_runbook_lists_rule_amendment_and_d6_before_flip`;
  - `tests/governance/test_privacy_policy.py`: the generated policy names `listing_enquiry` with "90 days".

- [ ] **Step 1: Write the failing tests.**
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make check` once, the full gate. Expected: every target green.
- [ ] **Step 5: Commit** `docs(enquiries): release deliverables and the join-request switch runbook`.
