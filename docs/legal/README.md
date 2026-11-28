# Legal documents

`PRIVACY.md` is the privacy policy the Play Store listing links to.

## The policy is generated from the schema, not written beside it

**This heading is now true.** It was written before any generator
existed: the text underneath was hand-authored *against* the schema and
verified by a five-row table of manual checks — careful work, and not
what the heading claimed. `scripts/generate_privacy_policy.py` is what
makes the sentence a fact.

`team.md` requires the text to follow each table's written disposition
rather than being authored independently, because *a privacy policy that
contradicts the implementation is worse than a vague one*.

### How it works

The generator writes **between markers** in `PRIVACY.md`:

```
<!-- BEGIN GENERATED: governance manifest -->
<!-- END GENERATED: governance manifest -->
```

Everything outside them is human prose and stays editable — the contact
address, the reasoning a parent reads, the plain-language summary.
Inside them is what can silently stop matching the code: which data is
deleted, which is kept, and for how long.

```
python3 -m scripts.generate_privacy_policy          # regenerate
python3 -m scripts.generate_privacy_policy --check  # the gate's form
```

`make check` compares the committed region against a fresh render and
**fails on drift**, the same shape as the OpenAPI schema-diff gate and
for the same reason. **Regeneration is the only sanctioned fix.**
Hand-editing the file to turn a red check green inverts the control into
a rubber stamp, and it looks exactly like fixing the problem.

The compared region ends with a digest over the whole manifest —
disposition, retention class **and basis** for every table. Without it a
changed `basis` would alter nothing on the page and pass the gate, which
is how the first version of this generator behaved, on precisely the
field that matters most: the generator publishes the manifest's stated
reasoning, so a basis that disagrees with its own disposition produces a
policy that is mechanically consistent and substantively wrong.

### What this does NOT cover

Nothing mechanically prevents a factual claim being written in the prose
**outside** the markers, where the comparison does not reach. The rival
hand-written table that used to sit in this file has been removed to
shrink that surface, and the `PRIVACY.md` retention table with it — but
the obligation remains partly manual and is recorded as such rather than
rounded up.

These claims are outside the generated region and were checked by hand:

| Claim | Verified against |
|---|---|
| One-time code expires in 5 minutes | `CODE_LIFETIME` in `app/auth/otp.py` |
| Session tokens last 30 days | `REFRESH_TOKEN_LIFETIME` in `app/auth/tokens.py` |
| Codes and tokens stored as hashes | `app/auth/hashing.py` |
| Internet is the only granted permission | the merged release manifest |
| No device or advertising identifiers | the release DEX scan |
| A review needs an accepted guardian link, 30 days in the class, 4 attended sessions and, after leaving, no more than 180 days | `app/reviews/eligibility.py` |
| Nobody who runs or teaches a class reviews it | `app/reviews/eligibility.py` [T3-c, T3-f] |
| Review words up to 1,000 characters; a phone number or web address is refused | `MAX_BODY` in `app/reviews/authoring.py`, `app/reviews/content.py` |
| Nothing public below three published reviews | `REVIEW_THRESHOLD` in `migrations/versions/0045_hub_reviews.py` |
| Month and year only; a tenure label, never a name | `month_label` in `app/hub/public/ratings.py`, the labels in `app/hub/public/messages.py` |
| Published weekly; an edit within 30 days goes back to be checked | `app/reviews/publication.py`, `EDIT_WINDOW` in `app/reviews/authoring.py` |
| A teacher reads reviews only as the public does | `app/reviews/owner.py`, `tests/gates/test_teacher_reviews_read_views.py` |
| A report by anyone who runs or teaches the class holds nothing; a child-safety or personal-information report from anyone else takes a review down | `runs_batch_sql` in `app/reviews/eligibility.py`, shared by `app/moderation/reviews.py` and eligibility [F10, I-2] |
| Deleting a review removes its reply and every report on either | `app/reviews/forget.py` |

## NOT YET TRUE: account deletion

**The policy describes two deletion paths. Neither is implemented.**

`project.md` makes both release-blocking:

> ALWAYS provide both account-deletion paths — in-app, and an
> externally accessible route usable without reinstalling the app —
> as release-blocking V1 deliverables [TC-19] [RC-4] [RC-5]

Current state:

- No deletion endpoint exists in `app/api/`
- No Settings screen exists in the Android app
- No externally reachable deletion page exists

This is recorded here rather than softened in the policy, because the
policy has to describe what the finished product does and the gap is
a build obligation, not a drafting one.

**Do not submit the Data Safety form or publish to a public track
until both paths exist and are tested.** Play requires a working
deletion route for any app that collects personal data, and a policy
promising one that does not answer is worse than no policy — it is a
false statement to a regulator about children's data.

Internal testing is fine meanwhile; the policy is accurate about
everything else.

## The disposition decided for this policy

**The table that used to sit here has been removed, and its removal is
the point.** It was a second per-table disposition list, maintained by
hand beside `app/governance/dispositions.py` — and the two had already
disagreed: this file said `account` was "hard delete" while the manifest
said `ANONYMIZE_IN_PLACE` and `PRIVACY.md` promised the phone number was
"deleted permanently". Three documents, three answers, nothing failing.
A rival source is how that happens, so there is now one source.

**`app/governance/dispositions.py` is it.** Every disposition, retention
class and stated reason lives there, the policy is generated from it,
and the drift gate keeps the two in step.

Two decisions worth recording here, because they are history rather than
current state and the manifest carries only the latter:

- The open question `team.md` flagged — what happens to a teacher's
  record of a child who deletes their account — was first decided on
  2026-10-20 as **anonymise in place**.
- On **2026-10-25** the human reversed the `account` entry to **hard
  delete**, choosing the published policy's promise over the manifest.
  The hazard the old basis named — a released number being reused by a
  different person while enrollments still referenced the account — is
  real and is closed by the constraint rather than by the disposition:
  migration `0007` makes the three `account` references `SET NULL`, so a
  new account taking the same number inherits nothing from the old one.

**The deletion implementation must match the manifest**, and
`project.md` already requires a test per path asserting exactly that.

## Data Safety: what the public hub changes

**Review the Play Data Safety form against this list before the release
that ships the public hub (H2).** The form is filled in the Play Console,
not from this repository, so nothing here checks it; this section is the
record of what changed. `PRIVACY.md`'s generated region already carries
the hub tables (`owner_listing`, `batch_listing`, `hub_report`,
`hub_feedback`, `hub_moderation_event`, `cdn_invalidation`) and was
current when this section was written
(`python3 -m scripts.generate_privacy_policy --check`).

**1. New: public display of what a teacher or centre chooses to
publish.** Anyone, signed in or not, can read a published listing on the
site at `/hub/en` and `/hub/bn`, and search engines index it. Nothing is
public before the owner's own `publish`, and a listing can be
unpublished at any time. What a published listing shows:

| Shown publicly | Whose | Condition |
|---|---|---|
| Public name, headline, biography, qualifications, how they teach | the teacher's or centre's | always, once published |
| Area: district and upazila | the teacher's or centre's | when set |
| Street address | a centre's only; never a solo tutor's | when set |
| **Contact phone number** | the teacher's or centre's | **opt-in**: only a number entered for the listing, which may differ from the account's |
| A centre teacher's name | that teacher's | only with that teacher's own recorded consent; otherwise "Centre faculty" |
| Class listings: public title, description, syllabus, subjects, class levels, curriculum, how it is taught, admissions status | the teacher's or centre's | per class, once that class is published |
| Weekly times and the monthly fee | the teacher's or centre's | each only when the owner chose to show it |
| Seat counts: seats in the class, seats free, and the day they last changed (`0048`) | the teacher's or centre's: **typed by them, never counted from enrollments** | only when the owner chose to show them; both numbers required |
| "Runs classes" badge | derived from the owner's own activity | a yes/no, recomputed daily; it names no student |

**No student or guardian data is shown on any public page**: no name,
photo, marks, attendance, enrollment or anything a student or guardian
wrote (`project.md`, Forbidden) — with one exception, added by H4: a
review a guardian chose to submit for publication, shown without a name
(item 5). The pages are rendered only from the `hub_public_*` views and
the fixed list of area names, read through a role that can see nothing
else. The people whose data becomes public are teachers and centre
staff, all adults, by their own choice.

For the form: the data types concerned (name, phone number, address,
and the listing text as user-generated content) are already collected
for teachers. What changes is that they are now **displayed publicly at
the user's request**. Whether Play counts that as "shared" is a judgement
for whoever submits the form, against Play's current definitions; it is
not decided here.

**2. New: reports.** A signed-in reader -- which can be a student or a
guardian -- can report a hub page. Stored: which page, a reason from a
fixed list, an optional note of up to 500 characters, the reporting
account and the time (`hub_report`). It is seen only by the platform
administrators who moderate the hub, shown with an opaque author
reference and never a name or phone number; it is never shown to the
teacher reported. It is deleted with the reporter's account. Form
category: user-generated content, collected, not shared; purpose: app
functionality (moderation).

**3. New: the demand question.** A teacher with a published listing is
asked, 60 and 90 days after first publishing, whether the hub brought
them a student. Stored: the answer and which account answered
(`hub_feedback`). It is used to decide whether the hub continues.
Deleted with a solo teacher's account; a centre's answers stay with the
centre and lose the answering manager. Form category: user-generated
content or app interactions (whichever the form's wording fits), from
teachers only; purpose: analytics.

**4. New: listing photos [H3].** A teacher or centre can add photos to
their public listing. **Review the Play Data Safety form against this
list before the release that ships them.**

- **Who uploads.** Teachers and centre managers only (the owner of a
  listing). A student or guardian cannot upload a photo, and no student
  photo is ever published (`project.md`, Forbidden).
- **When it is public.** Only after a platform administrator has approved
  it. Until then a photo sits in a private bucket, visible to the uploader
  and the moderators alone. A child-safety or personal-information report
  on an approved photo takes it down at once, before any moderator acts.
- **What is stored.** The image is decoded and re-encoded as WebP at three
  sizes by a sandboxed function, so **EXIF and location data are removed**
  and no original byte is published; the original is deleted within a day.
  Alongside it: alt text in English and Bangla, written by the owner.
- **How long.** Until the owner withdraws or deletes it, or deletes their
  account. A solo teacher's account deletion removes the photos and queues
  the deletion of every image file; a centre's photos belong to the centre
  and stay (`PRIVACY.md`, generated from `listing_media`).
- **Form category:** photos, user-generated content, collected and shown
  publicly at the user's request; purpose: app functionality. No new
  Android permission: the app uses the system photo picker, which grants
  access only to the photo the person picks. No new SDK, no new
  identifier.

**5. New: guardian reviews [H4].** A guardian can rate and review a
class their child attends. **Review the Play Data Safety form against
this list before the release that turns reviews on** (the switch, not the
release that ships the code: reviews ship off; `infra/README.md`,
"Switching reviews on").

- **Who writes.** Verified guardians only: an accepted guardian link to a
  student in that class, at least 30 days in it and 4 attended sessions,
  and, after the child leaves, for no more than 180 days. Students cannot
  write reviews in V1, and nobody who runs or teaches the class can.
- **What is stored.** For a review (`review`): a star rating (1–5),
  optional words of up to 1,000 characters (a phone number or web address
  is refused), the class, the author's account and role, the evidence
  enrollment, a tenure bucket frozen at first submit, the moderation
  state and any rejection code, the administrator who last decided it,
  and its submission, edit, approval and decision times (never shown),
  and the month it was published (shown). For a teacher's reply
  (`review_reply`), one per review: up to 1,000 characters, the account
  that wrote it, the moderation state and any rejection code, the
  administrator who last decided it, its creation, edit and decision
  times (never shown), and the month it was published (shown).
- **When it is public.** Only after a platform administrator has approved
  it, at the next weekly publication, and only once the class has at
  least **three** published reviews; below that nothing shows, not even
  a count. It is shown with a tenure label ("Verified guardian · enrolled
  6–12 months") and the month and year, **never a name**, an initial,
  the child's school class or a day. The administrator sees it under an
  opaque author reference; the teacher sees only what the public sees.
- **How long.** Until the author deletes it, **which they can do at any
  time**; deletion is total (the review, its reply and every report on
  either). **It is deleted with the author's account**, and the reviews
  of a solo teacher's classes are deleted with that teacher's account and
  listing (`PRIVACY.md`, generated from `review` and `review_reply`).
- **Form category:** user-generated content (and the rating, if the form
  asks separately), collected from guardians and **shown publicly after
  moderation at the user's request**; purpose: app functionality. Whether
  Play counts public display as "shared" is, as in item 1, a judgement
  for whoever submits the form. No new SDK, no new Android permission, no
  new identifier.

**6. New: join requests [H5].** A signed-in parent or guardian can ask a
teacher or centre with a public listing to take their child into a class
("Ask to join"). **Review the Play Data Safety form against this list
before the release that turns join requests on** (the switch, not the
release that ships the code: join requests ship off; `infra/README.md`,
"Switching join requests on").

- **Who sends.** A signed-in account that declares, on each request, that
  it is the child's parent or guardian aged 18 or older; a request
  without that declaration is refused. Nobody who runs the listing can
  send one to it. A teacher or centre chooses whether to accept requests
  at all.
- **What is collected.** For a request (`listing_enquiry`): the student's
  name (up to 80 characters) as the guardian typed it, their school
  class, chosen from a fixed list, an optional message of up to 300
  characters (a phone number or web address in the name or the message
  is refused), the listed class it is about if any, the sending account,
  whether the guardian chose to share their contact, its status, the
  owner's answer (one of three fixed outcomes) and the times it was sent
  and answered. **The phone number or email
  address is not collected anew**: it is the one already on the account,
  read live and only on a request where the guardian chose to share it,
  never copied into the request.
- **Shared with whom.** Only with the one teacher or centre the guardian
  chose, at the guardian's direction: a solo teacher, or each of a
  centre's managers and nobody else who works there. The contact goes
  with it only if the guardian chose to share it on that request: the
  phone number, or the email address when the account has no phone
  number. What comes back to the guardian is a fixed answer, never words
  the teacher writes.
- **Never.** Shown on any public page, or to platform administrators:
  no administrator route reads join requests, and the role the public
  pages are rendered through cannot read the table.
- **Deleted.** When the guardian withdraws it, **which they can do at any
  time**, answered or not and with the switch off too; withdrawal is
  total (the request and every inbox item about it, the teacher's and the
  guardian's). **With the guardian's account**, and with a solo
  teacher's. And **90 days after it was sent** in any case, by the
  retention purge, which the switch never stops (`PRIVACY.md`, generated
  from `listing_enquiry`, and its "Join requests" section).
- **Form category:** name (the student's, as typed) and user-generated
  content (the message), collected from guardians and **shared with the
  one teacher or centre they choose, at their request**; phone number or
  email address, already declared as collected, now also **shared with
  that teacher or centre only when the user chooses to, per request**.
  Purpose: app functionality. Whether Play counts a transfer the user
  initiates, to a recipient the user chooses, as "shared" is a judgement
  for whoever submits the form, against Play's current definitions; it
  is not decided here. No new SDK, no new Android permission, no new
  identifier.

**7. New: interest in a class [0049].** A signed-in parent or guardian
can tell the teacher of a listed class, even a full one, that they are
interested, so the teacher can call when a place opens. Stored as a
second kind of join request (`listing_enquiry.kind = 'interest'`), on the
same switch, the same owner opt-in, the same 90-day purge and the same
deletion paths. **Review the Data Safety form against this before the
release that turns join requests on**, as for item 6.

- **Who shares.** A signed-in account with a phone number that declares,
  on each interest, that it is a parent or guardian aged 18 or older.
- **What is collected.** The class, the sharing account, its status and
  when it was shared and closed. **Nothing typed**: no student name, no
  class level, no message.
- **Shared with whom.** The phone number already on the account, **always**
  (an interest is the choice to share it), with the one teacher or the
  managers of the one centre that runs the class, read live and never
  copied. **Form category:** phone number, already declared as
  collected, now also shared with the teacher or centre the user
  chooses, at their request; purpose: app functionality. The same
  judgement on Play's "shared" applies as in item 6.
- **Never** public, never shown to platform administrators, and no new
  SDK, permission or identifier.

**8. New: page-view counts [0050].** Each public owner and batch page
carries a 1x1 image (`/hub/v/{o|b}/{id}.gif`, answered `no-store` so the
edge cache passes it through), and each load adds one to
`hub_page_view` for that page and Bangladesh day. **Nothing about the
reader is stored**: no address, cookie, user agent, referrer or account;
the table's four columns are the page kind, the page id, the day and the
count, asserted by `tests/hub/test_page_views.py`. Only the owner reads
the counts (`GET /v1/hub/listing/views`, the teacher lens), as 7- and
30-day totals; no public page or search order uses them. Kept 12 months.
The load counts against the hub's existing per-network minute read
limit, a short-lived counter already in place for every hub page. The
web app's hub pages are not the Android app, so the **app's** Data
Safety answers are unchanged: no new SDK, permission or identifier, and
nothing collected from app users. Whoever submits the form confirms that
reading against Play's current definitions.

**Families target-audience declaration.** The app's audience includes
children, so the declaration must say the app carries **user-generated
content** (teachers' listing text and photos, guardians' reviews and
teachers' replies to them) that is **pre-moderated before it is public**,
that no student uploads a photo or writes a review (photos come from
teachers and centres, reviews from guardians), and that **every public
listing, photo, review and reply can be reported from inside the app** by
a signed-in user, with a child-safety or personal-information report
taking a photo, review or reply down at once (for a review or reply,
unless someone who runs or teaches the class filed it). Once join
requests are switched on, the declaration also says that **a join
request comes only from an account declaring, on that request, that it
is a parent or guardian aged 18 or older**, that it goes only to the one
teacher or centre chosen and is never public (so it is not moderated:
nobody but that recipient reads it), and that **no message reaches a
child account from a teacher through this feature**: the only reply is a
fixed answer, delivered to the guardian who asked. Whoever submits the
declaration confirms this against Play's current wording; it is recorded
here because nothing in the repository checks it.

### The D8 legal review of the review policy

Hub spec D8: a local legal review of the review policy happens **before
free-text reviews go live**. Turning the switch on is going live, so the
review is recorded here and the runbook checks for it. **Not yet
recorded.**

| Date | Reviewer | What was reviewed | Outcome, and any change it requires |
|---|---|---|---|
| — | — | — | — |

**Not changed by the hub:** no new SDK, no new Android permission, no
device or advertising identifier, no cookie on the public pages, and no
script on them at all (their CSP is `default-src 'none'`). Public page
reads are counted per network for the rate limit in the same counter
table the sign-in ceilings already use, keyed on an address prefix, not
an account.

## Hosting the link

Play needs a public URL. The raw GitHub link works:

```
https://raw.githubusercontent.com/arshomashohag/shikkhok-plus/main/docs/legal/PRIVACY.md
```

Raw Markdown renders as plain text, which Play accepts but reads
poorly on a phone. Better options, in order of effort:

1. **GitHub Pages** — enable it for this repository and the file
   renders as a styled page at a stable URL.
2. The repository's own file view, which renders Markdown but shows
   GitHub's chrome around it.

Whichever you choose, the branch must be public and the URL must stay
reachable: Play rechecks it, and a dead privacy-policy link is grounds
for removal.
