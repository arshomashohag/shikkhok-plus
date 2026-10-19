# Releasing the Android app

```bash
git tag v0.2.0 && git push origin v0.2.0
```

That is the whole release. The tag triggers `release-android.yml`,
which builds, runs both gates, signs, and attaches everything to a
**draft** GitHub release for you to review.

## One-time setup

### 1. The upload key

**Generate it once and never lose it.** With Play App Signing, Google
holds the real signing key and this is only the *upload* key — losing
it is recoverable through Play support, which is the entire reason to
use App Signing rather than managing the signing key yourself.

```bash
keytool -genkeypair -v \
  -keystore upload.jks \
  -alias upload \
  -keyalg RSA -keysize 4096 -validity 10000
```

Store `upload.jks` somewhere durable and outside the repository. Then:

```bash
base64 -i upload.jks | pbcopy
```

### 2. Secrets, under Settings → Environments → `android-release`

| Name | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | the clipboard contents from above |
| `ANDROID_KEYSTORE_PASSWORD` | the store password you chose |
| `ANDROID_KEY_ALIAS` | `upload` |
| `ANDROID_KEY_PASSWORD` | the key password you chose |

And one variable:

| Name | Value |
|---|---|
| `ANDROID_API_BASE_URL` | `https://api.shikkhokplus.nirmatabd.com` |

The workflow refuses a non-https base URL. A release build talks to
the real backend over the public internet carrying phone numbers and
OTPs; plain http would ship them in cleartext and the app would work
perfectly, so nothing else would report it.

**The environment matters.** Without it, a workflow edit on any
branch could read the upload key.

## What the build enforces

Two gates, both from `team.md`, wired to `bundleRelease` so they
cannot be skipped on the release that matters.

**The merged-manifest permission allowlist.** The release manifest
must declare exactly the approved permissions. It checks the *merged*
manifest, not the source one — the source is what we wrote, the merged
one is what a transitive SDK has added, and the difference is the
point. It also asserts the absence of
`com.google.android.gms.permission.AD_ID`, the declaration Play's
Families review looks for.

Currently approved: `android.permission.INTERNET`, plus AndroidX's
self-scoped `DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` (prefixed with
our own package — a hardening measure, not a user-facing grant).

**The minified-DEX identifier scan.** The release DEX must reference
no device identifier: `getImei`, `getSubscriberId`,
`getSimSerialNumber`, `getLine1Number`, `getSerial`, `getMacAddress`,
`getBSSID`, `getSSID`, `AdvertisingIdClient`, `android_id`.

Two things that scan learned the hard way, recorded so nobody
"simplifies" them back:

- It matches **whole identifiers**, not substrings. A bare `contains`
  flagged `getSerial` inside `getSerialization` and `getSerializedSize`
  on the first run — protobuf and kotlinx.serialization reported as
  device-identifier access. A gate whose findings are usually wrong
  gets switched off, and then the one real finding never surfaces.
- It looks for `android_id`, the lowercase **value**, not `ANDROID_ID`,
  the field name. `Settings.Secure.ANDROID_ID` is a compile-time
  String constant, so javac inlines it and the field name never
  reaches the DEX. Found by injecting a deliberate ANDROID_ID read:
  the gate passed, and the DEX showed `ANDROID_ID` absent while
  `android_id` was present. Listing only the field name meant this
  gate could never have caught the single most likely identifier an
  SDK would read.

Both run on the **R8-minified** build, because a debug build can
differ in which dependencies are present and the release AAB is what
ships.

## Rehearsing without spending a version

```
Actions → release-android → Run workflow → version: 0.2.0
```

A dry run: it builds and runs every gate but creates no GitHub
release. Worth doing before a real tag, because **a version number
spent on a failed build is spent permanently** — Play reserves every
versionCode it has seen.

## Release notes

Generated from conventional commits since the previous tag, into
`CHANGELOG.md` and a Play-limited `play-release-notes.txt`.

**They are a draft.** Commit subjects are written for developers:
"count cannot derive from an unknown ARN" is accurate and meaningless
to a teacher reading the store listing. Edit before publishing.

## Uploading

1. Download the `release-<version>` artifact from the run
2. Play Console → Testing → Internal testing → Create release
3. Upload `android-release.aab`
4. Upload `mapping.txt` under App bundle → deobfuscation file —
   without it a crash report from closed testing is unreadable
5. Paste the **edited** release notes

The Data Safety form is answered from what is in the build. Both
gates passed, so no device or advertising identifier is present.

## Rolling back

There is no rollback. An installed app cannot be forced to update and
a published versionCode cannot be reused — ship a new version with a
higher code. This is why the dry run exists.
