# Public Hub H3 (Moderated Photos) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Release 2 of the hub: moderated photos on owner and batch pages.
- Owners upload photos from the web and Android editors.
- A sandboxed Lambda re-encodes every upload to WebP, which strips EXIF and GPS data.
- The platform admin approves each photo before it is public.
- Approved photos appear on the public pages.
- A child-safety or personal-information report hides a photo at once.
- Deleting a photo, or the account, removes the objects.

**Architecture:**
- **Upload.** The client uploads straight to a private S3 bucket through a presigned POST. The bytes never touch the API.
- **Sanitising.** An S3 event triggers a Lambda with no VPC, no database access and no other bucket access. It decodes with Pillow and writes WebP variants to `staged/`.
- **Approval.** The API reads the Lambda's result. On the admin's approval it copies the variants to `public/{public_key}/`, the only prefix CloudFront serves. CloudFront serves that prefix on the site distribution at `/m/*`.
- **Credentials.** The API reaches the bucket with short-lived credentials for a narrow media role, refreshed by the host (see Deviations).
- **Takedown.** Object deletes and CDN invalidations go through outboxes written in the same transaction as the change.

**Tech Stack:**
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, and boto3 (new: pinned, locked, used only in `app/hub/media/storage.py`).
- Lambda: Python 3.12 on arm64, with Pillow pinned in its own hashed lockfile.
- Infra: Terraform (S3, CloudFront OAC, Lambda, IAM).
- Clients: web React/TS; Android Kotlin/Compose with the Photo Picker.

**Spec:** `docs/superpowers/specs/2026-11-14-public-hub-design.md`. Read in particular:
- §2 (modules: `app/hub/media`, "Pillow lives only in the Lambda");
- §3 (`listing_media`);
- §5 Photos;
- §8 rule "ALWAYS pre-moderate hub images";
- §10 (a report on a photo hides it at once).

The detail behind §5 is in `docs/reviews/2026-11-14-public-hub/team/technical-design.md` §3 (media pipeline), §4.1 (media and admin routes), the error table, and §7 (the Lambda's own test suite).

**Built on H2** (`docs/superpowers/plans/2026-11-17-public-hub-h2.md`, on `main`):
- the four public views read as `shikkhok_hub_reader`;
- `render.page` with the view registry;
- the `cdn_invalidation` outbox, with `claim`/`ack`/`fail` from a host script, because the container never calls CloudFront (ruling R8);
- the canary harness;
- `HubReport` on web and the Android App Link (report kind `media` already exists in `HUB_REPORT_TARGET_VALUES`).

**Deviations from the spec, decided here (owner: please confirm before execution):**
1. **How the API reaches S3.** The spec has the API presign uploads, read results and copy objects, but the container holds no AWS credentials (OPS-4: IMDS hop limit 1). We keep that, and add a dedicated `media` IAM role whose only permissions are on the media bucket's prefixes.
   - A host cron job assumes the role every 15 minutes and writes the 1-hour credentials to `/srv/shikkhokplus/media-creds/credentials`, mounted read-only into the `api` container.
   - boto3 reads them through `AWS_SHARED_CREDENTIALS_FILE`.
   - An SSRF still cannot reach the instance role. A compromised container gains only photo-bucket access.
   - Rejected alternatives:
     - raising the hop limit, which exposes the instance role;
     - a host signing daemon, which is a second long-running service to secure;
     - an IAM user key, which would be a long-lived key, forbidden by the bootstrap README.
2. **A `held` media status.** §10 says a child-safety or personal-information report on a photo hides it at once. The §3 status list has no state for "approved but taken down pending a decision", so `held` is added.
3. **An `archive/` copy of approved variants.** `staged/` expires after 30 days, so a held photo that is later cleared could not be restored. On approval the variants are copied to both `public/{public_key}/` and `archive/{media_id}/`. A restore copies from `archive/` to a fresh `public_key`, so no stale cached URL comes back.
4. **Suspension and unpublishing unlink photos but do not delete their objects.** The page stops showing them through the view, and the URLs remain unguessable 128-bit keys. Objects are deleted only on withdraw, delete, reject, hold, or account deletion.
5. **Migration numbers** start at 0043.

## Global Constraints

- **Upload limits (verbatim):**
  - **Size:** ≤ 8 MB, i.e. `content-length-range` 1–8388608 in the POST policy.
  - **Types:** exactly `image/jpeg`, `image/png` or `image/webp`.
  - **Presigned POST:** expires in 10 minutes.
  - **Object key:** exactly `quarantine/{media_id}`.
- **Quotas (verbatim):**
  - **Per owner:** 12 photos at owner level (`batch_id IS NULL`).
  - **Per batch:** 8 photos.
  - **Daily:** 30 uploads per owner per day, as `ScopeKind.HUB_MEDIA_DAILY = "hub_media_day"` and `HUB_MEDIA_OWNER_DAILY = 30`.
  - A photo counts against the 12 and the 8 in every status except `rejected` and `withdrawn`.
- **Variants:** WebP at widths 320, 960 and 1600 px (never upscaled), at `staged/{media_id}/{w}.webp`, plus `staged/{media_id}/result.json` `{"ok": true, "width": w, "height": h}` or `{"ok": false, "reason": "unreadable"}`.
- **Decoding:**
  - `Image.MAX_IMAGE_PIXELS = 40_000_000`.
  - The magic bytes must match the declared type.
  - Only the first frame is used.
  - No metadata is written.
- **Statuses:** `awaiting_upload, processing, pending_review, approved, rejected, withdrawn, held`.
  - `public_key IS NOT NULL` exactly when the status is `approved`.
- **Bucket prefixes:**
  - `quarantine/` expires after 1 day.
  - `staged/` expires after 30 days.
  - `public/` and `archive/` never expire.
  - CloudFront (OAC) reads only `public/*`.
- **`/m/*` response headers (verbatim):**
  - `Cache-Control: public, max-age=31536000, immutable`
  - `X-Content-Type-Options: nosniff`
  - `Content-Security-Policy: default-src 'none'; sandbox`
  - `Content-Type: image/webp`
- **Image URL:** `/m/{public_key}/{w}.webp` on the site host. The page CSP's `img-src 'self'` covers it, and nothing in the page CSP changes.
- **Admin preview:** presigned GETs of `staged/` or `archive/` that expire in **5 minutes**.
- **Alt text:** `alt_en` and `alt_bn`, each ≤ 200 characters, phone-scanned like other listing text. Both are required before a photo can be submitted for review.
- **Error codes (verbatim):**

  | Code | Status | Class | Message key |
  |---|---|---|---|
  | `MEDIA_TYPE_NOT_ALLOWED` | 400 | `ValidationError` | `hub.media.type_not_allowed` |
  | `MEDIA_TOO_LARGE` | 400 | `ValidationError` | `hub.media.too_large` |
  | `MEDIA_LIMIT_REACHED` | 409 | `ConflictError` | `hub.media.limit_reached` |
  | `MEDIA_NOT_UPLOADED` | 409 | `ConflictError` | `hub.media.not_uploaded` |
  | `MEDIA_UNREADABLE` | 400 | `ValidationError` | `hub.media.unreadable` |

- **Route counts:**
  - `PUBLIC_ROUTES` stays **19**, and `PUBLIC_CACHEABLE_ROUTES` stays the same **4**.
  - Six new `TeacherLens` routes.
  - Two new `PLATFORM_ADMIN_ROUTES`: `GET /v1/admin/hub/media/{media_id}` and `POST /v1/admin/hub/media/{media_id}/decision`. The admin queue also gains `kind=media`.
- **Public data sources:** public handlers read only the five views `hub_public_owner`, `hub_public_batch`, `hub_public_teacher_name`, `hub_public_area` and `hub_public_media` (new), under `as_hub_reader`. `hub_public_media` exposes approved media only, under a visible owner and (for batch media) a visible batch.
- **boto3:** imported only by `app/hub/media/storage.py`, which a gate test asserts. Never in `app/hub/public/**`.
- **Pillow:** only in `lambdas/image_sanitiser/`. Its `requirements.txt` has hashes and joins `make audit` / `deploy/cve_gate.py` and the release SBOM.
- **Cost:** new `cost_breakdown` lines `media` and `image_lambda`. The budget guard stays under USD 50.
- **Carried from H2:**
  - every backend gate runs ruff, ruff format, mypy and the task's pytest directories, plus `tests/contract` whenever a migration, `DISPOSITIONS` or a route changes;
  - head pins move in all four files;
  - `DISPOSITIONS` / `HARD_DELETE_SCOPES` changes are followed by `python3 -m scripts.generate_privacy_policy`;
  - run `make openapi` then `cd web && npm run gen:api`;
  - EN/BN twins everywhere, with Latin digits;
  - every new Android action is wired through its navigation route, with a route-level test;
  - terraform `fmt` plus `validate` through the scratch provider mirror;
  - CloudFront Functions stay inside the runtime-2.0 feature guard;
  - a comment that states a count is asserted by a test;
  - commits are conventional, with the trailer.

## Review Focus

1. **A file that is not the image it claims to be:**
   - a JPEG/HTML polyglot;
   - an SVG renamed `.png`;
   - a truncated JPEG;
   - a 30 000 × 30 000 PNG bomb.

   Each ends as `{"ok": false, "reason": "unreadable"}`, nothing staged, and `complete` answers `MEDIA_UNREADABLE`. A file that does decode is re-encoded, so no original byte reaches `public/`. Tests: Task 3 `test_polyglot_and_svg_are_unreadable`, `test_decompression_bomb_is_unreadable`; Task 4 `test_complete_unreadable_marks_rejected`.
2. **`complete` called before the Lambda has written its result** (a slow network, a double tap) answers `MEDIA_NOT_UPLOADED` and changes nothing; a later call succeeds. Test: Task 4 `test_complete_before_result_is_not_uploaded_then_succeeds`.
3. **A child-safety report on an approved photo.** The photo leaves the page and its `/m/` URL stops being served before any admin acts. That means `held`, public objects deleted and an invalidation enqueued, all in the report's transaction. Test: Task 6 `test_child_safety_report_holds_photo_in_same_transaction`.
4. **Two uploads racing at the quota** never leave more than 12 owner photos or 8 batch photos. Test: Task 4 `test_concurrent_inits_never_exceed_quota`, with overlapping sessions and an owner-row lock.
5. **A solo owner deletes their account.** No `listing_media` row survives, every object prefix of theirs is enqueued for deletion, and every approved photo's `/m/` path is invalidated. Test: Task 8 `test_solo_owner_deletion_removes_media_rows_and_enqueues_objects`.

---

### Task 1: Media data, outbox and public view (0043)

**Files:**
- Create: `migrations/versions/0043_listing_media.py`
- Modify: `app/db/models.py` (`ListingMedia`, `MediaObjectTask`, `MEDIA_STATUS_VALUES`, `HUB_MEDIA_OBJECT_JOB = "hub_media_objects"` in `EXPECTED_JOBS`), `app/governance/dispositions.py`, `app/governance/deletion.py` (`HARD_DELETE_SCOPES`), the head pins, `tests/privacy/test_hub_public_views.py` (the reader-privilege test: five views plus `bd_area`)
- Test: `tests/db/test_migration_0043.py`, `tests/privacy/test_hub_public_media_view.py`

**Interfaces:**
- Produces:
  - **`listing_media`:**
    - **Columns:** `id UUID PK`, `owner_id FK owner ON DELETE CASCADE`, `batch_id FK batch NULL ON DELETE CASCADE`, `status media_status NOT NULL DEFAULT 'awaiting_upload'`, `content_type VARCHAR(16)`, `byte_size INT`, `public_key CHAR(32) NULL UNIQUE` (hex of 16 random bytes), `width SMALLINT NULL`, `height SMALLINT NULL`, `widths SMALLINT[] NULL` (the variant names written, from `result.json`), `alt_en VARCHAR(200) NULL`, `alt_bn VARCHAR(200) NULL`, `position SMALLINT NOT NULL DEFAULT 0`, `rejection_code VARCHAR(32) NULL`, `created_at`, `decided_at NULL`.
    - **Constraints:** CHECK `(status = 'approved') = (public_key IS NOT NULL)`, and a partial UNIQUE `(owner_id, coalesce(batch_id, '00000000-…'), position) WHERE status = 'approved'`.
  - **`media_object_task`:** `id BIGINT identity`, `op VARCHAR(8) CHECK IN ('delete')`, `prefix VARCHAR(80)` (always one of `quarantine/{id}`, `staged/{id}/`, `archive/{id}/`, `public/{key}/`), `requested_at`, `done_at NULL`, `attempts SMALLINT DEFAULT 0`. A CHECK on `prefix` is a regex over exactly those four shapes.
  - **`hub_public_media` view** (`security_barrier`, `SELECT` to the reader only):
    - **Columns:** `owner_slug`, `batch_slug NULL`, `media_id` (for the report link), `public_key`, `width`, `height`, `alt_en`, `alt_bn`, `position`.
    - **Rows:** approved media whose owner listing is published. Batch media also needs its batch to appear in `hub_public_batch`.
  - **Dispositions:**
    - `listing_media`: `HARD_DELETE`, `SOLO_OWNER`, `LIFE_OF_ACCOUNT`; a centre's media survives a manager's deletion, as its listing does.
    - `media_object_task`: `NOT_PERSONAL`, `DAYS_7`.

- [ ] **Step 1: Write failing tests.**
  - `test_0043_creates_media_tables_view_and_enum` (enum labels exactly the seven statuses).
  - `test_public_key_iff_approved` (CHECK raises both ways).
  - `test_object_task_prefix_shapes_only` (`public/../x` and `profile/` are refused).
  - `test_hub_reader_reads_only_the_five_views` (rename and extend the H2 test).
  - `test_media_view_hides_unapproved_and_unpublished` (one parametrised case per non-approved status, plus owner draft, batch draft, inactive batch).
  - `test_media_view_references_no_private_table` (the H2 two-layer check, applied to `hub_public_media`).
  - `test_media_dispositions`.
- [ ] **Step 2: Run** `pytest tests/db/test_migration_0043.py tests/privacy -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the migration (CREATE TYPE, tables, view with the H2 `CREATE VIEW … WITH (security_barrier)` helper, grant), models, dispositions, head pins. Then run `python3 -m scripts.generate_privacy_policy`.
- [ ] **Step 4: Run** the gate (backend set plus `tests/db tests/privacy tests/governance tests/contract`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): listing media, object outbox and public media view (0043)`.

### Task 2: Media bucket, CDN behaviour, media role and host credentials

**Files:**
- Create: `infra/modules/media/{main.tf,variables.tf,outputs.tf}`
- Modify:
  - `infra/main.tf`: wire the module; cost lines `media = 0.05` (about 1.5 GB) and `image_lambda = 0.00`, with comments stating the arithmetic.
  - `infra/modules/site/main.tf`: a third origin, the media bucket via OAC; an ordered behaviour `/m/*` (GET/HEAD, CachingOptimized, a new images response-headers policy); no viewer function.
  - `infra/modules/app/main.tf`: an instance-role inline policy `sts:AssumeRole` on the media role only.
  - `infra/modules/app/user_data.sh.tftpl`: a `/usr/local/bin/shikkhokplus-media-creds` script and a `*/15 * * * *` cron entry. It runs `aws sts assume-role --duration-seconds 3600`, writes an INI file atomically (temp file + `mv`), mode 0640 with the container's group, and logs to a pre-created file. It also runs once at boot, before compose starts.
  - `deploy/docker-compose.staging.yml`: a read-only mount of `/srv/shikkhokplus/media-creds` into `api`; env `AWS_SHARED_CREDENTIALS_FILE`, `AWS_REGION`, `SHIKKHOKPLUS_MEDIA_BUCKET`.
  - `infra/bootstrap/main.tf`: the workload boundary allows `s3:*Object*` on the media bucket ARN, `sts:AssumeRole` on the media role ARN, and the Lambda and S3-notification management actions the module needs. A person re-applies bootstrap.
  - The web app CSP: `connect-src` (the upload POST) and `img-src` (the editor's presigned thumbnails, and the preview iframe, which inherits the page CSP) each gain exactly the bucket's regional endpoint, from `vite.config.ts`'s config source.
  - The admin UI CSP: `img-src` gains the same endpoint, in `infra/modules/admin`.
  - `deploy.yml`: passes the bucket name into the runtime env.
- Test: `infra/modules/site/functions/runtime-features.test.mjs` (unchanged; it must still pass), `tests/gates/test_media_infra.py`

**Interfaces:**
- Produces:
  - **Bucket:** `{name_prefix}-media`.
    - Block Public Access on, SSE-S3, no versioning, BucketOwnerEnforced.
    - Lifecycle `quarantine/` 1 day and `staged/` 30 days.
    - CORS: `POST` from exactly the web-app origin, with allowed headers limited to what a presigned POST needs.
  - **Media role** `{name_prefix}-media`:
    - trusted only by the instance role;
    - `s3:PutObject` on `quarantine/*` (used only to sign POSTs);
    - `s3:GetObject` on `staged/*` and `archive/*`;
    - `s3:PutObject` and `s3:GetObject` on `public/*` and `archive/*` (copies);
    - `s3:DeleteObject` on all four prefixes;
    - `s3:ListBucket` with the `s3:prefix` condition limited to the four prefixes.
  - **Outputs:** `media_bucket`, `media_bucket_regional_domain`, `media_role_arn`.
  - **Images response-headers policy:** exactly the `/m/*` headers in Global Constraints.

- [ ] **Step 1: Write failing gate tests** (they read HCL and the template text, on the repository's existing gate pattern):
  - `test_media_bucket_blocks_public_access_and_expires_prefixes`;
  - `test_cdn_serves_only_public_prefix_with_sandbox_headers`;
  - `test_media_role_scoped_to_four_prefixes`;
  - `test_instance_role_may_only_assume_media_role`;
  - `test_host_refreshes_media_creds_every_15_minutes_and_at_boot`;
  - `test_compose_mounts_creds_read_only`;
  - `test_cost_breakdown_has_media_lines`.
- [ ] **Step 2: Run** `pytest tests/gates/test_media_infra.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Run `terraform fmt` and `validate` on `infra/` and `infra/bootstrap` through the scratch mirror. Record in `infra/README.md` the manual step: "re-apply bootstrap before the deploy that ships H3".
- [ ] **Step 4: Run** the gate tests plus `make infra-functions`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(infra): media bucket, /m/* behaviour and host-refreshed media credentials`.

### Task 3: The image-sanitiser Lambda

**Files:**
- Create:
  - `lambdas/image_sanitiser/handler.py`;
  - `lambdas/image_sanitiser/requirements.in` (Pillow only) and `requirements.txt` (hashed, from `uv pip compile --generate-hashes --python-platform aarch64-manylinux2014`);
  - `lambdas/image_sanitiser/tests/` (with small fixture files generated at test time, never committed binaries);
  - `infra/modules/media/lambda.tf`.
- Modify:
  - `Makefile`: `lambda-image` builds `dist/image_sanitiser.zip` from the lockfile with `--only-binary :all:`, and `lambda-test` runs its tests. `make check` runs `lambda-test`.
  - `deploy/cve_gate.py` / `make audit`: also audit `lambdas/image_sanitiser/requirements.txt`.
  - `.github/workflows/deploy.yml`: before the release job, build the zip, `aws lambda update-function-code`, and wait for `LastUpdateStatus=Successful`. The release SBOM step includes the Lambda lockfile.
  - `.github/workflows/check.yml`: a `lambda` job.

**Interfaces:**
- Produces:
  - `handler(event, context) -> None`.
  - For each `ObjectCreated` record under `quarantine/{uuid}`:
    1. Read the object.
    2. Check the magic bytes against JPEG (`FF D8 FF`), PNG (`89 50 4E 47 0D 0A 1A 0A`) and WebP (`RIFF....WEBP`).
    3. `Image.open`, then `img.load()` under `MAX_IMAGE_PIXELS = 40_000_000` with `DecompressionBombWarning` as an error.
    4. Apply the EXIF orientation transpose, then convert to RGB (keep RGBA when there is alpha) using the first frame.
    5. Write each width ≤ the source width (always at least the smallest, scaled down to 320 or kept smaller) as `staged/{id}/{w}.webp` (`quality=82`, `method=6`, with no `exif=` and no `icc_profile=`).
    6. Write `result.json`.
    7. Delete the quarantine object.
  - Any decode error writes `{"ok": false, "reason": "unreadable"}` and deletes the quarantine object.
  - Keys that do not match the pattern are ignored and logged.
  - **Terraform:**
    - arm64, Python 3.12, 1024 MB, 30 s timeout, reserved concurrency 2, no VPC;
    - role: `s3:GetObject`/`DeleteObject` on `quarantine/*` and `s3:PutObject` on `staged/*` only, plus logs;
    - S3 notification `s3:ObjectCreated:*` with prefix `quarantine/`;
    - code is ignored after the first apply (the seeder's two-writer split).

- [ ] **Step 1: Write failing tests.** Run them against `handler` with a fake S3 object store (a dict-backed stub passed in through a module-level client factory):
  - `test_jpeg_with_gps_exif_is_stripped` (re-open each output: `getexif()` is empty and no `GPSInfo`);
  - `test_png_with_alpha_keeps_alpha`;
  - `test_variants_never_upscale` (a 500 px source gives `result.json` `widths == [320, 960]`, with `960.webp` 500 px wide; a 200 px source gives `widths == [320]` at 200 px; a 2000 px source gives `[320, 960, 1600]` at those exact widths);
  - `test_polyglot_and_svg_are_unreadable` (Review Focus 1);
  - `test_decompression_bomb_is_unreadable` (a 30 000 × 30 000 PNG header);
  - `test_truncated_jpeg_is_unreadable`;
  - `test_declared_type_mismatch_is_unreadable` (PNG bytes at a key whose upload declared JPEG; the type travels as S3 object metadata `x-amz-meta-declared-type`, set by the presigned POST);
  - `test_quarantine_object_deleted_every_time`;
  - `test_unexpected_key_ignored`.
- [ ] **Step 2: Run** `make lambda-test`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - **Variant rule:** for each target width `w` in (320, 960, 1600), write `{w}.webp` at `min(w, source_width)` wide, skipping a target whose `min` equals the previous target's. `result.json` lists the written widths in `"widths": [...]` alongside width and height.
- [ ] **Step 4: Run** `make lambda-test`, `make lambda-image` (the zip contains Pillow's aarch64 wheel), `make audit`, and terraform fmt/validate. Expected: PASS.
- [ ] **Step 5: Commit** `feat(media): image-sanitiser Lambda re-encodes uploads to WebP`.

### Task 4: Media service — storage wrapper, uploads, library, object outbox

**Files:**
- Create:
  - `app/hub/media/__init__.py`;
  - `storage.py`: `MediaStore` Protocol, `S3MediaStore`, and `FakeMediaStore` in `tests/hub/media/fakes.py`;
  - `uploads.py`;
  - `library.py`;
  - `objects.py` (outbox);
  - `commands.py`;
  - `quota.py`.
- Modify:
  - `pyproject.toml` / `requirements.txt`: boto3 via `make lock`, without `--upgrade`, then `make audit`.
  - `app/auth/ceilings.py`: `HUB_MEDIA_DAILY`, `HUB_MEDIA_OWNER_DAILY = 30`.
  - `app/errors` registry: the five codes.
  - `message-keys.json` and the Android/web bundles: the five keys, EN/BN.
  - `user_data.sh.tftpl`: cron `*/2` `docker compose exec -T api python -m app.hub.media.commands drain`, on the invalidation sender's exec pattern.
  - `tests/gates`: the import gate allows `boto3` only in `app/hub/media/storage.py`.
- Test: `tests/hub/media/test_uploads.py`, `test_library.py`, `test_objects.py`, `tests/gates/test_boto3_confined.py`

**Interfaces:**
- **`MediaStore`:**
  - `presign_upload(media_id: uuid.UUID, content_type: str) -> UploadTicket` (url, fields, expires_at);
  - `read_result(media_id) -> SanitiseResult | None` (None when absent);
  - `copy_variants(src_prefix: str, dst_prefix: str, widths: list[int]) -> None`;
  - `delete_prefix(prefix: str) -> None`;
  - `presign_get(key: str) -> str` (5 minutes).
  - `S3MediaStore()` takes its bucket from `SHIKKHOKPLUS_MEDIA_BUCKET`. When the bucket is unset, `presign_upload` raises `TransientError` and `delete_prefix` logs and no-ops (local development).
- **`uploads.init_upload(session, store, lens: TeacherLens, *, batch_id, content_type, byte_size, now) -> UploadTicket`:**
  - validates the type and size (the two `ValidationError` codes);
  - locks the owner row `FOR UPDATE`, checks the 12/8 quotas (`MEDIA_LIMIT_REACHED`), then consumes `HUB_MEDIA_DAILY`;
  - inserts `awaiting_upload` and presigns.
  - The batch must belong to the lens's owner, or the caller gets the existing not-found refusal.
- **`uploads.complete(session, store, lens, media_id, *, alt_en, alt_bn) -> ListingMedia`:**
  - no result yet → `MEDIA_NOT_UPLOADED`;
  - unreadable → status `rejected`, `rejection_code='unreadable'`, enqueue a delete of `staged/{id}/`, raise `MEDIA_UNREADABLE`;
  - ok → `pending_review` with width, height and widths, alt text phone-scanned.
  - Idempotent on `pending_review`.
- **`library`:**
  - `list_media(session, lens, batch_id | None) -> list[ListingMedia]`;
  - `update_alt(...)`: a change to an `approved` photo's alt text returns it to `pending_review`, enqueues a delete of its `public/{key}/` and an invalidation, and clears `public_key`;
  - `reorder(session, lens, batch_id, ids) -> list[ListingMedia]`;
  - `withdraw(session, lens, media_id) -> None`: status `withdrawn`, enqueue deletes of every prefix it has, and an invalidation of `/m/{key}/*` if it was approved.
- **`objects`:**
  - `enqueue(session, prefixes: list[str], now) -> None`;
  - `drain(session, store, now, limit=50) -> int`: marks `done_at`, or increments `attempts` and logs on failure.
  - The heartbeat is `HUB_MEDIA_OBJECT_JOB`, stamped on an empty drain or a drain that completed work (the R8a rule).

- [ ] **Step 1: Write failing tests** (with `FakeMediaStore`):
  - `test_init_refuses_type_size_and_foreign_batch`;
  - `test_init_counts_every_nonterminal_status_against_quota`;
  - `test_concurrent_inits_never_exceed_quota` (Review Focus 4: two threads, two sessions, Barrier);
  - `test_daily_ceiling_30`;
  - `test_presign_policy_exact` (`S3MediaStore` against botocore's Stubber: conditions contain `content-length-range` 1–8388608, the exact Content-Type, the key `quarantine/{id}`, the `x-amz-meta-declared-type` field, and a 600 s expiry);
  - `test_complete_before_result_is_not_uploaded_then_succeeds` (Review Focus 2);
  - `test_complete_unreadable_marks_rejected`;
  - `test_alt_text_phone_scanned_and_required`;
  - `test_alt_edit_on_approved_returns_to_review_and_unpublishes`;
  - `test_withdraw_enqueues_all_prefixes_and_invalidation`;
  - `test_drain_marks_done_and_retries_failures`;
  - `test_boto3_imported_only_by_storage`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the gate plus `tests/hub tests/gates tests/contract`, and `make audit`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(media): upload sessions, quotas, library and object outbox`.

### Task 5: Media editor API

**Files:**
- Create: `app/schemas/media.py`
- Modify: `app/api/hub.py` (or a new `app/api/hub_media.py` registered beside it), `app/contract/routes.py` (no public change; the six routes resolve `TeacherLens`), `openapi.json` and `web/src/api/schema.d.ts` (generated)
- Test: `tests/hub/media/test_media_routes.py`

**Interfaces:**
- **Routes:**
  - `POST /v1/hub/media/uploads`: `MediaUploadInit{batch_id: UUID | None, content_type: Literal["image/jpeg","image/png","image/webp"], byte_size: int}` → `MediaUploadTicket{media_id, url, fields: dict[str, str], expires_at}`.
  - `POST /v1/hub/media/{media_id}/complete`: `MediaComplete{alt_en, alt_bn}` → `MediaResponse`.
  - `GET /v1/hub/media?batch_id=` → `list[MediaResponse]`.
  - `PATCH /v1/hub/media/{media_id}`: `MediaUpdate{alt_en?, alt_bn?}` → `MediaResponse`.
  - `PUT /v1/hub/media/order`: `MediaOrder{batch_id?, ids}` → `list[MediaResponse]`.
  - `DELETE /v1/hub/media/{media_id}` → 204.
- **`MediaResponse`:**
  - Fields: `id`, `batch_id`, `status`, `alt_en`, `alt_bn`, `position`, `width`, `height`, `rejection_code`, `thumb_url`.
  - `thumb_url` is the public `/m/{key}/320.webp` when approved, else a 5-minute presigned GET of `staged/{id}/320.webp` when `pending_review`, else null. It is the owner's own photo.
- **Rules:** every write consumes the existing `HUB_LISTING_OWNER_DAILY`. Upload init consumes `HUB_MEDIA_DAILY` instead.

- [ ] **Step 1: Write failing tests:**
  - `test_six_routes_require_teacher_lens`;
  - `test_class_teacher_and_other_owner_refused`;
  - `test_upload_flow_end_to_end_with_fake_store`;
  - `test_error_envelopes_for_five_codes`;
  - `test_media_response_has_no_private_fields` (the H0 privacy gate walks `MediaResponse`).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement**, then run `make openapi` and `npm run gen:api`.
- [ ] **Step 4: Run** the gate plus `tests/contract tests/gates tests/privacy`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(api): media editor routes`.

### Task 6: Moderation — admin decisions and the report hold

**Files:**
- Create: `app/moderation/media.py`
- Modify:
  - `app/api/admin.py`: `kind: Literal["report","listing","media"]`; `GET /v1/admin/hub/media/{media_id}`; `POST /v1/admin/hub/media/{media_id}/decision`.
  - `app/contract/routes.py`: `PLATFORM_ADMIN_ROUTES` +2, with the count asserted.
  - `app/moderation/reports.py`: `_reportable` accepts `media` (an approved photo under a visible listing). A `child_safety` or `personal_info` report on media calls `media.hold`.
  - `app/moderation/vocab.py`: media rejection codes `identifiable_child`, `personal_info`, `not_relevant`, `low_quality`, `other`.
  - `web/src/admin/hub/Queue.tsx` and its test: a Media tab with the 5-minute preview, a checklist line "No identifiable student in the photo" / its BN twin, and approve or reject with a code.
- Test: `tests/moderation/test_media_moderation.py`

**Interfaces:**
- **`media.decide(session, store, lens: PlatformAdminLens, media_id, *, approve: bool, code: str | None, now) -> ListingMedia`:**
  - Applies only to `pending_review` or `held`.
  - **Approve:** mint `public_key = secrets.token_hex(16)`; `copy_variants` staged→`public/{key}/` and staged→`archive/{id}/` (from `archive/` when held); set `position` to the next free slot; status `approved`; record the moderation event.
  - **Reject:** status `rejected` with the code; enqueue deletes of `staged/`, `archive/` and `public/`; invalidate.
- **`media.hold(session, media_id, now) -> None`:** in the reporting transaction, set status `held`, clear `public_key`, enqueue a delete of `public/{old}/`, and enqueue invalidation paths `/m/{old}/*` plus the owner (and batch) page paths from `invalidation.owner_paths` / `batch_paths`.
- **Admin GET:** returns preview URLs from `presign_get` for the three variants, alt text, owner `public_name`, the batch `public_title`, the report count, and nothing about the uploader's account.

- [ ] **Step 1: Write failing tests:**
  - `test_approve_copies_to_public_and_archive_and_sets_key`;
  - `test_reject_enqueues_all_deletes`;
  - `test_child_safety_report_holds_photo_in_same_transaction` (Review Focus 3: roll back the report and the photo is still approved; commit and it is `held` with outbox rows);
  - `test_other_report_reasons_do_not_hold`;
  - `test_restore_from_hold_uses_fresh_key`;
  - `test_admin_preview_carries_no_account_fields`;
  - `test_decision_on_approved_or_rejected_is_conflict`.
  - Web: `media tab approves and rejects`, `preview images load from presigned URLs`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the gate plus `tests/moderation tests/contract tests/hub`, and `cd web && npm run check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(moderation): approve, reject and hold hub photos`.

### Task 7: Photos on public pages

**Files:**
- Modify:
  - `app/hub/public/views.py`: `HubImage{media_id: UUID, src: str, srcset: str, width: int, height: int, alt: str}`, registered. `HubOwnerPage.images` and `HubBatchPage.images` are `list[HubImage]`.
  - `app/hub/public/queries.py`: read `hub_public_media`, ordered by `position`, owner-level images on the owner page and batch images on the batch page.
  - `app/hub/listings/preview.py`: the preview shows the owner's `approved` and `pending_review` photos, the latter through presigned GETs and marked "Awaiting review" / BN twin.
  - `templates/owner.html` and `batch.html`: `<img>` with `src`, `srcset`, `sizes`, `width`, `height`, `alt` and `loading="lazy"`, plus a per-photo report link `kind=media&id={media_id}`.
  - `hub.css`: a gallery grid with no inline style.
  - The JSON-LD gains `image`, the first image's 960 URL.
  - `tests/privacy/canary.py`: the world gains a pending, a rejected and a held photo with canary alt text, plus an approved photo.
- Test: `tests/hub/test_public_media.py`, `tests/privacy/test_hub_canary.py` (the walked-body count unchanged; new probes)

**Interfaces:**
- Consumes: `hub_public_media` (Task 1).
- Produces: image URLs that are exactly `/m/{public_key}/{w}.webp`, using only widths present in `listing_media.widths` (Task 1 column, set by Task 4's `complete` from `result.json`).

- [ ] **Step 1: Write failing tests:**
  - `test_owner_and_batch_pages_show_only_approved_photos_in_order`;
  - `test_img_tags_have_dimensions_alt_and_srcset_from_stored_widths`;
  - `test_locale_picks_alt_with_fallback`;
  - `test_photo_report_link`;
  - `test_page_csp_unchanged_and_no_inline_style`;
  - `test_canary_alt_of_unapproved_photos_never_public`;
  - `test_preview_marks_pending_photos`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the gate plus `tests/hub tests/privacy tests/contract`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hub): moderated photos on public pages`.

### Task 8: Deletion and takedown wiring

**Files:**
- Modify:
  - `app/governance/deletion.py`: a solo-owner deletion first reads every media row's prefixes and approved keys, enqueues object deletes and `/m/{key}/*` invalidations, then hard-deletes the rows.
  - `app/hub/listings/hide.py` and `batches.py`: a retired batch's approved photos stay rows but leave the page through the view (Deviation 4). Only the existing page invalidation is enqueued.
- Test: `tests/governance/test_media_deletion.py`

- [ ] **Step 1: Write failing tests:**
  - `test_solo_owner_deletion_removes_media_rows_and_enqueues_objects` (Review Focus 5);
  - `test_centre_media_survive_manager_deletion`;
  - `test_retired_batch_photos_leave_page_without_object_deletes`;
  - `test_every_enqueued_prefix_matches_the_check_shapes`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the gate plus `tests/governance tests/hub tests/contract`, then regenerate the privacy policy. Expected: PASS.
- [ ] **Step 5: Commit** `feat(governance): delete photo objects with their owner`.

### Task 9: Web editor photos

**Files:**
- Create: `web/src/features/teacher/hub/Photos.tsx` and its tests
- Modify: `Listing.tsx` and `BatchListings.tsx` (a Photos section each), the strings via `node scripts/sync-strings.mjs`

**Interfaces:**
- `<input type="file" accept="image/jpeg,image/png,image/webp">` feeds the upload flow:
  1. Check type and size client-side (format only; the server decides).
  2. `POST /v1/hub/media/uploads`.
  3. A multipart `fetch` to the ticket `url` with `fields` and then the file.
  4. Poll `POST …/complete` every 2 s for up to 60 s while it answers `MEDIA_NOT_UPLOADED`.
  5. Show "Awaiting review".
- Alt text EN/BN is required before `complete`.
- Reorder with up and down buttons, then `PUT order`.
- Delete with a confirmation.
- The quota shows from the server's list length, as "4 of 12".

- [ ] **Step 1: Write failing tests:**
  - `uploads through the presigned form and shows awaiting review`;
  - `retries complete while not uploaded, stops at 60s with retry`;
  - `requires both alt texts`;
  - `shows server error messages for the five codes`;
  - `reorder sends ids in order`.
- [ ] **Step 2: Run** `cd web && npm run check`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `cd web && npm run check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(web): upload and manage hub photos`.

### Task 10: Android editor photos

**Files:**
- Create: `android/…/feature/hubmedia/{HubMediaApi.kt, HubMediaViewModel.kt, ui/HubPhotosScreen.kt}` and tests
- Modify: `HubRoutes.kt` (a destination plus every action wired), the listing and batch screens (an entry row), `values/` and `values-bn/` strings, `MessageKeys.kt`

**Interfaces:**
- `ActivityResultContracts.PickVisualMedia(ImageOnly)` needs no permission, and the manifest-allowlist gate stays unchanged.
- The content resolver gives the type and size; a file over 8 MB is refused client-side with the server's message key.
- The OkHttp multipart POST to the ticket URL uses the fields first and the file last.
- The `complete` polling, alt text, order and delete behave exactly as on web.
- The ViewModel state machine covers idle, picking, uploading, waiting_review, failed(retryable), and done.

- [ ] **Step 1: Write failing tests:**
  - ViewModel: `upload success`, `not uploaded then success`, `unreadable`, `limit reached`, `network failure keeps alt text and offers retry`.
  - `HubPhotosRouteTest` drives the real route with a MockEngine for both API and S3, asserting the multipart field order.
  - `ManifestGateTest` is unchanged (no new permission).
- [ ] **Step 2: Run** `make android`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make android && make android-quality`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(android): upload and manage hub photos with the photo picker`.

### Task 11: Deploy, smoke and release deliverables

**Files:**
- Modify:
  - `deploy/smoke.py` `--hub`: also `GET {site}/m/does-not-exist/320.webp` returns 403 or 404 with `nosniff`, proving the behaviour routes to the bucket and serves nothing unapproved.
  - `deploy.yml`: the Lambda code update from Task 3 runs before the release.
  - `docs/legal/README.md` Data Safety delta: photos uploaded by teachers, shown publicly after moderation, EXIF and location removed, deleted with the account.
  - `docs/legal/PRIVACY.md` (regenerated).
  - The Families user-content declaration note.
  - `infra/README.md`: the manual steps (bootstrap re-apply; the moderation checklist line).
  - `site` copy: the "Private by design" paragraph says photos are reviewed before they appear.
- Test: `tests/gates/test_deploy_workflow.py` (`test_deploy_updates_image_lambda_before_release`, `test_hub_smoke_checks_media_behaviour`), `site/test/build.test.mjs` (both twins)

- [ ] **Step 1: Write failing tests.**
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make check` (the full gate, once). Expected: every target green, including `lambda-test`.
- [ ] **Step 5: Commit** `feat(deploy): ship the image Lambda, smoke /m/*, and photo release deliverables`.
