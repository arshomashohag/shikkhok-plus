# Public hub — design

Date: 2026-11-14
Status: draft for approval. All product decisions are recorded below and were
approved by the owner on 2026-11-14.
Source analysis: `docs/reviews/2026-11-14-public-hub/REPORT.md` (the reconciled
CEO, product, design and engineering report), with the detail behind it in
`docs/reviews/2026-11-14-public-hub/team/technical-design.md`. Mockups:
`docs/reviews/2026-11-14-public-hub/mockups.html`.

## Why

ShikkhokPlus charges nobody and grows one teacher at a time. Today it saves a
tutor time; a public hub lets it also bring them students, which is what a
tutor's income depends on. It is also the one thing Facebook groups and
classified sites cannot copy: reviews from people we *know* held a seat.

Success: families searching for "HSC physics tutor Mirpur" land on a
ShikkhokPlus page, find a tutor or centre near them with the subjects,
schedule and (if the owner shows it) fee, and contact them. Teachers who
publish get students. No child's data ever appears on a public page.

Anti-goals. Each of these would make the hub a failure even if it works:
- an existing user finds themselves listed without having agreed;
- a child's name, photo, marks or attendance appears publicly;
- a teacher can work out which family wrote a review;
- the hub needs JavaScript, cookies or a third-party script on public pages;
- hosting rises past the USD 50/month ceiling.

## Owner decisions, 2026-11-14

| # | Decision |
|---|---|
| D1 | **Opt-in listing.** Every owner gets a ready-made draft; nothing is public until they publish. Each batch is published separately. A teacher at a centre is named only after that teacher agrees. |
| D2 | **Reviews from verified guardians only in V1.** The guardian must hold an accepted seat for at least 30 days with at least 4 attended classes. Student reviews come later, behind an age signal. |
| D3 | **Amend D-5** so a review its author submits for publication may be shown, with the safeguards in §6. |
| D4 | **Amend D-6** so an admin may see content submitted for publication, under an opaque author reference. |
| D5 | Raise `PUBLIC_ROUTES` from 14 to 18. |
| D6 | Update the site copy, Data Safety form, privacy policy and Families user-content declaration. These block release. |
| D7 | The owner moderates alone: 48 h for photos and reviews, 24 h for child-safety reports, reviews published weekly. |
| D8 | A local legal review of the review policy happens before free-text reviews go live. |
| D9 | Reviews are built only if the directory meets the day-90 demand bar in §9. |
| D10 | No PDFs in V1. Syllabus and routine are structured text fields. |

## What the codebase already gives us

- Batches hang off `owner`, which already models a solo tutor (`kind =
  'teacher'`) and a centre (`kind = 'organisation'`, named), with accepted,
  revocable `owner_member` rows (`app/db/models.py`). A listing is one more
  thing an owner has.
- Subjects (`batch_subject`), weekly schedule (`schedule_slot`) and rooms are
  already structured, so a listing derives them rather than retyping them.
- The lens is resolved per request and every route must name one or be in an
  asserted allowlist (`app/contract/routes.py`), so new public routes are a
  deliberate, counted change.
- Restricted database roles with a meta-test (`shikkhok_app`, the RLS
  meta-test) give us the pattern for a read-only public role.
- The admin app (`app/api/admin.py`, `app/admin/`) and help tickets
  (`app/help/`) give us a moderation queue pattern with an opaque requester
  label (`app/help/identity.py`).
- The marketing site has its own CloudFront distribution with a no-JavaScript
  CSP (`infra/modules/site`). The seeder Lambda (`infra/modules/seeder`) is a
  precedent for a small free-tier Lambda.
- `app/api/html.py` already serves HTML with strict security headers.

## What does not fit today

1. **The privacy gate cannot see public pages.** `forbidden_fields()` in
   `app/contract/privacy.py` checks only teacher-facing routes, and only JSON
   `response_model` schemas. A public HTML page has neither, so as built a hub
   page could print a child's name and every gate would pass.
2. **A solo tutor has no public name we may read.** `owner.name` is set only
   for centres; the tutor's own name is `profile.self_name`, behind row-level
   security. The hub must collect its own `public_name`.
3. **`batch.collection_number` is the tutor's personal bKash or Nagad
   number**, on the same row as everything a batch page wants to show.
4. **No upload path exists.** `python-multipart` is deliberately absent,
   there is no image library, and the instance role reaches no media bucket.
5. **No public cache is safe on the API distribution.** It caches nothing,
   on the stated reasoning that a cached authenticated response is a
   cross-teacher leak.
6. **No float and no Python `decimal` outside `app/money`**, so a rating
   average must be computed in SQL.

## Approaches

**Where public pages are rendered** (decided in the team analysis):

| Option | Trade-off | Verdict |
|---|---|---|
| JSON API consumed by the PWA and Android | Not indexable; doubles the UI work | Rejected for public browsing |
| Prerender static HTML into the site bucket | Static pages cannot search, so search would need a second, dynamic path | Rejected |
| **Server-render HTML from the API, served through the site distribution on a cached `/hub/*` path** | One renderer, dynamic search, crawlers absorbed by the cache | **Chosen** |

**Phasing** (decided): one launch, rejected as putting the two hardest privacy
surfaces first; **directory, then photos, then reviews**, chosen.

**PDFs** (decided, D10): safe rendering, malware scanning and phishing links
cost more than they earn now; structured text is searchable and bilingual.

## Design

### 1. Releases and units

| Release | Units | Contents |
|---|---|---|
| R1 Directory | H0, H1, H2 | Opt-in profiles and batch listings, public pages, search, sitemap, reports, suspension |
| R2 Photos | H3 | Moderated photos |
| R3 Reviews | H4 | Verified-guardian reviews, replies, moderation |
| Optional | H5 | Join requests through the app |

Each unit is its own spec-to-plan cycle and its own short-lived branch. H0 must
merge before any public route exists.

### 2. Modules and boundaries

| Module | Owns | Boundary |
|---|---|---|
| `app/hub/listings` | Owner and batch listings, slugs, area vocabulary, publish state | Imports no fees, marks, students or guardians code |
| `app/hub/public` | Search, page view models, Jinja2 templates, sitemap | **Import gate**: nothing from `app.*` beyond an allowlist. Every query runs under `SET LOCAL ROLE shikkhok_hub_reader`. |
| `app/hub/media` | Upload sessions, presigned S3 POST, invalidation outbox | Pillow lives only in the Lambda |
| `app/reviews` | Eligibility, `ReviewerLens`, lifecycle, replies, rating arithmetic | Never imported by `app/hub/public` |
| `app/moderation` | Admin queues, decisions, `hub_moderation_event` | Behind `admin_gate` |

`shikkhok_hub_reader` may `SELECT` only `bd_area` and the four views
`hub_public_owner`, `hub_public_batch`, `hub_public_media` and
`hub_public_review`.

### 3. Data (migrations 0034–0037)

```
bd_area           code PK, kind (division|district|upazila), parent_code,
                  name_en, name_bn                          -- seeded, ~570 rows
owner_listing     owner_id PK, slug UNIQUE, status (draft|published|hidden|suspended)
                  default draft, public_name NOT NULL, headline_en/bn, bio_en/bn,
                  qualifications, teaching_mode[], district_code, upazila_code,
                  street_address (centres only, trigger), public_contact_phone
                  (opt-in, never prefilled), consent_version/at/by,
                  published_at, suspended_at, suspension_reason_code,
                  search_text GENERATED
batch_listing     batch_id PK, owner_id, slug (unique per owner), status,
                  description_en/bn, syllabus_en/bn, class_levels[], curriculum,
                  subject_tags[], mode, admissions (open|waitlist|closed),
                  show_fee, show_schedule  -- NOT NULL, no default
listing_media     id, owner_id, batch_id NULL, kind (image), status
                  (awaiting_upload|processing|pending_review|approved|rejected|withdrawn),
                  quarantine_key, public_key (only when approved, CHECK),
                  sha256, width, height, alt_en/bn, position, rejection_code
cdn_invalidation  id, path, requested_at, sent_at, aws_id   -- outbox
review            id, batch_id, author_account_id, enrollment_id, author_role
                  (guardian|student; V1 guardian), rating 1-5, body <= 1000,
                  status (pending|published|rejected|removed), tenure_bucket,
                  published_month, edited_at, decided_at
                  UNIQUE (batch_id, author_account_id)
review_reply      review_id PK, body <= 1000, status, written_by_account_id
hub_report        id, target_kind (listing|media|review|reply), target_id,
                  reporter_account_id, reason, status
                  UNIQUE (target_kind, target_id, reporter_account_id)
hub_moderation_event  append-only, closed enums, no free text
listing_enquiry   optional (H5)
```

There is no aggregate table. The average is
`round(10*sum(rating)::numeric/count(*))::int`, sent as integer tenths
(43 = 4.3). Sorting by rating uses a Bayesian score (prior 3.5, weight 5),
computed in SQL. Every new table gets its `DISPOSITIONS` entry in the same
migration: listings and media are hard-deleted with a solo owner; a centre's
listing survives a manager's deletion; reviews and reports are hard-deleted
with their author; moderation events are kept 12 months, invalidations 7 days.

### 4. Public pages and caching

- Routes P1–P4: `GET /hub/{en|bn}`, `/hub/{en|bn}/t/{owner}`,
  `/hub/{en|bn}/t/{owner}/{batch}`, `/hub/sitemap.xml`.
- The site distribution gets a second origin (the API, with its
  `X-Origin-Secret`) and a GET/HEAD-only `/hub/*` behaviour. It forwards **no
  headers and no cookies**, and only an allowlist of query parameters, which a
  viewer-request function normalises and enforces.
- The API distribution answers 404 on `/hub*`.
- Owner and batch pages are cached for 10 minutes; search for 5 minutes;
  draft, suspended and missing listings get a byte-identical 404.
- Takedowns go through the `cdn_invalidation` outbox in the same transaction,
  drained by a cron job.
- Pages carry no JavaScript and use the CSP
  `default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`.
  Search is a plain GET form.
- The site module's "there is no API behind it" comment is rewritten in the
  same change.

### 5. Photos (R2)

1. A presigned **POST** (≤ 8 MB, JPEG, PNG or WebP) uploads to `quarantine/`.
2. A Lambda with no database access and no VPC re-encodes the image to WebP at
   320, 960 and 1600 px, which strips EXIF and GPS data, and writes it to
   `staged/`.
3. An admin approves it, and it is copied to `public/{opaque}`, the only
   prefix CloudFront serves, as `nosniff` with a `sandbox` CSP.

Quotas: 12 owner photos, 8 per batch, 30 uploads per owner per day. Lifecycle
rules expire abandoned objects. Android uses the Photo Picker, which needs no
storage permission. Pillow has its own lockfile in the CVE gate and SBOM.

### 6. Reviews (R3)

Eligibility grants a `ReviewerLens` from one SQL statement, written
test-first. The account must be the guardian on an enrollment with
`guardian_decision='accepted'`, and must not be relink-blocked. The batch
listing must be published. The guardian must have joined at least 30 days ago.
The enrollment must have at least 4 attended, non-cancelled sessions. If
`inactive_from` is set, it must be within the last 180 days.

A non-member gets an identical `NOT_AVAILABLE`. A member who is not yet
eligible gets `REVIEW_NOT_YET_ELIGIBLE` with an `eligible_from` date.

Display rules:
- **Label:** "Verified guardian · enrolled under 6 months / 6–12 months /
  over 1 year". Never a name.
- **Dates:** month only.
- **Publication:** weekly batch.
- **Threshold:** text, average and distribution appear only once the batch has
  3 or more published reviews.
- **Pending reviews** are invisible to everyone, the teacher included.
- **Teachers** read reviews through the same public view, so a review can
  never be joined to a seat.

Owner and author powers:
- **Owner:** one reply, and may report. Never hide or delete.
- **Author:** edit within 30 days, which re-moderates. Delete at any time,
  totally.

Review text matching `01[3-9]\d{8}` (after normalising Bangla digits) or a URL
is refused.

### 7. API

The full table is in `REPORT.md` §7. Summary:

| Group | Routes | Auth |
|---|---|---|
| Public pages | 4 | public, cacheable |
| Owner listing and member name consent | 10 | `TeacherLens` |
| Media | 6 | `TeacherLens` |
| Reports | 1 | lens-exempt, authenticated |
| Reviewable list | 1 | lens-exempt, authenticated |
| My review | 3 | `ReviewerLens` |
| Teacher review and reply | 3 | `TeacherLens` |
| Admin moderation | 7 | `PlatformAdminLens` |

`POST/PATCH /v1/batches` are unchanged. There are 12 new error codes, each
through the five-class hierarchy and added to `message-keys.json` plus the
Android and web bundles. Money stays a JSON string.

### 8. Privacy controls (H0, before any public route)

1. A public-facing audience in `forbidden_fields`, forbidding owner-private
   fields, account ids, every phone field, `collection_number`,
   `display_name`, `enrollment_id` and `student_id`.
2. An HTML view-model registry: a public handler renders only registered
   Pydantic models, which the gate walks.
3. A canary probe: seed unique strings into every private field, render
   every hub page in both locales plus the sitemap, and assert that no canary
   appears.
4. A `hub_reader` meta-test: `SELECT` on `profile`, `enrollment`, `review`
   and `payment_method` raises.
5. A `PUBLIC_CACHEABLE_ROUTES` gate: no auth dependency in any public route.
6. The rule amendments (D3, D4) and the new rules, through the learnings
   ritual:
   - NEVER put student data on a public surface;
   - NEVER render a public page except through a registered view model read
     as `shikkhok_hub_reader`;
   - NEVER list anyone without their recorded consent;
   - ALWAYS pre-moderate hub images and reviews.

### 9. Measures and gates

At day 90 of R1:

| Gate | Condition |
|---|---|
| **Continue** to reviews | Opt-in ≥ 20% of active owners and contact rate ≥ 20% |
| **Freeze** | Opt-in < 10% or < 150 search sessions a month |
| **Pull reviews** | > 5% of reviews reported in a quarter |

Counts are server-side only.

## Left to the builder

- Jinja2 or hand-escaped templates. The analysis recommends Jinja2, pinned and
  locked.
- Exact slug rules and reservation length after unpublishing (suggested 90
  days).
- The subject-tag vocabulary and the Bangla transliteration helper.
- How the server-side checklist weights listing completeness.
- Copy, within the tone of `claude_design/` and the existing string bundles.
