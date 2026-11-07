# ShikkhokPlus web

The web client: an installable PWA over the same `/v1` API the Android app
uses. Open it in a browser, or install it from the address bar (Chrome,
Edge) and it runs in its own window like a desktop app — with a side rail
on a wide window and the phone's bottom bar on a narrow one.

It follows `claude_design/` (tokens, payment-state chips, screen states)
and mirrors the Android app's behaviour screen for screen; where the two
could differ, the Android code was read and the web copies its rule.

## Run it

```bash
make up          # the API and Postgres, from the repo root
make web-dev     # http://localhost:5173, proxied to the API on :8000
```

The dev server proxies `/v1`, `/health` and `/staging` to the API, so it
is same-origin and needs no CORS. With `SHIKKHOKPLUS_STAGING_OUTBOX=1`
(the local default) the code for a number is at
`/staging/last-otp?phone=…`.

| Command               | What it does                                                                 |
| --------------------- | ---------------------------------------------------------------------------- |
| `npm run check`       | The whole gate, as CI runs it (`make web` from the root)                     |
| `npm run gen`         | Regenerate API types and string bundles (see below)                          |
| `npm run gen:icons`   | Re-render the PNG icons from `public/icons/mark.svg` (needs Playwright)      |
| `npm run build`       | Production build into `dist/`, with the service worker                       |
| `npm run dev:admin`   | The admin app on http://localhost:5174 (see [The admin app](#the-admin-app)) |
| `npm run build:admin` | The admin app's build into `dist-admin/`                                     |

## Deploying

`deploy.yml` does it, after the API release succeeds: it runs `make web`
with `WEB_BASE=/ui/`, uploads `dist/` to the environment's web bucket
under `ui/`, invalidates `/ui/*` and smokes the result through CloudFront.

Where it is served (`infra/modules/cdn/web.tf`): a private S3 bucket,
read only by the API's own CloudFront distribution through Origin Access
Control, on the paths `/ui` and `/ui/*`. So the UI and the API share one
origin -- the app calls `/v1` on the host it was loaded from, no CORS is
configured, and `SHIKKHOKPLUS_WEB_ORIGINS` stays unset. A CloudFront
Function serves `index.html` for client-side routes such as `/ui/dues`.

| Environment | Web client                                                                         |
| ----------- | ---------------------------------------------------------------------------------- |
| staging     | `https://app.shikkhokplus.<apex>/ui/` (also `https://api.shikkhokplus.<apex>/ui/`) |
| production  | `https://app.shikkhokplus-prod.<apex>/ui/`                                         |

`app.<zone>/` on its own redirects to `/ui/`. The hostname is the
`ui_subdomain` Terraform variable; empty serves the UI only at
`api.<zone>/ui/`.

Upload order matters and is in the workflow: hashed `assets/` first
(immutable), then `index.html`, `sw.js` and the manifest (`no-cache`),
then old assets are pruned -- so a tab that loaded the previous release a
moment ago still finds its files.

**First deploy after this change needs `infra/bootstrap` re-applied** (from a
laptop, as bootstrap always is): the infrastructure role gains the right
to create `shikkhokplus-*-web-*` buckets, and the deploy role gains the
upload, the invalidation and the three new SSM parameters.

To serve a build somewhere else entirely, build with
`VITE_API_BASE_URL=https://<api host>` and set
`SHIKKHOKPLUS_WEB_ORIGINS=https://<web origin>` on the API
(`app/web_origins.py`): exact `https` origins only.

## The admin app

The platform administrators' app is **a separate build** (`admin.html` →
`src/admin/main.tsx`, `npm run build:admin` → `dist-admin/`: `index.html`
plus hashed `assets/*`, base `/`). It is served at the root of its own
hostname, `https://admin.<zone>/`, which CloudFront restricts by IP and
which adds the `X-Admin-Edge` header the API requires on every admin
route; off that edge the API answers 404 and the app says it is not
available from here. The main app contains none of it: no admin route,
screen, string or API path, which `npm run check:bundles` asserts on both
builds after they are built (the admin build in turn carries no service
worker, manifest or main-app screen, and its CSP's `connect-src` is
exactly `'self'`). Admin strings are `src/admin/i18n/admin.{en,bn}.json`,
outside the main app's `src/i18n/web/` glob, added at start-up by
`src/admin/strings.ts`.

**Log-in** takes an SMS code and an authenticator code:

1. `POST /v1/admin/auth/otp` with the number; the answer is the same for
   any number, and only an allowlisted administrator's gets an SMS.
2. `POST /v1/admin/auth/verify` with the SMS code returns a five-minute
   challenge and the next step. If the challenge lapses on screen, log-in
   starts again from the number and says why.
3. First time (`enroll`): a QR code of the `otpauth://` URI, the key in
   groups of four with Copy, and on a phone an "Open in authenticator
   app" link; then a code from the app. The server then returns the
   session **and ten recovery codes, shown once**, with Copy all; the
   dashboard opens only after "I've saved them". Every other time
   (`verify`): a code from the app, or a recovery code instead.
   `POST /v1/admin/auth/mfa` answers a wrong code inline (the field keeps
   focus), and after five wrong codes locks for 15 minutes.

**The session** is one admin access token for an hour, with no refresh
token: kept in memory and in `sessionStorage` (survives a reload, gone
when the tab closes; never `localStorage`), shown in the header as
"Signed in until 14:32" (Dhaka time). Every admin call sends it as a
bearer token to the same origin (`src/admin/client.ts`). A 401 from any
call, or the hour running out with the tab open, ends the session and
returns to log-in, which afterwards goes back to the screen the
administrator was on. A 403 means the number is not, or no longer, an
administrator, and offers Log out. App tokens are not accepted on admin
routes.

What the screens show is unchanged and stays inside the administrator
boundary [TC-14] [D-6]: teacher and centre names, students and guardians
only as counts or as role plus an opaque reference
(`Student · #A1B2C3D4E5`); `screens/mappers.ts` drops a name that arrives
for anyone who is not a teacher or centre member, and a test holds it to
that. Screens are one lazy chunk, fetched after log-in.

**The QR code** is drawn by `qrcode-generator` **2.0.4** (MIT, no
dependencies, published 2025-08-07; about 21 kB minified, 8 kB gzipped), as
an SVG, black on white with a four-module quiet zone in every theme, at a
whole number of pixels per module. The component (`src/ui/QrCode.tsx`) and
the rest of the setup screen's pieces (`src/ui/authenticator.tsx`: the key
in groups of four with Copy, "Open in authenticator app", the recovery-code
list with Copy all) are shared with the main app's two-step verification,
each app passing its own strings. In the main app the encoder loads only
with the settings screen's lazy chunk, which `check:bundles` asserts.

**Running it locally.** The API refuses admin routes without the edge
header and from a network not on its list, so run the API with both set,
then the admin dev server with the same secret:

```bash
# the API (make up, or uvicorn) with:
SHIKKHOKPLUS_ADMIN_EDGE_SECRET=dev-edge-secret
SHIKKHOKPLUS_ADMIN_ALLOWED_CIDRS=127.0.0.1/32,::1/128
SHIKKHOKPLUS_PLATFORM_ADMIN_PHONES=+8801XXXXXXXXX   # your number
# then:
SHIKKHOKPLUS_ADMIN_EDGE_SECRET=dev-edge-secret npm run dev:admin
```

`npm run dev:admin` serves the admin app at http://localhost:5174 and
proxies `/v1/admin` to `http://localhost:8000` (or `SHIKKHOKPLUS_API`),
adding `X-Admin-Edge` from `SHIKKHOKPLUS_ADMIN_EDGE_SECRET`, as the admin
CloudFront distribution does in a deployment. It warns at start-up when
the variable is unset. `npm run preview:admin` serves `dist-admin/`.

## Two-step verification

Optional for every account; the server says when to suggest it
(`recommended`: teachers and centre members) and when it cannot be turned
off (`required`). The client decides neither.

**Signing in.** `POST /v1/auth/verify` answers exactly as before for an
account without it. With it on, the answer carries no tokens but
`mfa_required`, a five-minute `mfa_challenge` and `mfa_expires_in`, and
the sign-in screen asks for the authenticator code (`features/auth/MfaStep.tsx`:
six digits, `inputmode="numeric"`, `autocomplete="one-time-code"`, checks
by itself after the sixth, as the SMS step does), or a recovery code
instead. `POST /v1/auth/mfa` returns the token pair, and **only then is
anything stored**. A wrong code is said inline (`mfa.code_wrong`; a wrong
recovery code in its own words); `mfa.locked` replaces the field with the
message and Start again; the challenge lapsing, on screen or as the
server's 401 `mfa.challenge_expired`, goes back to the number with a
notice. Both calls are anonymous, so that 401 never reaches token renewal
or sign-out: there is no session yet.

**Settings → Two-step verification** (`/settings/security`, lazy; entry
rows on More and Settings, with a "Recommended" label while it is
suggested and off): the status, "On since", recovery codes left (a
warning at two or fewer). **Turn on**: the QR code and the key with Copy,
"Open in authenticator app" on a phone, then the app's first code, then
ten recovery codes **shown once** with Copy all until "I've saved them"
(a reload or closing the tab asks first). **Turn off** with an
authenticator or recovery code, not offered when required. **New
recovery codes** with an authenticator code, shown once the same way.
Nothing is stored: the secret and the codes live in the screen's state.

**The home prompt.** For `recommended` and not `enabled`, the home screen
(Batches, Today, My classes) shows "Protect your account with two-step
verification" with Turn on, which opens the setup directly, and Not now.
Not now is a per-viewer convenience kept in `localStorage`
(`sp.mfa.prompt.dismissed`, a flag and nothing from the API); the
Settings label stays. Students and guardians are never prompted. The
status behind the label and the prompt is read once per session into a
small in-memory store (`features/account/security/status.ts`) and
forgotten at sign-out.

## Decisions worth knowing

- **Strings come from Android.** `src/i18n/generated/` is built from
  `android/src/main/res/values{,-bn}/strings.xml` and `MessageKeys.kt`;
  only a handful of web-only strings (`web_*`) live here. The bundles and
  the server's `message_key` list are checked in both languages by tests.
- **API types come from `openapi.json`.** `src/api/schema.d.ts` is
  generated; a contract change that breaks a screen fails `tsc`.
- **Fonts are Android's.** The merged Noto Sans + Noto Sans Bengali files,
  byte-identical, so both clients render the same glyphs.
- **`check:generated` keeps all three honest**: CI fails if any copy no
  longer matches its source, as the backend's schema-diff gate does.
- **Money is never a JS number** [TC-7]. `core/money.ts` keeps the wire
  string, fails loudly on a JSON number, refuses numeric coercion, and has
  no arithmetic. `parseFloat` is a lint error. Every figure on screen is
  one the server sent [TC-9].
- **The service worker caches the app shell only.** No API response is
  ever written to Cache Storage or any browser storage: children's data
  would sit unencrypted on what may be a shared computer, which the
  Android app avoids by encrypting its copies. Offline, the app opens and
  says that it needs a connection; it recovers by itself when back online.
- **Writes need a connection** [D-9]. There is no offline queue; a failed
  write says so and offers Try again.
- **Token renewal is serialised across tabs** with a Web Lock, because the
  server revokes the whole token family when a rotated-out refresh token
  is presented — two tabs refreshing at once would sign the person out.
- **One-tap approve only when the server says the payment matches** and
  the transaction ID is new; anything short, over or reused goes through
  the sheet, as `VerifyViewModel.approveAsReported` does.

## What is built

Every screen the Android app has, for every role.

| Role     | Screens                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Everyone | Sign in (with the authenticator step for accounts that have it), create account, two-step verification settings, role picker, invitations, inbox (unread count on More), help centre (my questions, ask a question, the thread; new replies counted on More), edit profile, delete account, More, Settings (language, theme, text size), install and update prompts                                                                                                                                            |
| Teacher  | Today (T1); batches, new batch, edit batch, schedule; a batch's Students (T7), Classes, Exams and Notices tabs; add student (T8), mark inactive, remove; record a class (T2) with attendance, plan, move and cancel; new and edit exam, marks entry (T3), publish, results and corrections; Dues (T5) with reminders; verify payments (T4) and the payment itself, including split payments and changing a decision; a student's fee history and progress; where students pay; collections and a batch's month |
| Student  | My batches (S1); a batch (S2) with classes, exams, notices and teacher; a class, an exam, its marksheet, a notice; progress and dashboard; fee history; send money (S3)                                                                                                                                                                                                                                                                                                                                        |
| Guardian | Children (G1); each child's batch and everything a student sees about it; progress (G3) with the trend; payments (G2); send money for one or several children; my children                                                                                                                                                                                                                                                                                                                                     |

**Every request says which app it is** (`api/platform.ts`):
`X-Client-Platform: web` and `X-Client-Version: <package.json version>`
(injected as `__APP_VERSION__`, trimmed to `[0-9A-Za-z.+-]{1,32}`), token
renewal included. The server records them at sign-in and refresh for the
admin overview's Android-versus-web figures. They name the build, not the
person or the browser.

**How it is organised.** Each area owns a directory and its own string
files: `features/teacher/{classes,exams,students,money}`,
`features/family/{batch,pay}`, `features/account/area` and
`features/help`. Every teacher
URL is in `features/teacher/paths.ts`; student and guardian screens are
written once with a reader (`'me'` or `'child'`, `features/family/reader.ts`)
and mounted under `/my/:seat` and `/child/:seat`. Every area screen loads
on first use (`core/lazy.tsx`), and React with the router is a separate
long-lived chunk.

## Follow-ups

- **Refresh token in an `HttpOnly` cookie.** It sits in `localStorage`
  today, protected by a strict CSP and no third-party script. A cookie
  needs the refresh route to read it from the cookie instead of the body.
- **Bangla layout check for web screens.** Screens were checked by
  screenshot in Bangla and English during development; the web screens
  are not yet in `docs/delivery/bangla-layout-check.md`.
- **Split the language bundles.** Both languages' strings ship in the entry
  chunk; loading only the active one would take about 50 kB off it.
- `npm audit` reports 0 issues in shipped packages and 12 low/moderate in
  the build toolchain (`typescript-eslint`'s `minimatch`, `workbox-build`'s
  `glob`); CI annotates them. ESLint 9 is out of support; moving to 10 is
  its own change.
