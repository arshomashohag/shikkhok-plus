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

| Command             | What it does                                                            |
| ------------------- | ----------------------------------------------------------------------- |
| `npm run check`     | The whole gate, as CI runs it (`make web` from the root)                |
| `npm run gen`       | Regenerate API types and string bundles (see below)                     |
| `npm run gen:icons` | Re-render the PNG icons from `public/icons/mark.svg` (needs Playwright) |
| `npm run build`     | Production build into `dist/`, with the service worker                  |

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
| Everyone | Sign in, create account, role picker, invitations, inbox (unread count on More), edit profile, delete account, More, Settings (language, theme, text size), install and update prompts                                                                                                                                                                                                                                                                                                                         |
| Teacher  | Today (T1); batches, new batch, edit batch, schedule; a batch's Students (T7), Classes, Exams and Notices tabs; add student (T8), mark inactive, remove; record a class (T2) with attendance, plan, move and cancel; new and edit exam, marks entry (T3), publish, results and corrections; Dues (T5) with reminders; verify payments (T4) and the payment itself, including split payments and changing a decision; a student's fee history and progress; where students pay; collections and a batch's month |
| Student  | My batches (S1); a batch (S2) with classes, exams, notices and teacher; a class, an exam, its marksheet, a notice; progress and dashboard; fee history; send money (S3)                                                                                                                                                                                                                                                                                                                                        |
| Guardian | Children (G1); each child's batch and everything a student sees about it; progress (G3) with the trend; payments (G2); send money for one or several children; my children                                                                                                                                                                                                                                                                                                                                     |

**How it is organised.** Each area owns a directory and its own string
files: `features/teacher/{classes,exams,students,money}`,
`features/family/{batch,pay}` and `features/account/area`. Every teacher
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
