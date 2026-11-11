# Security review: ShikkhokPlus application and backend

Date: 2026-11-11. Reviewer: DevSecOps specialist (analysis only, no code changed).
Scope: `app/`, `migrations/`, `web/src`, `infra/`, `Dockerfile`, compose files, `.github/workflows/`.
Commit reviewed: `7547918` (HTML verification email, #77).

## 1. Posture summary

The codebase is mature. Many of its controls are mechanical rather than left to review, and most of
the items on a generic checklist are already handled. I checked each of the following in code and
none of them is a finding:

- **Tokens.** The JWT algorithm is pinned, keys are found by `kid`, `iss` and `aud` are checked, and
  expiry is compared against the server clock (`app/auth/tokens.py:304-349`). Scoped tokens require
  an audience (`:380-412`). Refresh tokens are stored as hashes and rotate with reuse detection and a
  60-second grace window. The whole token family is revoked on logout, on password change and on
  password setup (`app/accounts/passwords.py:164`, `:281`).
- **OTP.** Codes come from `secrets` and are stored as HMAC under a key held outside the database.
  Each code allows 5 attempts under `FOR UPDATE`, belongs to one purpose, and both branches do the
  same work. Responses are identical for known and unknown numbers (`app/auth/otp.py:150-345`). The
  network-wide failed-verify ceilings are in place (`app/api/auth.py:259-298`).
- **Passwords and MFA.** Passwords use scrypt with N=2^14, r=8, p=5, and a dummy hash keeps the
  timing equal (`app/accounts/passwords.py:207-212`). TOTP refuses a reused step and the factor locks
  after 5 wrong codes (`app/auth/totp.py:84-112`, `app/auth/mfa.py:61`).
- **Admin.** An administrator needs an allowlisted identifier, the edge secret (compared in constant
  time), a CIDR allowlist and a confirmed MFA factor (`app/authz/admin.py`, `app/api/deps.py:73-78`).
- **Authorization.** Lens dependencies return the value each query is scoped by, and a
  route-enumeration gate checks that every route has one. I sampled 12 routes that take path
  parameters: payroll adjustments, notification detail, exam examiner, the workspace header, the
  deletion routes, and the fee and marks reads. Every one scopes through the lens or through the
  account id, and **I found no IDOR**. Row-level security exists on `profile` only, which matches the
  Mandated rule. Every other table depends on the lens layer alone (see Section 4).
- **Database grants.** The app role is `shikkhok_app` and is not the owner. `ledger_entry` and
  `auth_audit_log` are append-only for that role (`migrations/versions/0015...py:118-124`).
- **HTTP.** CORS allows exact origins only, with no wildcard and no credentials (`app/web_origins.py`).
  nginx overwrites the client IP from `CloudFront-Viewer-Address`, and Uvicorn runs with
  `--no-proxy-headers` and no access log. The origin secret is checked, ingress is limited to the
  CloudFront prefix list, and nginx keeps its default 1 MB body cap.
- **Email.** The new HTML verification email escapes the code and the site URL, and the site URL
  must be a bare https origin (`app/gateway/email_html.py:263-301`). Header injection is not
  possible: the address pattern `[^@\s]+@...` excludes CR/LF (`app/accounts/identifier.py:41`), and
  `email.message.EmailMessage` rejects line breaks in headers.
- **Infrastructure and supply chain.** Every S3 bucket has its public access block and a TLS-only
  policy. RDS is encrypted, private and protected from deletion. The container runs as a non-root
  user from a digest-pinned base, built from a hashed lockfile. Every action is pinned to a SHA,
  every workflow has a `permissions:` block, OIDC is scoped per environment, and Gitleaks, pip-audit,
  npm audit, osv-scanner and the ECR scan release gates are all in place.

**What remains is mostly availability abuse and gaps between controls.** The rate-limit design
protects the SMS budget well, but it can be turned against legitimate users (SEC-1, SEC-4, SEC-5).
Account deletion is the one irreversible action with no step-up check (SEC-2). Unexpected database
errors are not redacted on their way to the logs (SEC-3). I found no Critical or High finding.

## 2. Findings

| ID | Sev | Title | Evidence | Scenario | Recommended fix | Effort | Confidence |
|---|---|---|---|---|---|---|---|
| SEC-1 | Medium | Password failures fill the global failed-verify ceiling, which then refuses every sign-in in the product | `app/auth/ceilings.py:231-233` (global 300/h), `:641-668` (`check_password_allowed` calls `check_verify_allowed`), `:670-686` and `:606-626` (each password failure increments the global scope); `app/accounts/passwords.py:191-218`; `deploy/docker-compose.staging.yml:40` | Since 0032, password is the primary sign-in, and every wrong password, from anyone, counts toward one product-wide total of 300 per hour. An attacker using about 15 IPv4 /24s (20 failures each) or 5 IPv6 /48s (60 each) reaches 300 in minutes. Every password sign-in, OTP verify and contact verify is then refused until the hour turns, and repeating the attack each hour keeps sign-in down. Real users' typos also count, so the ceiling can trip at normal peak load with no attacker. The C-20 trade-off of an outage over a guessing run was made for six-digit codes. It does not carry over to passwords, which already have their own per-identifier ceiling. | Give password failures a separate global scope that alerts but does not refuse, and keep the per-identifier, per-/64 and per-/48 refusals. If a hard global stop is still wanted, apply it only to prefixes with no successful sign-in in the last 30 days. | S | Confirmed (code path); attack cost plausible |
| SEC-2 | Medium | `DELETE /v1/me` destroys the account with only a bearer token: no step-up check, and MFA is bypassed | `app/api/deletion.py:622-659` (only `token_subject`). Compare `:567-596`, where the external route requires the TOTP for MFA accounts so that "a SIM swap alone cannot destroy an account" | Someone holding a 15-minute access token (a borrowed phone that is signed in, the PWA's `localStorage`, a leaked log) can permanently delete a teacher account with all its batches and fee records, even when the owner turned MFA on. The password-change path asks for the current password for exactly this case (`app/accounts/passwords.py:243-246`), and deletion is the one action that cannot be recovered. | Require the current password, plus a TOTP or recovery code when an MFA factor is confirmed, in the `DELETE /v1/me` body. Alternatively, require an `auth_time` claim less than 5 minutes old. Both clients need the matching prompt. | M | Confirmed |
| SEC-3 | Medium | Unexpected database errors return 500 and write the bound SQL parameters to CloudWatch | `app/db/session.py:82-105` (no `hide_parameters=True`); `app/request_scope.py:80-95` renders only Operational, Integrity and PoolTimeout errors; `:165-178` logs `exc_info`; trigger at `app/schemas/marks.py:146,170` (`total_marks: int = Field(ge=1)` with no upper bound) against `app/db/models.py:2331` (`Integer`); `app/marks/exams.py:196-210` checks only `< 1`; batch jobs at `app/fees/generation.py:448` | A teacher, or a script holding a teacher token, sends `POST /v1/batches/{id}/exams` with `total_marks=3000000000`. The int4 overflow raises `DataError`, which no handler maps. The client gets a 500, and the traceback logged includes `[SQL: ...] [parameters: {...}]`. Any unmapped `DataError` or `ProgrammingError` on a statement that carries names, phone numbers or marks writes them to logs, which breaks the Deployment rule that error logs never carry a phone number, OTP or token. | Set `hide_parameters=True` on `create_engine`. Map `DataError` to a 400 `ValidationError` envelope. Add `le=` bounds to `total_marks`, and add a gate test that every `int` field on a request model has an upper bound. | S | Confirmed (mechanism); PII content plausible |
| SEC-4 | Medium | The unauthenticated already-added lookup uses up the victim number's daily signup allowance | `app/api/accounts.py:278-282` (lookup calls `check_and_consume_signup`); `app/auth/ceilings.py:136` (`SIGNUP_PER_NUMBER_DAILY = 3`), `:549-579`; the signup route spends the same scope at `app/api/accounts.py:189-193` | Three anonymous `GET /v1/accounts/already-added?phone=<victim>` requests stop that number from signing up for 24 hours. The likely target is a student or guardian a teacher has just enrolled, which blocks the D1 acceptance flow. From one IP, 10 numbers an hour can be blocked. The Android form makes the same lookup as it renders, so one honest retry after a failed send can exhaust the allowance. | Give the lookup its own scope, per IP and per /48 only, or a separate per-number counter with a higher limit. Stop it from spending signup's per-number allowance. | S | Confirmed |
| SEC-5 | Low | Ceilings are checked, then recorded later, so concurrent bursts exceed them and hold database connections during scrypt | `app/auth/ceilings.py:589-604` and `:777-815` (`_peek` is a plain SELECT; `_increment` runs after the work); `app/accounts/passwords.py:191-216`; pool of 8+4 per worker at `app/db/session.py:89-91` | N concurrent `POST /v1/auth/password` requests all read a count below 10 or 20 before any increment lands, so the per-identifier and per-/64 limits are exceeded by roughly the size of the burst. Each request holds a pooled connection through about 16 MiB of scrypt work. With 24 in flight, every other API request waits `pool_timeout` and gets a 503. | Increment first with `UPSERT ... RETURNING count`, refuse when the count is over the limit, and refund it on success. Cap concurrent scrypt calls per worker with a semaphore. Add nginx `limit_req` on `/v1/auth/`. | M | Plausible |
| SEC-6 | Low | The external deletion route's verify step skips the C-20 network-wide ceilings and the dead-code cool-off | `app/api/deletion.py:567-573`; compare `app/api/auth.py:259-298` | Codes are guessed here without counting against `/64`, `/48` or the global total, and `record_dead_code` is never called. The per-code limit of 5 and the deletion issue ceilings still bound this to about 25 guesses per number per day, so the practical odds are small. The danger is inconsistency: the route that destroys data has the weakest guessing controls. | Wrap the verify in `check_verify_allowed`, `record_verify_failure` and `record_dead_code`, as `/v1/auth/verify` does. | S | Confirmed |
| SEC-7 | Low | The API CloudFront behavior has no response-headers policy, so the deletion HTML page can be framed | `infra/modules/cdn/main.tf:245-262` (default behavior: no `response_headers_policy_id`; only web paths get one, at `web.tf:132`); `app/api/deletion.py:358-369` (no headers set) | `/account-deletion` is a state-changing HTML form served without `frame-ancestors`, `X-Frame-Options`, HSTS or `nosniff`. A phishing page can frame the real page and talk a victim into entering their code, so the genuine origin lends it credibility. API JSON responses also lack `nosniff` and HSTS. | Attach a response-headers policy to the default behavior: HSTS, `nosniff`, `DENY`, and a CSP of `default-src 'none'; form-action 'self'; frame-ancestors 'none'`. Or set the same headers on the `HTMLResponse` in the app. | S | Confirmed |
| SEC-8 | Low | The PWA keeps the 30-day refresh token in `localStorage` | `web/src/api/tokens.ts:3-10`, `:77-85` | Any script that runs on the origin can steal the refresh token and keep access for up to 30 days. This is mitigated, not removed: `script-src 'self'` (`web/vite.config.ts:67`) and no `dangerouslySetInnerHTML` or `innerHTML` sinks in `web/src`. Already listed as follow-up work in `web/README.md`. | Move the refresh token into an `HttpOnly; Secure; SameSite=Strict` cookie scoped to `Path=/v1/auth`, and keep the access token in memory only. | M | Confirmed (design) |
| SEC-9 | Low | The OIDC `sub` pattern uses `@*` wildcards where exact IDs could be pinned | `infra/bootstrap/main.tf:208-211`, `:340-344` | In `StringLike`, `*` also matches `/` and `:`, so the condition depends on GitHub never allowing an environment name containing `/<repo>@...:environment:production-infra`. Exploiting it would also need admin rights on another repository of the same owner. | The numeric owner and repo IDs are fixed and known (see the CloudTrail example in the comment). Put them in variables and use `StringEquals` on the exact `sub`. | S | Plausible |
| SEC-10 | Low | The database URL does not verify the server certificate | `infra/modules/app/secrets.tf:61`, `:75` (no `sslmode`; psycopg defaults to `prefer`) | RDS PG16 enforces TLS, but the client never checks the certificate. A man-in-the-middle inside the VPC could read credentials and children's data in transit. | Add `?sslmode=verify-full&sslrootcert=<RDS global bundle>` and bake the bundle into the image. | S | Confirmed |
| SEC-11 | Low | The runtime image ships the dev toolchain (pytest, mypy, ruff, pip-audit) | `Dockerfile` (lockfile note: the lock is compiled `--extra dev --extra api` and copied whole) | The packages are not needed to serve requests, and they widen what a process inside the container can use. The reason is documented and accepted, but it is still surface. | Compile an api-only lock alongside the dev lock, and add a CI check that the two agree on every shared pin. | M | Confirmed |

## 3. Top 5 fixes, ranked by risk reduction per unit of effort

1. **SEC-3: redact database errors (S).** One engine flag, one exception mapping and one schema bound
   close a path from user input to PII in logs.
   *Acceptance:* a test sends `total_marks = 2**31` to `POST /v1/batches/{id}/exams` and gets a 400
   `ErrorEnvelope`, not a 500. A `caplog` test that forces a `DataError` asserts the log has no
   `parameters:` substring. `build_engine().hide_parameters` is asserted `True`.
2. **SEC-1: stop password typos from shutting down sign-in for everyone (S).** This removes a
   cheap, repeatable outage.
   *Acceptance:* in a test, 300 password failures from 15 distinct /24s are followed by a correct
   OTP verify and a correct password sign-in from a fresh prefix, and both succeed. The global alert
   still fires exactly once. The per-identifier refusal at 10 an hour still holds.
3. **SEC-4: give the already-added lookup its own scope (S).** This closes an anonymous, targeted
   way to block onboarding.
   *Acceptance:* in a test, five `GET /v1/accounts/already-added?phone=X` calls from IP A are
   followed by `POST /v1/accounts/signup` for X from IP B, and the signup succeeds. The 11th lookup
   from IP A within an hour is refused.
4. **SEC-7: security headers on the API distribution (S).** This removes the framing risk on the
   only HTML page that changes state, and gives the API HSTS and `nosniff`.
   *Acceptance:* a gate test in `tests/gates/` parses `infra/modules/cdn/main.tf` and asserts that
   `default_cache_behavior` has a `response_headers_policy_id`. An app test asserts that
   `GET /account-deletion` returns `X-Frame-Options: DENY` and a CSP containing
   `frame-ancestors 'none'`. Post-deploy smoke checks that `curl -I` on the deletion page shows
   `Strict-Transport-Security`.
5. **SEC-2: step-up check on in-app deletion (M).** This puts the only irreversible action behind
   the same factor the external route already requires.
   *Acceptance:* `DELETE /v1/me` without a password returns 400 `REAUTH_REQUIRED`. On an MFA
   account, the password without a TOTP returns 400 `MFA_CODE_REQUIRED`. The existing test that the
   in-app and external paths leave identical surviving row sets still passes. Calling it again after
   success with the same token still reports deleted (BR1.4).

## 4. Notes outside the table (accepted design, no action proposed)

- **Access tokens outlive revocation.** They remain valid for up to 15 minutes after logout, a
  password change or a family revocation, because there is no denylist. This matches BR4.2. SEC-2
  limits the worst use of that window.
- **Row-level security covers `profile` only.** Fee, marks and attendance isolation rests entirely
  on the lens layer and its route-enumeration gate. That is a deliberate choice, recorded in
  project.md. If defense in depth is wanted later, the cheapest next step is RLS on `ledger_entry`
  and `exam_mark`, keyed on owner.
- **Daily send budgets can be exhausted on purpose.** An attacker can use up the email (1,000 a day)
  and deletion SMS (50 a day) budgets. This is the documented money-over-availability trade-off. Keep
  watching the budget alerts.
