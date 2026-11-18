# Public Hub H2 (Public Pages, Search, Sitemap) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Release 1 of the hub, the public directory. This covers:
- the no-JavaScript Bangla/English pages for published tutors, centres and batches;
- search with filters, and a sitemap;
- Dhaka and other city areas in the area list;
- prompt takedown through the CDN;
- the signed-in report entry from public pages;
- the editor's "preview as public";
- the in-app teacher question that drives the day-90 decision.

**Architecture:**
- The API renders Jinja2 templates from registered public view models.
- Those models are built only from four SQL views, read under `SET LOCAL ROLE shikkhok_hub_reader`.
- The site's CloudFront distribution serves the pages on a GET-only, credential-free, cached `/hub/*` behaviour whose origin is the API. The API's own host refuses `/hub*`.
- Takedowns enqueue a CloudFront invalidation in the same transaction. The request drains it after commit, with a cron backstop.

**Tech Stack:**
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, Jinja2 (new, pinned and locked), pytest + testcontainers.
- Infra: Terraform (AWS CloudFront, CloudFront Functions JS 2.0, S3, IAM).
- Web: React/TS/Vite.
- Android: Kotlin/Compose.

**Spec:** `docs/superpowers/specs/2026-11-14-public-hub-design.md`, approved 2026-11-14. Read in particular:
- §4 Public pages and caching
- §8 Privacy controls
- §9 Measures
- §10 Reporting
- "Changes recorded during H0/H1 build"

H0/H1 are on `main` (PR #80); see `docs/superpowers/plans/2026-11-14-public-hub-h0-h1.md` for what they built.

**Carried in from the H0/H1 final review (binding):**
1. **Visibility:** an owner page needs `owner_listing.status = 'published'`. A batch page needs batch listing `published`, AND `batch.active`, AND owner listing `published`. Unpublishing an owner leaves its batch rows `published`, so the views must check all three.
2. **Retrofitted invalidation:** every takedown path enqueues an invalidation: suspension, owner/batch unpublish, `hide_for_inactive_batch`, consent withdrawal, solo-owner account deletion, and a slug change (the old path).
3. **Views run with their owner's rights and bypass RLS:** no hub view may reference `profile`. Use `security_barrier`.
4. **Placement:** the public route handlers live inside `app/hub/public/**`, so the import gate covers them.
5. **Canary world:** must hold a published listing, a never-published draft (with a public name and a slug), a centre with an unconsented member (`owner_member.display_name` and `invited_phone`), and an owner whose public phone differs from their account phone.
6. **No `batch.name` on any public page:** use `batch_listing.public_title`.

**Deviations from the spec, decided here:**
- **Public route count:** `PUBLIC_ROUTES` goes 15 → 19. PR #81 added one after the spec said 14 → 18. The four hub routes are unchanged.
- **Migration numbers start at 0039:** main already holds 0037 and 0038 from PR #81.
- **Search vocabulary:** search uses the existing `to_tsvector('simple', …)` column (built in H1), extended, plus structured filters. The spec's `pg_trgm` is not needed for whole-word matching and costs an extension; revisit at p95 > 200 ms on 5,000 listings.
- **Invalidation is drained after commit by the request itself** (best-effort), with a 10-minute cron as backstop. A per-minute cron would start a container every minute on the 2 GB host.

## Global Constraints

- **Public route counts:** `PUBLIC_ROUTES` becomes exactly **19**, and `PUBLIC_CACHEABLE_ROUTES` exactly these **4**:
  - `("GET", "/hub/{locale}")`
  - `("GET", "/hub/{locale}/t/{owner_slug}")`
  - `("GET", "/hub/{locale}/t/{owner_slug}/{batch_slug}")`
  - `("GET", "/hub/sitemap.xml")`

  `locale ∈ {"en", "bn"}`. Any other locale gets the byte-identical 404.
- **Draft/missing/suspended/hidden:** a draft, missing, suspended or hidden owner or batch, an inactive batch, or a batch under an unpublished owner each return a **byte-identical** 404 body with `Cache-Control: public, s-maxage=60`.
- **Cache-Control (verbatim):**

  | Page | Header |
  |---|---|
  | Owner and batch pages | `public, max-age=60, s-maxage=600` |
  | Search/landing | `public, max-age=60, s-maxage=300` |
  | Sitemap | `public, s-maxage=3600` |

- **Page CSP (verbatim):** `default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`.
  - The only `<script>` element allowed is one `type="application/ld+json"` data block. Browsers never execute it, and `default-src 'none'` already forbids executable scripts.
  - No inline style and no inline handler on any hub page.
- **Stylesheet:** one file, `app/hub/public/static/hub.css`, is the single source. Its public URL is `/hub-assets/hub.<first 12 hex of sha256(file)>.css`. The API computes that name at import time, and `site/build.mjs` copies the same file under the same name into `dist/hub-assets/`, so `style-src 'self'` covers it on the site host. No `@font-face`; the font stack is `"Noto Sans Bengali", "Noto Sans", system-ui, sans-serif`.
- **Query-string allowlist (verbatim):** `q`, `district`, `upazila`, `subject`, `level`, `page`. Anything else: the edge returns 400 and the origin ignores it.
- **Rate limit:** public reads are limited to **120/minute per IP** at the origin, keyed on `CloudFront-Viewer-Address`, the only header forwarded (kept out of the cache key).
- **Public data sources:** public handlers may read only the views `hub_public_owner`, `hub_public_batch`, `hub_public_area` and `hub_public_teacher_name`, and only under `as_hub_reader`. Nothing on a public page comes from `profile`, `account`, `enrollment`, `student`, `batch.name`, `collection_number`, `owner_member.invited_phone`, or an unconsented member's `display_name`.
- **Money:** `default_fee` as `Money`, rendered with `Money.format(locale)` (server-formatted), only when `show_fee`. Never float or Decimal outside `app/money`.
- **Bangla and English twins:** every hub page is served in both locales with `hreflang` pairs. Every new user-facing string exists in EN and BN (Android `values/` and `values-bn/`, web bundles via `node scripts/sync-strings.mjs`, and Jinja message catalogues). Latin digits in app-generated numbers, matching the existing bundles.
- **Opt-in:** an owner or batch never appears anywhere public before its own `publish`. Centre teachers are named only with `public_name_consent_at`, otherwise "Centre faculty" / "সেন্টারের শিক্ষকবৃন্দ".
- **Python:** Sphinx docstrings, type hints, Ruff line length 88, imports at top.
- **Every backend task's gate:** `python -m ruff check app tests`, `python -m ruff format --check app tests`, **`python -m mypy app`**, and the task's pytest directories. Web tasks run `cd web && npm run check`. Android tasks run `make android && make android-quality`. Infra tasks run `make infra-functions` and `terraform fmt -check -recursive infra`.
- **Each new migration** moves the head pins in all four places: `tests/db/test_migration_head_pin.py`, `test_migration_from_head.py`, `test_migration_runs.py` and `tests/auth/test_endpoints.py`.
- **Each new table** gets `DISPOSITIONS` and, where hard-deleted, `HARD_DELETE_SCOPES` entries, followed by `python3 -m scripts.generate_privacy_policy`.
- **After any API change:** `make openapi`, then `cd web && npm run gen:api`.
- A comment that states a count must be asserted by a test, or the number comes out.
- **Commits:** conventional, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **An owner unpublishes while a batch listing row stays `published`:** the batch page, the search results and the sitemap must not show it. (Task 2, `test_batch_under_unpublished_owner_is_invisible_everywhere`.)
2. **A suspended listing that is cached at the edge:** a `cdn_invalidation` row for the owner's path prefix is committed in the same transaction as the suspension, and the drain sends it. (Task 6, `test_suspension_enqueues_invalidation_in_same_transaction`.)
3. **A Bangla search typed with Bangla digits, a zero-width joiner, or mixed scripts** ("ঢাকা  physics", "মিরপুর‍") returns matches and never a 500. (Task 3, `test_search_normalises_bangla_input`.)
4. **A crawler sends `?utm_source=x` or `?q=a&q=b`:** the edge function rejects the unknown key with 400 and collapses repeated keys deterministically. The origin ignores unknown keys, so cache keys stay bounded. (Task 7, `query-allowlist.test.mjs`; Task 4, `test_unknown_query_keys_are_ignored`.)
5. **A centre teacher withdraws name consent:** the batch page shows "Centre faculty" within the 10-minute TTL, and an invalidation is enqueued. (Task 6, `test_consent_withdrawal_enqueues_invalidation`; Task 5, the canary covers the name.)

---

### Task 1: City areas — city corporations and metropolitan thanas (0039)

**Why:** an H2 blocker. Dhaka district holds only five rural upazilas, and the only "Mirpur" row is Kushtia's.

**Files:**
- Create: `migrations/versions/0039_city_areas.py`, `app/hub/listings/data/bd_city_area.csv`, `app/hub/listings/data/bd_metro_thana_bn.csv`
- Modify:
  - `app/db/models.py` (`BdArea` kind values);
  - `app/hub/areas.py` and the `AreaOption` Literal in `app/schemas/hub.py`;
  - `app/hub/listings/owner.py` (area consistency check);
  - `tests/db/test_migration_head_pin.py` and the other head pins;
  - `app/hub/listings/data/LICENSE-bangladesh-geocode.txt` (add the new source files and fetch date).
- Test: `tests/db/test_migration_0039.py`, `tests/hub/test_city_areas.py`

**Data source:** the same MIT dataset, `github.com/nuhil/bangladesh-geocode`:
- `city_corporations/` gives `id, division_id, district_id, name, bn_name, url, bbs_code`.
- `postcodes/` gives `…, city_corporation_id, thana, post_office, postcode, …, link_method`. Only rows with `link_method = 'metro_thana'` are used.

A metropolitan thana is the distinct `thana` value per `city_corporation_id`. Its code is `"MT" + city_corporation.bbs_code.removeprefix("BD") + f"{n:02d}"`, where `n` counts the thanas of that city corporation in alphabetical order of the English name, starting at 1. For example, `MT3026250001` is 12 characters, the column width; a test asserts every code fits. Its parent is the city corporation. Because codes are stored in listings, the CSV is committed once and never regenerated in a way that renumbers: new thanas from a later data refresh get the next free ordinal.

**Bangla names:** the dataset has no Bangla names for metro thanas. Enter them by hand in `bd_metro_thana_bn.csv` (`code,name_bn`). **The owner reviews that file before this task's PR merges.** This is a human step, flagged in the PR description. Invent no English names.

**Interfaces:**
- Produces:
  - `bd_area.kind` gains `city_corporation` (parent: district) and `metro_thana` (parent: city corporation). Existing codes are unchanged.
  - `owner_listing.upazila_code` may now also hold a `metro_thana` code; the column keeps its name for compatibility.
  - `app.hub.areas.children(session, parent: str | None) -> list[AreaOption]`, where a district's children are its upazilas followed by its city corporations.
  - `owner._check_area` accepts an `upazila_code` whose parent is the district (an upazila) or whose grandparent is the district (a metro thana).

- [ ] **Step 1: Write failing tests.**
  - `test_0039_adds_city_corporations_and_metro_thanas`:
    - 12 city corporations;
    - Dhaka district (`BD3026`) has children named "Dhaka North City Corporation" and "Dhaka South City Corporation";
    - a metro thana named "Mirpur" exists under Dhaka North City Corporation.
  - `test_every_metro_thana_has_reviewed_bangla_name`: no `name_bn` is blank or equal to `name_en`.
  - `test_existing_codes_unchanged` (the 567 earlier rows are identical).
  - `test_listing_accepts_metro_thana_under_its_district`.
  - `test_listing_rejects_metro_thana_from_another_district` (`HUB_AREA_MISMATCH`).
- [ ] **Step 2: Run** `pytest tests/db/test_migration_0039.py tests/hub/test_city_areas.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Extend the `bd_area_kind` enum with `ALTER TYPE … ADD VALUE` in an autocommit block, then load both CSVs with stdlib `csv` relative to `__file__`. Make the downgrade refuse while any `owner_listing` references a `metro_thana` code. Extend the area picker's Literal on web and Android only if their generated types require it (web: `npm run gen:api`).
- [ ] **Step 4: Run** the gate (backend set plus `tests/db tests/governance`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): city corporations and metropolitan thanas (0039)`.

### Task 2: Public views, search columns and reader grants (0040)

**Files:**
- Create: `migrations/versions/0040_hub_public_views.py`
- Modify: `app/db/models.py` (`OwnerListing.public_name_latin`, `BatchListing.search_text`), `app/schemas/hub.py` and `app/hub/listings/owner.py` (the editable `public_name_latin`, ≤ 120, phone-scanned), the head pins
- Test: `tests/db/test_migration_0040.py`, `tests/privacy/test_hub_public_views.py`

**Interfaces:**
- **New columns:**
  - `owner_listing.public_name_latin VARCHAR(120) NULL`, an owner-entered Latin transliteration.
  - `owner_listing.search_text` regenerated as `to_tsvector('simple', public_name || ' ' || coalesce(public_name_latin,'') || ' ' || headlines || ' ' || coalesce(qualifications,''))`.
  - `batch_listing.search_text tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(public_title,'') || ' ' || coalesce(description_en,'') || ' ' || coalesce(description_bn,'') || ' ' || array_to_string(subject_tags,' '))) STORED`, with a GIN index.
- **Views,** all `WITH (security_barrier)` and all granted `SELECT` to `shikkhok_hub_reader` only:
  - `hub_public_owner`: published owner listings. Columns: slug, public_name, public_name_latin, kind (from `owner.kind`), headline_en/bn, bio_en/bn, qualifications, teaching_mode, district_code, upazila_code, street_address (centres only), public_contact_phone, runs_classes (precomputed by the view from the badge SQL), published_at, search_text, owner_id.
  - `hub_public_batch`: rows where batch listing `published` AND `batch.active` AND owner listing `published`. Columns: owner_slug, slug, public_title, description_en/bn, syllabus_en/bn, class_levels, curriculum, subject_tags, mode, admissions, fee (only when `show_fee`, else NULL), schedule (a JSON array of `{weekday, start, end}` only when `show_schedule`), search_text, batch_id.
  - `hub_public_teacher_name`: (batch_id, name) for accepted, unrevoked, consented members assigned via `schedule_slot.teacher_member_id` under published batches.
  - `hub_public_area`: `bd_area` passthrough.
- The view definitions reference no `profile`, `account`, `enrollment`, `student` or `batch.name`.

- [ ] **Step 1: Write failing tests,** each run under `as_hub_reader` on `restricted_session`:
  - `test_hub_reader_reads_only_the_four_views`: `has_table_privilege` over every table and view in `public`, true exactly for the four views and `bd_area`.
  - `test_views_do_not_reference_private_tables`: parse `pg_views.definition` for the four views and assert none of `profile`, `account`, `enrollment`, `student`, `payment_method`, `batch.name` / `b.name`.
  - `test_draft_owner_absent_from_views`.
  - `test_batch_under_unpublished_owner_is_invisible_everywhere` (Review Focus 1).
  - `test_inactive_batch_absent`.
  - `test_fee_null_unless_show_fee`.
  - `test_schedule_null_unless_show_schedule`.
  - `test_unconsented_member_absent_from_teacher_name_view`.
  - `test_views_are_security_barrier`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the migration, models, editor field and grants.
  - Add a comment where the grants are added explaining that `shikkhok_app` inherits them through membership (the H0 Task 1 minor).
  - Run `make openapi` and `npm run gen:api`.
  - Add `public_name_latin` to the web and Android editors as an optional field with EN/BN labels; this folds the client change into this task.
- [ ] **Step 4: Run** the gate, including `cd web && npm run check` and `make android`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): public views and search columns for the hub reader (0040)`.

### Task 3: Public read service and view models

**Files:**
- Create: `app/hub/public/queries.py`, `app/hub/public/views.py` (Pydantic view models), `app/hub/public/normalise.py`
- Test: `tests/hub/test_public_queries.py`

**Interfaces:**
- **View models,** each `@register_view`:
  - `HubOwnerCard`: slug, public_name, kind, area_names `{en, bn}`, runs_classes.
  - `HubBatchCard`: owner_slug, slug, public_title, subjects, class_levels, curriculum, mode, admissions, fee (`Money | None`), schedule (`list[PublicSlot] | None`), teacher_names.
  - `HubOwnerPage`: the owner card plus headline, bio, qualifications, teaching_mode, street_address, public_contact_phone, and its batches.
  - `HubBatchPage`: owner card plus batch card plus description, syllabus.
  - `HubSearchPage`: query echo, filters, results, page, pages, total.
  - `HubSitemap`: urls with `{loc, alternates}`.

  No field is named `display_name`, `name` or `phone`; the contact field is `public_contact_phone`.
- **Functions,** all taking `session: Session` and calling `as_hub_reader(session)` first:
  - `search(session, *, locale: Literal["en","bn"], q: str | None, district: str | None, upazila: str | None, subject: str | None, level: str | None, page: int) -> HubSearchPage`. Twenty per page; `page` starts at 1, and a page past the end is empty, never an error.
  - `owner_page(session, locale, owner_slug) -> HubOwnerPage | None`.
  - `batch_page(session, locale, owner_slug, batch_slug) -> HubBatchPage | None`.
  - `sitemap(session) -> HubSitemap`.
- **Text normalisation:** `normalise.query_terms(q: str) -> list[str]`.
  - NFC-normalise, strip zero-width characters (U+200B–U+200D, U+FEFF), map Bangla digits to Latin, lowercase, split on whitespace, drop empty terms, cap at 8 terms of at most 40 characters each.
  - Match each term as a `to_tsquery('simple', term || ':*')` prefix, AND-ed, against owner `search_text` OR any of the owner's batch `search_text` values.
- **Ranking:** `ts_rank` descending, then `published_at` descending, then slug.
- **Filters:**
  - `district`: matches the owner district.
  - `upazila`: matches `upazila_code`, or any child metro thana when given a city corporation code.
  - `subject`: any batch's `subject_tags` contains it (case-insensitive).
  - `level`: any batch's `class_levels` contains it (vocabulary values only; anything else is ignored).
- **Teacher names:** for a centre batch, `teacher_names` comes from `hub_public_teacher_name`, else "Centre faculty" in the requested locale. A solo owner shows `public_name`.

- [ ] **Step 1: Write failing tests:**
  - `test_search_finds_by_bangla_and_latin_name`;
  - `test_search_normalises_bangla_input` (Review Focus 3);
  - `test_search_filters_district_city_corporation_and_level`;
  - `test_search_page_past_end_is_empty`;
  - `test_owner_page_none_for_draft_hidden_suspended_missing`;
  - `test_batch_page_none_for_retired_or_unpublished_parent`;
  - `test_centre_faculty_fallback_localised`;
  - `test_fee_formatted_by_money_module_only_when_shown`;
  - `test_sitemap_lists_only_published_with_both_locales`.
- [ ] **Step 2: Run** `pytest tests/hub/test_public_queries.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the gate plus `tests/contract/test_public_privacy.py`. The registered views must be leak-free. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): public read service and registered view models`.

### Task 4: Public HTML routes, templates and editor preview

**Files:**
- Create:
  - `app/hub/public/routes.py`;
  - `app/hub/public/render.py`;
  - `app/hub/public/templates/` (`base.html`, `search.html`, `owner.html`, `batch.html`, `not_found.html`, `sitemap.xml`);
  - `app/hub/public/messages.py` (an EN/BN string table, keyed);
  - `app/hub/public/static/hub.css` (see Global Constraints: `site/build.mjs` copies it to `dist/hub-assets/hub.<hash>.css`, with a site build test asserting the name equals the API's `render.STYLESHEET_PATH`).
- Modify:
  - `pyproject.toml` / `requirements.txt` (pin `jinja2` with hashes via the lockfile workflow; check it against the CVE gate);
  - `app/main.py` (register the router);
  - `app/api/html.py` (`html_response(content, status_code=200, *, csp: str = DEFAULT_CSP, cache_control: str | None = None)`);
  - `app/contract/routes.py` (`PUBLIC_ROUTES` +4 with written reasons, `PUBLIC_CACHEABLE_ROUTES` = the four);
  - `tests/contract/test_route_lenses.py` (15 → 19);
  - `app/api/hub.py` (`GET /v1/hub/listing/preview?locale=en|bn`, `TeacherLens`, HTML, `Cache-Control: no-store`);
  - `app/auth/ceilings.py` (`HUB_PUBLIC_READ_IP_MINUTE = 120`);
  - `site/build.mjs` and `site/test/build.test.mjs` (copy `app/hub/public/static/hub.css` to `dist/hub-assets/hub.<hash>.css` and assert the name matches the API's).
- Test: `tests/hub/test_public_routes.py`, `tests/contract/test_public_cacheable.py` (now non-vacuous)

**Interfaces:**
- **Routes:** exactly the four in Global Constraints. Each handler opens a session, calls the Task 3 function, and renders through `render.page(view: BaseModel, template: str, locale) -> str`, which refuses any model not in `registered_views()`.
- **Every page has:**
  - `<html lang>`;
  - canonical and `hreflang` (en, bn, x-default = en) links;
  - `<title>` and meta description;
  - schema.org `EducationalOrganization` (owner) or `Course` (batch) JSON-LD in one `<script type="application/ld+json">` data block, with `<` escaped as `<` inside the JSON.
  - `<link rel="stylesheet" href="{render.STYLESHEET_PATH}">`, where `render.STYLESHEET_PATH: Final[str]` is computed from `hub.css`.
  - **No** `AggregateRating`.
  - Search pages carry `noindex`; owner and batch pages are indexable.
- **Report link:** each owner and batch page carries `<a href="{WEB_APP_URL}/ui/hub-report?kind=owner_listing|batch_listing&id=…">`. `WEB_APP_URL` comes from the existing settings.
- **Preview:** `GET /v1/hub/listing/preview` builds the same `HubOwnerPage` from the caller's own listing and batch rows, draft included, through a separate owner-scoped builder in `app/hub/listings/preview.py`. That builder outputs the same registered view model, so the privacy gate walks it. It renders a banner reading "Preview — not public yet" / "প্রিভিউ — এখনও প্রকাশিত নয়".
- **Rate limit:** a dependency reads `CloudFront-Viewer-Address`, falling back to the client host, and consumes `HUB_PUBLIC_READ_IP_MINUTE`. A breach returns 429 with a plain HTML page.

- [ ] **Step 1: Write failing tests:**
  - `test_four_public_routes_render_both_locales`;
  - `test_unknown_locale_and_missing_slug_return_byte_identical_404`;
  - `test_cache_control_headers_exact`;
  - `test_csp_exact_and_no_script_or_inline_style` (parse with `html.parser`: no `<script>` except `type="application/ld+json"`, no `style=`, no `on*=`);
  - `test_unknown_query_keys_are_ignored` (Review Focus 4);
  - `test_hreflang_pairs_and_canonical`;
  - `test_no_aggregate_rating_markup`;
  - `test_preview_shows_draft_with_banner_and_no_store`;
  - `test_preview_refuses_other_owner_and_class_teacher`;
  - `test_public_read_ceiling_120_per_minute`;
  - `test_route_count_is_19` (in the route-lens test);
  - `test_cacheable_routes_have_no_auth` (now walks four routes).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Use Jinja2 with `autoescape=True` and a `StrictUndefined` environment, loaded once. Bangla titles wrap via the site's CSS (`overflow-wrap: anywhere`).
- [ ] **Step 4: Run** the gate plus `tests/contract tests/gates tests/privacy`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): public pages, search and sitemap rendered from registered views`.

### Task 5: Canary and privacy probes over the real pages

**Files:**
- Modify: `tests/privacy/canary.py`, `tests/privacy/test_hub_canary.py`
- Create: `tests/privacy/test_hub_public_probes.py`

**Interfaces:**
- Extend `seed_canaries` to the world in carried-in item 5:
  - a published solo owner and batch;
  - a never-published draft with a canary public name and slug;
  - a centre with a published batch and an unconsented member whose `display_name` and `invited_phone` are canaries;
  - an owner whose `public_contact_phone` differs from `account.phone` (the account phone is a canary);
  - a batch whose `batch.name` is a canary.
- `CanaryWorld` gains `owner_slug`, `batch_slug`, `centre_slug` and `centre_batch_slug`. `_resolve` handles `{locale}`, `{owner_slug}` and `{batch_slug}`, yielding both the solo pair and the centre pair. Any other placeholder still raises.

- [ ] **Step 1: Write failing tests:**
  - `test_no_canary_on_any_cacheable_public_page`. It now walks 4 routes × 2 locales plus both owner/batch pairs, and asserts the exact walked count.
  - `test_draft_canary_never_public`.
  - `test_unconsented_member_name_and_phone_never_public`.
  - `test_account_phone_never_public_but_public_contact_is`.
  - `test_batch_name_never_public`.
  - `test_preview_route_carries_no_other_owner_canary`.
- [ ] **Step 2: Run.** Expected: FAIL, for the new world fields.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/privacy -q`. Expected: PASS.
- [ ] **Step 5: Commit** `test(privacy): canary walks every public hub page and the preview`.

### Task 6: Invalidation outbox and retrofitted takedown paths (0041)

**Files:**
- Create: `migrations/versions/0041_cdn_invalidation.py`, `app/hub/public/invalidation.py`, `app/hub/public/commands.py`
- Modify:
  - `app/db/models.py` (`CdnInvalidation`; `HUB_INVALIDATION_JOB = "hub_cdn_invalidation"`);
  - `app/moderation/suspension.py`;
  - `app/hub/listings/owner.py` (`unpublish`, slug change);
  - `app/hub/listings/batches.py` (`unpublish`, slug change);
  - `app/hub/listings/hide.py`;
  - `app/hub/listings/member_consent.py`;
  - `app/governance/deletion.py` (solo-owner delete);
  - `app/governance/dispositions.py` (`cdn_invalidation`: `NOT_PERSONAL`, `DAYS_7`);
  - `infra/modules/app/user_data.sh.tftpl` (cron entry);
  - `infra/modules/app/main.tf` (IAM `cloudfront:CreateInvalidation` on the site distribution ARN only, passed in as a variable);
  - `infra/main.tf` (wire the ARN);
  - the head pins.
- Test: `tests/hub/test_invalidation.py`, `tests/gates/test_scheduled_jobs.py` (it must pass with the new job)

**Interfaces:**
- **Table:** `cdn_invalidation(id, path VARCHAR(300), requested_at, sent_at NULL, aws_id NULL, attempts SMALLINT default 0)`.
- **Enqueue:** `invalidation.enqueue(session, paths: list[str], now) -> None` adds rows to the caller's transaction. CloudFront allows `*` only as the last character, so paths are expanded per locale:
  - an owner takedown: `/hub/en/t/{owner_slug}*` and `/hub/bn/t/{owner_slug}*`, which also cover its batches;
  - a batch takedown: `/hub/en/t/{owner_slug}/{batch_slug}` and the `bn` twin;
  - a slug change: the old paths;
  - always also `/hub/sitemap.xml`.
- **Helper:** `invalidation.owner_paths(slug: str) -> list[str]` and `invalidation.batch_paths(owner_slug: str, batch_slug: str) -> list[str]`, so no caller writes a path by hand. A test asserts no generated path contains `*` anywhere but the end.
- **Drain:** `invalidation.drain(session, client: InvalidationClient, now, limit=50) -> int` sends unsent rows in one `CreateInvalidation` batch, stamps `sent_at`/`aws_id`, and on failure increments `attempts` and logs.
  - `InvalidationClient` is a Protocol with `create_invalidation(paths: list[str], caller_reference: str) -> str`.
  - The boto3 implementation uses the site distribution id from `SHIKKHOKPLUS_SITE_DISTRIBUTION_ID`. When unset (local), it logs and no-ops.
- **After commit:** a response middleware (or `BackgroundTasks` on the takedown routes) runs `drain` best-effort.
- **Cron:** `python -m app.hub.public.commands drain` every 10 minutes (`*/10 * * * *`), recording a heartbeat under `HUB_INVALIDATION_JOB`.

- [ ] **Step 1: Write failing tests:**
  - `test_suspension_enqueues_invalidation_in_same_transaction` (Review Focus 2: roll back the suspension, and no row remains);
  - `test_owner_unpublish_and_batch_unpublish_enqueue`;
  - `test_slug_change_enqueues_old_path`;
  - `test_hide_for_inactive_batch_enqueues`;
  - `test_consent_withdrawal_enqueues_invalidation` (Review Focus 5);
  - `test_solo_owner_deletion_enqueues`;
  - `test_drain_batches_and_stamps`;
  - `test_drain_failure_increments_attempts_and_keeps_row`;
  - `test_drain_without_distribution_id_noops`.

  Each enqueue test also asserts `/hub/sitemap.xml` is included.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the migration, model, enqueue calls, drain, command, cron entry and IAM.
- [ ] **Step 4: Run** the gate plus `tests/gates tests/governance tests/moderation tests/hub`, and `terraform fmt -check -recursive infra`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): invalidation outbox on every takedown path (0041)`.

### Task 7: CloudFront — `/hub/*` on the site distribution; block on the API host

**Files:**
- Create: `infra/modules/site/functions/hub-query.js` and `hub-query.test.mjs`, `infra/modules/cdn/functions/hub-block.js` and `hub-block.test.mjs`
- Modify:
  - `infra/modules/site/main.tf`, `variables.tf` and `outputs.tf`;
  - `infra/modules/cdn/main.tf` and `outputs.tf` (output `origin_fqdn`);
  - `infra/main.tf` (pass `api_origin_fqdn`, `origin_secret` into the site module);
  - the Makefile `infra-functions` target (if it enumerates files);
  - `site/build.mjs` (robots.txt gains `Sitemap: ${siteUrl}/hub/sitemap.xml`);
  - `site/README.md`.

**Interfaces:**
- **Site module:**
  - a second origin (`shikkhokplus-hub-api`, domain `var.api_origin_fqdn`, https-only, custom header `X-Origin-Secret = var.origin_secret`);
  - an ordered behaviour on `/hub/*`, GET/HEAD only;
  - a cache policy honouring origin `Cache-Control`, with `min_ttl` 0 and `max_ttl` 3600, and with the query strings `q`, `district`, `upazila`, `subject`, `level` and `page` in the key;
  - an origin request policy forwarding only the `CloudFront-Viewer-Address` header, no cookies, and the same query strings;
  - the existing response-headers policy, kept: the API sets the CSP;
  - a viewer-request function association for `hub-query.js`.
- **`hub-query.js`:**
  - answers 400 for any query key outside the allowlist;
  - for a repeated key, keeps the first value;
  - lowercases `district`, `upazila`, `subject` and `level`;
  - truncates `q` to 200 characters;
  - rewrites `/hub` and `/hub/` to `/hub/en` with a 301;
  - passes everything else through.
- **`hub-block.js` on the API distribution** (behaviour `/hub*`): always 404 with an empty body.
- **Comments:** rewrite the site module's "there is no API behind it to leak" comment to state the narrowed truth: "only the credential-less, GET-only `/hub/*` slice of the API, which receives no cookies and only the viewer-address header".

- [ ] **Step 1: Write failing tests:**
  - `hub-query.test.mjs`: unknown key → 400; a repeated key keeps the first value; lowercasing; `q` truncation; `/hub` → 301 `/hub/en`; allowed keys pass.
  - `hub-block.test.mjs`: any `/hub*` → 404.
- [ ] **Step 2: Run** `make infra-functions`. Expected: FAIL.
- [ ] **Step 3: Implement** the functions and Terraform. Run `terraform fmt -recursive infra` and `terraform -chdir=infra validate`; use `-backend=false` init if needed.
- [ ] **Step 4: Run** `make infra-functions` and `make site`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(infra): serve /hub through the site distribution and block it on the API host`.

### Task 8: Teacher demand question (`hub_feedback`)

**Files:**
- Create: `app/hub/feedback.py`, `app/hub/feedback_commands.py`
- Create: `migrations/versions/0042_hub_feedback.py`
- Modify:
  - `app/db/models.py` (`HubFeedback`; `HUB_FEEDBACK_JOB = "hub_feedback_question"`);
  - `app/notifications/inbox.py` (kind `HUB_FEEDBACK_QUESTION = "hub_feedback_question"`, not legacy);
  - `app/api/hub.py` (`POST /v1/hub/feedback`, `TeacherLens`);
  - `app/governance/dispositions.py`;
  - `infra/modules/app/user_data.sh.tftpl` (a daily cron at 03:00 UTC);
  - message keys, Android EN/BN, `MessageKeys.kt`, web bundles;
  - the head pins.
- Test: `tests/hub/test_feedback.py`

**Interfaces:**
- **Table:** `hub_feedback(id, owner_id FK owner CASCADE, asked_on DATE, day SMALLINT CHECK IN (60, 90), answer VARCHAR(10) NULL CHECK IN ('yes','not_yet','not_sure'), answered_at NULL, answered_by_account_id FK SET NULL)`, with UNIQUE `(owner_id, day)`. Disposition: `HARD_DELETE` with a solo owner (`SOLO_OWNER` scope), kept for a centre, `LIFE_OF_ACCOUNT`.
- **Daily job:**
  - `feedback.ask_due(session, today: dt.date) -> int` inserts `(owner_id, 60|90)` with `ON CONFLICT DO NOTHING` for owners whose first `published_at` (Dhaka date) is exactly 60 or 90 days before `today`, or up to 7 days before that, to self-heal a missed run.
  - It delivers `HUB_FEEDBACK_QUESTION` to the managing accounts (solo owner; accepted managers), in the same transaction.
- **Answer:** `POST /v1/hub/feedback` takes `{day: 60|90, answer: "yes"|"not_yet"|"not_sure"}` and returns 204. Answering twice overwrites. Answering for a day never asked gets `HUB_FEEDBACK_NOT_ASKED` (409).
- **Clients:** the inbox item for `hub_feedback_question` opens a three-choice prompt on web and Android. Its copy reads "Did the hub bring you a student?" / "হাব থেকে কি কোনো শিক্ষার্থী পেয়েছেন?". The client work is in this task: web plus Android, each with one ViewModel/component test.

- [ ] **Step 1: Write failing tests:**
  - `test_asks_at_day_60_and_90_dhaka_date`;
  - `test_self_heals_missed_run_within_7_days`;
  - `test_idempotent_concurrent_runs` (two overlapping `ask_due`, exactly one row per (owner, day));
  - `test_answer_overwrites_and_refuses_unasked_day`;
  - `test_centre_managers_receive_question`;
  - `test_deletion_disposition`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the backend, cron entry and both clients.
- [ ] **Step 4: Run** the gate, `cd web && npm run check`, and `make android && make android-quality`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): ask publishing teachers whether the hub brought a student`.

### Task 9: Signed-in report entry — web screen, Android App Link, `assetlinks.json`

**Files:**
- **Web:** `web/src/features/common/HubReport.tsx` with a test; route `/hub-report` in the signed-in router; the strings.
- **Android:**
  - the report screen and ViewModel with tests under `feature/hublisting/report/`;
  - `AndroidManifest.xml`: an `<intent-filter android:autoVerify="true">` on the main activity for `https://${appHost}/ui/hub-report`, where the host is a manifest placeholder per build type;
  - navigation and strings.
- **`assetlinks.json` on the app host:** App Links verify against the host in the intent filter, which is the web-app host served by the API distribution, not the marketing site.
  - `deploy.yml` writes `.well-known/assetlinks.json` to the web bucket root from SSM `android-cert-sha256` (a new parameter, documented in `web/README.md`), with `Cache-Control: max-age=3600` and `Content-Type: application/json`. The deploy step fails when the parameter is unset.
  - `infra/modules/cdn/main.tf` gains an ordered behaviour for exactly `/.well-known/assetlinks.json` to the web origin, GET/HEAD, with the managed caching-optimized policy.
  - A gate test in `tests/gates/test_deploy_workflow.py` asserts the upload step and the behaviour both exist.

**Interfaces:**
- **Query:** `kind ∈ {owner_listing, batch_listing}` and `id` must be a UUID. Anything else shows "This link isn't valid" with no request sent.
- **Signed-out users:** sign in first, then return to the report.
- **The form:** a reason, from the server vocabulary with localized labels, and an optional note of at most 500 characters. It calls `POST /v1/hub/reports`.
- **Errors:**
  - `REPORT_TARGET_NOT_FOUND` → "This listing can no longer be reported";
  - `REPORT_ALREADY_FILED` → "You've already reported this";
  - `HUB_REPORT_CEILING` → its own message;
  - a network failure → Retry, keeping the input.

- [ ] **Step 1: Write failing tests:**
  - web: `opens from the query, sends reason and note`, `rejects bad kind or id without a request`, `signed-out user is sent through sign-in and back`, `failure keeps input and offers retry`;
  - Android: the ViewModel state machine equivalents, plus a manifest test asserting the intent filter is present with `autoVerify`;
  - gates: `test_deploy_writes_assetlinks_with_package_and_fingerprint` (the generated JSON names `com.shikkhokplus.app` and the SSM value) and `test_cdn_routes_assetlinks_to_web_origin`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `cd web && npm run check`, `make android && make android-quality`, `pytest tests/gates -q` and `make infra-functions`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): signed-in report entry from public pages on web and Android`.

### Task 10: Editors — preview and "View public page"

**Files:** web `web/src/features/teacher/hub/Listing.tsx` and its tests; Android `ui/HubListingScreen.kt` and its tests; the strings.

**Interfaces:**
- **"Preview as public":**
  - Web opens `GET /v1/hub/listing/preview?locale=` in a new tab. It is an authenticated fetch rendered into a sandboxed `<iframe srcdoc>` with `sandbox=""`, so the page cannot run anything.
  - Android opens it in a WebView with JavaScript disabled.
- **"View public page":** shown only when the listing is `published`. It opens `{SITE_URL}/hub/{locale}/t/{slug}`. `SITE_URL` comes from build config (web `VITE_SITE_URL`, Android `BuildConfig.SITE_URL`); add it where missing.

- [ ] **Step 1: Write failing tests:**
  - web: `preview renders server HTML in a sandboxed frame`, `view-public link only when published`;
  - Android: the matching ViewModel and screen tests.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the client gates. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): preview as public and view public page in both editors`.

### Task 11: Deploy, smoke and release deliverables

**Files:**
- Modify:
  - `.github/workflows/deploy.yml`:
    - pass `SHIKKHOKPLUS_SITE_DISTRIBUTION_ID` to the API container;
    - read SSM `android-cert-sha256` into the site build;
    - after the site and API deploy, smoke `GET {site}/hub/en` (200, CSP present), `GET {site}/hub/sitemap.xml` (200), `GET {site}/hub/en?utm=x` (400), and `GET {api}/hub/en` (404);
  - `deploy/smoke.py` (a `--hub` mode, with tests in `tests/gates/test_deploy_workflow.py`);
  - `deploy/docker-compose.staging.yml` (forward the env var);
  - `docs/legal/PRIVACY.md` (regenerated);
  - `docs/legal/README.md` (the Data Safety delta: new public display of teacher listing text, area and opt-in contact; reports; feedback answers);
  - the site pages `site/src/pages/index.html` and `site/src/pages/bn/index.html` (a "Find a tutor" link to `/hub/en` and `/hub/bn`; "Private by design" copy adjusted to say listings are opt-in);
  - `CHANGELOG.md`: none, because it is generated at release.

- [ ] **Step 1: Write failing tests:** `test_deploy_smokes_hub_routes` and `test_deploy_passes_distribution_id`, in the deploy workflow gate. Site `build.test.mjs` checks the new links exist in both twins.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make check` (the full gate, once, at the end of the plan). Expected: every target green.
- [ ] **Step 5: Commit** `feat(deploy): smoke the public hub and publish the release deliverables`.
