# Smoke Test Results: Unique usernames

## Status: NOT RUN

Nothing was deployed, by the person's decision ("Record, don't deploy
(Recommended)"), so there was nothing to smoke. Every row below is **not yet
checked**.

The rows fall into two groups:

- **§ 1 (automated)**: `deploy/smoke.py` runs these when the person
  dispatches the staging deploy.
- **§ 2 and § 3 (manual)**: nothing automated discharges these. The person
  checks them by hand on staging after that deploy.

team.md (Deployment): "A deploy is not done until smoke passes." This intent
is therefore not done on staging until § 1 passes. It is not verified until
§ 2 and § 3 are recorded.

---

## 1. The automated smoke set (`deploy/smoke.py`, run by `deploy.yml`)

Command, from the step "Smoke through CloudFront":

```
python3 deploy/smoke.py <api-url from SSM> --attempts 18 --interval 10 [--sign-in-phone <SHIKKHOKPLUS_SMOKE_PHONE>]
```

| # | Check | Pass condition | Runs on staging when | Result |
|---|---|---|---|---|
| S1 | `GET /health` through CloudFront | HTTP 200, within 18 attempts 10 s apart | always | not yet checked |
| S2 | Database connectivity | `"database": "ok"` | always | not yet checked |
| S3 | Schema at this commit's head | `"migration_revision"` equals the head computed from `migrations/versions`, which is **`0038`** on the merged tree | always | not yet checked |
| S4 | Sign-in end to end: `POST /v1/auth/otp`, read the code from `GET /staging/last-otp`, `POST /v1/auth/verify`, then `GET /v1/me` with the issued token, expecting a `lenses` list | each call succeeds and a token is issued | only when `SHIKKHOKPLUS_STAGING_OUTBOX=1` **and** `SHIKKHOKPLUS_SMOKE_PHONE` is set | not yet checked. **See the defect below** |

A smoke failure triggers the automatic tag rollback (`deployment-log.md`
§ 6a). The `web`, `site` and `admin` jobs run their own smokes on the static
clients after the API release.

**Defect in S4 (pre-existing, not introduced by this intent, and it affects
this deploy).** S4 expects `POST /v1/auth/verify` to return an
`access_token`. Since revision 0032 (2026-11-08, PR #74), verify never signs
anyone in. It returns `password_setup_token` (`app/api/auth.py`,
`verify_code`). `smoke.py`'s sign-in path was written on 2026-11-07 and has
not been updated since. Its gate test, `tests/gates/test_smoke_sign_in.py`,
runs against a fake server that still returns `access_token` from verify, so
CI stays green.

Consequence: if staging has both outbox variables set, S4 fails with
"verification returned no access token", and the deploy rolls itself back.
If they are not set, S4 is skipped and the smoke is health only (S1–S3).

Before dispatching, the person should check those two variables in the
`staging` GitHub environment. This stage did not read them. The variables
are repository configuration, and this stage contacts nothing.

The durable fix is to make S4 sign in through `POST /v1/auth/password` with
`login`. That fix is outside this stage's write scope.

team.md's smoke set also names "one read of a fee cycle". `smoke.py`'s own
docstring says that read needs seeded data and **is not automated**.

## 2. This intent's additions: manual checks on staging

**Nothing automated discharges these.** They exercise the deployed build
through the real public path. The unit and integration suites already prove
the behaviour against PostgreSQL 16 in CI; what these add is evidence that
the staging release serves it.

Use a staging account created for the check, never a real person's data.
team.md forbids copying child-identifying production data into any tool
context.

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| M1 | Username sign-up (U1 FR1/FR2, U3, U4) | In the web client at `/ui/` and in the Android app: sign up with a new username plus a phone, then plus an email. Verify the code, then set a password | Account created. `GET /v1/me` shows the username and `username_required: false` | not yet checked |
| M2 | One-field sign-in (FR4) | Sign in three times through `POST /v1/auth/password` with `login` = the username, then the phone, then the email, using the same password. Repeat once with different letter case in the username | All four sign in. A wrong password gives the same refusal for all three forms | not yet checked |
| M3 | Availability lookup | `POST /v1/accounts/username-availability` (public) and `POST /v1/me/username-availability` (signed in), with a free name, a taken name, an invalid shape (`ab`, a phone-like name, Bangla script) and a reserved name | Free, unavailable, invalid and reserved answers respectively. A 429 `auth.lookup.too_many` after the per-IP hourly ceiling (30) | not yet checked |
| M4 | Choose-username gate (existing accounts) | Sign in with an account that existed before 0038, by phone or email | `GET /v1/me` shows `username_required: true`. Web and Android show the choose-username gate first, before any lens screen. After `PUT /v1/me/username`, the gate clears | not yet checked |
| M5 | Username change and hold | `PUT /v1/me/username` to a new name. Then try to claim the old name from a second account | Rename succeeds. The old name is held (unavailable) for the cooling-off period | not yet checked |
| M6 | Contacts: add, replace, remove (U2) | `POST /v1/me/contact`, then `/v1/me/contact/verify` to add an email to a phone-only account. Then replace it. Then try `POST /v1/me/contact/remove` on the last remaining contact | Add and replace succeed after verification. Removing the last verified contact is refused | not yet checked |
| M7 | Teacher-recorded email and invitation matching (U2 FR6) | As a teacher, record a student and a guardian email (`POST`/`PATCH /v1/students`). As a centre manager, invite a member by email. Then sign up or add that email on another account | The seat or invitation links to the account that verified the email. `GET /v1/accounts/already-added` reports the match | not yet checked |
| M8 | Username is owner-private (privacy gate) | As a teacher, read the batch roster and the student detail for M7's student | No `username` field anywhere in a teacher-lens response | not yet checked |

**Rollback rule tied to M7** (U2 NFR7.3): creating an email-only centre
invitation on staging closes the plain tag-rollback window there
(`deployment-log.md` § 6a). Do M7 last, after the release is accepted.

## 3. Deferred staging measurements from Build and Test

All are **not yet checked**, and for each one **nothing automated discharges
it**. Each is a manual timed run whose figure goes in the PR or here. Run
constraints come from the U2 run plan:

- no ceiling override (the ceilings are module constants in
  `app/auth/ceilings.py`);
- one source host on one /64;
- separate clock hours;
- no other OTP, sign-up or lookup traffic during the run.

| Target | Figure required | How | Result |
|---|---|---|---|
| NFR8 / U1 NFR8.1 | Both availability lookups ≤ 300 ms at p95 | Through CloudFront: 25 public lookups in one clock hour, 25 authenticated in the next (stays under `un_lk_ip_hour` 30). Mix of available, unavailable, invalid and reserved. Record the p95 of each set | not yet checked |
| U1 NFR1.2 | Medians of unknown-username, password-less-account and wrong-password sign-ins within 10% of each other | 20 sign-ins per case, over different usernames so no ceiling refuses | not yet checked |
| U1 NFR7.2 | Migration `0038` ≤ 10 s on staging | The host log carries no timestamps (`deployment-log.md` § 5). Read it from journal or docker timestamps on the new host, or with a timed rehearsal on a restored snapshot | not yet checked |
| U1 NFR7.4 | The migration is read from the deploy's own logged step | The same reading as U1 NFR7.2 | not yet checked |
| U2 NFR7.2 | Migration `0037` ≤ 10 s on staging | The same method as U1 NFR7.2 | not yet checked |
| U2 NFR8.1 | `GET /v1/accounts/already-added` ≤ 300 ms at p95, email form and phone form separately | 25 samples per form, in different clock hours. Any 429 voids that form's set | not yet checked |
| U2 NFR8.2 | U2 writes ≤ 500 ms at p95: `POST`/`PATCH /v1/students` with both emails, `POST /v1/centre/members` by email (100 requests each at ≤ 2 rps). Contact replace-verify and remove: max of 8 samples ≤ 500 ms | U2 run plan, hours 3 and 4 | not yet checked |
| U2 NFR8.7 | Each matcher and lookup statement ≤ 25 ms (`EXPLAIN (ANALYZE, BUFFERS)` execution time) | On staging, or on local PostgreSQL 16 seeded to design-point volume. Paste the plans and timings into the PR | not yet checked |
| U2 NFR8.6 | `match_contact` adds ≤ 50 ms to the verify transaction | Sum of the NFR8.7 statement timings | not yet checked |
| U2 NFR7.3 | Rollback rule on the release checklist | Checked off when the person accepts the rule in `deployment-log.md` § 6a | not yet checked |

These have **no owning stage in this plan** and are listed only for
completeness. They are manual pilot checks, and nothing automated discharges
them:

- U3 and U4 NFR8.4 low-end-device hint latency;
- FR11.2 Bangla layout (U3: 14 rows, U4: 20 rows in
  `docs/delivery/bangla-layout-check.md`).

## Sources

- `deploy/smoke.py` (`migration_head`, `sign_in`, `main`) and
  `tests/gates/test_smoke_sign_in.py`.
- `.github/workflows/deploy.yml`, step "Smoke through CloudFront".
- `app/api/auth.py` (`verify_code` returns `password_setup_token`;
  `POST /v1/auth/password`) and `app/schemas/auth.py` (`VerifyResponse`).
- `app/api/accounts.py` (`/accounts/username-availability`,
  `/accounts/already-added`) and `app/api/me.py` (`/me/username-availability`,
  `PUT /me/username`, `username_required`).
- `app/api/credentials.py` (`/me/contact`, `/contact/verify`,
  `/contact/remove`).
- `migrations/versions/0038_usernames.py` (the head).
- `construction/build-and-test/build-and-test-summary.md` (§ "Staging
  readings") and `performance-test-instructions.md` § 2.
- `aidlc/spaces/default/memory/team.md` (Deployment: the smoke set and the
  smoke-failure rollback) and `project.md` (a manual verifier is stated as not
  automated).

## Assumptions & Open Questions

- **Assumption**: staging has seed-able test accounts, or the person creates
  them during M1. The staging seeder Lambda exists only when `enable_seeder`
  is on.
- **Open**: whether `SHIKKHOKPLUS_STAGING_OUTBOX` and
  `SHIKKHOKPLUS_SMOKE_PHONE` are set in the `staging` environment. If both
  are, S4 will fail on the pre-existing defect above, and the deploy will roll
  back.
- **Open**: whether the person wants the S4 fix as its own small change
  before this deploy. The fix makes the sign-in smoke use password sign-in and
  updates the gate test's fake server.
