# Public Hub — Product Requirements (PM view)

Status: advisory draft, not an AI-DLC artifact. Source: owner proposal (BRIEF.md, verbatim) [desc]; product facts from `app/db/models.py` and the brief.

## 0. The position in one paragraph

The hub is worth building. It turns the people already using the product into a public directory, which is the growth loop the product lacks. The proposal as written cannot ship, though. Listing every tutor automatically, showing student-written comments on every batch, and letting the platform admin moderate those comments break three binding rules: D-5, D-6 and the Families-policy commitments (RC-1..RC-3). The MVP below keeps the proposal's intent and changes three defaults. **Listing is opt-in. Reviews come from adult (guardian) accounts only, are pre-moderated and are shown under a pseudonym. Rule amendments land before any code (H0).** With those three changes the hub is shippable within the USD 50 budget.

## 1. Personas and jobs-to-be-done

| Persona | Job to be done | What they need from the hub |
|---|---|---|
| **Guardian / parent** (primary decision maker; pays the fee) | "Find a reliable tutor or centre near us, for my child's class and subjects, at a fee I can afford, and know whether other parents were satisfied." | Filters (class, subject, area, fee), schedule, trustworthy ratings, a way to make contact |
| **Prospective student** (mostly 12–18; SSC/HSC) | "Find a batch my friends rate, at a time that fits school." | Browse and search. Must **not** have to give personal data to browse |
| **Solo tutor** | "Fill empty seats without paying for Facebook boosts, and look credible." | A rich profile, batch listings, an "accepting students" signal, replies to reviews, control over what is public |
| **Coaching centre manager** | "Show the centre's full timetable and faculty, and win enrolments from rival centres." | A centre profile that aggregates all batches, per-batch listings, control over which teacher members are named |
| **Platform admin / moderator** | "Keep the hub safe and lawful without seeing children's data." | A moderation queue that shows review text and the report reason only, plus takedown tools and an SLA view |
| **Anonymous web visitor / search engine** | "Land on a page from Google for 'physics tutor Mirpur HSC'." | Fast pages that work without JavaScript and are indexable, with EN and BN twins |

## 2. Scope

**MVP**
- Owner profile listing and batch listing, both opt-in, moving from draft to published, with photos and PDFs.
- Public web pages (server-rendered, readable without JavaScript) with search, filters and sort, in EN and BN, plus a sitemap.
- Ratings and reviews from **guardians** on eligible enrollments: pre-moderated, pseudonymous, with one owner reply per review.
- Reporting of listings and reviews, an admin moderation queue, and takedown.
- Contact through the channel the owner chose to publish (call or WhatsApp link). The hub collects no visitor data.
- Notifications to owners and reviewers. Lifecycle cascades for deletion and deactivation.

**Phase 2**
- Reviews written by students, once there is an age signal. [Decision needed]
- An in-app "request to join" enquiry that creates a lead in the owner's inbox (H7).
- Sub-dimension ratings.
- Area and subject landing pages for SEO.
- Hub browsing inside the Android app (a native screen rather than a link out).
- Manual identity or qualification verification badges.
- Saved and shortlisted listings.

**Out of scope**
- Online booking, seat reservation or payment through the hub.
- Promoted or paid placement. Ads of any kind (D-37).
- Messaging between strangers.
- Student photos, names, marks or attendance on any public surface.
- Third-party analytics on public pages.
- Importing reviews from other platforms.

## 3. Functional requirements

### (A) Listing and publishing

- **HUB-FR-1** An owner has at most one hub profile. It holds a display name, a bio (≤1,500 characters, BN or EN), qualifications (free-text list, ≤10 items), years of experience (integer), locality (division, district, upazila or thana and area, chosen from a fixed list; **no street address**), up to 6 photos, a logo or avatar, and a public contact (phone and/or WhatsApp, entered separately, never copied silently from the account phone).
- **HUB-FR-2** A batch listing extends one existing `batch`. It holds a description (≤2,000 characters), class level (fixed list: Class 1–12, SSC, HSC, Admission, O/A Level, Other), curriculum (National-Bangla, National-English version, English-medium (Cambridge/Edexcel), Madrasah, Other), mode (offline, online or hybrid), area (inherited from the profile, overridable), up to 6 photos and up to 5 PDFs (≤5 MB each, e.g. syllabus or routine). The listing **derives** its subjects from `batch_subject` and its weekly schedule from `schedule_slot`. Neither is retyped.
- **HUB-FR-3** Showing the fee is optional and is a per-listing switch. When shown, the value is the server-computed `default_fee`, serialized as a money string.
- **HUB-FR-4** Each batch listing carries an owner-set **"accepting students"** flag and an optional seat capacity. The server computes the displayed state, using values such as "Accepting", "Few seats left" (capacity minus accepted seats is 3 or fewer) and "Full". The client never computes it (TC-9).
- **HUB-FR-5** Profile and listings move through `draft → published → unpublished`. A draft is visible only to its owner lens. Publishing requires every required field and the publish consent in HUB-FR-6. Unpublishing removes the listing from public pages, search and the sitemap at once, with a CDN purge (≤5 minutes) [Decision needed: whether 5 minutes is acceptable].
- **HUB-FR-6** Publishing is **opt-in**. The first publish records the consent in a consent record (who, when, which consent-text version): a statement that the listed content will be public and indexable. Nothing is listed by default. This deliberately departs from "all tutors will be listed" [Decision needed; recommended default: opt-in].
- **HUB-FR-7** At a centre, only a `manager` member can publish the centre profile and its batch listings. A teacher member's name appears on a listing only after that member accepts a "show my name publicly" consent. Otherwise the listing shows "Centre faculty".
- **HUB-FR-8** A batch with `active = false` is automatically unpublished from the hub and cannot be published.
- **HUB-FR-9** Uploading a photo requires an attestation: "contains no identifiable child, or I hold the guardian's consent". The MVP recommendation is stricter: **no identifiable children at all**, enforced by moderation [Decision needed].

### (B) Discovery

- **HUB-FR-10** Filters available: subject (normalized from `batch_subject` names to a fixed subject vocabulary, with free text mapped to "Other"), class level, curriculum, area (hierarchical), mode, fee range (only listings that show a fee match a fee filter), minimum rating, and "accepting students only".
- **HUB-FR-11** Sort options: relevance (default), rating (Bayesian average, see FR-24), fee from low to high, and newest. A text query matches owner name, batch name, subjects and area, in Bangla or English script.
- **HUB-FR-12** Every published profile and batch has a stable, canonical URL, an EN twin and a BN twin (`hreflang`), a `<title>` and meta description, schema.org `EducationalOrganization` / `Course` JSON-LD **without `AggregateRating` markup until review volume makes it honest** (Phase 2), and an entry in a sitemap regenerated whenever something is published or unpublished.
- **HUB-FR-13** Search result pages are `noindex`. Profile and batch pages are indexable.

### (C) Ratings and reviews

- **HUB-FR-20 Eligibility (server predicate).** An account may review an enrollment only when **all** of the following hold:
  1. the account is that enrollment's `guardian_account_id` and `guardian_decision = accepted` (MVP);
  2. the batch is published on the hub;
  3. `joined_on` is at least 30 days ago;
  4. at least 4 sessions are recorded with that enrollment marked present;
  5. if `inactive_from` is set, it is at most 90 days ago, so leavers can still review;
  6. no review already exists for that enrollment.
- **HUB-FR-21** One review per enrollment. A guardian with two children in the same batch therefore writes two reviews. [Decision needed: one per guardian per batch instead; recommended to keep it per enrollment.]
- **HUB-FR-22** Each review has an overall rating of 1–5 stars (required) and optional text (20–1,000 characters). On submit the server rejects text that contains a phone number, email address or URL. The UI warns against naming a child.
- **HUB-FR-23 Display.** A review appears under a pseudonym that the server builds from coarse facts only. Example: "Guardian · Class 9 · enrolled 5 months · March 2026". It never includes a name, photo, phone, exact join date or enrollment id. **No API response in any lens returns the author's account id, enrollment id or student id for a review.** That includes the owner's own lens.
- **HUB-FR-24 Retaliation and inference guard.**
  - Individual reviews on a batch page are published only once the batch has **at least 3 published reviews**. Until then the reviews feed only the owner aggregate.
  - A review's public date is the **month only**, and publication is batched weekly.
  - Batch and owner aggregates use a Bayesian average (prior 3.5, weight 5) and appear as stars only once there are 3 or more reviews. Below that the page says "New on ShikkhokPlus".
- **HUB-FR-25** The author may edit or withdraw a review for 30 days after it is published. An edit goes back to moderation. After 30 days the author can only withdraw.
- **HUB-FR-26** The owner may post one public reply per review (≤500 characters). The reply can be edited and is moderated through the same queue. The owner cannot hide or delete a review. The owner can only report it (FR-30).
- **HUB-FR-27 Moderation states.** `submitted → pending → published | rejected`; `published → hidden (by report outcome) → restored | removed`; `withdrawn`. Every review is **pre-moderated** in the MVP. Only `published` reviews are public or counted.
- **HUB-FR-28** Reviews attach to the batch and roll up to the owner aggregate. When a batch is deactivated or unpublished, its reviews stay in the owner aggregate and are listed on the owner page under "Past batches".
- **HUB-FR-29** When the author deletes their account, their reviews and replies to them are **hard-deleted** and the aggregates are recomputed. When the owner deletes their account, the whole listing, all reviews on it and its media are deleted. Removing a student from a batch does not affect a review already published.

### (D) Contact and enquiries

- **HUB-FR-40 (MVP)** A "Contact" control shows the owner's published phone or WhatsApp as `tel:` and `https://wa.me/` links. The hub collects no visitor data and needs no sign-in.
- **HUB-FR-41 (Phase 2, H7)** A signed-in adult account can send a "request to join" enquiry: the requester's name, the class, and a message of up to 300 characters. It creates a lead in the owner's inbox and shares the requester's phone **only after** they consent explicitly. Accepting a lead pre-fills the existing add-student flow.

### (E) Moderation and trust

- **HUB-FR-30** Any visitor can report a listing, a photo, a document or a review. No sign-in is needed. The report captures a reason (spam or fake, offensive, personal information about a child, an image of a child, misleading information, other) and optional text. Reports are rate-limited by IP. A signed-in reporter can see the report's status.
- **HUB-FR-31** The admin moderation queue is built on the help-ticket precedent. It shows the item content, the report reasons and counts, and the moderation history. Actions: approve, reject (with a reason code), hide, restore, remove, and suspend the listing. Every action is logged with the admin and the reason.
- **HUB-FR-32** SLA: pending reviews are decided within 48 hours. "Image of a child" or "personal information about a child" reports trigger **automatic hiding** at the first report, and an admin then decides within 24 hours. The queue shows how long each item has waited.
- **HUB-FR-33** A listing that collects 3 or more upheld violations is suspended, and the owner is notified with the reason codes.
- **HUB-FR-34** A computed "Active on ShikkhokPlus" badge appears when an owner has 5 or more accepted enrollments and attendance recorded in the last 30 days. It is computed, not granted manually. Manual verification is Phase 2.

### (F) Notifications (existing `notification` inbox; no new push SDK)

- **HUB-FR-50** An eligible guardian gets one in-app prompt when an enrollment first becomes review-eligible. There are no repeat nags.
- **HUB-FR-51** The reviewer is notified of the moderation outcome (published or rejected with the reason code).
- **HUB-FR-52** The owner is notified of a newly published review, a newly published reply, any moderation action on their content, and suspension.
- **HUB-FR-53** Admins are notified when an auto-hide fires, and when the queue holds items older than 36 hours.

### Key acceptance criteria (Given/When/Then)

1. **Opt-in (FR-6)**
   - **Given** a tutor with active batches who has never published,
   - **When** an anonymous visitor searches the hub,
   - **Then** none of that tutor's batches or details appear in results, pages or the sitemap.
2. **Unpublish (FR-5)**
   - **Given** a published batch listing,
   - **When** the owner unpublishes it,
   - **Then** the listing's URL returns 410 within 5 minutes and the sitemap no longer contains it.
3. **Eligibility (FR-20)**
   - **Given** a guardian whose enrollment is accepted, joined 29 days ago, with 6 present sessions,
   - **When** they attempt to review,
   - **Then** the server refuses with `not_yet_eligible`.
   - On day 30 the same request succeeds.
4. **Student exclusion (FR-20)**
   - **Given** the student account on an eligible enrollment,
   - **When** it attempts to review in the MVP,
   - **Then** the server refuses with `not_eligible`.
5. **Author anonymity (FR-23)**
   - **Given** a published review,
   - **When** the owner lens, the admin lens or the public endpoint fetches it,
   - **Then** no response contains the author's account id, enrollment id, student id, name, phone or join date. A test over the generated OpenAPI schema enforces this.
6. **Threshold (FR-24)**
   - **Given** a batch with 2 published reviews,
   - **When** its public page is rendered,
   - **Then** no individual review text appears and no star average appears.
   - The third published review makes all three appear.
7. **Pre-moderation (FR-27)**
   - **Given** a newly submitted review,
   - **When** any public page or the owner's own screen renders,
   - **Then** the review is absent until an admin approves it.
8. **Child-image auto-hide (FR-32)**
   - **Given** a published photo,
   - **When** one visitor reports it as "image of a child",
   - **Then** it disappears from public pages immediately and appears in the queue flagged for a 24-hour decision.
9. **Deletion cascade (FR-29)**
   - **Given** a guardian with 2 published reviews,
   - **When** they delete their account,
   - **Then** both reviews and any replies to them are gone and the owner aggregate is recomputed without them.
10. **Fee as money (FR-3)**
    - **Given** a listing that shows its fee,
    - **When** the JSON endpoint is read,
    - **Then** the fee is a decimal string such as `"1500.00"`, never a JSON number.

## 4. Non-functional requirements

### Privacy: rule mapping and the amendments needed

| Rule | Collision | Amendment proposed (H0, through the learnings ritual, human-gated) |
|---|---|---|
| **D-5 / TC-13** "NEVER expose anything a student or guardian writes to any teacher" | A public review is guardian-written text that the teacher reads | Add one narrow exception: *"…except a hub review that its author explicitly submitted for public display after seeing the public-display notice, shown under a server-generated pseudonym and never linked, in any lens or response, to the author's account, enrollment or student record."* The profile table, RLS and every other student-written field stay untouched. |
| **D-6 / TC-14** admin sees subscriber info only | Moderation means reading review text | *"…except that a moderator may read hub review and reply text, report reasons and moderation history for items in the queue, never the author's identity, phone, profile, or any student record."* The admin review endpoint's schema is tested to contain no author fields. |
| **RC-1..RC-3** Families policy, COPPA, GDPR-K | User-generated content in an app with a child audience; minors as reviewers | MVP reviewers are guardians only. Every item is pre-moderated. In-app reporting is provided, as the Play UGC policy requires. Public pages collect no visitor data and set no cookies. Proposed new **FORBIDDEN**: no student-identifying data (name, photo, marks, attendance, enrollment date) on any public surface. |
| **RC-4 / RC-5** Data Safety and privacy policy | New collection (reviews, owner media, consent records) and new public display | Update the Data Safety form: user-generated content collected; owner photos collected. The privacy policy gains a "Public Hub" section generated from the per-table deletion dispositions (the existing practice). A Families/UGC declaration review happens before release. |
| **TC-9 / D-31** | Aggregates and seat state | The server computes the average, the threshold, the badge, seat state and eligibility. The client renders them. |
| **TC-7 / D-20** | Displayed fee | `Money` type, string on the wire. |
| **D-37 / TC-3 / TC-6** | Temptation to add web analytics | No third-party scripts on hub pages. Only server-side request counts. |

Two further privacy requirements:
- Every upload has its EXIF and GPS metadata stripped before storage. This is mandatory, because tutors photograph their homes.
- A listing never shows a street address. Area granularity stops at locality.

### Minors' safety
- The rule against identifiable children is enforced by the attestation, the auto-hide report reason and moderation.
- The review pseudonym, the 3-review threshold and month-only dates make it hard for a teacher to identify an individual reviewer in a small batch.
- [Decision needed] Batches with fewer than 5 total accepted enrollments ever never show individual reviews. Recommended: yes.

### Abuse and rate limits
- Report submissions: 10 per IP per hour. Review submissions are already bounded by eligibility (one per enrollment).
- Text filters reject contact details in reviews. Owner text is held to the same rule outside the dedicated contact field.
- Uploads: 6 photos per entity, 20 MB per owner, image types allow-listed by magic bytes, PDFs validated and re-served with `Content-Disposition` and a strict CSP.
- Search: 60 requests per IP per minute, with CDN caching in front.

### Performance (low-end Android on 3G in Bangladesh)
- Public pages render fully **without JavaScript**.
- HTML plus CSS for the first view is at most 60 KB compressed. The above-the-fold image is a WebP of at most 80 KB, and the other images lazy-load.
- Under Lighthouse mobile throttling ("Slow 4G" / 3G profile), LCP is 2.5 s or less on a profile page. This is checked in CI against a seeded staging page.
- Page reads are served from the CloudFront cache with a TTL of 10 minutes or more and purged on publish. Cached TTFB is under 200 ms; uncached search is under 800 ms at p95.

### SEO
- One canonical URL and EN/BN twins per page.
- Every page is in the sitemap.
- Text is server-rendered.
- Unpublished pages return 410.
- No `AggregateRating` markup in the MVP (FR-12), which avoids review-snippet policy risk.

### Bangla-first (D-43) and accessibility
- Every hub string ships with BN and EN twins.
- Search matches both Bangla and Latin transliteration of subjects and areas.
- Layout is verified at the longest Bangla string on a 360 dp screen, using the existing per-screen check.
- WCAG 2.1 AA contrast.
- Star ratings carry a text equivalent ("৪.২ / ৫").
- Every photo has owner-supplied alt text, which is required to publish.

### Cost (OC-4)
- No search service. PostgreSQL full-text search plus trigram indexes are enough.
- Media goes in the existing account's S3 behind CloudFront.
- Image resizing happens in the API process at upload, not in a separate service.
- Target incremental cost is under USD 5/month at 1,000 listings. H1 must include a cost estimate that the developer checks before merge.

## 5. Work units (dependency order)

| Unit | Goal | Scope | Depends on | Size | "Done" verifier |
|---|---|---|---|---|---|
| **H0 Policy and consent prerequisite** | Make the hub lawful under our own rules before code exists | D-5, D-6 and new FORBIDDEN amendments through the learnings ritual; privacy-policy "Public Hub" section; Data Safety and Families/UGC declaration delta; community guidelines (BN/EN); consent text v1 for publish, faculty name and review notice; per-table deletion dispositions for the new tables | — | M | Amended rules present in `project.md` with the owner's affirmation; generated privacy policy includes every new table's disposition (existing generator test extended); signed checklist of declaration changes |
| **H1 Media foundation** | Safe uploads that are cheap to serve | Presigned upload to a private bucket; magic-byte type check; size and count limits; EXIF stripping; WebP variants; PDF validation; media visible publicly only when its parent is published; delete cascade; cost estimate | H0 (dispositions) | L | Tests: a disallowed type is rejected; an uploaded JPEG has no EXIF/GPS; media of an unpublished listing returns 403; deleting the owner removes the objects; Terraform plan reviewed against budget |
| **H2 Listings and publishing** | Owners can author and publish | Profile and batch-listing tables; draft/publish/unpublish; consent records; faculty consent; seat state; owner editing screens in Android and the web PWA; locality and subject vocabularies | H0, H1 | L | Tests: FR-5/6/7/8 state transitions; seat state computed server-side; schema invariant that no listing response contains a student, enrollment or profile field; `PUBLIC_ROUTES` count updated and asserted |
| **H3 Public pages and discovery** | Visitors and search engines find listings | Server-rendered EN/BN pages; search and filters; sort; sitemap; 410 on unpublish; CDN cache and purge; report button entry | H2 | L | AC-1, AC-2 tests; Lighthouse budget job in CI; EN/BN twin check; HTML validates; zero `<script>` from third parties (grep gate) |
| **H4 Reviews** | Trustworthy, safe ratings | Eligibility predicate; submit, edit and withdraw; pseudonym; thresholds; Bayesian aggregate; owner reply; display stays dark until H5 ships | H0, H2, H3 | L | **Test-first** (an authorization predicate): AC-3, 4, 5, 6, 7; OpenAPI schema test that no review response in any lens carries author identifiers |
| **H5 Moderation and trust** | Nothing unsafe stays public | Report intake; admin queue on the help-ticket pattern; actions and audit; auto-hide; SLA view; suspension; computed badge | H4 | M | AC-8; admin endpoint schema has no author fields; moderation actions are audited; a queue-age query exists. **H4 and H5 release together**: the review display switch flips only after H5 merges |
| **H6 Notifications and lifecycle** | Close the loops | FR-50..53; deletion cascades (FR-29); batch deactivation (FR-8, FR-28) | H4, H5 | S | AC-9; the existing account-deletion tests extended to the hub tables, per the dispositions |
| **H7 Enquiries (Phase 2)** | Convert visitors into leads | FR-41 with consent; lead inbox; pre-fills add-student | H3, H6 | M | Tests: the phone is not shared without consent; enquiry rate limits |

## 6. Open questions

1. **Opt-in or listed by default?** Recommended: opt-in (FR-6). The proposal says "all will be listed". [Decision needed]
2. **Who may review in the MVP?** Recommended: guardians only. Student reviews wait for an age signal in Phase 2. Do we accept that adult students (HSC/admission age, 18+) without a guardian cannot review in the MVP? [Decision needed]
3. **Eligibility thresholds**: 30 days and 4 present sessions. Should the attendance condition be dropped for owners who do not record attendance? Without it, fake reviews from seeded enrollments are easier. [Decision needed]
4. **Pre-moderation load.** Who is the moderator, and is a 48-hour SLA realistic with a solo operator? If not, cap review intake or launch the hub in one city first. [Decision needed]
5. **Children in photos**: a strict ban (recommended) or guardian-consented images allowed?
6. **Fee visibility**: optional (recommended), or required so that the fee filter is useful?
7. **Hub inside the Android app** in the MVP, or a web link only (recommended)?
8. **Public URL host**: a separate `hub.` hostname or a path on the marketing site? This is an architecture call, but it changes the CSP, the sitemap and the budget.
9. **Legal review** of the D-5 amendment, and of whether public display counts as "sharing" for the Data Safety form. Recommended: an external counsel check before H4 release.
10. **Owner response to negative reviews**: is a right-of-reply sufficient, or should a dispute path (an owner report that pauses the review) exist? Recommended: report only, with no pause.
11. **Centres with many teachers**: should reviews ever be attributed to an individual teacher member? Recommended: no, attribute to the batch only.
