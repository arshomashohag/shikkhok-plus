# Public hub H3–H5: controller rulings, deferred minors and human steps

This file is the durable record of every decision taken on the owner's behalf while H3 (photos), H4 (reviews) and H5 (join requests) were built by subagent-driven development. Each ruling is copied verbatim from that unit's execution ledger, in the order it was made, with what it costs if it is wrong. The ledgers themselves were scratch files and have been deleted.

Plans: docs/superpowers/plans/2026-11-18-public-hub-h3.md, 2026-11-19-public-hub-h4.md, 2026-11-20-public-hub-h5.md. Spec: docs/superpowers/specs/2026-11-14-public-hub-design.md.

## H3 (photos)

### Rulings

- Ruling: R1 thumb_url absolute on site origin; web CSP img-src gains bucket endpoint + site origin — editor runs on app host — cost: one more allowed img origin.
- Ruling: R2 HUB_MEDIA_OBJECT_JOB 30-min staleness threshold — a 2-min drain alerting after 48 h would hide stuck deletes — cost: alert noise if drains stall.
- Ruling: R3 Task 3 owns the deploy.yml Lambda update and its test; Task 11 does not duplicate — avoid two writers — cost: none.
- Ruling: R4 Lambda created from a placeholder zip with ignore_changes on code; deploy uploads the real zip after the infrastructure job — the infra apply runs before any build — cost: first deploy needs the code-update step to succeed.
- Ruling: R5 bucket + Lambda in the app's runtime region; AWS_REGION passed to the container — one region for S3 events and the container — cost: none.
- Ruling: width/height INTEGER, not SMALLINT — a decodable 1000x40000 image within the 40M-pixel cap would 500 on complete — cost: none.
- Ruling: guard trigger ties listing_media.batch_id to owner_id's batch (as batch_listing's trigger does) — a cross-owner photo must be impossible, not merely hidden — cost: none.
- Ruling: accept the /m/* viewer function media-path.js (maps only /m/<32hex>/<320|960|1600>.webp -> /public/…, 404 nosniff otherwise) — CloudFront origin path cannot strip /m/ and the object layout is fixed by Task 1's CHECK — cost: one more CloudFront Function (free tier).
- Ruling: media bucket name is account-suffixed like web/site/admin/config buckets — S3 names are global — cost: none (fix round).
- Ruling: drop Content-Type from the /m/* response-headers policy; objects are stored with ContentType image/webp (Lambda put, copy preserves) and a test asserts it in Tasks 3/4 — AWS may refuse Content-Type as a custom header and the object's own type suffices — cost: none.
- Ruling: R6 a JPEG/PNG/WebP that decodes is ACCEPTED even with bytes after its end (Android motion photos, MPO), because the re-encode emits only decoded pixels; the safety property is "no original byte reaches staged/", tested by searching every variant for the appended marker. A file whose magic bytes are not an image (HTML named .jpg, SVG) stays unreadable — refusing motion photos would fail uploads from many Android phones; Review Focus 1's polyglot case becomes "appended HTML never survives" — cost: none (output is re-encoded either way).
- Ruling: R7 (a) accept format "MPO" when JPEG was declared, test with a real MPO; (b) aws_lambda_function_event_invoke_config maximum_retry_attempts = 0, maximum_event_age_in_seconds = 300; cascade resizes from the largest variant (and JPEG draft() for the decode) to cut work; (c) Task 4's complete() treats a row created more than 20 minutes ago (10-min presign + 30 s Lambda + margin) with no result.json as unreadable (rejected, rejection_code 'unreadable', staged/ + quarantine/ deletes enqueued) — the API is the only party that can give the photo a terminal state; a sweeper is unnecessary because complete() is what the client polls — cost: a genuinely slow upload completed after 20 min is refused and must be retried.
- Ruling: R8 media writes on a SUSPENDED owner listing are refused with the existing suspended-listing refusal (H1 makes a suspended listing read-only); enforce at the Task 5 routes (or service) — cost: none.
- Ruling: R9 the plan's "logs and no-ops" applies to presign only; for deletes, a missing bucket raises TransientError and the drain keeps the row (attempts++), so a misconfigured production goes stale and alerts — cost: local dev's media heartbeat is stale (harmless).
- Ruling: R10 `complete` consumes HUB_LISTING_OWNER_DAILY only when it changes state (pending_review or rejected-unreadable); a MEDIA_NOT_UPLOADED answer consumes nothing — clients poll complete every 2 s for up to 60 s, which would burn the 50/day listing allowance — cost: a hostile client can poll complete without limit, bounded by the read-only cost of fetching result.json (keep the global per-IP limits as they are).
- Ruling: R11 an admin UPHOLDING a report on a media target removes the photo in the same transaction (status rejected with the report's reason mapped to a rejection code, deletes of public/staged/archive enqueued, invalidation) — otherwise a non-holding report the admin agrees with leaves the photo public with no admin path to remove it — cost: none.
- Ruling: approval does not invalidate the page (appears within the 10-min TTL) — matches the H2 rule that edits ride the TTL and only takedowns invalidate — cost: up to 10 min delay.
- Ruling: R12 the per-photo report link kind=media is accepted by the server but refused as "not valid" by web HubReport.tsx and Android HubReportViewModel; Task 9 adds `media` to the web report screen and Task 10 to Android (with strings and the route test) — client work belongs to the client tasks — cost: photo report links show "not valid" until Tasks 9/10 land (same branch, never deployed in between).
- Ruling: R13 close the deletion race now: after taking the owner lock, upload init (and complete, alt edit, reorder) and the admin approve/restore re-check that a solo owner still has its account (owner.account_id IS NOT NULL for kind='teacher'); if not, refuse with the existing not-found/lens refusal and write nothing — otherwise a photo inserted or approved under a just-deleted solo owner is orphaned forever — cost: none.
- Ruling: R14 Task 10's "OkHttp multipart POST" is done with the project's Ktor client (OkHttp engine) via submitFormWithBinaryData on a separate, unauthenticated HttpClient (no bearer/auth plugin, no default headers), so the brief's MockEngine route test works and no dependency is added — the brief names OkHttp because it is the engine; adding raw OkHttp calls would bypass the project's single HTTP stack — cost: none.
- Ruling: R15 Android shows placeholder + alt + status pill instead of thumbnails (no image loader in the app; adding one needs an SDK admission note and is not in the plan) — the server/page shows the real photo; the editor's job is managing them — cost: owner cannot visually tell photos apart on Android (alt text distinguishes them).
- Ruling: R16 waiting_review = the complete poll, done = complete 200 — matches web's phases — cost: none.
- Ruling: R17 coverage-floor.txt raised to the merged figure in the H3 final fix wave (after all Android changes), not mid-unit — the ratchet arms on the merged figure — cost: none.
- Ruling: R18 Task 11's smoke uses a well-formed but absent key `/m/00000000000000000000000000000000/320.webp` (passes media-path.js, reaches the bucket via OAC → 403/404 with nosniff) AND a malformed `/m/does-not-exist/320.webp` (function's own 404 nosniff) — the brief's malformed path alone never reaches the bucket, so it would not prove the routing it claims — cost: none.
- Ruling: R19 a real S3 acceptance check of the Android multipart form (Task 10 ⚠️1) is a HUMAN STEP after deploy (one upload from a debug build to staging); smoke cannot upload without a teacher session — cost: a parser mismatch surfaces at the device check, not in CI.
- Ruling: I1 is fixed by a time gate (no approval / not queued until created_at + 20 min) with the Lambda max event age bounded so expiry + age <= the gate — deterministic and small — cost if wrong: a re-post landing after the gate could publish unreviewed content; mitigated by bounding event age.
- Ruling: I3 is fixed server-side in init_upload (withdraw own in-flight rows older than UPLOAD_WINDOW) rather than client refetch — the reviewer is right that a client fix only changes the display — cost if wrong: a very slow genuine upload past 20 min gets withdrawn; same R7c window already treats it as unreadable.
- Ruling: fix wave includes the reviewer's promoted minors and new minors; remaining deferred minors left per final-review.md reasons — cost if wrong: small polish debt visible in final-review.md.
- Ruling: I1 residual is closed now by a targeted completion of the same finding, not left for the human — unreviewed content on a children's-app public surface is load-bearing and the fix is small: record each staged variant's ETag at `complete` and approve only with CopySourceIfMatch on each; a mismatch refuses approval and withdraws the photo as unreadable. Time gate stays. Also fix minor (a) (project.md: a comment's claim must be true). — cost if wrong: one extra round of review time; deviates from "no second fix wave" by design.
- Ruling: minor (b) parked — same class as M6 left by final review; rare, self-resolving via Postgres deadlock detection with a retryable error — cost if wrong: an occasional failed reorder the user retries.
- Ruling: minor (c) parked — brief allowed it; server remains authoritative — cost if wrong: display drift if the quota rule changes.
- Ruling: freeze at `complete` — copy staged→archive with CopySourceIfMatch on the just-read ETags inside complete; admin preview and approval read archive/ only; approval copies archive→public; staged/ is never read after complete. This makes the reviewed bytes and published bytes the same object by construction — cost if wrong: complete becomes slower (3 S3 copies) and an archive copy exists for photos later rejected (deleted via outbox as today).
- Ruling: the three new minors ride along in this round where the freeze touches them (concurrent-approval guard on archive deletion; staged/ cleanup after complete) — cost: small.
- Ruling: fix round 4 (small): spend before the copy; correct the stale prose (project.md: a comment's claim must be true); narrow the media/API role's public/* copy-source condition to archive/* so I1 also holds in IAM — cost if wrong: an IAM mismatch would make approval fail closed on staging (HUMAN STEP staging approval already listed).

### Deferred minors

- Task 1: minor (deferred): PRIVACY table says media_object_task "Removed anyway after 7 days" — add "once done".
- Task 1: minor (deferred): test_migration_0043 downgrade assertion uses broad Exception.
- Task 2: minor (deferred): /m/* Cache-Control override may make browsers cache a 404 for a year (verify with curl -I on first apply, or set Cache-Control on the object instead).
- Task 2: minor (deferred): cost comment arithmetic (1.5 GB) does not match its stated inputs × 3 copies.
- Task 2: minor (deferred): CSP test fixture uses an unsuffixed bucket name.
- Task 3: minor (deferred): duplicate-delivery NoSuchKey branch dead (role lacks ListBucket -> 403); foreign-bucket record not explicitly ignored; bomb coverage PNG-only (add JPEG SOF / VP8X WebP); lambda-test installs Pillow into the backend venv; Lambda SBOM not asserted non-empty and cut at Android release SHA.
- Task 4: minor (deferred): drain holds one transaction across all S3 calls (commit per row); permanently failing prefix never alerted (attempts threshold -> error log); complete() ignores alt on repeat (docstring); boto3 gate regex misses `import os, boto3` (use AST); quarantine delete by listing not exact key; storage.py 643 lines (split helpers).
- Task 5: minor (deferred): consume_hub_listing_in_transaction public & duplicates _consume; no 401/full-403 parametrised route test; no test of complete at the listing ceiling (an at-ceiling owner cannot record unreadable); _begin_write spends before 404/400 (consistent with H1); no RED capture for route tests.
- Task 6: minor (deferred): expired staged/ on first approval raises TransientError forever; route-level uphold test missing (misnamed dismiss test); no restore-copy-failure test or overlapping-session race test; Queue.test picks the default reject code, comment asserts nothing, no owner_id-absent assertion; report rows on approved photos show no picture; max(taken) without default.
- Task 7: minor (deferred): `sizes` underestimates the 2-column slot at 600–776 px; hub_image 500s on width/height < 1 (add > 0 to the approved CHECK); probe test leaves a dependency override; Starlette deprecation warning (pre-existing); JSON-LD image uses src not strictly 960.
- Task 10: minor (deferred): unused `job` field / retry() has no in-flight guard
- Task 10: minor (deferred): picker.launch ActivityNotFoundException uncaught; lost result leaves Picking; process death drops alt texts
- Task 10: minor (deferred): orphaned awaiting_upload rows not reflected in count (refresh after fresh-ticket retry) — same class as W2/A1
- Task 10: minor (deferred): BucketClient KDoc "made on first upload" false
- Task 10: minor (deferred): slow-poll banner concatenates strings instead of a two-arg template
- Task 10: minor (deferred): failed delete leaves dialog open over banner (same as W3)
- Task 10: minor (deferred): read-only route test asserts only Add absent; suspended flag not driven from entry rows
- Task 10: minor (deferred): bucketForm hand-builds PartData.BinaryItem with ByteReadPacket (deprecated in newer Ktor)
- Task 11: minor (deferred) — smoke.py docstring line 107 chars; new test swaps smoke._get by hand instead of monkeypatch; no case for well-formed key wrongly 404 / malformed wrongly 403 (smoke accepts either for both); infra/README "AWS keeps >=10 unreserved concurrency" unverified against the account.

### Human steps recorded

- HUMAN STEP (H3): re-apply infra/bootstrap before the first H3 deploy (media role, Lambda function/role/logs, deploy-role UpdateFunctionCode/GetFunctionConfiguration). Check `aws lambda get-account-settings` for unreserved concurrency >= 12 before apply (reserved concurrency 2).
- Fix wave: DONE_WITH_CONCERNS (commits a1cbe2e..68da411 excluding 967615b plan doc); make check rc=0; Android coverage floor raised to 90.85% (R17). Concerns: no admin list for approved-unlisted photos (reject by id + owner delete suffice); I1 margin depends on S3 event + 300 s Lambda max event age (pinned by gate test); s3:x-amz-copy-source condition needs one staging approval to confirm (HUMAN STEP); Delete shown in suspended galleries for I2.
- HUMAN STEP: one staging takedown to confirm exact /m/ invalidations take effect through the viewer function's /m/ → public/ rewrite.
- Fix round 3 (freeze at complete): DONE_WITH_CONCERNS commit 417340a; make check rc=0. Concerns: pinned copy untested on real S3 (fails closed — every upload rejected if wrong; HUMAN STEP staging upload); complete holds owner lock across 3 S3 copies; one-day staged/ cleanup backstop is a judgement call. Re-review dispatched (opus).
- Fix round 4: DONE_WITH_CONCERNS commits 5c4ee9f, 7f89635, 6ec06ae; make check rc=0; tf fmt+validate pass. Concerns: IAM conditions + CopySourceIfMatch unproven on real AWS (fail closed; HUMAN STEP one staging upload + approval); DB-down during cleanup leaves archive unrecorded until next sweep/withdraw/deletion. Re-review dispatched (sonnet).

## H4 (reviews)

### Rulings

- Ruling: F1 SSM path /shikkhokplus/${var.name_prefix}/hub-reviews (no var.environment in infra/modules/app) — cost if wrong: path rename in T1 only.
- Ruling: F2 add "hub-reviews": "off" to _RECORD_PARAMS, deploy test in test_deploy_workflow.py, deploy/README env row — cost: deploy gate red until fixed.
- Ruling: F3 reviews_on fixture defined once in root tests/conftest.py — cost: fixture duplication.
- Ruling: F4 each task publishes the message keys it raises (T5 hub.review.not_found; T7 hub.review.already_decided, hub.review.code_invalid); literal message_key="…" form — cost: key-gate failures.
- Ruling: F5 add non-committing consume_hub_review_in_transaction; replies use consume_hub_listing_in_transaction — cost: a partial write on failure.
- Ruling: F6 put_reply calls refuse_suspended on the caller's listing first; source gate forbids only the review base table — cost: suspended owner replying.
- Ruling: F8 delete_reply deletes hub_report rows targeting the reply (deletion total) — cost: orphan report rows.
- Ruling: F9 upheld report removes target whatever its status; dismissed report restores only held — cost: an edited item escaping removal.
- Ruling: F10 (spec §6 "never hide") a report by the owner or its managers does not hold the review; goes to the 24 h queue; test_owner_report_does_not_hold_review — cost: owners could suppress reviews.
- Ruling: F11 hold time / waited_hours from latest review_held/reply_held event at — cost: wrong queue order.
- Ruling: F12 canary seeds 3 reviews on the solo batch and 2 on the centre batch, runs under reviews_on — cost: review pages unrendered by the canary.
- Ruling: F13 server sends average_display ("4.3") in OwnerBatchRatingWire; clients never format average_tenths — cost: client-side business formatting.
- Ruling: F14 StringConstraints(strip_whitespace=True, …) so blank reply is a standard validation error — cost: inconsistent limits.
- Ruling: F15 rename open_only → include_open — cost: inverted meaning bug.
- Ruling: F16 create missing scaffolding (tests/reviews/support.py helpers, test_hub_query_keys_agree.py as Create, InboxRouteTest; routes hub/reviews and hub/reviews/{batchId}) — cost: implementer confusion.
- Ruling: F17 add written_by_account_id, decided_by_account_id to REVIEW_FORBIDDEN_FIELDS — cost: an identifying field leaking.
- Ruling: F18 (spec over plan) review count exposed publicly only at >=3; record hub_public_rating as a deviation from the spec's reader-view list — cost: one less signal on small batches; protects attribution.
- Ruling: F19 owner preview has no review section; card ratings only, from the views, only when the switch is on — cost: owner sees less in preview.
- Ruling: F20 include eligible_from whenever tenure is unmet — cost: missing date in some refusals.
- Ruling: F21 queue-absence check moves to T7 as test_deleted_review_leaves_every_queue; T4 asserts rows gone — cost: none.
- Ruling: F22 review.id uuid4 via gen_random_uuid() default; share private _opaque_ref(prefix, id) with requester_ref — cost: guessable ids.
- Ruling: F23 T7 starts only after the H3 fix wave is committed; T7 brief based on that commit — cost: merge conflicts.
- Ruling: plan writer's owner questions — reply pre-moderation ON (project.md ALWAYS pre-moderate hub reviews; replies are published content); star ratings stay off with the whole switch until legal review (D8); "now eligible" and reply notifications cut from H4; Bangla review copy is a HUMAN STEP — cost if wrong: owner can relax any of these later; all reversible.
- Ruling: T2-a Tasks 5 and 9 treat "no hub_public_rating row" as below threshold; OwnerBatchRating has no review_count below 3 (preflight row 11 superseded) — cost if wrong: a crash or a leaked 1–2 count.
- Ruling: T2-b Task 5 teacher-side code reads only the two public views, enforced by F6's source gate forbidding the `review` base table in teacher modules — cost if wrong: a teacher-facing query bypassing the threshold.
- Ruling: T2-c every query on hub_public_review orders by published_month DESC, id, with a test (Tasks 5 and 9) — submission order must not leak — cost if wrong: attribution by order.
- Ruling: T2-d Task 13 must rewrite PRIVACY.md hand prose (lines ~100–105) to cover reviews before the switch is turned on — cost if wrong: a false privacy policy.
- Ruling: T3-a sibling seat choice ranks a seat still within the recency window above a closed one before earliest join date — otherwise a closed sibling hides a newer not-yet-eligible seat — cost if wrong: a guardian told "closed" when a later date would open.
- Ruling: T3-b eligible_from only on not_yet refusals, never on window-closed ones (F20 read as "tenure unmet and still reachable") — a closed window has no future date — cost if wrong: a missing date on a refusal.
- Ruling: T3-c nobody who runs the batch may review it — exclude the owner's account, accepted unrevoked managers (the managing_accounts set F10 uses) and any class teacher assigned to the batch, via NOT EXISTS in the seat stage; test-first test_owner_or_manager_of_the_batch_is_not_member plus a class-teacher case — spec §6 is silent, but a self-review defeats the feature's purpose — cost if wrong: a teacher who is also a genuine guardian in a batch they teach cannot review it.
- Ruling: T3-d fix the sibling minor in the same round: among not_yet siblings pick the one with the earliest known eligible_from — cost: none.
- Ruling: T3-e Task 4 accepts a first review only when standing == eligible (lens admits not_yet/closed/author_only); Task 6 never puts the lens's enrollment_id in any response — cost if wrong: an ineligible write or a joinable field leaking.
- Ruling: T3-f class-teacher exclusion requires a LIVE membership (revoked/declined teachers may review) and does not exclude examiners — the gap was control over seats, joined_on and attendance, which examiners and former staff do not hold — cost if wrong: an examiner reviews a batch they mark.
- Ruling: T3-g among not_yet siblings, a seat lacking only tenure ranks above one lacking tenure and attendance (whose F20 date is not a real eligibility day) — cost: none material.
- Ruling: T4-a editing a rejected/removed review inside 30 days returns it to pending, as the brief says — pre-moderation re-screens it and spec §6 gives authors the edit window without a status carve-out — cost if wrong: a moderator re-reads a resubmitted removed review
- Ruling: T4-b Task 6 never serialises MyReviewState.assessment or MyReview.submitted_at (carry to T6 dispatch)
- Ruling: T4-c Task 7 settle_report locks review/reply rows before hub_report rows, matching delete's order (carry to T7 dispatch)
- Ruling: T5-a delete_reply must work whatever the review's visibility (held, below threshold, hidden/suspended listing) — a person's right to remove their own words is never gated by publication, same principle as "the switch never gates a deletion"; ownership may be resolved by ONE narrow statement reading only review.batch_id (no content columns), confined to a single named helper the gate test allowlists by name; the response stays 204 for absent/foreign so nothing leaks — cost if wrong: one allowlisted base-table read in teacher code
- Ruling: T5-b a reply insert that loses to a concurrent review delete (FK violation) answers REVIEW_NOT_FOUND, not a 500 — cost: none
- Ruling: T5-c put_reply's own switch check and the 400 REQUEST_INVALID backstop follow Task 4 (M-6, M-2 deferred)
- Ruling: T5-d Task 7's reply-report decision locks the reply row before its hub_report rows (with T4-c: content first, then reports) — carry to T7
- Ruling: T5-e Task 10's account deletion takes the review row lock FOR UPDATE before calling forget (forget itself takes none) so it cannot deadlock with delete_reply — carry to T10
- Ruling: T6-a F13's field is named average_label, not average_display — the money gate treats every *_display field as a money display and is documented never-allowlistable; weakening a money gate for a field name is the wrong trade; the behaviour F13 asked for (server-rendered "4.3") is unchanged — carry the name to Tasks 9, 11, 12 — cost if wrong: a rename
- Ruling: T6-b REVIEW_ALREADY_DECIDED / REVIEW_CODE_INVALID envelopes are exercised in Task 7 where they are raised — cost: none
- Ruling: T7-a admin review routes check the admin host lock / admin lens before the switch — the admin host lock is the outermost boundary and an admin is the only caller; "switch before lens" protects member-facing NOT_AVAILABLE semantics, which do not exist here — cost: none
- Ruling: T7-b a pending item's wait restarts at its last edit — edited text is new content to the moderator — cost: an edited item queued behind newer ones
- Ruling: T7-c approving a held review or reply while another open child-safety/personal-info report still names it is refused with 409 REVIEW_REPORT_OPEN (message_key "hub.review.report_open"), mirroring MEDIA_REPORT_OPEN — a moderator must not re-publish over a standing child-safety report; this extends the global code list deliberately — cost if wrong: one more code
- Ruling: T7-d review/reply report rows don't offer Suspend listing — a family's words are not grounds to suspend a teacher — cost: none
- Ruling: T7-e an owner/manager-filed report does not block approval (consistent with F10: it holds nothing; it stays in the queue and upholding it still removes per F9) — cost if wrong: a moderator approves over an owner's child-safety report they had not yet read
- Ruling: T7-f Task 10 must leave no hub_report rows naming a review or reply removed by a listing/account cascade (forget first, then cascade) — carry to T10
- Ruling: T8-a owners are notified only when the batch has a hub_public_rating row after the run (≥3 AND publicly listed) — a hidden batch's owner could open nothing (Task 5 reads only the views), so a notice there points at an empty screen — cost if wrong: an owner of a hidden batch learns of new reviews only on relisting
- Ruling: T8-b an upheld report decided while the switch is off still removes the review and tells its author "removed" — a removal is a safety action and, like a deletion, is never gated by the switch — cost: an author notice while reviews are dark
- Ruling: T9-a (F18 applied to the brief's copy) below threshold the public pages show NO count — RatingSummary.count is int | None, None below threshold, and the line is "Ratings appear once a class has 3 reviews." / "কোনো ক্লাসে 3টি রিভিউ হলে রেটিং দেখা যাবে।", shown identically for 0, 1 or 2 reviews so nothing distinguishes them (the view has no row below 3 anyway); test "2 → count line only" becomes "2 → the identical below-threshold line as 0" — cost if wrong: one less signal on small batches
- Ruling: T9-b the public view model's server-rendered average is named average_label (T6-a consistency; money gate)
- Ruling: T9-c month fields named month_label (T6-a reasoning); rating_stars key accepted; noqa RUF001 on the decided en dash accepted
- Ruling: T9-d a cached search page may show the old owner rating / sort order for up to the 300 s TTL after a batch drops below 3 — the stale figure was itself a ≥3 aggregate already public, and search pages are deliberately never invalidated (H2) — cost: 5 minutes of a stale rating
- Ruling: T9-e the web /ui/hub-report kind=review|reply handling belongs to Task 11 (preflight row 41) — carry to T11
- Ruling: T10-a two mutual solo-reviewers deleting at the same instant may deadlock; the deletion retry wrapper re-runs it — accepted (cost: a retry)
- Ruling: T10-b Task 13 also updates the hub_moderation_event label in scripts/generate_privacy_policy.py ("listing or report" → include reviews and replies) — carry to T13
- Ruling: T10-c Task 13's PRIVACY.md prose (T2-d) also says reviews of a solo teacher's classes go with the listing — carry to T13
- Ruling: T11-a Task 11 also adds bangla-layout-check.md rows for the admin Reviews tab (T7 minor) and the public review section (T9 minor), since it edits that file — those two FINAL-WAVE items move here
- Ruling: T11-b shared strings are hub_review_* etc. in Android values (not web_*), so Task 12 reuses them — the i18n test reserves web_* for web-only keys — cost: none
- Ruling: T11-c a held review/reply shows its author "Awaiting review" — the author never learns a report exists (protects the reporter); Task 12 mirrors it
- Ruling: T11-d the teacher Reviews entry is a row on the listing editor (no tab bar exists), drawn only when GET /v1/hub/reviews succeeds — matches Android placement
- Ruling: T12-a coverage floor stays 90.85 in this commit (91.07 measured); the ratchet is raised in the final wave after fixes settle — cost: none
- Ruling: T12-b optional ?title= on the editor route accepted (path as ruled); guardianHomeRoute() extraction accepted; inbox taps open regardless of lens (existing Android convention)
- Ruling: FR-a (revises T7-c) every approval of a review or reply is refused with REVIEW_REPORT_OPEN while _still_held(...) is true, whatever the before-status — an edit or reply replacement moves a held item to pending and must not escape the block — cost: none
- Ruling: FR-b (revises F10/T7-e) the "runs the batch" set for report holds and _still_held equals the eligibility exclusion of T3-c: owner, accepted unrevoked managers, and live teachers assigned to the batch by weekly slot or single class; one shared helper so the two cannot drift — cost if wrong: a class teacher's genuine child-safety report waits for the 24 h queue
- Ruling: FR-c (revises F20/T3-b) the server sends eligible_from only with hub.review.not_yet_eligible (tenure alone unmet), as the global constraint states — the F20 broadening let the date over-promise when attendance was also unmet — cost: a guardian missing both learns the date only after attending
- Ruling: FR-d the T10 orphaned listing/photo reports and the batches_count Bengali digits stay deferred as pre-H4 follow-ups (listed for the owner)
- Ruling: New-1 (the admin decide route's 409 text still says "held" only) is carried into H5 Task 5, which regenerates openapi anyway. Why: it is one sentence, and the PR is shared. Cost if wrong: a stale doc string in the PR.
- Ruling: New-2 (privacy walker: a `-> dict[str, str]` route infers an untyped schema that walks clean) is carried into H5 Task 5 as fail-closed on an untyped object schema for listed routes. Why: H5 adds private-data routes to the same walker. Cost if wrong: a future bare-dict route evades the walker.
- Ruling (fixer concern c): dropping tenure_ok as a sort key is accepted. The re-reviewer showed the chosen seat's details are read only on an eligible first submit.

### Deferred minors

- Task 1: minor (deferred) — nits in tests/gates/test_hub_reviews_switch_infra.py and hub.review.off placement in MessageKeys.kt (see task-1-review.md)
- Task 2: minor (deferred) — below-threshold test exercises only `held` (not removed/deleted/edited-to-pending); grant test can't see the explicit Call 6 grant (has_table_privilege counts inherited).
- Task 3: minor (deferred) — not-memoised test runs outside a request; no test for author keeping lens after relink-block/seat delete.
- Task 4: minor (deferred): M-1 fourth copy of non-committing upsert in app/auth/ceilings.py — a private _consume_in_transaction would collapse them
- Task 4: minor (deferred): M-2 service-level range backstop answers 400 fields "rating" while the handler answers 422 "body.rating"
- Task 4: minor (deferred): M-4 test_forget _references covers only uuid columns in public schema; narrow docstring or Task 8 checks its jsonb payload
- Task 4: minor (deferred): M-5 test_delete_is_total doesn't assert reports on sibling reviews survive
- Task 4: minor (deferred): M-6 write re-checks the switch (keep — defence in depth)
- Task 4: minor (deferred): M-3 lost-race re-lock uses .one(); a concurrent DELETE between conflict and re-lock gives a 500
- Task 4: minor (deferred): if the race winner is deleted between conflict and re-lock, the PUT returns the empty state without writing (silent no-op) — untestable branch
- Task 5: minor (deferred): owner.py:614-615 lock-order comment misstates the author delete's order
- Task 5: minor (deferred): gate regexes miss comma joins, public.review/quoted names, USING review (brief's regexes)
- Task 5: minor (deferred): test_teacher_deletes_their_reply_below_threshold ends with always-true assert other != target
- Task 5: minor (deferred): put_reply can answer REVIEW_NOT_FOUND after a committed write (final view re-read)
- Task 5: minor (deferred): no test for an owner with no listings (empty ANY arrays)
- Task 5: minor (deferred): race tests' lock-waiter check not scoped to the thread's backend
- Task 6: minor (deferred): hub_reviews.py builds its own 404 off entries; REVIEWS_OFF_RESPONSES in switch.py unused and its docstring claim false
- Task 6: minor (deferred): off test assumes SHIKKHOKPLUS_HUB_REVIEWS unset in the environment (should monkeypatch delenv)
- Task 6: minor (deferred): privacy walker silently skips a listed route with no response model
- Task 6: minor (deferred): cast over loosely-typed reply status (hub_reviews.py:287)
- Task 6: minor (deferred): unauthenticated call to a gated route answers 404 HUB_REVIEWS_OFF while off, not 401 (follows ordering ruling)
- Task 7: minor (deferred): lock-order test passes whichever row is locked first (T4-c/T5-d rests on reading)
- Task 7: minor (deferred): _still_held reads manager membership at decision time, not filing time
- Task 7: minor (deferred): hub_reviews_reported counts review reports only, not reply reports (docstring states the reading)
- Task 7: minor (deferred): decide validates code before existence/status (400 before 404/409)
- Task 7: minor (deferred): _hours/_SECONDS_PER_HOUR duplicate reports._hours
- Task 7: minor (deferred): broad except Exception rollback in reviews.decide vs media's per-branch pattern
- Task 7: minor (deferred): BN "Public reviews" rendered as "Published reviews" — HUMAN Bangla review
- Task 8: minor (deferred): centre manager fan-out tested with one recipient only
- Task 8: minor (deferred): heartbeat assertions check existence only
- Task 8: minor (deferred): job reads once per review and per batch (N+1)
- Task 8: minor (deferred): tell_author lives in the job module but moderation uses it
- Task 8: minor (deferred): redundant expression in decide
- Task 9: minor (deferred): canary checks the 2-review count on one walked page of 11
- Task 9: minor (deferred): sort test pins order, not score values
- Task 9: minor (deferred): no test asserts per-star meter values
- Task 9: minor (deferred): batch page computes an owner aggregate it never renders (queries.py:663)
- Task 9: minor (deferred): three copies of the aggregate shape in ratings.py
- Task 9: minor (deferred): query-key gate's drift fixture is weak
- Task 10: minor (deferred): a review created on a solo batch after the lock is removed by the cascade, not forget (practically unreachable orphan)
- Task 10: minor (deferred): one UNION lock statement would remove the T10-a deadlock
- Task 10: minor (deferred): no test pins locking before forget (T5-e)
- Task 10: minor (deferred): _publish/_reply/_report helpers duplicate other test files
- Task 10: minor (deferred): test_review_deletion.py:677 counts every reply in the DB
- Task 11: minor (deferred): teacher Reviews screen keeps stale content if the switch goes off after load
- Task 11: minor (deferred): listing editor fetches the full reviews payload to decide the entry (T11-d accepted)
- Task 11: minor (deferred): no test for a failed /v1/hub/reviewable read
- Task 11: minor (deferred): offline wording differs between guardian editor and teacher screen
- Task 12: minor (deferred): HubListing Reviews row flickers on return
- Task 12: minor (deferred): past "edit until" date still shows after the window closes (web too)
- Task 12: minor (deferred): off-state route test waits with sleeps and can pass vacuously
- Task 12: minor (deferred): Kotlin contract test doesn't pin standing, waiting_on or rejection codes
- Task 12: minor (deferred): REVIEW_NOT_FOUND on delete leaves a stale review on screen
- Task 12: minor (deferred): load() not guarded against Loading — two calls while loading issue two GETs
- Task 13: minor (deferred): in-app notice before a material policy change has no record or check (HUMAN STEP / follow-up)
- Task 13: minor (deferred): Data Safety "What is stored" omits approved time, published month, reply writer and times
- Task 13: minor (deferred): switch-off regex in test is loose

### Human steps recorded

- Task 1: DONE_WITH_CONCERNS 55ac5de; added hub-reviews to deploy role SSM read list (bootstrap re-apply HUMAN STEP) and --cov=app.reviews; full suite not re-run after the coverage-scope fix. Review dispatched (sonnet).
- Task 13: HUMAN STEPS recorded: D8 legal review, D9 bar (read by hand; no admin figure), D6 declarations, Bangla site sentence; policy promises an in-app notice on material change and nothing sends one (runbook step 3 flags it)
- Task 13: minor (deferred): in-app notice before a material policy change has no record or check (HUMAN STEP / follow-up)
- H4: complete (6ec06ae..f152c10). Human steps: a production role and wrapper before D9; Bangla check of hub_review_unavailable and web_admin_reviews_public_sub.

## H5 (join requests)

### Rulings

- Ruling: H5 is built dark behind SHIKKHOKPLUS_HUB_ENQUIRIES (off) even though project.md Forbidden ("NEVER expose anything a student or guardian writes to any teacher, except a hub review…") would block turning it on — dark code exposes nothing; amending the rule via the learnings ritual is the runbook's first step and is the OWNER'S decision, surfaced in the final message — cost if wrong: the owner declines the amendment and H5 stays off (no rework beyond dead code).
- Ruling: guardians only, by a required unstored "parent/guardian, 18+" declaration — cost if wrong: Play Families may require a stronger signal (owner question).
- Ruling: message length 300 (FR-41) over the technical design's 1000 — spec wins.
- Ruling: no moderation/admin visibility of private enquiries (D4: admins see only content submitted for publication); owner protection is close/turn-off/limits — cost if wrong: add a report kind later.
- Ruling: seven routes (target read, withdraw DELETE, owner single-get) beyond REPORT §7.6's four — each serves consent, total deletion, or keeps a phone out of a URL.
- Ruling: retention 90 days from sending, open or closed — spec silent; cost if wrong: one constant.
- Ruling: F1–F21 are accepted as the scan recommends (see preflight.md Findings). Why: each matches the built code, and the spec is silent or agrees. Cost if wrong: small, local rework per finding. Owning tasks: F1, F2, F3, F4 to T1; F5, F21 to T2; F7, F8, F10, F12, F19 to T3; F11 to T4; F6, F9, F13 to T5; F14, F20 to T8; F15, F20 to T9; F16, F17, F18 to T10. F1 adds a human step: re-apply bootstrap/ before the first H5 deploy.
- Ruling: F22 (an eighth hub-reader view against spec §2's four) is recorded as a deviation. Why: a new view is narrower than altering hub_public_owner (Call 15). Cost if wrong: one view to fold later.
- Ruling: F23 is resolved. H4 closed clean at f152c10 (re-review: 17/17 fixed). The ledger is saved to scratchpad/rulings/h4-progress.md.
- Ruling: the H4 residuals carry into T5. New-1: the admin decide route's 409 text says pending and held are both refused; regenerate the schema. New-2: the privacy walker fails closed on an untyped object schema (a bare dict response) for listed routes. Both are folded into F13's shared _route_field_leaks.
- Ruling: I-1 is fixed even though it is partly plan-mandated ("the H4 Task 1 pattern"). Why: T10 extends this file and would make a third copy; a shared tests/gates/_hub_switches.py is mechanical. Cost if wrong: one small refactor of the H4 gate file.
- Ruling: option 1. Split the gate: tables stay NUMERIC(12,2); a view money column must be numeric and trace through pg_depend only to NUMERIC(12,2) table columns, with a fixture proving the view rule fires. Why: the money rule governs storage, the view stores nothing, and the provenance check is stronger than leaving views unchecked. Exempting or narrowing would weaken the gate (project.md NEVER), and recreating four views is out of scope. Also fix the false 0040 comment. Cost if wrong: one gate function to revisit.
- Ruling: a created_at now() default is accepted (it matches every comparable table).
- Ruling: the policy text describing solo-owner deletion ahead of T7's forget is accepted. Why: same PR, switch off, and T7 is owed; the final review checks T7 delivers it. Cost if wrong: the policy overpromises until T7 lands.
- Ruling: Minor 1 (no negative test for the gate's view branch) and Minor 4 (the docstring's "Three CHECKs" is an unasserted count, which project.md NEVER forbids) join the fix round. Why: both are cheap, and M4 is a standing rule. Cost if wrong: none.
- Ruling: consume after insert, i.e. only once a create is certain, accepted over the brief's step order. Why: the H4 T4 I-1 lesson. Cost: none.
- Ruling: global-constraints.md is updated for F10 (ENQUIRY_CONTAINS_CONTACT); the committed plan text stays as written, and the ledger is the record.
- Ruling: length checks returning 400 REQUEST_INVALID before the DB CHECK are accepted. Why: they avoid a 500.
- Ruling: the switch is gated at the T5 route decorator, not in the service, accepted per Global Constraints "Ordering". Cost if wrong: a non-route caller bypasses the switch; T5 review checks it.
- Ruling: MyEnquiry.owner_public_name is nullable via LEFT JOIN, accepted; the reviewer judges it.
- Ruling: carry T3 M1 (no test for a None owner_public_name) and M3 (the named-test manifest claims passing cases live in another function) into T4. Why: cheap, and T4 edits tests/enquiries. Cost: none.
- Ruling: carry T4 M1 (OUTCOMES is a third unchecked spelling of the outcome set) into T5. Fix: derive it with get_args or assert equality. Cost: none.
- Ruling: F9 is spelled as Literal[True] behind a JSON-boolean-only check, because Pydantic 2.14.2 refuses strict on a Literal. The effect matches F9 (1, 1.0, "true" and "on" all answer 422) and is tested. Cost: none.
- Ruling: the two existing privacy gates admit exactly OwnerEnquiryWire.guardian_phone and guardian_email, with a tested allowance. The contact predicate permits them on owner-side responses only; the reviewer judges the narrowness. Cost if wrong: a gate wider than needed.
- Ruling: Minors 1–4 all join the fix round. Why: three touch the privacy gate (the admin scan of app.schemas.enquiries, guardian routes forbidding guardian_phone and guardian_email, the stale "no phone" name), all are cheap, and the walker is being edited anyway. Cost: none.
- Ruling: the completed H0/H1 plan keeps the old test name, as a historical record. Cost: none.
- Ruling: the preview link also requires a slug, so a draft never renders an empty owner= parameter. Cost: none.
- Ruling: an opt-out rides the cache TTL with no invalidation, per Call 14. Cost if wrong: a stale link for at most the TTL, with the send refused by the server.
- Ruling: the send-vs-solo-owner-deletion race is deferred to the final review rather than fixed in T7. A guardian's request inserted after the owner's deletion commits is left with no reader on the owner side (the owner's accounts are gone). The guardian can still see and withdraw it, and the 90-day purge removes it. H4 reviews have the same race. The fix (a share lock on owner_listing in send) touches T3. Cost if wrong: the guardian keeps an orphan request for up to 90 days.
- Ruling: fix the deferred send-vs-deletion race now, together with T7 Minor 1 (the sender-side twin, which breaks Call 12), Minor 2 (a comment naming the retry backstop) and Minor 3 (test robustness), in one T7 follow-up round. Why: the reviewer gave a sound, bounded design (send takes the account advisory key and FOR SHARE on owner_listing; deletion takes FOR UPDATE on owner_listing before for_account). Doing it now is cheaper than in the final fix wave. The H4 reviews twin is left for the final review. Cost if wrong: one round.
- Ruling: the two new minors are fixed in round 2 now. (a) The early not-found raise in send leaks, by query count and lock wait, that a non-public slug exists; resolve first, then refuse when the held row is absent. (b) The cycle comment at deletion.py:668-674 is inverted. Why: (a) is privacy-adjacent and both are tiny. Cost: none.
- Ruling: the consent choice is two radios with no default ("Share my phone number with {owner}" / "Don't share it"), not a checkbox. Why: consent is an explicit choice either way, and a single unticked-by-default checkbox forces tick-then-untick to decline. The wire is unchanged. Cost: none.
- Ruling: the ENQUIRY_CONTAINS_CONTACT copy is reworded in T9 (which owns the shared Android strings) to fit radios and email-only accounts, e.g. "Remove phone numbers and web addresses. To give the teacher your contact, choose Share." EN and BN, keeping the shared শেয়ার word, with the web label test kept green. Cost: one string pair.
- Ruling: Retry is offered only when the error is retryable (server-provided retryable, or network), accepted per team.md "retryability is a property of the error class".
- Ruling: the prefilled form shows the server's message when the request cannot be read, accepted.
- Ruling: the BN share label using শেয়ার (matching the contact-refusal copy) is accepted over the brief's verbatim text.
- Ruling: carry to T9 (it owns shared copy) T8 M1 (the help line "cannot call you" also shows under the email option; reword to "cannot contact you"), M2 (HubEnquiry.test.tsx pins "tick Share"; pin only the shared word) and M4 (enquiries.api.ts states the unasserted counts "seven/four/three", a project.md NEVER).
- Ruling: test-after on the Android UI is accepted. It falls outside team.md's test-first predicate, since nothing there is money or authorization decided client-side.
- Ruling: extracting the More Profile block into navigation/MoreRoute.kt for a route test is accepted (behaviour unchanged).
- Ruling: M2 (move Quiet/Notice/DeleteDialog and NOTICE_MILLIS to core/designsystem, delete the duplicate Quiet, keep levelLabel in hublisting), M3 (list refresh read guard), M4 (cancel reading in answer()) and M5 (saved outliving the VM on process death) all join round 1. Why: M2 is the team.md erosion rule and XS now; M3–M5 are TC-8 / double-submit correctness on a thinly-reviewed surface. Cost: one larger round.
- Ruling: qualify the site sentence (index.html:192) now, before review, rather than leaving it to runbook step 2. Why: it is consistent with the conditional policy prose and is one sentence. Cost: none.
- Ruling: M1 (class is chosen, not typed), M2 ("What it holds" omissions), M3 (the switch-off runbook test is weakly pinned) and M5 join round 1. All are small doc and test fixes. Cost: none.
- Ruling: the full make check runs once at the final review rather than here.
- Ruling: disk freed (about 20 GB) by deleting stale tfv*/infra-copy Terraform scratch copies in the controller scratchpad. Containers and volumes were not touched.
- Ruling: the final fix wave covers M1, M2, the T3 docstring, the T1 test name, the H4-twin comment, M6 (site copy, done now rather than at runbook step 2), M7 (MINE_LIMIT to the retention-bound maximum, since it backs a policy promise) and M5 (one caplog test, per the team.md "important rules are mechanical"). Then the full make check plus Android. Cost if wrong: one fix wave.
- Ruling: deferred: M3 (inbox taps use the current workspace; pre-existing for claim_to_verify and hub_listing_suspended). Cost if wrong: a multi-workspace manager may miss a request until they switch workspace.
- Ruling: deferred: M4 (purge vs deletion 40P01). Cost if wrong: one day's purge stops early, and the next run catches up.
- Ruling: deferred: M8 (the preview link refuses the owner). Cost if wrong: an owner testing their own link thinks it is broken.
- Ruling: MINE_LIMIT is 5 × (90 + 2) = 460, not 450. The +2 covers the part-day the window starts in and the day since the purge last ran. CLASS_AGE is moved to dispositions.py so sending.py avoids importing the purge. Cost if wrong: 10 extra rows listed.
- Ruling: the H4 twin misnomer test_deploy_validates_switch_value_and_writes_it is left as a deferred minor.
- Ruling: main moved on with PR #83 (parallel backend suite via xdist, conftest, Makefile, check.yml, requirements). The branch merges origin/main before the PR is opened, then runs the full gate under the parallel runner. Why: the team requires branches up to date, and H3–H5 race tests (pg_locks waits) must be proven under xdist. Cost if wrong: one merge commit.

### Deferred minors

- Task 1: minor (deferred): deploy.yml switch read duplicated (factor read_switch at a third switch).
- Task 1: minor (deferred): app/hub/enquiries/switch.py mirrors app/reviews/switch.py (factory at a third switch; F3 mandated).
- Task 1: minor (deferred): test_deploy_validates_enquiries_switch_value_and_writes_it asserts no write (H4 misnomer copied).
- Task 1: minor (deferred): enquiries_on docstring names gated routes that do not exist until T5–T7.
- Task 2: minor (deferred): the tokenizer loses backslash-escape state (fails closed).
- Task 2: minor (deferred): test_hub_reader_meta asserts rolinherit rather than pg_auth_members.inherit_option (has_table_privilege is the real pin).
- Task 2: minor (deferred): test_closed_needs_outcome_and_time matches the constraint by prefix only.
- Task 2: minor (deferred): the owner_id ON DELETE CASCADE is untested.
- Task 2: minor (deferred): no exact-90-day boundary row in the purge test.
- Task 3: minor (deferred): consume_contact_change remains a fifth copy, outside F12's named set.
- Task 3: minor (deferred): the contact check duplicates app/reviews/content.py; share contains_contact(text).
- Task 3: minor (deferred): the ceilings.py:419 comment says "five is five different teachers" (withdraw-and-resend counts again).
- Task 3: minor (deferred): the test_target docstring lists a suspended-batch case that does not exist.
- Task 3: minor (deferred): forget runs 2×N remove_for_source statements; T7 bulk could use one DELETE.
- Task 3: minor (deferred): consume_contact_change is still a hand copy.
- Task 4: minor (deferred): the batch_name '' fallback is untested and currently unreachable.
- Task 6: minor (deferred): test_public_enquiry_link:229 search page does not assert the owner is a hit.
- Task 6: minor (deferred): the switch-off test's on-control checks the EN owner page only.
- Task 6: minor (deferred): the batch link uses batch.report_id (pinned by a test); add a comment.
- Task 8: minor (deferred): untested paths: the NewStudent failed enquiry read, the non-retryable close-after-save banner, and MyEnquiries under HUB_ENQUIRIES_OFF.
- Task 8: minor (deferred): the unavailable-or-ErrorCard block is duplicated, and the retryable expression appears at 5 sites.
- Task 8: minor (deferred): MyEnquiries (eager) imports teacher/hub/hubUi into the main chunk.
- Task 9: minor (deferred): the RefreshFailed banner render is untested, and its copy does not say the list is stale (KDoc and bangla rows say "could not refresh").
- Task 9: minor (deferred): file-private duplicates of Quiet, NOTICE_MILLIS and DeleteDialog remain (not cross-feature).
- Task 9: minor (deferred): afterSave() WAIT on a non-retryable failure leaves only Back (pre-existing; contradicts its KDoc).
- Task 10: minor (deferred): one over-long wrapped line in PRIVACY.md "What the teacher sees".

### Human steps recorded

- Task 1: implementer DONE_WITH_CONCERNS (e918db4): human steps are apply infra/ and re-apply bootstrap/ before the first H5 deploy, and a Bangla check of the term ভর্তির অনুরোধ
- Task 3: human: Bangla check of the 4 new strings, and the contact-refusal copy must match the T8/T9 consent checkbox label.
- Task 6: human: Bangla check of the link text.
- Task 8: human: Bangla check of all new web strings.
- Task 9: human: Bangla check of the reworded contact and help strings.
