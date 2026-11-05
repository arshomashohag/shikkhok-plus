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

The build is static files. Two ways to serve it:

1. **Same origin as the API** (simplest): serve `dist/` from the host that
   already fronts the API, with `index.html` as the fallback for unknown
   paths that are not `/v1`, `/health`, `/account-deletion` or `/staging`.
   Build with `VITE_API_BASE_URL` empty. No CORS is involved.
2. **Its own origin** (static host or CDN): build with
   `VITE_API_BASE_URL=https://<api host>` and set
   `SHIKKHOKPLUS_WEB_ORIGINS=https://<web origin>` on the API. That is the
   only thing that turns CORS on (`app/web_origins.py`): exact `https`
   origins only, a wildcard refuses to start.

Either way, serve `sw.js` with `Cache-Control: no-cache` so an update is
noticed, and everything under `assets/` as immutable.

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

| Role     | Screens                                                                                                                                                        |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Everyone | Sign in (phone + 6-digit code), create account, role picker, invitations, More, Settings (language, theme, text size), install, update prompt                  |
| Teacher  | Today (T1), Batches (T6), new batch, Single batch — Students tab (T7), Dues (T5), Verify payments with partial, carry/waive, reject and duplicate warning (T4) |
| Student  | My batches (S1)                                                                                                                                                |
| Guardian | Home with child switcher (G1)                                                                                                                                  |

Not yet on the web, and said so on screen where a tab exists: record a
class (T2), marks entry (T3), add student (T8), the Classes/Exams/Notices
tabs, reminders, student payment submission (S3), guardian payments and
progress, fee history, payment methods, profile edit, account deletion
and the inbox.

## Follow-ups

- **Refresh token in an `HttpOnly` cookie.** It sits in `localStorage`
  today, protected by a strict CSP and no third-party script. A cookie
  needs the refresh route to read it from the cookie instead of the body.
- **Bangla layout check for web screens.** Screens were checked by
  screenshot in Bangla and English during development; the web screens
  are not yet in `docs/delivery/bangla-layout-check.md`.
- **Split the language bundles.** Both languages ship in the main chunk
  (~145 kB gzipped in all); loading only the active one would halve the
  strings' share.
- `npm audit` reports 0 issues in shipped packages and 12 low/moderate in
  the build toolchain (`typescript-eslint`'s `minimatch`, `workbox-build`'s
  `glob`); CI annotates them. ESLint 9 is out of support; moving to 10 is
  its own change.
