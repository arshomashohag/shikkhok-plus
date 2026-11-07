# ShikkhokPlus public site

The marketing pages, FAQ and contact details, in English (`/`, `/faq/`) and
Bangla (`/bn/`, `/bn/faq/`), plus a bilingual 404 page. Plain HTML and one
stylesheet: **no JavaScript at all**, so the Content-Security-Policy can be
`default-src 'none'` with only same-origin styles, images and fonts.

Served at the project zone's apex by its own CloudFront distribution
(`infra/modules/site`):

| Environment | Site                                 | Also answers (301 to the site)           |
| ----------- | ------------------------------------ | ---------------------------------------- |
| staging     | `https://shikkhokplus.<apex>/`       | `https://www.shikkhokplus.<apex>/`       |
| production  | `https://shikkhokplus-prod.<apex>/`  | `https://www.shikkhokplus-prod.<apex>/`  |

## Run it

```bash
make site                                   # build + every test, as CI runs it
cd site && npm run build                    # build only, into site/dist
python3 -m http.server 8080 -d site/dist    # preview at http://localhost:8080
```

Node 22, no dependencies, nothing to install.

| Variable      | What it sets                                         | Local default            |
| ------------- | ---------------------------------------------------- | ------------------------ |
| `SITE_URL`    | canonical and hreflang links, `og:url`, the sitemap  | `http://localhost:8080`  |
| `WEB_APP_URL` | every "Open the web app" link                        | `http://localhost:5173/` |
| `API_URL`     | the account-deletion link (`<API_URL>/account-deletion`) | `http://localhost:8000` |

The deploy reads all three from SSM (`site-url`, `web-url`, `api-url`).
The Play Store link and the contact address are constants in `build.mjs`.

## How it is put together

```
src/partials/layout.html        the document: head, meta, OG, skip link
src/partials/header.<en|bn|404>.html, footer.<en|bn|404>.html
src/pages/**.html               one fragment per page, with JSON front matter
src/assets/**                   CSS, fonts, images -- content-hashed on build
src/static/                     copied as is (favicon.ico, the font licence)
```

A page starts with `<!--meta {"title": "...", "description": "..."} -->`.
`{{NAME}}` inserts an HTML-escaped value and `{{{NAME}}}` a raw one; an
unknown name fails the build. A page's language comes from its path
(`/bn/...` is Bangla) and **every English page must have a Bangla twin**
at `/bn/<same path>` and the reverse, or the build fails -- so the
language switch and the hreflang links can never point at nothing. A page
marked `"standalone": true` (the 404) is exempt, gets `noindex` and stays
out of the sitemap.

Copy follows the app: features are described from `web/README.md`, the
specs in `docs/superpowers/specs/` and the Android string bundles, and
Bangla terms (ফি, বকেয়া, পেমেন্ট যাচাই, রুটিন, হাজিরা, শিক্ষকপ্লাস) are the
ones `android/src/main/res/values-bn/strings.xml` uses. Do not describe a
feature that is not built.

Screenshots are cropped from `store_listing/` and re-encoded as WebP at
480 px wide (about 25 kB each). The Dues image stops above the store
image's "Remind ... · SMS" button, because reminders are delivered in the
app, not by SMS. The fonts are the app's own merged Noto Sans + Noto Sans
Bengali (regular and semibold only).

## What the tests hold (`site/test/`)

`build.test.mjs` builds into a temporary directory with distinctive URLs
and checks: every page builds; no placeholder or localhost default
survives; every internal link, asset and in-page `#fragment` resolves;
every asset's name carries the hash of its content and every asset is
referenced; no `<script>`, `<style>`, `style=` or inline handler; every
page has `lang`, a title, a description, and (unless standalone) a
canonical URL and `en`/`bn`/`x-default` alternates; the two languages
have the same pages, the same home sections and the same FAQ questions
(12-16, same ids, same order); robots.txt and the sitemap; size budgets.

`site-router.test.mjs` runs the CloudFront Function
(`infra/modules/site/functions/site-router.js`) as written: `www.` to the
apex with the path and query kept, `/faq` to `/faq/`, `/faq/` to
`/faq/index.html`, and real files passed through.

## Caching

| Object                                   | `Cache-Control`                          |
| ---------------------------------------- | ---------------------------------------- |
| `assets/*` (hashed)                      | `public, max-age=31536000, immutable`    |
| pages, `sitemap.xml`, `robots.txt`, etc. | `public, max-age=300, s-maxage=31536000` |

The distribution's cache policy honours the origin's header within
[0, one year], with nothing in the cache key (no cookie, header or query
string) and gzip and Brotli on. So the edge keeps everything for a year;
browsers keep assets for a year -- safe, because a changed file is a new
URL -- and revalidate pages after five minutes. Each deploy invalidates
`/*`, so a release is visible everywhere as soon as the invalidation
completes. A missing page (S3's 403 or 404) becomes `/404.html` with a 404
status, cached for one minute.

## Deploying

`deploy.yml`'s `site` job, which needs the `infrastructure` job and not the
API release (the site calls no API):

1. read `site-bucket`, `site-distribution-id`, `site-url`, `web-url` and
   `api-url` from SSM, failing clearly if any is missing;
2. `npm run build` with those URLs (the tests ran on the pull request);
3. upload hashed assets, then the pages, each with an explicit
   Content-Type and the Cache-Control above;
4. invalidate `/*` and wait for it;
5. only then delete objects the new build no longer has;
6. smoke through CloudFront: both home pages and both FAQs, the page
   names this build's stylesheet, `/faq` is a 301 to `/faq/`, the
   stylesheet is `immutable`, the CSP header is present, a missing page
   is a 404, and `www.` is a 301 to the apex.

**First deploy after this change needs `infra/bootstrap` re-applied, from
a laptop, as bootstrap always is**: the infrastructure role gains the
right to create `shikkhokplus-*-site-*` buckets, and the deploy role gains
the site upload and the three `site-*` parameters. Until then the
infrastructure job fails at `CreateBucket` with AccessDenied, or the site
job stops at "Cannot read the site's target from SSM", and nothing
changes. The first apply also issues a certificate for the apex and
`www.` and creates their alias records; the smoke retries for three
minutes while those propagate.
