# CEO memo — the ShikkhokPlus Public Hub

**To:** Product owner. **From:** CEO (review team: CEO, PM, Designer, Developer). **Date:** 2026-11-14
**Verdict:** **Yes to a hub, no to the hub as proposed.** We build an opt-in public directory first to test whether families want it. Reviews come later, only from verified guardians, and only after you amend two binding rules on purpose.

---

## 1. Strategic thesis

**What we are today.** We are a free bookkeeping tool that charges nobody (requirements A13, `aidlc/spaces/default/intents/261022-remaining-slices/inception/requirements-analysis/requirements.md`). The site promises "Free, with no ads", "No tracking" and "Private by design" (`site/src/pages/index.html`). We grow one teacher at a time and have no revenue path. The original intent treated a "public tutor discovery marketplace" as a deliberate V1 exclusion. Its only architectural requirement was "not coupling batch visibility to teacher identity" (`.../261016-shikhokplus-tuition-app/ideation/scope-definition/scope-document.md` §3; `intent-capture/intent-statement.md`). **Market research was deliberately skipped** (`ideation/approval-handoff/approval-handoff-questions.md`). So demand for discovery is an untested hypothesis, and the first phase has to test it.

**Why the hub matters anyway:**

1. **It changes what we sell to teachers.** A tutor's income depends on how many students they have. Today we save teachers time. A hub can also bring them students, and new students are worth more to a tutor than saved time. That is the strongest retention lever available to us.
2. **We have something no one else has: verified enrolment.** Facebook groups and classified listings cannot tell whether a reviewer ever attended a class. We know who held an accepted seat and for how long. A review marked "verified guardian, enrolled 9 months" is the one thing in this market that is hard to copy. If we let anyone rate, we give that away.
3. **SEO and growth.** Public pages in Bangla and English for searches like "physics tutor Mirpur" are the cheapest way to acquire users. Each listing also advertises the app to the teacher's peers.
4. **A future revenue path that keeps the promise.** Clearly labelled teacher-side promotion could fund us later without ads, tracking or charging families.

**What it changes.** We go from being a private record-keeper to also being a public publisher of content written by our users. That puts our core promise at stake, so **the hub has to be a separate layer that users consent to and write for publication. It must never be a view onto the private records.**

## 2. The biggest risks, ranked

1. **Auto-listing everyone breaks our promise, and it is the worst part of the proposal.** Every existing user joined under "your own batches stay entirely yours". Publishing them without asking is the kind of breach people do not forgive. It also has concrete leak paths:
   - `batch.collection_number` is often a teacher's personal bKash number.
   - Batch names can contain children's or school names.
   - Centre listings would name teacher-members who never agreed to be named.
2. **Minors writing public reviews.** Most of our users are school students (RC-1..RC-3), and the Play Families policy applies in full. Public content from minors brings several problems:
   - It triggers the user-generated-content moderation duties.
   - A child can be identified from batch context.
   - Defamation exposure: Bangladesh has criminal-law exposure for online defamation. We need local legal advice before any free-text review goes live.
   - Our Data Safety and privacy declarations (RC-4/RC-5) change.
3. **Retaliation, and teachers turning against us.** The teacher being reviewed also marks the child being discussed. In a batch of eight, an "anonymous" review is not anonymous. Teachers are the side we need to keep, and a rating system they find unfair will make them leave. Either harm alone is serious.
4. **Moderation collides with D-6, and we are a solo team.** Moderating reviews means an admin reads content written by guardians, which D-6 forbids as written. One person cannot run a moderation queue with a 24-hour turnaround.
5. **Cost and capacity.** Today there is no media or upload infrastructure, no public read surface beyond 14 counted `PUBLIC_ROUTES`, and a USD 50/month ceiling (OC-4). Photos, documents and a lot of free text are where the cost and the work pile up.

## 3. Decisions on the contested calls

| Question | Position | Reason |
|---|---|---|
| Opt-in or auto-list | **Explicit opt-in, per owner and per batch. Default off for everyone, including all existing users.** | Consent is the only listing consistent with what we promised. |
| Centre listings | The centre is listed by a manager. **Each member teacher's name appears only after that teacher consents.** | A manager's consent does not cover someone else. |
| Who may review | **Guardians only, on an accepted enrolment held for at least 60 days. One review per enrolment, editable. Former guardians may review for 12 months after leaving.** | Verified and adult. Allowing former guardians lowers the risk of retaliation. |
| Students reviewing | **No, in any version, while we cannot verify age.** | We cannot tell an adult student from a minor, and Families policy decides the question for us. |
| Reviewer identity shown | **Never a name.** Shown as "Verified guardian · enrolled N months". The server holds the author link for abuse handling only. | It protects the family while the verification still means something. |
| Small-batch protection | **Aggregate score shown only once a batch has 5 or more reviews. New reviews are released in monthly batches, not one at a time.** | This blunts deanonymisation and retaliation. |
| Review format | **Structured ratings (3–4 named dimensions) first. Free text only after pre-moderation exists.** | Structured ratings cannot defame anyone. |
| Teacher reply / dispute | **One public reply per review. Teachers can report a review on stated grounds** (false fact, personal information, abuse, author not enrolled). | Teachers get a voice and a formal route, not a veto. |
| Teacher can hide reviews | **No.** A reported review stays up unless it breaks policy. A report citing personal information or abuse hides it until reviewed, because minors may be identifiable. | If teachers can hide reviews, the reviews are worthless. |
| Fees shown publicly | **Teacher's choice per batch, off by default.** Shown as "from BDT X/month", formatted by the server as a money string (TC-7). **`collection_number` never appears on the hub.** | Price is useful to families, but it is the teacher's commercial decision. |
| Enquiry / lead button | **MVP: a contact method the teacher chooses to publish, with clicks counted on the server. Phase 2: an in-app enquiry that requires sign-in by one-time code and is rate-limited.** | The MVP measures demand with no new write path between users and no SMS spam exposure. |
| Monetisation | **Free in V1. Later, clearly labelled promotion for teachers only. Never pay-to-rank inside review ordering. Never ads.** | Trust is the asset, and we do not charge until there is real usage. |
| Where it lives | **Public web: server-rendered HTML with no JavaScript, EN+BN twins and a sitemap, under the marketing domain. The app reads the same API.** | Search visibility is half the value. In-app only would miss it. |
| Photos and documents | **Not in the MVP.** Phase 2: one profile photo and a few batch photos. Documents (certificates) are never public files. Later they could support an admin-reviewed "verified" badge. | We have no upload infrastructure, and this is where moderation cost grows. |

## 4. Phasing and metrics

**MVP: "Hub Zero", a directory without reviews.** Opt-in profiles for owners and centres, plus per-batch listings showing:
- subjects and class level
- a structured area (district / upazila / thana)
- weekly schedule, in-person or online
- whether the batch is accepting students
- an optional fee
- a short bio and the published contact.

Families can browse by area and subject. Teacher-written text has a report link and admin takedown. There are no reviews, no uploads and no student data of any kind.

**Phase 2**, only if the MVP passes the gate below:
- verified-guardian structured ratings with the safeguards in §3
- teacher replies and the report queue
- pre-moderated free text
- photos
- in-app enquiry.

**Later:** credential verification badges, labelled promotion, centre-level aggregate scores.

**Metrics, measured at day 90 of the MVP:**
- **Supply:** at least 25% of active owners (at least one active batch) publish a listing, and at least 70% of published listings are complete.
- **Demand:** at least 500 search sessions a month on hub pages. At least 20% of published listings get one or more contact clicks.
- **Value:** at least 15% of publishing teachers answer yes to a one-tap prompt asking whether they got a student from the hub.
- **Guardrails** (any breach stops rollout):
  - zero incidents of child data appearing on a public page
  - teachers who publish keep using the app at least as well as those who don't
  - account deletions do not rise
  - the hub adds at most USD 10 a month in cost.

**Kill / continue:**
- **Continue to Phase 2** if opt-in is at least 20% **and** contact rate is at least 20%.
- **Freeze** if opt-in is below 10% **or** there are fewer than 150 search sessions a month. Listings stay up and we do not build reviews.
- **Pull reviews** in Phase 2 if more than 5% of reviews are reported in a quarter, or if teachers leave noticeably after receiving low ratings.

## 5. What you must decide explicitly

1. **Amend D-5 (TC-13).** Proposed: "NEVER expose anything a student or guardian writes to any teacher, **except a hub review its guardian author explicitly submits for publication, shown without the author's identity.**" Add a new NEVER: no student-lens account writes public content.
2. **Amend D-6 (TC-14).** Proposed: an admin may additionally see hub listings, submitted and reported review text, a "verified enrolment" flag and tenure. The admin never sees the reviewer's name, phone number, child, marks or fees, and enforcement acts on an opaque account reference.
3. **Confirm no auto-listing**, including for existing users, and confirm per-teacher consent inside centres.
4. **Accept the positioning change**, which brings these updates:
   - the "Your own batches stay entirely yours" copy
   - a Data Safety form update
   - a privacy-policy update
   - the Families declaration for user-generated content.

   All of these are release-blocking under RC-4/RC-5.
5. **Approve a deliberate increase in `PUBLIC_ROUTES`**, and fund a local legal review of the review policy before any free text goes live.
6. **Confirm the product stays free, with no ads**, and that future promotion never affects review ordering.

My recommendation is to approve items 3–6 now and ship Hub Zero. Decide items 1–2 only when Phase 2 passes its gate, so we do not change a privacy rule before we have evidence that reviews are worth it.
